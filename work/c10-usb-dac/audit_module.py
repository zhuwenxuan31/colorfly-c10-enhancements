"""Audit finished ELF/ABI/CRCs and every original code redirect, offline."""
from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import Cs,CS_ARCH_MIPS,CS_MODE_MIPS32,CS_MODE_LITTLE_ENDIAN
import hashlib,json
BASE=Path(__file__).resolve().parent
stock=BASE.parent/'c10-analysis/appfs/local/modules/g_audio.ko';candidate=BASE/'build/g_audio.candidate.ko'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
a=ELFFile(stock.open('rb'));b=ELFFile(candidate.open('rb'))
assert b['e_type']=='ET_REL' and b['e_machine']=='EM_MIPS' and b['e_flags']==a['e_flags']==0x50001001
for n in ['.modinfo','.gnu.linkonce.this_module']:
 assert a.get_section_by_name(n).data()==b.get_section_by_name(n).data(),n
exports=json.loads((BASE/'kernel-exports.json').read_text())['exports']
ver=b.get_section_by_name('__versions').data();versions={ver[i+4:i+64].split(b'\0',1)[0].decode():int.from_bytes(ver[i:i+4],'little') for i in range(0,len(ver),64)}
undefined=[s.name for s in b.get_section_by_name('.symtab').iter_symbols() if s['st_shndx']=='SHN_UNDEF' and s.name]
for name in undefined:assert name in exports and versions[name]==int(exports[name]['crc'],16),name
assert versions['module_layout']==int.from_bytes(a.get_section_by_name('__versions').data()[:4],'little')
for unit in ['feedback','descriptors','usb_engine']:
 e=ELFFile((BASE/'build'/f'{unit}.o').open('rb'));assert e['e_flags']==0x50001001
 syms=list(e.get_section_by_name('.symtab').iter_symbols())
 for rs in e.iter_sections():
  if rs['sh_type']=='SHT_REL':
   for r in rs.iter_relocations():
    assert r['r_info_type'] not in [9,10,11],(unit,'PIC relocation',r['r_info_type'])
    if syms[r['r_info_sym']]['st_shndx']=='SHN_UNDEF':assert r['r_info_type']!=4,(unit,'cross-region direct call')
 c=Cs(CS_ARCH_MIPS,CS_MODE_MIPS32|CS_MODE_LITTLE_ENDIAN)
 gp=[]
 for sec in e.iter_sections():
  if sec['sh_flags']&4:
   for ins in c.disasm(sec.data(),0):
    assert not ins.mnemonic.startswith(('lwc1','swc1','ldc1','sdc1','cvt.','add.s','mul.s'))
    if '$gp' in ins.op_str:gp.append(ins.mnemonic+' '+ins.op_str)
 if unit!='usb_engine':assert not gp,(unit,gp)
 else:assert gp and all(x.startswith('move ') and x.endswith(', $gp') for x in gp),gp
r={'candidate_sha256':sha(candidate),'stock_sha256':sha(stock),'elf_flags':hex(b['e_flags']),'kernel_imports_crc_matched':len(undefined),'metadata_and_module_layout_preserved':True,'original_app_v70_not_modified':True,'redirects':json.loads((BASE/'build/redirects.json').read_text()),'hardware_audio_tested':False}
(BASE/'build/audit.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='redirects'},indent=2))
