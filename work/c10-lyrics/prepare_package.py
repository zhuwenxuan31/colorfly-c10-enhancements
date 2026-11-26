"""Prepare application-only v74 and a v75 image with the exact v72 payload."""
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import wave

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORK = HERE.parent
SCOPE = WORK / 'c10-prototype'
sys.path[:0] = [str(SCOPE), str(WORK / 'c10-analysis')]
from package import parse, rebuild
from read_ext import ExtReader
from verify_updater_scope import verify

OUT = ROOT / 'outputs/C10_同步歌词_候选_v74'
BASE = ROOT / 'outputs/C10_USB_DAC兼容修复_候选_v72/C10_USB_DAC兼容修复_待实测_v72.bin'
BASE_SHA = 'fbb7f248f1a0f1a1111f990bd4be2a8111a7b82c4cfcd07660fcfb692571035a'
ENTRY = 'local/aplayer/ap.dge'
TOOLS = SCOPE / 'fs-tools/e2fsprogs-1.47.2'
FILES = ('C10_同步歌词_待实测_v74.bin', 'C10_回退v72播放与USB_DAC_v75.bin')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(reader):
    files = {}

    def visit(inode, path):
        _, mode, size = reader.inode(inode)
        if mode & 0o170000 == 0o40000:
            for name, child in reader.entries(inode):
                visit(child, path + '/' + name if path else name)
        else:
            files[path] = (mode, size, sha(reader.contents(inode)))

    visit(2, '')
    return files


def sample():
    folder = OUT / '000_LYRICS_TEST'
    folder.mkdir(exist_ok=True)
    lyrics = '[00:00.00]开场 · C10 同步歌词\n[00:04.00]第二行 · 正在跟随播放\n[00:08.00]第三行 · 暂停可以停在这一句\n[00:12.00]第四行 · 同步测试结束\n'
    (folder / '01_LYRICS_TEST.lrc').write_text(lyrics, encoding='utf8')
    rate = 44100
    audio = bytearray()
    for i in range(rate * 16):
        part = i // (rate * 4)
        j = i % (rate * 4)
        gain = max(0, min(j / 2200, (rate * 2 - j) / 2200, 1))
        value = round(220 * gain * math.sin(2 * math.pi * (400 + 90 * part) * j / rate))
        audio.extend(struct.pack('<hh', value, value))
    with wave.open(str(folder / '01_LYRICS_TEST.wav'), 'wb') as file:
        file.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
        file.writeframes(audio)
    return {path.name: sha(path.read_bytes()) for path in folder.iterdir()}


def main():
    src = BASE.read_bytes()
    assert sha(src) == BASE_SHA
    original = parse(src)
    assert original['version'] == 72
    app_image = original['payloads'][3]
    binary = (HERE / 'build/ap.lyrics.dge').read_bytes()
    patch = json.loads((HERE / 'build/patch.json').read_text())
    assert sha(binary) == patch['after']
    OUT.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(prefix='c10-v74-') as name:
        temp = Path(name)
        image = temp / 'appfs.ext3'
        image.write_bytes(app_image)
        before = inventory(ExtReader(image))
        assert before[ENTRY][2] == patch['before']
        srcfile = temp / 'lyrics.dge'
        srcfile.write_bytes(binary)
        script = temp / 'debugfs.txt'
        script.write_text(f'rm /{ENTRY}\nwrite "{srcfile}" /{ENTRY}\n'
                          f'set_inode_field /{ENTRY} mode 0{before[ENTRY][0]:o}\n')
        edited = subprocess.run([TOOLS/'debugfs/debugfs','-w','-f',script,image],
                                capture_output=True, text=True, check=True)
        (OUT / 'debugfs.log').write_text(edited.stdout + edited.stderr)
        checked = subprocess.run([TOOLS/'e2fsck/e2fsck','-fn',image],capture_output=True,text=True)
        (OUT / 'e2fsck.log').write_text(checked.stdout + checked.stderr)
        checked.check_returncode()
        after = inventory(ExtReader(image))
        assert set(after) == set(before) and len(image.read_bytes()) == len(app_image)
        assert after[ENTRY] == (before[ENTRY][0], len(binary), sha(binary))
        assert {path for path in before if before[path] != after[path]} == {ENTRY}

        packages = []
        for name, version, payload in zip(FILES, (74,75), (image.read_bytes(), app_image)):
            data = rebuild(src, payload, version)
            parts = parse(data)
            assert parts['payloads'][:3] == original['payloads'][:3]
            assert parts['payloads'][3] == payload
            assert parts['burn_offsets'] == original['burn_offsets']
            scope = verify(data)
            (OUT/name).write_bytes(data)
            packages.append({'file': name, 'version': version, 'sha256': sha(data), 'scope': scope})

    record = {'base_sha256': BASE_SHA, 'changed_application_file': ENTRY,
              'other_application_files_preserved': len(before) - 1,
              'app_sha256': sha(binary), 'test_files': sample(), 'packages': packages}
    (OUT / '候选包核验.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
