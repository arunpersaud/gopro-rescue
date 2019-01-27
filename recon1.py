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


def get_frame_nr(filename):
    with redirect_stdout(None):
        with redirect_stderr(None):
            last_ret = True
            A = cv2.VideoCapture(filename)
            frames = []
            while True:
                ret, frame = A.read()
                if ret == False and last_ret == False:
                    break
                last_ret = ret
                frames.append(frame)
    return len(frames)


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

LRV_old = Path('reconstructed01.LRV_orig')
LRV = Path('reconstructed01.LRV')
shutil.copyfile(LRV, LRV_old)

out = Counter(used)

save_used(used, 'used-orig.json')


def make_video(used):
    save_used(used, 'used-current.json')
    c = 0
    assert 1 in used, 'header is missing'
    assert 2 in used, 'moov is missing'
    assert 3 in used, 'blocks are missing'
    with open('reconstructed01.LRV', 'wb') as out2:
        for i, k in enumerate(used):
            if k in [1, 3]:
                out2.write(mybytes[i*cluster_size:(i+1)*cluster_size])
                c += 1
            if k == 2:
                for j in range(mdat2_cluster_length-c):
                    out2.write(zero_cluster)
                out2.write(mybytes[i*cluster_size:(i+2)*cluster_size])
                break
    return c


def find_pos(used):
    """find highest postion after a 3 that is 0"""
    pos = 0
    for i, v in enumerate(used):
        if v == 3:
            pos = i
    for i, v in enumerate(used):
        if i <= pos:
            continue
        if v == 3:
            continue
        if v < 0:
            pos = i
        if v == 2:
            continue
        if v >= 0:
            break
    return pos


def check_sound(filename):
    with subprocess.Popen("ffmpeg -y -i reconstructed01.LRV -vn -c:a copy soundtrack.m4a", shell=True, cwd='/home/arun/tmp/recup_dir.1', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as p:
        pass
    with subprocess.Popen("mplayer -ao null -speed 100 soundtrack.m4a", shell=True, cwd='/home/arun/tmp/recup_dir.1', bufsize=1, universal_newlines=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE) as p:
        for line in p.stdout:
            if 'channel element' in line:
                p.stdin.write('q')
                p.stdin.flush()
                break
        before, after = line.split('channel element')
        nr = after.split()[0]
    return nr

# make_video(used)
# print('nr frames', get_frame_nr('reconstructed01.LRV'))
# sys.exit(0)


pos = 0
last = 0
max_frame_old = 0
with tqdm(total=len(used), file=sys.stdout) as pbar:
    while True:
        out = Counter(used)
        pbar.set_description(f'testing clusters: found->{out[3]:3d}, #fn {max_frame_old}')
        if pos > 350 and out[3] < 4:
            print('giving up.')
            sys.exit(1)

        max_frame_old = get_frame_nr('reconstructed01.LRV')
        sound_old = 0  # check_sound('reconstructed01.LRV')
        # last position
        pos = find_pos(used)
        pbar.update(pos-last)
        # are we done?
        if pos+1 == len(used):
            break
        if used[pos+1] == 2:
            print('would overwrite a 2, breaking')
            break
        # try with new group of 4 at pos included and not
        test1 = used.copy()
        missing = min(mdat2_cluster_length - out[1]-out[3], 4)
        # add a new group of 4 (or less towards the end)
        new_pos = []
        for k in range(missing):
            if used[pos+1+k] != 0:
                print(f'would overwrite a used block, skipping... value {used[pos+1+k]} position {pos+1+k}')
            else:
                test1[pos+1+k] = 3
                new_pos.append(pos+1+k)
        good = make_video(test1)
        max_frame = get_frame_nr('reconstructed01.LRV')
        sound = 0  # check_sound('reconstructed01.LRV')
        if max_frame > max_frame_old:  # or sound > sound_old:
            # used[pos+1] = 3
            # find length of current run
            l = 0
            n = pos
            while used[n] > 0:
                n -= 1
                l += 1
            # copy new position, but don't make a run longer than 4
            for n in new_pos:
                if l < 4:
                    used[n] = 3
                    l += 1
            # print(f'pos {pos+1} is good', sound, max_frame)
        else:
            used[pos+1] = -3
            # print(f'pos {pos+1} is bad', sound, max_frame)
        last = pos

out = Counter(used)
save_used(used, 'used-last.json')

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
