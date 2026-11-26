"""Re-run v60 timer regressions against EQ ELF; extend expected menu to12."""
from pathlib import Path
import sys
import unittest
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'c10-dual-timer'))
import test_dual as old
from test_mips_patch import readword,tick
old.stock.IMAGE=(BASE/'build/ap.eq-candidate.dge').read_bytes()

class EQTimerRegression(old.CoexistenceTests):
    def test_menu_wraps_all_eleven_items(self):
        p=old.MenuProbe(selection=9)
        for expected in [10,11,0]:
            p.release(108);self.assertEqual(readword(p,0x444b5c),expected)
        p.release(103);self.assertEqual(readword(p,0x444b5c),11)
    def test_stock_navigation_discards_unsaved_sleep_edit_before_other_setting_save(self):
        p=old.MenuProbe(selection=10);self.assertFalse(tick(p,0));p.release(106)
        self.assertEqual(readword(p,old.PENDING),1)
        p.release(108);self.assertEqual(readword(p,0x444b5c),11)
        self.assertEqual(readword(p,old.PENDING),0)
        p.release(1);self.assertEqual(readword(p,old.SLEEP),0)
    def test_all_menu_selections_render_and_scroll_inside_original_bounds(self):
        for language in range(3):
            for selection in range(12):
                p=old.DrawProbe(language=language,selection=selection)
                records=p.draw();labels=[r for r in records if r['kind']=='label']
                self.assertTrue(7<=len(labels)<=8,(language,selection,len(labels)))
                self.assertEqual(sum(r['selected'] for r in labels),1,(language,selection))
                self.assertTrue(all(40<=r['y']<360 for r in labels))
                table=readword(p,p.symbols['C10UList']);thumb=readword(p,table+16)
                height=readword(p,thumb+12)
                pic=next(r for r in records if r['kind']=='pic' and r['surface']==thumb)
                self.assertEqual(pic['y'],43+(263-height)*selection//11)
                if selection==11:
                    self.assertIn(['均衡器 EQ','均衡器 EQ','Equalizer EQ'][language],
                                  [r['text'] for r in labels])

if __name__=='__main__':unittest.main(verbosity=2)
