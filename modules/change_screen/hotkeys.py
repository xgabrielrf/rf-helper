"""Atalhos globais (teclado + mouse) via hooks de baixo nível do Windows.

Os hooks rodam numa thread própria com message loop. Eventos são entregues à
thread do Tk por uma queue: ("action", nome) ou ("capture", binding | None).
"""
import ctypes
import queue
import threading
from ctypes import wintypes

from .winapi import HOOKPROC, kernel32, user32

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
HC_ACTION = 0
WM_QUIT = 0x0012
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_MBUTTONDOWN, WM_MBUTTONUP, WM_XBUTTONDOWN, WM_XBUTTONUP = 0x207, 0x208, 0x20B, 0x20C
LLKHF_INJECTED, LLMHF_INJECTED = 0x10, 0x01

VK_ESCAPE = 0x1B
VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
MODIFIER_VKS = {0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C}
EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x6F, 0x90}

MODIFIER_LABELS = {0xA0: "Shift Esq.", 0xA1: "Shift Dir.", 0xA2: "Ctrl Esq.", 0xA3: "Ctrl Dir.",
                   0xA4: "Alt Esq.", 0xA5: "Alt Gr"}
FAKE_LCTRL_SCAN = 0x21D     # Ctrl "falso" que o Windows injeta junto com o Alt Gr

MOUSE_LABELS = {"middle": "Botão do meio", "x1": "Mouse lateral 1 (X1)", "x2": "Mouse lateral 2 (X2)"}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


def format_binding(binding):
    if not binding:
        return "(não cadastrado)"
    parts = [name for flag, name in (("ctrl", "Ctrl"), ("alt", "Alt"), ("shift", "Shift"))
             if binding.get(flag)]
    parts.append(binding.get("label") or "?")
    return "+".join(parts)


def valid_binding(binding):
    """Valida um binding vindo do config.json."""
    if not isinstance(binding, dict):
        return False
    if binding.get("type") == "key":
        return isinstance(binding.get("vk"), int)
    if binding.get("type") == "mouse":
        return binding.get("button") in MOUSE_LABELS
    return False


def _is_modifier_binding(binding):
    return binding.get("type") == "key" and binding.get("vk") in MODIFIER_LABELS


def _same_trigger(a, b):
    if _is_modifier_binding(a) or _is_modifier_binding(b):   # modificador sozinho: ignora o estado dos demais
        return a.get("type") == b.get("type") and a.get("vk") == b.get("vk")
    return (a.get("type") == b.get("type")
            and a.get("vk") == b.get("vk")
            and a.get("button") == b.get("button")
            and all(bool(a.get(m)) == bool(b.get(m)) for m in ("ctrl", "alt", "shift")))


def _key_label(vk):
    scan = user32.MapVirtualKeyW(vk, 0)
    lparam = (scan << 16) | ((1 << 24) if vk in EXTENDED_VKS else 0)
    buf = ctypes.create_unicode_buffer(64)
    if scan and user32.GetKeyNameTextW(lparam, buf, 64):
        return buf.value
    return f"VK {vk}"


