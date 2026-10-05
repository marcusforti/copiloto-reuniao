#!/usr/bin/env python3
"""Copiloto de Reunião — linha de comando.

  copiloto instalar [--modelo small]       cria o ambiente em ~/CopilotoReuniao/.venv e baixa o modelo
  copiloto verificar [--json]              confere se está tudo pronto
  copiloto teste [--segundos 8]            testa microfone e áudio do PC (com medidor)
  copiloto config [chave valor]            mostra/altera a configuração
  copiloto chave deepgram|soniox|anthropic VALOR
  copiloto iniciar --modo venda --cliente "Nome" [--objetivo ...] [--oferta ...] [--preco ...]
  copiloto acompanhar [--sessao PASTA]     (para o Monitor do Claude Code) imprime as falas novas em lotes
  copiloto status | parar | abrir
  copiloto transcricao [--sessao PASTA]    gera transcricao.txt legível
  copiloto resumo --dados resumo.json      gera resumo.html bonito na pasta da sessão
  copiloto simular exemplos/demo-venda.json [--audio] [--velocidade 1]
"""
import argparse
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(AQUI))
os.environ.setdefault("CT2_USE_MKL", "0")  # MKL reserva ~2 GB a mais e derruba a transcrição em PC com navegador aberto
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from cop import VERSAO, config  # noqa: E402  (só stdlib nesses dois)

VENV = config.PASTA / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _no_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == VENV.resolve()
    except Exception:
        return False


def _reexecutar_no_venv():
    """Se o ambiente do copiloto existe e não estamos nele, roda de novo lá dentro (assim o comando é sempre `python copiloto.py`)."""
    if os.environ.get("COPILOTO_SEM_VENV") or _no_venv() or not VENV_PY.exists():
        return
    if len(sys.argv) > 1 and sys.argv[1] in ("instalar",):
        return
    r = subprocess.run([str(VENV_PY), str(Path(__file__).resolve())] + sys.argv[1:])
    sys.exit(r.returncode)


def saida_utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass


