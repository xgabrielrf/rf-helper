import unittest

from modules.clicker.model import (DELAY, KEY, MODE_CLICK, MODE_MACRO, TRAILING_DELAY_MS,
                                   ClickerConfig, KeyRow, Macro, delay_event, key_event)


def kinds(macro):
    return [e.kind for e in macro.events]


class MacroRecordingTest(unittest.TestCase):
    def test_first_key_has_no_leading_delay_and_times_are_between_keys(self):
        m = Macro()
        m.start_recording()
        m.record_key(0x41, "A", 10.000)
        m.record_key(0x42, "B", 10.250)
        m.record_key(0x43, "C", 10.300)
        self.assertEqual(kinds(m), [KEY, DELAY, KEY, DELAY, KEY])
        self.assertEqual([e.value for e in m.events if e.kind == DELAY], [250, 50])

    def test_stop_adds_trailing_delay_once(self):
        m = Macro()
        m.start_recording()
        m.record_key(0x41, "A", 1.0)
        m.stop_recording()
        self.assertEqual(m.events[-1].kind, DELAY)
        self.assertEqual(m.events[-1].value, TRAILING_DELAY_MS)
        n = len(m.events)
        m.start_recording()
        m.stop_recording()                      # nada gravado: não acrescenta outro
        self.assertEqual(len(m.events), n)

    def test_recording_again_continues_history(self):
        m = Macro()
        m.start_recording()
        m.record_key(0x41, "A", 1.0)
        m.stop_recording()
        m.start_recording()
        m.record_key(0x42, "B", 50.0)           # 1ª tecla da nova gravação: sem Tempo à frente
        m.record_key(0x43, "C", 50.5)
        m.stop_recording()
        self.assertEqual(kinds(m), [KEY, DELAY, KEY, DELAY, KEY, DELAY])
        self.assertEqual([e.value for e in m.events if e.kind == KEY], [0x41, 0x42, 0x43])

    def test_stop_with_nothing_recorded_keeps_empty(self):
        m = Macro()
        m.start_recording()
        m.stop_recording()
        self.assertTrue(m.is_empty())
        self.assertEqual(m.events, [])


class MacroEditingTest(unittest.TestCase):
    def setUp(self):
        self.m = Macro([key_event(1, "a"), delay_event(100), key_event(2, "b"),
                        delay_event(200), key_event(3, "c")])

    def test_set_delays_applies_to_all_selected_delays_and_ignores_keys(self):
        changed = self.m.set_delays([0, 1, 2, 3], 500)
        self.assertEqual(changed, 2)
        self.assertEqual([e.value for e in self.m.events if e.kind == DELAY], [500, 500])
        self.assertEqual([e.value for e in self.m.events if e.kind == KEY], [1, 2, 3])

    def test_set_delays_clamps_negative(self):
        self.m.set_delays([1], -5)
        self.assertEqual(self.m.events[1].value, 0)

    def test_move_and_reorder(self):
        self.m.move(4, 0)                        # tecla "c" vai para o início
        self.assertEqual([e.value for e in self.m.events][0], 3)
        self.m.reorder([1, 0, 2, 3, 4])
        self.assertEqual(self.m.events[0].kind, KEY)
        with self.assertRaises(ValueError):
            self.m.reorder([0, 0, 1, 2, 3])

    def test_delete(self):
        self.m.delete([2])
        self.assertEqual(self.m.key_count(), 2)
        self.assertEqual(len(self.m.events), 4)

    def test_summary(self):
        self.assertEqual(self.m.key_count(), 3)
        self.assertEqual(self.m.duration_ms(), 300)


class ClickerConfigTest(unittest.TestCase):
    def test_default_is_unconfigured_with_one_empty_row(self):
        cfg = ClickerConfig()
        self.assertEqual(len(cfg.keys), 1)
        self.assertFalse(cfg.is_configured())
        self.assertEqual(cfg.mode, MODE_CLICK)

    def test_configured_depends_on_active_mode(self):
        cfg = ClickerConfig()
        cfg.keys = [KeyRow(0x58, "X", 100)]
        self.assertTrue(cfg.is_configured())
        cfg.mode = MODE_MACRO
        self.assertFalse(cfg.is_configured())            # macro vazia
        cfg.macro.events = [key_event(0x58, "X")]
        self.assertTrue(cfg.is_configured())

    def test_roundtrip(self):
        cfg = ClickerConfig(mode=MODE_MACRO, keys=[KeyRow(0x58, "X", 250), KeyRow()],
                            macro=Macro([key_event(0x41, "A"), delay_event(300)], loop=False))
        again = ClickerConfig.from_dict(cfg.to_dict())
        self.assertEqual(again.to_dict(), cfg.to_dict())
        self.assertIsNot(again.macro, cfg.macro)
        self.assertFalse(again.macro.loop)

    def test_from_dict_tolerates_garbage(self):
        for bad in (None, 5, "x", [], {"mode": "zzz", "keys": "nope", "macro": 3},
                    {"keys": [None, {"vk": "x", "ms": -4}], "macro": {"events": [1, {"kind": "key"}]}}):
            cfg = ClickerConfig.from_dict(bad)
            self.assertIn(cfg.mode, (MODE_CLICK, MODE_MACRO))
            self.assertGreaterEqual(len(cfg.keys), 1)
            self.assertFalse(cfg.is_configured())

    def test_loop_defaults_to_true(self):
        self.assertTrue(Macro().loop)


if __name__ == "__main__":
    unittest.main()
