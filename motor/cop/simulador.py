"""Simulação de reunião (para testar, treinar e gravar demonstrações sem ninguém do outro lado).

Roteiro JSON:
{
  "briefing": {"modo": "venda", "cliente": "...", "oferta": "...", "preco": "..."},
  "falas": [{"quem": "cliente"|"voce", "texto": "...", "pausa": 1.0}, ...],
  "conselhos": [{"apos_fala": 3, "dados": {<mesmo formato de conselhos.json>}}, ...]
}

Modo texto (padrão): as falas aparecem no ritmo de quem está falando, com medidores animados. Não usa microfone.
Modo --audio: sintetiza as vozes (voz do Windows ou do Mac), toca no pipeline real (VAD + Whisper/API) e mede a precisão.
"""
import json
import random
import subprocess
import sys
import tempfile
import threading
import time
import wave
import webbrowser
from datetime import datetime
from pathlib import Path

import numpy as np

from . import config
from .sessao import Sessao, escrever_json


def _carregar(roteiro: Path) -> dict:
    return json.loads(roteiro.read_text(encoding="utf-8"))


def _aplicar_conselhos(s: Sessao, rot: dict, n_falas: int, aplicados: set):
    for i, c in enumerate(rot.get("conselhos", [])):
        if i not in aplicados and n_falas >= c.get("apos_fala", 0):
            aplicados.add(i)
            dados = dict(c["dados"])
            dados["atualizado"] = datetime.now().strftime("%H:%M")
            escrever_json(s.conselhos, dados)
            with open(s.historico, "a", encoding="utf-8") as f:
                f.write(json.dumps({"hora": dados["atualizado"], "texto": dados.get("agora", ""), "porque": dados.get("porque", "")}, ensure_ascii=False) + "\n")


def _estado_simulado(s, inicio, niveis, falas, urls, status="rodando"):
    agora = time.time()
    return {
        "status": status,
        "pid": None,
        "inicio": inicio,
        "atualizado": agora,
        "transcricao": {"motor": "simulação"},
        "cerebro": "roteiro",
        "niveis": niveis,
        "ultimo_som": {"voce": agora, "cliente": agora},
        "falas": falas,
        "dispositivos": {"microfone": "simulação", "saidas": ["simulação"]},
        "alertas": [],
        "atraso_s": 0,
        "painel": urls,
        "rotulos": {"voce": "VOCÊ", "cliente": "CLIENTE"},
    }


def simular_texto(roteiro: Path, velocidade=1.0, abrir=True, manter_s=90):
    from .servidor import Servidor

    rot = _carregar(roteiro)
    b = rot.get("briefing", {})
    s = Sessao.nova(b.get("cliente", "simulacao"), b.get("modo", "venda"))
    escrever_json(s.briefing, {**b, "simulacao": True})
    srv = Servidor(s, config.carregar())
    srv.iniciar()
    inicio = time.time()
    niveis = {"voce": -70.0, "cliente": -70.0}
    contagem = {"voce": 0, "cliente": 0}
    falando = {"quem": None}
    parar = threading.Event()

    def pulsar():
        while not parar.is_set():
            for c in niveis:
                alvo = random.uniform(-26, -12) if falando["quem"] == c else random.uniform(-72, -62)
                niveis[c] = round(niveis[c] * 0.4 + alvo * 0.6, 1)
            escrever_json(s.estado, _estado_simulado(s, inicio, dict(niveis), dict(contagem), srv.urls))
            time.sleep(0.12)

    threading.Thread(target=pulsar, daemon=True).start()
    time.sleep(0.5)
    if abrir:
        webbrowser.open(srv.urls["pc"])
    print(f"SESSAO={s.pasta}\nPAINEL={srv.urls['pc']}", flush=True)
    time.sleep(3 / velocidade)
    aplicados = set()
    _aplicar_conselhos(s, rot, 0, aplicados)
    for i, f in enumerate(rot["falas"], 1):
        falando["quem"] = f["quem"]
        dur = max(1.2, len(f["texto"].split()) * 0.34) / velocidade
        time.sleep(dur)
        falando["quem"] = None
        s.adicionar_fala(f["quem"], f["texto"])
        contagem[f["quem"]] += 1
        print(f"  {f['quem']}: {f['texto'][:70]}", flush=True)
        time.sleep(1.2 / velocidade)
        _aplicar_conselhos(s, rot, i, aplicados)
        time.sleep(f.get("pausa", 0.6) / velocidade)
    print(f"Simulação terminou. Painel continua aberto por {manter_s}s.", flush=True)
    time.sleep(manter_s)
    parar.set()
    escrever_json(s.estado, _estado_simulado(s, inicio, niveis, contagem, srv.urls, status="parado"))
    srv.encerrar()
    return 0


