"""Ícones de estado do clicker, desenhados por código (sem arquivos de imagem).

Dois desenhos (tecla = modo Click, círculo com play = modo Macro) × três cores (estado).
"""
import tkinter as tk

from .manager import OFF, ON, UNSET
from .model import MODE_MACRO

COLORS = {UNSET: "#9a9a9a", OFF: "#d13b3b", ON: "#2e9e4f"}
MARK = "#ffffff"
BASE_SIZE = 16

_size = BASE_SIZE
_master = None
_cache = {}


def init(master):
    """Chamar uma vez, com o Tk já criado. Ajusta o tamanho ao DPI (a UI é DPI-aware)."""
    global _size, _master
    _master = master
    _size = max(BASE_SIZE, round(BASE_SIZE * master.winfo_fpixels("1i") / 96))
    _cache.clear()


def get(mode, state):
    key = (mode, state)
    if key not in _cache:
        _cache[key] = _draw(mode, COLORS[state])
    return _cache[key]


def _round_rect(u, v, x0, y0, x1, y1, r):
    if not (x0 <= u <= x1 and y0 <= v <= y1):
        return False
    cx, cy = min(max(u, x0 + r), x1 - r), min(max(v, y0 + r), y1 - r)
    return (u - cx) ** 2 + (v - cy) ** 2 <= r * r


def _keycap(u, v):
    if not _round_rect(u, v, 1, 2, 15, 14, 3):
        return None
    ring = _round_rect(u, v, 2.6, 3.4, 13.4, 11.4, 1.8) and not _round_rect(
        u, v, 3.8, 4.6, 12.2, 10.2, 0.8)
    return "mark" if ring else "body"


def _play(u, v):
    if (u - 8) ** 2 + (v - 8) ** 2 > 7 ** 2:
        return None
    in_triangle = 6 <= u <= 11.5 and abs(v - 8) <= (11.5 - u) * (3.6 / 5.5)
    return "mark" if in_triangle else "body"


def _draw(mode, color):
    shape = _play if mode == MODE_MACRO else _keycap
    size = _size
    img = tk.PhotoImage(master=_master, width=size, height=size)
    for y in range(size):
        x = 0
        while x < size:
            part = shape((x + 0.5) * BASE_SIZE / size, (y + 0.5) * BASE_SIZE / size)
            end = x + 1
            while end < size and shape((end + 0.5) * BASE_SIZE / size,
                                       (y + 0.5) * BASE_SIZE / size) == part:
                end += 1
            if part:
                img.put(color if part == "body" else MARK, to=(x, y, end, y + 1))
            x = end
    return img