# =====================================================================================
# instalar / verificar
# =====================================================================================
def cmd_instalar(a):
    if sys.version_info < (3, 10):
        print(f"ERRO: precisa de Python 3.10 ou mais novo (este é {sys.version.split()[0]}).")
        return 1
    config.PASTA.mkdir(parents=True, exist_ok=True)
    if not VENV_PY.exists():
        print(f"Criando ambiente em {VENV} …")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
    req = AQUI / ("requirements-mac.txt" if sys.platform == "darwin" else "requirements.txt")
    print("Instalando bibliotecas (pode levar alguns minutos na primeira vez) …")
    subprocess.check_call([str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip", "-q"])
    subprocess.check_call([str(VENV_PY), "-m", "pip", "install", "-q", "-r", str(req)])
    if a.api:
        subprocess.check_call([str(VENV_PY), "-m", "pip", "install", "-q", "anthropic"])
    cfg = config.carregar()
    modelo = a.modelo or cfg.get("modelo_local", "auto")
    if modelo == "auto":
        modelo = subprocess.run(
            [str(VENV_PY), "-c", f"import sys; sys.path.insert(0, r'{AQUI}'); from cop.sistema import escolher_modelo; print(escolher_modelo())"],
            capture_output=True, text=True,
        ).stdout.strip() or "small"
    if cfg.get("transcricao", "local") == "local" or a.modelo:
        print(f"Baixando o modelo de transcrição '{modelo}' (uma vez só; ~250 MB a 1,5 GB) …")
        subprocess.check_call([str(VENV_PY), "-c", f"from faster_whisper import WhisperModel; WhisperModel('{modelo}', device='cpu', compute_type='int8')"])
    if not config.ARQ_CONFIG.exists():
        config.salvar(cfg)
    print("\nPRONTO. Próximo passo: copiloto teste")
    if sys.platform == "darwin":
        print("\nMac: para ouvir o cliente, instale o BlackHole (veja instalar/instalar-mac.sh) e crie um Multi-Output Device.")
    return 0


def _verificacoes() -> dict:
    r = {"versao": VERSAO, "python": sys.version.split()[0], "venv": str(VENV), "venv_ok": VENV_PY.exists(), "pasta": str(config.PASTA)}
    faltando = []
    mods = ["numpy", "faster_whisper", "silero_vad_lite", "soxr", "websockets", "psutil"]
    mods += ["pyaudiowpatch", "pycaw"] if os.name == "nt" else ["sounddevice"]
    for m in mods:
        try:
            __import__(m)
        except Exception:
            faltando.append(m)
    r["faltando"] = faltando
    cfg = config.carregar()
    r["config"] = cfg
    ch = config.chaves()
    r["chaves"] = {k: bool(ch.get(k)) for k in ("DEEPGRAM_API_KEY", "SONIOX_API_KEY", "ANTHROPIC_API_KEY")}
    try:
        from cop import sistema

        r["ram_livre_gb"] = round(sistema.ram_livre_gb(), 1)
        r["nucleos"] = sistema.nucleos()
        r["modelo_sugerido"] = sistema.escolher_modelo(cfg.get("modelo_local", "auto"))
    except Exception:
        pass
    problemas = []
    if not r["venv_ok"] or faltando:
        problemas.append("instalação incompleta: rode `copiloto instalar`")
    if cfg.get("transcricao") == "deepgram" and not r["chaves"]["DEEPGRAM_API_KEY"]:
        problemas.append("modo deepgram sem chave: `copiloto chave deepgram SUA_CHAVE`")
    if cfg.get("transcricao") == "soniox" and not r["chaves"]["SONIOX_API_KEY"]:
        problemas.append("modo soniox sem chave: `copiloto chave soniox SUA_CHAVE`")
    if cfg.get("cerebro") == "api" and not r["chaves"]["ANTHROPIC_API_KEY"]:
        problemas.append("cérebro por API sem chave: `copiloto chave anthropic SUA_CHAVE`")
    r["problemas"] = problemas
    r["pronto"] = not problemas
    return r


def cmd_verificar(a):
    r = _verificacoes()
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(f"Copiloto de Reunião {r['versao']} | Python {r['python']} | pasta {r['pasta']}")
        print(f"Transcrição: {r['config']['transcricao']} | modelo: {r.get('modelo_sugerido')} | cérebro: {r['config']['cerebro']}")
        print(f"RAM livre: {r.get('ram_livre_gb')} GB | núcleos: {r.get('nucleos')}")
        print("PRONTO ✔" if r["pronto"] else "PENDÊNCIAS:\n- " + "\n- ".join(r["problemas"]))
    return 0 if r["pronto"] else 1


# =====================================================================================
# teste de dispositivos
# =====================================================================================
def _tocar_tom(segundos=2.0):
    """Toca um som suave na saída padrão para conferir se o áudio do PC está sendo captado."""
    import numpy as np

    t = np.arange(int(48000 * segundos)) / 48000
    onda = (0.15 * np.sin(2 * np.pi * 440 * t) * np.sin(np.pi * t / segundos)).astype(np.float32)
    if os.name == "nt":
        import pyaudiowpatch as pa

        p = pa.PyAudio()
        try:
            s = p.open(format=pa.paFloat32, channels=1, rate=48000, output=True)
            s.write(onda.tobytes())
            s.stop_stream()
            s.close()
        finally:
            p.terminate()
    else:
        import sounddevice as sd

        sd.play(onda, 48000)
        sd.wait()


def cmd_teste(a):
    import threading

    import numpy as np

    from cop.audio import CLIENTE, VOCE, Mixer, criar_fonte

    cfg = config.carregar()
    picos = {VOCE: -90.0, CLIENTE: -90.0}
    audio_mic = []

    def ao_bloco(canal, bloco, ts):
        db = 20 * np.log10(float(np.sqrt(np.mean(bloco * bloco))) + 1e-9)
        picos[canal] = max(picos[canal], db)
        if canal == VOCE:
            audio_mic.append(bloco.copy())

    mx = Mixer(ao_bloco)
    fonte = criar_fonte(mx, cfg, logar=lambda m: None)
    mx.iniciar()
    fonte.iniciar()
    getattr(fonte, "pronto", None) and fonte.pronto.wait(10)
    time.sleep(0.5)
    print(f"Microfone: {fonte.dispositivos.get('microfone')}")
    print(f"Saídas ouvidas: {', '.join(fonte.dispositivos.get('saidas') or []) or 'nenhuma'}")
    print(f"\n>>> FALE AGORA por {a.segundos} segundos (ex.: 'testando, um, dois, três'). Vou tocar um som baixinho também.\n")
    threading.Thread(target=_tocar_tom, daemon=True).start()
    fim = time.time() + a.segundos
    while time.time() < fim:
        barra = lambda db: "█" * int(max(0, min(30, (db + 60) / 2)))  # noqa: E731
        print(f"\r  VOCÊ   {barra(mx.nivel[VOCE]):<30} {mx.nivel[VOCE]:6.1f} dB   CLIENTE {barra(mx.nivel[CLIENTE]):<30} {mx.nivel[CLIENTE]:6.1f} dB", end="", flush=True)
        time.sleep(0.15)
    print()
    fonte.encerrar()
    mx.encerrar()
    ok_mic = bool(picos[VOCE] > -45)
    ok_saida = bool(picos[CLIENTE] > -50)
    resultado = {"microfone": fonte.dispositivos.get("microfone"), "saidas": fonte.dispositivos.get("saidas"), "pico_voce_db": round(float(picos[VOCE]), 1), "pico_cliente_db": round(float(picos[CLIENTE]), 1), "mic_ok": ok_mic, "saida_ok": ok_saida}
    print("\nResultado:")
    print(f"  Microfone: {'OK ✔' if ok_mic else 'SEM SOM ✘ — confira se o microfone certo está como padrão de COMUNICAÇÃO no Windows (ou no Mac), ou se está no mudo'}")
    print(f"  Áudio do PC (cliente): {'OK ✔' if ok_saida else 'SEM SOM ✘ — o som do PC não chegou. No Mac: BlackHole + Multi-Output. No Windows: confira o volume/saída.'}")
    if ok_mic and a.transcrever and audio_mic:
        try:
            from cop.sistema import escolher_modelo
            from faster_whisper import WhisperModel

            m = WhisperModel(escolher_modelo(cfg.get("modelo_local", "auto")), device="cpu", compute_type="int8")
            segs, _ = m.transcribe(np.concatenate(audio_mic), language="pt", vad_filter=True)
            txt = " ".join(s.text.strip() for s in segs).strip()
            resultado["ouvi"] = txt
            print(f'  Entendi você dizer: "{txt}"')
        except Exception as e:
            print(f"  (não consegui transcrever o teste: {e})")
    if a.json:
        print("JSON:" + json.dumps(resultado, ensure_ascii=False))
    return 0 if ok_mic else 2


# =====================================================================================
# config / chaves
# =====================================================================================
def cmd_config(a):
    cfg = config.carregar()
    if a.chave:
        if a.chave not in config.PADRAO:
            print(f"Chave desconhecida. Opções: {', '.join(config.PADRAO)}")
            return 1
        v = a.valor
        padrao = config.PADRAO[a.chave]
        if isinstance(padrao, bool):
            v = str(v).lower() in ("1", "sim", "true", "s", "yes")
        elif isinstance(padrao, int):
            v = int(v)
        elif isinstance(padrao, list):
            v = [x.strip() for x in str(v).split(",") if x.strip()]
        cfg[a.chave] = v
        config.salvar(cfg)
    print(json.dumps(cfg, ensure_ascii=False, indent=1))
    return 0


def cmd_chave(a):
    nomes = {"deepgram": "DEEPGRAM_API_KEY", "soniox": "SONIOX_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
    config.salvar_chave(nomes[a.provedor], a.valor)
    print(f"Chave {a.provedor} salva em {config.ARQ_ENV} (só no seu computador).")
    return 0


# =====================================================================================
# sessão: iniciar / motor / acompanhar / status / parar
# =====================================================================================
def _spawn_destacado(args: list, log: Path):
    """Processo independente: sobrevive ao fim do comando e ao limite de tarefas em segundo plano do Claude Code.

    No Windows, o Claude Code pode rodar os comandos dentro de um "Job Object" que mata os filhos quando a tarefa
    termina. Primeiro tentamos sair do job (CREATE_BREAKAWAY_FROM_JOB). Se o job não permitir, criamos o processo
    pelo WMI: quem vira "pai" é o serviço do Windows, fora de qualquer job."""
    if os.name == "nt":
        DETACHED, NOVO_GRUPO, FUGIR_DO_JOB = 0x8, 0x200, 0x01000000
        try:
            with open(log, "a", encoding="utf-8") as err:
                return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=err, stderr=err, creationflags=DETACHED | NOVO_GRUPO | FUGIR_DO_JOB, close_fds=True)
        except OSError:
            pass
        linha = subprocess.list2cmdline(args)
        ps = (
            "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
            f"-Arguments @{{CommandLine={_ps_str(linha)}; CurrentDirectory={_ps_str(str(AQUI))}}}; "
            "if ($r.ReturnValue -ne 0) { exit 1 } else { $r.ProcessId }"
        )
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"não consegui iniciar o motor: {r.stderr.strip()[:300]}")
        return None
    with open(log, "a", encoding="utf-8") as err:
        return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=err, stderr=err, start_new_session=True, close_fds=True)


