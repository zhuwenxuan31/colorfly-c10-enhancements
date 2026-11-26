import unittest,struct
from pathlib import Path
BASE=Path(__file__).resolve().parent
def descriptors(data):
 result=[];o=0
 while o<len(data):
  n=data[o];assert n>=2 and o+n<=len(data);result.append(data[o:o+n]);o+=n
 assert o==len(data);return result
class Descriptors(unittest.TestCase):
 def check(self,hs):
  data=(BASE/'build'/('hs.bin' if hs else 'fs.bin')).read_bytes();d=descriptors(data)
  self.assertEqual(struct.unpack_from('<H',data,2)[0],len(data));self.assertEqual(data[4],2)
  h=next(x for x in d if x[1:3]==b'\x24\x01')
  self.assertEqual(h[0],9);self.assertEqual(h[7:],bytes([1,1]))
  ac=[]
  for x in d[2:]:
   if x[1]==4:break
   ac.append(x)
  self.assertEqual(struct.unpack_from('<H',h,5)[0],sum(map(len,ac)))
  alts=[x for x in d if x[1]==4 and x[2]==1];self.assertEqual([x[4] for x in alts],[0,2])
  endpoints=[x for x in d if x[1]==5];self.assertEqual(len(endpoints),2)
  out,feedback=endpoints
  self.assertEqual(out[3],5);self.assertEqual(out[6],4 if hs else 1);self.assertEqual(out[8],feedback[2])
  self.assertEqual(feedback[3],0x11);self.assertTrue(feedback[2]&0x80);self.assertEqual(struct.unpack_from('<H',feedback,4)[0],4 if hs else 3)
  fmt=next(x for x in d if len(x)==11 and x[1:4]==b'\x24\x02\x01');self.assertEqual(fmt[4:8],bytes([2,2,16,1]));self.assertEqual(int.from_bytes(fmt[8:11],'little'),48000)
  ids={x[3] for x in ac if x[2] in [2,3]};ot=next(x for x in ac if x[2]==3);self.assertIn(ot[7],ids)
 def test_high_speed(self):self.check(True)
 def test_full_speed(self):self.check(False)
if __name__=='__main__':unittest.main(verbosity=2)
