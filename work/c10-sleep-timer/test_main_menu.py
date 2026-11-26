"""Exercise the stock function/settings main menu in the candidate MIPS ELF.

Rendering/font calls are recorded or given fixture dimensions; no SDL, audio,
filesystem save or device call is executed. This is not a physical screenshot.
"""
import io
from pathlib import Path
import struct
import sys
import unittest

from elftools.elf.elffile import ELFFile
from PIL import Image

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / 'c10-analysis'))
import trace_stock_poweroff as stock
from test_mips_patch import tick, readword
from unicorn.mips_const import (
    UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3,
    UC_MIPS_REG_PC, UC_MIPS_REG_RA, UC_MIPS_REG_SP, UC_MIPS_REG_V0,
)

stock.IMAGE = (BASE / 'build/ap.sleep-candidate.dge').read_bytes()
APP = BASE.parent / 'c10-analysis/appfs/local/aplayer'


class MenuProbe(stock.Probe):
    def __init__(self, language=0, selection=0, duration=0):
        super().__init__(0)
        elf = ELFFile(io.BytesIO(stock.IMAGE))
        self.symbols = {s.name: s['st_value']
                        for s in elf.get_section_by_name('.dynsym').iter_symbols()}
        self.recorded = []
        self.u.mem_map(0x21000000, 0x10000)
        self.heap = 0x21000000
        for group, count, global_name in [('res/C10UList', 20, 'C10UList'),
                                          ('res/C10UPlay', 20, 'C10UPlay'),
                                          ('cfg/C10USysCfg', 23, 'C10USysCfg')]:
            table = self.allocate(count * 4)
            self.word(self.symbols[global_name], table)
            for i in range(count):
                surface = self.allocate(64)
                with Image.open(APP / (group + f'{i + 1:02}.png')) as image:
                    width, height = image.size
                self.word(surface + 8, width)
                self.word(surface + 12, height)
                self.word(table + i * 4, surface)
        for name in ['blitSurface', 'sdl_draw_pic', 'draw_bat_state',
                     'c10get_text_wh', 'c10sysconfigtxt_scroll', 'sdl_draw_text',
                     'c10writeglobalattr']:
            self.stubs[self.symbols[name]] = name
        self.word(self.symbols['c10_ui_type'], 3)
        self.word(self.symbols['c10uicfgmenutype'], selection)
        self.word(self.symbols['tglobalproperty'] + 0xc, language)
        self.word(self.symbols['c10syscfgitem'], language)
        self.word(self.symbols['c10syscfgitem'] + 0x14, duration)
        self.word(self.symbols['c10syscfgitem'] + 0x18, 5)
        self.word(self.symbols['tglobalproperty'] + 8, 5)
        self.word(self.symbols['main_font_12'], 12)
        self.word(self.symbols['main_font_18'], 18)

    def allocate(self, size):
        addr = self.heap
        self.heap += (size + 15) & ~15
        assert self.heap < 0x21010000
        return addr

    def string(self, address):
        return bytes(self.u.mem_read(address, 256)).split(b'\0', 1)[0].decode('utf8')

    def hook(self, u, address, size, data):
        name = self.stubs.get(address)
        if name not in {'blitSurface', 'sdl_draw_pic', 'draw_bat_state',
                        'c10get_text_wh', 'c10sysconfigtxt_scroll', 'sdl_draw_text',
                        'TTF_SizeUTF8', 'SDL_Flip', 'c10writeglobalattr'}:
            return super().hook(u, address, size, data)
        a, b, c, d = [u.reg_read(r) for r in
                      [UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3]]
        sp = u.reg_read(UC_MIPS_REG_SP)
        if name == 'c10get_text_wh':
            text = self.string(a)
            self.word(b + 8, len(text) * 18)
            self.word(b + 12, 22)
        elif name == 'TTF_SizeUTF8':
            self.word(c, len(self.string(b)) * 7)
            self.word(d, 15)
        elif name == 'c10sysconfigtxt_scroll':
            self.recorded.append({'kind': 'label', 'text': self.string(b),
                                  'selected': bool(a), 'x': c, 'y': d})
        elif name == 'sdl_draw_text':
            self.recorded.append({'kind': 'value', 'text': self.string(readword(self, sp + 16)),
                                  'x': a, 'y': b})
        elif name == 'c10writeglobalattr':
            self.recorded.append({'kind': 'mock_save', 'path': self.string(a)})
        u.reg_write(UC_MIPS_REG_V0, 0)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def invoke(self, entry, a0=0, a1=0):
        self.stopped = None
        self.stops = {stock.RETURN}
        self.u.reg_write(UC_MIPS_REG_RA, stock.RETURN)
        self.u.reg_write(UC_MIPS_REG_A0, a0)
        self.u.reg_write(UC_MIPS_REG_A1, a1)
        self.run(entry)

    def draw(self):
        self.recorded.clear()
        self.invoke(0x4276a4, 0x2100f000)
        return list(self.recorded)

    def release(self, key):
        self.invoke(0x425a30, key, 0)


