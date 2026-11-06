"""Fila de logins automáticos (botão Play): um por vez, numa thread, sem tocar no Tk.

`login_fn(launcher_path, server_index, login, password, on_status, cancel)` faz o login de
verdade (modules.autologin.launcher.login) e levanta `LoginError`/`Cancelled`. Quem usa esta
classe chama `drain()` periodicamente, na thread do Tk, para receber o que mudou.
"""
import queue
import threading
from collections import namedtuple

from ..autologin import Cancelled, LoginError

QUEUED, RUNNING = "queued", "running"
# kind: "status" | "done" (value = PID do client novo) | "error" | "cancelled" | "skipped"
Event = namedtuple("Event", "account_id kind text value", defaults=(None,))
Job = namedtuple("Job", "account_id launcher_path server_index login password cancel")


class PlayController:
    def __init__(self, login_fn, should_skip=None):
        """`should_skip(account_id)` (opcional, chamado na thread da fila) diz que a conta já está em
        jogo: o job é descartado na hora de rodar, com o evento "skipped"."""
        self.login_fn = login_fn
        self.should_skip = should_skip or (lambda account_id: False)
        self._jobs = queue.Queue()
        self._events = queue.Queue()
        self._state = {}                # account_id -> (QUEUED|RUNNING, texto)
        self._cancels = {}              # account_id -> threading.Event
        self._thread = None
        self._stopping = False

    # --- chamado na thread do Tk ---------------------------------------------
    def state(self, account_id):
        """(QUEUED|RUNNING, texto) enquanto a conta está na fila ou entrando; senão None."""
        return self._state.get(account_id)

    def busy(self):
        return bool(self._state)

    def start(self, server, account):
        if account.id in self._state or not account.password:
            return False
        cancel = self._cancels[account.id] = threading.Event()
        self._state[account.id] = (QUEUED, "Na fila")
        self._jobs.put(Job(account.id, server.launcher_path, server.server_index, account.login,
                           account.password, cancel))
        self._ensure_thread()
        return True

    def start_many(self, server, accounts):
        """Enfileira `accounts` **na ordem recebida** (a da tela). Retorna os ids que entraram na fila."""
        return [a.id for a in accounts if self.start(server, a)]

    def cancel_all(self):
        for account_id in list(self._cancels):
            self.cancel(account_id)

    def cancel(self, account_id):
        """Tira da fila na hora; se já está entrando, a thread para na próxima etapa."""
        cancel = self._cancels.get(account_id)
        if cancel is None:
            return
        cancel.set()
        if self._state.get(account_id, (None,))[0] == QUEUED:
            self._state.pop(account_id, None)
            self._cancels.pop(account_id, None)

    def drain(self):
        """Eventos novos desde a última chamada (e atualiza `state`)."""
        events = []
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                return events
            if event.kind == "status":
                if event.account_id in self._state:
                    self._state[event.account_id] = (RUNNING, event.text)
            else:
                self._state.pop(event.account_id, None)
                self._cancels.pop(event.account_id, None)
            events.append(event)

    def shutdown(self):
        """Cancela tudo e deixa a thread terminar sozinha."""
        self._stopping = True
        for cancel in list(self._cancels.values()):
            cancel.set()
        self._jobs.put(None)

    # --- thread --------------------------------------------------------------
    def _ensure_thread(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="play", daemon=True)
            self._thread.start()

    def _run(self):
        while not self._stopping:
            job = self._jobs.get()
            if job is None:
                return
            put = lambda kind, text="", _id=job.account_id: self._events.put(Event(_id, kind, text, None))
            if job.cancel.is_set():         # cancelado na fila: a tela já limpou o estado
                continue
            if self.should_skip(job.account_id):
                put("skipped", "Já está em jogo.")
                continue
            put("status", "Abrindo o launcher…")
            try:
                pid = self.login_fn(job.launcher_path, job.server_index, job.login, job.password,
                                    lambda text: put("status", text), job.cancel)
                self._events.put(Event(job.account_id, "done", "", pid))
            except Cancelled:
                put("cancelled")
            except LoginError as exc:
                put("error", str(exc))
            except Exception as exc:                # falha inesperada: não derruba a fila
                put("error", f"Erro inesperado: {type(exc).__name__}")
