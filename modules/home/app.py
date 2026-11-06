"""Tela inicial do RF Helper: servidores à esquerda, contas no meio, Modo grupo à direita."""
import ctypes
import sys
import tkinter as tk
from tkinter import messagebox

from ..accounts import model, store
from ..accounts.model import Server
from ..accounts.running import RunningAccounts
from ..autologin import LoginError
from ..autologin.winapi import Win32Api
from ..change_screen import config
from ..change_screen.app import App as GroupApp
from ..change_screen.app import relaunch_as_admin
from ..characters.watcher import CharacterWatcher
from ..clicker import windowing
from ..shared import branding
from . import account_dialog, images, server_dialog, theme
from .placement import ClientPlacer
from .play import RUNNING, PlayController

CLIENT_IMAGE = "RF_Online.bin"
WINDOW_SIZE = "1020x640"
SIDEBAR_WIDTH = 270
RAIL_WIDTH = 68
CARD_MIN_WIDTH = 300
CHARACTER_SLOTS = 3             # o card sempre reserva as 3 linhas: ele não muda de tamanho com 1 ou 2 personagens
DESCRIPTION_CHARS = 38
DRAG_THRESHOLD = 6              # px de movimento antes de um arrasto contar como arrasto
PLAY_POLL_MS = 100
RUNNING_POLL_MS = 2000
PLACE_POLL_MS = 500             # a janela nova do RF vai para o canto logo que aparece
NOTICE_MS = 9000
MASK = "••••••••"
IN_GAME_GREEN = "#4cc27d"


def _default_login(*args):
    """Login de verdade (modules.autologin.launcher); importado só quando alguém clica em Play."""
    try:
        from ..autologin.launcher import login
    except ImportError:
        raise LoginError("O login automático ainda não está disponível nesta versão.")
    return login(*args)


def _ellipsize(text, limit):
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


