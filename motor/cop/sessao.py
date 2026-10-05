"""Uma sessão = uma reunião. Tudo fica numa pasta em ~/CopilotoReuniao/sessoes/<data_hora_cliente>/.

transcricao.jsonl   uma fala por linha: {"id","ts","hora","quem","texto"}
conselhos.json      escrito pelo cérebro (Claude Code ou API) e lido pelo painel
historico.jsonl     cada "fale agora" que já apareceu (o motor registra quando muda)
estado.json         status do motor (níveis de áudio, alertas, atraso) atualizado a cada segundo
briefing.json       modo, cliente, oferta, objetivo
motor.log           log do motor
"""
import json
import os
import re
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from . import config

_trava = threading.Lock()


def _slug(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", txt).strip("-").lower()[:40]


def escrever_json(caminho: Path, dados) -> None:
    """Escrita atômica: o painel nunca lê um arquivo pela metade."""
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    for _ in range(5):
        try:
            os.replace(tmp, caminho)
            return
        except PermissionError:  # Windows: arquivo aberto por outro processo
            time.sleep(0.05)


def ler_json(caminho: Path, padrao=None):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except Exception:
        return padrao


class Sessao:
    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)
        self.transcricao = self.pasta / "transcricao.jsonl"
        self.conselhos = self.pasta / "conselhos.json"
        self.historico = self.pasta / "historico.jsonl"
        self.estado = self.pasta / "estado.json"
        self.briefing = self.pasta / "briefing.json"
        self.log = self.pasta / "motor.log"
        self.cursor = self.pasta / "cursor_acompanhar.txt"
        self.parar = self.pasta / "PARAR"
        self._prox_id = None

    # ---------- criação / localização ----------
    @classmethod
    def nova(cls, cliente: str = "", modo: str = "venda") -> "Sessao":
        nome = datetime.now().strftime("%Y-%m-%d_%H%M")
        if cliente:
            nome += "_" + _slug(cliente)
        pasta = config.PASTA_SESSOES / nome
        n = 2
        while pasta.exists():
            pasta = config.PASTA_SESSOES / f"{nome}-{n}"
            n += 1
        pasta.mkdir(parents=True)
        return cls(pasta)

    @classmethod
    def ultima(cls) -> "Sessao | None":
        if not config.PASTA_SESSOES.exists():
            return None
        pastas = sorted((p for p in config.PASTA_SESSOES.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
        return cls(pastas[-1]) if pastas else None

    @classmethod
    def abrir(cls, caminho: str | None) -> "Sessao | None":
        if caminho:
            return cls(Path(caminho))
        return cls.ultima()

    # ---------- transcrição ----------
    def _proximo_id(self) -> int:
        if self._prox_id is None:
            self._prox_id = len(self.ler_falas()) + 1
        i = self._prox_id
        self._prox_id += 1
        return i

    def adicionar_fala(self, quem: str, texto: str, ts: float | None = None) -> dict:
        ts = ts or time.time()
        with _trava:
            item = {
                "id": self._proximo_id(),
                "ts": round(ts, 2),
                "hora": datetime.fromtimestamp(ts).strftime("%H:%M:%S"),
                "quem": quem,
                "texto": texto,
            }
            with open(self.transcricao, "a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return item

    def ler_falas(self, desde_id: int = 0) -> list:
        if not self.transcricao.exists():
            return []
        out = []
        with open(self.transcricao, encoding="utf-8") as f:
            for linha in f:
                try:
                    item = json.loads(linha)
                except Exception:
                    continue
                if item.get("id", 0) > desde_id:
                    out.append(item)
        return out

    # ---------- log ----------
    def logar(self, msg: str) -> None:
        linha = f"[{datetime.now():%H:%M:%S}] {msg}"
        try:
            with open(self.log, "a", encoding="utf-8") as f:
                f.write(linha + "\n")
        except Exception:
            pass

    # ---------- briefing ----------
    def ler_briefing(self) -> dict:
        return ler_json(self.briefing, {}) or {}
