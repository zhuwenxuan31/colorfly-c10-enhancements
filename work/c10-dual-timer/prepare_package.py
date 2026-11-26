"""Build and verify local candidate/recovery containers. Never access USB."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import zipfile

BASE = Path(__file__).resolve().parent
PROTO = BASE.parent / 'c10-prototype'
sys.path.insert(0, str(PROTO))
from package import parse, rebuild
from read_ext import ExtReader
from verify_updater_scope import verify

OUT = BASE.parents[1] / 'outputs/C10_双关机_候选_v60'
ZIP = Path('inputs/20160721_C10固件_update.zip')
STOCK_SHA = '7d5f35b9c35ff02aaf6d1a12eb6064af6814395d6b3da76ede8889c82a9b94fc'


def sha(b):
    return hashlib.sha256(b).hexdigest()


def inventory(r):
    records = {}

    def walk(inode, path):
        raw, mode, size = r.inode(inode)
        kind = mode & 0xf000
        if kind == 0x4000:
            for name, child in r.entries(inode):
                walk(child, path + '/' + name if path else name)
        else:
            records[path] = {'inode': inode, 'mode': mode, 'size': size,
                             'sha256': sha(r.contents(inode)), 'inode_hex': raw.hex()}
    walk(2, '')
    return records


def main():
    assert sha(ZIP.read_bytes()) == '1e922ddbded508311f11fa5380cb2c2dae5e63a0241eb59587ef05978f71edb9'
    with zipfile.ZipFile(ZIP) as z:
        original = z.read('c10_update.bin')
    source = parse(original)
    candidate = (BASE / 'build/ap.dual-candidate.dge').read_bytes()
    manifest = json.loads((BASE / 'build/patch-manifest.json').read_text())
    assert sha(candidate) == manifest['candidate_sha256']
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='c10-sleep-offline-') as temporary:
        path = Path(temporary) / 'appfs.ext3'
        path.write_bytes(source['payloads'][3])
        reader = ExtReader(path)
        before = inventory(reader)
        appname = 'local/aplayer/ap.dge'
        inode = before[appname]['inode']
        assert before[appname]['sha256'] == STOCK_SHA
        assert before[appname]['size'] == len(candidate)
        # Preserve every inode/directory byte. Replace only the existing file's
        # allocated data bytes, using its verified ext3 block map.
        image = bytearray(reader.data)
        raw, _, _ = reader.inode(inode)
        cursor = 0
        touched = []
        for index, block in enumerate(struct.unpack_from('<15I', raw, 40)):
            if cursor == len(candidate):
                break
            for data_block in reader.pointers(block, 0 if index < 12 else index - 11):
                if cursor == len(candidate):
                    break
                assert data_block != 0, 'Unexpected sparse original app'
                size = min(reader.bs, len(candidate) - cursor)
                offset = data_block * reader.bs
                assert reader.data[offset:offset + size] == reader.contents(inode)[cursor:cursor + size]
                piece = candidate[cursor:cursor + size]
                if image[offset:offset + size] != piece:
                    touched.append({'offset': offset, 'size': size})
                image[offset:offset + size] = piece
                cursor += size
        assert cursor == len(candidate)
        path.write_bytes(image)
        after_reader = ExtReader(path)
        after = inventory(after_reader)
        assert set(before) == set(after)
        changed = [p for p in before if before[p] != after[p]]
        assert changed == [appname]
        assert before[appname]['inode_hex'] == after[appname]['inode_hex']
        assert after_reader.contents(inode) == candidate
        check = subprocess.run([str(PROTO / 'fs-tools/e2fsprogs-1.47.2/e2fsck/e2fsck'),
                                '-fn', str(path)], text=True, capture_output=True)
        (OUT / 'e2fsck.log').write_text(check.stdout + check.stderr)
        check.check_returncode()
        packages = []
        for name, appfs, version in [
            ('C10_闲置与睡眠关机_待实测_v60.bin', bytes(image), 60),
            ('C10_原厂内容回退_v61.bin', source['payloads'][3], 61),
        ]:
            binary = rebuild(original, appfs, version)
            parsed = parse(binary)
            assert parsed['payloads'][:3] == source['payloads'][:3]
            assert parsed['burn_offsets'] == source['burn_offsets']
            dispatcher = verify(binary)
            (OUT / name).write_bytes(binary)
            packages.append({'name': name, 'sha256': sha(binary), 'version': version,
                             'length': len(binary), 'order': parsed['order'],
                             'total': parsed['total'], 'dispatcher': dispatcher})
        report = {'status': 'local firmware candidates only; NOT installed or staged to USB',
                  'changed_files': changed, 'preserved_files': len(before) - 1,
                  'all_inodes_and_other_file_contents_unchanged': True,
                  'modified_app_data_blocks': touched,
                  'candidate_app_sha256': sha(candidate), 'packages': packages,
                  'physical_poweroff_validated': False}
        (OUT / '候选包核验.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        (OUT / '补丁明细.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
