from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
import re, struct, json, sys

path=Path(sys.argv[1])
with path.open('rb') as f:
    e=ELFFile(f)
    syms=e.get_section_by_name('.dynsym')
    symbols=list(syms.iter_symbols()) if syms else []
    dynamic=e.get_section_by_name('.dynamic')
    tags={x.entry.d_tag: x.entry.d_val for x in dynamic.iter_tags()} if dynamic else {}
    needed=[x.needed for x in dynamic.iter_tags() if x.entry.d_tag=='DT_NEEDED'] if dynamic else []
    interp=e.get_section_by_name('.interp')
    print(json.dumps(dict(file=str(path),architecture=e.get_machine_arch(),little_endian=e.little_endian,
                         entry=hex(e.header.e_entry),flags=hex(e.header.e_flags),needed=needed,
                         interpreter=interp.data().rstrip(b'\0').decode() if interp else None,
                         dynamic_symbols=len(symbols)),ensure_ascii=False))
    def readva(va, size):
        for s in e.iter_segments():
            start=s.header.p_vaddr
            if s.header.p_type=='PT_LOAD' and start<=va<start+s.header.p_filesz:
                return s.data()[va-start:va-start+size]
        return b''
    gp=struct.unpack_from('<I',e.get_section_by_name('.reginfo').data(),20)[0]
    got=e.get_section_by_name('.got'); got_names={}
    if got:
        for i in range(tags.get('DT_MIPS_GOTSYM',len(symbols)),len(symbols)):
            addr=got.header.sh_addr+4*(tags['DT_MIPS_LOCAL_GOTNO']+i-tags['DT_MIPS_GOTSYM'])
            got_names[addr]=symbols[i].name
    funcs=[s for s in symbols if s.entry.st_info.type=='STT_FUNC' and s.entry.st_shndx!='SHN_UNDEF']
    if len(sys.argv)>2 and sys.argv[2]=='ALLTEXT':
        from elftools.elf.sections import Symbol
        from elftools.construct.lib.container import Container
        t=e.get_section_by_name('.text')
        funcs=[Symbol(Container(st_value=t.header.sh_addr,st_size=t.header.sh_size), 'ALLTEXT')]
    selected=re.compile(sys.argv[2] if len(sys.argv)>2 else 'init_c10_display|ctrl_sdl_key_even|update|checksum|crc|volume|volum|cpld',re.I)
    print('FUNCTIONS',[(s.name,hex(s.entry.st_value),s.entry.st_size) for s in funcs if selected.search(s.name)])
    md=Cs(CS_ARCH_MIPS,CS_MODE_MIPS32|CS_MODE_LITTLE_ENDIAN)
    for s in funcs:
        if not selected.search(s.name): continue
        print('\nFUNCTION',s.name,hex(s.entry.st_value),'size',s.entry.st_size,'gp',hex(gp))
        for ins in md.disasm(readva(s.entry.st_value,s.entry.st_size),s.entry.st_value):
            annotation=''
            m=re.search(r'(-?0x[0-9a-f]+|-?\d+)\(\$gp\)',ins.op_str)
            if m:
                v=gp+int(m[1],0)
                if v in got_names: annotation=got_names[v]
                else:
                    b=readva(v,4)
                    if len(b)==4:
                        target=struct.unpack('<I',b)[0]
                        annotation=hex(target)
                        raw=readva(target,120).split(b'\0')[0]
                        if raw and all(32<=c<127 for c in raw):annotation+=' '+repr(raw.decode())
            print(f'{ins.address:08x} {ins.mnemonic:8} {ins.op_str:32} {annotation}')
