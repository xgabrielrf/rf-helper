"""Persistência das configurações em %APPDATA%\\ChangeScreenRF\\config.json."""
import copy
import json
import os
import re

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ChangeScreenRF")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "enabled": True,
    "auto_profile": False,      # carregar sozinho o perfil do clicker com o nome do personagem
    "hotkeys": {"next": None, "prev": None, "last": None},
    "position": None,
    # Onde ficam as outras janelas ('+x+y'): atalhos, tela do clicker, tela da macro e os formulários da tela
    # inicial. A tela inicial não está aqui: ela sempre abre no meio da tela.
    "windows": {"settings": None, "clicker": None, "macro": None, "server_dialog": None, "account_dialog": None},
}
POSITION_RE = re.compile(r"^[+-]\d+[+-]\d+$")


def load():
    cfg = copy.deepcopy(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return cfg
    if not isinstance(data, dict):
        return cfg
    for flag in ("enabled", "auto_profile"):
        if isinstance(data.get(flag), bool):
            cfg[flag] = data[flag]
    if isinstance(data.get("position"), str) and POSITION_RE.match(data["position"]):
        cfg["position"] = data["position"]
    if isinstance(data.get("windows"), dict):
        for name in cfg["windows"]:
            value = data["windows"].get(name)
            if isinstance(value, str) and POSITION_RE.match(value):
                cfg["windows"][name] = value
    if isinstance(data.get("hotkeys"), dict):
        for action in cfg["hotkeys"]:
            cfg["hotkeys"][action] = data["hotkeys"].get(action)
    return cfg


def save(cfg):
    """Escrita atômica (arquivo temporário + replace). Erros de disco são ignorados."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)
    except OSError:
        pass
