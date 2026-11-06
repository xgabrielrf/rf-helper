import os
import tempfile
import unittest

from modules.clicker import profiles
from modules.clicker.model import MODE_MACRO, ClickerConfig, KeyRow, Macro, key_event


class ProfilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old = profiles.PROFILES_PATH
        profiles.PROFILES_PATH = os.path.join(self.tmp.name, "sub", "profiles.json")
        self.addCleanup(setattr, profiles, "PROFILES_PATH", self._old)

    def test_missing_file_is_empty(self):
        self.assertEqual(profiles.names(), [])
        self.assertIsNone(profiles.load("nada"))

    def test_save_load_delete(self):
        cfg = ClickerConfig(mode=MODE_MACRO, keys=[KeyRow(0x58, "X", 200)],
                            macro=Macro([key_event(0x41, "A")], loop=False))
        self.assertTrue(profiles.save("Farm", cfg))
        self.assertTrue(profiles.save("heal", ClickerConfig()))
        self.assertEqual(profiles.names(), ["Farm", "heal"])
        self.assertEqual(profiles.load("Farm").to_dict(), cfg.to_dict())
        self.assertTrue(profiles.delete("Farm"))
        self.assertFalse(profiles.delete("Farm"))
        self.assertEqual(profiles.names(), ["heal"])

    def test_overwrite_and_name_cleanup(self):
        profiles.save("  a   b  ", ClickerConfig())
        self.assertEqual(profiles.names(), ["a b"])
        self.assertFalse(profiles.save("   ", ClickerConfig()))
        self.assertEqual(len(profiles.clean_name("x" * 100)), profiles.MAX_NAME)

    def test_find_ignores_case_and_returns_the_stored_name(self):
        profiles.save("Guerreiro", ClickerConfig())
        self.assertEqual(profiles.find("guerreiro"), "Guerreiro")
        self.assertEqual(profiles.find("  GUERREIRO "), "Guerreiro")
        self.assertIsNone(profiles.find("iGuerreiro"))
        self.assertIsNone(profiles.find(""))
        self.assertIsNone(profiles.find(None))

    def test_corrupted_file_is_tolerated(self):
        os.makedirs(os.path.dirname(profiles.PROFILES_PATH))
        for content in ("{nao e json", "[]", '{"profiles": 3}', '{"profiles": {"a": 1, "b": {}}}'):
            with open(profiles.PROFILES_PATH, "w", encoding="utf-8") as f:
                f.write(content)
            names = profiles.names()
            self.assertIsInstance(names, list)
        self.assertEqual(profiles.names(), ["b"])
        self.assertFalse(profiles.load("b").is_configured())


if __name__ == "__main__":
    unittest.main()
