"""Wrappers ctypes das funções Win32 usadas pelo clicker."""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
winmm = ctypes.WinDLL("winmm")

LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
HWND = ctypes.c_void_p

HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)

user32.SendMessageTimeoutW.argtypes = [HWND, wintypes.UINT, WPARAM, LPARAM, wintypes.UINT,
                                       wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = LRESULT
user32.IsWindow.argtypes = [HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.GetKeyNameTextW.argtypes = [wintypes.LONG, wintypes.LPWSTR, ctypes.c_int]
user32.GetKeyNameTextW.restype = ctypes.c_int

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, WPARAM, LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, WPARAM, LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = ctypes.c_void_p

winmm.timeBeginPeriod.argtypes = [wintypes.UINT]
winmm.timeEndPeriod.argtypes = [wintypes.UINT]
