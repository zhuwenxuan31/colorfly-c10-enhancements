"""Relocate and execute actual original+overlay MIPS module, mocked kernel only.
Never opens a device, runs host kernel ioctls, or starts audio. Every external
call is trapped. USB ep ops, allocation, PCM writes and scheduling are modeled.
"""
from pathlib import Path
import io,struct,unittest,json
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_MIPS,UC_MODE_MIPS32,UC_MODE_LITTLE_ENDIAN,UC_HOOK_CODE
from unicorn.mips_const import *
BASE=Path(__file__).resolve().parent
class ModuleProbe:
 def __init__(self):
  self.u=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN);u=self.u
  self.heap=0x03000000;u.mem_map(self.heap,0x400000);u.mem_map(0x20000000,0x10000);u.mem_map(0x7ff00000,0x100000)
  self.allocs={};self.freed=set();self.stubs={};self.calls=[];self.queues={};self.enabled={};self.scheduled=False;self.pcm_bytes=bytearray();self.frame=0;self.alloc_count=0;self.fail_alloc=None;self.fail_enable=None;self.fail_queue=None;self.pcm_result=None;self.inject_pcm=None;self.after_ioctl=None;self.require_nonblock=False;self.stopped=False
  e=ELFFile(io.BytesIO((BASE/'build/g_audio.candidate.ko').read_bytes()));self.elf=e
  symbols=list(e.get_section_by_name('.symtab').iter_symbols());self.sections={};address=0x01000000
  for i,s in enumerate(e.iter_sections()):
   if s['sh_flags']&2 and s['sh_size']:
    size=(s['sh_size']+4095)&~4095;u.mem_map(address,size);self.sections[i]=address
    if s['sh_type']!='SHT_NOBITS':u.mem_write(address,s.data())
    address+=size
  self.values=[];self.symbols={}
  for i,s in enumerate(symbols):
   index=s['st_shndx']
   if index=='SHN_UNDEF':
    if not s.name:value=0
    elif s['st_info']['type']=='STT_OBJECT' or s.name in ['_ctype','kmalloc_caches','init_uts_ns']:value=self.fixture(8192)
    else:value=0x20000000+i*16;self.stubs[value]=s.name
   elif index=='SHN_ABS':value=s['st_value']
   elif isinstance(index,int):value=self.sections.get(index,0)+s['st_value']
   else:raise AssertionError(index)
   self.values.append(value)
   if s.name:self.symbols[s.name]=value
  for rs in e.iter_sections():
   if rs['sh_type']!='SHT_REL' or rs['sh_info'] not in self.sections:continue
   pending={};base=self.sections[rs['sh_info']]
   for r in rs.iter_relocations():
    o=base+r['r_offset'];w=self.word(o);typ=r['r_info_type'];si=r['r_info_sym'];S=self.values[si]
    if typ==2:self.word(o,w+S)
    elif typ==5:pending.setdefault(si,[]).append((o,w))
    elif typ==6:
     lo=(w&65535)-65536 if w&32768 else w&65535
     for ho,hw in pending.pop(si,[]):
      a=((hw&65535)<<16)+lo+S;self.word(ho,(hw&0xffff0000)|(((a+0x8000)>>16)&65535))
     self.word(o,(w&0xffff0000)|((lo+S)&65535))
    elif typ==4:
     dest=((w&0x3ffffff)<<2)+S;assert dest>>28==(o+4)>>28
     self.word(o,(w&0xfc000000)|((dest>>2)&0x3ffffff))
    elif typ!=0:raise AssertionError(('unsupported relocation',typ))
   assert not pending
  self.gp=self.fixture(1024);self.word(self.gp+24,0x7fffffff)
  self.ret=0x2000fff0;u.reg_write(UC_MIPS_REG_GP,self.gp);u.reg_write(UC_MIPS_REG_SP,0x7ffff000)
  self.gadget=self.fixture(128);ops=self.fixture(32);self.word(ops,self.stub('get_frame'));self.word(self.gadget,ops);self.word(self.gadget+16,3);self.word(self.gadget+20,1);self.word(self.gadget+24,self.string_ptr('musb_hdrc'))
  self.out=self.ep('ep1out');self.feedback=self.ep('ep1in');head=self.gadget+8
  self.word(head,self.out+12);self.word(head+4,self.feedback+12);self.word(self.out+12,self.feedback+12);self.word(self.out+16,head);self.word(self.feedback+12,head);self.word(self.feedback+16,self.out+12)
  self.config=self.fixture(128);self.cdev=self.fixture(128);self.word(self.config+28,self.cdev);self.word(self.cdev,self.gadget)
  self.audio=self.fixture(256);self.word(self.audio+16,self.config);self.word(self.audio+0x98,self.symbols['as_out_ep_desc']);self.work=self.audio+0xa0;self.word(self.work+4,self.work+4);self.word(self.work+8,self.work+4);self.word(self.work+12,self.symbols['c10_work'])
  self.substream=self.fixture(256);self.runtime=self.fixture(512);self.status=self.fixture(32);self.word(self.audio+0x64,self.substream);self.word(self.substream+0x70,self.runtime);self.word(self.runtime+0x94,self.status);self.word(self.runtime+0x78,1<<20);self.word(self.runtime+0x38,256);self.word(self.runtime+0x40,8192);self.word(self.status,2)
  u.hook_add(UC_HOOK_CODE,self.hook)
 def fixture(self,n):
  p=self.heap;self.heap+=(n+15)&~15;assert self.heap<0x03400000;return p
 def allocate(self,n):
  self.alloc_count+=1
  if self.fail_alloc==self.alloc_count:return 0
  p=self.fixture(n);self.allocs[p]=n;return p
 def free(self,p):
  if not p:return
  assert p in self.allocs or p==self.audio,('unknown free',hex(p))
  assert p not in self.freed,('double free',hex(p));self.freed.add(p)
 def word(self,p,v=None):
  if v is None:return struct.unpack('<I',self.u.mem_read(p,4))[0]
  self.u.mem_write(p,struct.pack('<I',v&0xffffffff))
 def string(self,p):return bytes(self.u.mem_read(p,512)).split(b'\0',1)[0].decode()
 def string_ptr(self,s):p=self.fixture(len(s)+1);self.u.mem_write(p,s.encode()+b'\0');return p
 def stub(self,name):
  p=0x2000b000+len(self.stubs)*16;assert p<self.ret if hasattr(self,'ret') else True
  self.stubs[p]=name;return p
 def ep(self,name):
  p=self.fixture(32);self.word(p+4,self.string_ptr(name));ops=self.fixture(40);self.word(p+8,ops);self.word(p+20,512)
  for i,n in enumerate(['ep_enable','ep_disable','ep_alloc','ep_free','ep_queue','ep_dequeue']):self.word(ops+4*i,self.stub(n))
  self.queues[p]=[];return p
 def reply(self,value=0):self.u.reg_write(UC_MIPS_REG_V0,value&0xffffffff);self.u.reg_write(UC_MIPS_REG_PC,self.u.reg_read(UC_MIPS_REG_RA))
 def hook(self,u,address,size,data):
  if address==self.ret:self.stopped=True;u.emu_stop();return
  name=self.stubs.get(address)
  if not name:return
  a,b,c,d=[u.reg_read(r) for r in [UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3]];self.calls.append((name,a,b,c));result=0
  if name=='__kmalloc':result=self.allocate(a)
  elif name=='kmem_cache_alloc':result=self.allocate(2048)
  elif name=='kfree':self.free(a)
  elif name=='strlen':result=len(self.string(a))
  elif name=='strrchr':
   s=self.string(a);i=s.rfind(chr(b&255));result=a+i if i>=0 else 0
  elif name=='simple_strtoul':
   import re
   m=re.match(r'\d+',self.string(a));result=int(m[0]) if m else 0
  elif name=='ep_alloc':result=self.allocate(48)
  elif name=='ep_free':
   assert b not in self.queues[a];self.free(b)
  elif name=='ep_enable':
   if self.fail_enable==a:result=-5
   else:self.enabled[a]=True
  elif name=='ep_disable':
   self.enabled[a]=False;self.queues[a].clear()
  elif name=='ep_queue':
   assert self.enabled.get(a),('queue disabled',hex(a));assert b not in self.queues[a],('duplicate queue',hex(b))
   assert b not in self.freed and self.word(b) not in self.freed
   if self.fail_queue==a:result=-5
   else:self.queues[a].append(b)
  elif name=='ep_dequeue':
   if b in self.queues[a]:self.queues[a].remove(b)
  elif name=='schedule_work':self.scheduled=True;result=1
  elif name=='cancel_work_sync':self.scheduled=False;result=1
  elif name=='get_frame':result=self.frame
  elif name=='snd_pcm_kernel_ioctl':
   if b==0x20004143:self.word(self.status,1)
   elif b==0x20004140:self.word(self.status,2);self.word(self.status+8,0)
   else:raise AssertionError(('unexpected PCM ioctl',hex(b)))
   if self.after_ioctl:self.after_ioctl(self,b)
  elif name=='snd_pcm_lib_write':
   assert self.word(self.gp+24)==0,'kernel addr_limit not set'
   if self.require_nonblock:assert self.word(a+0xa4)&0x80,'native PCM write would block'
   result=c if self.pcm_result is None else min(c,self.pcm_result) if self.pcm_result>0 else self.pcm_result
   if result>0:self.pcm_bytes.extend(u.mem_read(b,result*4));self.word(self.status,3)
   if self.inject_pcm:self.inject_pcm(self)
  elif name in ['printk','filp_close']:pass
  else:raise AssertionError(('unexpected kernel call',name,hex(address)))
  self.reply(result)
 def call(self,name,*args):
  self.stopped=False
  for reg,value in zip([UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3],args):self.u.reg_write(reg,value)
  p=self.symbols[name] if isinstance(name,str) else name;self.u.reg_write(UC_MIPS_REG_RA,self.ret);self.u.reg_write(UC_MIPS_REG_T9,p)
  sp=self.u.reg_read(UC_MIPS_REG_SP);gp=self.u.reg_read(UC_MIPS_REG_GP)
  for segment in range(5):
   self.resume_needed=False
   self.u.emu_start(p if segment==0 else self.u.reg_read(UC_MIPS_REG_PC),0,count=2000000)
   if self.stopped:break
   assert self.resume_needed,('bound',name,hex(self.u.reg_read(UC_MIPS_REG_PC)))
  assert self.stopped,('resume bound',name)
  assert sp==self.u.reg_read(UC_MIPS_REG_SP) and gp==self.u.reg_read(UC_MIPS_REG_GP),'ABI corrupt'
  v=self.u.reg_read(UC_MIPS_REG_V0);return v if v<0x80000000 else v-0x100000000
 def nested(self,name,*args):
  ctx=self.u.context_save();stopped=self.stopped
  try:return self.call(name,*args)
  finally:self.u.context_restore(ctx);self.stopped=stopped;self.resume_needed=True
 def bind(self):return self.call('c10_bind',self.config,self.audio)
 def start(self):return self.call('c10_set_alt',self.audio,1,1)
 def pump(self):self.scheduled=False;self.call('c10_work',self.work)
 def deliver(self,data):
  q=self.queues[self.out].pop(0);self.u.mem_write(self.word(q),data);self.word(q+36,len(data));self.word(q+32,0);self.call(self.word(q+16),self.out,q)
