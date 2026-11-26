"""Actual original slave parser/run_command/libaf dynamic PCM checks, offline.
Only libc memory/strings/logging are mocked; no MPlayer command handler,
property, filter control/reinit or audio-driver initializer is mocked.
"""
from pathlib import Path
import sys,struct,math,json
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'c10-eq/v66-audio-investigation'))
from probe_full_cli import CLI
from unicorn.mips_const import *

class LiveNative(CLI):
 def __init__(self,filters=(),rate=44100,fmt=9,bps=2):
  super().__init__()
  # Reconfigure the real af stream fixture before its first initialization.
  self.rate,self.sample_format,self.bps=rate,fmt,bps
  self.u.mem_write(self.stream+8,struct.pack('<6I',0,0,rate,2,fmt,bps))
  self.u.mem_write(self.stream+32,struct.pack('<6I',0,0,rate,2,fmt,bps))
  pos=self.string_area
  for i,text in enumerate(filters):
   b=text.encode()+b'\0';self.u.mem_write(pos,b);self.word(self.list+4*i,pos);pos+=len(b)
  self.word(self.list+len(filters)*4,0)
  assert self.initialize()==0
  self.ctx=0xfda1f8;self.sh=0x10008000
  self.word(self.ctx+0x28,self.sh);self.word(self.ctx+0x2c,0)
  self.word(self.ctx+0x40,self.stream);self.word(self.ctx+4,0)
  self.word(self.sh+0x7c,self.stream);self.word(self.sh+0x38,fmt)
  self.word(self.sh+0x3c,rate);self.word(self.sh+0x44,2)
  self.word(0xff6c84,0x402)
  ao=self.symbols['ao_data'];self.word(ao,rate);self.word(ao+4,2);self.word(ao+8,fmt)
  self.in_command=False;self.hardware_calls=[];self.output=[];self.af_play_during_command=0
  self.forbidden={self.symbols[n]:n for n in ['init_best_audio_out','uninit_player','__libc_open','__libc_write','__libc_ioctl'] if n in self.symbols}
 def hook(self,u,address,size,data):
  if getattr(self,'in_command',False):
   if address in self.forbidden:
    self.hardware_calls.append(self.forbidden[address]);raise AssertionError(('unexpected audio/device call',self.forbidden[address]))
   if address==self.symbols['af_play']:self.af_play_during_command+=1
  if hasattr(self,'output') and self.stubs.get(address)=='mp_msg':
   a=u.reg_read(UC_MIPS_REG_A2);fmt=self.string(a).decode(errors='replace')
   if fmt=='ANS_%s=%s\n':
    name=self.string(u.reg_read(UC_MIPS_REG_A3)).decode()
    arg=self.readword(u.reg_read(UC_MIPS_REG_SP)+16);value=self.string(arg).decode()
    self.output.append(f'ANS_{name}={value}\n')
   else:self.output.append(fmt)
  return super().hook(u,address,size,data)
 def command(self,line):
  p=self.allocate(line.strip().encode()+b'\0')
  cmd=self.call(self.symbols['mp_input_parse_cmd'],p,count=1000000)
  assert cmd,line
  assert self.readword(cmd+0x5c)==4,(line,self.readword(cmd+0x5c))
  self.in_command=True
  try:r=self.call(self.symbols['run_command'],self.ctx,cmd,count=4000000)
  finally:self.in_command=False
  assert self.af_play_during_command==0
  return r
 def current_gains(self):
  name=self.allocate(b'equalizer\0');af=self.call(self.symbols['af_get'],self.stream,name)
  assert af
  self.u.mem_write(self.argument,struct.pack('<II',self.gains_area,0))
  assert self.call(self.readword(af+4),af,0x40001d01,self.argument)==1
  return struct.unpack('<10f',self.u.mem_read(self.gains_area,40))
 @property
 def gains_area(self):return 0x1000a000
 def rms(self):
  peak=(1<<(self.bps*8-1))-1
  samples=[v for i in range(1024) for v in [int(peak*.36*math.sin(2*math.pi*1000*i/self.rate))]*2]
  _,audio=self.process_pcm(samples)
  ratio=math.sqrt(sum(x*x for x in audio[-512:])/sum(x*x for x in samples[-512:]))
  return ratio,max(map(abs,audio))/peak

if __name__=='__main__':
 p=LiveNative(['equalizer=0:0:0:0:0:0:0:0:0:0','volume=0:0:0'])
 print('initial',p.graph(),flush=True)
 p.command('pausing_keep_force af_cmdline equalizer -12:-12:-12:-12:-12:-12:-12:-12:-12:-12')
 assert p.current_gains()==(-12.,)*10
 p.command('pausing_keep_force get_property pause')
 assert p.output[-1]=='ANS_pause=no\n',p.output[-5:]
 print('dynamic cut',p.rms(),p.hardware_calls,flush=True)
 q=LiveNative([])
 for line in [
  'pausing_keep_force af_add volume=-200.0:0:0,equalizer=0:0:0:0:0:0:0:0:0:0',
  'pausing_keep_force af_cmdline volume -200.0:0:0',
  'pausing_keep_force af_cmdline equalizer 0:0:0:0:0:0:0:0:0:0',
  'pausing_keep_force get_property pause']:
  q.command(line)
 print('lazy graph',q.graph(),'ack',q.output[-1],flush=True)
 assert q.output[-1]=='ANS_pause=no\n'
 assert all(x['format']==29 for x in q.graph() if x['name'] in ['equalizer','volume'])
 assert [x['name'] for x in q.graph()].index('equalizer')<[x['name'] for x in q.graph()].index('volume')
 assert q.hardware_calls==[]
 q.command('pausing_keep_force af_cmdline equalizer -12:-12:-12:-12:-12:-12:-12:-12:-12:-12')
 q.command('pausing_keep_force af_cmdline volume 0.0:0:0')
 print('lazy cut',q.rms(),flush=True)
 assert q.rms()[0]<.5
 print('PASS: native dynamic control, unique pause fence, lazy float order and no AO re-open',flush=True)
