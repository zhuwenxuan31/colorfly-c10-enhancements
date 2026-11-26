"""Apply three app-only hooks to the exact C10 v74 application binary."""
import hashlib
import io
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'c10-lyrics/build/ap.lyrics.dge'
BASE_SHA = 'ddba9d4a960be4d2e5ab5eba06f457501a861f110d9176f13ee5e51e82b621fb'
HOOKS = {
    0x426230: (0x0810ceca, 0, 'c10_delete_down'),
    0x425a30: (0x0810ceb4, 0, 'c10_delete_up'),
    0x418ea0: (0x03200008, 0x27bd0028, 'c10_delete_flip'),
}


def main():
    original = BASE.read_bytes()
    assert hashlib.sha256(original).hexdigest() == BASE_SHA
    elf = ELFFile(io.BytesIO(original))
    module_elf = ELFFile(io.BytesIO((HERE / 'build/module.elf').read_bytes()))
    module = module_elf.get_section_by_name('.delete')
    assert [s.name for s in module_elf.iter_sections() if s['sh_flags'] & 2 and s['sh_size']] == ['.delete']
    symbols = {}
    for symbol in module_elf.get_section_by_name('.symtab').iter_symbols():
        if symbol.name:
            assert symbol['st_shndx'] != 'SHN_UNDEF', symbol.name
            symbols[symbol.name] = symbol['st_value']
    assert module['sh_addr'] == symbols['c10_delete_down'] == 0x457000
    assert module['sh_addr'] + module['sh_size'] < 0x460000
    assert not any(s['sh_type'] in {'SHT_REL', 'SHT_RELA'} for s in module_elf.iter_sections())

    result = bytearray(original)
    patches = set()
    for address, (instruction, delay_slot, entry) in HOOKS.items():
        offset, = elf.address_offsets(address, 8)
        assert struct.unpack_from('<2I', original, offset) == (instruction, delay_slot)
        struct.pack_into('<I', result, offset, 0x08000000 | (symbols[entry] >> 2))
        patches.update(range(offset, offset + 4))
    for index, seg in enumerate(elf.iter_segments()):
        if seg['p_type'] == 'PT_LOAD' and seg['p_vaddr'] == 0x450000:
            assert seg['p_flags'] == 5 and seg['p_align'] == 65536
            assert seg['p_offset'] + seg['p_filesz'] == len(original)
            assert seg['p_filesz'] == seg['p_memsz']
            offset = seg['p_offset'] + module['sh_addr'] - seg['p_vaddr']
            assert offset >= len(original)
            size = offset + module['sh_size'] - seg['p_offset']
            header = elf['e_phoff'] + index * elf['e_phentsize'] + 16
            struct.pack_into('<II', result, header, size, size)
            patches.update(range(header, header + 8))
            result.extend(bytes(offset - len(original)))
            result.extend(module.data())
            break
    else:
        raise AssertionError('Missing v74 RX segment')
    assert all(a == b or i in patches for i, (a, b) in enumerate(zip(original, result)))
    out = HERE / 'build'
    (out / 'ap.delete.dge').write_bytes(result)
    report = {'before': BASE_SHA, 'after': hashlib.sha256(result).hexdigest(), 'symbols': symbols}
    (out / 'patch.json').write_text(json.dumps(report, indent=2) + '\n')
    print('App patch SHA-256', report['after'])


if __name__ == '__main__':
    main()
