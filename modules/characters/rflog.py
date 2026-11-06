"""Descobre o personagem de cada client do RF lendo o `NetLog\\rfclient.log` do jogo.

O log é compartilhado por todos os clients da mesma instalação e as linhas não trazem o PID.
Cada linha é `[n] MM/DD/AA HH:MM:SS: mensagem`, e o contador `n` cresce de 1 em 1 dentro de um
client. Então:

- um client novo escreve `[1] ... GetDataFromLauncher`; essa linha abre um "fluxo", e o processo
  vivo é ligado ao fluxo cujo início bate com a hora de criação do processo;
- as demais linhas vão para o fluxo cujo contador está logo antes de `n` (o menor salto). TODOS
  os fluxos entram na conta, inclusive os de clients já fechados: sem eles, as linhas de um
  client fechado cairiam num vivo cujo contador coincidisse e o arrastariam para longe do seu
  número real. Com vários clients escrevendo juntos o jogo perde uma linha de vez em quando
  (`[783] [784] [786]`), então o salto não é sempre 0, mas no log real nunca passou de 2;
- se dois fluxos esperam o mesmo número, a linha é do que escreveu por último; se os dois
  estavam ativos no mesmo instante (abertos com segundos de diferença), não dá para saber de
  quem é: o contador anda, mas o conteúdo (conta, personagem) é ignorado. Melhor ficar sem nome
  do que mostrar o de outro client;
- `base result ( 0 - NOME )` é o personagem que entrou no mapa; carregar o mapa `lobby` é o
  client voltando à seleção de personagem (sem personagem).

Só lê o arquivo (nunca toca no processo do jogo).
"""
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

LOG_RELATIVE = os.path.join("NetLog", "rfclient.log")
ENCODING = "cp1252"

LINE_RE = re.compile(r"^\[(\d+)\] (\d\d)/(\d\d)/(\d\d) (\d\d):(\d\d):(\d\d): (.*)$")
ACCOUNT_RE = re.compile(r"^SetAccountID (\S+)")
CHARACTER_RE = re.compile(r"base result \( 0 - (.+?) \)\s*$")
LOBBY_RE = re.compile(r"^\d+ \) load map \( \.\\map\\lobby\\", re.I)
LAUNCH_PREFIX = "GetDataFromLauncher"

TIE_WINDOW = timedelta(seconds=2)  # fluxos ativos com menos que isso de diferença não se distinguem
START_TOLERANCE = (timedelta(seconds=-5), timedelta(seconds=60))   # início do fluxo − criação do processo
MAX_GAP = 3                         # linhas perdidas que ainda se aceitam entre duas do mesmo client
# Quanto do log, antes do client vivo mais antigo, também se lê: os clients que já fecharam mas
# escreviam junto com ele precisam ter o seu fluxo (o `[1]` de abertura) visto para não confundir.
READ_MARGIN = timedelta(days=7)
SEEK_BLOCK = 64 * 1024


@dataclass(frozen=True)
class CharacterInfo:
    name: Optional[str]         # None = o client está na seleção de personagem (ou ainda no login)
    account: Optional[str]


def log_path_for(exe_path):
    return os.path.normpath(os.path.join(os.path.dirname(exe_path), LOG_RELATIVE))


def parse_line(raw):
    """(contador, datetime, mensagem) ou None se a linha não tem o formato do log."""
    m = LINE_RE.match(raw)
    if not m:
        return None
    try:
        when = datetime(2000 + int(m[4]), int(m[2]), int(m[3]), int(m[5]), int(m[6]), int(m[7]))
    except ValueError:
        return None
    return int(m[1]), when, m[8]


class Stream:
    """As linhas de um único client (da abertura até agora)."""
    __slots__ = ("start", "account", "name", "last_n", "last_ts", "tied_at")

    def __init__(self, start):
        self.start = start
        self.account = None
        self.name = None
        self.last_n = 1
        self.last_ts = start
        self.tied_at = None         # contador em que houve empate com outro fluxo