class ModuleTests(unittest.TestCase):
 def test_bind_real_original_autoconfig_and_descriptor_copy(self):
  p=ModuleProbe();self.assertEqual(p.bind(),0)
  self.assertEqual(p.word(p.audio+0x94),p.out)
  for off,hs in [(8,False),(12,True)]:
   table=p.word(p.audio+off);self.assertTrue(table);endpoints=[]
   for i in range(16):
    a=p.word(table+i*4)
    if not a:break
    n=p.u.mem_read(a,2)[0];d=bytes(p.u.mem_read(a,n))
    if d[1]==5:endpoints.append(d)
   self.assertEqual(len(endpoints),2);self.assertEqual(endpoints[0][6],4 if hs else 1)
 def test_bind_start_and_raw_pcm_no_channel_or_sample_changes(self):
  p=ModuleProbe();self.assertEqual(p.bind(),0);self.assertEqual(p.start(),0);self.assertEqual(len(p.queues[p.out]),8);self.assertEqual(len(p.queues[p.feedback]),1)
  data=struct.pack('<hh',1234,-5678)*48
  for _ in range(80):p.deliver(data);p.pump()
  self.assertEqual(p.pcm_bytes,data*80);self.assertEqual(p.word(p.gp+24),0x7fffffff)
 def test_feedback_irq_tracks_pcm_pointer_and_requeues_no_sleeping_calls(self):
  p=ModuleProbe();p.bind();p.start();played=0
  for ms in range(200):
   p.frame=ms;p.deliver(bytes(192));p.pump()
   if p.word(p.status)==3:played+=48;p.word(p.status+8,(played//256*256)%(1<<20))
   request=p.queues[p.feedback].pop(0);p.word(request+32,0);p.calls.clear();p.call(p.word(request+16),p.feedback,request)
   q=int.from_bytes(p.u.mem_read(p.word(request),4),'little')
   self.assertTrue((6<<16)-393<=q<=(6<<16)+393)
   self.assertFalse(any(x[0] in ['snd_pcm_kernel_ioctl','snd_pcm_lib_write','cancel_work_sync','__kmalloc'] for x in p.calls))
   self.assertEqual(p.queues[p.feedback],[request])
 def test_startup_prefills_before_first_pcm_write(self):
  p=ModuleProbe();p.bind();p.start();p.deliver(bytes(192));p.pump();self.assertEqual(len(p.pcm_bytes),0,'must prefill a reservoir before starting DMA')
 def test_repeated_alt_and_stop_unbind_release_every_allocation(self):
  p=ModuleProbe();p.bind();p.start();count=p.alloc_count;self.assertEqual(p.start(),0);self.assertEqual(p.alloc_count,count)
  p.call('c10_set_alt',p.audio,1,0);self.assertEqual(p.queues[p.out],[]);self.assertEqual(p.queues[p.feedback],[])
  p.call('c10_unbind',p.config,p.audio);self.assertFalse(set(p.allocs)-p.freed)
class FailureTests(unittest.TestCase):
 def test_every_bind_allocation_failure_releases_owned_memory(self):
  normal=ModuleProbe();self.assertEqual(normal.bind(),0);count=normal.alloc_count
  for fail in range(1,count+1):
   p=ModuleProbe();p.fail_alloc=fail
   self.assertLess(p.bind(),0,fail);self.assertFalse(set(p.allocs)-p.freed,fail)
 def test_enable_or_queue_failure_leaves_no_live_requests(self):
  for op in ['enable','queue']:
   for endpoint in ['out','feedback']:
    p=ModuleProbe();p.bind();setattr(p,'fail_'+op,getattr(p,endpoint))
    self.assertLess(p.start(),0,(op,endpoint))
    self.assertFalse(any(p.queues.values()),(op,endpoint));p.call('c10_unbind',p.config,p.audio)
    self.assertFalse(set(p.allocs)-p.freed)
 def test_partial_pcm_writes_preserve_all_bytes_and_addr_limit(self):
  p=ModuleProbe();p.bind();p.start();p.pcm_result=17;data=struct.pack('<hh',3000,-1000)*48
  for _ in range(60):p.deliver(data);p.pump()
  self.assertEqual(bytes(p.pcm_bytes),data*60);self.assertEqual(p.word(p.gp+24),0x7fffffff)
 def test_pcm_error_stops_instead_of_dropping_or_replaying(self):
  for failure in [0,-32]:
   p=ModuleProbe();p.bind();p.start();p.pcm_result=failure
   for _ in range(45):
    if not p.queues[p.out]:break
    p.deliver(bytes(192));p.pump()
   self.assertEqual(p.word(p.gp+24),0x7fffffff);n=len(p.pcm_bytes)
   p.pcm_result=None;p.pump();self.assertEqual(len(p.pcm_bytes),n)
   p.call('c10_unbind',p.config,p.audio);self.assertFalse(set(p.allocs)-p.freed)
 def test_pcm_backpressure_is_nonblocking_and_retries_without_loss(self):
  p=ModuleProbe();p.bind();p.start();p.require_nonblock=True;p.word(p.substream+0xa4,0x100);p.pcm_result=-11
  data=struct.pack('<hh',123,-456)*48
  for _ in range(60):p.deliver(data);p.pump()
  self.assertEqual(p.pcm_bytes,b'');self.assertEqual(p.word(p.substream+0xa4),0x100);self.assertEqual(p.word(p.gp+24),0x7fffffff)
  p.pcm_result=None;p.pump();self.assertEqual(bytes(p.pcm_bytes),data*60)
 def test_unbind_drops_pcm_before_waiting_for_worker(self):
  p=ModuleProbe();p.bind();p.start();p.calls.clear();p.call('c10_unbind',p.config,p.audio)
  names=[x[0] for x in p.calls];self.assertIn('snd_pcm_kernel_ioctl',names)
  self.assertLess(names.index('snd_pcm_kernel_ioctl'),names.index('cancel_work_sync'))
 def test_full_speed_feedback_length_and_native_frame_units(self):
  p=ModuleProbe();p.word(p.gadget+16,2);p.bind();p.start();q=p.queues[p.feedback][0]
  self.assertEqual(p.word(q+4),3);self.assertEqual(bytes(p.u.mem_read(p.word(q),3)),bytes([0,0,12]))
 def test_stop_start_during_pending_drop_preserves_new_data(self):
  p=ModuleProbe();p.bind();p.start();p.call('c10_set_alt',p.audio,1,0);data=struct.pack('<hh',2222,-3333)*48
  def restart(q,cmd):
   if cmd!=0x20004143:return
   q.after_ioctl=None;q.nested('c10_set_alt',q.audio,1,1)
   for _ in range(60):
    r=q.queues[q.out].pop(0);q.u.mem_write(q.word(r),data);q.word(r+36,len(data));q.word(r+32,0);q.nested(q.word(r+16),q.out,r)
  p.after_ioctl=restart;p.pump();self.assertEqual(bytes(p.pcm_bytes),data*60)
 def test_restart_during_old_pcm_error_does_not_fail_new_generation(self):
  p=ModuleProbe();p.bind();p.start();old=struct.pack('<hh',1111,-1111)*48;new=struct.pack('<hh',2222,-2222)*48
  for _ in range(43):p.deliver(old)
  def restart(q):
   q.inject_pcm=None;q.pcm_result=None;q.nested('c10_set_alt',q.audio,1,0);q.nested('c10_set_alt',q.audio,1,1)
   for _ in range(60):
    r=q.queues[q.out].pop(0);q.u.mem_write(q.word(r),new);q.word(r+36,len(new));q.word(r+32,0);q.nested(q.word(r+16),q.out,r)
  p.inject_pcm=restart;p.pcm_result=-32;p.pump();self.assertEqual(bytes(p.pcm_bytes),new*60)
 def test_bad_packet_is_not_written_to_pcm(self):
  p=ModuleProbe();p.bind();p.start();p.deliver(bytes(191));p.pump();self.assertEqual(p.pcm_bytes,b'')
 def test_irq_alt_stop_calls_no_pcm_ioctl_or_cancel(self):
  p=ModuleProbe();p.bind();p.start();p.calls.clear();p.call('c10_set_alt',p.audio,1,0)
  self.assertFalse(any(c[0] in ['cancel_work_sync','snd_pcm_kernel_ioctl','snd_pcm_lib_write'] for c in p.calls))
if __name__=='__main__':unittest.main(verbosity=2)
