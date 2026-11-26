"""Create an app-only probe package and exact v80 application rollback."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent/'c10-lyrics'))
from prepare_package import ENTRY, ExtReader, TOOLS, inventory, parse, rebuild, sha, verify

OUTPUT = ROOT/'outputs/C10_CS4398只读诊断_v84'
BASE = ROOT/'outputs/C10_目录歌曲删除_候选_v80/C10_目录歌曲删除_待实测_v80.bin'
BASE_SHA = '1855367680e53e3cfbe77de2fd08c92ffb199d69cec084777e2cb781885d0fa7'
APP = 'local/aplayer/ap.factory'
MODULE = 'local/modules/c10_dac_probe.ko'


def main(compare=False):
    out=ROOT/'outputs/C10_CS4398快慢滤波试听_v86' if compare else OUTPUT
    baseline = BASE.read_bytes()
    assert sha(baseline) == BASE_SHA
    source = parse(baseline)
    assert source['version'] == 80
    original = source['payloads'][3]
    probe = HERE/'build'/('c10_dac_trial.ko' if compare else 'c10_dac_probe.ko')
    launcher = HERE/('trial_launcher.sh' if compare else 'launcher.sh')
    with tempfile.TemporaryDirectory(prefix='c10-dac-package-') as temp:
        folder = Path(temp)
        image = folder/'application.ext3'
        image.write_bytes(original)
        original_fs = ExtReader(image)
        before = inventory(original_fs)

        def extract(path):
            inode = 2
            for part in path.split('/'):
                inode = dict(original_fs.entries(inode))[part]
            return original_fs.contents(inode)

        original_app = folder/'ap.factory'
        original_app.write_bytes(extract(ENTRY))
        assert sha(original_app.read_bytes()) == before[ENTRY][2]
        insert = {APP: (original_app, before[ENTRY][0]),
                  ENTRY: (launcher, before[ENTRY][0]), f'local/modules/{probe.name}': (probe, 0o100644)}
        commands = [f'rm /{ENTRY}']
        for target, (local, mode) in insert.items():
            commands += [f'write "{local}" /{target}', f'set_inode_field /{target} mode 0{mode:o}']
        edit = folder/'fs-edit.txt'
        edit.write_text('\n'.join(commands)+'\n')
        subprocess.run([TOOLS/'debugfs/debugfs', '-w', '-f', edit, image], check=True)
        subprocess.run([TOOLS/'e2fsck/e2fsck', '-fn', image], check=True)
        after = inventory(ExtReader(image))
        assert {k: v for k,v in after.items() if k not in insert} == {k: v for k,v in before.items() if k != ENTRY}
        for target, (local, mode) in insert.items():
            data = local.read_bytes()
            assert after[target] == (mode, len(data), sha(data))
        assert after[APP] == before[ENTRY]
        candidate = image.read_bytes()
    assert len(candidate) == len(original)
    out.mkdir(exist_ok=True)
    results=[]
    versions = ((86,candidate,'C10_CS4398快慢滤波试听_待实测_v86.bin'), (87,original,'C10_回退v80_v87.bin')) if compare else (
        (84,candidate,'C10_CS4398只读诊断_待实测_v84.bin'), (85,original,'C10_回退v80_v85.bin'))
    for version, payload, name in versions:
        data = rebuild(baseline, payload, version)
        checked = parse(data)
        assert checked['version']==version
        assert checked['burn_offsets']==source['burn_offsets']
        assert checked['payloads'][:3]==source['payloads'][:3]
        assert checked['payloads'][3]==payload
        record={'file':name,'version':version,'sha256':sha(data),'scope':verify(data)}
        (out/name).write_bytes(data)
        results.append(record)
    (out/'候选包核验.json').write_text(json.dumps({'base':BASE_SHA,'module':sha(probe.read_bytes()),
          'factory_app':before[ENTRY][2],'packages':results}, ensure_ascii=False, indent=2)+'\n')
    for record in results:
        print(record['sha256'], record['file'])


if __name__ == '__main__':
    assert sys.argv[1:] in ([], ['--compare'])
    main(compare='--compare' in sys.argv)
