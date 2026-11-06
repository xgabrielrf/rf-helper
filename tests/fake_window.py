"""Janela falsa para testar o envio de teclas: registra as mensagens que recebe.

Os testes sempre miram o HWND desta janela. Nunca procuram janelas do RF.
"""
import ctypes
import itertools
import threading
import time
from ctypes import wintypes as w

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
WATCH = {0x06: "ACTIVATE", 0x86: "NCACTIVATE", 0x100: "KEYDOWN", 0x101: "KEYUP"}
WM_CLOSE, WM_DESTROY = 0x0010, 0x0002
_counter = itertools.count(1)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetModuleHandleW.restype = w.HMODULE
user32.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.restype = w.HWND
user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU,
                                   w.HINSTANCE, w.LPVOID]
user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.IsWindow.argtypes = [w.HWND]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE), ("hIcon", w.HANDLE),
                ("hCursor", w.HANDLE), ("hbrBackground", w.HANDLE),
                ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR)]


class FakeWindow:
    def __init__(self):
        self.log = []                       # (instante, nome, wparam)
        self.hwnd = None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(5) or not self.hwnd:
            raise RuntimeError("janela falsa não subiu")

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg in WATCH:
            with self._lock:
                self.log.append((time.perf_counter(), WATCH[msg], wparam))
            return 1 if msg == 0x86 else 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _run(self):
        self._cb = WNDPROC(self._proc)
        name = f"RFHelperFakeWindow{next(_counter)}_{id(self)}"
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW(lpfnWndProc=self._cb, hInstance=hinst, lpszClassName=name)
        user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(0, name, "RF Helper fake window", 0, 0, 0, 10, 10,
                                           None, None, hinst, None)
        self._ready.set()
        msg = w.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def snapshot(self):
        with self._lock:
            return list(self.log)

    def keydowns(self, vk=None):
        return [t for t, name, wp in self.snapshot()
                if name == "KEYDOWN" and (vk is None or wp == vk)]

    def close(self):
        if self.hwnd and user32.IsWindow(self.hwnd):
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        self._thread.join(2)
