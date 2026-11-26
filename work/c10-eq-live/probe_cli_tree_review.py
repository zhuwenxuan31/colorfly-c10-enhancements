"""Independent offline CLI/tree/iterator check; never runs audio or host IO.

Actual factory command parser, play-tree storage/cleanup/iterator, and af*
string-list parser execute. Config registry lookup/check and push/pop are
fixture stubs. The af-add setter is routed to its real registered option
parser, with the REAL af_cfg+4 as destination. This does not replace the
separate full config-registry/main-chain investigation.
"""
import json
from probe_filter_chain import Pipeline
from unicorn.mips_const import *


class TreeProbe(Pipeline):
    def __init__(self):
        super().__init__([])
        self.events = []
        for name in ['strcmp', 'strncmp', 'strlen', 'strdup', 'strstr',
                     'strchr', 'strrchr', 'strcpy', 'strncpy', 'strcat',
                     'm_config_get_option', 'm_config_check_option',
                     'm_config_set_option', 'm_config_push', 'm_config_pop']:
            if name in self.symbols:
                self.stubs[self.symbols[name]] = name

    def cstring(self, address):
        out = bytearray()
        for offset in range(16384):
            value = self.u.mem_read(address + offset, 1)[0]
            if not value:
                return bytes(out)
            out.append(value)
        raise AssertionError('unterminated fixture string')

    def allocate(self, raw):
        address = self.heap
        self.heap += (len(raw) + 15) & ~15
        assert self.heap < 0x10400000
        self.allocations[address] = len(raw)
        self.u.mem_write(address, raw)
        return address

    def hook(self, u, address, size, data):
        if address == 0x10007000:
            old_sp, old_ra = self.setter_return
            u.reg_write(UC_MIPS_REG_SP, old_sp)
            u.reg_write(UC_MIPS_REG_PC, old_ra)
            return
        name = self.stubs.get(address)
        if name not in {'strcmp', 'strncmp', 'strlen', 'strdup', 'strstr',
                        'strchr', 'strrchr', 'strcpy', 'strncpy', 'strcat',
                        'm_config_get_option', 'm_config_check_option',
                        'm_config_set_option', 'm_config_push', 'm_config_pop'}:
            return super().hook(u, address, size, data)
        a, b, c = [u.reg_read(r) for r in
                   [UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2]]
        if name == 'm_config_get_option':
            assert self.cstring(b) == b'af-add'
            result = 0xfd3e28
        elif name == 'm_config_check_option':
            assert self.cstring(b) == b'af-add'
            self.events.append(['check', self.cstring(b).decode()])
            result = 1
        elif name == 'm_config_set_option':
            assert self.cstring(b) == b'af-add'
            self.events.append(['set', self.cstring(b).decode(), self.cstring(c).decode()])
            # Keep the original iterator's return address; run the actual
            # registered af* parser against the original global list pointer.
            u.reg_write(UC_MIPS_REG_A0, 0xfd3e28)
            u.reg_write(UC_MIPS_REG_A3, 0xfdad18)
            old_sp = u.reg_read(UC_MIPS_REG_SP)
            self.setter_return = (old_sp, u.reg_read(UC_MIPS_REG_RA))
            u.reg_write(UC_MIPS_REG_SP, old_sp - 32)
            self.word(old_sp - 32 + 16, 0)
            u.reg_write(UC_MIPS_REG_RA, 0x10007000)
            u.reg_write(UC_MIPS_REG_T9, 0x4330c0)
            u.reg_write(UC_MIPS_REG_PC, 0x4330c0)
            return
        elif name in ['m_config_push', 'm_config_pop']:
            self.events.append([name])
            result = 0
        elif name in ['strcmp', 'strncmp']:
            left, right = self.cstring(a), self.cstring(b)
            if name == 'strncmp':
                left, right = left[:c], right[:c]
            result = (left > right) - (left < right)
        elif name == 'strlen':
            result = len(self.cstring(a))
        elif name == 'strdup':
            result = self.allocate(self.cstring(a) + b'\0')
        elif name in ['strstr', 'strchr', 'strrchr']:
            raw = self.cstring(a)
            needle = self.cstring(b) if name == 'strstr' else bytes([b & 255])
            index = raw.rfind(needle) if name == 'strrchr' else raw.find(needle)
            if name != 'strstr' and b & 255 == 0:
                index = len(raw)
            result = 0 if index < 0 else a + index
        elif name in ['strcpy', 'strncpy', 'strcat']:
            raw = self.cstring(b)
            if name == 'strncpy':
                raw = (raw + bytes(c))[:c]
            else:
                raw += b'\0'
            destination = a + len(self.cstring(a)) if name == 'strcat' else a
            u.mem_write(destination, raw)
            result = a
        else:
            return super().hook(u, address, size, data)
        u.reg_write(UC_MIPS_REG_V0, result & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def filters(self):
        result = []
        array = self.readword(0xfdad18)
        if array:
            for index in range(16):
                pointer = self.readword(array + index * 4)
                if not pointer:
                    break
                result.append(self.cstring(pointer).decode())
        return result


def run(arguments):
    p = TreeProbe()
    argv = 0x10009000
    for index, argument in enumerate(arguments):
        p.word(argv + index * 4, p.allocate(argument.encode() + b'\0'))
    p.word(argv + len(arguments) * 4, 0)
    tree = p.call(p.symbols['m_config_parse_mp_command_line'],
                  0x10008000, len(arguments), argv, count=1000000)
    after_parse = p.filters()
    tree = p.call(p.symbols['play_tree_cleanup'], tree, count=1000000)
    iterator = p.call(p.symbols['play_tree_iter_new'], tree, 0x10008000,
                      count=1000000)
    result = p.call(p.symbols['play_tree_iter_step'], iterator, 0, 0,
                    count=1000000)
    after_step = p.filters()
    expected = arguments[arguments.index('-af-add') + 1].split(',')
    assert result == 1 and after_step == expected, (result, after_step, p.events)
    return {'argv': arguments, 'after_parse': after_parse,
            'iterator_result': result, 'after_step': after_step,
            'events': p.events}


if __name__ == '__main__':
    value = 'equalizer=0:0:-1:-3:-4:-4:-3:-3:-3:-3,volume=0.0:0:0'
    for arguments in [['mplayer', '-af-add', value, 'file.wav'],
                      ['mplayer', 'file.wav', '-af-add', value]]:
        print(json.dumps(run(arguments), ensure_ascii=False), flush=True)
