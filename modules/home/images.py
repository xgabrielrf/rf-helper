"""Ícone do servidor: qualquer imagem que o Windows (GDI+) abra — png, jpg, ico... — vira um PNG
quadrado de 48 px guardado em %APPDATA%\\ChangeScreenRF\\icons, que o Tk carrega sem biblioteca extra.
"""
import ctypes
import os
import tkinter as tk
from ctypes import wintypes

ICON_SIZE = 48
ICONS_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ChangeScreenRF", "icons")

_PNG_ENCODER = (0x557CF406, 0x1A04, 0x11D3, bytes([0x9A, 0x73, 0x00, 0x00, 0xF8, 0x1E, 0xF3, 0x2E]))
_PIXEL_FORMAT_ARGB = 0x26200A
_INTERPOLATION_HIGH_QUALITY_BICUBIC = 7

gdiplus = ctypes.WinDLL("gdiplus")


class _GdiplusInput(ctypes.Structure):
    _fields_ = [("GdiplusVersion", wintypes.UINT), ("DebugEventCallback", ctypes.c_void_p),
                ("SuppressBackgroundThread", wintypes.BOOL), ("SuppressExternalCodecs", wintypes.BOOL)]


class _Guid(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


def _call(name, *args):
    return getattr(gdiplus, name)(*args) == 0       # Status.Ok


def convert(source, dest, size=ICON_SIZE):
    """Grava em `dest` (PNG, `size`×`size`, mantendo a proporção sobre fundo transparente).
    Retorna False se a imagem não puder ser lida ou gravada."""
    token = ctypes.c_void_p()
    start = _GdiplusInput(1, None, False, False)
    if gdiplus.GdiplusStartup(ctypes.byref(token), ctypes.byref(start), None) != 0:
        return False
    src, dst, graphics = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    try:
        if not _call("GdipCreateBitmapFromFile", ctypes.c_wchar_p(source), ctypes.byref(src)):
            return False
        w, h = wintypes.UINT(), wintypes.UINT()
        gdiplus.GdipGetImageWidth(src, ctypes.byref(w))
        gdiplus.GdipGetImageHeight(src, ctypes.byref(h))
        if not w.value or not h.value:
            return False
        scale = min(size / w.value, size / h.value)
        dw, dh = max(1, round(w.value * scale)), max(1, round(h.value * scale))
        if not (_call("GdipCreateBitmapFromScan0", size, size, 0, _PIXEL_FORMAT_ARGB, None, ctypes.byref(dst))
                and _call("GdipGetImageGraphicsContext", dst, ctypes.byref(graphics))):
            return False
        gdiplus.GdipSetInterpolationMode(graphics, _INTERPOLATION_HIGH_QUALITY_BICUBIC)
        if not _call("GdipDrawImageRectI", graphics, src, (size - dw) // 2, (size - dh) // 2, dw, dh):
            return False
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        clsid = _Guid(_PNG_ENCODER[0], _PNG_ENCODER[1], _PNG_ENCODER[2], (ctypes.c_ubyte * 8)(*_PNG_ENCODER[3]))
        return _call("GdipSaveImageToFile", dst, ctypes.c_wchar_p(dest), ctypes.byref(clsid), None)
    finally:
        for handle, free in ((graphics, "GdipDeleteGraphics"), (dst, "GdipDisposeImage"), (src, "GdipDisposeImage")):
            if handle.value:
                getattr(gdiplus, free)(handle)
        gdiplus.GdiplusShutdown(token)


def cache_path(server_id):
    return os.path.join(ICONS_DIR, f"{server_id}.png")


def prepare(server_id, source):
    """Converte `source` para o cache do servidor. Retorna True se há um ícone válido em cache
    (source vazio/ilegível apaga o cache e retorna False)."""
    dest = cache_path(server_id)
    if source and os.path.isfile(source) and convert(source, dest):
        return True
    forget(server_id)
    return False


def forget(server_id):
    try:
        os.remove(cache_path(server_id))
    except OSError:
        pass


def load(master, server_id):
    """PhotoImage do ícone em cache, ou None."""
    path = cache_path(server_id)
    if not os.path.isfile(path):
        return None
    try:
        return tk.PhotoImage(master=master, file=path)
    except tk.TclError:
        return None
