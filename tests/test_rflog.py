import os
import tempfile
import unittest
from datetime import datetime, timedelta

from modules.characters.rflog import (CharacterTracker, LogReader, LogState, log_path_for,
                                      parse_line)

T0 = datetime(2026, 11, 1, 19, 0, 0)


def stamp(when):
    return when.strftime("%m/%d/%y %H:%M:%S")


class FakeLog:
    """Escreve linhas no formato do rfclient.log, com um contador por client."""

    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.counters = {}

    def emit(self, client, when, msg):
        n = self.counters.get(client, 0) + 1
        self.counters[client] = n
        with open(self.path, "ab") as f:
            f.write(f"[{n}] {stamp(when)}: {msg}\r\n".encode("cp1252"))

    def launch(self, client, when, account):
        self.counters[client] = 0
        self.emit(client, when, "GetDataFromLauncher")
        self.emit(client, when, f"SetAccountID {account} ^^ {account}")

    def enter_map(self, client, when, name):
        self.emit(client, when, "AcceptClientCheck SystemMsg_MoveinUserRequest_zone")
        self.emit(client, when, "100 ) base req")
        self.emit(client, when, f"101 ) base result ( 0 - {name} )")

    def to_lobby(self, client, when):
        self.emit(client, when, "100 ) moveout req (0)")
        self.emit(client, when, "118 ) load map ( .\\map\\lobby\\lobby.BSP )")


class ParseTest(unittest.TestCase):
    def test_valid_line(self):
        n, when, msg = parse_line("[406] 11/02/26 02:21:00: 101 ) base result ( 0 - Mago )")
        self.assertEqual((n, when, msg), (406, datetime(2026, 11, 2, 2, 21, 0),
                                          "101 ) base result ( 0 - Mago )"))

    def test_invalid_lines(self):
        for bad in ("", "lixo", "[x] 11/02/26 02:21:00: a", "[1] 13/45/26 99:99:99: a",
                    "[1] 11/02/26 02:21:00 sem dois pontos"):
            self.assertIsNone(parse_line(bad), bad)

    def test_log_path_for(self):
        self.assertEqual(log_path_for(r"C:\RFBrasil\RF_Online.bin"),
                         os.path.normpath(r"C:\RFBrasil\NetLog\rfclient.log"))


class TrackerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.exe = os.path.join(self.tmp.name, "RF_Online.bin")
        self.log = FakeLog(log_path_for(self.exe))
        self.tracker = CharacterTracker()

    def procs(self, **created):
        """pid → (exe, criação); a criação do processo é ~2 s antes de o log abrir o client."""
        return {int(pid[1:]): (self.exe, when - timedelta(seconds=2)) for pid, when in created.items()}

    def names(self, procs):
        return {pid: info.name for pid, info in self.tracker.refresh(procs).items()}

    def filler(self, client, when, count):
        for i in range(count):
            self.log.emit(client, when + timedelta(seconds=i), "Particle Not Found")

    def test_three_interleaved_clients_are_told_apart(self):
        a, b, c = T0, T0 + timedelta(minutes=5), T0 + timedelta(minutes=9)
        self.log.launch("A", a, "conta01")
        self.filler("A", a, 100)
        self.log.launch("B", b, "conta02")
        self.filler("B", b, 40)
        self.filler("A", b, 30)                      # A continua escrevendo enquanto B abre
        self.log.launch("C", c, "conta03")
        for i, (client, name) in enumerate((("C", "Cee"), ("A", "Ayy"), ("B", "Bee"))):
            self.log.enter_map(client, c + timedelta(seconds=10 + i), name)
        for i in range(30):                          # os três seguem escrevendo, intercalados
            for client in "ABC":
                self.log.emit(client, c + timedelta(minutes=1, seconds=i), "Particle Not Found")
        info = self.tracker.refresh(self.procs(p1=a, p2=b, p3=c))
        self.assertEqual({p: (i.name, i.account) for p, i in info.items()},
                         {1: ("Ayy", "conta01"), 2: ("Bee", "conta02"), 3: ("Cee", "conta03")})

    def test_clients_writing_the_same_counter_at_once_give_no_name_instead_of_a_wrong_one(self):
        self.log.launch("A", T0, "conta01")
        self.log.launch("B", T0 + timedelta(seconds=1), "conta02")
        for client, name in (("A", "Ayy"), ("B", "Bee")):    # mesmo número de linha, mesma hora
            self.log.emit(client, T0 + timedelta(seconds=9), "100 ) base req")
        for client, name in (("A", "Ayy"), ("B", "Bee")):
            self.log.emit(client, T0 + timedelta(seconds=9), f"101 ) base result ( 0 - {name} )")
        procs = {1: (self.exe, T0 - timedelta(seconds=2)), 2: (self.exe, T0 - timedelta(seconds=1))}
        self.assertEqual(self.names(procs), {1: None, 2: None})

    def test_unambiguous_line_after_a_tie_recovers_the_name(self):
        self.log.launch("A", T0, "conta01")
        self.log.launch("B", T0 + timedelta(seconds=1), "conta02")
        for client in "AB":
            self.log.emit(client, T0 + timedelta(seconds=9), "101 ) base result ( 0 - Ambiguo )")
        self.filler("A", T0 + timedelta(seconds=10), 5)       # A anda; os contadores se separam
        self.log.emit("A", T0 + timedelta(seconds=20), "101 ) base result ( 0 - Ayy )")
        procs = {1: (self.exe, T0 - timedelta(seconds=2)), 2: (self.exe, T0 - timedelta(seconds=1))}
        self.assertEqual(self.names(procs), {1: "Ayy", 2: None})

    def test_character_switch_goes_through_lobby(self):
        self.log.launch("A", T0, "conta01")
        self.log.enter_map("A", T0 + timedelta(seconds=5), "Guerreiro")
        procs = self.procs(p1=T0)
        self.assertEqual(self.names(procs), {1: "Guerreiro"})
        self.log.to_lobby("A", T0 + timedelta(minutes=10))
        self.assertEqual(self.names(procs), {1: None})               # na seleção: sem personagem
        self.log.enter_map("A", T0 + timedelta(minutes=11), "iGuerreiro")
        self.assertEqual(self.names(procs), {1: "iGuerreiro"})

    def test_foreign_lines_with_a_nearby_counter_do_not_steal(self):
        """Regressão (bug real): linhas de um client desconhecido, com contador pouco à frente do
        de um vivo, eram atribuídas ao vivo quando o casamento aceitava saltos no contador, e o
        nome do personagem saía trocado."""
        self.log.launch("LIVE", T0, "viva")                       # contador do vivo: 2
        self.log.counters["FOREIGN"] = 6                           # outro client, que ninguém lista
        self.log.emit("FOREIGN", T0, "101 ) base result ( 0 - Intruso )")   # n = 7
        self.log.enter_map("LIVE", T0 + timedelta(seconds=5), "Vivo")        # n = 3, 4, 5
        self.assertEqual(self.names(self.procs(p1=T0)), {1: "Vivo"})

    def test_closed_client_does_not_drag_a_live_one_away_from_its_real_counter(self):
        """Regressão (bug real: o client de uma conta mostrava o personagem de outra). Um client já
        fechado continua com a numeração em dia no log; se ele não fosse acompanhado, as suas linhas
        seguintes caíam num vivo parado no número anterior, que ficava adiantado para sempre e
        nunca mais reconhecia as linhas verdadeiras (o personagem novo)."""
        self.log.launch("LIVE", T0, "viva")
        self.filler("LIVE", T0 + timedelta(seconds=3), 10)        # o vivo para no contador 12
        self.log.launch("CLOSED", T0 + timedelta(minutes=5), "fechada")
        self.filler("CLOSED", T0 + timedelta(minutes=5, seconds=1), 10)    # o outro também chega ao 12
        self.filler("CLOSED", T0 + timedelta(minutes=6), 30)               # e segue sozinho até 42
        self.log.enter_map("LIVE", T0 + timedelta(minutes=10), "Vivo")     # o vivo retoma em 13
        self.assertEqual(self.names(self.procs(p1=T0)), {1: "Vivo"})

    def test_a_line_lost_in_the_counter_does_not_strand_the_client(self):
        """Com vários clients escrevendo juntos o jogo perde linhas (`[783] [784] [786]`)."""
        self.log.launch("A", T0, "conta01")
        self.filler("A", T0 + timedelta(seconds=1), 5)
        self.log.counters["A"] += 1                                # uma linha que nunca chegou ao arquivo
        self.log.enter_map("A", T0 + timedelta(seconds=9), "Ayy")
        self.assertEqual(self.names(self.procs(p1=T0)), {1: "Ayy"})

    def test_stopped_stream_does_not_take_lines_from_the_active_one(self):
        """Dois fluxos esperando o mesmo número: vale o que está ativo (o fechado fica parado)."""
        self.log.launch("DEAD", T0, "morta")
        self.log.enter_map("DEAD", T0 + timedelta(seconds=5), "Fantasma")      # morre com contador 5
        later = T0 + timedelta(hours=3)
        self.log.launch("LIVE", later, "viva")
        self.log.enter_map("LIVE", later + timedelta(seconds=9), "Vivo")       # n = 3, 4, 5 e ...
        self.log.emit("LIVE", later + timedelta(seconds=10), "101 ) base result ( 0 - Vivo2 )")   # n = 6
        self.assertEqual(self.names(self.procs(p1=later)), {1: "Vivo2"})

    def test_idle_client_with_the_same_counter_does_not_take_the_active_ones_line(self):
        """Caso real do log: um client parado há minutos e outro ativo chegam ao mesmo número."""
        self.log.launch("A", T0, "conta01")
        self.log.launch("B", T0 + timedelta(minutes=2), "conta02")
        self.filler("B", T0 + timedelta(minutes=2), 10)           # B: contador 12, ativo agora
        self.filler("A", T0 + timedelta(seconds=3), 10)           # A: contador 12, parado desde cedo
        late = T0 + timedelta(minutes=30)
        self.log.emit("B", late, "101 ) base result ( 0 - Bee )")   # n = 13, e A também espera 13
        procs = {1: (self.exe, T0 - timedelta(seconds=2)),
                 2: (self.exe, T0 + timedelta(minutes=2) - timedelta(seconds=2))}
        self.assertEqual(self.names(procs), {1: None, 2: "Bee"})

    def test_incremental_reads_and_partial_last_line(self):
        self.log.launch("A", T0, "conta01")
        procs = self.procs(p1=T0)
        self.assertEqual(self.names(procs), {1: None})
        with open(self.log.path, "ab") as f:             # linha cortada no meio, sem \n
            f.write(f"[3] {stamp(T0)}: 101 ) base result ( 0 - Cor".encode())
        self.assertEqual(self.names(procs), {1: None})
        with open(self.log.path, "ab") as f:
            f.write(b"tada )\r\n")
        self.assertEqual(self.names(procs), {1: "Cortada"})

    def test_log_restarting_from_zero_is_followed(self):
        self.log.launch("A", T0, "conta01")
        self.log.enter_map("A", T0, "Antigo")
        for i in range(20):
            self.log.emit("A", T0, "Particle Not Found : " + "x" * 30)
        procs = self.procs(p1=T0)
        self.assertEqual(self.names(procs), {1: "Antigo"})
        os.remove(self.log.path)                          # o jogo recria o arquivo, menor
        self.log.launch("A", T0, "conta01")
        self.log.enter_map("A", T0, "Novo")
        self.assertEqual(self.names(procs), {1: "Novo"})

    def test_missing_log_or_unmatched_process_gives_nothing(self):
        self.assertEqual(self.tracker.refresh(self.procs(p1=T0)), {})
        self.log.launch("A", T0, "conta01")
        stranger = {9: (self.exe, T0 + timedelta(days=2))}   # nenhum client abriu nessa hora
        self.assertEqual(self.tracker.refresh(stranger), {})

    def test_large_log_is_read_from_the_process_start(self):
        old = T0 - timedelta(days=30)
        for i in range(4000):                             # ~200 KB de histórico antigo
            self.log.emit("OLD", old + timedelta(seconds=i), "Particle Not Found : " + "x" * 40)
        self.log.launch("A", T0, "conta01")
        self.log.enter_map("A", T0 + timedelta(seconds=5), "Guerreiro")
        size = os.path.getsize(self.log.path)
        self.assertGreater(size, 150_000)
        procs = self.procs(p1=T0)
        self.assertEqual(self.names(procs), {1: "Guerreiro"})
        reader = self.tracker._logs[log_path_for(self.exe)][0]
        self.assertGreater(reader.start_offset, 0)
        self.assertLess(reader.start_offset, size)
        self.assertLess(size - reader.start_offset, size // 2)   # pulou o histórico em vez de ler tudo

    def test_older_process_appearing_later_rereads_history(self):
        self.log.launch("A", T0, "conta01")
        self.log.enter_map("A", T0, "Ayy")
        later = T0 + timedelta(hours=1)
        self.log.launch("B", later, "conta02")
        self.log.enter_map("B", later, "Bee")
        self.assertEqual(self.names(self.procs(p2=later)), {2: "Bee"})
        self.assertEqual(self.names(self.procs(p1=T0, p2=later)), {1: "Ayy", 2: "Bee"})

    def test_logs_without_live_clients_are_dropped(self):
        self.log.launch("A", T0, "conta01")
        self.tracker.refresh(self.procs(p1=T0))
        self.assertEqual(len(self.tracker._logs), 1)
        self.tracker.refresh({})
        self.assertEqual(len(self.tracker._logs), 0)


class LogStateTest(unittest.TestCase):
    def test_lobby_match_is_case_insensitive_and_only_for_load_map(self):
        s = LogState()
        s.feed(1, T0, "GetDataFromLauncher")
        s.feed(2, T0, "101 ) base result ( 0 - Guerreiro )")
        s.feed(3, T0, "Particle Not Found : .\\chef\\lobby\\x.spt")      # menção a "lobby" não conta
        self.assertEqual(s.streams[0].name, "Guerreiro")
        s.feed(4, T0, "118 ) load map ( .\\MAP\\Lobby\\lobby.bsp )")
        self.assertIsNone(s.streams[0].name)

    def test_non_zero_result_code_is_not_a_character(self):
        s = LogState()
        s.feed(1, T0, "GetDataFromLauncher")
        s.feed(2, T0, "101 ) base result ( 1 - Erro )")
        self.assertIsNone(s.streams[0].name)


class ReaderTest(unittest.TestCase):
    def test_reader_handles_missing_file(self):
        reader = LogReader(os.path.join(tempfile.gettempdir(), "nao-existe-rf", "x.log"))
        self.assertEqual(reader.read_new(), [])


if __name__ == "__main__":
    unittest.main()
