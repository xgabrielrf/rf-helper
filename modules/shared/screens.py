"""Onde ficam os monitores e como manter uma janela sempre dentro de algum deles.

As regras (`fits`, `clamp`, `center_in`, `point_visible`) são puras: recebem a lista de monitores, e por isso
são testáveis sem Windows. `monitors()` pergunta ao Windows pelas áreas de trabalho (sem a barra de tarefas).
Todo retângulo é `(esquerda, topo, direita, base)` em pixels; vale uma janela por vez, com a moldura (barra de
título) incluída.

Regra do programa: uma janela pode **passar de um monitor para o outro** (o usuário arrasta), mas **nunca
pode ficar escondida**: ao soltar ou ao salvar, ela precisa caber nas áreas dos monitores; se não couber, é
puxada para dentro do monitor mais próximo.
"""
import ctypes
from ctypes import wintypes

SHADOW = 12             # as bordas invisíveis da moldura (sombra) do Windows 10/11 não contam como "fora"
MIN_VISIBLE = 0.97      # fração da janela que precisa estar sobre algum monitor
POINT_MARGIN = (80, 40)  # um canto salvo precisa ficar pelo menos isso para dentro de um monitor


def _area(rect):
    return max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])


def _intersect(a, b):
    return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))


def fits(rect, monitors, shadow=SHADOW):
    """A janela está (quase toda) sobre os monitores? Pode atravessar dois monitores vizinhos."""
    if not monitors:
        return True                     # sem informação: não mexe em nada
    # a sombra invisível dos lados e da base não é parte da janela que o usuário vê
    visible = (rect[0] + shadow, rect[1], rect[2] - shadow, rect[3] - shadow)
    total = _area(visible)
    if total <= 0:
        return False
    covered = sum(_area(_intersect(visible, m)) for m in monitors)
    return covered / total >= MIN_VISIBLE


def _nearest(rect, monitors):
    """Monitor com mais área em comum com a janela; sem nenhuma, o de centro mais perto."""
    best = max(monitors, key=lambda m: _area(_intersect(rect, m)))
    if _area(_intersect(rect, best)) > 0:
        return best
    cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
    return min(monitors, key=lambda m: ((m[0] + m[2]) / 2 - cx) ** 2 + ((m[1] + m[3]) / 2 - cy) ** 2)


def clamp(rect, monitors):
    """Retângulo de mesmo tamanho, deslocado o mínimo para caber no monitor mais próximo. Uma janela maior
    que o monitor fica com o canto superior esquerdo (e a barra de título) visível."""
    if not monitors:
        return rect
    m = _nearest(rect, monitors)
    width, height = rect[2] - rect[0], rect[3] - rect[1]
    left = m[0] if width >= m[2] - m[0] else min(max(rect[0], m[0]), m[2] - width)
    top = m[1] if height >= m[3] - m[1] else min(max(rect[1], m[1]), m[3] - height)
    return (left, top, left + width, top + height)


def center_in(monitor, width, height):
    """Canto superior esquerdo de uma janela `width`×`height` centrada no monitor."""
    return (monitor[0] + (monitor[2] - monitor[0] - width) // 2, monitor[1] + (monitor[3] - monitor[1] - height) // 2)


def point_visible(x, y, monitors, margin=POINT_MARGIN):
    """O canto (x, y) cai dentro de algum monitor, com folga? (Para uma posição lida do disco.)"""
    if not monitors:
        return True
    return any(m[0] - 10 <= x <= m[2] - margin[0] and m[1] - 10 <= y <= m[3] - margin[1] for m in monitors)


# --- Windows ---------------------------------------------------------------------------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)

MONITORINFOF_PRIMARY = 1
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


_MonitorEnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                      wintypes.LPARAM)
user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), _MonitorEnumProc, wintypes.LPARAM]
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MonitorInfo)]
user32.GetSystemMetrics.argtypes = [ctypes.c_int]


def monitors(with_primary=False):
    """Áreas de trabalho dos monitores (sem a barra de tarefas). Com `with_primary`, devolve também o índice
    do monitor principal. Se o Windows não responder, usa a área virtual inteira como um monitor só."""
    found, primary = [], 0

    @_MonitorEnumProc
    def callback(handle, _dc, _rect, _data):
        nonlocal primary
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            if info.dwFlags & MONITORINFOF_PRIMARY:
                primary = len(found)
            w = info.rcWork
            found.append((w.left, w.top, w.right, w.bottom))
        return True
    try:
        user32.EnumDisplayMonitors(None, None, callback, 0)
    except OSError:
        found = []
    if not found:
        left, top = user32.GetSystemMetrics(SM_XVIRTUALSCREEN), user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        width, height = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN), user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        if width > 0 and height > 0:
            found = [(left, top, left + width, top + height)]
    return (found, primary) if with_primary else found
