"""Limpeza do texto transcrito: alucinações típicas do Whisper em português, repetições e eco."""
import re
import threading
import time
import unicodedata
from collections import deque
from difflib import SequenceMatcher

# frases que o Whisper inventa em silêncio/ruído (vieram de YouTube na base de treino)
ALUCINACOES = [
    r"legendas? (pela|por) .*amara\.org",
    r"amara\.org",
    r"obrigad[oa] por (assistir|ver|acompanhar)",
    r"inscreva-se( no canal)?",
    r"(ative|deixe) (o|seu) (sininho|like)",
    r"at[ée] o pr[óo]ximo v[íi]deo",
    r"legendado por",
    r"transcri[çc][ãa]o (de|por) ",
    r"^(tchau[,.! ]*)+$",
    r"^(m+h*m+|hmm+|uhum+|ah+|eh+|oh+)[.!?]*$",
    r"^(\.|,|!|\?|-|…|\s)*$",
    r"^(music|música|aplausos|risos|silêncio|\[.*\]|\(.*\))[.!]*$",
]
_RE_ALUC = [re.compile(p, re.I) for p in ALUCINACOES]
_RE_NAO_LATINO = re.compile(r"[^\u0000-ɏḀ-ỿ -⁯₠-⃏\s]")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", t).split())


def colapsar_repeticoes(texto: str) -> str:
    """'Quem? Quem? Quem? Quem?' -> 'Quem?' ; 'um, um, um, um' -> 'um' ; frases repetidas idem."""
    palavras = texto.split()
    if len(palavras) < 3:
        return texto
    for n in range(1, 7):  # n-gramas de 1 a 6 palavras
        out, i = [], 0
        while i < len(palavras):
            bloco = palavras[i : i + n]
            chave = [re.sub(r"\W", "", w.lower()) for w in bloco]
            j = i + n
            reps = 1
            while j + n <= len(palavras) and [re.sub(r"\W", "", w.lower()) for w in palavras[j : j + n]] == chave:
                reps += 1
                j += n
            if reps >= 3 and any(chave):
                out.extend(bloco)
                i = j
            else:
                out.append(palavras[i])
                i += 1
        palavras = out
    return " ".join(palavras)


def limpar(texto: str) -> str:
    t = _RE_NAO_LATINO.sub("", texto or "").strip()
    t = re.sub(r"\s+", " ", t)
    t = colapsar_repeticoes(t)
    if any(r.search(t) for r in _RE_ALUC) and len(t) < 90:
        return ""
    if len(re.sub(r"\W", "", t)) < 2:
        return ""
    return t


def parecido(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


class FiltroEco:
    """Sem fone, o microfone escuta o cliente pela caixa de som e a fala dele vira 'VOCÊ'.
    Segura a fala do VOCÊ por alguns segundos e descarta se for quase igual a uma fala do CLIENTE no mesmo momento."""

    def __init__(self, emitir, ativo: bool, espera_s: float = 4.0, janela_s: float = 8.0, limiar: float = 0.6):
        self.emitir = emitir  # fn(canal, texto, ts)
        self.ativo = ativo
        self.espera_s = espera_s
        self.janela_s = janela_s
        self.limiar = limiar
        self.cliente = deque(maxlen=40)
        self.pendentes = deque()
        self.trava = threading.Lock()
        self.descartadas = 0

    def entrada(self, canal: str, texto: str, ts: float) -> None:
        if not self.ativo:
            self.emitir(canal, texto, ts)
            return
        with self.trava:
            if canal == "cliente":
                self.cliente.append((ts, texto))
                self.emitir(canal, texto, ts)
            else:
                self.pendentes.append((time.time(), canal, texto, ts))
        self.tick()

    def tick(self) -> None:
        if not self.ativo:
            return
        agora = time.time()
        with self.trava:
            while self.pendentes and agora - self.pendentes[0][0] >= self.espera_s:
                _, canal, texto, ts = self.pendentes.popleft()
                eco = any(
                    abs(tc - ts) <= self.janela_s and parecido(texto, tx) >= self.limiar for tc, tx in self.cliente
                )
                if eco:
                    self.descartadas += 1
                else:
                    self.emitir(canal, texto, ts)

    def descarregar(self):
        self.espera_s = 0
        self.tick()
