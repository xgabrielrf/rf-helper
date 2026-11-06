"""Uma sessão de clicker por janela (HWND): configuração, runner e estado do ícone.

Tudo aqui roda na thread do Tk, exceto o callback de término do Runner, que só enfileira.
`on_change(hwnd)` e `on_message(texto)` são chamados sempre na thread do Tk.
"""
import queue

from . import profiles
from . import runner as runner_mod
from .model import ClickerConfig
from .runner import Runner

UNSET, OFF, ON = "unset", "off", "on"      # cinza / vermelho / verde

EXIT_MESSAGES = {
    runner_mod.ACCESS_DENIED: "Sem acesso à janela do RF: abra o programa como administrador.",
    runner_mod.FAILED: "Falha ao enviar teclas: a janela não respondeu.",
}
RESTART_JOIN_S = 0.3


class Session:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.cfg = ClickerConfig()
        self.runner = None
        self.config_win = None
        self.title = ""
        self.character = None       # personagem em jogo neste client (None = na seleção/desconhecido)
        self.profile = None         # último perfil carregado ou salvo aqui (aparece ao reabrir a tela)


class ClickerManager:
    def __init__(self, on_change=None, on_message=None, get_position=None, set_position=None):
        self.on_change = on_change or (lambda hwnd: None)
        self.on_message = on_message or (lambda text: None)
        # Onde ficam as telas de configuração ("clicker", "macro"): quem usa o módulo decide onde
        # guardar. get_position(nome) → '+x+y' ou None; set_position(nome, '+x+y').
        self.get_position = get_position or (lambda name: None)
        self.set_position = set_position or (lambda name, position: None)
        self.auto_profile = False   # carregar sozinho o perfil com o nome do personagem
        self._sessions = {}
        self._exits = queue.Queue()

    # --- consulta -----------------------------------------------------------
    def session(self, hwnd):
        if hwnd not in self._sessions:
            self._sessions[hwnd] = Session(hwnd)
        return self._sessions[hwnd]

    def mode(self, hwnd):
        return self.session(hwnd).cfg.mode

    def state(self, hwnd):
        s = self._sessions.get(hwnd)
        if s is None or not s.cfg.is_configured():
            return UNSET
        return ON if s.runner is not None and s.runner.is_running else OFF

    # --- ligar / desligar ---------------------------------------------------
    def toggle(self, hwnd):
        s = self.session(hwnd)
        if s.runner is not None:
            self.stop(hwnd)
        elif s.cfg.is_configured():
            self.start(hwnd)
        else:
            self.on_message("Configure o clicker (⚙) antes de ligar.")

    def start(self, hwnd):
        s = self.session(hwnd)
        if s.runner is not None or not s.cfg.is_configured():
            return
        s.runner = Runner(hwnd, s.cfg.copy(), lambda r, reason: self._exits.put((r, reason)))
        s.runner.start()
        self.on_change(hwnd)

    def stop(self, hwnd):
        s = self._sessions.get(hwnd)
        if s is None or s.runner is None:
            return
        runner, s.runner = s.runner, None
        runner.stop()
        self.on_change(hwnd)

    def config_changed(self, hwnd):
        """A configuração foi editada: reinicia o runner com ela, ou o desliga se ficou vazia."""
        s = self._sessions.get(hwnd)
        if s is None:
            return
        if s.runner is not None:
            old, s.runner = s.runner, None
            old.stop()
            old.join(RESTART_JOIN_S)        # evita duas threads enviando à mesma janela
            if s.cfg.is_configured():
                self.start(hwnd)
                return
        self.on_change(hwnd)

    def replace_config(self, hwnd, cfg):
        """Troca a configuração inteira (ex.: carregar perfil)."""
        self.session(hwnd).cfg = cfg
        self.config_changed(hwnd)

    # --- personagem ---------------------------------------------------------
    def character_changed(self, hwnd, name):
        """O personagem do client mudou. `name` None = voltou à seleção de personagem.

        Voltar à seleção para o clicker (as teclas não fazem sentido ali). Quando um personagem
        entra, e `auto_profile` está ligado, carrega o perfil de mesmo nome (se existir). Um
        clicker nunca é ligado sozinho."""
        s = self.session(hwnd)
        if name == s.character:
            return
        s.character = name
        if name is None:
            if s.runner is not None:
                self.stop(hwnd)
                self.on_message("Clicker parado: o client voltou à seleção de personagem.")
            return
        if not self.auto_profile:
            return
        found = profiles.find(name)
        cfg = profiles.load(found) if found else None
        if cfg is None:
            return
        self.replace_config(hwnd, cfg)
        s.profile = found
        if s.config_win is not None and s.config_win.alive():
            s.config_win.reload(found)
        self.on_message(f"Perfil '{found}' carregado.")

    def set_title(self, hwnd, title):
        """Atualiza o título das janelas do clicker (o nome da linha mudou)."""
        s = self.session(hwnd)
        s.title = title
        if s.config_win is not None and s.config_win.alive():
            s.config_win.retitle()

    # --- ciclo de vida ------------------------------------------------------
    def poll(self):
        """Processa runners que terminaram sozinhos (macro sem loop, janela fechada, erro)."""
        while True:
            try:
                runner, reason = self._exits.get_nowait()
            except queue.Empty:
                return
            s = self._sessions.get(runner.hwnd)
            if s is None or s.runner is not runner:     # parado/reiniciado por nós: já tratado
                continue
            s.runner = None
            self.on_change(runner.hwnd)
            if reason in EXIT_MESSAGES:
                self.on_message(EXIT_MESSAGES[reason])

    def forget(self, hwnd):
        """A janela do RF fechou: para tudo e descarta a sessão."""
        s = self._sessions.pop(hwnd, None)
        if s is None:
            return
        if s.runner is not None:
            s.runner.stop()
        if s.config_win is not None:
            s.config_win.close()

    def stop_all(self):
        for hwnd in list(self._sessions):
            self.forget(hwnd)

    # --- janelas ------------------------------------------------------------
    def open_config(self, parent, hwnd, title):
        from .config_window import ConfigWindow     # import tardio: o manager não exige Tk
        s = self.session(hwnd)
        s.title = title
        if s.config_win is not None and s.config_win.alive():
            s.config_win.focus()
            return
        s.config_win = ConfigWindow(parent, self, s)
