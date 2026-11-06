"""Win32 do login automático: achar processos, achar as partes do launcher e mexer nelas por mensagens.

Tudo por mensagens de janela (sem foco e sem mover o mouse do usuário). O launcher é do tipo CCR:
a tela de login é um diálogo (#32770) com dois `Edit` reais (ID e senha) e botões desenhados à mão;
a lista de servidores é outro diálogo de 330x540 desenhado pelo próprio launcher.
As medidas abaixo são do launcher do RF Brasil, em coordenadas de 96 dpi: a thread de login pede
"DPI não consciente" para o Windows devolver essas mesmas coordenadas em qualquer escala.
"""
import ctypes
import os
import subprocess
from ctypes import wintypes
from dataclasses import dataclass, field

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_CHAR, WM_CLOSE, WM_COMMAND = 0x0102, 0x0010, 0x0111
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK = 0x0200, 0x0201, 0x0202, 0x0203
MK_LBUTTON, BM_CLICK, EM_SETSEL, WM_GETTEXT = 0x0001, 0x00F5, 0x00B1, 0x000D
IDOK = 1
SMTO_ABORTIFHUNG = 0x0002
TH32CS_SNAPPROCESS = 0x2
PROCESS_TERMINATE = 0x0001
VK_BACK = 8

# Medidas do launcher (px a 96 dpi)
MAIN_MIN_WIDTH = 900            # o diálogo principal tem ~1015 px; modais são bem menores
MODAL_MAX_WIDTH = 700
LIST_SIZE = (330, 540)          # diálogo da lista de servidores (Launcher.xml, SLDlgInfo DLG_POS)
LOGIN_BUTTON_WIDTH = 66         # botão LOGIN (os outros da fileira têm 80 e 106)
LOGIN_BUTTON_BAND = 60          # o LOGIN fica até 60 px abaixo do campo de ID
FIRST_SERVER_CLICK = (60, 24)   # 1ª linha da lista, relativa ao diálogo da lista (LIST_RECT começa em y=16)

EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumProc, wintypes.LPARAM]
user32.EnumChildWindows.argtypes = [wintypes.HWND, EnumProc, wintypes.LPARAM]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t,
                                       wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]


@dataclass
class Modal:
    hwnd: int
    texts: tuple
    buttons: list = field(default_factory=list)


@dataclass
class LauncherState:
    main: int = 0
    edits: list = field(default_factory=list)       # [ID, senha] (esquerda → direita)
    login_button: int = 0
    server_list: int = 0
    modals: list = field(default_factory=list)

    @property
    def login_ready(self):
        return bool(self.main and len(self.edits) >= 2 and self.login_button and not self.modals)


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def logical_dpi_for_this_thread():
    """Faz esta thread enxergar o launcher (que não é DPI-aware) em coordenadas de 96 dpi."""
    try:
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-1))      # DPI_AWARENESS_CONTEXT_UNAWARE
    except (AttributeError, OSError):
        pass


