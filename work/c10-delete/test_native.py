"""Exercise the patched key entries and browse flip in the actual MIPS application."""
import json
import stat
import struct
import unittest
from pathlib import Path

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
from unicorn.mips_const import (
    UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_GP, UC_MIPS_REG_PC,
    UC_MIPS_REG_RA, UC_MIPS_REG_SP, UC_MIPS_REG_V0,
)

HERE = Path(__file__).resolve().parent / 'build'
DOWN, UP, FLIP = 0x426230, 0x425a30, 0x418ea0
STACK, RETURN, NODE, TRACK, SCREEN = 0x210f0000, 0x21001000, 0x21002000, 0x21003000, 0x21004000
PATH = '/mnt/memory/测试/歌曲.flac'
TRASH = '/mnt/memory/.c10-recycle/测试/歌曲.flac.deleted'


class Device:
    def __init__(self):
        self.cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        self.cpu.mem_map(0x400000, 0x60000)
        self.cpu.mem_map(0x21000000, 0x100000)
        with (HERE / 'ap.delete.dge').open('rb') as app:
            for seg in ELFFile(app).iter_segments():
                if seg['p_type'] == 'PT_LOAD':
                    self.cpu.mem_write(seg['p_vaddr'], seg.data())
        self.stubs = {0x433b28: 'stock_down', 0x433ad0: 'stock_up'}
        imports = {'malloc': 0x48dc, 'ticks': 0x48f0, 'maprgb': 0x4814, 'fill': 0x4894,
                   'text': 0x46b8, 'blit': 0x47fc, 'free_surface': 0x4a00, 'flip': 0x4630}
        for i, (name, slot) in enumerate(imports.items()):
            target = 0x21008000 + i * 8
            self.word(0x440000 + slot, target)
            self.stubs[target] = name
        symbols = json.loads((HERE / 'patch.json').read_text())['symbols']
        for name in ('lstat64', 'mkdir', 'rename'):
            self.stubs[symbols[f'delete_{name}']] = name
        self.cpu.hook_add(UC_HOOK_CODE, self.hook)
        self.word(0x444aa0, NODE)
        self.word(NODE + 0x10, 1)
        self.word(NODE + 0x30, TRACK)
        self.word(0x444b04, 0x21007000)
        self.word(0x444440, 2)
        self.cpu.mem_write(TRACK, PATH.encode() + b'\0')
        self.cpu.mem_write(SCREEN, struct.pack('<4I', 0, SCREEN + 0x100, 400, 360))
        self.now = 0
        self.texts = []
        self.forwarded = []
        self.renamed = []
        self.fs = {p: stat.S_IFDIR for p in ('/mnt', '/mnt/memory', '/mnt/memory/测试')}
        self.fs[PATH] = stat.S_IFREG

    def word(self, addr, value):
        self.cpu.mem_write(addr, struct.pack('<I', value))

    def string(self, addr):
        return self.cpu.mem_read(addr, 900).partition(b'\0')[0].decode()

    def hook(self, cpu, addr, _size, _data):
        name = self.stubs.get(addr)
        if name is None:
            return
        a, b = cpu.reg_read(UC_MIPS_REG_A0), cpu.reg_read(UC_MIPS_REG_A1)
        result = 0
        if name.startswith('stock_'):
            self.forwarded.append((name, a, b))
        elif name == 'malloc':
            result = 0x21010000
        elif name == 'ticks':
            result = self.now
        elif name == 'lstat64':
            mode = self.fs.get(self.string(a))
            if mode is None:
                result = -2
            else:
                self.word(b + 24, mode)
        elif name == 'mkdir':
            self.fs[self.string(a)] = stat.S_IFDIR
        elif name == 'rename':
            src, dst = self.string(a), self.string(b)
            assert src in self.fs and dst not in self.fs
            self.fs[dst] = self.fs.pop(src)
            self.renamed.append((src, dst))
        elif name == 'text':
            self.texts.append(self.string(b))
            result = 0x21060000
        elif name == 'flip':
            assert a == SCREEN
            result = 7
        cpu.reg_write(UC_MIPS_REG_V0, result & 0xffffffff)
        cpu.reg_write(UC_MIPS_REG_PC, cpu.reg_read(UC_MIPS_REG_RA))

    def call(self, address, a, b=0):
        cpu = self.cpu
        cpu.reg_write(UC_MIPS_REG_SP, STACK - (40 if address == FLIP else 0))
        cpu.reg_write(UC_MIPS_REG_GP, 0x44c4d0)
        cpu.reg_write(UC_MIPS_REG_RA, RETURN)
        cpu.reg_write(UC_MIPS_REG_A0, a)
        cpu.reg_write(UC_MIPS_REG_A1, b)
        cpu.emu_start(address, RETURN, count=1500000)
        assert cpu.reg_read(UC_MIPS_REG_PC) == RETURN
        assert cpu.reg_read(UC_MIPS_REG_SP) == STACK

    def press(self, button, time=0, repeated=0):
        self.now = time
        self.call(DOWN, button, repeated)

    def release(self, button, time=800):
        self.now = time
        self.call(UP, button)

    def draw(self, time=800):
        self.now = time
        self.call(FLIP, SCREEN)
        assert self.cpu.reg_read(UC_MIPS_REG_V0) == 7

    def choose_delete(self):
        self.press(106)
        self.release(106)
        self.release(108)
        self.release(106)


class NativeTests(unittest.TestCase):
    def test_short_press_delegates_both_original_events(self):
        device = Device()
        device.press(106)
        self.assertEqual(device.forwarded, [])
        device.release(106, 200)
        self.assertEqual(device.forwarded, [('stock_down', 106, 0), ('stock_up', 106, 0)])

    def test_long_press_opens_menu_and_selecting_delete_moves_song(self):
        device = Device()
        device.press(106)
        device.draw(720)
        self.assertIn('删除', device.texts)
        self.assertIn('歌曲.flac', device.texts)
        self.assertIn('移到回收站', device.texts)
        self.assertEqual(device.renamed, [])
        device.release(106)
        self.assertEqual(device.renamed, [])
        device.release(108)
        device.release(106)
        self.assertEqual(device.renamed, [(PATH, TRASH)])
        self.assertNotIn(PATH, device.fs)
        self.assertEqual(device.forwarded, [])

    def test_cancel_and_unrelated_screens_do_not_move_anything(self):
        device = Device()
        device.press(106)
        device.release(106)
        device.release(1)
        device.word(0x444b34, 3)
        device.press(106)
        device.release(106)
        self.assertEqual(device.forwarded, [('stock_down', 106, 0), ('stock_up', 106, 0)])
        self.assertEqual(device.renamed, [])

    def test_conflict_and_currently_playing_song_are_protected(self):
        for conflict in (True, False):
            with self.subTest(conflict=conflict):
                device = Device()
                if conflict:
                    device.fs['/mnt/memory/.c10-recycle'] = stat.S_IFDIR
                    device.fs['/mnt/memory/.c10-recycle/测试'] = stat.S_IFDIR
                    device.fs[TRASH] = stat.S_IFREG
                else:
                    device.word(0x444a80, TRACK)
                    device.word(0x444440, 1)
                device.choose_delete()
                self.assertEqual(device.renamed, [])
                self.assertIn(PATH, device.fs)


if __name__ == '__main__':
    unittest.main()
