import unittest

from modules.home.placement import SETTLE_S, TOLERANCE, ClientPlacer

AREA = (0, 0, 1920, 1032)


class FakeDesktop:
    """Janelas do RF falsas: hwnd -> (esq, topo, dir, base); None = minimizada."""

    def __init__(self):
        self.windows = {}
        self.moves = []
        self.now = 0.0
        self.area = AREA
        self.minimized = set()
        self.fail_move = False

    def add(self, hwnd, left=300, top=200, width=1606, height=929):
        self.windows[hwnd] = (left, top, left + width, top + height)

    def move(self, hwnd, left, top):
        if self.fail_move:
            raise OSError("negado")
        r = self.windows[hwnd]
        self.windows[hwnd] = (left, top, left + r[2] - r[0], top + r[3] - r[1])      # só a posição muda
        self.moves.append((hwnd, left, top))

    def placer(self):
        return ClientPlacer(lambda: [(h, "RF Online", h) for h in self.windows], lambda h: None if h in self.minimized else self.windows[h],
                            self.move, lambda: self.area, clock=lambda: self.now)


class PlacerTests(unittest.TestCase):
    def setUp(self):
        self.desk = FakeDesktop()
        self.placer = self.desk.placer()

    def test_janela_que_ja_estava_aberta_nao_e_mexida(self):
        self.desk.add(1)
        self.placer.update()
        self.desk.now += 1
        self.assertEqual(self.placer.update(), [])
        self.assertEqual(self.desk.windows[1][:2], (300, 200))

    def test_janela_nova_vai_para_o_canto_superior_esquerdo_sem_mudar_de_tamanho(self):
        self.placer.update()
        self.desk.add(7)
        self.assertEqual(self.placer.update(), [7])
        self.assertEqual(self.desk.windows[7], (0, 0, 1606, 929))

    def test_respeita_a_barra_de_tarefas_do_monitor_principal(self):
        self.desk.area = (60, 0, 1920, 1032)             # barra de tarefas à esquerda
        self.placer.update()
        self.desk.add(7)
        self.placer.update()
        self.assertEqual(self.desk.windows[7][:2], (60, 0))

    def test_ja_no_canto_nao_e_movida(self):
        self.placer.update()
        self.desk.add(7, left=-1, top=0)                  # a moldura do jogo começa em -1
        self.assertEqual(self.placer.update(), [])
        self.assertEqual(self.desk.moves, [])
        self.desk.add(8, left=TOLERANCE, top=0)
        self.assertEqual(self.placer.update(), [])

    def test_o_jogo_reposiciona_a_propria_janela_no_inicio(self):
        self.placer.update()
        self.desk.add(7)
        self.placer.update()
        self.desk.now += 3
        self.desk.windows[7] = (500, 400, 2106, 1329)     # o jogo se reposicionou depois de criada
        self.assertEqual(self.placer.update(), [7])
        self.assertEqual(self.desk.windows[7][:2], (0, 0))

    def test_depois_do_prazo_a_janela_e_do_usuario(self):
        self.placer.update()
        self.desk.add(7)
        self.placer.update()
        self.desk.now += SETTLE_S + 1
        self.desk.windows[7] = (1920, 100, 3526, 1029)    # o usuário arrastou para o outro monitor
        self.assertEqual(self.placer.update(), [])
        self.assertEqual(self.desk.windows[7][:2], (1920, 100))

    def test_cada_janela_nova_tem_o_seu_prazo(self):
        self.placer.update()
        self.desk.add(1)
        self.placer.update()
        self.desk.now += SETTLE_S + 1
        self.desk.add(2)
        self.desk.windows[1] = (800, 300, 2406, 1229)
        self.assertEqual(self.placer.update(), [2])
        self.assertEqual(self.desk.windows[1][:2], (800, 300))

    def test_varias_janelas_novas_de_uma_vez(self):
        self.placer.update()
        for hwnd in (1, 2, 3):
            self.desk.add(hwnd)
        self.assertEqual(sorted(self.placer.update()), [1, 2, 3])

    def test_minimizada_nao_e_mexida(self):
        self.placer.update()
        self.desk.add(7)
        self.desk.minimized.add(7)
        self.assertEqual(self.placer.update(), [])
        self.assertEqual(self.desk.moves, [])

    def test_janela_que_fecha_sai_da_conferencia(self):
        self.placer.update()
        self.desk.add(7)
        self.placer.update()
        del self.desk.windows[7]
        self.assertEqual(self.placer.update(), [])

    def test_erro_ao_listar_as_janelas_nao_derruba(self):
        def boom():
            raise OSError("sem acesso")
        placer = ClientPlacer(boom, lambda h: None, lambda *a: None, lambda: AREA)
        self.assertEqual(placer.update(), [])

    def test_erro_ao_mover_nao_derruba_e_tenta_de_novo(self):
        self.placer.update()
        self.desk.add(7)
        self.desk.fail_move = True
        self.assertEqual(self.placer.update(), [])
        self.desk.fail_move = False
        self.assertEqual(self.placer.update(), [7])

    def test_sem_monitor_nao_mexe_em_nada(self):
        self.desk.area = None
        self.placer.update()
        self.desk.add(7)
        self.assertEqual(self.placer.update(), [])
        self.assertEqual(self.desk.moves, [])


if __name__ == "__main__":
    unittest.main()
