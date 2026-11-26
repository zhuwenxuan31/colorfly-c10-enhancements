"""Execute original C10 MIPS timer branches offline. Never run host commands.

External calls are intercepted, not executed. The result proves branch behavior,
not successful unmounts, audio cleanup, settings persistence or physical power-off.
"""
import hashlib
import io
import json
from pathlib import Path
import struct

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.mips_const import (
    UC_MIPS_REG_A0, UC_MIPS_REG_GP, UC_MIPS_REG_PC, UC_MIPS_REG_RA,
    UC_MIPS_REG_S0, UC_MIPS_REG_S3, UC_MIPS_REG_S5, UC_MIPS_REG_S6,
    UC_MIPS_REG_SP, UC_MIPS_REG_V0,
)

BASE = Path(__file__).resolve().parent
IMAGE = (BASE / 'appfs/local/aplayer/ap.dge').read_bytes()
SHA = hashlib.sha256(IMAGE).hexdigest()
assert SHA == '7d5f35b9c35ff02aaf6d1a12eb6064af6814395d6b3da76ede8889c82a9b94fc'
GP = 0x44C4D0
RETURN = 0x2000F000


class Probe:
    def __init__(self, setting):
        elf = ELFFile(io.BytesIO(IMAGE))
        self.u = u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        pages = set()
        for seg in elf.iter_segments():
            if seg['p_type'] != 'PT_LOAD':
                continue
            for page in range(seg['p_vaddr'] & ~4095,
                              (seg['p_vaddr'] + seg['p_memsz'] + 4095) & ~4095, 4096):
                if page not in pages:
                    u.mem_map(page, 4096)
                    pages.add(page)
            u.mem_write(seg['p_vaddr'], seg.data())
        u.mem_map(0x20000000, 0x10000)
        u.mem_map(0x7FF00000, 0x100000)
        syms = list(elf.get_section_by_name('.dynsym').iter_symbols())
        tags = {t.entry.d_tag: t.entry.d_val
                for t in elf.get_section_by_name('.dynamic').iter_tags()}
        got = elf.get_section_by_name('.got')['sh_addr']
        self.calls = []
        self.stops = {RETURN}
        self.stopped = None
        self.stubs = {0x41E84C: 'mplayerclose'}
        for i in range(tags['DT_MIPS_GOTSYM'], len(syms)):
            sym = syms[i]
            if sym['st_info']['type'] == 'STT_FUNC' and sym['st_shndx'] == 'SHN_UNDEF':
                address = 0x20000000 + i * 16
                self.stubs[address] = sym.name
                self.word(got + 4 * (tags['DT_MIPS_LOCAL_GOTNO'] + i - tags['DT_MIPS_GOTSYM']), address)
        self.word(0x4463AC + 0x14, setting)
        u.reg_write(UC_MIPS_REG_GP, GP)
        u.reg_write(UC_MIPS_REG_SP, 0x7FFFF000)
        u.reg_write(UC_MIPS_REG_RA, RETURN)
        self.word(0x7FFFF010, GP)
        u.hook_add(UC_HOOK_CODE, self.hook)

    def word(self, addr, value):
        self.u.mem_write(addr, struct.pack('<I', value & 0xFFFFFFFF))

    def hook(self, u, address, size, data):
        if address in self.stops:
            self.stopped = address
            u.emu_stop()
            return
        if address not in self.stubs:
            return
        name = self.stubs[address]
        if name not in {'mplayerclose', 'puts'}:
            raise AssertionError('Unexpected intercepted external call: ' + name)
        event = {'call': name, 'mocked': True}
        if name == 'puts':
            ptr = u.reg_read(UC_MIPS_REG_A0)
            event['text'] = bytes(u.mem_read(ptr, 256)).split(b'\0', 1)[0].decode('utf8')
        self.calls.append(event)
        u.reg_write(UC_MIPS_REG_V0, 0)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def run(self, entry):
        self.u.emu_start(entry, 0, count=5000)
        assert self.stopped is not None, 'Instruction bound reached'


def getter(setting):
    p = Probe(setting)
    p.run(0x41C9B0)
    return p.u.reg_read(UC_MIPS_REG_V0)


def decision(setting, state, elapsed_ms):
    p = Probe(setting)
    p.word(0x444440, state)
    p.u.reg_write(UC_MIPS_REG_S0, elapsed_ms)
    p.u.reg_write(UC_MIPS_REG_S3, 1)
    p.u.reg_write(UC_MIPS_REG_S5, 0)
    p.u.reg_write(UC_MIPS_REG_S6, 0x440000)
    p.stops = {0x41B964, 0x41BA48}
    p.run(0x41B918)
    shutdown = p.stopped == 0x41BA48
    return {'setting': setting, 'playing_state': state, 'elapsed_ms': elapsed_ms,
            'shutdown_branch': shutdown, 'stop_address': hex(p.stopped)}


def shutdown_entry():
    p = Probe(1)
    p.word(0x44446C, 1)
    p.word(0x444B78, 1)
    p.u.reg_write(UC_MIPS_REG_S6, 0x440000)
    p.stops = {0x41BA84}
    p.run(0x41BA48)
    assert p.calls == [{'call': 'mplayerclose', 'mocked': True},
                       {'call': 'puts', 'mocked': True, 'text': 'auto poweroff '}]
    assert struct.unpack('<I', p.u.mem_read(0x44446C, 4))[0] == 0
    assert struct.unpack('<I', p.u.mem_read(0x444B78, 4))[0] == 0
    return {'calls': p.calls, 'main_loop_runflag': 0, 'shutdown_animation_flag': 0}


def main():
    values = [getter(x) for x in range(4)]
    assert values == [0, 300, 600, 1200]
    cases = [decision(0, 2, 7200000), decision(1, 1, 7200000),
             decision(1, 2, 299999), decision(1, 2, 300000),
             decision(1, 2, 300001), decision(2, 2, 600001),
             decision(3, 2, 1200001)]
    assert [c['shutdown_branch'] for c in cases] == [False, False, False, False, True, True, True]
    print(json.dumps({'original_app_sha256': SHA, 'setting_seconds': values,
                      'cases': cases, 'original_shutdown_entry': shutdown_entry(),
                      'limits': 'Original instructions only; mocked mplayerclose/puts; '
                      'not a timed-shutdown patch or on-device validation. No host commands, '
                      'USB writes, firmware changes or physical shutdown performed.'},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
