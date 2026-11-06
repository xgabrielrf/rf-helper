"""Envio de uma tecla a uma janela, sem foco: a mesma sequência do RFClicker original."""
import ctypes

from .winapi import user32

WM_ACTIVATE, WM_KEYDOWN, WM_KEYUP, WM_NCACTIVATE = 0x0006, 0x0100, 0x0101, 0x0086
SMTO_ABORTIFHUNG = 0x0002
ERROR_ACCESS_DENIED = 5
SEND_TIMEOUT_MS = 250       # janela travada não pode segurar o Stop por muito tempo


class SendError(Exception):
    pass


class WindowGone(SendError):
    """A janela deixou de existir."""


class AccessDenied(SendError):
    """UIPI: o RF está elevado e este programa não."""


def _send(hwnd, msg, wparam):
    result = ctypes.c_size_t()
    if user32.SendMessageTimeoutW(hwnd, msg, wparam, 0, SMTO_ABORTIFHUNG,
                                  SEND_TIMEOUT_MS, ctypes.byref(result)):
        return
    error = ctypes.get_last_error()
    if not user32.IsWindow(hwnd):
        raise WindowGone()
    if error == ERROR_ACCESS_DENIED:
        raise AccessDenied()
    raise SendError(f"SendMessageTimeout falhou (erro {error})")


def send_key(hwnd, vk):
    """Ativa a janela (sem trazê-la à frente), aperta e solta `vk`, e desfaz a ativação."""
    _send(hwnd, WM_ACTIVATE, 1)
    _send(hwnd, WM_KEYDOWN, vk)
    _send(hwnd, WM_KEYUP, vk)
    _send(hwnd, WM_NCACTIVATE, 0)