def _ps_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _pid_vivo(pid) -> bool:
    if not pid:
        return False
    try:
        import psutil

        return psutil.pid_exists(int(pid))
    except Exception:
        try:
            os.kill(int(pid), 0)
            return True
        except Exception:
            return False


def _sessao_ativa():
    from cop.sessao import Sessao, ler_json

    s = Sessao.ultima()
    if not s:
        return None, {}
    e = ler_json(s.estado, {}) or {}
    return s, e


def cmd_iniciar(a):
    from cop.sessao import Sessao, escrever_json, ler_json

    s0, e0 = _sessao_ativa()
    if s0 and e0.get("status") in ("rodando", "iniciando") and _pid_vivo(e0.get("pid")):
        print(f"Já existe uma reunião rodando: {s0.pasta}\nPainel: {e0.get('painel', {}).get('pc')}\nPara encerrar: copiloto parar")
        return 1
    cfg = config.carregar()
    if a.transcricao:
        cfg["transcricao"] = a.transcricao
    if a.cerebro:
        cfg["cerebro"] = a.cerebro
    if a.sem_fone:
        cfg["fone"] = False
    config.salvar(cfg)
    s = Sessao.nova(a.cliente or "", a.modo)
    briefing = {
        "modo": a.modo,
        "cliente": a.cliente or "",
        "empresa": a.empresa or "",
        "objetivo": a.objetivo or "",
        "oferta": a.oferta or "",
        "preco": a.preco or "",
        "contexto": a.contexto or "",
        "vocabulario": [v.strip() for v in (a.vocabulario or "").split(",") if v.strip()],
        "perfil": str(config.PASTA_PERFIL / "perfil.md") if (config.PASTA_PERFIL / "perfil.md").exists() else "",
        "criado": time.strftime("%Y-%m-%d %H:%M"),
    }
    escrever_json(s.briefing, briefing)
    escrever_json(s.conselhos, {"fase": "Abertura", "agora": "Abra com rapport e confirme o objetivo da conversa e o tempo que vocês têm.", "porque": "Começo de reunião: alinhar expectativa evita que a conversa se perca.", "perguntas": [], "sinais": [], "objecoes": [], "evitar": [], "atualizado": time.strftime("%H:%M")})
    _spawn_destacado([sys.executable, str(Path(__file__).resolve()), "motor", "--sessao", str(s.pasta)], s.pasta / "motor_saida.log")
    print(f"Iniciando o motor (transcrição: {cfg['transcricao']}) …", flush=True)
    fim = time.time() + (a.espera or 90)
    e = {}
    while time.time() < fim:
        e = ler_json(s.estado, {}) or {}
        if e.get("status") in ("rodando", "erro"):
            break
        time.sleep(0.5)
    if e.get("status") != "rodando":
        log = (s.pasta / "motor_saida.log").read_text(encoding="utf-8", errors="replace")[-1500:] if (s.pasta / "motor_saida.log").exists() else ""
        print(f"ERRO: o motor não subiu. status={e.get('status')} erro={e.get('erro')}\n{log}")
        return 2
    fim = time.time() + 10  # espera os dispositivos de áudio abrirem para mostrar quais estão sendo ouvidos
    while time.time() < fim and not (e.get("dispositivos") or {}).get("microfone"):
        time.sleep(0.5)
        e = ler_json(s.estado, {}) or e
    urls = e.get("painel", {})
    abriu = bool(cfg.get("abrir_painel", True) and not a.sem_painel)
    if abriu:
        webbrowser.open(urls.get("pc", ""))
    print(f"SESSAO={s.pasta}")
    print(f"PAINEL={urls.get('pc')}")
    if urls.get("celular"):
        print(f"CELULAR={urls.get('celular')}")
    print(f"MICROFONE={e.get('dispositivos', {}).get('microfone')}")
    print(f"SAIDAS={', '.join(e.get('dispositivos', {}).get('saidas') or [])}")
    print(f"CONSELHOS={s.conselhos}")
    print("\nO copiloto está ouvindo." + (" Painel aberto no navegador." if abriu else f" Painel: {urls.get('pc')}"))
    print("⚠ Se for compartilhar tela, compartilhe SÓ a aba/janela da apresentação, nunca a tela inteira (o cliente veria o painel).")
    return 0


