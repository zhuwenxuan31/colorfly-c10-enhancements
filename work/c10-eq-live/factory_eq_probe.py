"""Run isolated original MPlayer EQ functions in Unicorn, never on hardware.

Only allocation/free/logging are intercepted. Native audio/filesystem/syscall
execution is rejected. This establishes DSP behavior, not device performance.
"""
from pathlib import Path
import hashlib
import io
import json
import math
import struct

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE, UC_HOOK_INTR
from unicorn.mips_const import *

BASE = Path(__file__).resolve().parent
BINARY = BASE.parent / 'c10-analysis/appfs/local/aplayer/mplayer'
SHA = '8e802544ed1d0e0eae5748b139c7ca260cce221d5cd61cb1478645083e8499c3'
RETURN = 0x10000000


class FactoryEQ:
    def __init__(self):
        blob = BINARY.read_bytes()
        assert hashlib.sha256(blob).hexdigest() == SHA
        e = ELFFile(io.BytesIO(blob))
        self.u = u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        pages = set()
        for seg in e.iter_segments():
            if seg['p_type'] != 'PT_LOAD':
                continue
            for page in range(seg['p_vaddr'] & ~4095,
                              (seg['p_vaddr'] + seg['p_memsz'] + 4095) & ~4095, 4096):
                if page not in pages:
                    u.mem_map(page, 4096)
                    pages.add(page)
            u.mem_write(seg['p_vaddr'], seg.data())
        u.mem_map(0x10000000, 0x400000)
        u.mem_map(0x7ff00000, 0x100000)
        self.heap = 0x10100000
        self.symbols = {s.name: s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()
                        if s['st_value']}
        self.stubs = {}
        for name in ['calloc', 'malloc', 'free', 'mp_msg']:
            self.stubs[self.symbols[name]] = name
        self.finished = False
        self.calls = []
        self.allocations = {}
        self.af = 0x10001000
        self.argument = 0x10002000
        self.gains = 0x10002100
        self.pcm = 0x10010000
        self.data = 0x10003000
        u.hook_add(UC_HOOK_CODE, self.hook)
        u.hook_add(UC_HOOK_INTR, self.trap)
        # The factory binary itself contains native FPU instructions.
        u.reg_write(UC_MIPS_REG_CP0_STATUS, u.reg_read(UC_MIPS_REG_CP0_STATUS) | 0x20000000)
        self.word(self.af, self.symbols['af_info_equalizer'])

    def word(self, address, value):
        self.u.mem_write(address, struct.pack('<I', value & 0xffffffff))

    def readword(self, address):
        return struct.unpack('<I', self.u.mem_read(address, 4))[0]

    def hook(self, u, address, size, data):
        if address == RETURN:
            self.finished = True
            u.emu_stop()
            return
        name = self.stubs.get(address)
        if not name:
            return
        a, b = [u.reg_read(r) for r in [UC_MIPS_REG_A0, UC_MIPS_REG_A1]]
        result = 0
        if name in {'calloc', 'malloc'}:
            length = a * b if name == 'calloc' else a
            assert 0 < length < 1000000
            result = self.heap
            self.heap += (length + 15) & ~15
            assert self.heap < 0x10400000
            self.allocations[result] = length
            u.mem_write(result, bytes(length))
        self.calls.append(name)
        u.reg_write(UC_MIPS_REG_V0, result)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def trap(self, u, number, data):
        raise AssertionError(f'Native exception/syscall {number} at {u.reg_read(UC_MIPS_REG_PC):x}')

    def call(self, entry, *args, count=5000000):
        self.finished = False
        self.u.reg_write(UC_MIPS_REG_SP, 0x7ffef000)
        self.u.reg_write(UC_MIPS_REG_RA, RETURN)
        self.u.reg_write(UC_MIPS_REG_T9, entry)
        for reg, value in zip([UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3], args):
            self.u.reg_write(reg, value)
        self.u.emu_start(entry, 0, count=count)
        assert self.finished, f'Instruction bound at {self.u.reg_read(UC_MIPS_REG_PC):x}'
        value = self.u.reg_read(UC_MIPS_REG_V0)
        return value if value < 0x80000000 else value - 0x100000000

    def open(self):
        assert self.call(0x442e44, self.af) == 1
        assert self.readword(self.af + 4) == 0x442f44
        assert self.readword(self.af + 12) == 0x442ce0

    def configure(self, gains, rate=44100, channels=2):
        assert len(gains) == 10
        self.u.mem_write(self.gains, struct.pack('<10f', *gains))
        for channel in range(channels):
            self.u.mem_write(self.argument, struct.pack('<II', self.gains, channel))
            assert self.call(0x442f44, self.af, 0x40001d00, self.argument) == 1
        self.rate, self.channels = rate, channels
        self.u.mem_write(self.data, struct.pack('<6I', self.pcm, 0, rate, channels, 0x1d, 4))
        result = self.call(0x442f44, self.af, 0x10000100, self.data)
        return result, struct.unpack('<6I', self.u.mem_read(self.readword(self.af + 20), 24))

    def process(self, samples):
        assert len(samples) % self.channels == 0
        raw = struct.pack('<' + 'f' * len(samples), *samples)
        assert len(raw) < 0xf0000
        self.u.mem_write(self.pcm, raw)
        self.u.mem_write(self.data, struct.pack('<6I', self.pcm, len(raw), self.rate,
                                              self.channels, 0x1d, 4))
        assert self.call(0x442ce0, self.af, self.data) == self.data
        return list(struct.unpack('<' + 'f' * len(samples), self.u.mem_read(self.pcm, len(raw))))


if __name__ == '__main__':
    p = FactoryEQ()
    p.open()
    result, fmt = p.configure([0] * 10)
    print(json.dumps({'open': True, 'reinit_result': result, 'filter_format': fmt,
                      'mocked_calls': p.calls, 'limits': 'isolated original EQ; not filter-chain negotiation or hardware'}, indent=2))
