"""Ícone do RF Helper nas janelas e na barra de tarefas (o logo vem embutido em logo_data.py)."""
import base64
import ctypes
import tkinter as tk

from .logo_data import PNG_BASE64

APP_ID = "RFHelper"


def png_bytes(size):
    return base64.b64decode(PNG_BASE64[size])


def prepare():
    """Chamar ANTES de criar o Tk: dá ao processo uma identidade própria. Sem isso o Windows agrupa o
    programa sob o Python na barra de tarefas e mostra o ícone do pythonw."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass


def apply(root):
    """Põe o logo como ícone de `root` e de **toda janela criada depois** (iconphoto com default=True).
    Falha em silêncio: no pior caso fica o ícone padrão do Tk."""
    try:
        photos = [tk.PhotoImage(master=root, data=PNG_BASE64[size]) for size in sorted(PNG_BASE64)]
        root.iconphoto(True, *photos)
        root._rf_helper_icons = photos          # o Tk não guarda a referência
    except (tk.TclError, KeyError, ValueError):
        pass
