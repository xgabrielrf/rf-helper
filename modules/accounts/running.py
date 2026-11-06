"""Quais contas estão em jogo agora (sem Tk, sem Win32: quem usa informa os PIDs vivos).

Duas fontes por PID vivo:
- **bind**: o PID que o próprio Play acabou de abrir para aquela conta (autoritativo, não depende do log);
- **o log**: o `SetAccountID` que o client escreve no `rfclient.log`, para clients abertos por fora.
O login é comparado sem diferenciar maiúsculas.
"""


def _key(login):
    return (login or "").strip().lower()


class RunningAccounts:
    def __init__(self):
        self._bound = {}            # pid → login (chave minúscula), aberto pelo Play
        self._from_log = {}         # pid → login (chave minúscula), lido do log
        self._live = set()

    def bind(self, login, pid):
        """Registra que `pid` é o client de `login` (chamado quando o Play devolve o PID novo)."""
        self._bound[pid] = _key(login)

    def update(self, live_pids, log_accounts):
        """`live_pids`: PIDs de RF_Online.bin existentes agora; `log_accounts`: {pid: login|None} do log.

        Retorna os **desencontros**: `[(pid, login pedido, login que o log mostra)]` para um PID que o Play
        ligou a uma conta mas cujo log diz outra (o launcher pode ter entrado com o ID errado). Essas ligações
        são descartadas: vale o que o log diz."""
        self._live = set(live_pids)
        self._from_log = {pid: _key(acc) for pid, acc in (log_accounts or {}).items()
                          if pid in self._live and _key(acc)}
        mismatches = []
        for pid, login in list(self._bound.items()):
            if pid not in self._live:
                del self._bound[pid]
            elif pid in self._from_log and self._from_log[pid] != login:
                mismatches.append((pid, login, self._from_log[pid]))
                del self._bound[pid]
        return mismatches

    def pids_for(self, login):
        key = _key(login)
        if not key:
            return set()
        pids = {pid for pid, acc in self._bound.items() if acc == key}
        pids |= {pid for pid, acc in self._from_log.items() if acc == key}
        return pids & self._live

    def is_running(self, login):
        return bool(self.pids_for(login))

    def running_logins(self):
        """Conjunto de logins (minúsculos) com pelo menos um client vivo."""
        return {acc for acc in list(self._bound.values()) + list(self._from_log.values())
                if any(p in self._live for p in self.pids_for(acc))}
