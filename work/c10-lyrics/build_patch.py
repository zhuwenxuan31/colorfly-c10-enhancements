"""Append the lyrics renderer to the v72 app's existing RX segment."""
import hashlib
import io
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'c10-eq-live/build/ap.eq-candidate.dge'
BASE_SHA = 'beca3dedeef9b191dd6f71e6b72274c8a9b3eb09fbe50266cbb77d640a3fb2ff'
HOOK = 0x41a15c
ENTRY = 0x455000


def main():
    original = BASE.read_bytes()
    assert hashlib.sha256(original).hexdigest() == BASE_SHA
    elf = ELFFile(io.BytesIO(original))
    compiled = ELFFile(io.BytesIO((HERE / 'module.elf').read_bytes()))
    module = compiled.get_section_by_name('.lyrics')
    symbols = {}
    for sym in compiled.get_section_by_name('.symtab').iter_symbols():
        assert not (sym.name and sym['st_shndx'] == 'SHN_UNDEF'), sym.name
        if sym.name:
            symbols[sym.name] = sym['st_value']
    assert symbols['lyrics_flip'] == module['sh_addr'] == compiled.header['e_entry'] == ENTRY
    assert 0 < module['sh_size'] < 0x9000
    assert [s.name for s in compiled.iter_sections() if s['sh_flags'] & 2 and s['sh_size']] == ['.lyrics']
    assert not any(s['sh_type'] in {'SHT_REL', 'SHT_RELA'} for s in compiled.iter_sections())

    result = bytearray(original)
    for index, segment in enumerate(elf.iter_segments()):
        if segment['p_type'] == 'PT_LOAD' and segment['p_vaddr'] == 0x450000:
            assert segment['p_flags'] == 5 and segment['p_align'] == 65536
            assert segment['p_offset'] + segment['p_filesz'] == len(original)
            assert segment['p_filesz'] == segment['p_memsz'] == 0x4d54
            off = segment['p_offset'] + ENTRY - segment['p_vaddr']
            size = off + module['sh_size'] - segment['p_offset']
            header = elf['e_phoff'] + index * elf['e_phentsize']
            struct.pack_into('<II', result, header + 16, size, size)
            result.extend(bytes(off - len(result)))
            result.extend(module.data())
            break
    else:
        raise AssertionError('Missing EQ executable segment')

    offset = HOOK - 0x400000
    assert result[offset:offset + 8] == bytes.fromhex('09f8200321204002')
    struct.pack_into('<I', result, offset, 0x0c000000 | (ENTRY >> 2))
    assert all(original[i] == result[i] for i in range(len(original))
               if not (offset <= i < offset + 4 or header + 16 <= i < header + 24))
    out = HERE / 'build'
    out.mkdir(exist_ok=True)
    (out / 'ap.lyrics.dge').write_bytes(result)
    report = {'before': BASE_SHA, 'after': hashlib.sha256(result).hexdigest(),
              'playback_flip_call': hex(HOOK), 'symbols': symbols}
    (out / 'patch.json').write_text(json.dumps(report, indent=2) + '\n')
    print('App patch SHA-256', report['after'])


if __name__ == '__main__':
    main()
