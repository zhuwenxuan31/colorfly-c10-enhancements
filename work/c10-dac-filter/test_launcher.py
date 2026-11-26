import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class LauncherTest(unittest.TestCase):
    def test_opt_in_and_use_only_real_playback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for directory in ('bin', 'sbin', 'tmp', 'mnt/memory', 'usr/local/aplayer', 'proc/11/fd'):
                (root/directory).mkdir(parents=True, exist_ok=True)
            helper = root/'bin/busybox'
            helper.write_text('''#!/bin/sh
case "$1" in
insmod|rmmod) printf '%s: applet not found\n' "$1" >&2; exit 127 ;;
dmesg) echo 'noise'; echo 'C10DAC_PROBE1 filter=fast id=71 control=40 value=b0' ;;
sleep) exit 0 ;;
*) applet=$1; shift; exec "$applet" "$@" ;;
esac
''')
            helper.chmod(0o755)
            for tool in ('insmod', 'rmmod'):
                loader = root/'sbin'/tool
                loader.write_text('#!/bin/sh\nprintf "%s %s\\n" "${0##*/}" "$*" >> "$C10_DAC_ROOT/calls"\n')
                loader.chmod(0o755)
            factory = root/'usr/local/aplayer/ap.factory'
            factory.write_text('#!/bin/sh\nprintf "%s\\n" "$*"\n')
            factory.chmod(0o755)
            env = {**os.environ, 'C10_DAC_ROOT': tmp}
            def launch():
                proc = subprocess.run(['/bin/sh', HERE/'launcher.sh', 'stock-argument'],
                                      env=env, capture_output=True, text=True, check=True)
                self.assertEqual(proc.stdout, 'stock-argument\n')
            launch()
            self.assertFalse((root/'calls').exists())
            (root/'mnt/memory/.c10-dac-probe').touch()
            (root/'proc/11/stat').write_text('11 (mplayer) S 1\n')
            (root/'proc/11/fd/4').symlink_to('/dev/dsp')
            launch()
            launch()
            report = root/'mnt/memory/C10_DAC_PROBE.log'
            deadline = time.monotonic() + 4
            while not report.is_file() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertEqual((root/'calls').read_text().splitlines(), [
                f'insmod {root}/usr/local/modules/c10_dac_probe.ko', 'rmmod c10_dac_probe'])
            log = report.read_text()
            self.assertIn('filter=fast id=71 control=40 value=b0', log)
            self.assertNotIn('noise', log)


if __name__ == '__main__':
    unittest.main()