class MainMenuTests(unittest.TestCase):
    def test_timer_is_a_peer_of_language_and_play_mode_on_opening_page(self):
        p = MenuProbe(selection=0)
        labels = [r for r in p.draw() if r['kind'] == 'label']
        titles = [r['text'] for r in labels]
        self.assertIn('语言设置', titles)
        self.assertIn('播放模式', titles)
        self.assertIn('睡眠定时关机', titles)
        self.assertEqual(len(labels), 8)
        timer = next(r for r in labels if r['text'] == '睡眠定时关机')
        self.assertGreater(timer['y'], 0)
        self.assertLess(timer['y'], 360)

    def test_selecting_timer_highlights_it_and_shows_all_four_durations(self):
        for duration, expected in enumerate(['OFF', '30min', '60min', '90min']):
            with self.subTest(duration=duration):
                p = MenuProbe(selection=5, duration=duration)
                records = p.draw()
                selected = [r['text'] for r in records if r['kind'] == 'label' and r['selected']]
                self.assertEqual(selected, ['睡眠定时关机'])
                values = [r['text'] for r in records if r['kind'] == 'value']
                self.assertIn(expected, values)

    def test_stock_right_and_left_keys_cycle_timer_values(self):
        p = MenuProbe(selection=5)
        option = p.symbols['c10syscfgitem'] + 0x14
        for key, expected_values in [(106, [1, 2, 3, 0]), (105, [3, 2, 1, 0])]:
            for expected in expected_values:
                p.release(key)
                self.assertEqual(readword(p, option), expected)
        self.assertEqual(p.calls, [])

    def test_settings_commit_arms_real_timer_without_changing_other_properties(self):
        p = MenuProbe(selection=5)
        self.assertFalse(tick(p, 0))  # Same initialization as normal startup.
        properties = p.symbols['tglobalproperty']
        before = bytes(p.u.mem_read(properties, 36))
        p.release(106)  # Select 30 minutes with the physical right key.
        p.release(1)  # Original settings commit path.
        after = bytes(p.u.mem_read(properties, 36))
        self.assertEqual(before[:20], after[:20])
        self.assertEqual(before[24:], after[24:])
        self.assertEqual(readword(p, properties + 0x14), 1)
        self.assertEqual(readword(p, p.symbols['c10saveattr']), 1)
        self.assertFalse(tick(p, 1000))
        self.assertFalse(tick(p, 1800999))
        self.assertTrue(tick(p, 1801000))

    def test_simplified_traditional_and_english_menu_labels(self):
        for language, title in [(0, '睡眠定时关机'), (1, '睡眠定時關機'), (2, 'Sleep timer')]:
            with self.subTest(language=language):
                p = MenuProbe(language=language, selection=5)
                self.assertIn(title, [r['text'] for r in p.draw() if r['kind'] == 'label'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
