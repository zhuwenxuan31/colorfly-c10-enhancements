"""Original registered af* CLI string-list parser: append rather than replace."""
import json
import struct
from probe_filter_chain import Pipeline

p = Pipeline([])
initial = 0x10006000
old = 0x10006100
name = 0x10006200
value = 0x10006300
destination = 0x10006400
p.u.mem_write(old, b'dummy\0')
p.u.mem_write(initial, struct.pack('<II', old, 0))
p.allocations[initial] = 8
p.word(destination, initial)
p.u.mem_write(name, b'af-add\0')
p.u.mem_write(value, b'equalizer=0:0:0:0:0:1:0:0:0:0,volume=10.7:0:0\0')
p.word(0x7ffef000 + 16, 0)
result = p.call(0x4330c0, 0xfd3e28, name, value, destination)
assert result > 0, result
array = p.readword(destination)
filters = []
for i in range(12):
    pointer = p.readword(array + i * 4)
    if not pointer:
        break
    filters.append(bytes(p.u.mem_read(pointer, 256)).split(b'\0', 1)[0].decode())
assert filters == ['dummy', 'equalizer=0:0:0:0:0:1:0:0:0:0', 'volume=10.7:0:0'], filters
print(json.dumps({'registered_option': 'af*', 'option_name': 'af-add', 'parse_result': result,
                  'resulting_filters': filters, 'existing_filter_preserved': True,
                  'limits': 'original registered option type parser; not complete MPlayer process startup or hardware'}, indent=2))