def cmd_motor(a):
    # a pasta do copiloto vem do caminho da sessão (<pasta>/sessoes/<sessão>): o motor pode ter sido criado pelo
    # WMI no Windows, sem herdar as variáveis de ambiente de quem chamou
    casa = Path(a.sessao).resolve().parent.parent
    if casa.name and (casa / "sessoes").is_dir():
        config.PASTA, config.ARQ_CONFIG, config.ARQ_ENV, config.PASTA_SESSOES = casa, casa / "config.json", casa / ".env", casa / "sessoes"
        config.PASTA_PERFIL = casa / "perfil"
    from cop.motor import Motor
    from cop.sessao import Sessao

    Motor(Sessao(Path(a.sessao))).rodar()
    return 0


def cmd_acompanhar(a):
    """Feito para o Monitor do Claude Code: cada lote impresso vira uma notificação para o Claude dar conselhos.
    Guarda um cursor em disco: se o Monitor expirar e for religado, continua de onde parou."""
    from cop.sessao import Sessao, ler_json

    s = Sessao.abrir(a.sessao)
    if not s:
        print("Nenhuma sessão encontrada. Rode: copiloto iniciar")
        return 1
    rot = {"voce": "VOCÊ", "cliente": "CLIENTE"}
    try:
        cursor = int(s.cursor.read_text().strip())
    except Exception:
        cursor = 0
    pendentes, ultimo_envio, alertas_vistos = [], 0.0, set()
    gatilhos = ("caro", "pensar", "depois", "sócio", "socio", "esposa", "marido", "orçamento", "orcamento", "não sei", "nao sei", "concorrente", "desconto", "parcel", "garantia", "quanto custa", "preço", "preco", "valor")
    inicio = time.time()
    while True:
        e = ler_json(s.estado, {}) or {}
        rot.update({k: v for k, v in (e.get("rotulos") or {}).items()})
        novas = s.ler_falas(cursor)
        if novas:
            pendentes += novas
            cursor = novas[-1]["id"]
        for al in e.get("alertas", []):
            chave = (al.get("tipo"), al.get("msg"))
            if chave not in alertas_vistos:
                alertas_vistos.add(chave)
                print(f"[COPILOTO ALERTA {time.strftime('%H:%M:%S')}] {al.get('msg')}", flush=True)
        agora = time.time()
        urgente = any(p["quem"] == "cliente" and (p["texto"].rstrip().endswith("?") or any(g in p["texto"].lower() for g in gatilhos)) for p in pendentes)
        if pendentes and (agora - ultimo_envio >= a.intervalo or (urgente and agora - ultimo_envio >= 6) or len(pendentes) >= 14):
            linhas = [f"[COPILOTO {time.strftime('%H:%M:%S')}] {len(pendentes)} fala(s) nova(s){' — CLIENTE perguntou/objetou' if urgente else ''} | conselhos: {s.conselhos}"]
            pendentes.sort(key=lambda p: p["ts"])
            linhas += [f"  {p['hora']} {rot.get(p['quem'], p['quem'])}: {p['texto']}" for p in pendentes]
            print("\n".join(linhas), flush=True)
            s.cursor.write_text(str(cursor))
            pendentes, ultimo_envio = [], agora
            if a.um_lote:
                return 0
        if a.um_lote and agora - inicio > 120:
            print("[COPILOTO] sem falas novas nos últimos 2 min.", flush=True)
            return 0
        status = e.get("status")
        parado = status in ("parado", "erro") or (e.get("atualizado") and agora - e["atualizado"] > 30 and agora - inicio > 30)
        if parado:
            if pendentes:
                print("\n".join(f"  {p['hora']} {rot.get(p['quem'], p['quem'])}: {p['texto']}" for p in pendentes), flush=True)
                s.cursor.write_text(str(cursor))
            print(f"[COPILOTO FIM] o motor parou (status={status}). Rode /reuniao-fim para o resumo.", flush=True)
            return 0
        time.sleep(1.0)


