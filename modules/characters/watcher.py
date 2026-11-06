"""Thread que mantém atualizado o personagem de cada PID, sem travar a interface.

A UI informa os PIDs com `set_pids` e lê o resultado com `names()`; nenhuma das duas bloqueia.
"""
import threading

from . import winapi
from .rflog import CharacterTracker

REFRESH_S = 2.0


class CharacterWatcher:
    def __init__(self, interval=REFRESH_S):
        self._interval = interval
        self._tracker = CharacterTracker()
        self._lock = threading.Lock()
        self._pids = set()
        self._infos = {}                    # pid → CharacterInfo
        self._process_cache = {}            # pid → (exe, criação) | None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="character-watcher", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def set_pids(self, pids):
        pids = set(pids)
        with self._lock:
            changed = pids != self._pids
            self._pids = pids
        if changed:
            self._wake.set()                # janela nova: não espera o próximo ciclo

    def names(self):
        """pid → nome do personagem (None quando está na seleção). PIDs sem log/fluxo ficam de fora."""
        with self._lock:
            return {pid: info.name for pid, info in self._infos.items()}

    def accounts(self):
        """pid → login da conta (o `SetAccountID` do log; None se o fluxo ainda não o mostrou)."""
        with self._lock:
            return {pid: info.account for pid, info in self._infos.items()}

    def _run(self):
        while not self._stop.is_set():
            try:
                self._refresh()
            except Exception:
                pass                        # leitura do log nunca derruba o programa
            self._wake.wait(self._interval)
            self._wake.clear()

    def _refresh(self):
        with self._lock:
            pids = set(self._pids)
        for pid in list(self._process_cache):
            if pid not in pids:
                del self._process_cache[pid]
        processes = {}
        for pid in pids:
            if pid not in self._process_cache:
                self._process_cache[pid] = winapi.process_info(pid)
            if self._process_cache[pid]:
                processes[pid] = self._process_cache[pid]
        infos = self._tracker.refresh(processes)
        with self._lock:
            self._infos = infos
