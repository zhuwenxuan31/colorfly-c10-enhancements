"""Offline C10 container reader/builder. Never opens a block device."""
import struct,zlib

def crc(data):return (zlib.crc32(data,0xffffffff)^0xffffffff)&0xffffffff
def parse(data):
    if len(data)<16:raise ValueError('short container')
    if crc(data[:-4])!=struct.unpack_from('<I',data,len(data)-4)[0]:raise ValueError('container CRC mismatch')
    size,version=struct.unpack_from('<II',data)
    if size>4096 or size<1 or 8+size>len(data)-4:raise ValueError('invalid header length')
    try:
        fields=dict(line.split('=',1) for line in data[8:8+size].decode('ascii').splitlines())
        if fields['Customer']!='colorfly' or int(fields['update_version'])!=version:raise ValueError('wrong customer/version')
        order,total=int(fields['update_order']),int(fields['update_total'])
        arrays={key:[int(x) for x in fields[key].split(',') if x] for key in ['files_length','burn_offset','files_offset']}
    except (UnicodeError,KeyError,ValueError) as ex:raise ValueError('invalid C10 header') from ex
    if any(len(a)!=4 for a in arrays.values()) or not 1<=order<=4 or not 1<=total<=4:raise ValueError('invalid component counts')
    cursor=8+size;payloads=[]
    for start,length,burn in zip(arrays['files_offset'],arrays['files_length'],arrays['burn_offset']):
        if start!=cursor or length<=0 or length>268435456 or burn<0 or burn>0x7fffffff or start+length>len(data)-4:raise ValueError('invalid component bounds')
        payloads.append(data[start:start+length]);cursor+=length
    if cursor!=len(data)-4:raise ValueError('unaccounted container bytes')
    return dict(version=version,order=order,total=total,payloads=payloads,burn_offsets=arrays['burn_offset'],offsets=arrays['files_offset'])

def rebuild(original,application,version):
    before=parse(original)
    if len(application)!=len(before['payloads'][3]):raise ValueError('application filesystem size must stay unchanged')
    if not 0<version<=0xffffffff:raise ValueError('invalid version')
    components=[*before['payloads'][:3],application]
    lengths=[len(c) for c in components];offsets=before['offsets']
    for _ in range(10):
        header=('Customer=colorfly\n'+f'update_version={version}\nupdate_order=4\nupdate_total=1\n'+
                'files_length='+','.join(map(str,lengths))+',\n'+
                'burn_offset='+','.join(map(str,before['burn_offsets']))+',\n'+
                'files_offset='+','.join(map(str,offsets))+',').encode('ascii')
        cursor=8+len(header);new=[]
        for length in lengths:new.append(cursor);cursor+=length
        if offsets==new:break
        offsets=new
    else:raise ValueError('header offsets did not converge')
    body=struct.pack('<II',len(header),version)+header+b''.join(components)
    result=body+struct.pack('<I',crc(body));after=parse(result)
    if after['payloads'][:3]!=before['payloads'][:3] or after['burn_offsets']!=before['burn_offsets']:raise ValueError('non-application component changed')
    return result
