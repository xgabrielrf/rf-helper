"""Códigos de tecla (VK) e rótulos legíveis."""
import ctypes

from .winapi import user32

MODIFIER_VKS = {0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C}
EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x6F, 0x90}
IGNORED_VKS = {0x00, 0xE7, 0xFF}        # VK_PACKET e códigos reservados


def is_modifier(vk):
    return vk in MODIFIER_VKS


def is_sendable(vk):
    """Tecla que o clicker consegue enviar: única, não modificadora."""
    return 0 < vk < 0xFF and vk not in MODIFIER_VKS and vk not in IGNORED_VKS


def key_label(vk):
    scan = user32.MapVirtualKeyW(vk, 0)
    lparam = (scan << 16) | ((1 << 24) if vk in EXTENDED_VKS else 0)
    buf = ctypes.create_unicode_buffer(64)
    if scan and user32.GetKeyNameTextW(lparam, buf, 64):
        return buf.value
    return f"VK {vk}"
