"""Offline ELF extension of the verified v60 app. Never accesses USB."""
from pathlib import Path
import hashlib
import io
import json
import struct
import sys
from elftools.elf.elffile import ELFFile

BASE=Path(__file__).resolve().parent
V60=BASE.parent/'c10-dual-timer/build/ap.dual-candidate.dge'
SHA='d112f5b947f33ed1ec69d7a7444442b97e8882a5093329ec5939bd2562f73c2f'


def jump(address):
    assert address%4==0 and address>>28==0
    return 0x08000000|(address>>2)


def image(path,section):
    e=ELFFile(io.BytesIO(path.read_bytes()))
    sec=e.get_section_by_name(section)
    symbols={}
    for sym in e.get_section_by_name('.symtab').iter_symbols():
        assert not(sym.name and sym['st_shndx']=='SHN_UNDEF'),sym.name
        symbols[sym.name]=sym['st_value']
    for s in e.iter_sections():
        if s['sh_flags']&2 and s['sh_size']:assert s.name==section,(s.name,s['sh_size'])
        assert s['sh_type'] not in {'SHT_REL','SHT_RELA'}
    return sec['sh_addr'],sec.data(),symbols


def prepare():
    before=V60.read_bytes();assert hashlib.sha256(before).hexdigest()==SHA
    v60=json.loads((V60.parent/'patch-manifest.json').read_text())
    start,module,syms=image(BASE/'module.elf','.module')
    assert start==0x450000 and syms['eq_popen']==start
    assert 0<len(module)<0x10000
    out=BASE/'build';out.mkdir(exist_ok=True)
    names={'EQ_INIT':'eq_init','EQ_OPEN':'eq_open_item','EQ_DRAW':'eq_try_draw',
           'EQ_KEY':'eq_handle_key','EQ_DOWN':'eq_handle_down','EQ_MAIN':'eq_main_draw',
           'EQ_FGETS':'eq_fgets'}
    lines=[f'.equ {key}, 0x{syms[value]:x}' for key,value in names.items()]
    lines.append(f'.equ OLD_OPTION_ENTRY, 0x{v60["symbols"]["c10_menu_option_entry"]:x}')
    (out/'module-addrs.inc').write_text('\n'.join(lines)+'\n')
    table=v60['symbols']['c10_menu_dispatch_table']-0x400000
    (out/'menu-prefix.bin').write_bytes(before[table:table+44])


