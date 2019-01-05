"""
Usage: recon1.py <start> <stop>

"""


from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from docopt import docopt
import cv2
import json
import sys
import numpy as np
import shutil
import subprocess
from tqdm import tqdm
from pathlib import Path

cluster_size = 256*512

commands = docopt(__doc__)
# print(commands)
# sys.exit(1)


def save_used(used, filename='used.json'):
    """Save all information used to reconstruct movie"""
    data = {'image': '/sdimage-p1.img', 'start': start,
            'header2': header2, 'stop': stop, 'used': [int(x) for x in used]}
    with open(filename, 'w') as f:
        json.dump(data, f)


# tahoe video
# start = 540443
# stop = 540748+2

start = int(commands['<start>'])
stop = int(commands['<stop>'])

with open('/sdimage-p1.img', 'rb') as f:
    f.seek(cluster_size*start)
    mybytes = f.read((stop-start)*cluster_size)

header = b'\x00\x00\x00\x14\x66\x74\x79\x70\x6d\x70\x34\x31\x20\x13\x10\x18'
zero_cluster = b'\x00'*cluster_size

# find headers
header1 = 0
assert mybytes[:len(header)] == header, 'Wrong first header'

header2 = mybytes.find(header, cluster_size) // cluster_size
# should be at beginning of cluster
assert mybytes[header2*cluster_size:header2*cluster_size+len(header)] == header, 'Wrong second header'

print(f'header positions:     {header1} {header2}')

# get mdat information
mdat1_length = int.from_bytes(mybytes[20:24], byteorder='big')
mdat2_length = int.from_bytes(mybytes[header2*cluster_size+20:header2*cluster_size+24], byteorder='big')

# how many clusters is mdat long
mdat1_cluster_length = (mdat1_length+20) // cluster_size
mdat2_cluster_length = (mdat2_length+20) // cluster_size

print('mdat cluster lengths:', mdat1_cluster_length, mdat2_cluster_length)

# find moov+mvhd positions that fits with mdat
subsections = [b'mvhd', b'udta', b'iods', b'trak', b'trak', b'trak', b'trak', b'trak']


def find_moov(mdat_length, ignore=None):
    offset = (mdat_length + 20 + 4) % cluster_size
    if offset >= cluster_size - 4:
        print('Error: moov at end of cluster')
        sys.exit(1)
    moov = []
    for i in range(stop-start):
        if mybytes[i*cluster_size+offset:i*cluster_size+4+offset] == b'moov':
            if not moov:
                moov.append(i)
                break
    assert len(moov) == 1, 'Could not find a moov'
    offset = (mdat_length + 20) % cluster_size
    moov_offset = offset
    moov_length = int.from_bytes(mybytes[offset+i*cluster_size:offset+4+i*cluster_size], byteorder='big')

    if offset + moov_length > cluster_size:
        #print('need to look at subsections')
        pos = (offset+i*cluster_size+12) % cluster_size
        cluster = i
        for sec in subsections:
            #print(f'looking for {sec} at {pos} at cluster {cluster}, stop at {stop}')
            while mybytes[cluster*cluster_size+pos:cluster*cluster_size+4+pos] != sec:
                cluster += 1
                if cluster in ignore:
                    continue
                if cluster > stop:
                    print('reached end')
                    break
            moov.append(cluster)
            tmp = b''
            for m in moov:
                tmp += mybytes[m*cluster_size:(m+1)*cluster_size]
            sec_length = int.from_bytes(tmp[pos-4-cluster_size:pos-cluster_size], byteorder='big')
            assert tmp[pos-cluster_size:pos+4-cluster_size] == sec, 'incorrect section'
            pos = (pos+sec_length) % cluster_size
            # print(f'found sec with length {sec_length}, next pos {pos}')
        # ensure all of moov in tmp
        assert moov_offset+moov_length <= len(tmp), 'Very end of moov missing'

    moov = sorted(list(set(moov)))
    return moov, moov_length


