import json
import os
import tempfile
import unittest

from modules.change_screen import config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        old = (config.CONFIG_DIR, config.CONFIG_PATH)
        config.CONFIG_DIR = self.tmp.name
        config.CONFIG_PATH = os.path.join(self.tmp.name, "config.json")
        self.addCleanup(lambda: (setattr(config, "CONFIG_DIR", old[0]), setattr(config, "CONFIG_PATH", old[1])))

    def write(self, data):
        with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def test_defaults_when_missing(self):
        cfg = config.load()
        self.assertTrue(cfg["enabled"])
        self.assertFalse(cfg["auto_profile"])

    def test_auto_profile_roundtrip(self):
        cfg = config.load()
        cfg["auto_profile"] = True
        config.save(cfg)
        self.assertTrue(config.load()["auto_profile"])

    def test_old_file_without_auto_profile_keeps_working(self):
        self.write({"enabled": False, "hotkeys": {"next": None}, "position": "+1+2"})
        cfg = config.load()
        self.assertFalse(cfg["enabled"])
        self.assertFalse(cfg["auto_profile"])
        self.assertEqual(cfg["position"], "+1+2")

    def test_window_positions_roundtrip_and_ignore_garbage(self):
        cfg = config.load()
        self.assertEqual(cfg["windows"], {"settings": None, "clicker": None, "macro": None, "server_dialog": None, "account_dialog": None})
        cfg["windows"]["clicker"] = "+120+80"
        cfg["windows"]["macro"] = "-1900+40"                 # monitor à esquerda
        config.save(cfg)
        loaded = config.load()["windows"]
        self.assertEqual((loaded["clicker"], loaded["macro"], loaded["settings"]),
                         ("+120+80", "-1900+40", None))
        self.write({"windows": {"settings": "100x200", "clicker": 5, "macro": "+1+2", "outra": "+3+4"}})
        loaded = config.load()["windows"]
        self.assertEqual(loaded, {"settings": None, "clicker": None, "macro": "+1+2", "server_dialog": None, "account_dialog": None})
        self.write({"windows": "lixo"})
        self.assertEqual(config.load()["windows"]["macro"], None)

    def test_bad_main_window_position_is_ignored(self):
        self.write({"position": "200x300+10+10"})
        self.assertIsNone(config.load()["position"])
        self.write({"position": "-1280+40"})            # monitor à esquerda (coordenada negativa)
        self.assertEqual(config.load()["position"], "-1280+40")

    def test_wrong_types_fall_back_to_defaults(self):
        self.write({"enabled": "sim", "auto_profile": 1})
        cfg = config.load()
        self.assertTrue(cfg["enabled"])
        self.assertFalse(cfg["auto_profile"])
        self.write("{nao e json")
        self.assertFalse(config.load()["auto_profile"])


if __name__ == "__main__":
    unittest.main()
