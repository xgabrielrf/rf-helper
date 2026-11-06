import unittest

from modules.shared import screens

# dois monitores lado a lado (o da direita é menor) e um à esquerda, com coordenadas negativas
MAIN = (0, 0, 1920, 1040)
RIGHT = (1920, 0, 3456, 864)
LEFT = (-1280, 100, 0, 1000)


def rect(x, y, w=400, h=300):
    return (x, y, x + w, y + h)


class FitsTest(unittest.TestCase):
    def test_window_inside_a_monitor_fits(self):
        self.assertTrue(screens.fits(rect(100, 100), [MAIN]))

    def test_window_across_two_adjacent_monitors_is_allowed(self):
        self.assertTrue(screens.fits(rect(1700, 100), [MAIN, RIGHT]), "arrastar de uma tela para outra é permitido")

    def test_window_mostly_off_screen_does_not_fit(self):
        self.assertFalse(screens.fits(rect(1800, 100), [MAIN]), "metade fora, sem monitor ali")
        self.assertFalse(screens.fits(rect(5000, 5000), [MAIN, RIGHT]))
        self.assertFalse(screens.fits(rect(-390, 100), [MAIN]), "quase toda à esquerda")

    def test_invisible_shadow_does_not_count_as_outside(self):
        self.assertTrue(screens.fits((-8, 0, 408, 308), [MAIN]), "janela encostada na borda: a sombra passa 8 px")
        self.assertTrue(screens.fits((1512, 732, 1928, 1048), [MAIN]))

    def test_part_over_a_gap_between_monitors_does_not_fit(self):
        # o monitor da direita é mais baixo (864): uma janela alta sobre a "quina" fica com parte no vazio
        self.assertFalse(screens.fits(rect(2000, 700, 400, 400), [MAIN, RIGHT]))
        self.assertFalse(screens.fits((3300, 700, 3700, 1000), [MAIN, RIGHT]))

    def test_no_monitor_info_means_do_not_touch(self):
        self.assertTrue(screens.fits(rect(99999, 99999), []))


class ClampTest(unittest.TestCase):
    def test_pulls_a_far_window_into_the_nearest_monitor(self):
        self.assertEqual(screens.clamp(rect(5000, 5000), [MAIN, RIGHT]), (3056, 564, 3456, 864))
        self.assertEqual(screens.clamp(rect(-4000, 20), [MAIN]), (0, 20, 400, 320))

    def test_keeps_the_monitor_with_most_overlap(self):
        # parte no monitor principal, parte no vazio sob o monitor da direita (mais baixo): fica no principal
        moved = screens.clamp(rect(1700, 700), [MAIN, RIGHT])
        self.assertEqual(moved, (1520, 700, 1920, 1000), "mais da janela estava no monitor principal")

    def test_monitor_that_was_unplugged(self):
        # a janela estava no monitor da direita, que não existe mais: vai para o que sobrou
        self.assertTrue(screens.fits(screens.clamp(rect(2500, 200), [MAIN]), [MAIN]))

    def test_window_bigger_than_the_monitor_keeps_its_title_bar(self):
        self.assertEqual(screens.clamp((-300, -200, 2300, 1400), [MAIN]), (0, 0, 2600, 1600))

    def test_negative_coordinates_monitor(self):
        self.assertEqual(screens.clamp(rect(-1500, 150), [LEFT, MAIN]), (-1280, 150, -880, 450))

    def test_window_already_inside_is_untouched(self):
        self.assertEqual(screens.clamp(rect(100, 100), [MAIN]), rect(100, 100))

    def test_no_monitors_returns_the_rect(self):
        self.assertEqual(screens.clamp(rect(9, 9), []), rect(9, 9))


class CenterAndPointTest(unittest.TestCase):
    def test_center_in(self):
        self.assertEqual(screens.center_in(MAIN, 1000, 600), (460, 220))
        self.assertEqual(screens.center_in(RIGHT, 400, 300), (2488, 282))

    def test_point_visible(self):
        self.assertTrue(screens.point_visible(100, 100, [MAIN, RIGHT]))
        self.assertTrue(screens.point_visible(2000, 50, [MAIN, RIGHT]))
        self.assertFalse(screens.point_visible(5000, 100, [MAIN, RIGHT]))
        self.assertFalse(screens.point_visible(1900, 100, [MAIN]), "o canto precisa de folga para dentro")
        self.assertTrue(screens.point_visible(5, 5, []))


class RealMonitorsTest(unittest.TestCase):
    def test_this_machine_reports_at_least_one_sane_monitor(self):
        found, primary = screens.monitors(with_primary=True)
        self.assertTrue(found)
        self.assertTrue(0 <= primary < len(found))
        for left, top, right, bottom in found:
            self.assertTrue(right > left and bottom > top)


if __name__ == "__main__":
    unittest.main()