moov1, moov1_length = find_moov(mdat1_length, [])
print('moov1:', moov1)
print('moov1 length', moov1_length)
moov2, moov2_length = find_moov(mdat2_length, ignore=moov1)
print('moov2:', moov2)
print('moov2 length', moov2_length)

# create array to mark which blocks have been used
# and write initial video out

used = np.array([0] * (len(mybytes)//cluster_size+20))

with open('reconstructed01.MP4', 'wb') as out1:
    out1.write(mybytes[:header2*cluster_size])
    used[:header2] = -3
    used[0] = -1
    for i in range(mdat1_cluster_length-header2):
        out1.write(zero_cluster)
    for m in moov1:
        out1.write(mybytes[m*cluster_size:(m+1)*cluster_size])
        used[m] = -2

with open('reconstructed01.LRV', 'wb') as out2:
    out2.write(mybytes[header2*cluster_size:(header2+4)*cluster_size])
    used[header2:header2+1] = 1
    used[header2+1:header2+3] = 3
    # this is just a guess
    #used[header2+4] = -3
    for i in range(mdat2_cluster_length-4):
        out2.write(zero_cluster)
    for m in moov2:
        out2.write(mybytes[m*cluster_size:(m+1)*cluster_size])
        used[m] = 2

# read video index
out = subprocess.run(['/home/arun/src/Prog/Bento4/cmakebuild/mp4iframeindex',
                      'reconstructed01.LRV'], stdout=subprocess.PIPE)
idx = json.loads(out.stdout)

LRV_old = Path('reconstructed01.LRV_orig')
LRV = Path('reconstructed01.LRV')
shutil.copyfile(LRV, LRV_old)

out = Counter(used)

save_used(used, 'used-orig.json')

# reconstr LRV
tmp = mybytes[header2*cluster_size:(header2+1)*cluster_size]
frame_header = b'\x00\x00\x00\x02\t\x10\x00\x00\x00'
offsets = [i['offset'] for i in idx]
n_old = 0
last_cluster = header2


def last_frame(b):
    for o in offsets:
        if o+10 < len(b):
            if tmp[o:o+len(frame_header)] == frame_header:
                #print(o, 'got it')
                pass
            else:
                return o
        else:
            return o
    return None


while True:
    next_pos = last_frame(tmp)
    if next_pos is None:
        break

    # find next cluster
    for c in range(last_cluster+1, stop):
        cluster = mybytes[c*cluster_size: (c+1)*cluster_size]
        p = next_pos % cluster_size
        if cluster[p:p+len(frame_header)] == frame_header:
            tmp += cluster
            used[c] = 3
            break
    else:
        print('no cluster found')

for i, u in enumerate(used):
    if u == 2:
        cluster = mybytes[i*cluster_size: (i+1)*cluster_size]
        tmp += cluster
with open('reconstructed01.LRV', 'wb') as out2:
    out2.write(tmp)

out = Counter(used)
new = []
for u in used:
    if u != 0:
        new.append(u)
    else:
        new.append(-3)
save_used(new, 'used-last.json')


# cut to correct size

shutil.copyfile(LRV, 'reconstructed01.LRV_before_cut')
with open('reconstructed01.LRV', 'rb') as f:
    f.read(20)
    mybytes = f.read(4)
    mdat_length = int.from_bytes(mybytes, byteorder='big')
    print('mdat length:', mdat_length)
    f.seek(mdat_length-4, 1)
    mybytes = f.read(4)
    moov_length = int.from_bytes(mybytes, byteorder='big')
    print('moov lengths', moov_length)

total = 20 + mdat_length + moov_length
print('file size', total)
with open('reconstructed01.LRV', 'rb') as f:
    mybytes = f.read()

with open('reconstructed01.LRV', 'wb') as f:
    f.write(mybytes[:total])

sys.stdout.flush()