class HomeApp:
    def __init__(self, root, login_fn=None, api=None, placer=None):
        self.root = root
        self.cfg = config.load()
        self.servers, self.selected_id = store.load()
        if self.selected_id is None and self.servers:
            self.selected_id = self.servers[0].id
        self.api = api or Win32Api()        # processos (listar/encerrar); os testes trocam por um falso
        self.running = RunningAccounts()    # contas com client vivo (PID do Play + SetAccountID do log)
        self.running_ids = frozenset()      # ids das contas em jogo (trocado por inteiro: a fila lê de outra thread)
        self.characters = CharacterWatcher()
        self.placer = placer or ClientPlacer.real()     # janelas novas do RF → canto superior esquerdo
        self.play =PlayController(login_fn or _default_login, should_skip=lambda account_id: account_id in self.running_ids)
        self.group = None                   # GroupApp aberto pelo Modo grupo
        self._icons = {}                    # server.id -> PhotoImage (o Tk não guarda a referência)
        self._cards = {}                    # account.id -> {"frame", "button", "status", "state"}
        self._selected = {}                 # account.id -> BooleanVar (conta marcada para iniciar em lote)
        self._shown_passwords = set()
        self._results = {}                  # account.id -> (texto, é_erro): último resultado do Play
        self._logins = {}                   # account.id -> login, para ligar o PID novo à conta
        self._drag = None
        self._columns = 0
        self._notice_job = None

        self._build_ui()
        windowing.center_on_screen(root)        # a tela inicial SEMPRE abre no meio da tela (posição não é lembrada)
        windowing.keep_on_screen(root)
        self._refresh_all()
        self.characters.start()
        self._poll_play()
        self._poll_running()
        self._poll_place()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # --- interface ----------------------------------------------------------
    def _build_ui(self):
        root = self.root
        root.title("RF Helper")
        root.configure(bg=theme.BG)
        root.minsize(860, 480)
        root.geometry(WINDOW_SIZE)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # esquerda: servidores
        side = tk.Frame(root, bg=theme.PANEL, width=SIDEBAR_WIDTH)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        side.rowconfigure(1, weight=1)
        side.columnconfigure(0, weight=1)
        head = tk.Frame(side, bg=theme.PANEL)
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(16, 10))
        theme.label(head, "Lista de servidores", font=theme.FONT_BIG).pack(side="left")
        theme.button(head, "+", self._add_server, bg=theme.BLUE, font=("Segoe UI", 13, "bold"),
                     padx=10, pady=0).pack(side="right")
        self.server_list = theme.ScrollFrame(side, theme.PANEL)
        self.server_list.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 8))
        self.server_list.inner.columnconfigure(0, weight=1)

        # centro: cabeçalho, barra de seleção, contas, avisos
        center = tk.Frame(root, bg=theme.BG)
        center.grid(row=0, column=1, sticky="nsew")
        center.columnconfigure(0, weight=1)
        center.rowconfigure(2, weight=1)
        self.header = tk.Frame(center, bg=theme.BG)
        self.header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))
        self.title = theme.label(self.header, "", font=theme.FONT_TITLE)
        self.title.pack(side="left")
        self.header_buttons = tk.Frame(self.header, bg=theme.BG)
        self.header_buttons.pack(side="left", padx=(12, 0))
        theme.button(self.header_buttons, "Editar", self._edit_server, font=theme.FONT_SMALL,
                     padx=10, pady=3).pack(side="left", padx=(0, 6))
        theme.button(self.header_buttons, "Excluir", self._delete_server, bg=theme.RED, font=theme.FONT_SMALL,
                     padx=10, pady=3).pack(side="left")
        self.add_account_btn = theme.button(self.header, "Adicionar conta  +", self._add_account, bg=theme.GREEN)
        self.add_account_btn.pack(side="right")

        self.toolbar = tk.Frame(center, bg=theme.BG)
        self.toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 4))
        self.select_all_btn = theme.button(self.toolbar, "Selecionar todas", self._toggle_select_all,
                                           font=theme.FONT_SMALL, padx=10, pady=4)
        self.select_all_btn.pack(side="left")
        self.start_btn = theme.button(self.toolbar, "", self._start_selected, bg=theme.GREEN, font=theme.FONT_SMALL,
                                      padx=12, pady=4)
        self.start_btn.pack(side="left", padx=(8, 0))
        self.cancel_queue_btn = theme.button(self.toolbar, "Cancelar fila", self._cancel_queue, bg=theme.RED,
                                             font=theme.FONT_SMALL, padx=10, pady=4)

        self.accounts = theme.ScrollFrame(center, theme.BG)
        self.accounts.grid(row=2, column=0, sticky="nsew", padx=(20, 12), pady=(2, 0))
        self.accounts.on_width = self._on_accounts_width
        self.notice = tk.StringVar()
        self.notice_label = theme.label(center, textvariable=self.notice, font=theme.FONT_SMALL, anchor="w",
                                        justify="left", wraplength=640)
        self.notice_label.grid(row=3, column=0, sticky="ew", padx=20, pady=(4, 10))

        # direita: faixa com o Modo grupo
        rail = tk.Frame(root, bg=theme.PANEL, width=RAIL_WIDTH)
        rail.grid(row=0, column=2, sticky="ns")
        rail.grid_propagate(False)
        group = tk.Frame(rail, bg=theme.PANEL, cursor="hand2")
        group.pack(pady=(14, 0), padx=8, fill="x")
        icon = theme.group_icon(group, bg=theme.PANEL)
        icon.pack(pady=(6, 0))
        caption = theme.label(group, "Modo grupo", fg=theme.MUTED, font=("Segoe UI", 8), bg=theme.PANEL)
        caption.pack(pady=(0, 6))
        for widget in (group, icon, caption):
            widget.bind("<Button-1>", lambda _e: self._open_group())
            widget.bind("<Enter>", lambda _e: self._rail_hover(group, icon, caption, True))
            widget.bind("<Leave>", lambda _e: self._rail_hover(group, icon, caption, False))

    @staticmethod
    def _rail_hover(group, icon, caption, on):
        bg = theme.GRAY if on else theme.PANEL
        for widget in (group, icon, caption):
            widget.configure(bg=bg)

    # --- dados ---------------------------------------------------------------
    @property
    def server(self):
        return next((s for s in self.servers if s.id == self.selected_id), None)

    def _save(self):
        if not store.save(self.servers, self.selected_id):
            self._notify("Não foi possível salvar os servidores e contas.", error=True)
            return False
        return True

    def _window_position(self, name):
        return config.load()["windows"].get(name)

    def _remember_window(self, name, position):
        """Relê o config.json antes de gravar: o Modo grupo guarda as posições dele no mesmo arquivo."""
        cfg = config.load()
        if cfg["windows"].get(name) != position:
            cfg["windows"][name] = position
            config.save(cfg)

    def _notify(self, text, error=False):
        if self._notice_job is not None:
            self.root.after_cancel(self._notice_job)
        self.notice.set(text)
        self.notice_label.configure(fg="#ff7b7b" if error else theme.MUTED)
        self._notice_job = self.root.after(NOTICE_MS, lambda: self.notice.set(""))

    # --- servidores ------------------------------------------------------------
    def _refresh_all(self):
        self._refresh_servers()
        self._refresh_accounts()

    def _refresh_servers(self):
        inner = self.server_list.inner
        for child in inner.winfo_children():
            child.destroy()
        self._icons = {}
        for row, server in enumerate(self.servers):
            selected = server.id == self.selected_id
            bg = "#333a43" if selected else theme.PANEL
            frame = tk.Frame(inner, bg=bg, cursor="hand2")
            frame.grid(row=row, column=0, sticky="ew", pady=1)
            frame.columnconfigure(1, weight=1)
            self._icons[server.id] = images.load(self.root, server.id)
            icon = theme.initial_icon(frame, server.name, 40, image=self._icons[server.id])
            icon.configure(bg=bg)
            icon.grid(row=0, column=0, rowspan=2, padx=(10, 10), pady=8)
            name = theme.label(frame, server.name, font=theme.FONT_BOLD, bg=bg, anchor="w")
            name.grid(row=0, column=1, sticky="ew", pady=(10, 0))
            count = len(server.accounts)
            info = theme.label(frame, f"{count} conta" + ("" if count == 1 else "s"), fg=theme.MUTED,
                               font=theme.FONT_SMALL, bg=bg, anchor="w")
            info.grid(row=1, column=1, sticky="ew", pady=(0, 10))
            for widget in (frame, icon, name, info):
                widget.bind("<Button-1>", lambda _e, sid=server.id: self._select_server(sid))
                if not selected:
                    widget.bind("<Enter>", lambda _e, f=frame, w=(icon, name, info): self._row_hover(f, w, True))
                    widget.bind("<Leave>", lambda _e, f=frame, w=(icon, name, info): self._row_hover(f, w, False))
        if not self.servers:
            theme.label(inner, "Nenhum servidor ainda.\nClique em + para adicionar.", fg=theme.MUTED,
                        font=theme.FONT_SMALL, justify="left").grid(row=0, column=0, padx=14, pady=10, sticky="w")

    @staticmethod
    def _row_hover(frame, widgets, on):
        bg = "#2d333a" if on else theme.PANEL
        frame.configure(bg=bg)
        for widget in widgets:
            widget.configure(bg=bg)

    def _select_server(self, server_id):
        if server_id == self.selected_id:
            return
        self.selected_id = server_id
        self._save()
        self._refresh_all()
        self.accounts.scroll_top()

    def _add_server(self):
        data = server_dialog.ask(self.root, position=self._window_position("server_dialog"),
                                 remember=lambda p: self._remember_window("server_dialog", p))
        if not data:
            return
        server = Server(*data)
        images.prepare(server.id, server.icon_path)
        self.servers.append(server)
        self.selected_id = server.id
        self._save()
        self._refresh_all()

    def _edit_server(self):
        server = self.server
        if server is None:
            return
        data = server_dialog.ask(self.root, server, position=self._window_position("server_dialog"),
                                 remember=lambda p: self._remember_window("server_dialog", p))
        if not data:
            return
        icon_changed = data[2] != server.icon_path
        server.name, server.launcher_path, server.icon_path = data
        if icon_changed:
            images.prepare(server.id, server.icon_path)
        self._save()
        self._refresh_all()

    def _delete_server(self):
        server = self.server
        if server is None:
            return
        count = len(server.accounts)
        extra = f" e suas {count} conta{'s' if count != 1 else ''}" if count else ""
        if not messagebox.askyesno("Excluir servidor", f"Excluir o servidor '{server.name}'{extra}?\n\n"
                                   "Isso só apaga os dados do RF Helper, não o jogo.", parent=self.root):
            return
        for account in server.accounts:
            self.play.cancel(account.id)
            self._selected.pop(account.id, None)
        index = self.servers.index(server)
        self.servers.remove(server)
        images.forget(server.id)
        neighbor = self.servers[min(index, len(self.servers) - 1)] if self.servers else None
        self.selected_id = neighbor.id if neighbor else None
        self._save()
        self._refresh_all()

    # --- contas ----------------------------------------------------------------
    def _on_accounts_width(self, width):
        columns = max(1, min(3, width // CARD_MIN_WIDTH))
        if columns != self._columns:
            self._columns = columns
            self._layout_cards()

    def _layout_cards(self):
        server = self.server
        if server is None:
            return
        inner = self.accounts.inner
        for col in range(3):
            inner.columnconfigure(col, weight=1 if col < self._columns else 0, uniform="cards" if col < self._columns else "")
        for index, account in enumerate(server.accounts):
            refs = self._cards.get(account.id)
            if refs:
                refs["frame"].grid(row=index // self._columns, column=index % self._columns,
                                   sticky="nsew", padx=6, pady=6)

    def _refresh_accounts(self):
        server = self.server
        inner = self.accounts.inner
        for child in inner.winfo_children():
            child.destroy()
        self._cards = {}
        for col in range(3):
            inner.columnconfigure(col, weight=0, uniform="")
        has_server = server is not None
        self.title.configure(text=server.name if has_server else "RF Helper")
        if has_server:
            self.header_buttons.pack(side="left", padx=(12, 0))
            self.add_account_btn.pack(side="right")
        else:
            self.header_buttons.pack_forget()
            self.add_account_btn.pack_forget()
        has_accounts = has_server and bool(server.accounts)
        if has_accounts:
            self.toolbar.grid()
        else:
            self.toolbar.grid_remove()
        if not has_server:
            self._empty_state("Adicione um servidor para começar", "Adicionar servidor", self._add_server)
            return
        if not server.accounts:
            self._empty_state("Nenhuma conta neste servidor ainda", "Adicionar conta", self._add_account)
            return
        self._columns = max(1, min(3, self.accounts.canvas.winfo_width() // CARD_MIN_WIDTH))
        for account in server.accounts:
            self._logins[account.id] = account.login
            self._cards[account.id] = self._build_card(inner, server, account)
        self._layout_cards()
        self._refresh_buttons()

    def _empty_state(self, text, button_text, command):
        box = tk.Frame(self.accounts.inner, bg=theme.BG)
        box.grid(row=0, column=0, columnspan=3, pady=120)
        self.accounts.inner.columnconfigure(0, weight=1)
        theme.label(box, text, fg=theme.MUTED, font=theme.FONT_BIG).pack(pady=(0, 14))
        theme.button(box, button_text + "  +", command, bg=theme.GREEN).pack()

    def _selection_var(self, account):
        if account.id not in self._selected:
            self._selected[account.id] = tk.BooleanVar(master=self.root, value=False)
        return self._selected[account.id]

    def _build_card(self, parent, server, account):
        """Card de altura fixa: cabeçalho, descrição (1 linha), 3 vagas de personagem, senha, botão, status."""
        card = tk.Frame(parent, bg=theme.CARD, highlightthickness=1, highlightbackground=theme.LINE)
        card.columnconfigure(0, weight=1)

        head = tk.Frame(card, bg=theme.CARD)
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 2))
        theme.Checkbox(head, self._selection_var(account), command=self._update_toolbar).pack(side="left", padx=(0, 8))
        theme.label(head, account.login, font=theme.FONT_BIG, bg=theme.CARD).pack(side="left")
        menu = tk.Menu(card, tearoff=0)
        menu.add_command(label="Editar", command=lambda: self._edit_account(account))
        menu.add_command(label="Excluir", command=lambda: self._delete_account(account))
        more = theme.button(head, "⋮", None, bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 12, "bold"),
                            padx=8, pady=0)
        more.configure(command=lambda: menu.tk_popup(more.winfo_rootx(), more.winfo_rooty() + more.winfo_height()))
        more.pack(side="right")

        theme.label(card, _ellipsize(account.description, DESCRIPTION_CHARS) or " ", fg=theme.MUTED,
                    font=theme.FONT_SMALL, bg=theme.CARD, anchor="w").grid(row=1, column=0, sticky="ew", padx=14)

        chars = tk.Frame(card, bg=theme.CARD)
        chars.grid(row=2, column=0, sticky="ew", padx=14, pady=(6, 4))
        for slot in range(CHARACTER_SLOTS):
            char = account.characters[slot] if slot < len(account.characters) else None
            if char:
                theme.dot(chars, model.race_color(char.race)).grid(row=slot, column=0, padx=(0, 8), pady=2)
                theme.label(chars, char.name, font=theme.FONT_BOLD, bg=theme.CARD, anchor="w").grid(
                    row=slot, column=1, sticky="w")
                theme.label(chars, f"{model.race_label(char.race)} · {char.cls}", fg=theme.MUTED,
                            font=theme.FONT_SMALL, bg=theme.CARD).grid(row=slot, column=2, sticky="w", padx=(10, 0))
            else:       # vaga livre: mesma estrutura de uma linha preenchida, só para reservar a altura
                tk.Frame(chars, width=12, height=12, bg=theme.CARD).grid(row=slot, column=0, padx=(0, 8), pady=2)
                theme.label(chars, " ", font=theme.FONT_BOLD, bg=theme.CARD).grid(row=slot, column=1, sticky="w")

        pw_row = tk.Frame(card, bg=theme.INPUT)
        pw_row.grid(row=3, column=0, sticky="ew", padx=14, pady=(4, 8))
        theme.label(pw_row, "Senha", fg=theme.MUTED, font=theme.FONT_SMALL, bg=theme.INPUT).pack(side="left", padx=(8, 8), pady=5)
        pw_text = theme.label(pw_row, "", font=theme.FONT_MONO, bg=theme.INPUT)
        pw_text.pack(side="left")
        eye = theme.button(pw_row, "👁", None, bg=theme.INPUT, hover=theme.GRAY, fg=theme.MUTED,
                           font=("Segoe UI Symbol", 10), padx=8, pady=0)
        eye.pack(side="right")
        eye.configure(command=lambda: self._toggle_password(account, pw_text))
        self._paint_password(account, pw_text)

        action = theme.button(card, "", lambda: self._card_action(server, account), bg=theme.GREEN, pady=7)
        action.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 4))
        status = theme.label(card, " ", fg=theme.MUTED, font=theme.FONT_SMALL, bg=theme.CARD, anchor="w",
                             justify="left", wraplength=280)
        status.grid(row=5, column=0, sticky="ew", padx=14, pady=(0, 6))
        self._bind_drag_tree(card, account)
        return {"frame": card, "button": action, "status": status}

    # --- reordenar por arrasto ---------------------------------------------------
    def _bind_drag_tree(self, widget, account):
        """O arrasto vale em qualquer parte do card, menos nos botões e na caixa de seleção."""
        if not isinstance(widget, (tk.Button, theme.Checkbox, tk.Menu)):
            widget.bind("<ButtonPress-1>", lambda e: self._drag_press(e, account), add="+")
            widget.bind("<B1-Motion>", self._drag_motion, add="+")
            widget.bind("<ButtonRelease-1>", self._drag_release, add="+")
        for child in widget.winfo_children():
            self._bind_drag_tree(child, account)

    def _card_at(self, x_root, y_root):
        server = self.server
        for account in (server.accounts if server else []):
            refs = self._cards.get(account.id)
            if not refs:
                continue
            frame = refs["frame"]
            left, top = frame.winfo_rootx(), frame.winfo_rooty()
            if left <= x_root < left + frame.winfo_width() and top <= y_root < top + frame.winfo_height():
                return account
        return None

    def _drag_press(self, event, account):
        self._drag = {"account": account, "x": event.x_root, "y": event.y_root, "active": False, "target": None}

    def _set_card_border(self, account, color):
        refs = self._cards.get(account.id) if account else None
        if refs:
            refs["frame"].configure(highlightbackground=color)

    def _drag_motion(self, event):
        drag = self._drag
        if not drag:
            return
        if not drag["active"]:
            if abs(event.x_root - drag["x"]) + abs(event.y_root - drag["y"]) < DRAG_THRESHOLD:
                return
            drag["active"] = True
            self.root.configure(cursor="fleur")
            self._set_card_border(drag["account"], theme.BLUE)
        target = self._card_at(event.x_root, event.y_root)
        if target is drag["account"]:
            target = None
        if target is not drag["target"]:
            self._set_card_border(drag["target"], theme.LINE)
            self._set_card_border(target, theme.GREEN)
            drag["target"] = target

    def _drag_release(self, _event):
        drag, self._drag = self._drag, None
        if not drag or not drag["active"]:
            return
        self.root.configure(cursor="")
        self._set_card_border(drag["account"], theme.LINE)
        self._set_card_border(drag["target"], theme.LINE)
        if drag["target"] is not None:
            self._move_account(drag["account"], drag["target"])

    def _move_account(self, account, target):
        """`account` ocupa o lugar de `target`; os demais se ajeitam."""
        server = self.server
        if server is None or account not in server.accounts or target not in server.accounts:
            return
        index = server.accounts.index(target)
        server.accounts.remove(account)
        server.accounts.insert(index, account)
        self._save()
        self._refresh_accounts()

    # --- senha ----------------------------------------------------------------------
    def _paint_password(self, account, label):
        if account.password is None:
            label.configure(text="ilegível: edite a conta", fg="#ff7b7b", font=theme.FONT_SMALL)
        elif account.id in self._shown_passwords:
            label.configure(text=account.password, fg=theme.TEXT)
        else:
            label.configure(text=MASK if account.password else "", fg=theme.TEXT)

    def _toggle_password(self, account, label):
        if account.id in self._shown_passwords:
            self._shown_passwords.discard(account.id)
        else:
            self._shown_passwords.add(account.id)
        self._paint_password(account, label)

    def _add_account(self):
        server = self.server
        if server is None:
            return
        account = account_dialog.ask(self.root, position=self._window_position("account_dialog"),
                                     remember=lambda p: self._remember_window("account_dialog", p))
        if account:
            server.accounts.append(account)
            self._save()
            self._refresh_all()

    def _edit_account(self, account):
        server = self.server
        edited = account_dialog.ask(self.root, account, position=self._window_position("account_dialog"),
                                    remember=lambda p: self._remember_window("account_dialog", p))
        if not edited or server is None:
            return
        edited.unreadable_token = "" if edited.password else account.unreadable_token
        server.accounts[server.accounts.index(account)] = edited
        self._save()
        self._refresh_all()

    def _delete_account(self, account):
        server = self.server
        if server is None or not messagebox.askyesno(
                "Excluir conta", f"Excluir a conta '{account.login}'?\n\nIsso só apaga os dados do RF Helper.",
                parent=self.root):
            return
        self.play.cancel(account.id)
        server.accounts.remove(account)
        self._shown_passwords.discard(account.id)
        self._selected.pop(account.id, None)
        self._results.pop(account.id, None)
        self._save()
        self._refresh_all()

    # --- seleção e início em lote ---------------------------------------------------------
    def _selected_accounts(self):
        """Contas marcadas, na ordem em que aparecem na tela."""
        server = self.server
        return [a for a in (server.accounts if server else []) if self._selected.get(a.id) and self._selected[a.id].get()]

    def _toggle_select_all(self):
        server = self.server
        if server is None or not server.accounts:
            return
        everything = len(self._selected_accounts()) == len(server.accounts)
        for account in server.accounts:
            self._selection_var(account).set(not everything)
        self._update_toolbar()

    def _update_toolbar(self):
        server = self.server
        total = len(server.accounts) if server else 0
        picked = len(self._selected_accounts())
        self.select_all_btn.configure(text="Desmarcar todas" if total and picked == total else "Selecionar todas")
        self.start_btn.configure(text=f"▶  Iniciar selecionadas ({picked})" if picked else "▶  Iniciar selecionadas",
                                 state="normal" if picked else "disabled")
        theme.set_button_colors(self.start_btn, theme.GREEN if picked else theme.GRAY)
        if self.play.busy():
            self.cancel_queue_btn.pack(side="left", padx=(8, 0))
        else:
            self.cancel_queue_btn.pack_forget()

    def _start_selected(self):
        server = self.server
        accounts = self._selected_accounts()
        if server is None or not accounts:
            return
        ready = [a for a in accounts if a.id not in self.running_ids and a.password]
        in_game = [a for a in accounts if a.id in self.running_ids]
        unreadable = [a for a in accounts if not a.password]
        for account in ready:
            self._results.pop(account.id, None)
        queued = self.play.start_many(server, ready)
        for account in accounts:
            self._selection_var(account).set(False)
        notes = []
        if in_game:
            notes.append(f"já em jogo, puladas: {', '.join(a.login for a in in_game)}")
        if unreadable:
            notes.append(f"sem senha legível: {', '.join(a.login for a in unreadable)}")
        if notes:
            self._notify("Início em lote: " + "; ".join(notes) + ".", error=bool(unreadable))
        elif queued:
            self._notify(f"{len(queued)} conta{'s' if len(queued) != 1 else ''} na fila, na ordem da tela.")
        self._refresh_buttons()

    def _cancel_queue(self):
        self.play.cancel_all()
        self._refresh_buttons()

    # --- botão do card: Play / Pause / Cancelar --------------------------------------------
    def _card_action(self, server, account):
        if self.play.state(account.id):
            self.play.cancel(account.id)
        elif account.id in self.running_ids:
            self._pause(account)
        elif not account.password:
            self._notify(f"A senha de '{account.login}' não pôde ser lida: edite a conta e digite de novo.", error=True)
        else:
            self._results.pop(account.id, None)
            self.play.start(server, account)
        self._refresh_buttons()

    def _pause(self, account):
        pids = self.running.pids_for(account.login)
        if not pids:
            return
        if not messagebox.askyesno("Encerrar o RF", f"Encerrar o RF da conta '{account.login}'?\n\n"
                                   "O personagem será desconectado.", parent=self.root):
            return
        for pid in pids:
            self.api.kill(pid)
        self._results.pop(account.id, None)
        self._notify(f"RF da conta '{account.login}' encerrado.")
        self.root.after(600, self._poll_running_once)

    def _refresh_buttons(self):
        for account_id in list(self._cards):
            self._update_card(account_id)
        self._update_toolbar()

    def _update_card(self, account_id):
        refs = self._cards.get(account_id)
        if not refs:
            return
        state = self.play.state(account_id)
        result = self._results.get(account_id)
        in_game = account_id in self.running_ids
        button, status = refs["button"], refs["status"]
        if state is not None:
            kind, text = state
            button.configure(text="Cancelar" if kind == RUNNING else "Sair da fila")
            theme.set_button_colors(button, theme.RED if kind == RUNNING else theme.GRAY)
            status.configure(text=text, fg=theme.MUTED)
        elif in_game:
            button.configure(text="❚❚  Pause")
            theme.set_button_colors(button, theme.RED)
            if result and result[1]:
                status.configure(text=result[0], fg="#ff7b7b")
            else:
                status.configure(text="Em jogo", fg=IN_GAME_GREEN)
        else:
            button.configure(text="▶  Play")
            theme.set_button_colors(button, theme.GREEN)
            text, is_error = result or (" ", False)
            status.configure(text=text, fg="#ff7b7b" if is_error else theme.MUTED)

    # --- eventos da fila --------------------------------------------------------------
    def _poll_play(self):
        accounts = {a.id: a for s in self.servers for a in s.accounts}
        events = self.play.drain()
        for event in events:
            account = accounts.get(event.account_id)
            if event.kind == "error":
                self._results[event.account_id] = (event.text, True)
                self._notify(f"{account.login if account else 'Conta'}: {event.text}", error=True)
            elif event.kind == "done":
                self._results[event.account_id] = ("Client aberto.", False)
                if account is not None and event.value:
                    self.running.bind(account.login, event.value)
                    self._poll_running_once()
            elif event.kind == "cancelled":
                self._results[event.account_id] = ("Cancelado.", False)
            elif event.kind == "skipped":
                self._results[event.account_id] = (event.text, False)
        if events:
            self._refresh_buttons()
        else:
            for account_id in list(self._cards):
                if self.play.state(account_id):
                    self._update_card(account_id)       # o texto da etapa muda sem evento de fim
        self.root.after(PLAY_POLL_MS, self._poll_play)

    # --- contas em jogo ---------------------------------------------------------------
    def _poll_running(self):
        self._poll_running_once()
        self.root.after(RUNNING_POLL_MS, self._poll_running)

    def _poll_running_once(self):
        try:
            pids = self.api.pids_named(CLIENT_IMAGE)
        except OSError:
            return
        self.characters.set_pids(pids)
        mismatches = self.running.update(pids, self.characters.accounts())
        for _pid, wanted, got in mismatches:
            self._notify(f"Atenção: o Play de '{wanted}' abriu a conta '{got}'. O launcher entrou com outro ID.",
                         error=True)
            for server in self.servers:
                for account in server.accounts:
                    if account.login.lower() == wanted:
                        self._results[account.id] = (f"Abriu a conta '{got}', não esta.", True)
        now = frozenset(a.id for s in self.servers for a in s.accounts if self.running.is_running(a.login))
        if now != self.running_ids:
            self.running_ids = now
            self._refresh_buttons()

    def _poll_place(self):
        try:
            self.placer.update()
        except Exception:               # arrumar a janela é um favor: nunca pode derrubar a tela inicial
            pass
        self.root.after(PLACE_POLL_MS, self._poll_place)

    # --- Modo grupo ----------------------------------------------------------------
    def _open_group(self):
        if self.group is not None and self.group.root.winfo_exists():
            self.group.root.deiconify()
            self.group.root.lift()
            return
        top = tk.Toplevel(self.root)
        try:
            self.group = GroupApp(top, on_closed=self._group_closed)
        except Exception:
            top.destroy()
            raise

    def _group_closed(self):
        self.group = None

    # --- fechar --------------------------------------------------------------------
    def _on_close(self):
        if self.play.busy() and not messagebox.askyesno(
                "Sair", "Há um login em andamento. Sair mesmo assim?", parent=self.root):
            return
        self.play.shutdown()
        self.characters.stop()
        if self.group is not None:
            self.group._on_close()
        self.root.destroy()


def main():
    if "--no-admin" not in sys.argv and relaunch_as_admin("modules.home"):
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    branding.prepare()
    root = tk.Tk()
    branding.apply(root)
    HomeApp(root)
    root.mainloop()
