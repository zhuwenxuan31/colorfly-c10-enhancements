from pathlib import Path
import struct, json, hashlib, sys

class ExtReader:
    def __init__(self, image):
        self.data = Path(image).read_bytes()
        self.sb = self.data[1024:2048]
        assert self.sb[56:58] == b'\x53\xef'
        self.bs = 1024 << self.u32(self.sb, 24)
        self.ipg = self.u32(self.sb, 40)
        self.isize = struct.unpack_from('<H', self.sb, 88)[0] or 128
        self.gdt = (self.u32(self.sb, 20) + 1) * self.bs
    @staticmethod
    def u32(b, o): return struct.unpack_from('<I', b, o)[0]
    def block(self, n):
        if n == 0: return bytes(self.bs)
        start = n * self.bs
        assert start + self.bs <= len(self.data), ('block outside image', n)
        return self.data[start:start+self.bs]
    def inode(self, n):
        group, index = divmod(n-1, self.ipg)
        table = self.u32(self.data, self.gdt + group*32 + 8)
        start = table*self.bs + index*self.isize
        i = self.data[start:start+self.isize]
        mode = struct.unpack_from('<H', i)[0]
        size = self.u32(i, 4)
        if mode & 0xf000 == 0x8000: size |= self.u32(i, 108) << 32
        return i, mode, size
    def pointers(self, n, depth):
        if depth == 0:
            yield n
        else:
            for p in struct.unpack('<'+'I'*(self.bs//4), self.block(n)):
                yield from self.pointers(p, depth-1)
    def contents(self, n):
        i, mode, size = self.inode(n)
        if mode & 0xf000 == 0xa000 and size <= 60: return i[40:40+size]
        assert not self.u32(i, 32) & 0x80000, 'extents unsupported'
        assert size < 300_000_000, 'unexpected file size'
        out = bytearray()
        ptrs = struct.unpack_from('<15I', i, 40)
        for k, p in enumerate(ptrs):
            if len(out) >= size: break
            for block in self.pointers(p, 0 if k < 12 else k-11):
                if len(out) >= size: break
                out.extend(self.block(block))
        assert len(out) >= size
        return bytes(out[:size])
    def entries(self, n):
        data = self.contents(n); offset = 0
        while offset+8 <= len(data):
            ino, length, namelen, typ = struct.unpack_from('<IHBB', data, offset)
            assert length >= 8 and offset+length <= len(data)
            if ino:
                raw = data[offset+8:offset+8+namelen]
                if raw not in (b'.', b'..'):
                    name = raw.decode('utf-8', errors='surrogateescape')
                    assert '/' not in name and '\x00' not in name
                    yield name, ino
            offset += length
    def extract(self, dest):
        dest = Path(dest); dest.mkdir(parents=True, exist_ok=True)
        manifest = []
        def walk(ino, rel, parents):
            assert ino not in parents, 'directory loop'
            _, mode, size = self.inode(ino)
            kind = mode & 0xf000
            record = dict(path=str(rel), inode=ino, mode=oct(mode), size=size)
            if kind == 0x4000:
                record['type']='directory'; (dest/rel).mkdir(exist_ok=True)
                manifest.append(record)
                for name, child in self.entries(ino): walk(child, rel/name, parents | {ino})
            elif kind == 0x8000:
                record['type']='file'; b=self.contents(ino)
                (dest/rel).write_bytes(b); record['sha256']=hashlib.sha256(b).hexdigest()
                manifest.append(record)
            elif kind == 0xa000:
                record.update(type='symlink', target=self.contents(ino).decode('utf8', errors='replace'))
                manifest.append(record)
            else:
                record['type']='special'; manifest.append(record)
        walk(2, Path('.'), set())
        return manifest

if __name__ == '__main__':
    r=ExtReader(sys.argv[1]); manifest=r.extract(sys.argv[2])
    Path(sys.argv[2]+'.manifest.json').write_text(json.dumps(manifest, ensure_ascii=True, indent=2))
    print(json.dumps(dict(block_size=r.bs, inode_size=r.isize, entries=len(manifest),
                         regular_files=sum(x['type']=='file' for x in manifest),
                         symlinks=sum(x['type']=='symlink' for x in manifest))))
