"""Configuração do usuário: ~/CopilotoReuniao/config.json e ~/CopilotoReuniao/.env (chaves)."""
import json
import os
from pathlib import Path

PASTA = Path(os.environ.get("COPILOTO_HOME", Path.home() / "CopilotoReuniao"))
ARQ_CONFIG = PASTA / "config.json"
ARQ_ENV = PASTA / ".env"
PASTA_SESSOES = PASTA / "sessoes"
PASTA_PERFIL = PASTA / "perfil"

PADRAO = {
    # "local" = grátis, faster-whisper no PC | "deepgram" ou "soniox" = pago, por API (chave do usuário)
    "transcricao": "local",
    # tiny | base | small | medium | auto (auto escolhe pelo PC)
    "modelo_local": "auto",
    # "claude-code" = a sessão do Claude Code dá os conselhos | "api" = o motor chama a API da Anthropic sozinho
    "cerebro": "claude-code",
    "modelo_cerebro": "claude-opus-5-5",
    "intervalo_cerebro_s": 20,
    # dispositivos: "auto" ou parte do nome do dispositivo
    "microfone": "auto",
    "saida": "auto",
    # o usuário usa fone? Sem fone o microfone pega a voz do cliente (eco) e o filtro fica mais agressivo
    "fone": True,
    "rotulo_voce": "VOCÊ",
    "rotulo_cliente": "CLIENTE",
    "vocabulario": [],
    "porta": 8765,
    "abrir_painel": True,
    "celular": True,
}


def carregar() -> dict:
    cfg = dict(PADRAO)
    if ARQ_CONFIG.exists():
        try:
            cfg.update(json.loads(ARQ_CONFIG.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def salvar(cfg: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    limpo = {k: v for k, v in cfg.items() if k in PADRAO}
    ARQ_CONFIG.write_text(json.dumps(limpo, ensure_ascii=False, indent=2), encoding="utf-8")


def ler_perfil(limite: int = 60000) -> str:
    """Perfil do usuário (ofertas, cliente, objeções, script de vendas): perfil.md primeiro, depois os outros .md da pasta."""
    if not PASTA_PERFIL.exists():
        return ""
    arquivos = sorted(PASTA_PERFIL.glob("*.md"), key=lambda p: (p.name != "perfil.md", p.name))
    partes = []
    for p in arquivos:
        try:
            partes.append(f"### Arquivo {p.name}\n" + p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return "\n\n".join(partes)[:limite]


def termos_perfil() -> list:
    """Lista da seção '## Nomes e termos' do perfil.md: vira vocabulário da transcrição."""
    p = PASTA_PERFIL / "perfil.md"
    if not p.exists():
        return []
    termos, dentro = [], False
    for linha in p.read_text(encoding="utf-8").splitlines():
        if linha.startswith("## "):
            dentro = "nomes e termos" in linha.lower()
            continue
        if dentro and linha.strip() and not linha.strip().startswith(("<", ">")):
            termos += [t.strip(" -*") for t in linha.split(",") if t.strip(" -*")]
    return [t for t in termos if 1 < len(t) < 60][:60]


def chaves() -> dict:
    """Lê ~/CopilotoReuniao/.env (KEY=valor). Variáveis de ambiente têm prioridade."""
    out = {}
    if ARQ_ENV.exists():
        for linha in ARQ_ENV.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            k, v = linha.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("DEEPGRAM_API_KEY", "SONIOX_API_KEY", "ANTHROPIC_API_KEY"):
        if os.environ.get(k):
            out[k] = os.environ[k]
    return out


def salvar_chave(nome: str, valor: str) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    atuais = {}
    if ARQ_ENV.exists():
        for linha in ARQ_ENV.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                k, v = linha.split("=", 1)
                atuais[k.strip()] = v.strip()
    atuais[nome] = valor.strip()
    ARQ_ENV.write_text("".join(f"{k}={v}\n" for k, v in atuais.items()), encoding="utf-8")
    try:
        os.chmod(ARQ_ENV, 0o600)
    except Exception:
        pass
