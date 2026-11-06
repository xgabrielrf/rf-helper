import unittest

from modules.accounts.running import RunningAccounts


class RunningAccountsTest(unittest.TestCase):
    def test_nothing_running_at_first(self):
        r = RunningAccounts()
        self.assertFalse(r.is_running("conta01"))
        self.assertEqual(r.pids_for(""), set())

    def test_account_read_from_the_log_ignores_case(self):
        r = RunningAccounts()
        r.update({10, 11}, {10: "Conta01", 11: "conta02"})
        self.assertEqual(r.pids_for("conta01"), {10})
        self.assertTrue(r.is_running("CONTA02"))
        self.assertFalse(r.is_running("conta03"))

    def test_pid_opened_by_play_counts_even_without_the_log(self):
        r = RunningAccounts()
        r.bind("conta02", 77)
        r.update({77, 5}, {})                    # o log ainda não leu esse client
        self.assertEqual(r.pids_for("conta02"), {77})

    def test_dead_pids_are_forgotten(self):
        r = RunningAccounts()
        r.bind("a", 1)
        r.update({1}, {2: "b"})
        self.assertTrue(r.is_running("a"))
        self.assertFalse(r.is_running("b"), "pid 2 não está vivo")
        r.update(set(), {})
        self.assertFalse(r.is_running("a"))
        r.update({1}, {})                        # o PID voltar a existir não ressuscita a ligação antiga
        self.assertFalse(r.is_running("a"))

    def test_same_account_in_two_clients_returns_both(self):
        r = RunningAccounts()
        r.bind("a", 1)
        r.update({1, 2}, {2: "a"})
        self.assertEqual(r.pids_for("a"), {1, 2})
        self.assertEqual(r.running_logins(), {"a"})

    def test_bound_pid_whose_log_says_another_account_is_a_mismatch(self):
        r = RunningAccounts()
        r.bind("conta02", 5)
        self.assertEqual(r.update({5}, {}), [], "o log ainda não leu: sem desencontro")
        self.assertEqual(r.update({5}, {5: "CONTA02"}), [], "mesma conta (maiúsculas): tudo certo")
        self.assertEqual(r.update({5}, {5: "conta01"}), [(5, "conta02", "conta01")])
        self.assertFalse(r.is_running("conta02"), "a ligação errada foi descartada")
        self.assertTrue(r.is_running("conta01"), "vale o que o log diz")

    def test_unknown_account_lines_are_ignored(self):
        r = RunningAccounts()
        r.update({1}, {1: None})
        self.assertEqual(r.running_logins(), set())


if __name__ == "__main__":
    unittest.main()
