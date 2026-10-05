"""Transcrição GRÁTIS, no próprio PC, com faster-whisper.

Um modelo só (compartilhado pelos dois canais), uma fila, um trabalhador.
Proteção de memória: se faltar RAM, libera e tenta DE NOVO o mesmo trecho com o mesmo modelo
(em 02/10 a solução de emergência foi trocar para um modelo pior e a qualidade despencou).
Só rebaixa o modelo se falhar várias vezes seguidas, e avisa no painel.

Causa raiz do crash de 02/10 ("mkl_malloc: failed to allocate memory"): com o Intel MKL, o ctranslate2
reserva ~2,2 GB de memória comprometida para o modelo small (o medium passa de 4 GB). Com o navegador e o
Meet abertos, o Windows recusa a alocação. Sem o MKL (backend oneDNN) o mesmo modelo usa ~290 MB, na mesma velocidade.

Cada chamada do Whisper custa ~o mesmo tempo para 2 s ou 25 s de áudio (janela fixa de 30 s). Por isso, quando
há fila, trechos seguidos do mesmo canal são juntados numa chamada só.
"""
import gc
import os
import queue
import threading
import time

import numpy as np

os.environ.setdefault("CT2_USE_MKL", "0")

from . import sistema  # noqa: E402

MAX_JUNTAR_S = 24.0

ESCADA = ["medium", "small", "base", "tiny"]


