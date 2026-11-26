"""Diagnostic marker, exact launch/output capture, bounded log; MIPS emulator.
All IO mocked in memory. No host process/audio/USB syscall executes.
"""
import unittest
from test_eq_ui import EQProbe,STATE,SYMS,stock,readword
from unicorn.mips_const import *
MARKER='/mnt/memory/.c10-eq-diag'
LOG='/mnt/memory/.c10-eq-runtime.log'
LIMIT=65536

class TraceProbe(EQProbe):
    def __init__(self,enabled=True,**kw):
        super().__init__(**kw)
        self.lines=[]
        if enabled:self.files[MARKER]=bytearray(b'1\n')
    def hook(self,u,address,size,data):
        if self.stubs.get(address)!='fgets':return super().hook(u,address,size,data)
        buf=u.reg_read(UC_MIPS_REG_A0);size=u.reg_read(UC_MIPS_REG_A1)
        line=self.lines.pop(0) if self.lines else None
        if line is not None:u.mem_write(buf,line[:size-1]+b'\0')
        u.reg_write(UC_MIPS_REG_V0,buf if line is not None else 0)
        u.reg_write(UC_MIPS_REG_GP,0x12345678) # caller must restore GP.
        u.reg_write(UC_MIPS_REG_PC,u.reg_read(UC_MIPS_REG_RA))
    def output(self,line,stream=0x12345678):
        self.lines.append(line);self.word(0x444cd8,stream)
        self.u.reg_write(UC_MIPS_REG_S0,0x440000)
        self.u.reg_write(UC_MIPS_REG_S3,0x2100e000)
        self.u.reg_write(UC_MIPS_REG_GP,stock.GP)
        self.stopped=None;self.stops={0x41f7f4}
        sp=self.u.reg_read(UC_MIPS_REG_SP)
        self.run(0x41f7e0)
        assert self.u.reg_read(UC_MIPS_REG_SP)==sp
        assert self.u.reg_read(UC_MIPS_REG_GP)==stock.GP
        return self.u.reg_read(UC_MIPS_REG_V0)

class TraceTests(unittest.TestCase):
    def test_enabled_marker_creates_boot_record(self):
        p=TraceProbe();p.init()
        self.assertIn(LOG,p.files)
        self.assertIn(b'C10_EQ_LIVE_v70 boot',p.files[LOG])
    def test_absent_or_invalid_marker_has_no_diagnostic_side_effects(self):
        for marker in [None,b'0\n',b'',b'junk']:
            p=TraceProbe(enabled=False)
            if marker is not None:p.files[MARKER]=bytearray(marker)
            p.init();cmd=p.command('mplayer "song.flac"')
            self.assertNotEqual(cmd[0],0x2100d000)
            self.assertEqual(cmd[1],'mplayer "song.flac" 2>&1')
            self.assertNotIn(LOG,p.files)
    def test_actual_launch_records_active_settings_and_exact_command(self):
        p=TraceProbe();p.init();p.saved_on()
        _,cmd,mode,gp=p.command('mplayer "song.flac"')
        self.assertTrue(cmd.endswith(' -v 2>&1'))
        self.assertIn(' -af-add equalizer=',cmd)
        self.assertIn(cmd.encode(),p.files[LOG])
        self.assertIn(b'enabled=1 preset=1',p.files[LOG])
        self.assertEqual(mode,'r');self.assertEqual(gp,stock.GP)
    def test_off_diagnostic_records_original_without_equalizer(self):
        p=TraceProbe();p.init();_,cmd,_,_=p.command('mplayer x')
        self.assertEqual(cmd,'mplayer x -v 2>&1')
        self.assertIn(b'enabled=0',p.files[LOG])
    def test_patched_stdout_callsite_preserves_data_pointer_mode_and_gp(self):
        p=TraceProbe();p.init();p.command('mplayer x')
        line=b'[libaf] Adding filter equalizer\n'
        self.assertEqual(p.output(line),0x2100e000)
        self.assertEqual(p.string_long(0x2100e000),line.decode())
        self.assertIn(line,p.files[LOG])
        before=bytes(p.files[LOG]);self.assertEqual(p.output(None),0)
        self.assertEqual(bytes(p.files[LOG]),before)
    def test_failed_log_writes_do_not_prevent_launch_or_alter_stdout(self):
        for failure in ['open','write','close']:
            p=TraceProbe();p.init();p.fail=failure
            self.assertEqual(p.command('mplayer x')[1],'mplayer x -v 2>&1')
            self.assertEqual(p.output(b'AUDIO: 44100 Hz\n'),0x2100e000)
            self.assertEqual(p.string_long(0x2100e000),'AUDIO: 44100 Hz\n')
    def test_disabled_trace_and_busy_trace_lock_still_return_stdout(self):
        p=TraceProbe(enabled=False);p.init();p.command('mplayer x')
        self.assertEqual(p.output(b'AUDIO: 48000 Hz\n'),0x2100e000)
        self.assertEqual(p.string_long(0x2100e000),'AUDIO: 48000 Hz\n')
        self.assertNotIn(LOG,p.files)
        q=TraceProbe();q.init();before=bytes(q.files[LOG]);q.word(STATE+176,1)
        self.assertTrue(q.command('mplayer x')[1].endswith(' -v 2>&1'))
        self.assertEqual(q.output(b'while log busy\n'),0x2100e000)
        self.assertEqual(bytes(q.files[LOG]),before)
    def test_log_size_cap_and_unrelated_stream_exclusion(self):
        p=TraceProbe();p.init();p.command('mplayer x')
        for _ in range(80):p.output(b'x'*1022+b'\n')
        self.assertLessEqual(len(p.files[LOG]),LIMIT)
        self.assertGreater(len(p.files[LOG]),LIMIT-2048)
        before=bytes(p.files[LOG]);p.output(b'UNRELATED\n',stream=0x87654321)
        self.assertEqual(bytes(p.files[LOG]),before)

if __name__=='__main__':unittest.main(verbosity=2)
