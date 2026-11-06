"""Cores e widgets do tema escuro da tela inicial.

Só widgets `tk` com cores explícitas (nada de mudar o tema global do ttk): a janelinha do Modo
grupo, que usa ttk, não pode mudar de aparência quando a tela inicial está aberta.
"""
import tkinter as tk

from ..clicker import windowing

BG = "#1e2227"          # fundo da área central
PANEL = "#262b31"       # barra lateral e faixa da direita
CARD = "#2f353d"
CARD_HOVER = "#363d46"
INPUT = "#1a1e23"
LINE = "#3a414a"
TEXT = "#e8ebef"
MUTED = "#9aa3ad"
GREEN, GREEN_HOVER = "#1f8a4c", "#27a35c"
BLUE, BLUE_HOVER = "#2f6fed", "#4a84f5"
RED, RED_HOVER = "#c43b3b", "#d95252"
GRAY, GRAY_HOVER = "#3d444d", "#4b535d"

FONT = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 15, "bold")
FONT_BIG = ("Segoe UI", 12, "bold")
FONT_MONO = ("Consolas", 10)


HOVERS = {GRAY: GRAY_HOVER, GREEN: GREEN_HOVER, BLUE: BLUE_HOVER, RED: RED_HOVER, CARD: CARD_HOVER,
          PANEL: GRAY}


def button(parent, text, command, bg=GRAY, hover=None, fg=TEXT, font=FONT_BOLD, padx=14, pady=6, **kw):
    """Botão plano com destaque ao passar o mouse."""
    hover = hover or HOVERS.get(bg, bg)
    btn = tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=hover,
                    activeforeground=fg, relief="flat", bd=0, cursor="hand2", font=font,
                    padx=padx, pady=pady, highlightthickness=0, **kw)
    btn.bind("<Enter>", lambda _e: btn.configure(bg=hover) if str(btn["state"]) == "normal" else None)
    btn.bind("<Leave>", lambda _e: btn.configure(bg=bg))
    return btn


def set_button_colors(btn, bg, hover=None):
    """Troca as cores de um `button()` já criado (ex.: Play ↔ Cancelar)."""
    hover = hover or HOVERS.get(bg, bg)
    btn.configure(bg=bg, activebackground=hover)
    btn.bind("<Enter>", lambda _e: btn.configure(bg=hover) if str(btn["state"]) == "normal" else None)
    btn.bind("<Leave>", lambda _e: btn.configure(bg=bg))


def label(parent, text="", fg=TEXT, bg=None, font=FONT, **kw):
    return tk.Label(parent, text=text, fg=fg, bg=bg if bg is not None else parent["bg"], font=font, **kw)


def entry(parent, textvariable=None, show=None, width=30, font=FONT):
    """Campo de texto escuro com borda que acende quando focado."""
    return tk.Entry(parent, textvariable=textvariable, show=show or "", width=width, font=font, bg=INPUT,
                    fg=TEXT, insertbackground=TEXT, relief="flat", bd=0, highlightthickness=1,
                    highlightbackground=LINE, highlightcolor=BLUE, disabledbackground=INPUT,
                    disabledforeground=MUTED, selectbackground=BLUE, selectforeground="white")


