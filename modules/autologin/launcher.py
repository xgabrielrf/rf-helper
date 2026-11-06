"""Login automático: dirige o próprio launcher do RF (sem tocar no jogo nem no protocolo).

Fluxo: abre o launcher → espera a tela de login → digita ID e senha por mensagens de teclado →
LOGIN → espera a lista de servidores → clica no servidor → espera nascer um novo `RF_Online.bin`.
Tudo por mensagens de janela, sem foco e sem mexer no mouse do usuário. Validado à mão com o
launcher do RF Brasil (veja o README, "Como o login automático funciona").

`login()` roda numa thread (modules/home/play.py) e nunca toca no Tk.
"""
import os
import time

from . import Cancelled, LoginError
from .winapi import FIRST_SERVER_CLICK, Win32Api, is_admin, logical_dpi_for_this_thread

CLIENT_IMAGE = "RF_Online.bin"
LAUNCHER_IMAGE = "RF_BrasilRPG.exe"
MAX_CREDENTIAL_LENGTH = 12          # limite do próprio launcher para ID e senha
POLL_S = 0.25

READY_TIMEOUT_S = 240               # o launcher pode estar baixando um patch
TYPE_ATTEMPTS = 4
VERIFY_PAUSE_S = 0.8                # espera antes de reler o campo (o ID salvo chega com atraso)
SETTLE_TIMEOUT_S = 30               # a tela de login pode piscar (janela "conectando") logo depois de pronta
LIST_TIMEOUT_S = 45                 # do clique em LOGIN até a lista de servidores
CLIENT_TIMEOUT_S = 60               # do clique no servidor até o novo RF_Online.bin
LAUNCHER_CLOSE_TIMEOUT_S = 60      # depois do client aberto, até o launcher fechar sozinho (~10 s)
DOUBLE_CLICK_AFTER_S = 15           # se um clique simples não bastar, tenta o duplo (não foi preciso no RF Brasil)

# Mensagens do launcher (em inglês) → texto para o usuário. Mensagens desconhecidas são repassadas como vieram.
KNOWN_MESSAGES = (
    ("wrong account", "Login ou senha incorretos."),
    ("please input the password or id", "Login ou senha em branco."),
    ("not appropriate", f"Login e senha precisam ter no máximo {MAX_CREDENTIAL_LENGTH} letras."),
)


def translate(texts):
    joined = " ".join(texts)
    for needle, message in KNOWN_MESSAGES:
        if needle in joined.lower():
            return message
    return f"O launcher respondeu: {joined}" if joined else "O launcher abriu uma mensagem inesperada."


def check_credentials(login, password):
    if not login or not password:
        raise LoginError("Login ou senha em branco.")
    if len(login) > MAX_CREDENTIAL_LENGTH or len(password) > MAX_CREDENTIAL_LENGTH:
        raise LoginError(f"O launcher só aceita login e senha com até {MAX_CREDENTIAL_LENGTH} letras.")


