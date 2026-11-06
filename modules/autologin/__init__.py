"""Login automático: abre o launcher do RF e entra com uma conta (ver launcher.py)."""


class LoginError(Exception):
    """O login não completou; a mensagem é legível para o usuário (nunca contém a senha)."""


class Cancelled(Exception):
    """O usuário cancelou o login em andamento."""
