"""Build and audit the probe module against the known C10 kernel ABI."""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from elftools.elf.elffile import ELFFile

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
OUT = HERE / 'build'
STOCK = WORK / 'c10-analysis/appfs/local/modules/g_audio.ko'
ZIG = WORK / 'c10-prototype/toolchain/zig-macos-aarch64-0.13.0/zig'
IMPORTS = {'bus_find_device_by_name', 'i2c_bus_type', 'i2c_verify_client',
           'i2c_smbus_read_byte_data', 'put_device', 'printk'}
NAME = 'c10_dac_probe'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    subprocess.run(args, check=True, cwd=HERE)


def descriptor(elf):
    section = elf.get_section_by_name('.gnu.linkonce.this_module')
    rel = elf.get_section_by_name('.rel.gnu.linkonce.this_module')
    symbols = elf.get_section_by_name('.symtab')
    locations = {symbols.get_symbol(r['r_info_sym']).name: (r['r_offset'], r['r_info_type'])
                 for r in rel.iter_relocations()}
    assert (section['sh_size'], section['sh_addralign']) == (292, 4)
    assert locations == {'init_module': (188, 2), 'cleanup_module': (276, 2)}
    return section


def main(compare=False):
    OUT.mkdir(exist_ok=True)
    run('cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
        HERE/'test_probe.c', HERE/'probe.c', '-o', OUT/'test_probe')
    run(OUT/'test_probe')
    name = 'c10_dac_trial' if compare else NAME
    imports = IMPORTS | {'i2c_smbus_write_byte_data'} if compare else IMPORTS
    units = [HERE/'probe.c']
    if compare:
        units = [HERE/'trial.c', HERE/'filter_compare.c']
        run('cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
            HERE/'test_filter_compare.c', HERE/'filter_compare.c', '-o', OUT/'test_filter_compare')
        run(OUT/'test_filter_compare')
    manifest = json.loads((WORK/'c10-usb-dac/kernel-exports.json').read_text())
    assert digest(WORK/'c10-analysis/kernel.raw') == manifest['kernel_sha256']
    assert digest(STOCK) == 'bbb5b13ff89919d9e13f53b954974185e4ae92ad7f737e20528d6a995e428773'
    with STOCK.open('rb') as original:
        factory = ELFFile(original)
        assert descriptor(factory).data() == bytes(12)+b'g_audio'+bytes(273)
        info = factory.get_section_by_name('.modinfo').data().split(b'\0')
        vermagic, = (x.decode('ascii') for x in info if x.startswith(b'vermagic='))
        assert re.fullmatch(r'vermagic=2\.6\.31\.3 mod_unload modversions MIPS32_R1 32BIT ', vermagic)
        original_flags = factory['e_flags']
    versions = ['.section __versions,"a",@progbits', '.balign 4']
    for symbol in sorted(imports | {'module_layout'}):
        crc = manifest['exports'][symbol]['crc']
        versions.extend((f'.long {crc}', f'.ascii "{symbol}"', f'.space {60-len(symbol)}'))
    metadata = OUT/(name+'_metadata.S')
    metadata.write_text('\n'.join([
        '.set noreorder', '.section .modinfo,"a",@progbits',
        '.asciz "license=GPL"', f'.asciz "description=C10 CS4398 {name}"',
        f'.asciz "{vermagic}"', '.asciz "depends="', *versions,
        '.section .gnu.linkonce.this_module,"aw",@progbits', '.balign 4',
        '.globl __this_module', '.type __this_module,@object', '__this_module:',
        '.space 12', f'.ascii "{name}"', '.space 176 - 13',
        '.long init_module', '.space 84', '.long cleanup_module', '.space 12',
        '.size __this_module, . - __this_module', '',
    ]))
    assert len(name) == 13
    flags = ['-target', 'mipsel-linux-musl', '-mcpu=mips32+soft_float+noabicalls+long_calls',
             '-mabi=32', '-fno-lto', '-G0', '-fno-pic', '-fno-pie', '-mno-abicalls',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector']
    objects = []
    for source in [*units, metadata]:
        output = OUT/(source.stem+'.o')
        run(ZIG, 'cc', *flags, '-Os', '-Wall', '-Wextra', '-Werror', '-c',
            source, '-o', output)
        objects.append(output)
    artifact = OUT/(name+'.ko')
    run(ZIG, 'ld.lld', '-r', '--build-id=none', *objects, '-o', artifact)
    with artifact.open('rb') as binary:
        module = ELFFile(binary)
        assert module.elfclass == 32 and module.little_endian and module['e_machine'] == 'EM_MIPS'
        assert module['e_type'] == 'ET_REL' and module['e_flags'] == original_flags
        assert descriptor(module).data() == bytes(12)+name.encode()+bytes(267)
        symbols = module.get_section_by_name('.symtab')
        assert {s.name for s in symbols.iter_symbols() if s.name and s['st_shndx'] == 'SHN_UNDEF'} == imports
        for section in module.iter_sections():
            if section['sh_type'] == 'SHT_REL':
                assert all(r['r_info_type'] in {2, 4, 5, 6} for r in section.iter_relocations())
    print(f'{artifact.name} SHA-256 {digest(artifact)}')


if __name__ == '__main__':
    assert sys.argv[1:] in ([], ['--compare'])
    main(compare='--compare' in sys.argv)
