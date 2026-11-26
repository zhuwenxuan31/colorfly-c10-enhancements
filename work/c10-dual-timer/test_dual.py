from pathlib import Path
import sys
import unittest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / 'c10-sleep-timer'))
from test_main_menu import MenuProbe
from test_mips_patch import tick, readword
import trace_stock_poweroff as stock
from unicorn.mips_const import (
    UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3,
    UC_MIPS_REG_GP, UC_MIPS_REG_S0, UC_MIPS_REG_S1, UC_MIPS_REG_S2,
    UC_MIPS_REG_S3, UC_MIPS_REG_S4, UC_MIPS_REG_S5, UC_MIPS_REG_S6,
    UC_MIPS_REG_S7, UC_MIPS_REG_FP, UC_MIPS_REG_SP, UC_MIPS_REG_T9,
)

stock.IMAGE = (BASE / 'build/ap.dual-candidate.dge').read_bytes()
IDLE = 0x4463c0
SLEEP = 0x446bfc
PENDING = 0x446c00


class DrawProbe(MenuProbe):
    def hook(self, u, address, size, data):
        if self.stubs.get(address) == 'sdl_draw_pic':
            self.recorded.append({'kind': 'pic', 'x': u.reg_read(UC_MIPS_REG_A0),
                                  'y': u.reg_read(UC_MIPS_REG_A1),
                                  'surface': u.reg_read(UC_MIPS_REG_A2)})
        return super().hook(u, address, size, data)


def arm(sleep, idle=0, now=1000):
    p = stock.Probe(idle)
    assert not tick(p, (now - 100) & 0xffffffff)
    p.word(SLEEP, sleep)
    assert not tick(p, now)
    return p


