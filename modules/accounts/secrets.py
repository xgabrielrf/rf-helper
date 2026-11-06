"""Proteção das senhas com o DPAPI do Windows (CryptProtectData), sem biblioteca externa.

O texto cifrado só abre para o mesmo usuário do Windows, no mesmo computador: copiar o
`servers.json` para outro PC/usuário não revela (nem entrega) as senhas. Não é proteção contra
quem já está logado como o usuário, só contra o arquivo em si (backup, nuvem, olhar por cima).
"""
import base64
import ctypes
from ctypes import wintypes

PREFIX = "dpapi:"
_ENTROPY = b"RF Helper accounts v1"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_pblob = ctypes.POINTER(_Blob)
crypt32.CryptProtectData.argtypes = [_pblob, wintypes.LPCWSTR, _pblob, ctypes.c_void_p, ctypes.c_void_p,
                                     wintypes.DWORD, _pblob]
crypt32.CryptProtectData.restype = wintypes.BOOL
crypt32.CryptUnprotectData.argtypes = [_pblob, ctypes.c_void_p, _pblob, ctypes.c_void_p, ctypes.c_void_p,
                                       wintypes.DWORD, _pblob]
crypt32.CryptUnprotectData.restype = wintypes.BOOL
kernel32.LocalFree.argtypes = [ctypes.c_void_p]
kernel32.LocalFree.restype = ctypes.c_void_p

CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _take(out):
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def protect(text):
    """'dpapi:<base64>' do texto, ou None se o Windows recusar."""
    raw, _keep = _blob(text.encode("utf-8"))
    entropy, _keep2 = _blob(_ENTROPY)
    out = _Blob()
    if not crypt32.CryptProtectData(ctypes.byref(raw), None, ctypes.byref(entropy), None, None,
                                    CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        return None
    return PREFIX + base64.b64encode(_take(out)).decode("ascii")


def unprotect(token):
    """Texto original, ou None se `token` não for nosso, estiver corrompido ou for de outro usuário/PC."""
    if not isinstance(token, str) or not token.startswith(PREFIX):
        return None
    try:
        data = base64.b64decode(token[len(PREFIX):], validate=True)
    except ValueError:
        return None
    raw, _keep = _blob(data)
    entropy, _keep2 = _blob(_ENTROPY)
    out = _Blob()
    if not crypt32.CryptUnprotectData(ctypes.byref(raw), None, ctypes.byref(entropy), None, None,
                                      CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        return None
    try:
        return _take(out).decode("utf-8")
    except UnicodeDecodeError:
        return None
