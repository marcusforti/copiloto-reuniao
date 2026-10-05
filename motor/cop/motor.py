"""O motor: roda como processo próprio (fora do Claude Code, então não morre no limite de 2 h de tarefas em
segundo plano). Captura → VAD → transcrição → filtros → transcricao.jsonl, e mantém estado.json para o painel."""
import json
import os
import signal
import threading
import time
from datetime import datetime

from . import config, filtros, sistema
from .audio import CLIENTE, VOCE, FonteArquivo, Mixer, criar_fonte
from .sessao import Sessao, escrever_json, ler_json
from .vad import Segmentador


class Motor:
    def __init__(self, sessao: Sessao, cfg: dict | None = None, arquivos: dict | None = None, velocidade: float = 1.0):
        self.sessao = sessao
        self.cfg = cfg or config.carregar()
        self.chaves = config.chaves()
        self.arquivos = arquivos
        self.velocidade = velocidade
        self.parar = threading.Event()
        self.alertas = {}
        self.inicio = time.time()
        self.contagem = {VOCE: 0, CLIENTE: 0}
        self.ultima_fala = {VOCE: 0.0, CLIENTE: 0.0}
        self.ultimo_agora = None
        self.servidor = None
        self.cerebro = None
        briefing = sessao.ler_briefing()
        self.vocabulario = list(self.cfg.get("vocabulario") or []) + list(briefing.get("vocabulario") or [])
        for k in ("cliente", "empresa", "oferta"):
            if briefing.get(k):
                self.vocabulario.append(briefing[k])
        self.eco = filtros.FiltroEco(self._gravar, ativo=True, limiar=0.8 if self.cfg.get("fone", True) else 0.6)

    # ---------------- alertas ----------------
    def alerta(self, tipo: str, msg: str, temporario: bool = False):
        anterior = self.alertas.get(tipo, {}).get("msg")
        self.alertas[tipo] = {"msg": msg, "ts": time.time(), "temporario": temporario}
        if anterior != msg and not (anterior and tipo == "atraso"):
            self.sessao.logar(f"ALERTA {tipo}: {msg}")

    def limpar_alerta(self, tipo: str):
        self.alertas.pop(tipo, None)

    # ---------------- pipeline ----------------
    def _ao_texto(self, canal, texto, ts):
        limpo = filtros.limpar(texto)
        if limpo:
            self.eco.entrada(canal, limpo, ts)

    def _gravar(self, canal, texto, ts):
        self.sessao.adicionar_fala(canal, texto, ts)
        self.contagem[canal] += 1
        self.ultima_fala[canal] = time.time()

    def _montar_transcricao(self):
        modo = self.cfg.get("transcricao", "local")
        if modo == "local":
            from .transcricao_local import TranscritorLocal

            self.stt = TranscritorLocal(self.cfg, self._ao_texto, self.sessao.logar, self.alerta, self.vocabulario)
            self.seg = {
                VOCE: Segmentador(lambda a, t: self.stt.enfileirar(VOCE, a, t)),
                CLIENTE: Segmentador(lambda a, t: self.stt.enfileirar(CLIENTE, a, t)),
            }

            def ao_bloco(canal, bloco, ts):
                self.seg[canal].alimentar(bloco, ts)

        else:
            from .transcricao_api import TranscritorAPI

            self.stt = TranscritorAPI(self.cfg, self.chaves, self._ao_texto, self.sessao.logar, self.alerta, self.vocabulario)
            self.seg = {}

            def ao_bloco(canal, bloco, ts):
                self.stt.bloco(canal, bloco, ts)

        return ao_bloco

    # ---------------- estado / alertas automáticos ----------------
    def _verificar(self):
        agora = time.time()
        rodando = agora - self.inicio
        mx = self.mixer
        # microfone sem nenhum som (dispositivo errado ou mudo) — o problema que apagou a voz do vendedor em 02/10
        if self.arquivos is None and rodando > 20:
            if agora - mx.ultimo_som[VOCE] > 45 and agora - mx.ultimo_som[CLIENTE] < 60:
                self.alerta("mic", "Não estou ouvindo VOCÊ há quase 1 minuto. Confira se o microfone certo está ativo (fone/headset) ou se você está no mudo.")
            elif agora - mx.ultimo_som[VOCE] < 10:
                self.limpar_alerta("mic")
            if agora - mx.ultimo_som[CLIENTE] > 90 and agora - mx.ultimo_som[VOCE] < 60:
                self.alerta("cliente", "Não estou ouvindo o CLIENTE. O áudio da reunião está saindo por um fone/caixa que eu não estou escutando?")
            elif agora - mx.ultimo_som[CLIENTE] < 10:
                self.limpar_alerta("cliente")
        erro_audio = getattr(self.fonte, "erro", None)
        if erro_audio:
            self.alerta("audio", erro_audio)
        else:
            self.limpar_alerta("audio")
        livre = sistema.ram_livre_gb()
        if livre < 0.6:
            self.alerta("memoria", f"Memória do PC quase no fim ({livre:.1f} GB livres). Feche abas e programas.")
        elif livre > 1.2:
            self.limpar_alerta("memoria")
        atraso = self.stt.atraso() if hasattr(self, "stt") else 0
        if atraso > 25:
            self.alerta("atraso", f"A transcrição está {atraso:.0f}s atrasada (PC sobrecarregado).", temporario=True)
        elif atraso < 8:
            self.limpar_alerta("atraso")
        for k in [k for k, v in self.alertas.items() if v.get("temporario") and agora - v["ts"] > 60]:
            self.alertas.pop(k, None)

    def _registrar_historico(self):
        c = ler_json(self.sessao.conselhos, None)
        if not c or not c.get("agora") or c.get("agora") == self.ultimo_agora:
            return
        self.ultimo_agora = c["agora"]
        item = {"hora": c.get("atualizado") or datetime.now().strftime("%H:%M"), "texto": c["agora"], "porque": c.get("porque", "")}
        with open(self.sessao.historico, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def estado(self, status="rodando") -> dict:
        mx = self.mixer
        info = self.stt.info() if hasattr(self, "stt") else {}
        return {
            "status": status,
            "pid": os.getpid(),
            "inicio": self.inicio,
            "atualizado": time.time(),
            "transcricao": info,
            "cerebro": self.cfg.get("cerebro", "claude-code"),
            "niveis": {VOCE: round(mx.nivel[VOCE], 1), CLIENTE: round(mx.nivel[CLIENTE], 1)},
            "ultimo_som": {VOCE: mx.ultimo_som[VOCE], CLIENTE: mx.ultimo_som[CLIENTE]},
            "falas": dict(self.contagem),
            "dispositivos": getattr(self.fonte, "dispositivos", {}),
            "alertas": [{"tipo": k, **v} for k, v in self.alertas.items()],
            "atraso_s": round(self.stt.atraso(), 1) if hasattr(self, "stt") else 0,
            "eco_descartado": self.eco.descartadas,
            "ram_livre_gb": round(sistema.ram_livre_gb(), 1),
            "painel": getattr(self.servidor, "urls", {}),
            "rotulos": {VOCE: self.cfg.get("rotulo_voce", "VOCÊ"), CLIENTE: self.cfg.get("rotulo_cliente", "CLIENTE")},
        }

    # ---------------- ciclo de vida ----------------
    def rodar(self):
        s = self.sessao
        s.logar(f"motor iniciando (pid {os.getpid()}) transcrição={self.cfg.get('transcricao')} cérebro={self.cfg.get('cerebro')}")
        escrever_json(s.estado, {"status": "iniciando", "pid": os.getpid(), "atualizado": time.time()})
        try:
            ao_bloco = self._montar_transcricao()
            self.mixer = Mixer(ao_bloco)
            if self.arquivos:
                self.fonte = FonteArquivo(self.mixer, self.arquivos, s.logar, self.velocidade)
            else:
                self.fonte = criar_fonte(self.mixer, self.cfg, s.logar)
            from .servidor import Servidor

            self.servidor = Servidor(s, self.cfg)
            self.servidor.iniciar()
            self.stt.iniciar()
            self.mixer.iniciar()
            self.fonte.iniciar()
            if self.cfg.get("cerebro") == "api":
                from .cerebro_api import CerebroAPI

                self.cerebro = CerebroAPI(self.cfg, self.chaves, s, s.logar, self.alerta)
                self.cerebro.iniciar()
        except Exception as e:
            s.logar(f"ERRO ao iniciar: {e!r}")
            escrever_json(s.estado, {"status": "erro", "erro": str(e), "pid": os.getpid(), "atualizado": time.time()})
            raise

        def _sinal(*_):
            self.parar.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _sinal)
            except Exception:
                pass

        while not self.parar.is_set():
            if s.parar.exists():
                break
            if isinstance(self.fonte, FonteArquivo) and self.fonte.terminou.is_set():
                time.sleep(3)
                for seg in self.seg.values():
                    seg.descarregar()
                self.stt.encerrar(esperar_s=60)
                break
            try:
                self.eco.tick()
                self._verificar()
                self._registrar_historico()
                escrever_json(s.estado, self.estado())
            except Exception as e:
                s.logar(f"erro no laço principal: {e!r}")
            self.parar.wait(1.0)
        self.encerrar()

    def encerrar(self):
        s = self.sessao
        s.logar("motor encerrando")
        try:
            self.fonte.encerrar()
            self.mixer.encerrar()
            for seg in getattr(self, "seg", {}).values():
                seg.descarregar()
            self.stt.encerrar(esperar_s=20)
            self.eco.descarregar()
            if self.cerebro:
                self.cerebro.encerrar()
            self._registrar_historico()
        except Exception as e:
            s.logar(f"erro ao encerrar: {e!r}")
        escrever_json(s.estado, self.estado("parado"))
        try:
            s.parar.unlink(missing_ok=True)
        except Exception:
            pass
        if self.servidor:
            self.servidor.encerrar()