class HotkeyManager:
    def __init__(self):
        self.events = queue.Queue()
        self.enabled = True
        self._bindings = {}          # ação -> binding
        self._capturing = False
        self._pending_mod = None     # modificador apertado durante a captura (vira atalho se soltar sozinho)
        self._swallowed = set()      # teclas/botões cujo "down" foi consumido (consumir também o "up")
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()
        # Referências mantidas: o GC não pode coletar os callbacks enquanto o hook existir.
        self._kb_cb = HOOKPROC(self._keyboard_proc)
        self._ms_cb = HOOKPROC(self._mouse_proc)

    # --- API usada pela UI -------------------------------------------------
    def set_binding(self, action, binding):
        bindings = dict(self._bindings)
        if binding:
            bindings[action] = binding
        else:
            bindings.pop(action, None)
        self._bindings = bindings

    def start_capture(self):
        self._pending_mod = None
        self._capturing = True

    def cancel_capture(self):
        self._pending_mod = None
        self._capturing = False

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(2)

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    # --- thread dos hooks ---------------------------------------------------
    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        hmod = kernel32.GetModuleHandleW(None)
        kb_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_cb, hmod, 0)
        ms_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._ms_cb, hmod, 0)
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        for hook in (kb_hook, ms_hook):
            if hook:
                user32.UnhookWindowsHookEx(hook)

    @staticmethod
    def _pressed(vk):
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)

    def _modifiers(self):
        return {"ctrl": self._pressed(VK_CONTROL), "alt": self._pressed(VK_MENU),
                "shift": self._pressed(VK_SHIFT)}

    def _keyboard_proc(self, n_code, w_param, l_param):
        if n_code == HC_ACTION:
            try:
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if info.vkCode == 0xA2 and info.scanCode == FAKE_LCTRL_SCAN:
                    return user32.CallNextHookEx(None, n_code, w_param, l_param)
                if self._handle(("k", info.vkCode), w_param in (WM_KEYDOWN, WM_SYSKEYDOWN),
                                w_param in (WM_KEYUP, WM_SYSKEYUP),
                                bool(info.flags & LLKHF_INJECTED),
                                info.vkCode in MODIFIER_VKS):
                    return 1
            except Exception:
                pass
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _mouse_proc(self, n_code, w_param, l_param):
        if n_code == HC_ACTION and w_param in (
                WM_MBUTTONDOWN, WM_MBUTTONUP, WM_XBUTTONDOWN, WM_XBUTTONUP):
            try:
                info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if w_param in (WM_MBUTTONDOWN, WM_MBUTTONUP):
                    button = "middle"
                else:
                    button = "x1" if (info.mouseData >> 16) & 0xFFFF == 1 else "x2"
                if self._handle(("m", button), w_param in (WM_MBUTTONDOWN, WM_XBUTTONDOWN),
                                w_param in (WM_MBUTTONUP, WM_XBUTTONUP),
                                bool(info.flags & LLMHF_INJECTED), False):
                    return 1
            except Exception:
                pass
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _handle(self, key, is_down, is_up, injected, is_modifier):
        """Retorna True se o evento deve ser consumido (não chega ao sistema/jogo)."""
        if injected:
            return False
        kind, value = key
        bindable_mod = is_modifier and value in MODIFIER_LABELS

        if is_up:
            if key in self._swallowed:
                self._swallowed.discard(key)
                return True
            if self._capturing and self._pending_mod == key:     # modificador solto sozinho
                self._pending_mod = None
                self._capturing = False
                self._swallowed.discard(key)
                self.events.put(("capture", {"type": "key", "vk": value, "ctrl": False,
                                             "alt": False, "shift": False,
                                             "label": MODIFIER_LABELS[value]}))
            return False
        if not is_down:
            return False
        if key in self._swallowed:      # auto-repeat de tecla já tratada
            return True

        if self._capturing:
            if is_modifier:
                if bindable_mod and self._pending_mod is None:
                    self._pending_mod = key
                return False
            self._pending_mod = None
            self._capturing = False
            self._swallowed.add(key)
            mods = self._modifiers()
            if kind == "k" and value == VK_ESCAPE and not any(mods.values()):
                self.events.put(("capture", None))
            else:
                binding = dict(mods)
                if kind == "k":
                    binding.update(type="key", vk=value, label=_key_label(value))
                else:
                    binding.update(type="mouse", button=value, label=MOUSE_LABELS[value])
                self.events.put(("capture", binding))
            return True

        if not self.enabled:
            return False
        probe = {} if bindable_mod else self._modifiers()
        if kind == "k":
            probe.update(type="key", vk=value)
        else:
            probe.update(type="mouse", button=value)
        for action, binding in self._bindings.items():
            if _same_trigger(binding, probe):
                self._swallowed.add(key)
                self.events.put(("action", action))
                return True
        return False
