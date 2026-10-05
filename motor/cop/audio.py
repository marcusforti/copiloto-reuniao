"""Captura de áudio: microfone (VOCÊ) e áudio do sistema (CLIENTE).

Tudo vira float32 mono 16 kHz e entra no Mixer, que entrega blocos de 100 ms por canal num relógio fixo.

Windows: PyAudioWPatch (WASAPI + loopback) e pycaw para achar o dispositivo de COMUNICAÇÃO padrão,
         que é o que Meet/Zoom/Teams usam. O loopback é aberto em TODAS as saídas ativas: se o fone
         Bluetooth trocar para o modo "viva-voz" (outro dispositivo), a voz do cliente continua chegando.
Mac:     sounddevice. Microfone padrão + dispositivo "BlackHole" para o áudio do sistema.
Arquivo: simulação (demo/teste) lendo dois WAV em tempo real.
"""
import threading
import time
import wave
from collections import deque

import numpy as np

from .sistema import SO

TAXA = 16000
BLOCO = 1600  # 100 ms

VOCE, CLIENTE = "voce", "cliente"


class _Reamostrador:
    def __init__(self, taxa_in: int):
        self.taxa_in = int(taxa_in)
        self.rs = None
        if self.taxa_in != TAXA:
            try:
                import soxr

                self.rs = soxr.ResampleStream(self.taxa_in, TAXA, 1, dtype="float32")
            except Exception:
                self.rs = None

    def __call__(self, x: np.ndarray) -> np.ndarray:
        if self.taxa_in == TAXA:
            return x
        if self.rs is not None:
            return self.rs.resample_chunk(x)
        # fallback simples: média móvel + interpolação
        n = max(1, int(round(self.taxa_in / TAXA)))
        if n > 1:
            x = np.convolve(x, np.ones(n, dtype=np.float32) / n, mode="same")
        m = int(len(x) * TAXA / self.taxa_in)
        if m <= 0:
            return np.zeros(0, np.float32)
        return np.interp(np.linspace(0, len(x) - 1, m), np.arange(len(x)), x).astype(np.float32)


# --------------------------------------------------------------------------------------
# Mixer: relógio de 100 ms. Soma todas as fontes de um canal (ex.: várias saídas em loopback).
# --------------------------------------------------------------------------------------
class Mixer:
    def __init__(self, ao_bloco):
        self.ao_bloco = ao_bloco  # fn(canal, bloco float32[1600], ts)
        self.buf = {}  # chave -> deque de arrays
        self.tam = {}
        self.canal_de = {}
        self.pronto = {}
        self.trava = threading.Lock()
        self.parar = threading.Event()
        self.nivel = {VOCE: -90.0, CLIENTE: -90.0}
        self.ultimo_som = {VOCE: 0.0, CLIENTE: 0.0}
        self.ultimo_pacote = {}
        self.t = None

    def entrada(self, canal: str, chave: str, x: np.ndarray) -> None:
        if x is None or len(x) == 0:
            return
        with self.trava:
            if chave not in self.buf:
                self.buf[chave] = deque()
                self.tam[chave] = 0
                self.pronto[chave] = False
            self.canal_de[chave] = canal
            self.buf[chave].append(x.astype(np.float32, copy=False))
            self.tam[chave] += len(x)
            self.ultimo_pacote[chave] = time.monotonic()
            # mais de 1,5 s acumulado = relógio do dispositivo adiantado: descarta o excesso
            while self.tam[chave] > TAXA * 3 // 2 and self.buf[chave]:
                velho = self.buf[chave].popleft()
                self.tam[chave] -= len(velho)

    def remover(self, chave: str) -> None:
        with self.trava:
            for d in (self.buf, self.tam, self.canal_de, self.pronto, self.ultimo_pacote):
                d.pop(chave, None)

    def _tirar(self, chave: str, n: int) -> np.ndarray:
        out = np.zeros(n, np.float32)
        q = self.buf[chave]
        # só começa a puxar depois de 200 ms guardados (evita picotar a fala por jitter)
        if not self.pronto[chave]:
            if self.tam[chave] < BLOCO * 2:
                return out
            self.pronto[chave] = True
        i = 0
        while i < n and q:
            a = q[0]
            k = min(n - i, len(a))
            out[i : i + k] = a[:k]
            i += k
            if k == len(a):
                q.popleft()
            else:
                q[0] = a[k:]
        self.tam[chave] -= i
        if self.tam[chave] <= 0:
            self.tam[chave] = 0
            self.pronto[chave] = False
        return out

    def _loop(self):
        prox = time.monotonic()
        while not self.parar.is_set():
            prox += BLOCO / TAXA
            espera = prox - time.monotonic()
            if espera > 0:
                time.sleep(espera)
            elif espera < -1.0:  # PC travou: não tenta recuperar o atraso todo
                prox = time.monotonic()
            agora = time.time()
            blocos = {VOCE: np.zeros(BLOCO, np.float32), CLIENTE: np.zeros(BLOCO, np.float32)}
            with self.trava:
                for chave in list(self.buf):
                    canal = self.canal_de.get(chave)
                    if canal in blocos:
                        blocos[canal] += self._tirar(chave, BLOCO)
            for canal, b in blocos.items():
                np.clip(b, -1.0, 1.0, out=b)
                rms = float(np.sqrt(np.mean(b * b)) + 1e-9)
                db = 20 * np.log10(rms)
                self.nivel[canal] = max(db, self.nivel[canal] - 3.0)  # decaimento suave para o medidor
                if db > -45:
                    self.ultimo_som[canal] = agora
                try:
                    self.ao_bloco(canal, b, agora)
                except Exception:
                    pass

    def iniciar(self):
        self.t = threading.Thread(target=self._loop, name="mixer", daemon=True)
        self.t.start()

    def encerrar(self):
        self.parar.set()


