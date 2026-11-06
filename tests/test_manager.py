import os
import tempfile
import time
import unittest

from modules.clicker import profiles
from modules.clicker.manager import OFF, ON, UNSET, ClickerManager
from modules.clicker.model import (MODE_MACRO, ClickerConfig, KeyRow, Macro, delay_event,
                                   key_event)
from tests.fake_window import FakeWindow


class ManagerTest(unittest.TestCase):
    def setUp(self):
        self.win = FakeWindow()
        self.addCleanup(self.win.close)
        self.changes, self.messages = [], []
        self.mgr = ClickerManager(on_change=self.changes.append, on_message=self.messages.append)
        self.addCleanup(self.mgr.stop_all)
        self.hwnd = self.win.hwnd

    def configure_click(self, ms=20):
        self.mgr.session(self.hwnd).cfg.keys = [KeyRow(0x70, "F1", ms)]

    def wait_until(self, cond, timeout=2.0):
        end = time.time() + timeout
        while time.time() < end:
            self.mgr.poll()
            if cond():
                return True
            time.sleep(0.01)
        return False

    def test_state_cycle_gray_red_green(self):
        self.assertEqual(self.mgr.state(self.hwnd), UNSET)
        self.mgr.toggle(self.hwnd)                       # cinza não liga
        self.assertEqual(self.mgr.state(self.hwnd), UNSET)
        self.assertEqual(len(self.messages), 1)

        self.configure_click()
        self.assertEqual(self.mgr.state(self.hwnd), OFF)
        self.mgr.toggle(self.hwnd)
        self.assertEqual(self.mgr.state(self.hwnd), ON)
        self.assertTrue(self.wait_until(lambda: len(self.win.keydowns(0x70)) >= 3))
        self.mgr.toggle(self.hwnd)
        self.assertEqual(self.mgr.state(self.hwnd), OFF)
        n = len(self.win.keydowns())
        time.sleep(0.1)
        self.assertLessEqual(len(self.win.keydowns()), n + 1)   # no máx. a tecla em curso

    def test_macro_without_loop_goes_back_to_red(self):
        s = self.mgr.session(self.hwnd)
        s.cfg.mode = MODE_MACRO
        s.cfg.macro = Macro([key_event(0x41, "A"), delay_event(50)], loop=False)
        self.mgr.toggle(self.hwnd)
        self.assertTrue(self.wait_until(lambda: self.mgr.state(self.hwnd) == OFF))
        self.assertEqual(len(self.win.keydowns(0x41)), 1)
        self.assertIn(self.hwnd, self.changes)

    def test_editing_restarts_runner_and_emptying_turns_gray(self):
        self.configure_click()
        self.mgr.toggle(self.hwnd)
        self.mgr.session(self.hwnd).cfg.keys = [KeyRow(0x71, "F2", 20)]
        self.mgr.config_changed(self.hwnd)
        self.assertEqual(self.mgr.state(self.hwnd), ON)
        self.assertTrue(self.wait_until(lambda: len(self.win.keydowns(0x71)) >= 2))

        self.mgr.session(self.hwnd).cfg.keys = [KeyRow()]
        self.mgr.config_changed(self.hwnd)
        self.assertEqual(self.mgr.state(self.hwnd), UNSET)
        n = len(self.win.keydowns())
        time.sleep(0.1)
        self.assertEqual(len(self.win.keydowns()), n)

    def test_window_closing_ends_runner_and_forget_clears_session(self):
        self.configure_click()
        self.mgr.toggle(self.hwnd)
        self.win.close()
        self.assertTrue(self.wait_until(lambda: self.mgr.state(self.hwnd) != ON))
        self.mgr.forget(self.hwnd)
        self.assertEqual(self.mgr.state(self.hwnd), UNSET)

    def test_stale_exit_of_replaced_runner_is_ignored(self):
        self.configure_click()
        self.mgr.toggle(self.hwnd)
        self.mgr.config_changed(self.hwnd)               # troca o runner
        time.sleep(0.1)
        self.mgr.poll()                                  # processa o término do antigo
        self.assertEqual(self.mgr.state(self.hwnd), ON)


