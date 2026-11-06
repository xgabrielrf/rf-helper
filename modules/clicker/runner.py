"""Execução do clicker/macro de UMA janela, numa thread própria.

A thread nunca toca no Tk: ao terminar chama `on_exit(runner, motivo)`, e quem chama
decide como levar isso à interface (ver manager.py, que usa uma queue).
"""
import heapq
import threading
import time

from . import sender
from .model import DELAY, MIN_CLICK_MS, MODE_MACRO
from .winapi import winmm

# Motivos de término
STOPPED, FINISHED, WINDOW_CLOSED, ACCESS_DENIED, FAILED = (
    "stopped", "finished", "window_closed", "access_denied", "failed")

MAX_CONSECUTIVE_FAILURES = 5    # timeouts seguidos antes de desistir da janela
MIN_LOOP_S = 0.01               # macro em loop sem tempos não pode inundar o jogo
RESYNC_S = 0.5                  # atraso acima disso (suspensão, travada) reinicia o relógio

_timer_lock = threading.Lock()
_timer_users = 0


def _timer_acquire():
    """Resolução de 1 ms enquanto houver algum runner ativo (o padrão do Windows é ~15 ms)."""
    global _timer_users
    with _timer_lock:
        _timer_users += 1
        if _timer_users == 1:
            winmm.timeBeginPeriod(1)


def _timer_release():
    global _timer_users
    with _timer_lock:
        _timer_users -= 1
        if _timer_users == 0:
            winmm.timeEndPeriod(1)


class Runner:
    def __init__(self, hwnd, cfg, on_exit):
        """`cfg`: cópia da configuração (o runner nunca vê edições feitas depois)."""
        self.hwnd = hwnd
        self.cfg = cfg
        self._on_exit = on_exit
        self._stop = threading.Event()
        self._failures = 0
        self._thread = threading.Thread(target=self._main, name=f"runner-{hwnd}", daemon=True)

    def start(self):
        _timer_acquire()
        self._thread.start()

    def stop(self):
        self._stop.set()

    @property
    def is_running(self):
        return self._thread.is_alive()

    def join(self, timeout=None):
        self._thread.join(timeout)

    # --- thread -------------------------------------------------------------
    def _main(self):
        try:
            if self.cfg.mode == MODE_MACRO:
                reason = self._run_macro()
            else:
                reason = self._run_click()
        except Exception:
            reason = FAILED
        finally:
            _timer_release()
        self._on_exit(self, reason)

    def _press(self, vk):
        """Envia a tecla. Retorna um motivo de término, ou None para continuar."""
        try:
            sender.send_key(self.hwnd, vk)
        except sender.WindowGone:
            return WINDOW_CLOSED
        except sender.AccessDenied:
            return ACCESS_DENIED
        except sender.SendError:
            self._failures += 1
            return FAILED if self._failures >= MAX_CONSECUTIVE_FAILURES else None
        self._failures = 0
        return None

    def _run_click(self):
        """Cada tecla com seu próprio período, em prazos absolutos (sem acumular deriva)."""
        rows = [(r.vk, max(MIN_CLICK_MS, r.ms) / 1000) for r in self.cfg.active_keys()]
        if not rows:
            return FINISHED
        start = time.perf_counter()
        heap = [(start, i) for i in range(len(rows))]
        heapq.heapify(heap)
        while True:
            due, i = heap[0]
            wait = due - time.perf_counter()
            if wait > 0 and self._stop.wait(wait):
                return STOPPED
            if self._stop.is_set():
                return STOPPED
            vk, period = rows[i]
            reason = self._press(vk)
            if reason:
                return reason
            nxt = due + period
            now = time.perf_counter()
            heapq.heapreplace(heap, (nxt if nxt >= now else now, i))

    def _run_macro(self):
        events = list(self.cfg.macro.events)
        loop = self.cfg.macro.loop
        clock = time.perf_counter()
        while True:
            loop_started = time.perf_counter()
            for event in events:
                if event.kind == DELAY:
                    clock += event.value / 1000
                    wait = clock - time.perf_counter()
                    if wait > 0:
                        if self._stop.wait(wait):
                            return STOPPED
                    elif wait < -RESYNC_S:
                        clock = time.perf_counter()
                    continue
                if self._stop.is_set():
                    return STOPPED
                reason = self._press(event.value)
                if reason:
                    return reason
            if not loop:
                return FINISHED
            spare = MIN_LOOP_S - (time.perf_counter() - loop_started)
            if spare > 0:
                if self._stop.wait(spare):
                    return STOPPED
                clock = time.perf_counter()