def build():
    original=V60.read_bytes();assert hashlib.sha256(original).hexdigest()==SHA
    result=bytearray(original)
    va,module,syms=image(BASE/'module.elf','.module')
    bridge_va,bridge,bs=image(BASE/'bridges.elf','.bridges')
    assert va==0x450000 and syms['eq_popen']==va
    assert bridge_va==0x433a00 and len(bridge)<=0x600
    v60=json.loads((V60.parent/'patch-manifest.json').read_text())
    changes=[]

    def replace(off,old,new,why):
        assert len(old)==len(new)
        assert bytes(result[off:off+len(old)])==old,why
        result[off:off+len(new)]=new
        changes.append({'offset':off,'size':len(new),'purpose':why,'before_hex':old.hex(),'after_hex':new.hex()})

    def words(a,old,new,why):
        replace(a-0x400000,struct.pack('<'+'I'*len(old),*old),
                struct.pack('<'+'I'*len(new),*new),why)

    e=ELFFile(io.BytesIO(original));null=None
    assert e['e_phnum']==8
    for i,seg in enumerate(e.iter_segments()):
        header=e['e_phoff']+i*e['e_phentsize']
        if seg['p_type']=='PT_NULL':
            assert null is None;null=header
        if seg['p_type']=='PT_LOAD' and seg['p_vaddr']==0x400000:
            end=bridge_va-0x400000+len(bridge)
            assert seg['p_filesz']==seg['p_memsz']<=0x33a00 and end<=0x34000
            replace(header+16,struct.pack('<II',seg['p_filesz'],seg['p_memsz']),
                    struct.pack('<II',end,end),'map extra RX bridges in old zero padding')
        if seg['p_type']=='PT_LOAD' and seg['p_vaddr']==0x444000:
            assert seg['p_memsz']==0x2c10
            replace(header+20,struct.pack('<I',0x2c10),struct.pack('<I',0x3000),
                    'reserve EQ state446d00, independent from stock and sleep')
    assert null is not None
    replace(0x33a00,bytes(len(bridge)),bridge,'GP-safe EQ interface bridges and twelve-entry menu table')
    # Match factory MIPS segment alignment, valid with 4/16/64KiB pages.
    module_offset=(len(result)+65535)&~65535
    new_header=struct.pack('<8I',1,module_offset,va,va,len(module),len(module),5,65536)
    # The stock unused header retains p_align=4; all other fields are zero.
    replace(null,struct.pack('<8I',0,0,0,0,0,0,0,4),new_header,
            'use original PT_NULL slot for new read/execute-only module segment')
    words(0x41c21c,[jump(0x418ef8)|0x04000000,0],
          [jump(bs['c10_eq_startup_entry'])|0x04000000,0],
          'initialize EQ prefs before stock creates playback threads; preserve original init result')
    words(0x4276a4,[0x3c1c0045,0x27bdffb0],
          [jump(bs['c10_eq_draw_dispatch_entry']),0],'EQ panel or exact stock menu fallback')
    words(0x425a30,[0x3c1c0045,0x27bdffd0],
          [jump(bs['c10_eq_key_dispatch_entry']),0],'EQ key handling or exact stock key fallback')
    words(0x426230,[0x3c1c0045,0x27bdffd8],
          [jump(bs['c10_eq_down_dispatch_entry']),0],
          'isolate EQ held-key navigation from stock settings key-down handler')
    words(0x425758,[jump(v60['symbols']['c10_menu_option_entry']),0],
          [jump(bs['c10_eq_option_entry']),0],'new EQ index11 without changing old index0..10 handlers')
    table=bs['c10_eq_menu_table']
    assert table>>16==0x43 and table&0xffff<0x8000
    old_table=v60['symbols']['c10_menu_dispatch_table']
    words(0x427860,[0x272c0000|(old_table&0xffff)],
          [0x272c0000|(table&0xffff)],'twelve-entry table with old eleven cases preserved')
    words(0x42784c,[0x2e51000b],[0x2e51000c],'menu draw bound twelve items')
    words(0x4256a4,[0x2402000a],[0x2402000b],'down wraps after EQ index11')
    words(0x4256e0,[0x240e000a],[0x240e000b],'up wraps to EQ index11')
    words(0x4277a8,[0x3c04cccc],[0x3c04ba2e],'scrollbar division11 high')
    words(0x4277b0,[0x3482cccd],[0x34828ba3],'scrollbar division11 low')
    # v60 shift3 remains correct for reciprocal 0xba2e8ba3.
    assert struct.unpack_from('<I',result,0x277d8)[0]==0x0003f0c2
    words(0x41ebec,[0x8f9980e0,0x02802021,0x3c140043],
          [0x02802021,0x3c140043,0x3c190045],
          'fixed450000 EQ popen wrapper preserving a0=old s4, original s4 and mode')
    assert result[0x1ebf8:0x1ec00]==original[0x1ebf8:0x1ec00]
    words(0x41f7e4,[0x8f998284,0x02602021,0x0320f809,0x24050400],
          [0x02602021,jump(bs['c10_eq_fgets_entry'])|0x04000000,0x24050400,0],
          'capture bounded playback stdout only; preserve fgets arguments and data')
    assert result[0x173d4:0x173e8]==original[0x173d4:0x173e8], 'metadata popen must stay stock'
    assert result[0x1c9b0:0x1ca00]==original[0x1c9b0:0x1ca00]
    result.extend(bytes(module_offset-len(result)))
    result.extend(module)
    # Prove segment layout and permissions from the actual finished ELF.
    done=ELFFile(io.BytesIO(result));segments=[s for s in done.iter_segments() if s['p_type']=='PT_LOAD']
    assert len(segments)==3
    ranges=sorted((s['p_vaddr'],s['p_vaddr']+s['p_memsz']) for s in segments)
    assert all(ranges[i][1]<=ranges[i+1][0] for i in range(len(ranges)-1))
    added=next(s for s in segments if s['p_vaddr']==va)
    assert added['p_flags']==5 and added['p_align']==65536
    assert added['p_offset']%65536==va%65536
    assert added.data()==module
    assert bridge[table-bridge_va:table-bridge_va+44]==(BASE/'build/menu-prefix.bin').read_bytes()
    report={'status':'local EQ candidate; not installed or hardware tested',
            'base_v60_app_sha256':SHA,'candidate_sha256':hashlib.sha256(result).hexdigest(),
            'module_va':va,'module_offset':module_offset,'module_bytes':len(module),
            'bridge_bytes':len(bridge),'module_symbols':{k:v for k,v in syms.items() if k.startswith(('eq_','orig_'))},
            'bridge_symbols':{k:v for k,v in bs.items() if k.startswith('c10_eq_')},'edits':changes}
    (BASE/'build/ap.eq-candidate.dge').write_bytes(result)
    (BASE/'build/patch-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['edits','module_symbols','bridge_symbols']},indent=2))


if __name__=='__main__':
    prepare() if len(sys.argv)>1 and sys.argv[1]=='prepare' else build()
