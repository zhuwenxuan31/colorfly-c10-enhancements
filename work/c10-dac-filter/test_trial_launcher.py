import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class TrialLauncherTest(unittest.TestCase):
    def test_comparison_only_runs_on_test_audio_and_switches_back(self):
        for expected in (False, True):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                for part in ('bin', 'sbin', 'tmp', 'mnt/memory/000_DAC_AB', 'proc/11/fd', 'usr/local/aplayer'):
                    (root/part).mkdir(parents=True)
                media=root/'mnt/memory'
                (media/'.c10-dac-ab').touch()
                (root/'proc/11/stat').write_text('11 (mplayer) S 1\n')
                (root/'proc/11/fd/4').symlink_to('/dev/dsp')
                audio=media/('000_DAC_AB/DAC_AB.wav' if expected else 'music.flac')
                (root/'proc/11/cmdline').write_bytes(b'mplayer\0-slave\0'+bytes(audio)+b'\0')
                for name, data in {
                    'bin/busybox': '''case "$1" in
dmesg) echo 'C10DAC_AB1 active=slow before=b0 after=b4'; echo 'C10DAC_AB1 restored=fast value=b0';;
sleep) printf '%s\\n' "$2" >> "$C10_DAC_ROOT/timing";;
*) applet=$1; shift; exec "$applet" "$@";;
esac
''',
                    'sbin/insmod': 'echo "slow $(wc -l < "$C10_DAC_ROOT/timing" | tr -d " ")" >> "$C10_DAC_ROOT/calls"\n',
                    'sbin/rmmod': 'echo "fast $(wc -l < "$C10_DAC_ROOT/timing" | tr -d " ")" >> "$C10_DAC_ROOT/calls"\n',
                    'usr/local/aplayer/ap.factory': 'echo factory\n',
                }.items():
                    path=root/name
                    path.write_text('#!/bin/sh\n'+data)
                    path.chmod(0o755)
                launched=subprocess.run(['/bin/sh', HERE/'trial_launcher.sh'], check=True, capture_output=True,
                                        text=True, env={**os.environ,'C10_DAC_ROOT':temp})
                self.assertEqual(launched.stdout,'factory\n')
                log=media/'C10_DAC_AB.log'
                deadline=time.monotonic()+8
                while not log.is_file() and time.monotonic()<deadline:
                    time.sleep(.02)
                if expected:
                    self.assertEqual((root/'calls').read_text(),'slow 20\nfast 40\n')
                    self.assertIn('restored=fast',log.read_text())
                else:
                    self.assertFalse((root/'calls').exists())
                    self.assertIn('no-test-playback',log.read_text())


if __name__=='__main__':
    unittest.main()
