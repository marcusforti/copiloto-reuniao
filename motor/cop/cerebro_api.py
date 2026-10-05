"""Cérebro por API (opcional, caminho pago): o próprio motor gera os conselhos chamando a API da Anthropic.
Não depende de uma sessão do Claude Code aberta nem dos limites do plano. Usa ANTHROPIC_API_KEY.

O roteiro de cada modo (venda, mentoria, diagnóstico) é o mesmo que o Claude Code usa:
skills/copiloto-reuniao/modos/<modo>.md + conselhos-formato.md. Fica no system prompt, com cache.
"""
import json
import threading
import time
from datetime import datetime
from pathlib import Path

from .sessao import escrever_json, ler_json

RAIZ = Path(__file__).resolve().parents[2]
PASTA_SKILL = RAIZ / "skills" / "copiloto-reuniao"

ESQUEMA = {
    "type": "object",
    "properties": {
        "fase": {"type": "string"},
        "agora": {"type": "string"},
        "porque": {"type": "string"},
        "perguntas": {"type": "array", "items": {"type": "string"}},
        "sinais": {"type": "array", "items": {"type": "string"}},
        "objecoes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"objecao": {"type": "string"}, "resposta": {"type": "string"}},
                "required": ["objecao", "resposta"],
                "additionalProperties": False,
            },
        },
        "evitar": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["fase", "agora", "porque", "perguntas", "sinais", "objecoes", "evitar"],
    "additionalProperties": False,
}


def _ler(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


class CerebroAPI:
    def __init__(self, cfg: dict, chaves: dict, sessao, logar=print, alerta=None):
        import anthropic

        chave = chaves.get("ANTHROPIC_API_KEY")
        self.anthropic = anthropic
        self.cliente = anthropic.Anthropic(api_key=chave) if chave else anthropic.Anthropic()
        self.modelo = cfg.get("modelo_cerebro") or "claude-opus-5-5"
        self.intervalo = max(8, int(cfg.get("intervalo_cerebro_s", 20)))
        self.sessao = sessao
        self.logar = logar
        self.alerta = alerta or (lambda *a, **k: None)
        self.parar = threading.Event()
        self.ultimo_id = 0
        self.rotulos = (cfg.get("rotulo_voce", "VOCÊ"), cfg.get("rotulo_cliente", "CLIENTE"))
        briefing = sessao.ler_briefing()
        modo = briefing.get("modo", "venda")
        from . import config

        perfil = config.ler_perfil()
        bloco_perfil = (
            "\n\n## PERFIL DE QUEM ESTÁ CONDUZINDO A CALL (ofertas, preços, cliente, objeções, script)\n"
            "Use isto em todos os conselhos. Siga o script/etapas do usuário quando houver. Nunca invente condição fora daqui.\n\n"
            + perfil
            if perfil
            else ""
        )
        self.system = [
            {
                "type": "text",
                "text": (
                    "Você é o copiloto de uma reunião AO VIVO. Você lê a transcrição e diz à pessoa do lado "
                    f"'{self.rotulos[0]}' o que falar agora para conduzir bem a conversa com '{self.rotulos[1]}'.\n\n"
                    + _ler(PASTA_SKILL / "modos" / f"{modo}.md")
                    + "\n\n"
                    + _ler(PASTA_SKILL / "conselhos-formato.md")
                    + bloco_perfil
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ]
        self.briefing_txt = json.dumps(briefing, ensure_ascii=False, indent=1)

    def _pedir(self, conteudo: str) -> dict:
        kwargs = dict(
            model=self.modelo,
            max_tokens=4000,
            system=self.system,
            messages=[{"role": "user", "content": conteudo}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": ESQUEMA}},
        )
        if self.modelo.startswith("claude-haiku"):
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": ESQUEMA}}
        try:
            # fallback do lado do servidor: se o modelo recusar, outro modelo responde na mesma chamada
            r = self.cliente.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        except TypeError:
            r = self.cliente.messages.create(**kwargs)
        if r.stop_reason == "refusal":
            raise RuntimeError("o modelo recusou este trecho")
        texto = next((b.text for b in r.content if b.type == "text"), "")
        return json.loads(texto)

    def _ciclo(self):
        falas = self.sessao.ler_falas()
        if not falas or falas[-1]["id"] <= self.ultimo_id:
            return
        novo_id = falas[-1]["id"]
        rotulo = {"voce": self.rotulos[0], "cliente": self.rotulos[1]}
        recentes = sorted(falas[-160:], key=lambda f: f["ts"])
        transcricao = "\n".join(f"[{f['hora']}] {rotulo.get(f['quem'], f['quem'])}: {f['texto']}" for f in recentes)
        anterior = ler_json(self.sessao.conselhos, {}) or {}
        anterior.pop("historico", None)
        conteudo = (
            f"BRIEFING DA REUNIÃO:\n{self.briefing_txt}\n\n"
            f"CONSELHOS QUE ESTÃO NA TELA AGORA:\n{json.dumps(anterior, ensure_ascii=False)}\n\n"
            f"TRANSCRIÇÃO (mais recente embaixo):\n{transcricao}\n\n"
            "Atualize os conselhos. Só troque o 'agora' se a conversa avançou ou surgiu algo novo."
        )
        t = time.time()
        dados = self._pedir(conteudo)
        dados["atualizado"] = datetime.now().strftime("%H:%M")
        dados["cerebro"] = self.modelo
        escrever_json(self.sessao.conselhos, dados)
        self.ultimo_id = novo_id  # só depois de gravar: se a chamada falhar, a mesma fala é tentada de novo
        self.logar(f"conselhos atualizados pela API em {time.time() - t:.1f}s")

    def _loop(self):
        espera = self.intervalo
        while not self.parar.wait(espera):
            try:
                self._ciclo()
                espera = self.intervalo
            except self.anthropic.AuthenticationError:
                self.alerta("cerebro", "A chave da Anthropic foi recusada. Configure de novo: copiloto chave anthropic SUA_CHAVE")
                espera = 60
            except self.anthropic.RateLimitError:
                self.alerta("cerebro", "Limite da API da Anthropic atingido; tento de novo em instantes.", temporario=True)
                espera = 30
            except self.anthropic.APIConnectionError:
                self.alerta("cerebro", "Sem conexão com a API da Anthropic.", temporario=True)
                espera = 15
            except Exception as e:
                self.logar(f"cérebro API: {e}")
                espera = self.intervalo

    def iniciar(self):
        threading.Thread(target=self._loop, name="cerebro-api", daemon=True).start()

    def encerrar(self):
        self.parar.set()
