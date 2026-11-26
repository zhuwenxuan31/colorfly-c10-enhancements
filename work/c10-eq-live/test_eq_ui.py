"""Execute patched MIPS UI/IO/launch paths. All external IO is in-memory.
No USB, host shutdown, shell or audio process is executed.
"""
from pathlib import Path
import json
import struct
import sys
import unittest
from unicorn import UC_PROT_READ, UC_PROT_EXEC
from unicorn.mips_const import *

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'c10-sleep-timer'))
from test_main_menu import MenuProbe
from test_mips_patch import readword
import trace_stock_poweroff as stock
MANIFEST=json.loads((BASE/'build/patch-manifest.json').read_text())
SYMS=MANIFEST['module_symbols']
stock.IMAGE=(BASE/'build/ap.eq-candidate.dge').read_bytes()
STATE=0x446d00
CONFIG='/mnt/memory/.c10-eq.cfg'
TEMP='/mnt/memory/.c10-eq.tmp'

class EQProbe(MenuProbe):
    def __init__(self,**kw):
        super().__init__(**kw)
        self.files={};self.fds={};self.io=[];self.launched=[];self.fail=None;self.short=False
        self.stubs[SYMS['orig_rename']]='rename'
        self.stubs[0x418ef8]='stock_init'
        self.u.mem_protect(0x450000,(MANIFEST['module_bytes']+4095)&~4095,UC_PROT_READ|UC_PROT_EXEC)
    def run(self,entry):
        self.u.emu_start(entry,0,count=1000000)
        assert self.stopped is not None,'Instruction bound reached'
    def invoke(self,entry,a0=0,a1=0):
        self.u.reg_write(UC_MIPS_REG_T9,entry)
        super().invoke(entry,a0,a1)
    def hook(self,u,address,size,data):
        name=self.stubs.get(address)
        if name not in {'open','read','write','close','fsync','unlink','rename','popen','stock_init'}:
            return super().hook(u,address,size,data)
        a,b,c=[u.reg_read(r) for r in (UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2)]
        result=0
        if name=='open':
            path=self.string(a);self.io.append((name,path,b,c))
            if self.fail=='open' or (not b&1 and path not in self.files):result=-1
            else:
                if b&1 and (b&0x200 or path not in self.files):self.files[path]=bytearray()
                fd=10+len(self.fds);self.fds[fd]=[path,len(self.files[path]) if b&8 else 0];result=fd
        elif name in {'read','write'}:
            path,pos=self.fds[a]
            if self.fail==name:result=-1
            elif name=='read':
                chunk=self.files[path][pos:pos+min(c,7) if self.short else pos+c]
                if chunk:u.mem_write(b,bytes(chunk))
                result=len(chunk)
            else:
                n=min(c,7) if self.short else c
                chunk=bytes(u.mem_read(b,n));self.files[path][pos:pos+n]=chunk;result=n
            if result>0:self.fds[a][1]+=result
        elif name=='unlink':self.files.pop(self.string(a),None)
        elif name=='rename':
            self.io.append((name,self.string(a),self.string(b)))
            if self.fail==name:result=-1
            else:self.files[self.string(b)]=self.files.pop(self.string(a))
        elif name in {'fsync','close'}:
            self.io.append((name,a));result=-1 if self.fail==name else 0
        elif name=='popen':
            self.launched.append((a,self.string_long(a),self.string(b),u.reg_read(UC_MIPS_REG_GP)))
            result=0x12345678
        elif name=='stock_init':result=0xfffffffe
        u.reg_write(UC_MIPS_REG_V0,result&0xffffffff)
        u.reg_write(UC_MIPS_REG_PC,u.reg_read(UC_MIPS_REG_RA))
    def string_long(self,a):
        return bytes(self.u.mem_read(a,2048)).split(b'\0',1)[0].decode()
    def init(self):self.invoke(SYMS['eq_init'])
    def opened(self):
        self.word(0x444b5c,11);self.release(106)
        assert readword(self,STATE+156)==1
    def select(self,row):
        while readword(self,STATE+160)!=row:self.release(108)
    def saved_on(self):
        self.opened();self.release(106);self.select(1);self.release(106)
        self.select(13);self.release(106)
    def command(self,text):
        ptr=0x2100d000;self.u.mem_write(ptr,text.encode()+b'\0')
        self.u.reg_write(UC_MIPS_REG_A0,0xdeadbeef) # Original callsite must replace it with s4.
        self.u.reg_write(UC_MIPS_REG_S4,ptr)
        self.u.reg_write(UC_MIPS_REG_GP,stock.GP)
        self.stopped=None;self.stops={0x41ec00}
        self.run(0x41ebec)
        assert self.u.reg_read(UC_MIPS_REG_V0)==0x12345678
        assert self.u.reg_read(UC_MIPS_REG_S4)==0x430000
        assert self.string_long(ptr)==text
        return self.launched[-1]