def cmd_status(a):
    s, e = _sessao_ativa()
    if a.sessao:
        from cop.sessao import Sessao, ler_json

        s = Sessao(Path(a.sessao))
        e = ler_json(s.estado, {}) or {}
    if not s:
        print("Nenhuma sessão ainda.")
        return 1
    vivo = _pid_vivo(e.get("pid"))
    resumo = {"sessao": str(s.pasta), "status": e.get("status") if vivo or e.get("status") == "parado" else "morto", "falas": e.get("falas"), "alertas": [x.get("msg") for x in e.get("alertas", [])], "painel": e.get("painel"), "transcricao": e.get("transcricao"), "dispositivos": e.get("dispositivos"), "ram_livre_gb": e.get("ram_livre_gb")}
    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    return 0


def cmd_parar(a):
    from cop.sessao import Sessao, ler_json

    s = Sessao.abrir(a.sessao)
    if not s:
        print("Nenhuma sessão.")
        return 1
    e = ler_json(s.estado, {}) or {}
    if e.get("status") == "parado":
        print(f"Já estava parado. SESSAO={s.pasta}")
        return 0
    s.parar.write_text("1")
    fim = time.time() + 60
    while time.time() < fim:
        e = ler_json(s.estado, {}) or {}
        if e.get("status") == "parado" or not _pid_vivo(e.get("pid")):
            break
        time.sleep(0.5)
    print(f"Reunião encerrada. {sum((e.get('falas') or {}).values())} falas transcritas.\nSESSAO={s.pasta}")
    return 0