def _class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _text(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def _rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def _visible(hwnd):
    return bool(user32.IsWindowVisible(hwnd))


def _children(hwnd):
    out = []

    @EnumProc
    def callback(child, _):
        out.append(child)
        return True
    user32.EnumChildWindows(hwnd, callback, 0)
    return out


def _tops_of(pids):
    out = []

    @EnumProc
    def callback(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            out.append(hwnd)
        return True
    user32.EnumWindows(callback, 0)
    return out


def _send(hwnd, msg, wparam=0, lparam=0, timeout_ms=1500):
    result = ctypes.c_size_t()
    user32.SendMessageTimeoutW(hwnd, msg, wparam, lparam, SMTO_ABORTIFHUNG, timeout_ms, ctypes.byref(result))
    return result.value


def _lparam(x, y):
    return (y << 16) | (x & 0xFFFF)


class Win32Api:
    """Tudo que o login precisa do Windows. `launcher.login` recebe uma instância (ou uma falsa, nos testes)."""

    # --- processos ------------------------------------------------------------
    def pids_named(self, image_name):
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        pids = set()
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        try:
            ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                if entry.szExeFile.lower() == image_name.lower():
                    pids.add(entry.th32ProcessID)
                ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snap)
        return pids

    def start(self, exe_path):
        """Abre o programa com a pasta dele como diretório de trabalho (o launcher usa caminhos relativos)."""
        return subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path)).pid

    def kill(self, pid):
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if handle:
            try:
                kernel32.TerminateProcess(handle, 1)
            finally:
                kernel32.CloseHandle(handle)

    # --- janelas do launcher ---------------------------------------------------
    def state(self, pids):
        st = LauncherState()
        for hwnd in _tops_of(set(pids)):
            if _class(hwnd) != "#32770" or not _visible(hwnd):
                continue
            left, _top, right, _bottom = _rect(hwnd)
            kids = _children(hwnd)
            if right - left > MAIN_MIN_WIDTH:
                st.main = hwnd
                st.edits = sorted((c for c in kids if _class(c) == "Edit" and _visible(c)), key=lambda c: _rect(c)[0])
                for child in kids:
                    r = _rect(child)
                    if _class(child) == "#32770" and _visible(child) and (r[2] - r[0], r[3] - r[1]) == LIST_SIZE:
                        st.server_list = child
                if len(st.edits) >= 2:
                    edit_top = _rect(st.edits[0])[1]
                    for child in kids:
                        r = _rect(child)
                        if (_class(child) == "Button" and _visible(child) and edit_top < r[1] <= edit_top + LOGIN_BUTTON_BAND
                                and r[2] - r[0] == LOGIN_BUTTON_WIDTH):
                            st.login_button = child
                            break
            elif right - left < MODAL_MAX_WIDTH:
                texts = tuple(_text(c) for c in kids if _class(c) == "Static" and _visible(c) and _text(c))
                buttons = [c for c in kids if _class(c) == "Button" and _visible(c)]
                if texts:       # sem texto = janelinha de "conectando", não é um aviso
                    st.modals.append(Modal(hwnd, texts, buttons))
        return st

    def replace_text(self, edit, text):
        """Apaga o campo (seleciona tudo + backspace) e digita `text` como teclado."""
        _send(edit, EM_SETSEL, 0, -1)
        user32.PostMessageW(edit, WM_CHAR, VK_BACK, 1)
        _sleep(0.2)
        for ch in text:
            user32.PostMessageW(edit, WM_CHAR, ord(ch), 1)
            _sleep(0.03)

    def read_text(self, edit):
        """Texto atual de um campo `Edit` comum (o de senha não pode ser lido de outro processo)."""
        buf = ctypes.create_unicode_buffer(256)
        _send(edit, WM_GETTEXT, 256, ctypes.addressof(buf))
        return buf.value

    def click_button(self, button):
        user32.PostMessageW(button, BM_CLICK, 0, 0)      # Post: o launcher pode abrir uma mensagem modal dentro do clique

    def click_at(self, hwnd, x, y, double=False):
        seq = [(WM_MOUSEMOVE, 0), (WM_LBUTTONDOWN, MK_LBUTTON), (WM_LBUTTONUP, 0)]
        if double:
            seq += [(WM_LBUTTONDBLCLK, MK_LBUTTON), (WM_LBUTTONUP, 0)]
        for msg, wparam in seq:
            user32.PostMessageW(hwnd, msg, wparam, _lparam(x, y))
            _sleep(0.06)

    def close_modal(self, modal):
        for button in modal.buttons[:1]:
            user32.PostMessageW(button, BM_CLICK, 0, 0)
        user32.PostMessageW(modal.hwnd, WM_COMMAND, IDOK, 0)

    def close_window(self, hwnd):
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def _sleep(seconds):
    import time
    time.sleep(seconds)