class CharacterChangedTest(unittest.TestCase):
    def setUp(self):
        self.win = FakeWindow()
        self.addCleanup(self.win.close)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        old = profiles.PROFILES_PATH
        profiles.PROFILES_PATH = os.path.join(self.tmp.name, "profiles.json")
        self.addCleanup(setattr, profiles, "PROFILES_PATH", old)
        self.messages = []
        self.mgr = ClickerManager(on_message=self.messages.append)
        self.addCleanup(self.mgr.stop_all)
        self.hwnd = self.win.hwnd
        profiles.save("Guerreiro", ClickerConfig(keys=[KeyRow(0x58, "X", 40)]))

    def test_auto_profile_off_never_loads(self):
        self.mgr.character_changed(self.hwnd, "Guerreiro")
        self.assertFalse(self.mgr.session(self.hwnd).cfg.is_configured())
        self.assertEqual(self.messages, [])

    def test_auto_profile_on_loads_the_profile_with_the_character_name_without_starting(self):
        self.mgr.auto_profile = True
        self.mgr.character_changed(self.hwnd, "guerreiro")            # sem diferenciar maiúsculas
        cfg = self.mgr.session(self.hwnd).cfg
        self.assertEqual([(r.vk, r.ms) for r in cfg.keys], [(0x58, 40)])
        self.assertEqual(self.mgr.state(self.hwnd), OFF)             # vermelho: o clicker não liga sozinho
        self.assertEqual(self.messages, ["Perfil 'Guerreiro' carregado."])
        time.sleep(0.1)
        self.assertEqual(self.win.keydowns(), [])

    def test_auto_profile_remembers_which_profile_is_loaded(self):
        self.mgr.auto_profile = True
        self.mgr.character_changed(self.hwnd, "guerreiro")
        self.assertEqual(self.mgr.session(self.hwnd).profile, "Guerreiro")     # nome salvo, não o digitado

    def test_character_without_profile_keeps_current_config(self):
        self.mgr.auto_profile = True
        self.mgr.session(self.hwnd).cfg.keys = [KeyRow(0x70, "F1", 50)]
        self.mgr.character_changed(self.hwnd, "Outro")
        self.assertEqual(self.mgr.session(self.hwnd).cfg.keys[0].vk, 0x70)
        self.assertEqual(self.messages, [])

    def test_back_to_character_select_stops_a_running_clicker(self):
        self.mgr.session(self.hwnd).cfg.keys = [KeyRow(0x70, "F1", 20)]
        self.mgr.character_changed(self.hwnd, "Guerreiro")
        self.mgr.toggle(self.hwnd)
        self.assertEqual(self.mgr.state(self.hwnd), ON)
        self.mgr.character_changed(self.hwnd, None)
        self.assertEqual(self.mgr.state(self.hwnd), OFF)
        self.assertEqual(len(self.messages), 1)
        self.assertIn("seleção", self.messages[0])

    def test_character_select_with_nothing_running_is_silent(self):
        self.mgr.character_changed(self.hwnd, "Guerreiro")
        self.mgr.character_changed(self.hwnd, None)
        self.assertEqual(self.messages, [])

    def test_repeating_the_same_character_does_nothing(self):
        self.mgr.auto_profile = True
        self.mgr.character_changed(self.hwnd, "Guerreiro")
        self.mgr.session(self.hwnd).cfg.keys = [KeyRow(0x70, "F1", 50)]    # edição manual depois
        self.mgr.character_changed(self.hwnd, "Guerreiro")
        self.assertEqual(self.mgr.session(self.hwnd).cfg.keys[0].vk, 0x70)
        self.assertEqual(len(self.messages), 1)

    def test_switching_character_loads_the_new_profile(self):
        profiles.save("iGuerreiro", ClickerConfig(keys=[KeyRow(0x31, "1", 90)]))
        self.mgr.auto_profile = True
        self.mgr.character_changed(self.hwnd, "Guerreiro")
        self.mgr.character_changed(self.hwnd, None)
        self.mgr.character_changed(self.hwnd, "iGuerreiro")
        self.assertEqual(self.mgr.session(self.hwnd).cfg.keys[0].vk, 0x31)


if __name__ == "__main__":
    unittest.main()
