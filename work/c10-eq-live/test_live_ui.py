"""Real MIPS editor/runtime. Only file/FIFO/clock interfaces mocked. No hardware."""
import unittest
from test_eq_trace import TraceProbe
from test_eq_ui import SYMS,STATE,readword,CONFIG,stock,MANIFEST
from unicorn.mips_const import *
PHASE=STATE+304
class LiveProbe(TraceProbe):
 def __init__(self,**kw):
  super().__init__(enabled=False,selection=11,**kw)
  self.packets=[];self.fifo_result=None;self.fifo_kind=0o010600;self.fifo_open=True;self.fifo_error=False
  self.stubs[SYMS['orig_fstat64']]='fstat64';self.after_fgets=None;self.after_write=None
 def result(self,u,value):
  u.reg_write(UC_MIPS_REG_V0,value&0xffffffff);u.reg_write(UC_MIPS_REG_PC,u.reg_read(UC_MIPS_REG_RA))
 def hook(self,u,address,size,data):
  name=self.stubs.get(address);a,b,c=[u.reg_read(x) for x in [UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2]]
  if name=='open' and self.string(a)=='/tmp/cmd':
   self.assert_flags=b;self.result(u,90 if self.fifo_open else -1);return
  if name=='fstat64':
   if not self.fifo_error:u.mem_write(b,bytes(128));self.word(b+24,self.fifo_kind)
   self.result(u,-1 if self.fifo_error else 0);return
  if name=='write' and a==90:
   self.packets.append(bytes(u.mem_read(b,c)).decode());self.result(u,c if self.fifo_result is None else self.fifo_result)
   if self.after_write:self.after_write(self)
   return
  if name=='close' and a==90:self.result(u,0);return
  super().hook(u,address,size,data)
  if name=='fgets' and self.after_fgets:self.after_fgets(self)
 def start(self,on=False):
  self.init()
  if on:self.saved_on()
  self.command('mplayer song.flac');self.word(0x444cd8,0x12345678);self.word(0x444440,1)
 def poll(self,now=100):self.invoke(SYMS['eq_live_poll'],now)
 def confirm(self):
  self.output(b'ANS_pause=no\n');self.poll()
 def prepare_live(self):
  self.start();self.opened();self.release(106);self.confirm();self.packets.clear()
