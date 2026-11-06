"""Servidores, contas e personagens (sem Tk, sem disco: ver store.py).

Um servidor aponta para o launcher do jogo; cada conta tem login/senha e até 3 personagens
(o RF tem 3 slots por conta, de qualquer raça/classe).
"""
import os
import uuid

MAX_CHARACTERS = 3
MAX_TEXT = 60               # nomes, login
MAX_DESCRIPTION = 300
MAX_CREDENTIAL = 12         # o launcher do RF recusa ID ou senha com mais de 12 letras

# Raça -> (nome mostrado, cor). Chaves são o que vai para o disco.
RACES = {
    "bellato": ("Bellato", "#e86aa6"),      # rosa
    "cora": ("Cora", "#9b59d0"),            # roxo
    "accretia": ("Accretia", "#f2f2f2"),    # branco
}

# TODO: trocar por todas as classes do jogo, separadas por raça (hoje só o papel no grupo).
# Quando isso virar `{raça: [classes]}`, só este lugar e o formulário de conta precisam mudar.
CLASSES = ["Tanker", "DPS", "Suporte"]

CLIENT_NAME = "RF_Online.bin"


def new_id():
    return uuid.uuid4().hex[:12]


def race_label(race):
    return RACES[race][0] if race in RACES else ""


def race_color(race):
    return RACES[race][1] if race in RACES else "#888888"


def _text(value, limit=MAX_TEXT):
    return " ".join(str(value or "").split())[:limit]


class Character:
    def __init__(self, name="", race="", cls=""):
        self.name, self.race, self.cls = name, race, cls

    def is_complete(self):
        return bool(self.name.strip()) and self.race in RACES and self.cls in CLASSES

    def to_dict(self):
        return {"name": self.name, "race": self.race, "class": self.cls}

    @classmethod
    def from_dict(cls, raw):
        if not isinstance(raw, dict):
            return None
        char = cls(_text(raw.get("name")), raw.get("race") if raw.get("race") in RACES else "",
                   raw.get("class") if raw.get("class") in CLASSES else "")
        return char if char.name else None


class Account:
    def __init__(self, login="", password=None, description="", characters=None, id=None):
        self.id = id or new_id()
        self.login = login
        self.password = password        # None = não foi possível ler (outro usuário/PC): pedir de novo
        self.description = description
        self.characters = list(characters or [])
        self.unreadable_token = ""      # senha cifrada que este usuário não consegue abrir (ver store.py)

    def error(self):
        """Mensagem do primeiro problema que impede salvar, ou None."""
        if not self.login.strip():
            return "Informe o login."
        if not self.password:
            return "Informe a senha."
        if len(self.login.strip()) > MAX_CREDENTIAL or len(self.password) > MAX_CREDENTIAL:
            return f"Login e senha podem ter no máximo {MAX_CREDENTIAL} letras (limite do launcher do RF)."
        if len(self.characters) > MAX_CHARACTERS:
            return f"No máximo {MAX_CHARACTERS} personagens por conta."
        for char in self.characters:
            if not char.is_complete():
                return "Preencha nome, raça e classe de cada personagem (ou remova o que não for usar)."
        return None


class Server:
    def __init__(self, name="", launcher_path="", icon_path="", accounts=None, id=None, server_index=0):
        self.id = id or new_id()
        self.name = name
        self.launcher_path = launcher_path
        self.icon_path = icon_path
        self.server_index = server_index    # qual linha da lista do launcher escolher após o login
        self.accounts = list(accounts or [])

    def error(self):
        if not self.name.strip():
            return "Informe o nome do servidor."
        if not self.launcher_path.strip():
            return "Informe o caminho do launcher."
        return None

    def warning(self):
        """Aviso (não bloqueia) sobre o caminho do launcher, ou None."""
        path = self.launcher_path.strip()
        if not os.path.isfile(path):
            return "O arquivo do launcher não foi encontrado nesse caminho."
        if not os.path.isfile(os.path.join(os.path.dirname(path), CLIENT_NAME)):
            return f"Não achei {CLIENT_NAME} na mesma pasta do launcher: confira se é o launcher certo."
        return None

    @property
    def folder(self):
        return os.path.dirname(self.launcher_path.strip())

    def find_account(self, account_id):
        return next((a for a in self.accounts if a.id == account_id), None)


def clean(value, limit=MAX_TEXT):
    return _text(value, limit)