# ---------------------------------------------------------------------------------------------
def _sintetizar(texto: str, destino: Path, voz: str, taxa_fala: int = 0):
    if sys.platform == "win32":
        t = texto.replace("'", "''")
        ps = (
            "Add-Type -AssemblyName System.Speech;"
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            f"try{{$s.SelectVoice('{voz}')}}catch{{}};$s.Rate={taxa_fala};"
            "$f=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono);"
            f"$s.SetOutputToWaveFile('{destino}',$f);$s.Speak('{t}');$s.Dispose()"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True)
    elif sys.platform == "darwin":
        aiff = destino.with_suffix(".aiff")
        subprocess.run(["say", "-v", "Luciana", "-o", str(aiff), texto], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(destino)], check=True)
    else:
        raise RuntimeError("síntese de voz só no Windows e no Mac")


def _ler(p: Path) -> np.ndarray:
    with wave.open(str(p)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0


def _gravar(p: Path, x: np.ndarray):
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def simular_audio(roteiro: Path, velocidade=1.0, abrir=True, voz="Microsoft Maria Desktop"):
    from .motor import Motor

    rot = _carregar(roteiro)
    b = rot.get("briefing", {})
    tmp = Path(tempfile.mkdtemp(prefix="copiloto-sim-"))
    faixas = {"voce": [], "cliente": []}
    print("Sintetizando vozes …", flush=True)
    for i, f in enumerate(rot["falas"]):
        arq = tmp / f"{i:03d}.wav"
        _sintetizar(f["texto"], arq, voz, taxa_fala=1 if f["quem"] == "voce" else -1)
        x = _ler(arq)
        silencio = np.zeros(int(16000 * (0.7 + f.get("pausa", 0.6))), np.float32)
        outro = "cliente" if f["quem"] == "voce" else "voce"
        faixas[f["quem"]] += [x, silencio]
        faixas[outro] += [np.zeros(len(x), np.float32), silencio]
    arquivos = {}
    for c, partes in faixas.items():
        arquivos[c] = tmp / f"faixa_{c}.wav"
        x = np.concatenate([np.zeros(16000, np.float32)] + partes)
        x += np.random.normal(0, 0.002, len(x)).astype(np.float32)  # chiado leve, como num microfone de verdade
        _gravar(arquivos[c], x)
    s = Sessao.nova((b.get("cliente") or "simulacao") + " audio", b.get("modo", "venda"))
    escrever_json(s.briefing, {**b, "simulacao": True})
    motor = Motor(s, arquivos=arquivos, velocidade=velocidade)
    aplicados = set()

    def conselhos():
        while True:
            _aplicar_conselhos(s, rot, len(s.ler_falas()), aplicados)
            time.sleep(1)

    threading.Thread(target=conselhos, daemon=True).start()

    def abrir_quando_pronto():
        for _ in range(120):
            urls = getattr(motor.servidor, "urls", None)
            if urls:
                print(f"SESSAO={s.pasta}\nPAINEL={urls['pc']}", flush=True)
                if abrir:
                    webbrowser.open(urls["pc"])
                return
            time.sleep(0.5)

    threading.Thread(target=abrir_quando_pronto, daemon=True).start()
    t = time.time()
    motor.rodar()
    dur = time.time() - t
    # precisão: compara o que foi dito com o que foi transcrito
    from difflib import SequenceMatcher

    from .filtros import _norm

    esperado = {c: " ".join(f["texto"] for f in rot["falas"] if f["quem"] == c) for c in ("voce", "cliente")}
    obtido = {c: " ".join(f["texto"] for f in s.ler_falas() if f["quem"] == c) for c in ("voce", "cliente")}
    print(f"\nSimulação com áudio terminou em {dur:.0f}s. Sessão: {s.pasta}")
    for c in ("voce", "cliente"):
        sim = SequenceMatcher(None, _norm(esperado[c]).split(), _norm(obtido[c]).split(), autojunk=False).ratio()
        print(f"  {c}: semelhança com o roteiro {sim:.0%}  ({len(obtido[c].split())}/{len(esperado[c].split())} palavras)")
    return 0


def simular(roteiro: Path, audio=False, velocidade=1.0, abrir=True, voz="Microsoft Maria Desktop"):
    if audio:
        return simular_audio(roteiro, velocidade, abrir, voz)
    return simular_texto(roteiro, velocidade, abrir)
