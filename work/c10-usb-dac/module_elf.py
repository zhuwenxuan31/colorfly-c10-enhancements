"""Constrained ELF32LE MIPS ET_REL edit. No module/kernel execution or USB IO."""
from pathlib import Path
import io,struct,hashlib,json
from elftools.elf.elffile import ELFFile
BASE=Path(__file__).resolve().parent
STOCK=BASE.parent/'c10-analysis/appfs/local/modules/g_audio.ko'
SHA='bbb5b13ff89919d9e13f53b954974185e4ae92ad7f737e20528d6a995e428773'

def rewrite(data,aliases,redirect,imports):
 assert hashlib.sha256(data).hexdigest()==SHA
 e=ELFFile(io.BytesIO(data));assert e.elfclass==32 and e.little_endian and e['e_type']=='ET_REL' and e['e_machine']=='EM_MIPS'
 sec=[bytearray(s.data()) if s['sh_type']!='SHT_NOBITS' else bytearray() for s in e.iter_sections()]
 headers=[list(struct.unpack_from('<10I',data,e['e_shoff']+i*40)) for i in range(e['e_shnum'])]
 st=e.get_section_by_name('.symtab');si=list(e.iter_sections()).index(st) if False else next(i for i,s in enumerate(e.iter_sections()) if s.name=='.symtab');stringindex=st['sh_link'];symbols=list(st.iter_symbols());names={s.name:i for i,s in enumerate(symbols) if s.name}
 def addsymbol(name,value,kind,index):
  if name in names:return names[name]
  no=len(sec[stringindex]);sec[stringindex].extend(name.encode()+b'\0')
  idx=len(sec[si])//16;sec[si].extend(struct.pack('<IIIBBH',no,value,0,kind,0,index));names[name]=idx;return idx
 for alias,original in aliases.items():
  s=symbols[names[original]];addsymbol(alias,s['st_value'],0x12,s['st_shndx'])
 new={old:addsymbol(new,0,0x12,0) for old,new in redirect.items()}
 targets={(symbols[names[n]]['st_shndx'],symbols[names[n]]['st_value']):n for n in redirect}
 edits=[]
 def redirect_at(rsindex,ri,offset,kind,target,wordzero=True):
  entry=offset*0 # keep all emitted offsets explicit below
  old=targets[target];newindex=new[old]
  struct.pack_into('<I',sec[rsindex],ri*8+4,(newindex<<8)|kind)
  source=headers[rsindex][7];word=struct.unpack_from('<I',sec[source],offset)[0]
  mask=0xffff0000 if kind in [5,6] else 0xfc000000 if kind==4 else 0
  if wordzero:struct.pack_into('<I',sec[source],offset,word&mask)
  edits.append({'section':e.get_section(source).name,'offset':offset,'type':kind,'from':old,'to':redirect[old]})
 for i,rs in enumerate(e.iter_sections()):
  if rs['sh_type']!='SHT_REL':continue
  rels=list(rs.iter_relocations());pending={}
  for j,r in enumerate(rels):
   typ=r['r_info_type'];sym=symbols[r['r_info_sym']];sh=sym['st_shndx'];o=r['r_offset'];source=rs['sh_info'];w=struct.unpack_from('<I',sec[source],o)[0]
   if not isinstance(sh,int):continue
   if typ==5:pending.setdefault(r['r_info_sym'],[]).append((j,o,w));continue
   if typ==6:
    low=(w&65535)-65536 if w&32768 else w&65535
    group=pending.pop(r['r_info_sym'],[])
    for hj,ho,hw in group:
     a=((hw&65535)<<16)+low+sym['st_value'];key=(sh,a&0xffffffff)
     if key in targets:
      redirect_at(i,hj,ho,5,key);redirect_at(i,j,o,6,key)
   elif typ in [2,4]:
    a=(w if typ==2 else (w&0x3ffffff)<<2)+sym['st_value'];key=(sh,a&0xffffffff)
    if key in targets:redirect_at(i,j,o,typ,key)
 assert set(x['from'] for x in edits)==set(redirect),(edits,redirect)
 # All added kernel imports must have an exact CRC from this original kernel.
 versionindex=next(i for i,s in enumerate(e.iter_sections()) if s.name=='__versions')
 existing={sec[versionindex][i+4:i+64].split(b'\0',1)[0].decode() for i in range(0,len(sec[versionindex]),64)}
 for name,crc in imports.items():
  addsymbol(name,0,0x12,0)
  assert name not in existing and len(name)<60
  sec[versionindex].extend(struct.pack('<I',crc)+name.encode()+bytes(60-len(name)))
 # Use per-interface class rather than claiming a nonexistent IAD function.
 sd=symbols[names['device_desc']];index=sd['st_shndx'];off=sd['st_value'];assert sec[index][off+4:off+7]==b'\xef\2\1';sec[index][off+4:off+7]=b'\0\0\0'
 # No program headers; move only file-backed section payloads and the table.
 result=bytearray(data[:e['e_ehsize']]);assert e['e_phnum']==0
 for i,h in enumerate(headers):
  if i==0:continue
  align=max(1,h[8]);result.extend(bytes((-len(result))%align));h[4]=len(result)
  if h[1]!=8:h[5]=len(sec[i]);result.extend(sec[i])
 result.extend(bytes((-len(result))%4));table=len(result)
 for h in headers:result.extend(struct.pack('<10I',*h))
 struct.pack_into('<I',result,32,table)
 after=ELFFile(io.BytesIO(result));assert after.get_section_by_name('.modinfo').data()==e.get_section_by_name('.modinfo').data()
 assert after.get_section_by_name('.gnu.linkonce.this_module').data()==e.get_section_by_name('.gnu.linkonce.this_module').data()
 return bytes(result),edits

def prepare():
 exports=json.loads((BASE/'kernel-exports.json').read_text())['exports'];data=STOCK.read_bytes()
 aliases={'stock_f_audio_bind':'f_audio_bind','stock_f_audio_unbind':'f_audio_unbind'}
 redirect={'f_audio_bind':'c10_bind','f_audio_set_alt':'c10_set_alt','f_audio_disable':'c10_disable','f_audio_unbind':'c10_unbind','f_audio_playback_work':'c10_work'}
 b,edits=rewrite(data,aliases,redirect,{'cancel_work_sync':int(exports['cancel_work_sync']['crc'],16)})
 (BASE/'build/stock-prepared.o').write_bytes(b);(BASE/'build/redirects.json').write_text(json.dumps(edits,indent=2)+'\n');print('Prepared original ABI module:',len(edits),'relocations redirected')
if __name__=='__main__':prepare()
