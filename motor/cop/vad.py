"""Segmenta a fala pela pausa (em vez de blocos fixos de 20 s): corta quando a pessoa para de falar,
com teto de 12 s. Usa Silero VAD (silero-vad-lite, sem torch); se não tiver, cai para energia."""
from collections import deque

import numpy as np

TAXA = 16000

try:
    from silero_vad_lite import SileroVAD
except Exception:
    SileroVAD = None


class Segmentador:
    def __init__(self, ao_segmento, pausa_s: float = 0.9, max_s: float = 15.0, min_fala_s: float = 0.35):
        self.ao_segmento = ao_segmento  # fn(audio float32, ts_inicio)
        self.vad = SileroVAD(TAXA) if SileroVAD else None
        self.janela = self.vad.window_size_samples if self.vad else 512
        self.resto = np.zeros(0, np.float32)
        self.pre = deque(maxlen=int(0.3 * TAXA / self.janela) + 1)  # 300 ms antes da fala
        self.falando = False
        self.seg = []
        self.n_fala = 0
        self.n_silencio = 0
        self.t0 = 0.0
        self.janelas_pausa = int(pausa_s * TAXA / self.janela)
        self.janelas_max = int(max_s * TAXA / self.janela)
        self.janelas_min_fala = int(min_fala_s * TAXA / self.janela)
        self.piso = -60.0

    def _prob(self, x: np.ndarray) -> float:
        if self.vad is not None:
            try:
                return float(self.vad.process(np.ascontiguousarray(x, dtype=np.float32)))
            except Exception:
                pass
        db = 20 * np.log10(float(np.sqrt(np.mean(x * x))) + 1e-9)
        self.piso = min(self.piso + 0.02, db) if db < self.piso + 6 else self.piso + 0.01
        return float(np.clip((db - self.piso - 8) / 12, 0, 1))

    def alimentar(self, bloco: np.ndarray, ts: float) -> None:
        x = np.concatenate([self.resto, bloco]) if len(self.resto) else bloco
        n = len(x) // self.janela
        dur_bloco = len(bloco) / TAXA
        for i in range(n):
            j = x[i * self.janela : (i + 1) * self.janela]
            t = ts - dur_bloco + (i * self.janela - len(self.resto)) / TAXA
            p = self._prob(j)
            if not self.falando:
                self.pre.append(j)
                if p > 0.5:
                    self.falando = True
                    self.seg = list(self.pre)
                    self.t0 = t - len(self.pre) * self.janela / TAXA
                    self.n_fala, self.n_silencio = 1, 0
            else:
                self.seg.append(j)
                if p > 0.35:
                    self.n_fala += 1
                    self.n_silencio = 0
                else:
                    self.n_silencio += 1
                if self.n_silencio >= self.janelas_pausa or len(self.seg) >= self.janelas_max:
                    self._fechar(cortado=len(self.seg) >= self.janelas_max)
        self.resto = x[n * self.janela :].copy()

    def _fechar(self, cortado=False):
        if self.n_fala >= self.janelas_min_fala:
            audio = np.concatenate(self.seg)
            if not cortado and self.n_silencio > 6:
                audio = audio[: -(self.n_silencio - 6) * self.janela]  # tira o silêncio do fim
            self.ao_segmento(audio, self.t0)
        self.seg = []
        self.pre.clear()
        self.falando = cortado and self.n_silencio < self.janelas_pausa
        if self.falando:
            self.t0 += self.janelas_max * self.janela / TAXA
        self.n_fala = 1 if self.falando else 0
        self.n_silencio = 0

    def descarregar(self):
        if self.falando and self.seg:
            self._fechar()
