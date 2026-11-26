"""Offline-only independent sleep + untouched original idle menu patch."""
from pathlib import Path
import hashlib
import io
import json
import struct
from elftools.elf.elffile import ELFFile

BASE = Path(__file__).resolve().parent
STOCK = BASE.parent / 'c10-analysis/appfs/local/aplayer/ap.dge'
SHA = '7d5f35b9c35ff02aaf6d1a12eb6064af6814395d6b3da76ede8889c82a9b94fc'


def jump(address):
    assert address % 4 == 0 and address >> 28 == 0
    return 0x08000000 | (address >> 2)


def build():
    original = STOCK.read_bytes()
    assert hashlib.sha256(original).hexdigest() == SHA
    data = bytearray(original)
    elf = ELFFile(io.BytesIO(original))
    payload = ELFFile(io.BytesIO((BASE / 'payload.elf').read_bytes()))
    section = payload.get_section_by_name('.payload')
    assert section['sh_addr'] == 0x433670
    blob = section.data()
    assert len(blob) <= 0x34000 - 0x33670, 'Payload exceeds original zero padding'
    for s in payload.iter_sections():
        if s['sh_flags'] & 2 and s['sh_size']:
            assert s.name in {'.payload', '.got'}, s.name
        assert s['sh_type'] not in {'SHT_REL', 'SHT_RELA'}
    symbols = {}
    for s in payload.get_section_by_name('.symtab').iter_symbols():
        assert not (s.name and s['st_shndx'] == 'SHN_UNDEF'), s.name
        symbols[s.name] = s['st_value']
    edits = []

    def change(offset, before, after, purpose):
        assert len(before) == len(after)
        assert original[offset:offset + len(before)] == before, purpose
        assert data[offset:offset + len(before)] == before, 'Overlapping edits: ' + purpose
        data[offset:offset + len(after)] = after
        edits.append({'offset': offset, 'size': len(after), 'purpose': purpose,
                      'before_hex': before.hex(), 'after_hex': after.hex()})

    def words(address, before, after, purpose):
        change(address - 0x400000, struct.pack('<' + 'I' * len(before), *before),
               struct.pack('<' + 'I' * len(after), *after), purpose)

    for i, seg in enumerate(elf.iter_segments()):
        if seg['p_type'] != 'PT_LOAD':
            continue
        header = elf['e_phoff'] + i * elf['e_phentsize']
        if seg['p_vaddr'] == 0x400000:
            end = 0x33670 + len(blob)
            assert seg['p_filesz'] == seg['p_memsz'] == 0x33664
            change(header + 16, struct.pack('<II', 0x33664, 0x33664),
                   struct.pack('<II', end, end), 'map new RX code in original zero padding')
        elif seg['p_vaddr'] == 0x444000:
            assert seg['p_memsz'] == 0x2be8
            change(header + 20, struct.pack('<I', 0x2be8), struct.pack('<I', 0x2c10),
                   'new independent sleep state; original idle property stays unchanged')
        else:
            raise AssertionError('Unexpected PT_LOAD')
    change(0x33670, bytes(len(blob)), blob, 'freestanding timer, menu bridges and new labels')
    words(0x41b918, [0x8f9983d4, 0],
          [jump(symbols['c10_power_checks_entry']), 0],
          'check sleep then replay original idle getter and untouched idle decision')
    words(0x41b788, [0x8f908134, 0x8f9980a8],
          [jump(symbols['c10_sleep_usb_entry']) | 0x04000000, 0],
          'USB cancels sleep only and replays original two loads')
    words(0x425758, [0x3c1c0045, 0x3c060044],
          [jump(symbols['c10_menu_option_entry']), 0],
          'new menu option index10; replay old code for original indices0..9')
    words(0x426024, [0x8e430014, 0x8e2b0014],
          [jump(symbols['c10_menu_commit_entry']), 0],
          'commit independent sleep and replay original idle-setting commit')
    words(0x4256ec, [0x8f988134, 0x8f8f8438],
          [jump(symbols['c10_menu_discard_entry']), 0],
          'discard uncommitted sleep edits with original dirty-navigation cancellation')
    words(0x4256a4, [0x24020009], [0x2402000a], 'down navigation maximum index10')
    words(0x4256e0, [0x240e0009], [0x240e000a], 'up navigation wraps to index10')
    words(0x42784c, [0x2e51000a], [0x2e51000b], 'draw dispatch accepts eleven items')
    table = symbols['c10_menu_dispatch_table']
    assert table >> 16 == 0x43 and table & 0xffff < 0x8000
    words(0x427860, [0x272c2a20], [0x272c0000 | (table & 0xffff)], 'extended main-menu dispatch table')
    offset = table - section['sh_addr']
    assert blob[offset:offset + 40] == original[0x32a20:0x32a48]
    assert struct.unpack_from('<I', blob, offset + 40)[0] == (symbols['c10_sleep_draw_entry'] - 0x44c4d0) & 0xffffffff
    words(0x4277a8, [0x3c0438e3], [0x3c04cccc], 'scrollbar divide by ten: multiplier high')
    words(0x4277b0, [0x34828e39], [0x3482cccd], 'scrollbar divide by ten: multiplier low')
    words(0x4277d8, [0x0003f042], [0x0003f0c2], 'scrollbar divide by ten: shift3')
    for begin, end in [(0x41b920, 0x41b964), (0x41c9b0, 0x41ca00),
                       (0x431d24, 0x431d3c), (0x432674, 0x432768)]:
        assert data[begin - 0x400000:end - 0x400000] == original[begin - 0x400000:end - 0x400000]
    allowed = {i for edit in edits for i in range(edit['offset'], edit['offset'] + edit['size'])}
    assert len(original) == len(data)
    assert all(i in allowed for i, (old, new) in enumerate(zip(original, data)) if old != new)
    report = {'status': 'offline dual-timer candidate; not installed',
              'stock_sha256': SHA, 'candidate_sha256': hashlib.sha256(data).hexdigest(),
              'payload_bytes': len(blob), 'symbols': {k: v for k, v in symbols.items() if k.startswith('c10_')},
              'original_idle_logic_getter_labels_unchanged': True, 'edits': edits}
    out = BASE / 'build'
    out.mkdir(exist_ok=True)
    (out / 'ap.dual-candidate.dge').write_bytes(data)
    (out / 'patch-manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'edits'}, indent=2))


if __name__ == '__main__':
    build()