class LogState:
    def __init__(self):
        self.streams = []

    def feed(self, n, when, msg):
        if n == 1 and msg.startswith(LAUNCH_PREFIX):
            self.streams.append(Stream(when))
            return
        gaps = [(n - s.last_n - 1, s) for s in self.streams if n > s.last_n and when >= s.last_ts]
        gaps = [(gap, s) for gap, s in gaps if gap <= MAX_GAP]
        if not gaps:
            return
        # Vale o fluxo com o menor salto (o do mesmo client quase sempre é 0). Se mais de um
        # espera exatamente o mesmo número, a linha é do que escreveu por último (os outros
        # estão parados). Quando os dois estavam ativos no mesmo instante, não há como saber.
        best = min(gap for gap, _ in gaps)
        candidates = [s for gap, s in gaps if gap == best]
        stream = max(candidates, key=lambda s: s.last_ts)
        close = [s for s in candidates if s is not stream and stream.last_ts - s.last_ts <= TIE_WINDOW]
        ambiguous = bool(close) or stream.tied_at == n
        for s in close:
            s.tied_at = stream.tied_at = n  # a outra linha `n`, que vem depois, também é incerta
        stream.last_n, stream.last_ts = n, when
        if ambiguous:
            return
        m = ACCOUNT_RE.match(msg)
        if m:
            stream.account = m[1]
            return
        m = CHARACTER_RE.search(msg)
        if m:
            stream.name = m[1]
        elif LOBBY_RE.match(msg):
            stream.name = None

    def bind(self, created_by_pid):
        """Liga cada processo (pid → hora de criação) ao fluxo que começou na mesma hora.
        Um-para-um, do mais antigo ao mais novo, sempre no fluxo livre mais próximo."""
        taken, result = set(), {}
        for pid, created in sorted(created_by_pid.items(), key=lambda kv: kv[1]):
            lo, hi = created + START_TOLERANCE[0], created + START_TOLERANCE[1]
            options = [s for s in self.streams if id(s) not in taken and lo <= s.start <= hi]
            if options:
                stream = min(options, key=lambda s: abs((s.start - created).total_seconds()))
                taken.add(id(stream))
                result[pid] = stream
        return result


class LogReader:
    """Lê só o que foi acrescentado ao arquivo desde a última leitura."""

    def __init__(self, path):
        self.path = path
        self.since = None           # só interessa o que for desta hora em diante
        self.start_offset = 0       # de onde a primeira leitura começou (para diagnóstico/testes)
        self.restarted = False      # o arquivo encolheu (foi recriado): o estado anterior não vale mais
        self._offset = None

    def reset(self, since):
        self.since, self._offset = since, None

    def read_new(self):
        """Linhas novas já interpretadas. [] se o arquivo não existe ou não cresceu."""
        try:
            size = os.path.getsize(self.path)
            with open(self.path, "rb") as f:
                if self._offset is not None and size < self._offset:
                    self.restarted = True
                if self._offset is None or self.restarted:           # 1ª leitura, ou arquivo recomeçou
                    self._offset = self.start_offset = self._seek_since(f, size)
                f.seek(self._offset)
                data = f.read(size - self._offset)
        except OSError:
            return []
        end = data.rfind(b"\n")
        if end < 0:
            return []                       # linha ainda incompleta: espera o resto
        self._offset += end + 1
        out = []
        for raw in data[:end].split(b"\n"):
            parsed = parse_line(raw.decode(ENCODING, errors="replace").rstrip("\r"))
            if parsed:
                out.append(parsed)
        return out

    def _seek_since(self, f, size):
        """Byte do começo de uma linha logo antes de `since`. As horas do log nunca voltam atrás,
        então uma busca binária evita reler arquivos grandes do início."""
        if self.since is None or size <= SEEK_BLOCK:
            return 0
        lo, hi = 0, size
        while hi - lo > SEEK_BLOCK:
            mid = (lo + hi) // 2
            when = self._time_at(f, mid)
            if when is not None and when < self.since:
                lo = mid
            else:
                hi = mid
        if lo == 0:
            return 0
        f.seek(lo)
        f.readline()                        # descarta a linha cortada
        return f.tell()

    @staticmethod
    def _time_at(f, pos):
        f.seek(pos)
        f.readline()
        for _ in range(50):                 # pula linhas fora do formato
            parsed = parse_line(f.readline().decode(ENCODING, errors="replace").rstrip("\r\n"))
            if parsed:
                return parsed[1]
        return None


class CharacterTracker:
    """Sem threads nem Tk: chame `refresh` de tempos em tempos."""

    def __init__(self):
        self._logs = {}             # caminho do log → (LogReader, LogState, processos vivos)

    def refresh(self, processes):
        """`processes`: pid → (caminho do .exe, hora de criação). Devolve pid → CharacterInfo,
        só para os pids que foram ligados a um fluxo do log."""
        by_log = {}
        for pid, (exe, created) in processes.items():
            by_log.setdefault(log_path_for(exe), {})[pid] = created
        for path in list(self._logs):
            if path not in by_log:
                del self._logs[path]        # nenhum client vivo usa mais este log

        result = {}
        for path, created_by_pid in by_log.items():
            alive = frozenset(created_by_pid.items())
            entry = self._logs.get(path)
            if entry is None or entry[2] != alive:
                # Entrou ou saiu um client: relê a janela do log do zero (o client mais antigo
                # pode ter mudado, e com ele o ponto de partida da leitura).
                reader = LogReader(path)
                reader.reset(min(created_by_pid.values()) - READ_MARGIN)
                entry = self._logs[path] = (reader, LogState(), alive)
            reader, state, _ = entry
            lines = reader.read_new()
            if reader.restarted:                    # arquivo recriado: o que sabíamos não vale mais
                reader.restarted = False
                state = LogState()
                self._logs[path] = (reader, state, alive)
            for n, when, msg in lines:
                state.feed(n, when, msg)
            for pid, stream in state.bind(created_by_pid).items():
                result[pid] = CharacterInfo(stream.name, stream.account)
        return result