def initial_icon(parent, text, size=40, bg=GRAY, image=None):
    """Quadradinho com a inicial do nome (ou a imagem do servidor, se houver)."""
    canvas = tk.Canvas(parent, width=size, height=size, bg=parent["bg"], highlightthickness=0, bd=0)
    if image is not None:
        canvas.create_image(size // 2, size // 2, image=image)
        canvas.image = image            # o Tk não guarda a referência
    else:
        canvas.create_rectangle(2, 2, size - 2, size - 2, fill=bg, outline="")
        canvas.create_text(size // 2, size // 2, text=(text.strip()[:1] or "?").upper(), fill=TEXT,
                           font=("Segoe UI", max(10, size // 2), "bold"))
    return canvas


def dot(parent, color, size=10):
    canvas = tk.Canvas(parent, width=size + 2, height=size + 2, bg=parent["bg"], highlightthickness=0, bd=0)
    canvas.create_oval(1, 1, size + 1, size + 1, fill=color, outline=LINE)
    return canvas


def group_icon(parent, size=34, color=TEXT, bg=PANEL):
    """Três pessoinhas (o ícone do Modo grupo), desenhadas à mão: sem arquivos de imagem."""
    c = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
    u = size / 34

    def person(cx, top, r, body_w):
        c.create_oval((cx - r) * u, top * u, (cx + r) * u, (top + 2 * r) * u, fill=color, outline="")
        c.create_arc((cx - body_w) * u, (top + 2 * r + 2) * u, (cx + body_w) * u, (top + 2 * r + 2 + 2 * body_w) * u,
                     start=0, extent=180, fill=color, outline="")

    person(17, 5, 5, 8)
    person(6, 11, 3.5, 5.5)
    person(28, 11, 3.5, 5.5)
    return c


class ScrollFrame(tk.Frame):
    """Área rolável (roda do mouse e barra fina escura). Os filhos entram em `.inner`."""

    BAR_WIDTH = 8

    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.bar = tk.Canvas(self, width=self.BAR_WIDTH, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self._thumb = self.bar.create_rectangle(0, 0, self.BAR_WIDTH, 0, fill=GRAY_HOVER, outline="")
        self._thumb_range = (0.0, 1.0)
        self._drag_from = None
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self._sync())
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._on_wheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))
        self.bar.bind("<ButtonPress-1>", self._bar_press)
        self.bar.bind("<B1-Motion>", self._bar_drag)
        self.bar.bind("<Configure>", lambda _e: self._draw_thumb())
        self.on_width = None            # chamado com a largura útil quando ela muda (reflow dos cards)
        self._width = 0

    def _on_scroll(self, first, last):
        self._thumb_range = (float(first), float(last))
        if self._thumb_range[0] <= 0.0 and self._thumb_range[1] >= 1.0:
            self.bar.pack_forget()
        elif not self.bar.winfo_ismapped():
            self.bar.pack(side="right", fill="y", padx=(4, 0), before=self.canvas)
        self._draw_thumb()

    def _draw_thumb(self):
        height = self.bar.winfo_height()
        first, last = self._thumb_range
        self.bar.coords(self._thumb, 0, first * height, self.BAR_WIDTH, max(last * height, first * height + 20))

    def _bar_press(self, event):
        height = max(1, self.bar.winfo_height())
        first, last = self._thumb_range
        if first * height <= event.y <= last * height:
            self._drag_from = (event.y, first)
        else:                           # clique fora do botão: centraliza nele
            self._drag_from = (event.y, first)
            self.canvas.yview_moveto(event.y / height - (last - first) / 2)
            self._drag_from = (event.y, self._thumb_range[0])

    def _bar_drag(self, event):
        if self._drag_from:
            start_y, start_first = self._drag_from
            self.canvas.yview_moveto(start_first + (event.y - start_y) / max(1, self.bar.winfo_height()))

    def _sync(self):
        self.canvas.configure(scrollregion=(0, 0, self.inner.winfo_reqwidth(), self.inner.winfo_reqheight()))

    def _on_resize(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)
        if event.width != self._width:
            self._width = event.width
            if self.on_width:
                self.on_width(event.width)

    def _on_wheel(self, event):
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def scroll_top(self):
        self.canvas.yview_moveto(0)


def dialog(parent, title):
    """Janela modal escura, centralizada sobre `parent`. Esc fecha. O chamador monta o conteúdo,
    chama `finish(win)` e depois `parent.wait_window(win)`."""
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=PANEL)
    win.resizable(False, False)
    win.transient(parent.winfo_toplevel())
    win.bind("<Escape>", lambda _e: win.destroy())
    return win


def finish(win, position=None, remember=None):
    """Posiciona o diálogo, mostra e captura o foco. Com `position` ('+x+y' lembrada) e um monitor que ainda
    existe, abre ali; senão, centraliza sobre a janela dona. Nunca fica fora das telas (`keep_on_screen`).
    `remember(posição)` é chamado ao fechar, com a última posição (sempre dentro das telas)."""
    win.update_idletasks()
    placed = windowing.visible_position(position)
    if placed:
        win.geometry(placed)
    else:
        owner = win.master.winfo_toplevel()
        x = owner.winfo_rootx() + (owner.winfo_width() - win.winfo_reqwidth()) // 2
        y = owner.winfo_rooty() + (owner.winfo_height() - win.winfo_reqheight()) // 2
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
    windowing.keep_on_screen(win)
    if remember:
        last = {"position": windowing.current_position(win)}

        def on_configure(event):
            if event.widget is win:
                last["position"] = windowing.current_position(win)

        def on_destroy(event):
            if event.widget is win:
                remember(last["position"])
        win.bind("<Configure>", on_configure, add="+")
        win.bind("<Destroy>", on_destroy, add="+")
    win.grab_set()
    win.focus_set()


class Dropdown(tk.Frame):
    """Lista suspensa escura: caixa com o valor e ▾; o clique abre uma lista sem borda com as opções.
    `options` = [(valor, texto, cor ou None)]. O valor escolhido fica em `variable` ("" = nada escolhido).

    Feita à mão porque o Combobox do ttk só aceita tema escuro mudando o tema global, o que mudaria
    também a janelinha do Modo grupo."""

    def __init__(self, parent, options, variable, placeholder="Selecione", width=14, bg=PANEL):
        super().__init__(parent, bg=INPUT, highlightthickness=1, highlightbackground=LINE, highlightcolor=BLUE,
                         cursor="hand2", takefocus=1)
        self.options = {value: (text, color) for value, text, color in options}
        self.order = [value for value, _t, _c in options]
        self.variable, self.placeholder, self.popup = variable, placeholder, None
        self._dot = tk.Canvas(self, width=12, height=12, bg=INPUT, highlightthickness=0, bd=0)
        self._label = tk.Label(self, bg=INPUT, fg=TEXT, font=FONT, anchor="w", width=width, padx=4, pady=5)
        self._arrow = tk.Label(self, text="▾", bg=INPUT, fg=MUTED, font=FONT_SMALL, padx=6)
        self._dot.pack(side="left", padx=(8, 0))
        self._label.pack(side="left", fill="x", expand=True)
        self._arrow.pack(side="right")
        for widget in (self, self._dot, self._label, self._arrow):
            widget.bind("<Button-1>", self._toggle)
        self.bind("<Return>", self._toggle)
        self.bind("<space>", self._toggle)
        self._trace = variable.trace_add("write", lambda *_: self._refresh())
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._refresh()

    def _on_destroy(self, event):
        if event.widget is self:
            self._close()
            try:
                self.variable.trace_remove("write", self._trace)
            except (tk.TclError, ValueError):
                pass

    def _refresh(self):
        value = self.variable.get()
        text, color = self.options.get(value, (self.placeholder, None))
        self._label.configure(text=text, fg=TEXT if value in self.options else MUTED)
        self._dot.delete("all")
        if color:
            self._dot.create_oval(1, 1, 11, 11, fill=color, outline=LINE)
            self._dot.pack(side="left", padx=(8, 0), before=self._label)
        else:
            self._dot.pack_forget()

    def _toggle(self, _event=None):
        if self.popup is not None:
            self._close()
        else:
            self._open()

    def _open(self):
        self.focus_set()
        popup = self.popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(bg=LINE)
        rows = tk.Frame(popup, bg=INPUT)
        rows.pack(padx=1, pady=1)
        for value in self.order:
            text, color = self.options[value]
            row = tk.Frame(rows, bg=INPUT, cursor="hand2")
            row.pack(fill="x")
            parts = [row]
            if color:
                dot = tk.Canvas(row, width=12, height=12, bg=INPUT, highlightthickness=0, bd=0)
                dot.create_oval(1, 1, 11, 11, fill=color, outline=LINE)
                dot.pack(side="left", padx=(8, 0))
                parts.append(dot)
            label = tk.Label(row, text=text, bg=INPUT, fg=TEXT, font=FONT, anchor="w", padx=6, pady=5)
            label.pack(side="left", fill="x", expand=True)
            parts.append(label)
            for part in parts:
                part.bind("<Button-1>", lambda _e, v=value: self._choose(v))
                part.bind("<Enter>", lambda _e, p=parts: [w.configure(bg=GRAY) for w in p])
                part.bind("<Leave>", lambda _e, p=parts: [w.configure(bg=INPUT) for w in p])
        popup.update_idletasks()
        width = max(self.winfo_width(), popup.winfo_reqwidth())
        popup.geometry(f"{width}x{popup.winfo_reqheight()}+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height()}")
        popup.bind("<Escape>", lambda _e: self._close())
        popup.bind("<FocusOut>", lambda _e: self.after(60, self._close_if_unfocused))
        popup.focus_force()

    def _close_if_unfocused(self):
        popup = self.popup
        if popup is None:
            return
        try:
            focused = popup.focus_displayof()
        except tk.TclError:
            focused = None
        if focused is None or not str(focused).startswith(str(popup)):
            self._close()

    def _choose(self, value):
        self.variable.set(value)
        self._close()

    def _close(self):
        popup, self.popup = self.popup, None
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
        try:
            self.focus_set()
        except tk.TclError:
            pass


class Checkbox(tk.Canvas):
    """Caixa de marcar desenhada à mão (o Checkbutton do Tk não segue o tema escuro)."""

    def __init__(self, parent, variable, command=None, bg=CARD, size=18):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.variable, self.command, self.size = variable, command, size
        self.bind("<Button-1>", self._toggle)
        self._trace = variable.trace_add("write", lambda *_: self._draw())
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._draw()

    def _on_destroy(self, event):
        if event.widget is self:        # a variável vive mais que a caixa (a seleção sobrevive a redesenhos)
            try:
                self.variable.trace_remove("write", self._trace)
            except (tk.TclError, ValueError):
                pass

    def _toggle(self, _event=None):
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()
        return "break"

    def _draw(self):
        self.delete("all")
        s = self.size
        on = bool(self.variable.get())
        self.create_rectangle(2, 2, s - 2, s - 2, outline=BLUE if on else MUTED, width=2, fill=BLUE if on else "")
        if on:
            self.create_line(5, s // 2 + 1, s // 2 - 1, s - 6, s - 5, 6, fill="white", width=2)
