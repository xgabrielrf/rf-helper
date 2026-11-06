"""Janela de criação/edição da macro: Record/Stop, Clear, Loop e a lista Tecla/Tempo."""
import tkinter as tk
from tkinter import messagebox, ttk

from . import keys, windowing
from .model import DELAY
from .recorder import KeyRecorder

POLL_RECORDER_MS = 20
SHIFT_MASK, CONTROL_MASK = 0x1, 0x4
POSITION_KEY = "macro"
HINT = ("Record grava as teclas e o tempo entre elas. Ctrl/Shift+clique seleciona vários; "
        "F2 ou duplo clique edita o tempo (Enter aplica a todos os selecionados); Delete remove; "
        "arraste para reordenar.")


class MacroWindow:
    def __init__(self, parent, session, on_change, manager):
        self.session = session
        self.manager = manager              # guarda a posição da janela
        self.on_change = on_change          # chamado quando a macro muda (fora da gravação)
        self.recorder = KeyRecorder()
        self.recording = False
        self.editor = None                  # (Entry, índices das linhas de Tempo) em edição
        self.drag_iid = None
        self.dragged = False
        self.drag_mods = 0

        self.win = win = tk.Toplevel(parent)
        win.attributes("-topmost", True)
        win.geometry("340x420" + (windowing.visible_position(manager.get_position(POSITION_KEY)) or ""))
        win.minsize(300, 300)
        win.protocol("WM_DELETE_WINDOW", self.close)
        self.retitle()
        win.columnconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)
        self._build()
        self._render()
        windowing.hide_close_button(win)        # fecha pelo OK
        windowing.keep_on_screen(win)           # nunca fica escondida fora das telas

    @property
    def macro(self):
        return self.session.cfg.macro

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
        self.win.title(f"Macro — {self.session.title}")

    def close(self):
        if not self.alive():
            return
        if self.recording:
            self._stop_recording()
        self._end_edit(commit=False)
        self.manager.set_position(POSITION_KEY, windowing.current_position(self.win))
        self.win.destroy()

    # --- construção ---------------------------------------------------------
    def _build(self):
        win = self.win
        bar = ttk.Frame(win)
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        self.record_btn = ttk.Button(bar, text="Record", width=9, command=self._toggle_record)
        self.record_btn.grid(row=0, column=0)
        self.clear_btn = ttk.Button(bar, text="Clear", width=9, command=self._clear)
        self.clear_btn.grid(row=0, column=1, padx=4)
        self.loop_var = tk.BooleanVar(value=self.macro.loop)
        ttk.Checkbutton(bar, text="Loop", variable=self.loop_var,
                        command=self._toggle_loop).grid(row=0, column=2, padx=(8, 0))

        frame = ttk.Frame(win)
        frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(frame, columns=("kind", "value"), show="headings",
                                 selectmode="extended")
        self.tree.heading("kind", text="Tipo")
        self.tree.heading("value", text="Valor")
        self.tree.column("kind", width=80, stretch=False)
        self.tree.column("value", width=180, anchor="e")
        self.tree.tag_configure("delay", foreground="#555")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.bind("<ButtonPress-1>", self._on_press, add="+")
        self.tree.bind("<B1-Motion>", self._on_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.tree.bind("<F2>", self._begin_edit)
        self.tree.bind("<Double-1>", self._on_double)
        self.tree.bind("<Delete>", self._delete_selected)

        self.status_var = tk.StringVar(value=HINT)
        ttk.Label(win, textvariable=self.status_var, foreground="#555", wraplength=310).grid(
            row=2, column=0, sticky="ew", padx=10, pady=(0, 4))
        ttk.Button(win, text="OK", width=10, command=self.close).grid(
            row=3, column=0, sticky="e", padx=8, pady=(0, 8))

    def _set_status(self, text):
        self.status_var.set(text or HINT)

    # --- lista --------------------------------------------------------------
    def _render(self, select=()):
        self.tree.delete(*self.tree.get_children())
        for i, event in enumerate(self.macro.events):
            if event.kind == DELAY:
                self.tree.insert("", "end", iid=str(i), values=("Tempo", f"{event.value} ms"),
                                 tags=("delay",))
            else:
                self.tree.insert("", "end", iid=str(i), values=("Tecla", event.label or event.value))
        if select:
            self.tree.selection_set([str(i) for i in select if i < len(self.macro.events)])

    def _selected(self):
        return sorted(int(i) for i in self.tree.selection())

    def _notify(self):
        self.on_change()

    # --- gravação -----------------------------------------------------------
    def _toggle_record(self):
        if self.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self._end_edit(commit=True)
        self.macro.start_recording()
        self.recorder.start()
        if not self.recorder.is_running:
            self._set_status("Não foi possível iniciar a gravação (hook de teclado).")
            return
        while not self.recorder.events.empty():
            self.recorder.events.get_nowait()
        self.recording = True
        self.record_btn.configure(text="Stop")
        self.clear_btn.state(["disabled"])
        self._set_status("Gravando… aperte as teclas e clique em Stop ao terminar.")
        self._poll_recorder()

    def _stop_recording(self):
        self.recorder.stop()
        self._drain_recorder()
        self.macro.stop_recording()
        self.recording = False
        self.record_btn.configure(text="Record")
        self.clear_btn.state(["!disabled"])
        self._set_status("")
        self._render()
        self._notify()

    def _drain_recorder(self):
        got = False
        while not self.recorder.events.empty():
            vk, when = self.recorder.events.get_nowait()
            self.macro.record_key(vk, keys.key_label(vk), when)
            got = True
        return got

    def _poll_recorder(self):
        if not self.recording or not self.alive():
            return
        if self._drain_recorder():
            self._render()
            children = self.tree.get_children()
            if children:
                self.tree.see(children[-1])
        self.win.after(POLL_RECORDER_MS, self._poll_recorder)

    # --- barra --------------------------------------------------------------
    def _clear(self):
        if self.recording:
            return
        if self.macro.key_count() and not messagebox.askyesno(
                "Limpar macro", "Apagar toda a macro gravada?", parent=self.win):
            return
        self._end_edit(commit=False)
        self.macro.clear()
        self._render()
        self._notify()

    def _toggle_loop(self):
        self.macro.loop = self.loop_var.get()
        self._notify()

    # --- edição de Tempo (F2) -----------------------------------------------
    def _begin_edit(self, _event=None):
        if self.recording or self.editor:
            return "break"
        delays = [i for i in self._selected() if self.macro.events[i].kind == DELAY]
        if not delays:
            self._set_status("Selecione uma ou mais linhas de Tempo e aperte F2.")
            return "break"
        iid = str(delays[0])
        self.tree.see(iid)
        bbox = self.tree.bbox(iid, "value")
        if not bbox:
            return "break"
        x, y, w, h = bbox
        entry = tk.Entry(self.tree, justify="right")
        entry.insert(0, str(self.macro.events[delays[0]].value))
        entry.select_range(0, "end")
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_force()
        entry.bind("<Return>", lambda _e: self._end_edit(commit=True))
        entry.bind("<Escape>", lambda _e: self._end_edit(commit=False))
        entry.bind("<FocusOut>", lambda _e: self._end_edit(commit=True))
        self.editor = (entry, delays)
        return "break"

    def _on_double(self, event):
        """Duplo clique numa linha de Tempo = F2 só nela (o 1º clique do duplo já deixou só ela
        selecionada; editar várias de uma vez continua sendo Ctrl+clique + F2). Com Ctrl/Shift o
        duplo clique é só seleção."""
        if event.state & (SHIFT_MASK | CONTROL_MASK) or self.recording or self.editor:
            return "break"
        iid = self.tree.identify_row(event.y)
        if not iid or self.tree.identify_region(event.x, event.y) != "cell":
            return "break"
        self.tree.selection_set(iid)
        self._begin_edit()
        return "break"              # sem a ação padrão do Treeview (abrir/fechar o item)

    def _end_edit(self, commit):
        if not self.editor:
            return
        entry, indexes = self.editor
        self.editor = None                  # antes do destroy: o FocusOut não reentra
        text = entry.get().strip().lower().removesuffix("ms").strip()
        entry.destroy()
        if not commit:
            return
        if not text.isdigit():
            self._set_status("Valor inválido: digite os milissegundos (número inteiro).")
            return
        self.macro.set_delays(indexes, int(text))
        self._set_status("")
        self._render(select=indexes)
        self.tree.focus_set()
        self._notify()

    # --- remover e reordenar -------------------------------------------------
    def _delete_selected(self, _event=None):
        if self.recording or self.editor:
            return "break"
        selected = self._selected()
        if selected:
            self.macro.delete(selected)
            self._render()
            self._notify()
        return "break"

    def _on_press(self, event):
        self.drag_iid = self.tree.identify_row(event.y) or None
        self.drag_mods = event.state & (SHIFT_MASK | CONTROL_MASK)
        self.dragged = False

    def _on_motion(self, event):
        if not self.drag_iid or self.recording or self.editor or self.drag_mods:
            return
        target = self.tree.identify_row(event.y)
        if target and target != self.drag_iid:
            self.tree.move(self.drag_iid, "", self.tree.index(target))
            self.dragged = True

    def _on_release(self, _event):
        iid, dragged = self.drag_iid, self.dragged
        self.drag_iid, self.dragged = None, False
        if not (iid and dragged):
            return
        order = [int(i) for i in self.tree.get_children()]
        self.macro.reorder(order)
        self._render(select=[order.index(int(iid))])
        self._notify()
