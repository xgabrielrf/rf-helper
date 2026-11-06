"""Formulário de conta: login, senha (com olho), até 3 personagens (nome, raça, classe) e descrição."""
import tkinter as tk

from ..accounts import model
from ..accounts.model import Account, Character
from . import theme

RACE_OPTIONS = [(key, label, color) for key, (label, color) in model.RACES.items()]
CLASS_OPTIONS = [(name, name, None) for name in model.CLASSES]


class _CharacterRow:
    """Uma linha: [nome do personagem] [raça ▾] [classe ▾] [✕]. A raça vem antes da classe."""

    def __init__(self, holder, character, on_remove):
        self.name = tk.StringVar(value=character.name if character else "")
        self.race = tk.StringVar(value=character.race if character else "")
        self.cls = tk.StringVar(value=character.cls if character else "")
        self.entry = theme.entry(holder, self.name, width=20)
        self.race_box = theme.Dropdown(holder, RACE_OPTIONS, self.race, placeholder="Raça", width=8)
        self.class_box = theme.Dropdown(holder, CLASS_OPTIONS, self.cls, placeholder="Classe", width=8)
        self.remove = theme.button(holder, "✕", on_remove, bg=theme.PANEL, fg=theme.MUTED, font=theme.FONT_SMALL,
                                   padx=6, pady=0)
        self.widgets = (self.entry, self.race_box, self.class_box, self.remove)

    def grid(self, row):
        self.entry.grid(row=row, column=0, sticky="ew", padx=(0, 6), pady=3, ipady=5)
        self.race_box.grid(row=row, column=1, sticky="ew", padx=(0, 6), pady=3)
        self.class_box.grid(row=row, column=2, sticky="ew", padx=(0, 4), pady=3)
        self.remove.grid(row=row, column=3, pady=3)

    def destroy(self):
        for widget in self.widgets:
            widget.destroy()

    def is_empty(self):
        return not (self.name.get().strip() or self.race.get() or self.cls.get())

    def character(self):
        return Character(model.clean(self.name.get()), self.race.get(), self.cls.get())


def ask(parent, account=None, position=None, remember=None):
    """Abre o formulário (vazio ou com os dados de `account`). Retorna um `Account` novo com os
    dados preenchidos (mesmo id, se editando) ou None se cancelado."""
    win = theme.dialog(parent, "Editar conta" if account else "Nova conta")
    result = []
    login = tk.StringVar(value=account.login if account else "")
    password = tk.StringVar(value=account.password or "" if account else "")
    error = tk.StringVar()
    rows = []

    body = tk.Frame(win, bg=theme.PANEL)
    body.grid(row=0, column=0, padx=18, pady=(14, 4), sticky="nsew")
    body.columnconfigure(0, weight=1)
    body.columnconfigure(1, weight=1)
    theme.label(body, "Editar conta" if account else "Nova conta", font=theme.FONT_BIG).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

    theme.label(body, "Login *").grid(row=1, column=0, sticky="w")
    theme.label(body, "Senha *").grid(row=1, column=1, sticky="w", padx=(10, 0))
    first = theme.entry(body, login, width=22)
    first.grid(row=2, column=0, sticky="ew", ipady=5, pady=(3, 0))
    pw_frame = tk.Frame(body, bg=theme.PANEL)
    pw_frame.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=(3, 0))
    pw_entry = theme.entry(pw_frame, password, show="•", width=16)
    pw_entry.pack(side="left", fill="x", expand=True, ipady=5)
    eye = theme.button(pw_frame, "👁", lambda: None, bg=theme.GRAY, font=("Segoe UI Symbol", 10), padx=8, pady=3)
    eye.pack(side="left", padx=(4, 0), fill="y")

    def toggle_password():
        pw_entry.configure(show="" if pw_entry.cget("show") else "•")
    eye.configure(command=toggle_password)

    section = tk.Frame(body, bg=theme.PANEL)
    section.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 2))
    theme.label(section, "Personagens (até %d)" % model.MAX_CHARACTERS, font=theme.FONT_BOLD).pack(side="left")
    add_btn = theme.button(section, "+ Adicionar", lambda: add_row(None), font=theme.FONT_SMALL, padx=10, pady=2)
    add_btn.pack(side="right")

    holder = tk.Frame(body, bg=theme.PANEL)
    holder.grid(row=4, column=0, columnspan=2, sticky="ew")
    holder.columnconfigure(0, weight=3)
    holder.columnconfigure(1, weight=2)
    holder.columnconfigure(2, weight=2)
    for col, title in enumerate(("Nome do personagem", "Raça", "Classe")):
        theme.label(holder, title, fg=theme.MUTED, font=theme.FONT_SMALL).grid(row=0, column=col, sticky="w")

    def relayout():
        for number, row in enumerate(rows, 1):
            row.grid(number)
        if len(rows) >= model.MAX_CHARACTERS:
            add_btn.pack_forget()
        elif not add_btn.winfo_ismapped():
            add_btn.pack(side="right")

    def add_row(character):
        if len(rows) < model.MAX_CHARACTERS:
            row = _CharacterRow(holder, character, lambda: remove_row(row))
            rows.append(row)
            relayout()

    def remove_row(row):
        rows.remove(row)
        row.destroy()
        relayout()
        win.geometry("")                # encolhe de volta ao conteúdo

    for character in (account.characters if account else []):
        add_row(character)
    if not rows:
        add_row(None)

    theme.label(body, "Descrição (opcional)").grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 3))
    description = tk.Text(body, width=46, height=2, font=theme.FONT, bg=theme.INPUT, fg=theme.TEXT,
                          insertbackground=theme.TEXT, relief="flat", bd=0, highlightthickness=1,
                          highlightbackground=theme.LINE, highlightcolor=theme.BLUE, wrap="word", padx=6, pady=4)
    description.grid(row=6, column=0, columnspan=2, sticky="ew")
    if account:
        description.insert("1.0", account.description)
    theme.label(body, textvariable=error, fg="#ff7b7b", font=theme.FONT_SMALL, wraplength=440,
                justify="left").grid(row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def save():
        chars = [r.character() for r in rows if not r.is_empty()]
        candidate = Account(model.clean(login.get()), password.get(),
                            model.clean(description.get("1.0", "end"), model.MAX_DESCRIPTION), chars,
                            id=account.id if account else None)
        problem = candidate.error()
        if problem:
            error.set(problem)
            return
        result.append(candidate)
        win.destroy()

    buttons = tk.Frame(win, bg=theme.PANEL)
    buttons.grid(row=1, column=0, sticky="e", padx=18, pady=(6, 14))
    theme.button(buttons, "Cancelar", win.destroy).pack(side="left", padx=(0, 8))
    theme.button(buttons, "Salvar", save, bg=theme.GREEN).pack(side="left")
    theme.finish(win, position, remember)
    first.focus_set()
    parent.wait_window(win)
    return result[0] if result else None