def login(launcher_path, server_index, login, password, on_status, cancel, api=None, clock=time.monotonic,
          sleep=time.sleep):
    """Entra com a conta e devolve o PID do novo RF_Online.bin. Levanta LoginError/Cancelled.

    `api`, `clock` e `sleep` existem para os testes (um launcher falso, sem esperar de verdade)."""
    check_credentials(login, password)
    server_index = server_index or 0
    if server_index != 0:
        raise LoginError("Por enquanto só o primeiro servidor da lista do launcher é suportado.")
    if api is None:
        if not os.path.isfile(launcher_path):
            raise LoginError("O launcher não foi encontrado: confira o caminho do servidor.")
        if not is_admin():
            raise LoginError("Abra o RF Helper como administrador para usar o Play (o launcher roda elevado).")
        logical_dpi_for_this_thread()
        api = Win32Api()

    def check():
        if cancel.is_set():
            raise Cancelled()

    def wait_until(predicate, timeout, what):
        end = clock() + timeout
        while True:
            check()
            value = predicate()
            if value:
                return value
            if clock() >= end:
                raise LoginError(what)
            sleep(POLL_S)

    clients_before = api.pids_named(CLIENT_IMAGE)
    launchers_before = api.pids_named(LAUNCHER_IMAGE)
    on_status("Abrindo o launcher…")
    api.start(launcher_path)
    ours = lambda: api.pids_named(LAUNCHER_IMAGE) - launchers_before       # inclui um relançamento após patch
    started = False
    try:
        def ready():
            pids = ours()
            if not pids:
                return None
            state = api.state(pids)
            for modal in state.modals:                     # aviso do launcher na abertura: fecha e segue
                api.close_modal(modal)
            return state if state.login_ready else None
        state = wait_until(ready, READY_TIMEOUT_S, "O launcher não chegou à tela de login.")
        sleep(1.0)                                         # deixa o launcher assentar
        state = wait_until(ready, SETTLE_TIMEOUT_S, "A tela de login do launcher mudou antes de digitar.")

        on_status("Digitando login e senha…")
        id_edit, password_edit = state.edits[0], state.edits[1]
        # O launcher preenche o ÚLTIMO ID SALVO ("ID SAVE") com atraso e pode sobrescrever o que digitamos
        # (com um ID do mesmo tamanho!). Por isso o que vale é o TEXTO do campo, lido de volta: só segue
        # quando ele é exatamente o login pedido e continua assim depois de uma pausa.
        for attempt in range(TYPE_ATTEMPTS):
            api.replace_text(id_edit, login)
            api.replace_text(password_edit, password)
            sleep(VERIFY_PAUSE_S)
            if api.read_text(id_edit) == login:
                sleep(VERIFY_PAUSE_S)
                if api.read_text(id_edit) == login:
                    break
            check()
            sleep(0.7)
        else:
            raise LoginError("O launcher alterou o campo de login (ID salvo). Tente de novo.")
        check()

        on_status("Entrando…")
        api.click_button(state.login_button)

        def after_login():
            st = api.state(ours()) if ours() else None
            if st is None:
                return None
            for modal in st.modals:
                if modal.texts:
                    return ("error", modal)
            return ("list", st) if st.server_list else None
        kind, found = wait_until(after_login, LIST_TIMEOUT_S, "O launcher não respondeu ao login (servidor fora do ar?).")
        if kind == "error":
            message = translate(found.texts)
            api.close_modal(found)
            raise LoginError(message)

        sleep(1.0)                                         # a lista precisa terminar de desenhar
        on_status("Escolhendo o servidor…")
        x, y = FIRST_SERVER_CLICK
        api.click_at(found.server_list, x, y)
        started = True
        click_time = clock()
        doubled = False

        def new_client():
            nonlocal doubled
            fresh = api.pids_named(CLIENT_IMAGE) - clients_before
            if fresh:
                return fresh
            if not doubled and clock() - click_time > DOUBLE_CLICK_AFTER_S:
                st = api.state(ours()) if ours() else None
                if st is not None and st.server_list:
                    doubled = True
                    api.click_at(st.server_list, x, y, double=True)
            return None
        on_status("Aguardando o jogo abrir…")
        fresh = wait_until(new_client, CLIENT_TIMEOUT_S, "O jogo não abriu depois de escolher o servidor.")
        # O launcher fecha sozinho alguns segundos depois. Só devolvemos depois disso: é o que faz a fila de
        # várias contas logar uma por vez. Cancelar aqui só para de esperar (o client já abriu).
        on_status("Aguardando o launcher fechar…")
        end = clock() + LAUNCHER_CLOSE_TIMEOUT_S
        while ours() and clock() < end and not cancel.is_set():
            sleep(POLL_S)
        return min(fresh)
    except (LoginError, Cancelled):
        if not started:
            _close_launcher(api, ours, sleep)
        raise


def _close_launcher(api, ours, sleep):
    """Fecha o launcher que abrimos (ele não deve ficar aberto depois de um erro ou cancelamento)."""
    pids = ours()
    if not pids:
        return
    for hwnd in [api.state(pids).main]:
        if hwnd:
            api.close_window(hwnd)
    sleep(1.0)
    for pid in ours():
        api.kill(pid)
