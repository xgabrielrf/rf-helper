"""Leva cada janela nova do RF Online para o canto superior esquerdo do monitor principal.

Só mexe em janelas que **aparecem depois** do RF Helper abrir (as que já estavam abertas ficam onde o usuário
as deixou) e só **na posição**: o tamanho, a ordem e o foco não mudam. O jogo cria e reposiciona a janela
durante os primeiros segundos, então a posição é conferida por `SETTLE_S` depois que ela aparece; passado
esse tempo a janela é do usuário e pode ser arrastada para onde ele quiser.

Sem Tk e sem Windows aqui dentro: quem lista e move as janelas é injetado (`ClientPlacer.real()` liga ao Win32).
"""
import time

SETTLE_S = 8.0          # tempo em que a posição de uma janela nova é conferida
TOLERANCE = 2           # px: a moldura do jogo começa em -1, isso já conta como "no canto"


class ClientPlacer:
    def __init__(self, list_windows, rect_of, move, work_area, clock=time.monotonic):
        """`list_windows()` → [(hwnd, titulo, pid)]; `rect_of(hwnd)` → (esq, topo, dir, base) ou None (minimizada);
        `move(hwnd, esq, topo)`; `work_area()` → retângulo do monitor principal (sem a barra de tarefas) ou None."""
        self._list_windows = list_windows
        self._rect_of = rect_of
        self._move = move
        self._work_area = work_area
        self._clock = clock
        self._known = None          # hwnds já vistos; None até a primeira conferência
        self._settling = {}         # hwnd -> instante em que deixa de ser conferida

    @classmethod
    def real(cls, process_name="rf_online.bin"):
        from ..change_screen import winapi
        from ..shared import screens

        def primary_area():
            found, primary = screens.monitors(with_primary=True)
            return found[primary] if found else None
        return cls(lambda: winapi.find_windows(process_name), winapi.window_rect, winapi.move_window, primary_area)

    def update(self):
        """Uma conferência. Devolve os hwnds que foram movidos (para os testes e para o log)."""
        try:
            current = {hwnd for hwnd, _title, _pid in self._list_windows()}
        except OSError:
            return []
        if self._known is None:                 # primeira vez: o que já está aberto não é mexido
            self._known = current
            return []
        now = self._clock()
        for hwnd in current - self._known:
            self._settling[hwnd] = now + SETTLE_S
        self._known = current
        for hwnd in list(self._settling):
            if hwnd not in current or now > self._settling[hwnd]:
                del self._settling[hwnd]
        moved = []
        area = self._work_area() if self._settling else None
        if area is None:
            return moved
        for hwnd in self._settling:
            try:
                rect = self._rect_of(hwnd)
                if rect is None:                # minimizada: a posição dela não é uma posição de verdade
                    continue
                if abs(rect[0] - area[0]) > TOLERANCE or abs(rect[1] - area[1]) > TOLERANCE:
                    self._move(hwnd, area[0], area[1])
                    moved.append(hwnd)
            except OSError:
                continue
        return moved
