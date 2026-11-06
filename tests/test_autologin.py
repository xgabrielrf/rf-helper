import threading
import unittest

from modules.autologin import Cancelled, LoginError, launcher
from modules.autologin.winapi import FIRST_SERVER_CLICK, LauncherState, Modal


class Clock:
    """Relógio falso: dormir só avança a hora, então os testes não esperam de verdade."""

    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeLauncher:
    """Um launcher falso com a mesma interface de Win32Api: fica pronto depois de BOOT_S, responde ao
    LOGIN depois de ANSWER_S (lista de servidores ou mensagem de erro) e abre o client ao clicar no servidor."""
    BOOT_S, ANSWER_S = 3.0, 2.0
    MAIN, ID_EDIT, PW_EDIT, LOGIN_BTN, LIST, MODAL, OK_BTN = 1, 2, 3, 4, 5, 6, 7

    def __init__(self, clock, login_error=None, needs_double_click=False, always_autofill=False,
                 never_answers=False, startup_modal=False, autofill_once=False, close_delay=0.0):
        self.clock = clock
        self.login_error, self.needs_double_click = login_error, needs_double_click
        self.always_autofill, self.never_answers, self.startup_modal = always_autofill, never_answers, startup_modal
        self.launchers, self.clients = {50}, {7}        # 50 = outro launcher do usuário, já aberto
        self.started_at = self.login_at = None
        self.typed, self.clicks, self.closed_modals = {}, [], 0
        self.window_closed = self.killed = False
        self.error_dismissed = False
        self.client_pid = 77
        self.autofill_once = autofill_once      # o launcher troca o ID digitado pelo ID salvo (do MESMO tamanho)
        self.saved_id = "contaSALVA1"
        self.replace_calls = 0
        self.close_delay = close_delay          # o launcher some tantos segundos depois de o client nascer
        self.client_at = None

    # --- processos
    def pids_named(self, image):
        if image == launcher.LAUNCHER_IMAGE:
            if self.client_at is not None and self.clock.now - self.client_at >= self.close_delay:
                self.launchers.discard(100)
            return set(self.launchers)
        return set(self.clients)

    def start(self, path):
        self.started_at = self.clock.now
        self.launchers.add(100)
        return 100

    def kill(self, pid):
        self.launchers.discard(pid)
        self.killed = True

    # --- janelas
    def state(self, pids):
        if 100 not in pids or self.started_at is None:
            return LauncherState()           # o launcher 50 existe, mas não é nosso: nunca é consultado de fato
        if self.clock.now - self.started_at < self.BOOT_S:
            if self.startup_modal and not self.closed_modals:
                return LauncherState(modals=[Modal(self.MODAL, ("Aviso de abertura",), [self.OK_BTN])])
            return LauncherState()
        st = LauncherState(main=self.MAIN, edits=[self.ID_EDIT, self.PW_EDIT], login_button=self.LOGIN_BTN)
        if self.login_at is not None and not self.never_answers and self.clock.now - self.login_at >= self.ANSWER_S:
            if self.login_error and not self.error_dismissed:
                st.modals = [Modal(self.MODAL, (self.login_error,), [self.OK_BTN])]
            elif not self.login_error:
                st.server_list = self.LIST
        return st

    def replace_text(self, edit, text):
        self.typed[edit] = text
        if edit == self.ID_EDIT:
            self.replace_calls += 1

    def read_text(self, edit):
        if edit == self.ID_EDIT and (self.always_autofill or (self.autofill_once and self.replace_calls == 1)):
            return self.saved_id                # mesmo tamanho do login: só o texto denuncia
        return self.typed.get(edit, "")

    def click_button(self, button):
        assert button == self.LOGIN_BTN
        self.login_at = self.clock.now

    def click_at(self, hwnd, x, y, double=False):
        self.clicks.append((hwnd, x, y, double))
        if hwnd == self.LIST and (double or not self.needs_double_click):
            self.clients.add(self.client_pid)
            self.client_at = self.clock.now

    def close_modal(self, modal):
        self.closed_modals += 1
        self.error_dismissed = True

    def close_window(self, hwnd):
        self.window_closed = True


