"""Actual original libaf matrix and absolute-level checks; no hardware calls."""
from pathlib import Path
import json
import math
from probe_filter_chain import Pipeline

records = []


def energy(samples):
    return sum(float(s) * s for s in samples)


for rate, fmt, bps in [(44100,9,2),(48000,9,2),(96000,9,2),(44100,17,3),(96000,17,3)]:
    print(f'checking flat pipeline {rate}Hz/{bps*8}bit', flush=True)
    p = Pipeline(['equalizer=0:0:0:0:0:0:0:0:0:0','volume=0:0:0'], rate, fmt, bps)
    assert p.initialize() == 0
    maximum = (1 << (bps*8-1)) - 1
    samples = [value for i in range(128) for value in [int(maximum*.75*math.sin(i*.2)),0]]
    output_format, audio = p.process_pcm(samples)
    assert len(audio) == len(samples)
    delta = max(abs(a-b) for a,b in zip(audio,samples))
    assert delta <= 2, (rate,fmt,bps,delta)
    assert not any(audio[1::2])
    graph = p.graph()
    assert next(x for x in graph if x['name']=='volume')['format'] == 29
    records.append({'rate':rate,'format':fmt,'bps':bps,'flat_max_sample_error':delta,'graph':graph})

for gain, volume in [(1,'10.7'),(6,'-4.6'),(12,'-15.9')]:
    print(f'checking absolute gain and no premature clipping: +{gain}dB', flush=True)
    values=[0]*10;values[5]=gain
    p=Pipeline(['equalizer='+':'.join(map(str,values)),'volume='+volume+':0:0'])
    assert p.initialize()==0
    ratios=[]
    peaks=[]
    for amplitude in [300,29000]:
        samples=[value for i in range(1024) for value in [int(amplitude*math.sin(2*math.pi*1000*i/44100))]*2]
        _,audio=p.process_s16(samples)
        ratio=math.sqrt(energy(audio[-512:])/energy(samples[-512:]))
        ratios.append(ratio);peaks.append(max(map(abs,audio)))
    assert .66 < ratios[1] < .75, (gain,ratios,peaks)
    assert abs(ratios[0]-ratios[1]) < .025, (gain,ratios)
    assert peaks[1] < 30000
    records.append({'single_positive_band_db':gain,'compensation_volume_db':volume,
                    'absolute_ratios_low_and_high':ratios,'max_abs_samples':peaks})

out=Path(__file__).resolve().parent/'pipeline-results.json'
out.write_text(json.dumps({'original_libaf_matrix':records,
 'limits':'allocation/memory/log/sscanf mocked; no on-device throughput, full file decode or physical DAC validation; flat tolerance is not a bit-perfect claim'},indent=2)+'\n')
print('PASS: five PCM/rate cases and three absolute level/high-amplitude cases',flush=True)
