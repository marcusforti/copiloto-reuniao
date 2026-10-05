"""Informações da máquina: RAM livre, núcleos, sistema operacional."""
import os
import platform

try:
    import psutil
except Exception:  # psutil é opcional
    psutil = None

SO = platform.system()  # "Windows" | "Darwin" | "Linux"


def ram_livre_gb() -> float:
    if psutil:
        return psutil.virtual_memory().available / 2**30
    if SO == "Windows":
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
                (n, ctypes.c_ulonglong) for n in ("tot", "avail", "a", "b", "c", "d", "e")
            ]

        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.avail / 2**30
    return 4.0


def ram_total_gb() -> float:
    if psutil:
        return psutil.virtual_memory().total / 2**30
    return 8.0


def nucleos() -> int:
    if psutil:
        return psutil.cpu_count(logical=False) or os.cpu_count() or 4
    return max(1, (os.cpu_count() or 4) // 2)


def escolher_modelo(pedido: str = "auto") -> str:
    """small é o equilíbrio (≈0,5 GB, ~4x mais rápido que o tempo real num i7 de 4 núcleos).
    medium só em máquina folgada; base em máquina apertada."""
    if pedido and pedido != "auto":
        return pedido
    livre, n = ram_livre_gb(), nucleos()
    if n >= 8 and livre >= 6:
        return "medium"
    if n >= 4 and livre >= 1.5:
        return "small"
    return "base"


def threads_whisper() -> int:
    # deixa núcleo sobrando para o Meet/Zoom e o navegador
    return max(2, min(4, nucleos() - 1))
