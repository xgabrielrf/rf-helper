"""Perfis nomeados (config completa do clicker) em %APPDATA%\\ChangeScreenRF\\profiles.json.

Mesma pasta do config.json do change_screen. Escrita atômica; arquivo ausente ou corrompido
é tolerado (vira "sem perfis").
"""
import json
import os

from .model import ClickerConfig

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ChangeScreenRF")
PROFILES_PATH = os.path.join(CONFIG_DIR, "profiles.json")
MAX_NAME = 40


def clean_name(name):
    return " ".join((name or "").split())[:MAX_NAME]


def _read():
    try:
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    profiles = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(profiles, dict):
        return {}
    return {name: raw for name, raw in profiles.items() if isinstance(raw, dict)}


def _write(profiles):
    try:
        os.makedirs(os.path.dirname(PROFILES_PATH), exist_ok=True)
        tmp = PROFILES_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "profiles": profiles}, f, indent=2, ensure_ascii=False)
        os.replace(tmp, PROFILES_PATH)
        return True
    except OSError:
        return False


def names():
    return sorted(_read(), key=str.lower)


def find(name):
    """Nome do perfil salvo que corresponde a `name` sem diferenciar maiúsculas, ou None."""
    wanted = clean_name(name).lower()
    return next((n for n in names() if n.lower() == wanted), None) if wanted else None


def load(name):
    raw = _read().get(name)
    return ClickerConfig.from_dict(raw) if raw is not None else None


def save(name, cfg):
    """Grava `cfg` em `name`. Retorna False se o nome for vazio ou o disco falhar."""
    name = clean_name(name)
    if not name:
        return False
    profiles = _read()
    profiles[name] = cfg.to_dict()
    return _write(profiles)


def delete(name):
    profiles = _read()
    if name not in profiles:
        return False
    del profiles[name]
    return _write(profiles)