class LiveTests(unittest.TestCase):
 def test_same_song_change_initial_handshake_then_latest_edit_without_save(self):
  p=LiveProbe();p.start();p.opened();p.release(106)
  self.assertEqual(len(p.packets),1);self.assertIn('af_add volume=-200',p.packets[0]);self.assertNotIn(CONFIG,p.files)
  p.select(1);p.release(106);p.release(106) # newest target Vocal while fence pending
  self.assertEqual(len(p.packets),1)
  p.confirm();self.assertIn('equalizer -4:-4:-3:-2:-1:0:0:-2:-3:-4',p.packets[-1]);self.assertNotIn(CONFIG,p.files)
  self.assertEqual(p.string_long(0x2100e000),'');self.assertEqual(readword(p,PHASE),2)
 def test_repeated_band_edits_and_presets_do_not_restart_or_seek(self):
  p=LiveProbe();p.prepare_live();p.select(2);p.release(106);p.release(106)
  self.assertEqual(len(p.packets),2);self.assertEqual(len(p.launched),1)
  self.assertTrue(all('af_cmdline' in x and 'seek' not in x and 'load' not in x for x in p.packets))
  self.assertIn('volume',p.packets[-1]);self.assertNotIn(CONFIG,p.files)
 def test_cancel_restores_saved_sound_and_return_saves_preview(self):
  p=LiveProbe();p.prepare_live();p.select(1);p.release(106);p.release(28)
  self.assertIn('equalizer 0:0:0:0:0:0:0:0:0:0',p.packets[-1]);self.assertNotIn(CONFIG,p.files)
  p.opened();p.release(106);p.select(1);p.release(106);p.release(1)
  self.assertEqual(p.files[CONFIG][8:10],b'\1\1');before=len(p.packets);p.poll();self.assertEqual(len(p.packets),before)
 def test_off_on_same_track_keep_installed_pair_and_no_duplicate_add(self):
  p=LiveProbe();p.prepare_live();p.select(1);p.release(106);p.select(0);p.release(106);p.release(106)
  self.assertEqual(readword(p,PHASE),2);self.assertTrue(all('af_add ' not in x for x in p.packets))
  self.assertIn('equalizer 0:0:-1',p.packets[-1])
 def test_paused_and_stopped_coalesce_without_resuming(self):
  for state in [0,2]:
   p=LiveProbe();p.start();p.word(0x444440,state);p.opened();p.release(106);p.select(1);p.release(106);p.poll(5000)
   self.assertEqual(p.packets,[]);p.word(0x444440,1);p.poll(5010);p.confirm()
   self.assertIn('equalizer 0:0:-1',p.packets[-1]);self.assertTrue(all('pausing_keep_force' in x for x in p.packets))
 def test_pause_during_handshake_freezes_timeout_and_latest_applies_on_resume(self):
  p=LiveProbe();p.start();p.opened();p.release(106);p.word(0x444440,0);p.poll(100000);self.assertEqual(readword(p,PHASE),1)
  p.select(1);p.release(106);p.output(b'ANS_pause=yes\n');p.poll(100010);self.assertEqual(len(p.packets),1)
  p.word(0x444440,1);p.poll(100020);self.assertIn('equalizer 0:0:-1',p.packets[-1])
 def test_eagain_retries_latest_and_rejects_nonfifo_or_short_write(self):
  p=LiveProbe();p.prepare_live();p.fifo_result=-1;p.select(2);p.release(106);p.release(106)
  p.fifo_result=None;p.poll();self.assertIn('equalizer 2:0:0',p.packets[-1]);self.assertEqual(readword(p,PHASE),2)
  for mode in ['regular','short','stat']:
   p=LiveProbe();p.start();p.opened()
   if mode=='regular':p.fifo_kind=0o100600
   elif mode=='short':p.fifo_result=5
   else:p.fifo_error=True
   p.release(106);self.assertEqual(readword(p,PHASE),3)
   if mode!='short':self.assertEqual(p.packets,[])
 def test_no_reader_is_retryable_and_config_lock_not_held_for_io(self):
  p=LiveProbe();p.start();p.fifo_open=False;p.opened();p.release(106);self.assertEqual(readword(p,PHASE),0)
  p.fifo_open=True;p.poll();self.assertEqual(readword(p,PHASE),1)
  self.assertEqual(p.assert_flags&3,1);self.assertTrue(p.assert_flags&0o200);self.assertTrue(p.assert_flags&0o400000)
 def test_failed_install_or_timeout_never_applies_positive_compensation(self):
  for error in [b"Couldn't find audio filter 'equalizer'\n",b'[libaf] Reinitialization did not work\n',None]:
   p=LiveProbe();p.start();p.opened();p.release(106);p.select(2);p.release(106)
   if error:p.output(error);p.output(b'ANS_pause=no\n')
   p.poll(3000);self.assertIn('volume 0.0',p.packets[-1]);self.assertEqual(readword(p,PHASE),4)
   before=len(p.packets);p.release(106);p.poll(9000);self.assertEqual(len(p.packets),before)
 def test_runtime_filter_error_enters_recovery_and_blocks_later_boost(self):
  p=LiveProbe();p.prepare_live();p.output(b"Filter 'equalizer' not found in chain.\n")
  self.assertEqual(readword(p,PHASE),3)
  p.select(2);p.release(106);self.assertIn('volume 0.0',p.packets[-1]);self.assertEqual(readword(p,PHASE),4)
  before=len(p.packets);p.release(106);p.poll(500);self.assertEqual(len(p.packets),before)
 def test_error_on_other_stream_cannot_poison_or_confirm_current_epoch(self):
  p=LiveProbe();p.start();p.opened();p.release(106);p.output(b'ANS_pause=no\n',0x87654321)
  self.assertEqual(readword(p,PHASE),1);p.word(0x444cd8,0x12345678);p.confirm();self.assertEqual(readword(p,PHASE),2)
 def test_fgets_epoch_captured_before_blocking_same_file_pointer_reused(self):
  p=LiveProbe();p.start();p.opened();p.release(106)
  def change(q):q.word(STATE+296,readword(q,STATE+296)+1)
  p.after_fgets=change;p.output(b'ANS_pause=no\n');self.assertEqual(readword(p,PHASE),1)
 def test_next_song_uses_preview_and_cancel_after_next_song_uses_saved(self):
  p=LiveProbe();p.start();p.opened();p.release(106);p.select(1);p.release(106)
  self.assertIn('equalizer=0:0:-1',p.command('mplayer next.flac')[1]);self.assertEqual(readword(p,PHASE),0)
  p.release(28);self.assertEqual(p.command('mplayer next2.flac')[1],'mplayer next2.flac 2>&1')
 def test_edit_during_launch_snapshot_does_not_lose_newer_preview(self):
  p=LiveProbe();p.init();p.opened();p.release(106);p.select(1)
  address=SYMS['eq_options'];triggered=[]
  from unicorn import UC_HOOK_CODE
  def edit(u,a,size,data):
   if triggered:return
   triggered.append(True)
   # UI requests Vocal after launch thread has copied old Flat snapshot.
   p.word(STATE+192,1);p.word(STATE+192+4,2)
   for i,g in enumerate([-4,-4,-3,-2,-1,0,0,-2,-3,-4]):p.word(STATE+192+8+4*i,g)
   p.word(STATE+308,1) # dirty
  h=p.u.hook_add(UC_HOOK_CODE,edit,begin=address,end=address)
  p.command('mplayer song.flac');p.u.hook_del(h)
  self.assertTrue(triggered);p.word(0x444cd8,0x12345678);p.word(0x444440,1);p.poll()
  self.assertTrue(p.packets,'launch cleared newer UI request')
 def test_mainloop_bridge_preserves_volatile_gp_hi_lo_then_dual_timer(self):
  p=LiveProbe();p.init();entry=MANIFEST['bridge_symbols']['c10_eq_poll_entry']
  # Stop before timer entry, whose normal code intentionally changes v0/t9.
  import json
  from pathlib import Path
  old=json.loads((Path(__file__).resolve().parent.parent/'c10-dual-timer/build/patch-manifest.json').read_text())
  p.stops={old['symbols']['c10_power_checks_entry']};p.stopped=None
  regs=[UC_MIPS_REG_AT,UC_MIPS_REG_V0,UC_MIPS_REG_V1,UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3]+[globals()['UC_MIPS_REG_T'+str(i)] for i in range(10)]+[UC_MIPS_REG_GP,UC_MIPS_REG_RA,UC_MIPS_REG_HI,UC_MIPS_REG_LO]
  for i,r in enumerate(regs):p.u.reg_write(r,0x12340000+i)
  before=[p.u.reg_read(r) for r in regs];sp=p.u.reg_read(UC_MIPS_REG_SP);p.run(entry)
  self.assertEqual(before,[p.u.reg_read(r) for r in regs]);self.assertEqual(p.u.reg_read(UC_MIPS_REG_SP),sp)
if __name__=='__main__':unittest.main(verbosity=2)