class EQMenuTests(unittest.TestCase):
    def test_new_load_segment_preserves_factory_64k_alignment(self):
        from elftools.elf.elffile import ELFFile
        import io
        elf=ELFFile(io.BytesIO(stock.IMAGE))
        segment=next(s for s in elf.iter_segments() if s['p_type']=='PT_LOAD' and s['p_vaddr']==0x450000)
        self.assertEqual(segment['p_align'],65536)
        self.assertEqual(segment['p_offset']%65536,0)
    def test_equalizer_is_its_own_main_menu_entry(self):
        p=EQProbe(selection=11)
        self.assertIn('均衡器 EQ',[r['text'] for r in p.draw() if r['kind']=='label'])
    def test_held_navigation_stays_in_eq_and_can_save_enabled(self):
        p=EQProbe(selection=11);p.init();p.opened();p.release(106)
        p.invoke(0x426230,108,0)
        for _ in range(13):
            p.invoke(0x426230,108,1)
            p.draw() # Real main loop redraws between held-key repeats.
            self.assertEqual(readword(p,0x444b5c),11)
            self.assertEqual(readword(p,STATE+156),1)
        self.assertEqual(readword(p,STATE+160),13)
        p.invoke(0x425a30,108,1) # A repeated key's release must not move twice.
        self.assertEqual(readword(p,STATE+160),13)
        p.invoke(0x426230,106,0);p.release(106)
        self.assertEqual(readword(p,STATE+156),0)
        self.assertEqual(p.files[CONFIG][8],1)
        p.opened();self.assertEqual(readword(p,STATE+108),1)
    def test_actual_short_press_release_save_sequence_with_redraw(self):
        p=EQProbe(selection=11);p.init()
        def tap(key):
            p.invoke(0x426230,key,0);p.draw();p.release(key);p.draw()
        tap(106);tap(106) # Open, then enable.
        tap(108);tap(106) # Bass preset.
        for _ in range(12):tap(108)
        self.assertEqual(readword(p,STATE+160),13)
        tap(106)
        self.assertEqual(p.files[CONFIG][8:10],bytes([1,1]))
        self.assertIn('equalizer=0:0:-1:-3:-4:-4:-3:-3:-3:-3',p.command('mplayer song.flac')[1])
    def test_key_down_fallback_retains_factory_behavior_outside_eq(self):
        candidate=stock.IMAGE
        original=(BASE.parent/'c10-dual-timer/build/ap.dual-candidate.dge').read_bytes()
        try:
            for key in [1,28,103,108,105,106,999]:
                for repeated in [0,1]:
                    stock.IMAGE=original;p=MenuProbe(selection=5)
                    p.invoke(0x426230,key,repeated)
                    stock.IMAGE=candidate;q=EQProbe(selection=5)
                    sp=q.u.reg_read(UC_MIPS_REG_SP);q.invoke(0x426230,key,repeated)
                    for addr,size in [(0x444b34,4),(0x444b5c,4),(0x446384,40),(0x4463ac,36)]:
                        self.assertEqual(p.u.mem_read(addr,size),q.u.mem_read(addr,size),(key,repeated,hex(addr)))
                    self.assertEqual(q.u.reg_read(UC_MIPS_REG_SP),sp)
                    self.assertEqual(q.u.reg_read(UC_MIPS_REG_GP),stock.GP)
        finally:stock.IMAGE=candidate
    def test_right_opens_full_panel_with_original_navigation_and_cancel(self):
        p=EQProbe(selection=11);p.init();p.opened()
        labels=[r['text'] for r in p.draw() if r['kind']=='label']
        self.assertEqual(labels,['EQ开关','预设','31 Hz','63 Hz','125 Hz','250 Hz','500 Hz'])
        p.release(103);self.assertEqual(readword(p,STATE+160),15)
        p.release(108);self.assertEqual(readword(p,STATE+160),0)
        p.release(106);p.release(28)
        self.assertEqual(readword(p,STATE+156),0)
        self.assertEqual(p.command('mplayer "song.flac"')[1],'mplayer "song.flac" 2>&1')
        self.assertEqual(p.files,{})
    def test_factory_back_key_saves_on_and_publishes_main_menu_value(self):
        p=EQProbe(selection=11);p.init();p.opened();p.release(106)
        p.select(1);p.release(106);p.release(106);p.release(1)
        self.assertEqual(readword(p,STATE+156),0)
        self.assertIn(CONFIG,p.files)
        self.assertEqual(p.files[CONFIG][8:10],bytes([1,2]))
        self.assertIn('人声',[r['text'] for r in p.draw() if r['kind']=='value'])
        p.opened();self.assertEqual(readword(p,STATE+108),1)
        self.assertIn(' -af-add equalizer=',p.command('mplayer song.flac')[1])
    def test_factory_back_key_can_save_off_after_on(self):
        p=EQProbe(selection=11);p.init();p.saved_on();p.opened()
        p.release(106);p.release(1)
        self.assertEqual(p.files[CONFIG][8],0)
        self.assertEqual(p.command('mplayer song.flac')[1],'mplayer song.flac 2>&1')
    def test_failed_back_save_keeps_old_file_active_and_edit_page(self):
        for failure in ['open','write','fsync','close','rename']:
            p=EQProbe(selection=11);p.init();p.saved_on();old=bytes(p.files[CONFIG])
            p.opened();p.release(106);p.fail=failure;p.release(1)
            self.assertEqual(readword(p,STATE+156),1)
            self.assertEqual(readword(p,STATE+168),1)
            self.assertEqual(bytes(p.files[CONFIG]),old)
            self.assertNotIn(' -af-add equalizer=',p.command('mplayer song.flac')[1]) # unsaved OFF preview remains audible
    def test_explicit_cancel_and_play_key_do_not_publish_or_save(self):
        for cancel in ['row15','play']:
            p=EQProbe(selection=11);p.init();p.opened();p.release(106)
            if cancel=='row15':p.select(15);p.release(106)
            else:p.release(28)
            self.assertNotIn(CONFIG,p.files)
            self.assertEqual(p.command('mplayer song.flac')[1],'mplayer song.flac 2>&1')
    def test_all_panel_rows_and_languages_draw_within_screen(self):
        for lang in range(3):
            p=EQProbe(language=lang,selection=11);p.init();p.opened()
            for row in range(16):
                p.select(row);records=p.draw()
                labels=[r for r in records if r['kind']=='label']
                self.assertEqual(len(labels),7)
                self.assertEqual(sum(r['selected'] for r in labels),1)
                self.assertTrue(all(40<=r['y']<330 for r in labels))
    def test_off_launch_has_no_dsp_but_captures_control_stderr(self):
        p=EQProbe();p.init()
        a,cmd,mode,gp=p.command('mplayer -slave "中文 song.flac" -af dummy')
        self.assertNotEqual(a,0x2100d000);self.assertEqual(mode,'r');self.assertEqual(gp,stock.GP)
        self.assertEqual(cmd,'mplayer -slave "中文 song.flac" -af dummy 2>&1')
    def test_on_uses_separate_buffer_and_preserves_existing_options(self):
        p=EQProbe();p.init();p.saved_on()
        a,cmd,mode,gp=p.command('mplayer -slave "song.mp3" -af dummy')
        self.assertNotEqual(a,0x2100d000)
        self.assertTrue(cmd.startswith('mplayer -slave "song.mp3" -af dummy -af-add equalizer='))
        self.assertIn(',volume=0.0:0:0',cmd);self.assertEqual(mode,'r')
        self.assertEqual(gp,stock.GP)
    def test_partial_io_save_is_atomic_and_survives_new_process(self):
        p=EQProbe();p.init();p.short=True;p.saved_on()
        self.assertEqual(len(p.files[CONFIG]),64);self.assertNotIn(TEMP,p.files)
        self.assertEqual([x[0] for x in p.io][-3:],['fsync','close','rename'])
        boot=EQProbe();boot.files={k:bytearray(v) for k,v in p.files.items()};boot.short=True;boot.init()
        self.assertIn(' -af-add equalizer=',boot.command('mplayer x')[1])
    def test_each_write_failure_keeps_old_active_config_and_no_temp(self):
        for failure in ['open','write','fsync','close','rename']:
            p=EQProbe();p.init();p.fail=failure;p.saved_on()
            self.assertEqual(readword(p,STATE+156),1)
            self.assertEqual(readword(p,STATE+168),1)
            self.assertNotIn(TEMP,p.files)
            self.assertIn(' -af-add equalizer=',p.command('mplayer x')[1]) # failed save keeps preview, not saved config
            self.assertEqual(readword(p,STATE+12),0)
    def test_bad_short_long_and_corrupt_records_fail_closed(self):
        good=EQProbe();good.init();good.saved_on();record=good.files[CONFIG]
        corrupt=bytearray(record);corrupt[15]^=1
        for raw in [b'',b'bad',record[:-1],record+b'X',corrupt]:
            p=EQProbe();p.files[CONFIG]=bytearray(raw);p.init()
            self.assertEqual(p.command('mplayer x')[1],'mplayer x 2>&1')
            self.assertEqual(readword(p,STATE+168),2)
    def test_oversized_command_falls_back_without_mutating_it(self):
        p=EQProbe();p.init();p.saved_on();text='mplayer '+('a'*1000)
        self.assertEqual(p.command(text)[0],0x2100d000)
        self.assertEqual(readword(p,STATE+168),3)
    def test_startup_hook_keeps_original_result_gp_and_stack(self):
        p=EQProbe();sp=p.u.reg_read(UC_MIPS_REG_SP)
        p.stops={0x41c224};p.stopped=None;p.run(0x41c21c)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_V0),0xfffffffe)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_GP),stock.GP)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_SP),sp)
        self.assertEqual(readword(p,STATE),0x45513031)
    def test_edit_limits_save_custom_and_readonly_headroom(self):
        p=EQProbe();p.init();p.opened();p.select(2)
        for _ in range(20):p.release(106)
        self.assertEqual(readword(p,STATE+108+8),12)
        self.assertEqual(readword(p,STATE+108+4),5)
        p.select(12);before=bytes(p.u.mem_read(STATE+108,48));p.release(106)
        self.assertEqual(bytes(p.u.mem_read(STATE+108,48)),before)
        p.select(14);p.release(106)
        self.assertEqual(readword(p,STATE+108),0)
    def test_timer_state_and_stock_properties_untouched_by_eq_save(self):
        p=EQProbe();p.init()
        p.u.mem_write(0x446bf0,bytes(range(32)))
        before=bytes(p.u.mem_read(0x4463ac,36));p.saved_on()
        self.assertEqual(bytes(p.u.mem_read(0x446bf0,32)),bytes(range(32)))
        self.assertEqual(bytes(p.u.mem_read(0x4463ac,36)),before)

if __name__=='__main__':unittest.main(verbosity=2)