# --------------------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------------------
class FonteWindows:
    def __init__(self, mixer: Mixer, cfg: dict, logar=print):
        import pyaudiowpatch as pa

        self.pa_mod = pa
        self.mixer = mixer
        self.cfg = cfg
        self.logar = logar
        self.p = None
        self.mic = None
        self.loops = {}
        self.parar = threading.Event()
        self.chave_mic = None
        self.assinatura = None
        self.t = None
        self.dispositivos = {"microfone": None, "saidas": []}
        self.pronto = threading.Event()

    # ---- nomes dos dispositivos padrão (papel "comunicação", o que apps de reunião usam) ----
    def _padrao(self, fluxo: int, papel: int = 2):
        try:
            from comtypes import CLSCTX_ALL, CoCreateInstance
            from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
            from pycaw.constants import CLSID_MMDeviceEnumerator
            from pycaw.utils import AudioUtilities

            enum = CoCreateInstance(CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, CLSCTX_ALL)
            dev_id = enum.GetDefaultAudioEndpoint(fluxo, papel).GetId()
            for d in AudioUtilities.GetAllDevices():
                if d.id == dev_id:
                    return d.FriendlyName
        except Exception:
            return None
        return None

    def _wasapi(self):
        return self.p.get_host_api_info_by_type(self.pa_mod.paWASAPI)["index"]

    def _achar_mic(self):
        pedido = (self.cfg.get("microfone") or "auto").lower()
        wasapi = self._wasapi()
        cands = [self.p.get_device_info_by_index(i) for i in range(self.p.get_device_count())]
        cands = [
            d for d in cands if d["hostApi"] == wasapi and d["maxInputChannels"] > 0 and not d.get("isLoopbackDevice")
        ]
        if pedido != "auto":
            for d in cands:
                if pedido in d["name"].lower():
                    return d
        nome = self._padrao(1, 2) or self._padrao(1, 0)
        if nome:
            for d in cands:
                if d["name"].startswith(nome[:28]) or nome.startswith(d["name"][:28]):
                    return d
        try:
            return self.p.get_default_wasapi_device()  # microfone padrão
        except Exception:
            return cands[0] if cands else None

    def _abrir(self, info, canal, chave):
        rs = _Reamostrador(int(info["defaultSampleRate"]))
        ch = max(1, int(info["maxInputChannels"]))
        mixer = self.mixer
        pa = self.pa_mod

        def cb(data, frames, t, status):
            x = np.frombuffer(data, np.int16).astype(np.float32) / 32768.0
            if ch > 1:
                x = x.reshape(-1, ch).mean(axis=1)
            mixer.entrada(canal, chave, rs(x))
            return (None, pa.paContinue)

        taxa = int(info["defaultSampleRate"])
        return self.p.open(
            format=pa.paInt16,
            channels=ch,
            rate=taxa,
            input=True,
            input_device_index=info["index"],
            frames_per_buffer=taxa // 20,
            stream_callback=cb,
        )

    def _fechar_tudo(self):
        for s in [self.mic] + list(self.loops.values()):
            try:
                if s:
                    s.stop_stream()
                    s.close()
            except Exception:
                pass
        for chave in list(self.mixer.buf):
            self.mixer.remover(chave)
        self.mic, self.loops = None, {}
        if self.p:
            try:
                self.p.terminate()
            except Exception:
                pass
        self.p = None

    def _abrir_tudo(self):
        self.p = self.pa_mod.PyAudio()
        mic = self._achar_mic()
        if mic:
            try:
                self.mic = self._abrir(mic, VOCE, "mic")
                self.chave_mic = mic["name"]
                self.dispositivos["microfone"] = mic["name"]
            except Exception as e:
                self.logar(f"falha ao abrir microfone {mic['name']}: {e}")
        pedido = (self.cfg.get("saida") or "auto").lower()
        saidas = []
        for lb in self.p.get_loopback_device_info_generator():
            if pedido != "auto" and pedido not in lb["name"].lower():
                continue
            if len(self.loops) >= 8:
                break
            try:
                self.loops[lb["name"]] = self._abrir(lb, CLIENTE, "lb:" + lb["name"])
                saidas.append(lb["name"].replace(" [Loopback]", ""))
            except Exception as e:
                self.logar(f"falha ao abrir saída {lb['name']}: {e}")
        self.dispositivos["saidas"] = saidas
        self.assinatura = self._assinatura()
        self.logar(f"microfone: {self.dispositivos['microfone']} | saídas: {', '.join(saidas) or 'nenhuma'}")

    def _assinatura(self):
        return (self._padrao(1, 2), self._padrao(0, 2), self._padrao(0, 0), self._contar_endpoints())

    def _contar_endpoints(self):
        try:
            from pycaw.utils import AudioUtilities

            return len([d for d in AudioUtilities.GetAllDevices() if str(getattr(d, "state", "")).endswith("Active")])
        except Exception:
            return None

    def _vigiar(self):
        try:
            import comtypes

            comtypes.CoInitialize()
        except Exception:
            pass
        self._abrir_tudo()
        self.pronto.set()
        mic_parado_desde = None
        while not self.parar.wait(2.0):
            try:
                mudou = self._assinatura() != self.assinatura
                idade_mic = time.monotonic() - self.mixer.ultimo_pacote.get("mic", 0)
                if idade_mic > 3:
                    mic_parado_desde = mic_parado_desde or time.monotonic()
                else:
                    mic_parado_desde = None
                if mudou or (mic_parado_desde and time.monotonic() - mic_parado_desde > 2):
                    motivo = "dispositivo de áudio mudou" if mudou else "microfone parou de mandar som"
                    self.logar(f"reconectando: {motivo}")
                    self._fechar_tudo()
                    time.sleep(0.8)
                    self._abrir_tudo()
                    mic_parado_desde = None
            except Exception as e:
                self.logar(f"erro no vigia de áudio: {e}")
        self._fechar_tudo()

    def iniciar(self):
        self.t = threading.Thread(target=self._vigiar, name="audio-win", daemon=True)
        self.t.start()

    def encerrar(self):
        self.parar.set()


