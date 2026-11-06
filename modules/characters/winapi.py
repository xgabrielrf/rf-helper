"""Caminho do executável e hora de criação de um processo (ctypes, só leitura)."""
import ctypes
from datetime import datetime
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
FILETIME_EPOCH_OFFSET = 116444736000000000      # 1601-01-01 → 1970-01-01, em unidades de 100 ns


class FILETIME(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    def value(self):
        return (self.high << 32) | self.low


kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    ctypes.c_void_p, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(FILETIME)] * 4
kernel32.GetProcessTimes.restype = wintypes.BOOL


def process_info(pid):
    """(caminho do .exe, hora de criação em horário local sem fuso) ou None se não for legível.
    A hora local é a mesma base de tempo das linhas do log do RF."""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(2048)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return None
        created, ignored1, ignored2, ignored3 = FILETIME(), FILETIME(), FILETIME(), FILETIME()
        if not kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(ignored1),
                                        ctypes.byref(ignored2), ctypes.byref(ignored3)):
            return None
        seconds = (created.value() - FILETIME_EPOCH_OFFSET) / 1e7
        return buf.value, datetime.fromtimestamp(seconds)
    finally:
        kernel32.CloseHandle(handle)