class CoexistenceTests(unittest.TestCase):
    def test_startup_preserves_original_idle_setting(self):
        p = stock.Probe(2)
        self.assertFalse(tick(p, 1000))
        self.assertEqual(readword(p, IDLE), 2)
        self.assertEqual(readword(p, SLEEP), 0)

    def test_original_idle_still_shuts_down_when_not_playing(self):
        p = stock.Probe(1)
        self.assertTrue(tick(p, 300001, state=2))

    def test_main_menu_contains_both_independent_entries(self):
        p = MenuProbe(selection=5)
        self.assertIn('无输出自动关机时间', [r['text'] for r in p.draw() if r['kind'] == 'label'])
        p.word(p.symbols['c10uicfgmenutype'], 10)
        self.assertIn('睡眠定时关机', [r['text'] for r in p.draw() if r['kind'] == 'label'])

    def test_original_right_key_changes_new_sleep_option_only(self):
        p = MenuProbe(selection=10)
        p.word(IDLE, 2)
        p.release(106)
        self.assertEqual(readword(p, PENDING), 1)
        self.assertEqual(readword(p, IDLE), 2)

    def test_menu_wraps_all_eleven_items(self):
        p = MenuProbe(selection=9)
        p.release(108)
        self.assertEqual(readword(p, p.symbols['c10uicfgmenutype']), 10)
        p.release(108)
        self.assertEqual(readword(p, p.symbols['c10uicfgmenutype']), 0)
        p.release(103)
        self.assertEqual(readword(p, p.symbols['c10uicfgmenutype']), 10)

    def test_original_idle_boundaries_and_disabled_while_playing(self):
        for setting, duration in [(1, 300000), (2, 600000), (3, 1200000)]:
            p = stock.Probe(setting)
            self.assertFalse(tick(p, duration, state=2))
            self.assertTrue(tick(p, duration + 1, state=2))
            self.assertFalse(tick(stock.Probe(setting), 9000000, state=1))
        self.assertFalse(tick(stock.Probe(0), 9000000, state=2))

    def test_activity_resets_only_original_idle_elapsed(self):
        p = stock.Probe(1)
        self.assertFalse(tick(p, 9000000, state=2, last_key=8999000))
        self.assertTrue(tick(p, 9300001, state=2, last_key=9000000))

    def test_sleep_boundaries_while_playing_with_idle_also_enabled(self):
        for option, duration in [(1, 1800000), (2, 3600000), (3, 5400000)]:
            p = arm(option, idle=1)
            self.assertFalse(tick(p, 1000 + duration - 1, last_key=1000 + duration - 1))
            self.assertTrue(tick(p, 1000 + duration, last_key=1000 + duration))
            self.assertEqual(readword(p, SLEEP), 0)
            self.assertEqual(readword(p, IDLE), 1)

    def test_idle_can_expire_before_sleep(self):
        p = arm(2, idle=1)
        self.assertTrue(tick(p, 302001, state=2, last_key=2000))
        self.assertEqual(readword(p, SLEEP), 2)

    def test_sleep_can_expire_while_idle_has_recent_activity(self):
        p = arm(1, idle=1)
        self.assertTrue(tick(p, 1801000, state=2, last_key=1800000))
        self.assertEqual(readword(p, IDLE), 1)

    def test_cancelling_sleep_does_not_disable_idle(self):
        p = arm(1, idle=1)
        p.word(SLEEP, 0)
        self.assertFalse(tick(p, 1801000, state=1))
        self.assertTrue(tick(p, 1801001, state=2, last_key=1501000))

    def test_disabling_idle_does_not_cancel_sleep(self):
        p = arm(1, idle=1)
        p.word(IDLE, 0)
        self.assertFalse(tick(p, 1800999, state=2))
        self.assertTrue(tick(p, 1801000, state=2))

    def test_sleep_pausing_and_keys_do_not_extend_deadline(self):
        p = arm(1)
        self.assertFalse(tick(p, 600000, state=2, last_key=600000))
        self.assertFalse(tick(p, 1200000, state=1, last_key=1200000))
        self.assertTrue(tick(p, 1801000, state=2, last_key=1801000))

    def test_sleep_tick_wrap(self):
        p = arm(1, idle=2, now=0xffff0000)
        self.assertFalse(tick(p, 0xffff0000 + 1799999))
        self.assertTrue(tick(p, 0xffff0000 + 1800000))

    def test_new_sleep_edit_and_save_do_not_change_original_idle_or_other_properties(self):
        p = MenuProbe(selection=10)
        p.word(IDLE, 2)
        p.word(p.symbols['c10syscfgitem'] + 0x14, 2)
        self.assertFalse(tick(p, 0))
        before = bytes(p.u.mem_read(p.symbols['tglobalproperty'], 36))
        p.release(106)
        self.assertEqual(readword(p, PENDING), 1)
        self.assertEqual(readword(p, SLEEP), 0)
        p.release(1)
        self.assertEqual(readword(p, SLEEP), 1)
        self.assertEqual(bytes(p.u.mem_read(p.symbols['tglobalproperty'], 36)), before)
        self.assertFalse(tick(p, 1000))
        self.assertTrue(tick(p, 1801000))

    def test_idle_edit_save_does_not_change_existing_sleep_deadline(self):
        p = MenuProbe(selection=5)
        self.assertFalse(tick(p, 0))
        p.word(SLEEP, 2)
        p.word(PENDING, 2)
        self.assertFalse(tick(p, 1000))
        p.release(106)
        p.release(1)
        self.assertEqual(readword(p, IDLE), 1)
        self.assertEqual(readword(p, SLEEP), 2)
        self.assertFalse(tick(p, 3600999))
        self.assertTrue(tick(p, 3601000))

    def test_menu_reopen_syncs_pending_from_active_and_discards_unsaved_edit(self):
        p = MenuProbe(selection=10)
        self.assertFalse(tick(p, 0))
        p.release(106)
        self.assertEqual(readword(p, PENDING), 1)
        p.word(p.symbols['c10_ui_type'], 0)
        self.assertFalse(tick(p, 1000))
        p.word(p.symbols['c10_ui_type'], 3)
        self.assertFalse(tick(p, 2000))
        self.assertEqual(readword(p, PENDING), 0)

    def test_stock_navigation_discards_unsaved_sleep_edit_before_other_setting_save(self):
        p = MenuProbe(selection=10)
        self.assertFalse(tick(p, 0))
        p.release(106)
        self.assertEqual(readword(p, PENDING), 1)
        p.release(108)  # Original navigation cancels the uncommitted edit.
        self.assertEqual(readword(p, p.symbols['c10uicfgmenutype']), 0)
        self.assertEqual(readword(p, PENDING), 0)
        p.release(1)
        self.assertEqual(readword(p, SLEEP), 0)

    def test_discarding_edit_keeps_already_active_sleep_and_original_deadline(self):
        p = MenuProbe(selection=10)
        self.assertFalse(tick(p, 0))
        p.word(SLEEP, 2)
        p.word(PENDING, 2)
        self.assertFalse(tick(p, 1000))
        p.release(106)
        self.assertEqual(readword(p, PENDING), 3)
        p.release(108)
        self.assertEqual(readword(p, PENDING), 2)
        p.release(1)
        self.assertEqual(readword(p, SLEEP), 2)
        self.assertFalse(tick(p, 3600999))
        self.assertTrue(tick(p, 3601000))

    def test_original_idle_save_path_is_still_called_and_boot_keeps_idle(self):
        p = MenuProbe(selection=5)
        self.assertFalse(tick(p, 0))
        p.release(106)
        p.release(1)
        self.assertEqual(readword(p, IDLE), 1)
        p.release(28)
        self.assertEqual(len([r for r in p.recorded if r['kind'] == 'mock_save']), 1)
        self.assertEqual(readword(p, IDLE), 1)
        boot = stock.Probe(readword(p, IDLE))
        self.assertFalse(tick(boot, 0))
        self.assertEqual(readword(boot, IDLE), 1)
        self.assertEqual(readword(boot, SLEEP), 0)

    def test_sleep_menu_left_and_right_cycle_independently(self):
        p = MenuProbe(selection=10)
        p.word(IDLE, 3)
        for key, values in [(106, [1, 2, 3, 0]), (105, [3, 2, 1, 0])]:
            for value in values:
                p.release(key)
                self.assertEqual(readword(p, PENDING), value)
                self.assertEqual(readword(p, IDLE), 3)

    def test_all_menu_selections_render_and_scroll_inside_original_bounds(self):
        for language in [0, 1, 2]:
            for selection in range(11):
                p = DrawProbe(language=language, selection=selection)
                records = p.draw()
                labels = [r for r in records if r['kind'] == 'label']
                self.assertEqual(len(labels), 8, (language, selection))
                self.assertEqual(sum(r['selected'] for r in labels), 1, (language, selection))
                self.assertTrue(all(40 <= r['y'] < 360 for r in labels))
                table = readword(p, p.symbols['C10UList'])
                thumb = readword(p, table + 16)
                height = readword(p, thumb + 12)
                pic = next(r for r in records if r['kind'] == 'pic' and r['surface'] == thumb)
                self.assertEqual(pic['y'], 43 + (263 - height) * selection // 10)
                if selection == 10:
                    titles = ['睡眠定时关机', '睡眠定時關機', 'Sleep timer']
                    self.assertIn(titles[language], [r['text'] for r in labels])

    def test_original_idle_values_and_new_sleep_values_are_different(self):
        for option, old, new in [(0, 'OFF', 'OFF'), (1, '5min', '30min'),
                                  (2, '10min', '60min'), (3, '20min', '90min')]:
            p = MenuProbe(selection=5, duration=option)
            self.assertIn(old, [r['text'] for r in p.draw() if r['kind'] == 'value'])
            p.word(p.symbols['c10uicfgmenutype'], 10)
            p.word(PENDING, option)
            self.assertIn(new, [r['text'] for r in p.draw() if r['kind'] == 'value'])

    def test_original_ten_setting_key_operations_match_exact_stock(self):
        candidate = stock.IMAGE
        original = (BASE.parent / 'c10-analysis/appfs/local/aplayer/ap.dge').read_bytes()
        try:
            for selection in range(10):
                for key in [105, 106]:
                    stock.IMAGE = original
                    old = MenuProbe(selection=selection)
                    old.release(key)
                    stock.IMAGE = candidate
                    new = MenuProbe(selection=selection)
                    new.release(key)
                    for address, size in [(old.symbols['c10syscfgitem'], 40),
                                          (old.symbols['tglobalproperty'], 36),
                                          (old.symbols['c10_ui_type'], 4)]:
                        self.assertEqual(old.u.mem_read(address, size), new.u.mem_read(address, size),
                                         (selection, key, hex(address)))
        finally:
            stock.IMAGE = candidate

    def test_usb_cancels_sleep_but_keeps_idle_and_original_argument_registers(self):
        p = arm(1, idle=3)
        p.word(PENDING, 2)
        args = [UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3]
        for i, reg in enumerate(args):
            p.u.reg_write(reg, 0x1230 + i)
        p.stopped = None
        p.stops = {0x41b790}
        p.run(0x41b788)
        self.assertEqual(readword(p, IDLE), 3)
        self.assertEqual(readword(p, SLEEP), 0)
        self.assertEqual(readword(p, PENDING), 0)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_S0), 0x4463ac)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_T9), readword(p, stock.GP - 0x7f58))
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_GP), stock.GP)
        for i, reg in enumerate(args):
            self.assertEqual(p.u.reg_read(reg), 0x1230 + i)
        self.assertFalse(tick(p, 9000000))

    def test_timer_bridge_preserves_stack_gp_and_callee_saved_registers(self):
        p = arm(1, idle=1)
        regs = [UC_MIPS_REG_S1, UC_MIPS_REG_S2, UC_MIPS_REG_S4,
                UC_MIPS_REG_S7, UC_MIPS_REG_FP]
        for i, reg in enumerate(regs):
            p.u.reg_write(reg, 0x50 + i)
        sp = p.u.reg_read(UC_MIPS_REG_SP)
        self.assertFalse(tick(p, 1001, last_key=777))
        for i, reg in enumerate(regs):
            self.assertEqual(p.u.reg_read(reg), 0x50 + i)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_S3), 1)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_S5), 777)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_S6), 0x440000)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_GP), stock.GP)
        self.assertEqual(p.u.reg_read(UC_MIPS_REG_SP), sp)

    def test_either_deadline_enters_original_player_close_branch(self):
        for p, now, state in [(arm(1), 1801000, 1), (arm(2, idle=1), 300001, 2)]:
            self.assertTrue(tick(p, now, state=state))
            p.stopped = None
            p.stops = {0x41ba84}
            p.word(0x44446c, 1)
            p.run(0x41ba48)
            self.assertEqual([c['call'] for c in p.calls], ['mplayerclose', 'puts'])
            self.assertEqual(readword(p, 0x44446c), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