def cmd_abrir(a):
    s, e = _sessao_ativa()
    url = (e.get("painel") or {}).get("pc")
    if url and e.get("status") == "rodando":
        webbrowser.open(url)
        print(url)
    elif s and (s.pasta / "resumo.html").exists():
        webbrowser.open((s.pasta / "resumo.html").as_uri())
        print(s.pasta / "resumo.html")
    else:
        print("Nada para abrir.")
    return 0


# =====================================================================================
# depois da reunião
# =====================================================================================
def cmd_perfil(a):
    """Mostra onde fica o perfil e o que já existe (o Claude escreve os arquivos direto na pasta)."""
    config.PASTA_PERFIL.mkdir(parents=True, exist_ok=True)
    print(f"PERFIL={config.PASTA_PERFIL}")
    arqs = sorted(config.PASTA_PERFIL.glob("*"))
    if not arqs:
        print("VAZIO: ainda não há perfil. Rode /reuniao-perfil.")
        return 0
    for p in arqs:
        print(f"  {p.name} ({p.stat().st_size // 1024 + 1} KB)")
    termos = config.termos_perfil()
    if termos:
        print("TERMOS=" + ", ".join(termos))
    if a.mostrar and (config.PASTA_PERFIL / "perfil.md").exists():
        print("\n" + (config.PASTA_PERFIL / "perfil.md").read_text(encoding="utf-8"))
    return 0


def cmd_transcricao(a):
    from cop.sessao import Sessao, ler_json

    s = Sessao.abrir(a.sessao)
    e = ler_json(s.estado, {}) or {}
    rot = {"voce": "VOCÊ", "cliente": "CLIENTE", **(e.get("rotulos") or {})}
    falas = sorted(s.ler_falas(), key=lambda f: f["ts"])
    txt = "\n".join(f"[{f['hora']}] {rot.get(f['quem'], f['quem'])}: {f['texto']}" for f in falas)
    destino = s.pasta / "transcricao.txt"
    destino.write_text(txt + "\n", encoding="utf-8")
    print(f"TRANSCRICAO={destino}\n{len(falas)} falas | briefing: {json.dumps(s.ler_briefing(), ensure_ascii=False)}")
    return 0


