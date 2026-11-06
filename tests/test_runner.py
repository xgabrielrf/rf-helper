import queue
import statistics
import time
import unittest

from modules.clicker import runner as runner_mod
from modules.clicker.model import (MODE_MACRO, ClickerConfig, KeyRow, Macro, delay_event,
                                   key_event)
from modules.clicker.runner import Runner
from tests.fake_window import FakeWindow

SEQUENCE = ["ACTIVATE", "KEYDOWN", "KEYUP", "NCACTIVATE"]


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.win = FakeWindow()
        self.addCleanup(self.win.close)
        self.exits = queue.Queue()

    def make(self, cfg):
        return Runner(self.win.hwnd, cfg, lambda r, reason: self.exits.put(reason))

    def wait_exit(self, timeout=3.0):
        return self.exits.get(timeout=timeout)

    def test_click_independent_periods_without_drift(self):
        cfg = ClickerConfig(keys=[KeyRow(0x70, "F1", 100), KeyRow(0x71, "F2", 150)])
        r = self.make(cfg)
        r.start()
        time.sleep(1.0)
        r.stop()
        self.assertEqual(self.wait_exit(), runner_mod.STOPPED)

        f1, f2 = self.win.keydowns(0x70), self.win.keydowns(0x71)
        self.assertTrue(10 <= len(f1) <= 11, len(f1))
        self.assertTrue(6 <= len(f2) <= 7, len(f2))
        gaps = [b - a for a, b in zip(f1, f1[1:])]
        self.assertAlmostEqual(statistics.median(gaps), 0.100, delta=0.015)
        self.assertAlmostEqual(f1[-1] - f1[0], (len(f1) - 1) * 0.100, delta=0.04)   # sem deriva

    def test_each_press_is_an_uninterrupted_sequence(self):
        cfg = ClickerConfig(keys=[KeyRow(0x70, "F1", 10), KeyRow(0x71, "F2", 10),
                                  KeyRow(0x72, "F3", 10)])
        r = self.make(cfg)
        r.start()
        time.sleep(0.4)
        r.stop()
        self.wait_exit()
        names = [n for _, n, _ in self.win.snapshot()]
        self.assertGreater(len(names), 40)
        self.assertEqual(len(names) % 4, 0)
        for i in range(0, len(names), 4):
            self.assertEqual(names[i:i + 4], SEQUENCE)

    def test_stop_is_immediate_even_with_long_period(self):
        r = self.make(ClickerConfig(keys=[KeyRow(0x70, "F1", 600_000)]))
        r.start()
        time.sleep(0.1)
        t0 = time.perf_counter()
        r.stop()
        self.assertEqual(self.wait_exit(), runner_mod.STOPPED)
        self.assertLess(time.perf_counter() - t0, 0.1)
        self.assertEqual(len(self.win.keydowns(0x70)), 1)       # a 1ª tecla sai logo ao ligar

    def test_macro_without_loop_runs_once_and_finishes(self):
        macro = Macro([key_event(0x41, "A"), delay_event(100), key_event(0x42, "B"),
                       delay_event(100)], loop=False)
        r = self.make(ClickerConfig(mode=MODE_MACRO, macro=macro))
        r.start()
        self.assertEqual(self.wait_exit(), runner_mod.FINISHED)
        a, b = self.win.keydowns(0x41), self.win.keydowns(0x42)
        self.assertEqual((len(a), len(b)), (1, 1))
        self.assertAlmostEqual(b[0] - a[0], 0.100, delta=0.03)

    def test_macro_loop_repeats_until_stopped(self):
        macro = Macro([key_event(0x41, "A"), delay_event(50)], loop=True)
        r = self.make(ClickerConfig(mode=MODE_MACRO, macro=macro))
        r.start()
        time.sleep(0.5)
        r.stop()
        self.assertEqual(self.wait_exit(), runner_mod.STOPPED)
        self.assertTrue(8 <= len(self.win.keydowns(0x41)) <= 11)

    def test_macro_loop_without_delays_does_not_flood(self):
        macro = Macro([key_event(0x41, "A")], loop=True)
        r = self.make(ClickerConfig(mode=MODE_MACRO, macro=macro))
        r.start()
        time.sleep(0.3)
        r.stop()
        self.wait_exit()
        self.assertLess(len(self.win.keydowns(0x41)), 40)

    def test_stops_by_itself_when_window_closes(self):
        r = self.make(ClickerConfig(keys=[KeyRow(0x70, "F1", 20)]))
        r.start()
        time.sleep(0.1)
        self.win.close()
        self.assertEqual(self.wait_exit(), runner_mod.WINDOW_CLOSED)

    def test_timer_resolution_is_released(self):
        r = self.make(ClickerConfig(keys=[KeyRow(0x70, "F1", 50)]))
        r.start()
        time.sleep(0.1)
        r.stop()
        self.wait_exit()
        self.assertEqual(runner_mod._timer_users, 0)


if __name__ == "__main__":
    unittest.main()
