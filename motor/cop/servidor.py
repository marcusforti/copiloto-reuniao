"""Servidor local do painel. No PC: http://127.0.0.1:<porta>/  No celular (mesma Wi-Fi): http://<ip>:<porta>/?k=<token>
O token impede que outra pessoa da rede abra o painel."""
import json
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .sessao import ler_json

PAINEL = Path(__file__).resolve().parents[2] / "painel" / "index.html"


class _HTTP(ThreadingHTTPServer):
    """No Windows, o padrão do Python (SO_REUSEADDR) deixa DOIS processos ouvirem a mesma porta, e o painel
    passa a mostrar a reunião errada. Aqui a porta é exclusiva: se estiver ocupada, usamos a próxima."""

    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def ip_local() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _ler_jsonl(p: Path, ultimos: int | None = None, desde: int = 0) -> list:
    if not p.exists():
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for linha in f:
            try:
                item = json.loads(linha)
            except Exception:
                continue
            if item.get("id", 10**9) > desde:
                out.append(item)
    return out[-ultimos:] if ultimos else out


class Servidor:
    def __init__(self, sessao, cfg):
        self.sessao = sessao
        self.cfg = cfg
        self.token = secrets.token_urlsafe(8)
        self.httpd = None
        self.urls = {}

    def _handler(self):
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _local(self):
                return self.client_address[0] in ("127.0.0.1", "::1")

            def _autorizado(self, q):
                return self._local() or q.get("k", [""])[0] == srv.token

            def _json(self, dados, codigo=200):
                corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
                self.send_response(codigo)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def do_GET(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                if not self._autorizado(q):
                    self._json({"erro": "acesso negado"}, 403)
                    return
                s = srv.sessao
                if u.path in ("/", "/index.html"):
                    corpo = PAINEL.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(corpo)))
                    self.end_headers()
                    self.wfile.write(corpo)
                elif u.path == "/api/estado":
                    desde = int(q.get("desde", ["0"])[0] or 0)
                    self._json(
                        {
                            "estado": ler_json(s.estado, {}),
                            "conselhos": ler_json(s.conselhos, {}),
                            "briefing": ler_json(s.briefing, {}),
                            "historico": _ler_jsonl(s.historico),
                            "falas": _ler_jsonl(s.transcricao, ultimos=None if desde else 80, desde=desde),
                            "celular": srv.urls.get("celular"),
                        }
                    )
                else:
                    self._json({"erro": "não encontrado"}, 404)

        return H

    def iniciar(self):
        celular = bool(self.cfg.get("celular", True))
        host = "0.0.0.0" if celular else "127.0.0.1"
        porta = int(self.cfg.get("porta", 8765))
        for p in range(porta, porta + 30):
            try:
                self.httpd = _HTTP((host, p), self._handler())
                break
            except OSError:
                continue
        if not self.httpd:
            raise RuntimeError("Nenhuma porta livre para o painel")
        p = self.httpd.server_address[1]
        self.urls = {"pc": f"http://127.0.0.1:{p}/"}
        if celular:
            self.urls["celular"] = f"http://{ip_local()}:{p}/?k={self.token}"
        threading.Thread(target=self.httpd.serve_forever, name="painel", daemon=True).start()
        self.sessao.logar(f"painel em {self.urls}")

    def encerrar(self):
        if self.httpd:
            threading.Thread(target=self.httpd.shutdown, daemon=True).start()
