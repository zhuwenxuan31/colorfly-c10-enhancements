"""Original MPlayer whole libaf negotiation/PCM path in offline MIPS emulator."""
from factory_eq_probe import FactoryEQ
import json
import math
import re
import struct
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3, UC_MIPS_REG_SP, UC_MIPS_REG_V0, UC_MIPS_REG_PC, UC_MIPS_REG_RA


class Pipeline(FactoryEQ):
    def __init__(self, filters, rate=44100, sample_format=9, bps=2):
        super().__init__()
        self.rate, self.sample_format, self.bps = rate, sample_format, bps
        for name in ['realloc', 'memcpy', 'memmove', 'memset', 'sscanf', 'strcasecmp', 'strncasecmp']:
            self.stubs[self.symbols[name]] = name
        self.stream = 0x10004000
        self.list = 0x10005000
        self.string_area = 0x10005100
        pos = self.string_area
        for index, text in enumerate(filters):
            raw = text.encode() + b'\0'
            self.u.mem_write(pos, raw)
            self.word(self.list + 4 * index, pos)
            pos += len(raw)
        self.word(self.list + 4 * len(filters), 0)
        self.u.mem_write(self.stream + 8, struct.pack('<6I', 0, 0, rate, 2, sample_format, bps))
        self.u.mem_write(self.stream + 32, struct.pack('<6I', 0, 0, rate, 2, sample_format, bps))
        self.word(self.stream + 56, 1)
        self.word(self.stream + 60, self.list)

    def hook(self, u, address, size, data):
        name = self.stubs.get(address)
        if name not in {'realloc', 'memcpy', 'memmove', 'memset', 'sscanf', 'strcasecmp', 'strncasecmp'}:
            return super().hook(u, address, size, data)
        a, b, c = [u.reg_read(reg) for reg in [UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2]]
        if name in {'strcasecmp', 'strncasecmp'}:
            left=bytes(u.mem_read(a, 512)).split(b'\0',1)[0].lower()
            right=bytes(u.mem_read(b, 512)).split(b'\0',1)[0].lower()
            if name=='strncasecmp':left,right=left[:c],right[:c]
            result=(left>right)-(left<right)
        elif name == 'sscanf':
            text = bytes(u.mem_read(a, 256)).split(b'\0', 1)[0].decode()
            fmt = bytes(u.mem_read(b, 256)).split(b'\0', 1)[0].decode()
            types = re.findall(r'%([fid])', fmt)
            assert fmt == ':'.join('%' + t for t in types), fmt
            fields = text.split(':')
            pointers = [c, u.reg_read(UC_MIPS_REG_A3)]
            pointers += [self.readword(u.reg_read(UC_MIPS_REG_SP) + 16 + i * 4) for i in range(max(0, len(types) - 2))]
            result = 0
            for value, typ, ptr in zip(fields, types, pointers):
                u.mem_write(ptr, struct.pack('<f' if typ == 'f' else '<i', float(value) if typ == 'f' else int(value)))
                result += 1
        elif name == 'realloc':
            assert 0 < b < 1000000
            result = self.heap
            self.heap += (b + 15) & ~15
            assert self.heap < 0x10400000
            u.mem_write(result, bytes(b))
            if a:
                old = self.allocations[a]
                u.mem_write(result, bytes(u.mem_read(a, min(old, b))))
            self.allocations[result] = b
        elif name in {'memcpy', 'memmove'}:
            u.mem_write(a, bytes(u.mem_read(b, c)))
            result = a
        else:
            u.mem_write(a, bytes([b & 255]) * c)
            result = a
        self.calls.append(name)
        u.reg_write(UC_MIPS_REG_V0, result & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def initialize(self):
        return self.call(self.symbols['af_init'], self.stream, count=15000000)

    def graph(self):
        result = []
        p = self.readword(self.stream)
        while p:
            assert len(result) < 20
            info = self.readword(p)
            name = self.readword(info + 4)
            text = bytes(self.u.mem_read(name, 64)).split(b'\0', 1)[0].decode()
            fmt = struct.unpack('<6I', self.u.mem_read(self.readword(p + 20), 24))
            result.append({'name': text, 'rate': fmt[2], 'channels': fmt[3], 'format': fmt[4], 'bps': fmt[5]})
            p = self.readword(p + 24)
        return result

    def process_s16(self, samples):
        assert self.bps == 2 and self.sample_format == 9
        return self.process_pcm(samples)

    def process_pcm(self, samples):
        raw = b''.join(int(s).to_bytes(self.bps, 'little', signed=True) for s in samples)
        self.u.mem_write(self.pcm, raw)
        self.u.mem_write(self.data, struct.pack('<6I', self.pcm, len(raw), self.rate, 2, self.sample_format, self.bps))
        result = self.call(self.symbols['af_play'], self.stream, self.data, count=15000000)
        fmt = struct.unpack('<6I', self.u.mem_read(result, 24))
        assert fmt[2:] == (self.rate, 2, self.sample_format, self.bps), fmt
        audio = bytes(self.u.mem_read(fmt[0], fmt[1]))
        return fmt, tuple(int.from_bytes(audio[i:i+self.bps], 'little', signed=True)
                          for i in range(0, len(audio), self.bps))


if __name__ == '__main__':
    p = Pipeline(['equalizer=0:0:0:0:0:0:0:0:0:0', 'volume=-9:0:0'])
    ret = p.initialize()
    assert ret == 0, ret
    graph = p.graph()
    samples = [value for i in range(128) for value in [int(1000 * math.sin(2 * math.pi * 1000 * i / 44100)), 0]]
    fmt, audio = p.process_s16(samples)
    assert not any(audio[1::2])
    assert any(audio[0::2])
    print(json.dumps({'init': ret, 'graph': graph, 'output': {'bytes': fmt[1], 'rate': fmt[2], 'channels': fmt[3], 'format': fmt[4], 'bps': fmt[5]},
                      'left_nonzero_right_zero': True, 'max_abs_sample': max(map(abs, audio)),
                      'limits': 'actual original libaf code; allocation/memory/log functions and colon-number sscanf mocked; no hardware, throughput or full-file decode validation'}, indent=2))
