"""Offline execute the original C10 updater's version gate, never hardware."""
from pathlib import Path
import hashlib,io,json,struct
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_MIPS,UC_MODE_MIPS32,UC_MODE_LITTLE_ENDIAN,UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_V0,UC_MIPS_REG_RA,UC_MIPS_REG_PC,UC_MIPS_REG_SP
B=Path(__file__).resolve().parent;binary=(B/'appfs/local/aplayer/ap.dge').read_bytes();assert hashlib.sha256(binary).hexdigest()=='7d5f35b9c35ff02aaf6d1a12eb6064af6814395d6b3da76ede8889c82a9b94fc'
def run(version):
 e=ELFFile(io.BytesIO(binary));u=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN);pages=set()
 for seg in e.iter_segments():
  if seg['p_type']!='PT_LOAD':continue
  for p in range(seg['p_vaddr']&~4095,(seg['p_vaddr']+seg['p_memsz']+4095)&~4095,4096):
   if p not in pages:u.mem_map(p,4096);pages.add(p)
  u.mem_write(seg['p_vaddr'],seg.data())
 u.mem_map(0x20000000,0x10000);u.mem_map(0x7ff00000,0x100000)
 syms=list(e.get_section_by_name('.dynsym').iter_symbols());tags={x.entry.d_tag:x.entry.d_val for x in e.get_section_by_name('.dynamic').iter_tags()};got=e.get_section_by_name('.got')['sh_addr'];stubs={}
 for i in range(tags['DT_MIPS_GOTSYM'],len(syms)):
  s=syms[i]
  if s['st_info']['type']=='STT_FUNC' and s['st_shndx']=='SHN_UNDEF':
   addr=0x20000000+i*16;stubs[addr]=s.name;u.mem_write(got+4*(tags['DT_MIPS_LOCAL_GOTNO']+i-tags['DT_MIPS_GOTSYM']),struct.pack('<I',addr))
 calls=[];ended=False
 def text(addr):
  b=bytearray()
  for i in range(2048):
   ch=u.mem_read(addr+i,1)[0]
   if not ch:return b.decode('utf8','replace')
   b.append(ch)
  raise AssertionError('unbounded text')
 def hook(uc,addr,size,data):
  nonlocal ended
  if addr==0x2000f000:ended=True;uc.emu_stop();return
  if addr not in stubs:return
  name=stubs[addr];a,b,c=[uc.reg_read(r) for r in [UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2]];ret=0
  if name=='fopen':calls.append({'call':name,'path':text(a)});ret=123
  elif name=='fread':assert b*c==8;uc.mem_write(a,struct.pack('<II',256,version));ret=c
  elif name=='printf':calls.append({'call':name,'format':text(a),'argument':b})
  elif name=='puts':calls.append({'call':name,'text':text(a)})
  elif name not in ['ferror','fclose']:raise AssertionError('unexpected call '+name)
  uc.reg_write(UC_MIPS_REG_V0,ret);uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
 u.hook_add(UC_HOOK_CODE,hook);u.reg_write(UC_MIPS_REG_SP,0x7ffff000);u.reg_write(UC_MIPS_REG_RA,0x2000f000);u.reg_write(UC_MIPS_REG_A0,0);u.emu_start(0x414eb8,0,count=10000);assert ended
 result=u.reg_read(UC_MIPS_REG_V0);result=result-0x100000000 if result>=0x80000000 else result
 return {'version':version,'result':result,'calls':calls}
records=[run(v) for v in [28,29,56,57]];assert [r['result'] for r in records]==[-1,0,0,0];print(json.dumps({'entry':'0x414eb8','gate':'unsigned version >= 29','records':records,'limits':'only first-eight-byte scan/version gate executed; not full CRC, physical update or recovery'},ensure_ascii=False,indent=2))
