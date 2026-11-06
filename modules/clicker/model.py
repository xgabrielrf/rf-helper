"""Modelo de dados do clicker (sem Tk, sem Win32): fácil de testar e de serializar."""
from dataclasses import dataclass, field

MODE_CLICK, MODE_MACRO = "click", "macro"
DEFAULT_MS = 100
MIN_CLICK_MS = 10               # piso do período de uma tecla no modo click
TRAILING_DELAY_MS = 1000        # tempo final acrescentado ao parar uma gravação
MAX_MS = 3_600_000

KEY, DELAY = "key", "delay"


@dataclass
class KeyRow:
    """Uma linha do modo click: tecla + período em ms. vk == 0 significa linha vazia."""
    vk: int = 0
    label: str = ""
    ms: int = DEFAULT_MS


@dataclass
class MacroEvent:
    kind: str                   # KEY ou DELAY
    value: int                  # vk (KEY) ou milissegundos (DELAY)
    label: str = ""             # rótulo da tecla (só KEY)


def key_event(vk, label):
    return MacroEvent(KEY, vk, label)


def delay_event(ms):
    return MacroEvent(DELAY, max(0, int(ms)))


class Macro:
    """Sequência de linhas Tecla/Tempo. Gravar acrescenta ao final (mantém o histórico)."""

    def __init__(self, events=None, loop=True):
        self.events = list(events or [])
        self.loop = loop
        self._rec_last = None       # instante (s) do último evento gravado; None = nada ainda
        self._rec_count = 0

    # --- consulta -----------------------------------------------------------
    def key_count(self):
        return sum(1 for e in self.events if e.kind == KEY)

    def duration_ms(self):
        return sum(e.value for e in self.events if e.kind == DELAY)

    def is_empty(self):
        return self.key_count() == 0

    # --- edição -------------------------------------------------------------
    def reorder(self, new_order):
        """`new_order`: índices antigos na nova ordem (permutação completa)."""
        if sorted(new_order) != list(range(len(self.events))):
            raise ValueError("ordem inválida")
        self.events = [self.events[i] for i in new_order]

    def move(self, src, dst):
        """Move a linha `src` para a posição `dst` (índice na lista já reordenada)."""
        event = self.events.pop(src)
        self.events.insert(dst, event)

    def delete(self, indexes):
        drop = set(indexes)
        self.events = [e for i, e in enumerate(self.events) if i not in drop]

    def set_delays(self, indexes, ms):
        """Aplica `ms` a todas as linhas de Tempo entre `indexes`; teclas são ignoradas.
        Retorna quantas linhas mudaram."""
        ms = max(0, min(MAX_MS, int(ms)))
        changed = 0
        for i in indexes:
            if 0 <= i < len(self.events) and self.events[i].kind == DELAY:
                self.events[i].value = ms
                changed += 1
        return changed

    def clear(self):
        self.events = []
        self._rec_last, self._rec_count = None, 0

    # --- gravação -----------------------------------------------------------
    def start_recording(self):
        self._rec_last, self._rec_count = None, 0

    def record_key(self, vk, label, when):
        """Registra uma tecla apertada no instante `when` (segundos). A primeira tecla de cada
        gravação não ganha Tempo à frente: não guarda o tempo de reação de quem apertou Record."""
        if self._rec_last is not None:
            self.events.append(delay_event(round((when - self._rec_last) * 1000)))
        self.events.append(key_event(vk, label))
        self._rec_last = when
        self._rec_count += 1

    def stop_recording(self):
        """Fecha a gravação com um Tempo final (define a pausa do loop), se gravou algo."""
        if self._rec_count and self.events and self.events[-1].kind != DELAY:
            self.events.append(delay_event(TRAILING_DELAY_MS))
        self._rec_last, self._rec_count = None, 0

    # --- serialização -------------------------------------------------------
    def to_dict(self):
        return {"loop": self.loop,
                "events": [{"kind": e.kind, "value": e.value, "label": e.label}
                           for e in self.events]}

    @classmethod
    def from_dict(cls, data):
        macro = cls()
        if not isinstance(data, dict):
            return macro
        if isinstance(data.get("loop"), bool):
            macro.loop = data["loop"]
        for raw in data.get("events") or []:
            if not isinstance(raw, dict) or not isinstance(raw.get("value"), int) \
                    or isinstance(raw.get("value"), bool) or raw["value"] < 0:
                continue
            if raw.get("kind") == KEY and 0 < raw["value"] < 0xFF:
                macro.events.append(key_event(raw["value"], str(raw.get("label") or "")))
            elif raw.get("kind") == DELAY:
                macro.events.append(delay_event(min(raw["value"], MAX_MS)))
        return macro


def _fresh_keys():
    return [KeyRow()]


@dataclass
class ClickerConfig:
    mode: str = MODE_CLICK
    keys: list = field(default_factory=_fresh_keys)
    macro: Macro = field(default_factory=Macro)

    def active_keys(self):
        return [row for row in self.keys if row.vk]

    def is_configured(self):
        if self.mode == MODE_MACRO:
            return not self.macro.is_empty()
        return bool(self.active_keys())

    def copy(self):
        return ClickerConfig.from_dict(self.to_dict())

    def to_dict(self):
        return {"mode": self.mode,
                "keys": [{"vk": r.vk, "label": r.label, "ms": r.ms} for r in self.keys],
                "macro": self.macro.to_dict()}

    @classmethod
    def from_dict(cls, data):
        cfg = cls()
        if not isinstance(data, dict):
            return cfg
        if data.get("mode") in (MODE_CLICK, MODE_MACRO):
            cfg.mode = data["mode"]
        rows = []
        for raw in data.get("keys") or []:
            if not isinstance(raw, dict):
                continue
            vk, ms = raw.get("vk"), raw.get("ms")
            vk = vk if isinstance(vk, int) and not isinstance(vk, bool) and 0 <= vk < 0xFF else 0
            ms = ms if isinstance(ms, int) and not isinstance(ms, bool) and ms > 0 else DEFAULT_MS
            rows.append(KeyRow(vk, str(raw.get("label") or "") if vk else "", min(ms, MAX_MS)))
        cfg.keys = rows or _fresh_keys()
        cfg.macro = Macro.from_dict(data.get("macro"))
        return cfg
