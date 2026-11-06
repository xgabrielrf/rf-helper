"""Servidores e contas em %APPDATA%\\ChangeScreenRF\\servers.json.

Mesma pasta do config.json. Escrita atômica; arquivo ausente ou corrompido vira "sem servidores".
As senhas vão cifradas (DPAPI, ver secrets.py), nunca em texto puro.
"""
import json
import os

from . import secrets
from .model import Account, Character, MAX_CHARACTERS, MAX_DESCRIPTION, Server, clean

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ChangeScreenRF")
STORE_PATH = os.path.join(CONFIG_DIR, "servers.json")


def _account_from(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("login"), str):
        return None
    chars = [Character.from_dict(c) for c in (raw.get("characters") or [])[:MAX_CHARACTERS]]
    token = raw.get("password")
    acc = Account(clean(raw["login"]), secrets.unprotect(token),
                  clean(raw.get("description"), MAX_DESCRIPTION), [c for c in chars if c],
                  id=raw.get("id") if isinstance(raw.get("id"), str) else None)
    if acc.password is None and isinstance(token, str):
        acc.unreadable_token = token        # outro usuário/PC: preserva o que estava no arquivo
    return acc


def _server_from(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
        return None
    index = raw.get("server_index")
    accounts = [_account_from(a) for a in (raw.get("accounts") or [])]
    return Server(clean(raw["name"]), str(raw.get("launcher_path") or ""), str(raw.get("icon_path") or ""),
                  [a for a in accounts if a], id=raw.get("id") if isinstance(raw.get("id"), str) else None,
                  server_index=index if isinstance(index, int) and 0 <= index < 20 else 0)


def load():
    """(servidores, id do último selecionado ou None)."""
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return [], None
    if not isinstance(data, dict) or not isinstance(data.get("servers"), list):
        return [], None
    servers = [s for s in map(_server_from, data["servers"]) if s]
    last = data.get("last_server")
    return servers, last if any(s.id == last for s in servers) else None


def save(servers, last_server=None):
    """Grava tudo. Retorna False se o disco falhar ou alguma senha não puder ser cifrada
    (nesse caso nada é escrito: melhor não salvar do que salvar em texto puro)."""
    out = []
    for server in servers:
        accounts = []
        for acc in server.accounts:
            token = secrets.protect(acc.password) if acc.password else acc.unreadable_token
            if token is None:
                return False
            accounts.append({"id": acc.id, "login": acc.login, "password": token,
                             "description": acc.description,
                             "characters": [c.to_dict() for c in acc.characters]})
        out.append({"id": server.id, "name": server.name, "launcher_path": server.launcher_path,
                    "icon_path": server.icon_path, "server_index": server.server_index,
                    "accounts": accounts})
    try:
        os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
        tmp = STORE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "last_server": last_server, "servers": out}, f, indent=2,
                      ensure_ascii=False)
        os.replace(tmp, STORE_PATH)
        return True
    except OSError:
        return False
