"""Execute the original updater's late-stage component selector in Unicorn.

Calls to libc and the payload-copy helper are intercepted, never executed on host.
This verifies one dispatcher, not the complete upgrade or recovery procedure.
"""
from pathlib import Path
import hashlib,io,json,struct,sys,os
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_MIPS,UC_MODE_MIPS32,UC_MODE_LITTLE_ENDIAN,UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_V0,UC_MIPS_REG_RA,UC_MIPS_REG_PC,UC_MIPS_REG_SP
from package import parse
BASE=Path(__file__).resolve().parent
binary=Path(os.environ.get('C10_ORIGINAL_APP',str(BASE.parent/'c10-analysis/appfs/local/aplayer/ap.dge')))
assert hashlib.sha256(binary.read_bytes()).hexdigest()=='7d5f35b9c35ff02aaf6d1a12eb6064af6814395d6b3da76ede8889c82a9b94fc'

def verify(container):
    p=parse(container);u=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
    elf=ELFFile(io.BytesIO(binary.read_bytes()));pages=set()
    for seg in elf.iter_segments():
        if seg.header.p_type!='PT_LOAD':continue
        a,size=seg.header.p_vaddr,seg.header.p_memsz
        for page in range(a&~4095,(a+size+4095)&~4095,4096):
            if page not in pages:u.mem_map(page,4096);pages.add(page)
        u.mem_write(a,seg.data())
    u.mem_map(0x10000000,0x100000);u.mem_map(0x20000000,0x10000);u.mem_map(0x7ff00000,0x100000)
    symbols=list(elf.get_section_by_name('.dynsym').iter_symbols());byname={s.name:s.entry.st_value for s in symbols}
    tags={t.entry.d_tag:t.entry.d_val for t in elf.get_section_by_name('.dynamic').iter_tags()}
    got=elf.get_section_by_name('.got').header.sh_addr;stubs={}
    for i in range(tags['DT_MIPS_GOTSYM'],len(symbols)):
        s=symbols[i]
        if s.entry.st_info.type=='STT_FUNC' and s.entry.st_shndx=='SHN_UNDEF':
            address=0x20000000+i*16;stubs[address]=s.name
            slot=got+4*(tags['DT_MIPS_LOCAL_GOTNO']+i-tags['DT_MIPS_GOTSYM']);u.mem_write(slot,struct.pack('<I',address))
    for address,values in [(0x10000000,[len(c) for c in p['payloads']]),(0x10000040,p['offsets']),(0x10000080,p['burn_offsets'])]:
        u.mem_write(address,struct.pack('<4I',*values))
    u.mem_write(byname['update_file'],struct.pack('<5I',p['order'],p['total'],0x10000000,0x10000040,0x10000080))
    u.mem_write(0x445168,struct.pack('<I',123))
    u.reg_write(UC_MIPS_REG_SP,0x7ffff000);u.reg_write(UC_MIPS_REG_RA,0x2000f000)
    record={'dispatcher_entry':'0x42b340','package_order':p['order'],'package_total':p['total'],'opens':[],'seeks':[],'copy_calls':[]}
    finished=False
    def cstring(address):
        b=bytearray()
        while len(b)<1024:
            x=u.mem_read(address+len(b),1)[0]
            if not x:return b.decode()
            b.append(x)
        raise AssertionError('unterminated string')
    def hook(uc,address,size,data):
        nonlocal finished
        args=[uc.reg_read(r) for r in [UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2]]
        if address==0x2000f000:finished=True;uc.emu_stop();return
        if address==0x42af30:
            record['copy_calls'].append({'package_offset':args[0],'length':args[1]})
            uc.reg_write(UC_MIPS_REG_V0,0);uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA));return
        if address in stubs:
            name=stubs[address];ret=0
            if name=='open':record['opens'].append({'path':cstring(args[0]),'flags':args[1]});ret=7
            elif name=='lseek':record['seeks'].append({'fd':args[0],'offset':args[1],'whence':args[2]});ret=args[1]
            elif name not in ['fsync','close','fclose']:raise AssertionError(('unexpected external call',name,args))
            uc.reg_write(UC_MIPS_REG_V0,ret);uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
    u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x42b340,0,count=10000)
    assert finished
    assert record['opens']==[{'path':'/dev/mmcblk0','flags':2}]
    assert record['seeks']==[{'fd':7,'offset':p['burn_offsets'][3],'whence':0}]
    assert record['copy_calls']==[{'package_offset':p['offsets'][3],'length':len(p['payloads'][3])}]
    record.update(result='application segment selected exactly once',limitations='Only dispatcher 0x42b340 executed; header parsing, acceptance, low-level writes, reboot, mount state and recovery are not validated.')
    return record

if __name__=='__main__':
    path=Path(sys.argv[1]);record=verify(path.read_bytes());print(json.dumps(record,indent=2,ensure_ascii=False))