class LauncherLoginTest(unittest.TestCase):
    def run_login(self, fake=None, login="conta01", password="senha123", cancel=None, **fake_kwargs):
        clock = Clock()
        self.fake = fake or FakeLauncher(clock, **fake_kwargs)
        self.fake.clock = clock
        self.statuses = []
        return launcher.login(r"C:\RF\RF_BrasilRPG.exe", 0, login, password, self.statuses.append,
                              cancel or threading.Event(), api=self.fake, clock=clock.time, sleep=clock.sleep)

    def test_success_returns_the_new_client_and_types_the_credentials(self):
        pid = self.run_login()
        self.assertEqual(pid, 77)
        self.assertEqual(self.fake.typed, {FakeLauncher.ID_EDIT: "conta01", FakeLauncher.PW_EDIT: "senha123"})
        self.assertEqual(self.fake.clicks, [(FakeLauncher.LIST, *FIRST_SERVER_CLICK, False)])
        self.assertFalse(self.fake.window_closed or self.fake.killed, "o launcher some sozinho: não mexe nele")
        self.assertEqual(self.statuses[0], "Abrindo o launcher…")
        self.assertIn("Aguardando o jogo abrir…", self.statuses)

    def test_waits_for_our_launcher_to_close_before_returning(self):
        pid = self.run_login(close_delay=9.0)
        self.assertEqual(pid, 77)
        self.assertNotIn(100, self.fake.launchers)
        self.assertGreaterEqual(self.fake.clock.now - self.fake.client_at, 9.0)
        self.assertIn("Aguardando o launcher fechar…", self.statuses)
        self.assertIn(50, self.fake.launchers, "o launcher do usuário continua aberto e não é esperado")

    def test_cancel_while_waiting_for_the_launcher_to_close_still_returns_the_client(self):
        clock = Clock()
        fake = FakeLauncher(clock, close_delay=30.0)
        cancel = threading.Event()
        original = fake.click_at

        def click_and_cancel(*args, **kwargs):
            original(*args, **kwargs)
            cancel.set()
        fake.click_at = click_and_cancel
        # o cancelamento chega depois do clique no servidor: o client nasce e a espera pelo fechamento é pulada
        with self.assertRaises(Cancelled):
            self.run_login(fake=fake, cancel=cancel)       # cancelado ainda esperando o client: Cancelled
        fake2 = FakeLauncher(Clock(), close_delay=30.0)
        cancel2 = threading.Event()
        original2 = fake2.pids_named

        def cancel_when_waiting(image):
            if fake2.client_at is not None:
                cancel2.set()
            return original2(image)
        fake2.pids_named = cancel_when_waiting
        self.assertEqual(self.run_login(fake=fake2, cancel=cancel2), 77)
        self.assertFalse(fake2.killed or fake2.window_closed)

    def test_other_launchers_and_clients_already_open_are_ignored(self):
        self.run_login()
        self.assertIn(50, self.fake.launchers, "o launcher do usuário não é tocado")
        self.assertIn(7, self.fake.clients)

    def test_wrong_password_reports_it_and_closes_our_launcher(self):
        with self.assertRaises(LoginError) as ctx:
            self.run_login(login_error="Wrong Account input.")
        self.assertEqual(str(ctx.exception), "Login ou senha incorretos.")
        self.assertEqual(self.fake.closed_modals, 1)
        self.assertTrue(self.fake.window_closed and self.fake.killed)
        self.assertIn(50, self.fake.launchers)

    def test_unknown_launcher_message_is_passed_through(self):
        with self.assertRaises(LoginError) as ctx:
            self.run_login(login_error="Server is under maintenance.")
        self.assertIn("Server is under maintenance.", str(ctx.exception))

    def test_cancel_before_login_closes_the_launcher(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            self.run_login(cancel=cancel)
        self.assertTrue(self.fake.killed)

    def test_cancel_after_choosing_the_server_leaves_the_launcher_alone(self):
        clock = Clock()
        fake = FakeLauncher(clock, needs_double_click=True)       # o client demora: dá tempo de cancelar
        cancel = threading.Event()
        original = fake.click_at

        def click_and_cancel(*args, **kwargs):
            original(*args, **kwargs)
            cancel.set()
        fake.click_at = click_and_cancel
        with self.assertRaises(Cancelled):
            self.run_login(fake=fake, cancel=cancel)
        self.assertFalse(fake.killed or fake.window_closed)

    def test_login_with_too_many_letters_never_opens_the_launcher(self):
        clock = Clock()
        fake = FakeLauncher(clock)
        with self.assertRaises(LoginError) as ctx:
            self.run_login(fake=fake, login="a" * 13)
        self.assertIn("12", str(ctx.exception))
        self.assertIsNone(fake.started_at)
        with self.assertRaises(LoginError):
            self.run_login(fake=FakeLauncher(clock), password="x" * 13)
        with self.assertRaises(LoginError):
            self.run_login(fake=FakeLauncher(clock), login="")

    def test_login_field_that_keeps_being_overwritten_is_an_error_and_never_logs_in(self):
        with self.assertRaises(LoginError) as ctx:
            self.run_login(login="contaNOVA001", always_autofill=True)      # 12 letras, igual ao ID salvo
        self.assertIn("ID salvo", str(ctx.exception))
        self.assertIsNone(self.fake.login_at, "nunca clicou em LOGIN com o ID errado")
        self.assertTrue(self.fake.killed)

    def test_saved_id_that_overwrites_the_typed_one_is_retyped_before_login(self):
        self.assertEqual(self.run_login(login="contaNOVA001", autofill_once=True), 77)
        self.assertEqual(self.fake.replace_calls, 2)
        self.assertEqual(self.fake.typed[FakeLauncher.ID_EDIT], "contaNOVA001")

    def test_launcher_that_never_answers_times_out(self):
        with self.assertRaises(LoginError) as ctx:
            self.run_login(never_answers=True)
        self.assertIn("não respondeu", str(ctx.exception))
        self.assertTrue(self.fake.killed)

    def test_single_click_ignored_falls_back_to_double_click(self):
        self.assertEqual(self.run_login(needs_double_click=True), 77)
        self.assertEqual([c[3] for c in self.fake.clicks], [False, True])

    def test_startup_message_is_dismissed(self):
        self.assertEqual(self.run_login(startup_modal=True), 77)
        self.assertEqual(self.fake.closed_modals, 1)

    def test_server_index_other_than_first_is_refused(self):
        clock = Clock()
        with self.assertRaises(LoginError):
            launcher.login("x.exe", 1, "a", "b", lambda t: None, threading.Event(), api=FakeLauncher(clock),
                           clock=clock.time, sleep=clock.sleep)

    def test_translate(self):
        self.assertEqual(launcher.translate(("Wrong Account input.",)), "Login ou senha incorretos.")
        self.assertIn("12", launcher.translate(("Number of letters in password or ID is not appropriate.  Please use 12 letters or less.",)))
        self.assertIn("Login ou senha em branco", launcher.translate(("Please input the password or ID",)))
        self.assertIn("inesperada", launcher.translate(()))


if __name__ == "__main__":
    unittest.main()
