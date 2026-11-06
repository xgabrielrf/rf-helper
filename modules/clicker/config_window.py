"""Janela "RF Clicker" de uma janela do RF: perfil, modo (Click | Macro) e teclas."""
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from . import keys, profiles, windowing
from .macro_window import MacroWindow
from .model import MAX_MS, MIN_CLICK_MS, MODE_CLICK, MODE_MACRO, KeyRow

DEBOUNCE_MS = 300           # editar teclas/ms em sequência reinicia o runner uma vez só
MAX_LIST_HEIGHT = 220       # acima disso a lista de teclas ganha barra de rolagem
ESCAPE_VK = 0x1B
POSITION_KEY = "clicker"


class ConfigWindow:
    def __init__(self, parent, manager, session):
        self.manager, self.session = manager, session
        self.macro_win = None
        self.capturing = None           # índice da linha cuja tecla está sendo cadastrada
        self.key_buttons = []
        self.change_job = None

        self.win = win = tk.Toplevel(parent)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self.close)
        position = windowing.visible_position(manager.get_position(POSITION_KEY))
        if position:
            win.geometry(position)
        self.retitle()

        # O perfil carregado/salvo da última vez continua selecionado ao reabrir (se ainda existir).
        self.profile_var = tk.StringVar(value=profiles.find(session.profile) or "")
        self.mode_var = tk.StringVar(value=self.cfg.mode)
        self.status_var = tk.StringVar()
        self.summary_var = tk.StringVar()
        self._build()
        self._render_rows()
        self._show_mode()
        self._refresh_summary()
        windowing.hide_close_button(win)        # fecha pelo OK
        windowing.keep_on_screen(win)           # nunca fica escondida fora das telas

    @property
    def cfg(self):
        return self.session.cfg

    # --- ciclo de vida ------------------------------------------------------
    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def focus(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def retitle(self):
        """O nome da linha pode mudar (o personagem entrou/saiu): acompanha nas janelas."""
        self.win.title(f"RF Clicker — {self.session.title}")
        if self.macro_win is not None and self.macro_win.alive():
            self.macro_win.retitle()

    def close(self):
        if not self.alive():
            return
        if self.change_job is not None:
            self.win.after_cancel(self.change_job)
            self.change_job = None
            self.manager.config_changed(self.session.hwnd)
        if self.macro_win is not None:
            self.macro_win.close()
        self.session.config_win = None
        self.manager.set_position(POSITION_KEY, windowing.current_position(self.win))
        self.win.destroy()

    # --- construção ---------------------------------------------------------
    def _build(self):
        win = self.win
        pad = {"padx": 10}

        prof = ttk.LabelFrame(win, text="Perfil")
        prof.grid(row=0, column=0, sticky="ew", pady=(10, 4), **pad)
        self.profile_box = ttk.Combobox(prof, textvariable=self.profile_var, state="readonly",
                                        width=18, values=profiles.names())
        self.profile_box.grid(row=0, column=0, padx=6, pady=6)
        self.profile_box.bind("<<ComboboxSelected>>", lambda _e: self._load_profile())
        ttk.Button(prof, text="Salvar", width=7, command=self._save_profile).grid(row=0, column=1)
        ttk.Button(prof, text="Salvar como…", width=14, command=self._save_profile_as).grid(
            row=0, column=2, padx=2)
        ttk.Button(prof, text="Excluir", width=7, command=self._delete_profile).grid(
            row=0, column=3, padx=(0, 6))

        mode = ttk.Frame(win)
        mode.grid(row=1, column=0, sticky="w", pady=4, **pad)
        ttk.Radiobutton(mode, text="Click (teclas com intervalo)", value=MODE_CLICK,
                        variable=self.mode_var, command=self._on_mode).grid(row=0, column=0)
        ttk.Radiobutton(mode, text="Macro (gravada)", value=MODE_MACRO,
                        variable=self.mode_var, command=self._on_mode).grid(
                            row=0, column=1, padx=(12, 0))

        self.click_panel = ttk.Frame(win)
        self.click_panel.grid(row=2, column=0, sticky="ew", **pad)
        ttk.Label(self.click_panel, text="Tecla", foreground="#555").grid(
            row=0, column=0, sticky="w")
        ttk.Label(self.click_panel, text="Delay (ms)", foreground="#555").grid(
            row=0, column=1, sticky="w")
        holder = ttk.Frame(self.click_panel)
        holder.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.canvas = tk.Canvas(holder, highlightthickness=0, borderwidth=0)
        self.scroll = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.rows_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.rows_frame.bind("<Configure>", self._fit_rows)
        ttk.Button(self.click_panel, text="+", width=4, command=self._add_row).grid(
            row=2, column=0, sticky="w", pady=(4, 0))

        self.macro_panel = ttk.Frame(win)
        self.macro_panel.grid(row=2, column=0, sticky="ew", **pad)
        ttk.Button(self.macro_panel, text="Macro…", width=12, command=self._open_macro).grid(
            row=0, column=0, sticky="w")
        ttk.Label(self.macro_panel, textvariable=self.summary_var, foreground="#555").grid(
            row=0, column=1, padx=8)

        ttk.Label(win, textvariable=self.status_var, foreground="#555", wraplength=330).grid(
            row=3, column=0, sticky="w", padx=10, pady=(6, 4))
        ttk.Button(win, text="OK", width=10, command=self.close).grid(
            row=4, column=0, sticky="e", padx=10, pady=(0, 10))

    def _fit_rows(self, _event=None):
        self.canvas.update_idletasks()
        height = self.rows_frame.winfo_reqheight()
        self.canvas.configure(scrollregion=(0, 0, self.rows_frame.winfo_reqwidth(), height),
                              width=self.rows_frame.winfo_reqwidth(),
                              height=min(height, MAX_LIST_HEIGHT))
        if height > MAX_LIST_HEIGHT:
            self.scroll.grid(row=0, column=1, sticky="ns")
        else:
            self.scroll.grid_remove()

    def _show_mode(self):
        if self.cfg.mode == MODE_MACRO:
            self.click_panel.grid_remove()
            self.macro_panel.grid()
        else:
            self.macro_panel.grid_remove()
            self.click_panel.grid()

    # --- modo ---------------------------------------------------------------
    def _on_mode(self):
        self._cancel_capture()
        self.cfg.mode = self.mode_var.get()
        self._show_mode()
        self._changed()

    def _changed(self):
        """Agrupa edições seguidas: o runner é reiniciado uma vez, ao parar de editar."""
        if self.change_job is not None:
            self.win.after_cancel(self.change_job)
        self.change_job = self.win.after(DEBOUNCE_MS, self._flush)

    def _flush(self):
        self.change_job = None
        self.manager.config_changed(self.session.hwnd)

    # --- linhas de teclas (modo click) ---------------------------------------
    def _key_text(self, row):
        return row.label if row.vk else "—"

    def _render_rows(self):
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self.key_buttons = []
        self.capturing = None
        for i, row in enumerate(self.cfg.keys):
            btn = ttk.Button(self.rows_frame, text=self._key_text(row), width=11,
                             command=lambda i=i: self._toggle_capture(i))
            btn.grid(row=i, column=0, padx=(0, 6), pady=2)
            btn.bind("<KeyPress>", lambda e, i=i: self._on_key(e, i))
            btn.bind("<FocusOut>", lambda _e, i=i: self._cancel_capture(i))
            self.key_buttons.append(btn)

            var = tk.StringVar(value=str(row.ms))
            var.trace_add("write", lambda *_a, i=i, v=var: self._set_ms(i, v))
            spin = ttk.Spinbox(self.rows_frame, from_=MIN_CLICK_MS, to=MAX_MS, width=9,
                               textvariable=var)
            spin.grid(row=i, column=1, pady=2)
            spin.bind("<FocusOut>", lambda _e, i=i, v=var: self._normalize_ms(i, v))
            ttk.Button(self.rows_frame, text="Clear", width=6,
                       command=lambda i=i: self._clear_row(i)).grid(row=i, column=2, padx=(6, 0))
        self._fit_rows()

    def _set_ms(self, index, var):
        text = var.get().strip()
        if not text.isdigit() or index >= len(self.cfg.keys):
            return
        ms = max(MIN_CLICK_MS, min(MAX_MS, int(text)))
        if self.cfg.keys[index].ms != ms:
            self.cfg.keys[index].ms = ms
            self._changed()

    def _normalize_ms(self, index, var):
        if index < len(self.cfg.keys):
            var.set(str(self.cfg.keys[index].ms))

    def _add_row(self):
        self._cancel_capture()
        self.cfg.keys.append(KeyRow())
        self._render_rows()

    def _clear_row(self, index):
        """Limpa a tecla; em linhas além da primeira, remove a linha."""
        self._cancel_capture()
        if index == 0:
            self.cfg.keys[0] = KeyRow()
        else:
            del self.cfg.keys[index]
        self._render_rows()
        self._changed()

    # --- cadastro de tecla ---------------------------------------------------
    def _toggle_capture(self, index):
        if self.capturing == index:
            self._cancel_capture()
            return
        self._cancel_capture()
        self.capturing = index
        self.key_buttons[index].configure(text="Aperte…")
        self.key_buttons[index].focus_set()
        self.status_var.set("Aperte a tecla (Esc cancela). Só tecla única, sem Ctrl/Alt/Shift.")

    def _cancel_capture(self, index=None):
        if self.capturing is None or (index is not None and index != self.capturing):
            return
        i, self.capturing = self.capturing, None
        if i < len(self.key_buttons):
            self.key_buttons[i].configure(text=self._key_text(self.cfg.keys[i]))
        self.status_var.set("")

    def _on_key(self, event, index):
        if self.capturing != index:
            return None
        vk = event.keycode
        if vk == ESCAPE_VK:
            self._cancel_capture()
        elif keys.is_sendable(vk):
            row = self.cfg.keys[index]
            row.vk, row.label = vk, keys.key_label(vk)
            self._cancel_capture()
            self._changed()
        return "break"      # modificadores são ignorados; nada vaza para o botão

    # --- macro --------------------------------------------------------------
    def _open_macro(self):
        if self.macro_win is not None and self.macro_win.alive():
            self.macro_win.focus()
            return
        self.macro_win = MacroWindow(self.win, self.session, on_change=self._macro_changed,
                                     manager=self.manager)

    def _macro_changed(self):
        self._refresh_summary()
        self._changed()

    def _refresh_summary(self):
        macro = self.cfg.macro
        if macro.is_empty():
            self.summary_var.set("Macro vazia")
        else:
            self.summary_var.set(f"{macro.key_count()} tecla(s) · {macro.duration_ms() / 1000:.1f} s"
                                 f" · loop {'sim' if macro.loop else 'não'}")

    # --- perfis -------------------------------------------------------------
    def _refresh_profiles(self):
        self.profile_box.configure(values=profiles.names())

    def _load_profile(self):
        name = self.profile_var.get()
        cfg = profiles.load(name)
        if cfg is None:
            self.status_var.set(f"Perfil '{name}' não encontrado.")
            self._refresh_profiles()
            return
        self.manager.replace_config(self.session.hwnd, cfg)
        self.reload(name)

    def reload(self, profile_name=None):
        """Redesenha tudo a partir da config atual da sessão (após carregar um perfil, à mão ou
        automaticamente). A janela da macro aberta apontaria para a macro antiga, então fecha."""
        if self.change_job is not None:
            self.win.after_cancel(self.change_job)
            self.change_job = None
        if self.macro_win is not None:
            self.macro_win.close()
            self.macro_win = None
        self._refresh_profiles()
        if profile_name:
            self.session.profile = profile_name
            self.profile_var.set(profile_name)
            self.status_var.set(f"Perfil '{profile_name}' carregado.")
        self.mode_var.set(self.cfg.mode)
        self._render_rows()
        self._show_mode()
        self._refresh_summary()

    def _save_profile(self):
        name = self.profile_var.get()
        if not name:
            self._save_profile_as()
        else:
            self._write_profile(name)

    def _save_profile_as(self):
        name = simpledialog.askstring("Salvar perfil", "Nome do perfil:", parent=self.win,
                                      initialvalue=self.profile_var.get())
        name = profiles.clean_name(name)
        if name:
            self._write_profile(name)

    def _write_profile(self, name):
        """Grava a config atual em `name`, perguntando antes se já existir um perfil com esse nome."""
        if name in profiles.names() and not messagebox.askyesno(
                "Salvar perfil", f"O perfil '{name}' já existe. Substituir pela configuração atual?",
                parent=self.win):
            return
        if profiles.save(name, self.cfg):
            self.session.profile = name
            self.profile_var.set(name)
            self._refresh_profiles()
            self.status_var.set(f"Perfil '{name}' salvo.")
        else:
            self.status_var.set("Não foi possível gravar o perfil em disco.")

    def _delete_profile(self):
        name = self.profile_var.get()
        if not name or not messagebox.askyesno(
                "Excluir perfil", f"Excluir o perfil '{name}'?", parent=self.win):
            return
        profiles.delete(name)
        if self.session.profile == name:
            self.session.profile = None
        self.profile_var.set("")
        self._refresh_profiles()
        self.status_var.set(f"Perfil '{name}' excluído.")
