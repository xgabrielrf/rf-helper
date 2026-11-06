"""Detalhes de janela compartilhados: sem botão X, posição lembrada e **sempre dentro de algum monitor**.

Regra do programa (vale para a tela inicial, o Modo grupo e todas as janelas extras): o usuário pode arrastar
uma janela entre monitores, mas ela nunca fica escondida fora das telas, e uma posição fora das telas nunca é
salva. Ao abrir, ao soltar (depois de arrastar) e ao salvar, a janela é puxada para dentro do monitor mais
próximo se não couber. As contas de geometria estão em `modules/shared/screens.py` (puras, testáveis).
"""
import ctypes
import re
import tkinter as tk
from ctypes import wintypes

from ..shared import screens

user32 = ctypes.WinDLL("user32", use_last_error=True)

GWL_STYLE = -16
WS_SYSMENU = 0x00080000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x4, 0x10, 0x20
VK_LBUTTON = 0x01
SETTLE_MS = 400                 # tempo parado depois de um movimento até conferir se a janela cabe nas telas

POSITION_RE = re.compile(r"^([+-]\d+)([+-]\d+)$")

user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short


def hide_close_button(win):
    """Tira o botão X (e o menu de sistema) da barra de título, que continua mostrando o título e
    permitindo arrastar a janela. Quem fecha a janela é o botão OK dela. Falha em silêncio."""
    try:
        win.update_idletasks()
        frame = user32.GetParent(win.winfo_id())
        if not frame:
            return
        style = user32.GetWindowLongW(frame, GWL_STYLE)
        user32.SetWindowLongW(frame, GWL_STYLE, style & ~WS_SYSMENU)
        user32.SetWindowPos(frame, None, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
                            | SWP_NOACTIVATE | SWP_FRAMECHANGED)
    except (OSError, ctypes.ArgumentError, AttributeError):
        pass


def frame_rect(win):
    """(esquerda, topo, direita, base) da janela inteira (moldura incluída), em pixels de tela."""
    win.update_idletasks()
    hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
    rect = wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)) and rect.right > rect.left:
        return rect.left, rect.top, rect.right, rect.bottom
    x, y = win.winfo_x(), win.winfo_y()
    return x, y, x + win.winfo_width(), y + win.winfo_height()


def _shift_to_fit(win):
    """(dx, dy) que põe a janela dentro de um monitor, ou None se ela já está nas telas."""
    rect = frame_rect(win)
    found = screens.monitors()
    if screens.fits(rect, found):
        return None
    moved = screens.clamp(rect, found)
    return moved[0] - rect[0], moved[1] - rect[1]


def _move_by(win, dx, dy):
    win.geometry(f"{win.winfo_x() + dx:+d}{win.winfo_y() + dy:+d}")


def current_position(win):
    """'+x+y' (como o Tk escreve em geometry) do canto superior esquerdo da janela, **sempre dentro das telas**:
    se a janela estiver escondida (ou quase) fora delas, devolve onde ela ficaria depois de puxada para dentro.
    É o que se grava no config: uma posição fora das telas nunca é salva."""
    x, y = win.winfo_x(), win.winfo_y()
    shift = _shift_to_fit(win)
    if shift:
        x, y = x + shift[0], y + shift[1]
    return f"{x:+d}{y:+d}"


def visible_position(position):
    """`position` ('+x+y') se tiver o formato certo e o canto cair dentro de algum monitor que existe agora
    (um monitor pode ter sido desligado desde que a posição foi salva); senão None. O ajuste fino do
    tamanho da janela é feito por `keep_on_screen`."""
    match = POSITION_RE.match(position) if isinstance(position, str) else None
    if not match:
        return None
    return position if screens.point_visible(int(match[1]), int(match[2]), screens.monitors()) else None


def center_on_screen(win):
    """Centraliza a janela no monitor principal (usado pela tela inicial, que sempre abre no meio)."""
    found, primary = screens.monitors(with_primary=True)
    if not found:
        return
    left, top, right, bottom = frame_rect(win)
    x, y = screens.center_in(found[primary], right - left, bottom - top)
    _move_by(win, x - left, y - top)


def keep_on_screen(win):
    """Garante agora e **depois de cada movimento** que a janela cabe nas telas. Dá para arrastá-la de um
    monitor para outro (ela pode atravessar os dois no meio do caminho); se ela for solta escondida, é
    puxada de volta para dentro do monitor mais próximo, depois de ficar parada por um instante."""
    state = {"job": None}

    def fix():
        state["job"] = None
        try:
            if not win.winfo_exists():
                return
            if user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000:      # ainda arrastando: espera soltar
                state["job"] = win.after(SETTLE_MS, fix)
                return
            shift = _shift_to_fit(win)
            if shift:
                _move_by(win, *shift)
        except (tk.TclError, OSError):
            pass

    def on_configure(event):
        if event.widget is not win:
            return
        if state["job"] is not None:
            try:
                win.after_cancel(state["job"])
            except tk.TclError:
                return
        state["job"] = win.after(SETTLE_MS, fix)

    win.bind("<Configure>", on_configure, add="+")
    try:
        win.update_idletasks()
        shift = _shift_to_fit(win)
        if shift:
            _move_by(win, *shift)
    except (tk.TclError, OSError):
        pass
