"""Gravação de teclas (para a macro) com um hook global de teclado, ativo só enquanto grava.

O hook nunca consome nada e só enfileira `(vk, instante)`; quem grava lê `events` na thread
do Tk. O instante é medido dentro do hook, então a latência do polling da UI não distorce os tempos.
"""
import ctypes
import queue
import threading
import time
from ctypes import wintypes

from . import keys
from .winapi import HOOKPROC, kernel32, user32

WH_KEYBOARD_LL, HC_ACTION, WM_QUIT = 13, 0, 0x0012
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
LLKHF_INJECTED = 0x10


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class KeyRecorder:
    def __init__(self):
        self.events = queue.Queue()     # (vk, perf_counter)
        self._down = set()              # filtra o auto-repeat de tecla segurada
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()
        self._cb = HOOKPROC(self._proc)  # o GC não pode coletar o callback enquanto o hook existir

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.is_running:
            return
        self._down.clear()
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="key-recorder", daemon=True)
        self._thread.start()
        self._ready.wait(2)

    def stop(self):
        if self._thread_id and self.is_running:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(1)
        self._thread, self._thread_id = None, None

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._cb,
                                        kernel32.GetModuleHandleW(None), 0)
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if hook:
            user32.UnhookWindowsHookEx(hook)

    def _proc(self, n_code, w_param, l_param):
        if n_code == HC_ACTION:
            try:
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = info.vkCode
                if not info.flags & LLKHF_INJECTED and keys.is_sendable(vk):
                    if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        if vk not in self._down:
                            self._down.add(vk)
                            self.events.put((vk, time.perf_counter()))
                    elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                        self._down.discard(vk)
            except Exception:
                pass
        return user32.CallNextHookEx(None, n_code, w_param, l_param)
