"""Build an offline-only stock application candidate; never access USB."""
from pathlib import Path
import hashlib
import io
import json
import struct

from elftools.elf.elffile import ELFFile

BASE = Path(__file__).resolve().parent
STOCK = BASE.parent / 'c10-analysis/appfs/local/aplayer/ap.dge'
SHA = '7d5f35b9c35ff02aaf6d1a12eb6064af6814395d6b3da76ede8889c82a9b94fc'


def jump(target):
    assert target % 4 == 0 and target >> 28 == 0
    return 0x08000000 | (target >> 2)


def make_patch():
    original = STOCK.read_bytes()
    assert hashlib.sha256(original).hexdigest() == SHA
    result = bytearray(original)
    payload = ELFFile(io.BytesIO((BASE / 'payload.elf').read_bytes()))
    section = payload.get_section_by_name('.payload')
    assert section['sh_addr'] == 0x433670
    blob = section.data()
    assert len(blob) < 0x34000 - 0x33670
    for sec in payload.iter_sections():
        if sec['sh_flags'] & 2 and sec['sh_size']:
            assert sec.name in {'.payload', '.got'}, sec.name
        assert sec['sh_type'] not in {'SHT_REL', 'SHT_RELA'}, 'Unresolved relocation'
    symbols = {s.name: s['st_value'] for s in payload.get_section_by_name('.symtab').iter_symbols()}
    for s in payload.get_section_by_name('.symtab').iter_symbols():
        assert not (s.name and s['st_shndx'] == 'SHN_UNDEF'), s.name
    edits = []

    def change(offset, expected, new, purpose):
        assert len(expected) == len(new)
        assert original[offset:offset + len(expected)] == expected, purpose
        result[offset:offset + len(new)] = new
        edits.append({'offset': offset, 'size': len(new), 'purpose': purpose,
                      'before_hex': expected.hex(), 'after_hex': new.hex()})

    elf = ELFFile(io.BytesIO(original))
    for i, seg in enumerate(elf.iter_segments()):
        if seg['p_type'] != 'PT_LOAD':
            continue
        header = elf['e_phoff'] + i * elf['e_phentsize']
        if seg['p_vaddr'] == 0x400000:
            end = 0x33670 + len(blob)
            assert seg['p_filesz'] == seg['p_memsz'] == 0x33664
            change(header + 16, struct.pack('<II', 0x33664, 0x33664),
                   struct.pack('<II', end, end), 'map new read/execute code in original zero padding')
        elif seg['p_vaddr'] == 0x444000:
            assert seg['p_memsz'] == 0x2be8
            change(header + 20, struct.pack('<I', 0x2be8), struct.pack('<I', 0x2c00),
                   'reserve zero initialized timer state at 0x446bf0..0x446bfb')
        else:
            raise AssertionError('Unexpected PT_LOAD')
    change(0x33670, bytes(len(blob)), blob, 'freestanding MIPS timer and USB cancel code')

    start, end = 0x41b918, 0x41b964
    hook = [0x02002021, jump(symbols['c10_sleep_tick']) | 0x04000000, 0]
    branch_pc = start + 4 * len(hook)
    hook += [0x14400000 | (((0x41ba48 - branch_pc - 4) // 4) & 0xffff),
             0, jump(end), 0]
    hook += [0] * ((end - start) // 4 - len(hook))
    # Exact stock block validated through source SHA and the unmodified gate probe.
    change(start - 0x400000, original[start - 0x400000:end - 0x400000],
           struct.pack('<' + 'I' * len(hook), *hook), 'replace idle-off test with sleep deadline test')
    change(0x1b788, struct.pack('<II', 0x8f908134, 0x8f9980a8),
           struct.pack('<II', jump(symbols['c10_sleep_usb_entry']) | 0x04000000, 0),
           'cancel on original USB-connected branch and replay the original two loads')

    def text(address, before, after):
        old = before.encode('utf8') + b'\0'
        new = after.encode('utf8') + b'\0'
        assert len(new) <= len(old)
        change(address - 0x400000, old, new.ljust(len(old), b'\0'), 'settings label: ' + after)

    text(0x432674, '无输出自动关机时间', '睡眠定时关机')
    text(0x432690, '無輸出自動關機時間', '睡眠定時關機')
    text(0x4326ac, 'Auto-Off time', 'Sleep timer')
    # Each original string has 8 bytes before the next one; do not change pointers.
    for address, old, new in [(0x431d24, '5min', '30min'),
                              (0x431d2c, '10min', '60min'),
                              (0x431d34, '20min', '90min')]:
        off = address - 0x400000
        before = original[off:off + 8]
        assert before.split(b'\0', 1)[0].decode() == old
        change(off, before, (new.encode() + b'\0').ljust(8, b'\0'), 'timer duration label: ' + new)
    allowed = {x for edit in edits for x in range(edit['offset'], edit['offset'] + edit['size'])}
    assert len(original) == len(result)
    assert all(i in allowed for i, (a, b) in enumerate(zip(original, result)) if a != b)
    return bytes(result), {'stock_sha256': SHA,
                           'candidate_sha256': hashlib.sha256(result).hexdigest(),
                           'symbols': {k: v for k, v in symbols.items() if k.startswith('c10_')},
                           'edits': edits, 'status': 'OFFLINE ONLY; not a firmware update or hardware validated'}


if __name__ == '__main__':
    binary, report = make_patch()
    out = BASE / 'build'
    out.mkdir(exist_ok=True)
    (out / 'ap.sleep-candidate.dge').write_bytes(binary)
    (out / 'patch-manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'edits'}, ensure_ascii=False, indent=2))