# --------------------------------------------------------------------------------------
# Mac (sounddevice + BlackHole)
# --------------------------------------------------------------------------------------
class FonteMac:
    def __init__(self, mixer: Mixer, cfg: dict, logar=print):
        import sounddevice as sd

        self.sd = sd
        self.mixer = mixer
        self.cfg = cfg
        self.logar = logar
        self.streams = []
        self.parar = threading.Event()
        self.dispositivos = {"microfone": None, "saidas": []}
        self.pronto = threading.Event()

    def _abrir(self, idx, canal, chave):
        info = self.sd.query_devices(idx)
        taxa = int(info["default_samplerate"])
        ch = min(2, int(info["max_input_channels"])) or 1
        rs = _Reamostrador(taxa)
        mixer = self.mixer

        def cb(indata, frames, t, status):
            x = indata.mean(axis=1) if indata.shape[1] > 1 else indata[:, 0]
            mixer.entrada(canal, chave, rs(x.astype(np.float32)))

        s = self.sd.InputStream(device=idx, channels=ch, samplerate=taxa, blocksize=taxa // 20, callback=cb)
        s.start()
        self.streams.append(s)
        return info["name"]

    def _abrir_tudo(self):
        devs = self.sd.query_devices()
        pedido_mic = (self.cfg.get("microfone") or "auto").lower()
        pedido_saida = (self.cfg.get("saida") or "auto").lower()
        mic_idx = self.sd.default.device[0]
        for i, d in enumerate(devs):
            if pedido_mic != "auto" and pedido_mic in d["name"].lower() and d["max_input_channels"] > 0:
                mic_idx = i
        bh = None
        for i, d in enumerate(devs):
            nome = d["name"].lower()
            alvo = pedido_saida if pedido_saida != "auto" else "blackhole"
            if alvo in nome and d["max_input_channels"] > 0:
                bh = i
                break
        if mic_idx is not None and mic_idx >= 0 and mic_idx != bh:
            self.dispositivos["microfone"] = self._abrir(mic_idx, VOCE, "mic")
        if bh is not None:
            self.dispositivos["saidas"] = [self._abrir(bh, CLIENTE, "blackhole")]
        else:
            self.logar("BlackHole não encontrado: a voz do cliente não será captada. Rode o instalador do Mac.")
        self.logar(f"microfone: {self.dispositivos['microfone']} | saídas: {self.dispositivos['saidas']}")

    def _fechar_tudo(self):
        for s in self.streams:
            try:
                s.stop()
                s.close()
            except Exception:
                pass
        self.streams = []
        for chave in list(self.mixer.buf):
            self.mixer.remover(chave)

    def _vigiar(self):
        self._abrir_tudo()
        self.pronto.set()
        while not self.parar.wait(2.0):
            if time.monotonic() - self.mixer.ultimo_pacote.get("mic", 0) > 4:
                self.logar("reconectando: microfone parou de mandar som")
                self._fechar_tudo()
                time.sleep(0.8)
                try:
                    self.sd._terminate()
                    self.sd._initialize()
                except Exception:
                    pass
                self._abrir_tudo()
        self._fechar_tudo()

    def iniciar(self):
        threading.Thread(target=self._vigiar, name="audio-mac", daemon=True).start()

    def encerrar(self):
        self.parar.set()


# --------------------------------------------------------------------------------------
# Arquivo (simulação): dois WAV tocados em tempo real como se fossem a reunião
# --------------------------------------------------------------------------------------
def ler_wav(caminho) -> np.ndarray:
    with wave.open(str(caminho)) as w:
        taxa, ch, larg = w.getframerate(), w.getnchannels(), w.getsampwidth()
        dados = w.readframes(w.getnframes())
    if larg != 2:
        raise ValueError("WAV precisa ser 16 bits")
    x = np.frombuffer(dados, np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return _Reamostrador(taxa)(x)


class FonteArquivo:
    def __init__(self, mixer: Mixer, arquivos: dict, logar=print, velocidade: float = 1.0):
        self.mixer = mixer
        self.faixas = {c: ler_wav(a) for c, a in arquivos.items() if a}
        self.logar = logar
        self.velocidade = velocidade
        self.parar = threading.Event()
        self.terminou = threading.Event()
        self.dispositivos = {"microfone": "arquivo (simulação)", "saidas": ["arquivo (simulação)"]}

    def _loop(self):
        pos = 0
        total = max((len(x) for x in self.faixas.values()), default=0)
        passo = 800  # 50 ms
        prox = time.monotonic()
        while pos < total and not self.parar.is_set():
            for canal, x in self.faixas.items():
                trecho = x[pos : pos + passo]
                if len(trecho):
                    self.mixer.entrada(canal, "arq:" + canal, trecho)
            pos += passo
            prox += passo / TAXA / self.velocidade
            espera = prox - time.monotonic()
            if espera > 0:
                time.sleep(espera)
        self.terminou.set()

    def iniciar(self):
        threading.Thread(target=self._loop, name="audio-arquivo", daemon=True).start()

    def encerrar(self):
        self.parar.set()


def criar_fonte(mixer, cfg, logar=print):
    if SO == "Windows":
        return FonteWindows(mixer, cfg, logar)
    if SO == "Darwin":
        return FonteMac(mixer, cfg, logar)
    raise RuntimeError("Sistema não suportado ainda (só Windows e Mac).")
