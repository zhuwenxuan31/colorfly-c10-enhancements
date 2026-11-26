"""Build a C10 application-only candidate and a matching v74 rollback."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / 'c10-lyrics'))
from prepare_package import ENTRY, ExtReader, TOOLS, inventory, parse, rebuild, sha, verify

BASE = ROOT / 'outputs/C10_同步歌词_候选_v74/C10_同步歌词_待实测_v74.bin'
BASE_SHA = '8a51870e4eeec772816fb5a81b059a4d9de251b1478db76b28b5404426c0a941'
OUT = ROOT / 'outputs/C10_目录歌曲删除_候选_v80'


def main():
    stock = BASE.read_bytes()
    assert sha(stock) == BASE_SHA
    package = parse(stock)
    assert package['version'] == 74
    original = package['payloads'][3]
    patch = json.loads((HERE / 'build/patch.json').read_text())
    app = (HERE / 'build/ap.delete.dge').read_bytes()
    assert sha(app) == patch['after']
    with tempfile.TemporaryDirectory(prefix='c10-v80-') as tmp:
        folder = Path(tmp)
        image = folder / 'appfs.ext3'
        image.write_bytes(original)
        before = inventory(ExtReader(image))
        assert before[ENTRY][2] == patch['before']
        program = folder / 'ap.dge'
        program.write_bytes(app)
        operations = folder / 'debugfs.txt'
        operations.write_text(f'rm /{ENTRY}\nwrite "{program}" /{ENTRY}\n'
                              f'set_inode_field /{ENTRY} mode 0{before[ENTRY][0]:o}\n')
        subprocess.run([TOOLS / 'debugfs/debugfs', '-w', '-f', operations, image], check=True)
        subprocess.run([TOOLS / 'e2fsck/e2fsck', '-fn', image], check=True)
        after = inventory(ExtReader(image))
        assert set(before) == set(after)
        assert {path for path in before if before[path] != after[path]} == {ENTRY}
        assert after[ENTRY] == (before[ENTRY][0], len(app), sha(app))
        candidate = image.read_bytes()
    assert len(candidate) == len(original)

    OUT.mkdir(exist_ok=True)
    result = []
    for number, name, payload in [(80, 'C10_目录歌曲删除_待实测_v80.bin', candidate),
                                  (81, 'C10_回退v74_v81.bin', original)]:
        data = rebuild(stock, payload, number)
        checked = parse(data)
        assert checked['version'] == number
        assert checked['burn_offsets'] == package['burn_offsets']
        assert checked['payloads'][:3] == package['payloads'][:3]
        assert checked['payloads'][3] == payload
        scope = verify(data)
        (OUT / name).write_bytes(data)
        result.append({'file': name, 'version': number, 'sha256': sha(data), 'scope': scope})
    report = {'base_sha256': BASE_SHA, 'changed_application_file': ENTRY,
              'other_application_files_preserved': len(before) - 1, 'packages': result}
    (OUT / '候选包核验.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    for item in result:
        print(item['sha256'], item['file'])


if __name__ == '__main__':
    main()
