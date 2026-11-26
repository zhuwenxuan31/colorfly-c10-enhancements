"""Execute production packets using actual original MPlayer parser/filter code.
No MPlayer decoder/device process runs. Native libc IO/audio syscalls trapped.
"""
import ctypes,math,json
from pathlib import Path
from native_live_probe import LiveNative
BASE=Path(__file__).resolve().parent
class Config(ctypes.Structure):_fields_=[('enabled',ctypes.c_int),('preset',ctypes.c_int),('gain',ctypes.c_int*10)]
lib=ctypes.CDLL(str(BASE/'build/liblive_model.dylib'))
lib.eq_volume_tenths.argtypes=[ctypes.POINTER(Config)]
lib.eq_live_change.argtypes=[ctypes.POINTER(Config),ctypes.c_int,ctypes.POINTER(Config),ctypes.c_char_p,ctypes.c_size_t]
lib.eq_live_install.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_size_t]
def packet(a,av,b):
 out=ctypes.create_string_buffer(512);n=lib.eq_live_change(ctypes.byref(a),av,ctypes.byref(b),out,512);assert n>=0
 return out.value.decode().splitlines()
def run_lines(p,lines,peaks=None):
 for line in lines:
  if line.strip():
   p.command(line)
   if peaks is not None:peaks.append(p.rms()[1])
results=[]
for rate,fmt,bps,filters in [(44100,9,2,[]),(96000,17,3,['volume=-3:0:0'])]:
 p=LiveNative(filters,rate,fmt,bps)
 out=ctypes.create_string_buffer(512);assert lib.eq_live_install(1,out,512)>0
 run_lines(p,out.value.decode().splitlines())
 graph=p.graph();assert [x['name'] for x in graph].count('volume')==1,graph
 assert [x['name'] for x in graph].count('equalizer')==1,graph
 assert all(x['format']==29 for x in graph if x['name'] in ['equalizer','volume']),graph
 assert [x['name'] for x in graph].index('equalizer')<[x['name'] for x in graph].index('volume'),graph
 assert p.output[-1]=='ANS_pause=no\n',p.output[-10:]
 a=Config(0,0,(ctypes.c_int*10)(*([0]*10)));av=-2000
 records=[]
 for gains in [[0]*10,[-12]*10,[1]+[0]*9,[0,12]+[0]*8,[-4,-4,-3,-2,-1,0,0,-2,-3,-4],[0]*10]:
  b=Config(1,5,(ctypes.c_int*10)(*gains));peaks=[];lines=packet(a,av,b)
  run_lines(p,lines,peaks)
  assert p.current_gains()==tuple(float(x) for x in gains)
  ratio,peak=p.rms();assert peak<.99,(gains,peak,peaks)
  assert all(x<.99 for x in peaks),(gains,peaks)
  records.append({'gains':gains,'ratio':ratio,'peak':peak,'intermediate_peaks':peaks})
  a=b;av=lib.eq_volume_tenths(ctypes.byref(b))
 p.word(p.ctx+4,2);before=p.readword(p.ctx+4)
 p.command('pausing_keep_force get_property pause');assert p.output[-1]=='ANS_pause=yes\n'
 run_lines(p,packet(a,av,Config(0,0,(ctypes.c_int*10)(*([0]*10)))))
 assert p.readword(p.ctx+4)==before
 assert p.hardware_calls==[]
 results.append({'rate':rate,'format':fmt,'bps':bps,'initial_filters':filters,'graph':graph,'transitions':records,'hardware_calls':p.hardware_calls,'paused_state_unchanged':True})
 print('PASS native matrix',rate,bps,flush=True)
(BASE/'native-live-matrix-results.json').write_text(json.dumps(results,indent=2)+'\n')
