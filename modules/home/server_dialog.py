"""Formulário de servidor: nome, launcher do jogo e ícone (opcional)."""
import tkinter as tk
from tkinter import filedialog, messagebox

from ..accounts.model import Server, clean
from . import theme

IMAGE_TYPES = [("Imagens", "*.png *.jpg *.jpeg *.ico *.bmp *.gif"), ("Todos os arquivos", "*.*")]


def ask(parent, server=None, position=None, remember=None):
    """Abre o formulário (vazio ou com os dados de `server`). Retorna (nome, launcher, ícone)
    ou None se cancelado."""
    win = theme.dialog(parent, "Editar servidor" if server else "Novo servidor")
    result = []
    name = tk.StringVar(value=server.name if server else "")
    launcher = tk.StringVar(value=server.launcher_path if server else "")
    icon = tk.StringVar(value=server.icon_path if server else "")
    error = tk.StringVar()

    body = tk.Frame(win, bg=theme.PANEL)
    body.grid(row=0, column=0, padx=18, pady=(14, 6))
    theme.label(body, "Novo servidor" if not server else "Editar servidor", font=theme.FONT_BIG).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

    def field(row, title, hint, var, browse=None):
        text = tk.Frame(body, bg=theme.PANEL)
        text.grid(row=row * 2 + 1, column=0, columnspan=2, sticky="w", pady=(6, 3))
        theme.label(text, title).pack(side="left")
        if hint:
            theme.label(text, "  " + hint, fg=theme.MUTED, font=theme.FONT_SMALL).pack(side="left")
        entry = theme.entry(body, var, width=46)
        entry.grid(row=row * 2 + 2, column=0, sticky="ew", ipady=6)
        if browse:
            theme.button(body, "...", browse, bg=theme.BLUE, padx=12, pady=5).grid(
                row=row * 2 + 2, column=1, sticky="ns", padx=(6, 0))
        return entry

    first = field(0, "Nome do servidor *", "", name)
    field(1, "Caminho do launcher *", "", launcher, lambda: _pick(
        launcher, "Escolha o launcher do jogo", [("Executável", "*.exe"), ("Todos os arquivos", "*.*")]))
    field(2, "Caminho do ícone", "(.png / .jpg / .ico) (Opcional)", icon, lambda: _pick(
        icon, "Escolha a imagem do ícone", IMAGE_TYPES))
    theme.label(body, textvariable=error, fg="#ff7b7b", font=theme.FONT_SMALL, wraplength=380,
                justify="left").grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def save():
        candidate = Server(clean(name.get()), launcher.get().strip().strip('"'), icon.get().strip().strip('"'))
        problem = candidate.error()
        if problem:
            error.set(problem)
            return
        warning = candidate.warning()
        if warning and not messagebox.askyesno("Confira o launcher", f"{warning}\n\nSalvar mesmo assim?",
                                               parent=win):
            return
        result.append((candidate.name, candidate.launcher_path, candidate.icon_path))
        win.destroy()

    buttons = tk.Frame(win, bg=theme.PANEL)
    buttons.grid(row=1, column=0, sticky="e", padx=18, pady=(8, 14))
    theme.button(buttons, "Cancelar", win.destroy).pack(side="left", padx=(0, 8))
    theme.button(buttons, "Salvar", save, bg=theme.GREEN).pack(side="left")
    win.bind("<Return>", lambda _e: save())
    theme.finish(win, position, remember)
    first.focus_set()
    parent.wait_window(win)
    return result[0] if result else None


def _pick(var, title, types):
    path = filedialog.askopenfilename(title=title, filetypes=types)
    if path:
        var.set(path.replace("/", "\\"))
