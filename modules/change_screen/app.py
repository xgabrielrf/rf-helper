"""Seletor de janelas do RF Online (multiconta). Veja o README.md."""
import ctypes
import queue
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from ..characters.watcher import CharacterWatcher
from ..clicker import icons, windowing
from ..clicker.manager import ClickerManager
from ..shared import branding
from . import config, winapi
from .hotkeys import HotkeyManager, format_binding, valid_binding

PROCESS_NAME = "RF_Online.bin"
WINDOW_POLL_MS = 1000       # procura janelas novas/fechadas
FOREGROUND_POLL_MS = 150    # acompanha qual janela da lista está em foco
EVENT_POLL_MS = 10          # consome eventos dos atalhos globais

ACTIONS = [
    ("next", "Próxima janela"),
    ("prev", "Janela anterior"),
    ("last", "Última usada (alterna)"),
]

WINDOW_SIZE = "200x300"
GREEN, RED = "#2e9e4f", "#d13b3b"


class Entry:
    def __init__(self, hwnd, fallback, title, pid):
        self.hwnd, self.title, self.pid = hwnd, title, pid
        self.fallback = fallback        # "RF 1": nome enquanto não se sabe o personagem
        self.character = None           # personagem em jogo (lido do log do RF)

    @property
    def name(self):
        return self.character or self.fallback


