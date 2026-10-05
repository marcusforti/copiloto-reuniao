"""Transcrição PAGA, por API em tempo real (a pessoa usa a própria chave).

deepgram  Nova-3, pt-BR. Conta nova ganha US$ 200 de crédito sem cartão (dá centenas de horas).
soniox    stt-rt-v5. O mais barato (≈ US$ 0,12 por hora de áudio por canal).

Cada canal (VOCÊ e CLIENTE) abre um WebSocket próprio. O relógio do Mixer manda áudio contínuo
(inclusive silêncio), então a conexão não cai por inatividade. Se cair, reconecta sozinho.
"""
import asyncio
import json
import os
import threading
import time
from urllib.parse import urlencode

import numpy as np

try:
    import websockets
except Exception:
    websockets = None


def _pcm16(bloco: np.ndarray) -> bytes:
    return (np.clip(bloco, -1, 1) * 32767).astype("<i2").tobytes()


class TranscritorAPI:
    def __init__(self, cfg: dict, chaves: dict, ao_texto, logar=print, alerta=None, vocabulario=None):
        if websockets is None:
            raise RuntimeError("Falta a biblioteca 'websockets' (pip install websockets).")
        self.provedor = cfg["transcricao"]
        self.chave = chaves.get("DEEPGRAM_API_KEY" if self.provedor == "deepgram" else "SONIOX_API_KEY")
        if not self.chave:
            raise RuntimeError(f"Sem chave da API {self.provedor}. Rode: copiloto chave {self.provedor} SUA_CHAVE")
        self.ao_texto = ao_texto
        self.logar = logar
        self.alerta = alerta or (lambda *a, **k: None)
        self.termos = [t for t in (vocabulario or []) if t][:50]
        self.loop = None
        self.filas = {}
        self.parar = threading.Event()
        self.fechando = threading.Event()
        self.t = None
        self.conectado = {"voce": False, "cliente": False}
        self.ultimo_final = 0.0

    # chamado pelo relógio do Mixer (outra thread)
    def bloco(self, canal: str, bloco: np.ndarray, ts: float):
        if self.loop and canal in self.filas:
            dados = _pcm16(bloco)
            try:
                self.loop.call_soon_threadsafe(self._por, canal, dados, ts)
            except RuntimeError:
                pass

    def _por(self, canal, dados, ts):
        q = self.filas[canal]
        if q.qsize() > 100:  # 10 s parados = desconectado; descarta o mais velho
            try:
                q.get_nowait()
            except Exception:
                pass
        q.put_nowait((dados, ts))

    def atraso(self) -> float:
        return 0.0

    async def _deepgram(self, canal):
        params = [
            ("model", "nova-3"),
            ("language", "pt-BR"),
            ("encoding", "linear16"),
            ("sample_rate", "16000"),
            ("channels", "1"),
            ("interim_results", "true"),
            ("endpointing", "400"),
            ("utterance_end_ms", "1200"),
            ("vad_events", "true"),
            ("smart_format", "true"),
            ("punctuate", "true"),
        ] + [("keyterm", t) for t in self.termos]
        url = os.environ.get("COPILOTO_URL_DEEPGRAM", "wss://api.deepgram.com/v1/listen") + "?" + urlencode(params)
        async with websockets.connect(url, additional_headers={"Authorization": f"Token {self.chave}"}, max_size=None) as ws:
            self.conectado[canal] = True
            self.logar(f"deepgram conectado ({canal})")
            partes, t0 = [], None

            async def enviar():
                q = self.filas[canal]
                while not self.parar.is_set():
                    if self.fechando.is_set() and q.empty():
                        break
                    try:
                        dados, ts = await asyncio.wait_for(q.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        await ws.send(json.dumps({"type": "KeepAlive"}))
                        continue
                    await ws.send(dados)
                await ws.send(json.dumps({"type": "CloseStream"}))  # o servidor devolve o que falta e fecha

            async def receber():
                nonlocal partes, t0
                async for bruto in ws:
                    msg = json.loads(bruto)
                    tipo = msg.get("type")
                    if tipo == "Results":
                        alt = msg["channel"]["alternatives"][0]
                        txt = (alt.get("transcript") or "").strip()
                        if msg.get("is_final") and txt:
                            if t0 is None:
                                t0 = time.time() - float(msg.get("duration", 0))
                            partes.append(txt)
                        if msg.get("speech_final") and partes:
                            self._emitir(canal, " ".join(partes), t0)
                            partes, t0 = [], None
                    elif tipo == "UtteranceEnd" and partes:
                        self._emitir(canal, " ".join(partes), t0)
                        partes, t0 = [], None
                    elif tipo == "Error" or msg.get("err_code"):
                        raise RuntimeError(str(msg)[:300])
                if partes:  # conexão fechou com texto final ainda não emitido
                    self._emitir(canal, " ".join(partes), t0)
                    partes, t0 = [], None

            await asyncio.gather(enviar(), receber())

    async def _soniox(self, canal):
        url = os.environ.get("COPILOTO_URL_SONIOX", "wss://stt-rt.soniox.com/transcribe-websocket")
        config = {
            "api_key": self.chave,
            "model": "stt-rt-v5",
            "audio_format": "pcm_s16le",
            "sample_rate": 16000,
            "num_channels": 1,
            "language_hints": ["pt"],
            "enable_endpoint_detection": True,
            "context": {"general": [{"key": "domain", "value": "Reunião de vendas ou mentoria"}], "terms": self.termos},
        }
        async with websockets.connect(url, max_size=None) as ws:
            await ws.send(json.dumps(config))
            self.conectado[canal] = True
            self.logar(f"soniox conectado ({canal})")
            buf, t0 = [], None

            async def enviar():
                q = self.filas[canal]
                while not self.parar.is_set():
                    if self.fechando.is_set() and q.empty():
                        break
                    try:
                        dados, ts = await asyncio.wait_for(q.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        dados = b"\x00\x00" * 1600  # 100 ms de silêncio mantém a conexão
                    await ws.send(dados)
                await ws.send("")  # frame vazio = fim do áudio; o servidor responde com finished

            async def receber():
                nonlocal buf, t0
                async for bruto in ws:
                    res = json.loads(bruto)
                    if res.get("error_code") is not None:
                        raise RuntimeError(f"{res['error_code']}: {res.get('error_message')}")
                    for tok in res.get("tokens", []):
                        if not tok.get("is_final"):
                            continue
                        if tok.get("text") in ("<end>", "<fin>"):
                            if "".join(buf).strip():
                                self._emitir(canal, "".join(buf).strip(), t0)
                            buf, t0 = [], None
                        else:
                            if t0 is None:
                                t0 = time.time()
                            buf.append(tok["text"])
                    if res.get("finished"):
                        break
                if "".join(buf).strip():  # descarrega o texto final que ficou sem marcador de fim
                    self._emitir(canal, "".join(buf).strip(), t0)
                    buf, t0 = [], None

            await asyncio.gather(enviar(), receber())

    def _emitir(self, canal, texto, t0):
        self.ultimo_final = time.time()
        self.ao_texto(canal, texto, t0 or time.time())

    async def _canal(self, canal):
        espera = 1
        while not self.parar.is_set():
            try:
                if self.provedor == "deepgram":
                    await self._deepgram(canal)
                else:
                    await self._soniox(canal)
                espera = 1
                if self.fechando.is_set():
                    break
            except Exception as e:
                self.conectado[canal] = False
                msg = str(e)
                self.logar(f"{self.provedor} ({canal}) caiu: {msg[:200]}")
                if "401" in msg or "403" in msg or "unauthorized" in msg.lower() or "invalid" in msg.lower() and "key" in msg.lower():
                    self.alerta("api", f"A chave da {self.provedor} foi recusada. Confira com: copiloto chave {self.provedor} NOVA_CHAVE")
                    espera = 30
                elif "402" in msg or "insufficient" in msg.lower() or "balance" in msg.lower():
                    self.alerta("api", f"Acabou o crédito na {self.provedor}.")
                    espera = 60
                else:
                    self.alerta("api", f"Conexão com a {self.provedor} caiu. Reconectando…", temporario=True)
                if self.parar.is_set() or self.fechando.is_set():
                    break
                await asyncio.sleep(espera)
                espera = min(espera * 2, 20)

    def _rodar(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.filas = {"voce": asyncio.Queue(), "cliente": asyncio.Queue()}
        self.loop.run_until_complete(asyncio.gather(self._canal("voce"), self._canal("cliente")))

    def iniciar(self):
        self.t = threading.Thread(target=self._rodar, name="stt-api", daemon=True)
        self.t.start()

    def encerrar(self, esperar_s: float = 0):
        """Para de aceitar áudio, manda o que falta, avisa o provedor do fim e espera as últimas transcrições."""
        self.fechando.set()
        if self.t and self.t.is_alive():
            self.t.join(timeout=min(max(esperar_s, 2), 15))
        self.parar.set()

    def info(self) -> dict:
        return {"motor": self.provedor, "conectado": dict(self.conectado)}