class TranscritorLocal:
    def __init__(self, cfg: dict, ao_texto, logar=print, alerta=None, vocabulario=None):
        self.cfg = cfg
        self.ao_texto = ao_texto  # fn(canal, texto, ts)
        self.logar = logar
        self.alerta = alerta or (lambda *a, **k: None)
        self.fila = queue.Queue()
        self.modelo_nome = sistema.escolher_modelo(cfg.get("modelo_local", "auto"))
        self.modelo = None
        self.parar = threading.Event()
        self.falhas = []
        self.segundos_na_fila = 0.0
        self.trava = threading.Lock()
        self.prompt = ""
        self.definir_vocabulario(vocabulario or [])
        self.processados = 0
        self.tempo_proc = 0.0
        self.audio_proc = 0.0

    def definir_vocabulario(self, termos):
        termos = [t for t in termos if t][:40]
        # o Whisper aceita um "contexto inicial": nomes próprios aqui viram grafia certa na transcrição
        self.prompt = ("Reunião em português do Brasil. " + ", ".join(termos) + ".") if termos else ""

    def carregar(self):
        from faster_whisper import WhisperModel

        livre = sistema.ram_livre_gb()
        if livre < 1.0:
            self.alerta("memoria", f"Pouca memória livre ({livre:.1f} GB). Feche abas do navegador para a transcrição não falhar.")
        t = time.time()
        self.modelo = WhisperModel(
            self.modelo_nome, device="cpu", compute_type="int8", cpu_threads=sistema.threads_whisper()
        )
        self.logar(f"modelo {self.modelo_nome} carregado em {time.time() - t:.1f}s (RAM livre {livre:.1f} GB)")

    def enfileirar(self, canal, audio, ts):
        with self.trava:
            self.segundos_na_fila += len(audio) / 16000
        self.fila.put((canal, audio, ts))

    def atraso(self) -> float:
        return self.segundos_na_fila

    def _transcrever(self, audio):
        segs, _ = self.modelo.transcribe(
            audio,
            language="pt",
            beam_size=1,
            without_timestamps=True,
            vad_filter=False,
            condition_on_previous_text=False,
            initial_prompt=self.prompt or None,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.2,
            temperature=[0.0, 0.2, 0.4],
        )
        partes = []
        for s in segs:
            if s.no_speech_prob > 0.6 and s.avg_logprob < -0.8:
                continue
            if s.avg_logprob < -1.2:
                continue
            partes.append(s.text.strip())
        return " ".join(partes).strip()

    def _rebaixar(self):
        """Troca por um modelo menor. Nunca deixa a exceção derrubar o trabalhador."""
        while True:
            i = ESCADA.index(self.modelo_nome) if self.modelo_nome in ESCADA else 1
            if i + 1 >= len(ESCADA):
                return False
            antigo = self.modelo_nome
            self.modelo_nome = ESCADA[i + 1]
            self.modelo = None
            gc.collect()
            time.sleep(1)
            try:
                self.carregar()
            except Exception as e:
                self.logar(f"falha ao carregar {self.modelo_nome}: {e}")
                continue
            self.alerta(
                "modelo",
                f"Memória insuficiente: troquei o modelo {antigo} pelo {self.modelo_nome}. A precisão cai um pouco. Feche programas e reinicie para voltar.",
            )
            return True

    def _proximo(self):
        """Pega o próximo trecho e, se houver fila, junta os trechos seguintes do mesmo canal."""
        canal, audio, ts = self.fila.get(timeout=0.5)
        partes, total = [audio], len(audio) / 16000
        pausa = np.zeros(int(0.3 * 16000), np.float32)
        with self.fila.mutex:
            while self.fila.queue:
                c2, a2, _ = self.fila.queue[0]
                if c2 != canal or total + len(a2) / 16000 > MAX_JUNTAR_S:
                    break
                self.fila.queue.popleft()
                partes += [pausa, a2]
                total += len(a2) / 16000
        return canal, (np.concatenate(partes) if len(partes) > 1 else audio), ts

    def _trabalhar(self):
        try:
            self.carregar()
        except Exception as e:
            self.logar(f"ERRO ao carregar modelo: {e}")
            self.alerta("modelo", f"Não consegui carregar o modelo de transcrição: {e}")
            if not self._rebaixar():
                return
        while not self.parar.is_set():
            try:
                canal, audio, ts = self._proximo()
            except queue.Empty:
                continue
            self.ocupado = True
            dur = len(audio) / 16000
            texto, tentativas = None, 0
            while texto is None and tentativas < 3:
                try:
                    t = time.time()
                    texto = self._transcrever(audio)
                    self.tempo_proc += time.time() - t
                    self.audio_proc += dur
                except Exception as e:  # mkl_malloc / MemoryError / RuntimeError de alocação
                    tentativas += 1
                    msg = str(e)
                    self.logar(f"falha na transcrição (tentativa {tentativas}): {msg[:160]}")
                    gc.collect()
                    time.sleep(1.5 * tentativas)
                    agora = time.time()
                    self.falhas = [f for f in self.falhas if agora - f < 300] + [agora]
                    memoria = "alloc" in msg.lower() or "memory" in msg.lower() or isinstance(e, MemoryError)
                    if memoria and len(self.falhas) >= 4:
                        self.falhas = []
                        if self._rebaixar():
                            tentativas = 0
            with self.trava:
                self.segundos_na_fila = max(0.0, self.segundos_na_fila - dur) if not self.fila.empty() else 0.0
            self.processados += 1
            try:
                if texto:
                    self.ao_texto(canal, texto, ts)
            finally:
                self.ocupado = False

    def iniciar(self):
        self.ocupado = False
        self.t = threading.Thread(target=self._trabalhar, name="whisper", daemon=True)
        self.t.start()

    def encerrar(self, esperar_s: float = 0):
        """Espera a fila E o trecho que está sendo transcrito agora (a última fala da reunião não pode se perder)."""
        fim = time.time() + esperar_s
        while esperar_s and (not self.fila.empty() or getattr(self, "ocupado", False)) and time.time() < fim:
            time.sleep(0.2)
        self.parar.set()
        t = getattr(self, "t", None)
        if t and t.is_alive():
            t.join(timeout=max(0.5, fim - time.time()))

    def info(self) -> dict:
        rtf = self.tempo_proc / self.audio_proc if self.audio_proc else None
        return {"motor": "local", "modelo": self.modelo_nome, "velocidade": round(rtf, 2) if rtf else None}