class App:
    def __init__(self, root, on_closed=None):
        """`root` pode ser o Tk (modo avulso) ou um Toplevel (aberto como "Modo grupo" pela tela
        inicial). `on_closed()` é chamado depois que a janela foi destruída."""
        self.root = root
        self.on_closed = on_closed
        self._closed = False           # embutido, o Tk segue vivo: os laços de after() precisam parar
        self.cfg = config.load()
        self.entries = []              # ordem da lista = ordem de próxima/anterior
        self.current = None            # hwnd da janela do RF usada por último
        self.previous = None           # hwnd da janela usada antes dela
        self.capturing = None          # ação em cadastro, ou None
        self.settings_win = None
        self.key_labels, self.key_buttons = {}, {}
        self.drag_iid = None
        self.dragged = False
        self.row_button = None         # (iid, "icon"|"gear") se o clique começou num botão da linha

        icons.init(root)
        self.clicker = ClickerManager(on_change=self._refresh_row, on_message=self._set_status,
                                      get_position=self._window_position,
                                      set_position=self._remember_window_position)
        self.clicker.auto_profile = self.cfg["auto_profile"]
        self.characters = CharacterWatcher()
        self.hotkeys = HotkeyManager()
        for action, _ in ACTIONS:
            binding = self.cfg["hotkeys"].get(action)
            if valid_binding(binding):
                self.hotkeys.set_binding(action, binding)
            else:
                self.cfg["hotkeys"][action] = None
        self.hotkeys.enabled = self.cfg["enabled"]

        self._build_ui()
        self.characters.start()
        self.hotkeys.start()
        self._poll_windows()
        self._poll_foreground()
        self._poll_events()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # --- interface ----------------------------------------------------------
    def _build_ui(self):
        root = self.root
        root.title("RF - Trocar janelas")
        root.attributes("-topmost", True)
        root.minsize(160, 200)
        saved = windowing.visible_position(self.cfg["position"])
        root.geometry(WINDOW_SIZE + (saved or ""))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        top = ttk.Frame(root)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        top.columnconfigure(0, weight=1)
        # Os dois botões têm a mesma altura (o ⚙ estica até o ATALHOS): o ON/OFF é só um
        # indicador colorido, não precisa chamar mais atenção que o resto.
        self.toggle_btn = tk.Button(top, font=("Segoe UI", 8, "bold"), fg="white",
                                    relief="flat", bd=0, pady=3, cursor="hand2",
                                    command=self._toggle_enabled)
        self.toggle_btn.grid(row=0, column=0, sticky="nsew")
        tk.Button(top, text="⚙", font=("Segoe UI Symbol", 12), relief="flat", bd=0, bg="#e1e1e1",
                  activebackground="#cfcfcf", width=3, cursor="hand2",
                  command=self._open_settings).grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        frame = ttk.Frame(root)
        frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        # Sem seleção do Treeview: o único destaque é a janela do RF em uso ("current").
        # Cada linha: [ícone do clicker] nome ... [⚙]. O ícone é a imagem do item; o ⚙ é a coluna "gear".
        self.tree = ttk.Treeview(frame, columns=("gear",), show="tree", selectmode="none", height=5)
        self.tree.column("#0", anchor="w", width=110, minwidth=60, stretch=True)
        self.tree.column("gear", anchor="center", width=30, minwidth=30, stretch=False)
        self.tree.tag_configure("current", background="#2f80ed", foreground="white")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        # 1 clique = ir para a janela; arrastar = ordenar. O nome da linha é o personagem em jogo.
        self.tree.bind("<ButtonPress-1>", self._on_press)
        self.tree.bind("<B1-Motion>", self._on_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_release)
        self.tree.bind("<Double-1>", lambda _e: "break")    # o 2º clique de um duplo não vale nada

        self.status = tk.StringVar()
        ttk.Label(root, textvariable=self.status, foreground="#555", wraplength=170).grid(
            row=2, column=0, sticky="ew", padx=10, pady=(0, 6))
        self._refresh_toggle()
        if not saved:                       # primeira vez (ou posição que não existe mais): no meio da tela
            windowing.center_on_screen(root)
        windowing.keep_on_screen(root)

    def _open_settings(self):
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.lift()
            self.settings_win.focus_force()
            return
        win = tk.Toplevel(self.root)
        self.settings_win = win
        win.title("Configurar atalhos")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self._close_settings)
        position = windowing.visible_position(self._window_position("settings"))
        if position:
            win.geometry(position)

        keys = ttk.LabelFrame(win, text="Atalhos")
        keys.grid(row=0, column=0, padx=10, pady=10)
        self.key_labels, self.key_buttons = {}, {}
        for row, (action, title) in enumerate(ACTIONS):
            ttk.Label(keys, text=title).grid(row=row, column=0, sticky="w", padx=6, pady=3)
            label = ttk.Label(keys, anchor="w", width=22)
            label.grid(row=row, column=1, sticky="ew", padx=6)
            btn = ttk.Button(keys, text="Cadastrar", width=10,
                             command=lambda a=action: self._toggle_capture(a))
            btn.grid(row=row, column=2, padx=2)
            ttk.Button(keys, text="Limpar", width=7,
                       command=lambda a=action: self._clear_binding(a)).grid(
                           row=row, column=3, padx=(0, 4))
            self.key_labels[action], self.key_buttons[action] = label, btn
        ttk.Label(win, foreground="#555",
                  text="Cadastrar: aperte a tecla, combinação ou botão do mouse.\n"
                       "Alt Gr, Ctrl e Shift sozinhos também valem. Esc cancela.").grid(
                           row=1, column=0, padx=10, pady=(0, 10))

        clicker = ttk.LabelFrame(win, text="Clicker")
        clicker.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.auto_profile_var = tk.BooleanVar(value=self.cfg["auto_profile"])
        ttk.Checkbutton(clicker, text="Carregar o perfil do personagem automaticamente",
                        variable=self.auto_profile_var, command=self._toggle_auto_profile).grid(
                            row=0, column=0, sticky="w", padx=6, pady=(4, 0))
        ttk.Label(clicker, foreground="#555", wraplength=380,
                  text="Quando um personagem entra no jogo, carrega o perfil salvo com o mesmo "
                       "nome dele (ex.: perfil \"Guerreiro\"). O clicker não liga sozinho.").grid(
                           row=1, column=0, sticky="w", padx=6, pady=(0, 6))
        ttk.Button(win, text="OK", width=10, command=self._close_settings).grid(
            row=3, column=0, sticky="e", padx=10, pady=(0, 10))
        self._refresh_key_labels()
        windowing.hide_close_button(win)        # fecha pelo OK
        windowing.keep_on_screen(win)

    def _close_settings(self):
        if self.capturing:
            self._end_capture("")
        if self.settings_win is not None:
            self._remember_window_position("settings", windowing.current_position(self.settings_win))
            self.settings_win.destroy()
        self.settings_win = None
        self.key_labels, self.key_buttons = {}, {}

    def _window_position(self, name):
        return self.cfg["windows"].get(name)

    def _remember_window_position(self, name, position):
        if self.cfg["windows"].get(name) != position:
            self.cfg["windows"][name] = position
            config.save(self.cfg)

    def _toggle_auto_profile(self):
        self.cfg["auto_profile"] = self.auto_profile_var.get()
        self.clicker.auto_profile = self.cfg["auto_profile"]
        config.save(self.cfg)

    def _refresh_toggle(self):
        on = self.hotkeys.enabled
        color = GREEN if on else RED
        self.toggle_btn.configure(
            text="ATALHOS: ON" if on else "ATALHOS: OFF",
            bg=color, activebackground=color, activeforeground="white")

    def _refresh_key_labels(self):
        for action, _ in ACTIONS:
            if action not in self.key_labels:
                return
            self.key_labels[action].configure(text=format_binding(self.cfg["hotkeys"][action]))
            self.key_buttons[action].configure(
                text="Aperte..." if self.capturing == action else "Cadastrar")

    def _set_status(self, text):
        self.status.set(text)

    # --- ON/OFF -------------------------------------------------------------
    def _toggle_enabled(self):
        self.hotkeys.enabled = not self.hotkeys.enabled
        self.cfg["enabled"] = self.hotkeys.enabled
        config.save(self.cfg)
        self._refresh_toggle()
        self._set_status("Atalhos ligados." if self.hotkeys.enabled
                         else "Atalhos desligados: as teclas voltam ao normal.")

    # --- cadastro de atalhos ------------------------------------------------
    def _toggle_capture(self, action):
        if self.capturing == action:
            self._end_capture("Cadastro cancelado.")
            return
        self.capturing = action
        self.hotkeys.start_capture()
        self._refresh_key_labels()
        self._set_status("Aperte a tecla ou botão do mouse (Esc cancela).")

    def _end_capture(self, message):
        self.capturing = None
        self.hotkeys.cancel_capture()
        self._refresh_key_labels()
        self._set_status(message)

    def _clear_binding(self, action):
        if self.capturing:
            self._end_capture("")
        self.cfg["hotkeys"][action] = None
        self.hotkeys.set_binding(action, None)
        config.save(self.cfg)
        self._refresh_key_labels()

    def _apply_capture(self, binding):
        action = self.capturing
        if binding is None:
            self._end_capture("Cadastro cancelado.")
            return
        for other, _ in ACTIONS:        # o mesmo atalho não pode servir a duas ações
            if other != action and self.cfg["hotkeys"][other] == binding:
                self.cfg["hotkeys"][other] = None
                self.hotkeys.set_binding(other, None)
        self.cfg["hotkeys"][action] = binding
        self.hotkeys.set_binding(action, binding)
        config.save(self.cfg)
        self._end_capture(f"Cadastrado: {format_binding(binding)}")

    # --- lista de janelas ---------------------------------------------------
    def _poll_windows(self):
        if self._closed:
            return
        found = {hwnd: (title, pid) for hwnd, title, pid in winapi.find_windows(PROCESS_NAME)}
        changed = False

        kept = [e for e in self.entries if e.hwnd in found]
        if len(kept) != len(self.entries):
            changed = True
            for e in self.entries:
                if e.hwnd not in found:
                    self.clicker.forget(e.hwnd)
                    if self.tree.exists(str(e.hwnd)):
                        self.tree.delete(str(e.hwnd))
            self.entries = kept
        known = {e.hwnd for e in self.entries}
        for hwnd, (title, pid) in found.items():
            if hwnd not in known:
                entry = Entry(hwnd, self._default_name(), title, pid)
                self.entries.append(entry)
                self.tree.insert("", "end", iid=str(hwnd), text=entry.name, values=("⚙",),
                                 image=self._row_icon(hwnd))
                changed = True
        for e in self.entries:
            e.title = found[e.hwnd][0]
        self._apply_characters()
        if changed:
            hwnds = {e.hwnd for e in self.entries}
            if self.current not in hwnds:
                self.current = None
            if self.previous not in hwnds:
                self.previous = None
        self.root.after(WINDOW_POLL_MS, self._poll_windows)

    def _apply_characters(self):
        """Nome da linha = personagem em jogo. PID ausente do resultado = ainda não sabemos
        (não mexe); None = o client está na seleção de personagem."""
        self.characters.set_pids(e.pid for e in self.entries)
        names = self.characters.names()
        for e in self.entries:
            if e.pid not in names or names[e.pid] == e.character:
                continue
            e.character = names[e.pid]
            if self.tree.exists(str(e.hwnd)):
                self.tree.item(str(e.hwnd), text=e.name)
            self.clicker.set_title(e.hwnd, f"{e.name} [{e.pid}]")
            self.clicker.character_changed(e.hwnd, e.character)

    def _default_name(self):
        used = {e.fallback for e in self.entries}
        n = 1
        while f"RF {n}" in used:
            n += 1
        return f"RF {n}"

    def _row_icon(self, hwnd):
        return icons.get(self.clicker.mode(hwnd), self.clicker.state(hwnd))

    def _refresh_row(self, hwnd):
        iid = str(hwnd)
        if self.tree.exists(iid):
            self.tree.item(iid, image=self._row_icon(hwnd))

    def _button_at(self, event):
        """'icon' ou 'gear' se o ponto cai num botão da linha; senão None."""
        if not self.tree.identify_row(event.y):
            return None
        if self.tree.identify_column(event.x) == "#1":
            return "gear"
        if self.tree.identify_element(event.x, event.y) in ("image", "Treeitem.indicator"):
            return "icon"
        return None

    def _open_clicker(self, hwnd):
        entry = self._entry_by_iid(str(hwnd))
        if entry:
            self._goto(hwnd)        # como se tivesse clicado na linha: o RF vem para a frente
            self.clicker.open_config(self.root, hwnd, f"{entry.name} [{entry.pid}]")

    def _on_press(self, event):
        iid = self.tree.identify_row(event.y) or None
        kind = self._button_at(event)
        self.row_button = (iid, kind) if kind else None
        self.drag_iid = None if kind else iid       # botões da linha não iniciam arraste nem "ir para"
        self.dragged = False

    def _on_motion(self, event):
        if not self.drag_iid:
            return
        target = self.tree.identify_row(event.y)
        if target and target != self.drag_iid:
            self.tree.move(self.drag_iid, "", self.tree.index(target))
            self.dragged = True

    def _on_release(self, event):
        button, self.row_button = self.row_button, None
        if button:
            iid, kind = button
            if self.tree.identify_row(event.y) == iid and self._button_at(event) == kind:
                if kind == "icon":
                    self.clicker.toggle(int(iid))
                else:
                    self._open_clicker(int(iid))
            return
        iid, dragged = self.drag_iid, self.dragged
        self.drag_iid, self.dragged = None, False
        if dragged:
            by_iid = {str(e.hwnd): e for e in self.entries}
            self.entries = [by_iid[i] for i in self.tree.get_children()]
        elif iid:
            self._goto(int(iid))

    def _entry_by_iid(self, iid):
        return next((e for e in self.entries if str(e.hwnd) == iid), None)

    # --- troca de janelas ---------------------------------------------------
    def _poll_foreground(self):
        if self._closed:
            return
        self._sync_foreground()
        current_iid = str(self.current) if self.current else None
        for e in self.entries:
            iid = str(e.hwnd)
            if self.tree.exists(iid):
                self.tree.item(iid, tags=("current",) if iid == current_iid else ())
        self.root.after(FOREGROUND_POLL_MS, self._poll_foreground)

    def _sync_foreground(self):
        """Se o usuário trocou de janela por conta própria, atualiza atual/anterior."""
        fg = winapi.foreground_window()
        if fg != self.current and any(e.hwnd == fg for e in self.entries):
            self.previous, self.current = self.current, fg

    def _goto(self, hwnd):
        if not winapi.is_window(hwnd):
            return
        self._sync_foreground()
        winapi.activate(hwnd)
        if hwnd != self.current:
            self.previous, self.current = self.current, hwnd
        entry = next((e for e in self.entries if e.hwnd == hwnd), None)
        if entry:
            self._set_status(f"Janela: {entry.name}")

    def _do_action(self, action):
        if not self.entries:
            self._set_status("Nenhuma janela do RF encontrada.")
            return
        self._sync_foreground()
        hwnds = [e.hwnd for e in self.entries]
        if action == "last":
            target = self.previous if self.previous in hwnds else None
        elif self.current in hwnds:
            step = 1 if action == "next" else -1
            target = hwnds[(hwnds.index(self.current) + step) % len(hwnds)]
        else:
            target = hwnds[0] if action == "next" else hwnds[-1]
        if target and target != winapi.foreground_window():
            self._goto(target)

    # --- eventos dos atalhos ------------------------------------------------
    def _poll_events(self):
        if self._closed:
            return
        self.clicker.poll()
        try:
            while True:
                kind, value = self.hotkeys.events.get_nowait()
                if kind == "capture" and self.capturing:
                    self._apply_capture(value)
                elif kind == "action" and self.hotkeys.enabled:
                    self._do_action(value)
        except queue.Empty:
            pass
        self.root.after(EVENT_POLL_MS, self._poll_events)

    def _on_close(self):
        self._closed = True
        self._close_settings()      # guarda a posição das janelas abertas (a do clicker é na stop_all)
        self.cfg["position"] = windowing.current_position(self.root)       # nunca fora das telas
        config.save(self.cfg)
        self.clicker.stop_all()
        self.characters.stop()
        self.hotkeys.stop()
        self.root.destroy()
        if self.on_closed:
            self.on_closed()


def relaunch_as_admin(module=None):
    """O RF roda elevado: sem privilégios iguais, o Windows (UIPI) não entrega as teclas
    ao nosso hook enquanto o jogo está em foco. Reabre o programa pedindo elevação (UAC).
    `module` é o pacote a reabrir com `-m` (padrão: este)."""
    if sys.platform != "win32" or ctypes.windll.shell32.IsUserAnAdmin():
        return False
    if getattr(sys, "frozen", False):
        exe, params, cwd = sys.executable, "", None
    else:
        # Como pacote: reabre com `-m` a partir da raiz do projeto (onde fica `modules/`).
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        params = f"-m {module or __package__}"
        cwd = str(Path(__file__).resolve().parents[2])
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, cwd, 1) > 32


def main():
    if "--no-admin" not in sys.argv and relaunch_as_admin():
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    branding.prepare()
    root = tk.Tk()
    branding.apply(root)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
