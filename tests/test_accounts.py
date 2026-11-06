import json
import os
import tempfile
import unittest

from modules.accounts import model, secrets, store
from modules.accounts.model import Account, Character, Server


def sample():
    chars = [Character("Guerreiro", "accretia", "DPS"), Character("Tanky", "bellato", "Tanker")]
    acc = Account("conta01", "s3nha-Ç!", "principal", chars)
    return Server("RF Brasil", r"C:\RFBrasil\RF_BrasilRPG.exe", "", [acc])


class SecretsTest(unittest.TestCase):
    def test_roundtrip_and_not_plaintext(self):
        token = secrets.protect("minha senha ção")
        self.assertTrue(token.startswith(secrets.PREFIX))
        self.assertNotIn("minha", token)
        self.assertEqual(secrets.unprotect(token), "minha senha ção")

    def test_garbage_is_rejected(self):
        for bad in (None, "", "texto", "dpapi:", "dpapi:@@@", "dpapi:AAAA", 5):
            self.assertIsNone(secrets.unprotect(bad))


class ValidationTest(unittest.TestCase):
    def test_account_needs_login_password_and_complete_characters(self):
        self.assertIsNotNone(Account("", "x").error())
        self.assertIsNotNone(Account("a", "").error())
        self.assertIsNone(Account("a", "x").error())
        self.assertIsNotNone(Account("a", "x", characters=[Character("n", "", "DPS")]).error())
        self.assertIsNotNone(Account("a", "x", characters=[Character("n", "cora", "Mago")]).error())
        self.assertIsNone(Account("a", "x", characters=[Character("n", "cora", "DPS")]).error())

    def test_login_and_password_limited_to_what_the_launcher_accepts(self):
        self.assertIsNone(Account("a" * 12, "b" * 12).error())
        self.assertIn("12", Account("a" * 13, "b").error())
        self.assertIn("12", Account("a", "b" * 13).error())

    def test_at_most_three_characters(self):
        chars = [Character(f"p{i}", "cora", "DPS") for i in range(4)]
        self.assertIsNone(Account("a", "x", characters=chars[:3]).error())
        self.assertIsNotNone(Account("a", "x", characters=chars).error())

    def test_server_requires_name_and_launcher(self):
        self.assertIsNotNone(Server("", "x.exe").error())
        self.assertIsNotNone(Server("n", " ").error())
        self.assertIsNone(Server("n", "x.exe").error())

    def test_warning_when_launcher_or_client_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            launcher = os.path.join(tmp, "L.exe")
            self.assertIn("não foi encontrado", Server("n", launcher).warning())
            open(launcher, "w").close()
            self.assertIn(model.CLIENT_NAME, Server("n", launcher).warning())
            open(os.path.join(tmp, model.CLIENT_NAME), "w").close()
            self.assertIsNone(Server("n", launcher).warning())


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        old = (store.CONFIG_DIR, store.STORE_PATH)
        store.CONFIG_DIR = self.tmp.name
        store.STORE_PATH = os.path.join(self.tmp.name, "servers.json")
        self.addCleanup(lambda: (setattr(store, "CONFIG_DIR", old[0]), setattr(store, "STORE_PATH", old[1])))

    def test_missing_or_corrupt_file_means_empty(self):
        self.assertEqual(store.load(), ([], None))
        for text in ("{nao e json", "[]", '{"servers": 3}'):
            with open(store.STORE_PATH, "w", encoding="utf-8") as f:
                f.write(text)
            self.assertEqual(store.load(), ([], None))

    def test_roundtrip(self):
        server = sample()
        self.assertTrue(store.save([server], server.id))
        servers, last = store.load()
        self.assertEqual(last, server.id)
        loaded = servers[0]
        self.assertEqual((loaded.id, loaded.name, loaded.launcher_path), (server.id, "RF Brasil", server.launcher_path))
        acc = loaded.accounts[0]
        self.assertEqual((acc.login, acc.password, acc.description), ("conta01", "s3nha-Ç!", "principal"))
        self.assertEqual([(c.name, c.race, c.cls) for c in acc.characters],
                         [("Guerreiro", "accretia", "DPS"), ("Tanky", "bellato", "Tanker")])

    def test_password_is_not_in_the_file(self):
        store.save([sample()])
        with open(store.STORE_PATH, "r", encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("s3nha", text)
        self.assertIn("dpapi:", text)

    def test_unknown_last_server_is_dropped_and_bad_entries_skipped(self):
        raw = {"last_server": "nao-existe", "servers": [
            "lixo", {"name": 5},
            {"id": "a", "name": "Bom", "launcher_path": "x.exe", "server_index": 99,
             "accounts": [{"login": 1}, {"login": "ok", "password": "texto-puro",
                                          "characters": [{"name": "A", "race": "x", "class": "DPS"}, {"race": "cora"}]}]}]}
        with open(store.STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(raw, f)
        servers, last = store.load()
        self.assertIsNone(last)
        self.assertEqual([s.name for s in servers], ["Bom"])
        self.assertEqual(servers[0].server_index, 0)
        acc = servers[0].accounts[0]
        self.assertEqual(acc.login, "ok")
        self.assertIsNone(acc.password)                 # texto puro não é aceito como senha
        self.assertEqual([(c.name, c.race) for c in acc.characters], [("A", "")])

    def test_unreadable_password_is_preserved_on_save(self):
        server = sample()
        store.save([server])
        with open(store.STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["servers"][0]["accounts"][0]["password"] = "dpapi:AAAA"     # "de outro usuário"
        with open(store.STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
        servers, _ = store.load()
        self.assertIsNone(servers[0].accounts[0].password)
        store.save(servers)
        with open(store.STORE_PATH, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["servers"][0]["accounts"][0]["password"], "dpapi:AAAA")


if __name__ == "__main__":
    unittest.main()
