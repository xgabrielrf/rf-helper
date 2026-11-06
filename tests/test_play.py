import threading
import time
import unittest

from modules.accounts.model import Account, Server
from modules.autologin import Cancelled, LoginError
from modules.home.play import QUEUED, RUNNING, PlayController


def wait_for(controller, kinds, timeout=3.0):
    """Junta eventos até ver todos os `kinds` (conjunto de (account_id, kind))."""
    seen, end = [], time.time() + timeout
    while time.time() < end:
        seen += controller.drain()
        if kinds <= {(e.account_id, e.kind) for e in seen}:
            return seen
        time.sleep(0.01)
    raise AssertionError(f"faltou {kinds - {(e.account_id, e.kind) for e in seen}}; vi {seen}")


class PlayTest(unittest.TestCase):
    def setUp(self):
        self.server = Server("S", r"C:\x\L.exe")
        self.a = Account("a", "senha-a", id="A")
        self.b = Account("b", "senha-b", id="B")
        self.calls, self.gate = [], threading.Event()

    def controller(self, fn):
        c = PlayController(fn)
        self.addCleanup(c.shutdown)
        return c

    def test_runs_one_at_a_time_in_order_and_reports_done(self):
        def fn(path, index, login, password, on_status, cancel):
            self.calls.append((login, password, path))
            on_status("etapa")
            self.gate.wait(2)
        c = self.controller(fn)
        self.assertTrue(c.start(self.server, self.a))
        self.assertTrue(c.start(self.server, self.b))
        self.assertFalse(c.start(self.server, self.a), "já está na fila")
        self.assertEqual(c.state("B")[0], QUEUED)
        wait_for(c, {("A", "status")})
        self.assertEqual(c.state("A"), (RUNNING, "etapa"))
        self.assertEqual(c.state("B")[0], QUEUED)
        self.assertEqual(len(self.calls), 1)
        self.gate.set()
        wait_for(c, {("A", "done"), ("B", "done")})
        self.assertEqual([x[0] for x in self.calls], ["a", "b"])
        self.assertEqual(self.calls[0][1:], ("senha-a", r"C:\x\L.exe"))
        self.assertFalse(c.busy())

    def test_errors_are_reported_and_do_not_stop_the_queue(self):
        def fn(path, index, login, password, on_status, cancel):
            if login == "a":
                raise LoginError("Senha incorreta.")
            if login == "b":
                raise ValueError("segredo: " + password)
        c = self.controller(fn)
        c.start(self.server, self.a)
        c.start(self.server, self.b)
        c.start(self.server, Account("c", "pw", id="C"))
        events = wait_for(c, {("A", "error"), ("B", "error"), ("C", "done")})
        texts = {e.account_id: e.text for e in events if e.kind == "error"}
        self.assertEqual(texts["A"], "Senha incorreta.")
        self.assertNotIn("senha-b", texts["B"])         # exceção inesperada nunca vaza a senha
        self.assertIn("ValueError", texts["B"])

    def test_cancel_while_queued_is_immediate_and_skips_the_job(self):
        def fn(path, index, login, password, on_status, cancel):
            self.calls.append(login)
            self.gate.wait(2)
        c = self.controller(fn)
        c.start(self.server, self.a)
        c.start(self.server, self.b)
        wait_for(c, {("A", "status")})
        c.cancel("B")
        self.assertIsNone(c.state("B"))
        self.gate.set()
        wait_for(c, {("A", "done")})
        time.sleep(0.1)
        self.assertEqual(self.calls, ["a"])

    def test_cancel_while_running(self):
        def fn(path, index, login, password, on_status, cancel):
            on_status("esperando")
            while not cancel.is_set():
                time.sleep(0.005)
            raise Cancelled()
        c = self.controller(fn)
        c.start(self.server, self.a)
        wait_for(c, {("A", "status")})
        c.cancel("A")
        wait_for(c, {("A", "cancelled")})
        self.assertIsNone(c.state("A"))
        self.assertTrue(c.start(self.server, self.a), "pode tentar de novo")

    def test_start_many_runs_in_the_order_given_and_reports_the_pid(self):
        def fn(path, index, login, password, on_status, cancel):
            self.calls.append(login)
            return {"c": 301, "a": 101, "b": 201}[login]
        c = self.controller(fn)
        accounts = [Account("c", "x", id="C"), Account("a", "x", id="A"), Account("b", "x", id="B")]
        self.assertEqual(c.start_many(self.server, accounts), ["C", "A", "B"])
        events = wait_for(c, {("C", "done"), ("A", "done"), ("B", "done")})
        self.assertEqual(self.calls, ["c", "a", "b"])
        self.assertEqual({e.account_id: e.value for e in events if e.kind == "done"}, {"C": 301, "A": 101, "B": 201})

    def test_start_many_ignores_accounts_already_queued(self):
        c = self.controller(lambda *a: self.gate.wait(2))
        c.start(self.server, self.a)
        self.assertEqual(c.start_many(self.server, [self.a, self.b]), ["B"])
        self.gate.set()

    def test_account_that_got_into_the_game_while_waiting_is_skipped(self):
        in_game = set()

        def fn(path, index, login, password, on_status, cancel):
            self.calls.append(login)
            in_game.add("B")                     # enquanto A loga, a conta B é aberta por fora
        c = self.controller(fn)
        c.should_skip = lambda account_id: account_id in in_game
        c.start_many(self.server, [self.a, self.b, Account("c", "x", id="C")])
        events = wait_for(c, {("A", "done"), ("B", "skipped"), ("C", "done")})
        self.assertEqual(self.calls, ["a", "c"])
        self.assertEqual([e.text for e in events if e.kind == "skipped"], ["Já está em jogo."])

    def test_cancel_all_clears_the_queue_and_stops_the_running_one(self):
        def fn(path, index, login, password, on_status, cancel):
            self.calls.append(login)
            while not cancel.is_set():
                time.sleep(0.005)
            raise Cancelled()
        c = self.controller(fn)
        c.start_many(self.server, [self.a, self.b])
        wait_for(c, {("A", "status")})
        c.cancel_all()
        self.assertIsNone(c.state("B"), "o da fila sai na hora")
        wait_for(c, {("A", "cancelled")})
        self.assertEqual(self.calls, ["a"])
        self.assertFalse(c.busy())

    def test_account_without_password_does_not_start(self):
        c = self.controller(lambda *a: None)
        self.assertFalse(c.start(self.server, Account("x", None, id="X")))
        self.assertFalse(c.busy())


if __name__ == "__main__":
    unittest.main()
