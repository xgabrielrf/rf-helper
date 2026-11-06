import time
import tkinter as tk
import unittest

from modules.clicker import windowing
from modules.shared import screens

# dois monitores lado a lado (o da direita é menor), como no computador do usuário
FAKE = [(0, 0, 1920, 1032), (1920, 0, 3456, 816)]


def fake_monitors(with_primary=False):
    return (list(FAKE), 0) if with_primary else list(FAKE)


class WindowingTest(unittest.TestCase):
    def setUp(self):
        original = screens.monitors
        screens.monitors = fake_monitors
        self.addCleanup(lambda: setattr(screens, "monitors", original))
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.root.geometry("300x200+100+100")
        self.root.update()

    def pump(self, ms):
        end = time.time() + ms / 1000
        while time.time() < end:
            self.root.update()
            time.sleep(0.01)

    def rect(self):
        return windowing.frame_rect(self.root)

    def test_center_on_screen_uses_the_primary_monitor(self):
        windowing.center_on_screen(self.root)
        self.root.update()
        left, top, right, bottom = self.rect()
        self.assertAlmostEqual((left + right) / 2, 960, delta=14)
        self.assertAlmostEqual((top + bottom) / 2, 516, delta=14)

    def test_window_opened_off_screen_is_pulled_in(self):
        self.root.geometry("+9000+9000")
        self.root.update()
        windowing.keep_on_screen(self.root)
        self.root.update()
        self.assertTrue(screens.fits(self.rect(), FAKE))

    def test_window_dropped_half_hidden_comes_back_after_a_moment(self):
        windowing.keep_on_screen(self.root)
        self.root.geometry("+1750+850")                 # metade para fora (embaixo do monitor da direita)
        self.pump(windowing.SETTLE_MS + 500)
        self.assertTrue(screens.fits(self.rect(), FAKE))

    def test_window_across_the_two_monitors_is_left_alone(self):
        windowing.keep_on_screen(self.root)
        self.root.geometry("+1800+100")                 # atravessa as duas telas: pode (arrastar entre telas)
        self.pump(windowing.SETTLE_MS + 500)
        self.assertEqual((self.root.winfo_x(), self.root.winfo_y()), (1800, 100))

    def test_saved_position_is_never_outside_the_screens(self):
        self.root.geometry("+9000+9000")
        self.root.update()
        pos = windowing.current_position(self.root)
        x, y = (int(v) for v in windowing.POSITION_RE.match(pos).groups())
        right, bottom = x + self.root.winfo_width(), y + self.root.winfo_height()
        self.assertTrue(screens.point_visible(x, y, FAKE) and right <= 3456 + 20 and bottom <= 1032 + 20, pos)

    def test_visible_position_rejects_what_is_on_no_monitor(self):
        self.assertEqual(windowing.visible_position("+100+100"), "+100+100")
        self.assertEqual(windowing.visible_position("+2500+100"), "+2500+100")
        self.assertIsNone(windowing.visible_position("+9000+100"))
        self.assertIsNone(windowing.visible_position("-1280+40"), "monitor da esquerda não existe nesta configuração")
        self.assertIsNone(windowing.visible_position("lixo"))
        self.assertIsNone(windowing.visible_position(None))


if __name__ == "__main__":
    unittest.main()
