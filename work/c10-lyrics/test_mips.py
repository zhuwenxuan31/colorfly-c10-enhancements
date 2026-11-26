"""Execute the actual v72 play-screen call and new MIPS renderer with mocked SDL and I/O."""
from pathlib import Path
import json
import struct
import unittest

from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32, Uc
from unicorn.mips_const import *

HERE = Path(__file__).resolve().parent
ARTIFACT = HERE / 'build/ap.lyrics.dge'
META = json.loads((HERE / 'build/patch.json').read_text())
CALL, RETURN, SCREEN, SONG = 0x41a15c, 0x41a164, 0x21001000, 0x21002000

# Exercise the linkage stubs against the same GOT slots used by stock ap.dge.
GOT = {
    'malloc': 0x48dc, 'free': 0x45f4, 'open': 0x499c,
    'close': 0x476c, 'read': 0x4840, 'maprgb': 0x4814,
    'fill_rect': 0x4894, 'measure': 0x49d4, 'render': 0x46b8,
    'upper_blit': 0x47fc, 'free_surface': 0x4a00, 'flip': 0x4630,
}


class Player:
    def __init__(self):
        self.u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        self.u.mem_map(0x400000, 0x60000)
        self.u.mem_map(0x21000000, 0x100000)
        with ARTIFACT.open('rb') as file:
            for seg in ELFFile(file).iter_segments():
                if seg['p_type'] == 'PT_LOAD':
                    self.u.mem_write(seg['p_vaddr'], seg.data())
        self.stubs = {META['symbols']['orig_fstat64']: 'stat'}
        for i, (name, address) in enumerate(GOT.items()):
            target = 0x21008000 + i * 8
            self.word(0x440000 + address, target)
            self.stubs[target] = name
        self.files = {}
        self.position = 0
        self.opened = []
        self.renders = []
        self.panels = []
        self.blits = []
        self.frees = []
        self.flips = []
        self.nalloc = 0
        self.kind = 0o100644
        self.track('/mnt/memory/测试.flac')
        self.word(0x444b04, 0x21003000)
        self.word(0x444cbc, 100)
        self.u.mem_write(SCREEN, struct.pack('<4I', 0, SCREEN + 0x100, 400, 360))
        self.u.hook_add(UC_HOOK_CODE, self.hook)

    def word(self, ptr, value):
        self.u.mem_write(ptr, struct.pack('<I', value))

    def track(self, path, cue=False):
        self.u.mem_write(SONG, bytes(0x400))
        self.u.mem_write(SONG, path.encode() + b'\0')
        self.word(0x444a80, SONG)
        self.word(SONG + 0x338, 1 if cue else 0)

    def string(self, ptr):
        return bytes(self.u.mem_read(ptr, 512)).split(b'\0', 1)[0].decode()

    def hook(self, u, address, size, _):
        name = self.stubs.get(address)
        if not name:
            return
        a, b, c, d = (u.reg_read(x) for x in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        result = 0
        if name == 'malloc':
            self.nalloc += 1
            result = 0x21010000 if a < 32769 else 0x21030000
        elif name == 'free':
            pass
        elif name == 'open':
            path = self.string(a)
            self.opened.append(path)
            self.position = 0
            self.file = self.files.get(path)
            assert b == 0o2400200 and c == 0, (oct(b), c)
            result = 3 if self.file is not None else -1
        elif name == 'stat':
            self.word(b + 24, self.kind)
        elif name == 'read':
            data = self.file[self.position:self.position + min(c, 41)]
            self.position += len(data)
            if data:
                u.mem_write(b, data)
            result = len(data)
        elif name == 'maprgb':
            result = 0x7bff
        elif name == 'fill_rect':
            self.panels.append((a, tuple(struct.unpack('<hhHH', u.mem_read(b, 8))), c))
        elif name == 'measure':
            self.word(c, len(self.string(b)) * 15)
            self.word(d, 24)
        elif name == 'render':
            text = self.string(b)
            self.renders.append((text, c))
            result = 0x21050000 + len(self.renders) * 32
            u.mem_write(result, struct.pack('<4I', 0, 0, len(text) * 15, 24))
        elif name == 'upper_blit':
            self.blits.append((a, c, struct.unpack('<hhHH', u.mem_read(d, 8))[:2]))
        elif name == 'free_surface':
            self.frees.append(a)
        elif name == 'flip':
            self.flips.append(a)
            result = 7
        elif name != 'close':
            raise AssertionError(name)
        u.reg_write(UC_MIPS_REG_V0, result & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def draw(self, seconds=0):
        self.word(0x444cb8, seconds)
        self.u.reg_write(UC_MIPS_REG_SP, 0x210f0000)
        self.u.reg_write(UC_MIPS_REG_GP, 0x44c4d0)
        self.u.reg_write(UC_MIPS_REG_S2, SCREEN)
        self.u.emu_start(CALL, RETURN, count=1000000)
        assert self.u.reg_read(UC_MIPS_REG_PC) == RETURN
        assert self.u.reg_read(UC_MIPS_REG_SP) == 0x210f0000
        assert self.u.reg_read(UC_MIPS_REG_S2) == SCREEN
        assert self.u.reg_read(UC_MIPS_REG_V0) == 7


class LyricsTests(unittest.TestCase):
    def test_reload_on_track_switch_and_advance_skip_and_back(self):
        p = Player()
        p.files['/mnt/memory/测试.lrc'] = '[00:00]开场\n[00:02]第二句\n[00:04]第三句'.encode()
        for t, word in [(0, '开场'), (2, '第二句'), (8, '第三句'), (1, '开场')]:
            p.draw(t)
            self.assertIn((word, 0x00bdecff), p.renders)
        self.assertEqual(len(p.opened), 1)
        self.assertEqual(len(p.panels), 4)
        renders = len(p.renders)
        p.draw(1)
        self.assertEqual(len(p.renders), renders)
        p.track('/mnt/mmc/换歌.mp3')
        p.draw()
        self.assertEqual(len(p.panels), 5)
        self.assertEqual(p.opened, ['/mnt/memory/测试.lrc', '/mnt/mmc/换歌.lrc'])
        self.assertEqual(p.flips, [SCREEN] * 6)

    def test_got_slots_are_original_dynamic_imports(self):
        with ARTIFACT.open('rb') as file:
            elf = ELFFile(file)
            dyn = {tag.entry.d_tag: tag.entry.d_val
                   for tag in elf.get_section_by_name('.dynamic').iter_tags()}
            symbols = list(elf.get_section_by_name('.dynsym').iter_symbols())
            start = elf.get_section_by_name('.got')['sh_addr']
            slots = {start + 4 * (dyn['DT_MIPS_LOCAL_GOTNO'] + i - dyn['DT_MIPS_GOTSYM']): symbols[i].name
                     for i in range(dyn['DT_MIPS_GOTSYM'], len(symbols))}
            names = {'maprgb': 'SDL_MapRGB', 'fill_rect': 'SDL_FillRect', 'measure': 'TTF_SizeUTF8',
                     'render': 'TTF_RenderUTF8_Blended', 'upper_blit': 'SDL_UpperBlit',
                     'free_surface': 'SDL_FreeSurface', 'flip': 'SDL_Flip'}
            for name, address in GOT.items():
                self.assertEqual(slots[0x440000 + address], names.get(name, name))

    def test_absent_non_regular_and_cue_preserve_stock_flip(self):
        p = Player()
        p.draw(); p.draw()
        self.assertEqual(len(p.opened), 1)
        p.track('/mnt/mmc/歌曲.flac')
        p.files['/mnt/mmc/歌曲.lrc'] = b'[00:00]One'
        p.kind = 0o10600
        p.draw()
        self.assertEqual(p.position, 0)
        p.track('/mnt/mmc/另一个.flac', cue=True)
        p.draw()
        self.assertEqual(len(p.opened), 2)
        self.assertEqual(p.panels, [])
        self.assertEqual(p.flips, [SCREEN] * 4)


if __name__ == '__main__':
    unittest.main(verbosity=2)
