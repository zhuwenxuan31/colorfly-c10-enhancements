"""Run the candidate ELF's actual MIPS timer/USB hooks. No hardware or shell."""
from pathlib import Path
import struct
import sys
import unittest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / 'c10-analysis'))
import trace_stock_poweroff as stock
from unicorn.mips_const import (
    UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3,
    UC_MIPS_REG_GP, UC_MIPS_REG_RA, UC_MIPS_REG_S0, UC_MIPS_REG_S1,
    UC_MIPS_REG_S2, UC_MIPS_REG_S3, UC_MIPS_REG_S4, UC_MIPS_REG_S5,
    UC_MIPS_REG_S6, UC_MIPS_REG_S7, UC_MIPS_REG_FP, UC_MIPS_REG_SP,
    UC_MIPS_REG_T9,
)

stock.IMAGE = (BASE / 'build/ap.sleep-candidate.dge').read_bytes()
OPTION = 0x4463c0


def readword(p, address):
    return struct.unpack('<I', p.u.mem_read(address, 4))[0]


def tick(p, now, state=1, last_key=0):
    p.stopped = None
    p.calls.clear()
    p.stops = {0x41b964, 0x41ba48}
    p.u.reg_write(UC_MIPS_REG_S0, now & 0xffffffff)
    p.u.reg_write(UC_MIPS_REG_S3, 1)
    p.u.reg_write(UC_MIPS_REG_S5, last_key & 0xffffffff)
    p.u.reg_write(UC_MIPS_REG_S6, 0x440000)
    p.word(0x444440, state)
    p.run(0x41b918)
    return p.stopped == 0x41ba48


def arm(selection, now=1000):
    p = stock.Probe(selection)
    assert not tick(p, (now - 100) & 0xffffffff)
    assert readword(p, OPTION) == 0
    p.word(OPTION, selection)
    assert not tick(p, now)
    return p


class TimerMachineTests(unittest.TestCase):
    def test_actual_30_60_90_minute_boundaries(self):
        for option, duration in [(1, 1800000), (2, 3600000), (3, 5400000)]:
            with self.subTest(option=option):
                p = arm(option)
                self.assertFalse(tick(p, 1000 + duration - 1))
                self.assertTrue(tick(p, 1000 + duration))
                self.assertEqual(readword(p, OPTION), 0)
                self.assertFalse(tick(p, 1000 + duration + 1000))

    def test_play_pause_and_keys_do_not_reset_countdown(self):
        p = arm(1)
        self.assertFalse(tick(p, 600000, state=1, last_key=599999))
        self.assertFalse(tick(p, 1200000, state=2, last_key=1200000))
        self.assertTrue(tick(p, 1801000, state=2, last_key=1801000))

    def test_disable_and_change_duration(self):
        p = arm(1)
        p.word(OPTION, 0)
        self.assertFalse(tick(p, 9000000))
        p.word(OPTION, 2)
        self.assertFalse(tick(p, 10000000))
        self.assertFalse(tick(p, 13599999))
        self.assertTrue(tick(p, 13600000))

    def test_boot_never_inherits_stored_setting(self):
        p = stock.Probe(2)
        self.assertFalse(tick(p, 8000000))
        self.assertEqual(readword(p, OPTION), 0)
        self.assertFalse(tick(p, 16000000))

    def test_unsigned_tick_wrap(self):
        p = arm(1, 0xffff0000)
        self.assertFalse(tick(p, 0xffff0000 + 1799999))
        self.assertTrue(tick(p, 0xffff0000 + 1800000))

    def test_usb_cancel_replays_original_loads_and_preserves_arguments(self):
        p = arm(1)
        args = [UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3]
        for i, reg in enumerate(args):
            p.u.reg_write(reg, 0x1230 + i)
        p.stopped = None
        p.stops = {0x41b790}
        p.run(0x41b788)
        self.assertEqual(readword(p, OPTION), 0)
        self.assertEqual(readword(p, 0x446bf4), 0)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_S0), 0x4463ac)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_T9), readword(p, stock.GP - 0x7f58))
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_GP), stock.GP)
        for i, reg in enumerate(args):
            self.assertEqual(p.u.reg_read(reg), 0x1230 + i)
        self.assertFalse(tick(p, 9000000))

    def test_callee_saved_registers_and_stack(self):
        p = arm(1)
        regs = [UC_MIPS_REG_S1, UC_MIPS_REG_S2, UC_MIPS_REG_S4,
                UC_MIPS_REG_S7, UC_MIPS_REG_FP]
        for i, reg in enumerate(regs):
            p.u.reg_write(reg, 0x50 + i)
        before_sp = p.u.reg_read(UC_MIPS_REG_SP)
        self.assertFalse(tick(p, 1001, last_key=777))
        for i, reg in enumerate(regs):
            self.assertEqual(p.u.reg_read(reg), 0x50 + i)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_S3), 1)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_S5), 777)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_S6), 0x440000)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_GP), stock.GP)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_SP), before_sp)

    def test_expiry_reaches_original_player_cleanup_branch(self):
        p = arm(1)
        self.assertTrue(tick(p, 1801000))
        p.stopped = None
        p.stops = {0x41ba84}
        p.word(0x44446c, 1)
        p.run(0x41ba48)
        self.assertEqual([c['call'] for c in p.calls], ['mplayerclose', 'puts'])
        self.assertEqual(readword(p, 0x44446c), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
