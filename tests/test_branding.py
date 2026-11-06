import struct
import tkinter as tk
import unittest

from modules.shared import branding
from modules.shared.logo_data import PNG_BASE64


class BrandingTest(unittest.TestCase):
    def test_embedded_pngs_are_valid_and_have_the_expected_sizes(self):
        self.assertEqual(sorted(PNG_BASE64), [16, 24, 32, 48, 64, 256])
        for size in PNG_BASE64:
            data = branding.png_bytes(size)
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            width, height = struct.unpack(">II", data[16:24])
            self.assertEqual((width, height), (size, size))

    def test_apply_sets_the_icon_without_touching_the_disk(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.withdraw()
        branding.apply(root)
        self.assertEqual(len(root._rf_helper_icons), 6)
        self.assertEqual(sorted(p.width() for p in root._rf_helper_icons), [16, 24, 32, 48, 64, 256])

    def test_apply_survives_a_broken_environment(self):
        class Broken:
            def iconphoto(self, *a):
                raise tk.TclError("sem ícone")
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.withdraw()
        orig = root.iconphoto
        root.iconphoto = Broken().iconphoto
        branding.apply(root)                     # não levanta
        root.iconphoto = orig


if __name__ == "__main__":
    unittest.main()
