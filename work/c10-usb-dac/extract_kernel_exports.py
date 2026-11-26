"""Read-only match kernel export records and CRCs to the original module."""
from pathlib import Path
from elftools.elf.elffile import ELFFile
import struct,json,hashlib,collections
BASE=Path(__file__).resolve().parent
raw=(BASE.parent/'c10-analysis/kernel.raw').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='7b3647b251b11364ff3e93e37fbce5b3fa54e695502fc843f0afdc89c5a0e0fb'
load=0x80010000
elf=ELFFile((BASE.parent/'c10-analysis/appfs/local/modules/g_audio.ko').open('rb'))
v=elf.get_section_by_name('__versions').data();known={v[i+4:i+64].split(b'\0',1)[0].decode():struct.unpack_from('<I',v,i)[0] for i in range(0,len(v),64)}
def word(o):return struct.unpack_from('<I',raw,o)[0]
def record(o):
 if o<0 or o+8>len(raw):return None
 a,p=word(o),word(o+4);off=p-load
 if not(load<=a<0x81000000 and a%4==0 and 0<=off<len(raw)):return None
 s=raw[off:off+180].split(b'\0',1)[0]
 if not s or any(x not in b'_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' for x in s):return None
 return a,s.decode()
needle=b'cancel_work_sync\0';pos=raw.find(needle);assert pos>=0
sites=[];start=0
while True:
 o=raw.find(struct.pack('<I',load+pos),start)
 if o<0:break
 start=o+1
 if o>=4 and record(o-4):sites.append(o-4)
assert len(sites)==1,sites
lo=hi=sites[0]
while record(lo-8):lo-=8
while record(hi+8):hi+=8
records=[record(o) for o in range(lo,hi+1,8)]
votes=collections.Counter()
for i,(addr,name) in enumerate(records):
 if name not in known:continue
 pattern=struct.pack('<I',known[name]);start=0
 while True:
  o=raw.find(pattern,start)
  if o<0:break
  start=o+1
  if o%4==0 and 0<=o-4*i<len(raw):votes[o-4*i]+=1
base,count=votes.most_common(1)[0];assert count>=10,(hex(base),count)
for i,(addr,name) in enumerate(records):
 if name in known:assert word(base+i*4)==known[name],name
exports={name:{'address':hex(addr),'crc':hex(word(base+i*4)),'record_offset':lo+i*8,'crc_offset':base+i*4} for i,(addr,name) in enumerate(records)}
report={'kernel_sha256':hashlib.sha256(raw).hexdigest(),'load_base':hex(load),'export_table_offset':lo,'export_count':len(records),'crc_base_offset':base,'known_module_crc_matches':count,'exports':exports}
(BASE/'kernel-exports.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in report if k!='exports'},indent=2))
for n in ['cancel_work_sync','flush_scheduled_work','schedule_work','snd_pcm_lib_write','snd_pcm_kernel_ioctl','__kmalloc','kfree']:
 print(n,exports.get(n))