def cmd_resumo(a):
    from cop.resumo import gerar
    from cop.sessao import Sessao

    s = Sessao.abrir(a.sessao)
    dados = json.loads(Path(a.dados).read_text(encoding="utf-8"))
    destino = gerar(s, dados)
    print(f"RESUMO={destino}")
    if not a.sem_abrir:
        webbrowser.open(destino.as_uri())
    return 0


def cmd_simular(a):
    from cop.simulador import simular

    return simular(Path(a.roteiro), audio=a.audio, velocidade=a.velocidade, abrir=not a.sem_painel, voz=a.voz)


# =====================================================================================
def main():
    saida_utf8()
    _reexecutar_no_venv()
    p = argparse.ArgumentParser(prog="copiloto", description="Copiloto de Reunião")
    sub = p.add_subparsers(dest="cmd", required=True)

    x = sub.add_parser("instalar")
    x.add_argument("--modelo")
    x.add_argument("--api", action="store_true", help="instala também o pacote da Anthropic (cérebro por API)")
    x.set_defaults(f=cmd_instalar)
    x = sub.add_parser("verificar")
    x.add_argument("--json", action="store_true")
    x.set_defaults(f=cmd_verificar)
    x = sub.add_parser("teste")
    x.add_argument("--segundos", type=int, default=8)
    x.add_argument("--transcrever", action="store_true")
    x.add_argument("--json", action="store_true")
    x.set_defaults(f=cmd_teste)
    x = sub.add_parser("config")
    x.add_argument("chave", nargs="?")
    x.add_argument("valor", nargs="?")
    x.set_defaults(f=cmd_config)
    x = sub.add_parser("chave")
    x.add_argument("provedor", choices=["deepgram", "soniox", "anthropic"])
    x.add_argument("valor")
    x.set_defaults(f=cmd_chave)
    x = sub.add_parser("iniciar")
    x.add_argument("--modo", default="venda", choices=["venda", "mentoria", "diagnostico", "geral"])
    for k in ("cliente", "empresa", "objetivo", "oferta", "preco", "contexto", "vocabulario"):
        x.add_argument(f"--{k}")
    x.add_argument("--transcricao", choices=["local", "deepgram", "soniox"])
    x.add_argument("--cerebro", choices=["claude-code", "api"])
    x.add_argument("--sem-fone", action="store_true")
    x.add_argument("--sem-painel", action="store_true")
    x.add_argument("--espera", type=int)
    x.set_defaults(f=cmd_iniciar)
    x = sub.add_parser("motor")
    x.add_argument("--sessao", required=True)
    x.set_defaults(f=cmd_motor)
    x = sub.add_parser("acompanhar")
    x.add_argument("--sessao")
    x.add_argument("--intervalo", type=int, default=20)
    x.add_argument("--um-lote", action="store_true", help="sai depois do primeiro lote (para ambientes sem Monitor)")
    x.set_defaults(f=cmd_acompanhar)
    for nome, f in (("status", cmd_status), ("parar", cmd_parar), ("transcricao", cmd_transcricao)):
        x = sub.add_parser(nome)
        x.add_argument("--sessao")
        x.set_defaults(f=f)
    x = sub.add_parser("perfil")
    x.add_argument("--mostrar", action="store_true", help="imprime o perfil.md inteiro")
    x.set_defaults(f=cmd_perfil)
    x = sub.add_parser("abrir")
    x.set_defaults(f=cmd_abrir)
    x = sub.add_parser("resumo")
    x.add_argument("--sessao")
    x.add_argument("--dados", required=True)
    x.add_argument("--sem-abrir", action="store_true")
    x.set_defaults(f=cmd_resumo)
    x = sub.add_parser("simular")
    x.add_argument("roteiro")
    x.add_argument("--audio", action="store_true", help="sintetiza vozes e passa pelo pipeline real de áudio+transcrição")
    x.add_argument("--velocidade", type=float, default=1.0)
    x.add_argument("--sem-painel", action="store_true")
    x.add_argument("--voz", default="Microsoft Maria Desktop")
    x.set_defaults(f=cmd_simular)

    a = p.parse_args()
    sys.exit(a.f(a) or 0)


if __name__ == "__main__":
    main()
