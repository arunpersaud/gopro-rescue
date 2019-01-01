"""
Usage: recon1.py <start> <header2> <stop>
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

# tahoe video
# start = 540443
# stop = 540748+2


commands = docopt(__doc__)
header1 = 0
start = int(commands['<start>'])
header2 = int(commands['<header2>'])-start
stop = int(commands['<stop>'])


with open('/sdimage-p1.img', 'rb') as f:
    # f.seek(cluster_size*855)
    # mybytes = f.read((2058-855)*cluster_size)
    f.seek(cluster_size*start)
    mybytes = f.read((stop-start)*cluster_size)

header = b'\x00\x00\x00\x14\x66\x74\x79\x70\x6d\x70\x34\x31\x20\x13\x10\x18'
zero_cluster = b'\x00'*cluster_size


def save_used(used, filename='used.json'):
    """Save all information used to reconstruct movie"""
    data = {'image': '/sdimage-p1.img', 'start': start,
            'header2': header2, 'stop': stop, 'used': [int(x) for x in used]}
    with open(filename, 'w') as f:
        json.dump(data, f)


assert mybytes[:len(header)] == header, 'Wrong first header'
assert mybytes[header2*cluster_size:header2*cluster_size+len(header)] == header, 'Wrong second header'

mdat1 = int.from_bytes(mybytes[20:24], byteorder='big') // cluster_size
mdat2 = int.from_bytes(mybytes[header2*cluster_size+20:header2 *
                               cluster_size+24], byteorder='big') // cluster_size

print('mdat', mdat1, mdat2)
# find moov+mvhd positions
pos = 0
moov1 = None
moov2 = None

while True:
    pos = mybytes.find(b'moov', pos+1)
    if pos == -1:
        break
    if moov1:
        moov2 = pos
    else:
        moov1 = pos
    # print(mybytes[pos+8:pos+12])

print(moov1, moov2)
a = moov1 % cluster_size

assert moov1 % cluster_size < cluster_size - \
    10, f"moov1 near end of cluster {a} < {cluster_size}"
assert moov2 % cluster_size < cluster_size - 10, "moov2 near end of cluster"

assert moov1 % cluster_size > 5, "moov1 near start of cluster"
assert moov2 % cluster_size > 5, "moov2 near start of cluster"

moov1_length = int.from_bytes(mybytes[moov1-4:moov1], byteorder='big')
moov2_length = int.from_bytes(mybytes[moov2-4:moov2], byteorder='big')

print('test', moov2, moov2+moov2_length)
print('test', moov2//cluster_size, (moov2+moov2_length)/cluster_size)
moov1 = moov1//cluster_size
moov2 = moov2//cluster_size
print('moov loc', moov1, moov2)
print('moov length', moov1_length, moov2_length)
print('moov length', moov1_length//cluster_size, moov2_length//cluster_size)

# create array to mark which blocks have been used

used = np.array([0] * (len(mybytes)//cluster_size+20))

with open('reconstructed01.MP4', 'wb') as out1:
    out1.write(mybytes[:(header2-4)*cluster_size])
    used[:header2] = -3
    used[0] = -1
    for i in range(mdat1-header2+4):
        out1.write(zero_cluster)
    out1.write(mybytes[moov1*cluster_size:(moov1+1)*cluster_size])
    used[moov1] = -2
with open('reconstructed01.LRV', 'wb') as out2:
    out2.write(mybytes[header2*cluster_size:(header2+4)*cluster_size])
    used[header2:header2+1] = 1
    used[header2+1:header2+4] = 3
    # this is just a guess
    used[header2+5] = -3
    for i in range(mdat2-4):
        out2.write(zero_cluster)
    out2.write(mybytes[moov2*cluster_size:(moov2+2)*cluster_size])
    used[moov2:moov2+2] = 2

LRV_old = Path('reconstructed01.LRV_orig')
LRV = Path('reconstructed01.LRV')
shutil.copyfile(LRV, LRV_old)

out = Counter(used)
assert out[2] <= mdat2-1, f'wrong amount of 2 packages {out[2]} instead of 49'

save_used(used, 'used-orig.json')
print(mdat2)


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
                for j in range(mdat2-c):
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


last = 0
with tqdm(total=len(used), file=sys.stdout) as pbar:
    go = True
    while go:
        out = Counter(used)
        pbar.set_description(f'testing clusters {out[3]:3d}')
        max_frame_old = get_frame_nr('reconstructed01.LRV')
        sound_old = 0  # check_sound('reconstructed01.LRV')
        pos = find_pos(used)
        pbar.update(pos-last)
        # try with new pos included and not
        test1 = used[:]
        if pos+1 == len(used):
            break
        if used[pos+1] == 2:
            print('would overwrite a 2, breaking')
            break
        test1[pos+1] = 3
        good = make_video(test1)
        max_frame = get_frame_nr('reconstructed01.LRV')
        sound = 0  # check_sound('reconstructed01.LRV')
        if max_frame > max_frame_old:  # or sound > sound_old:
            used[pos+1] = 3
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


# MP4_old = Path('reconstructed01.MP4_orig')
# MP4 = Path('reconstructed01.MP4')

# try reconstructing one by one
# while True:
#    # first create backup
#    shutil.copyfile(LRV, LRV_old)
#    shutil.copyfile(MP4, MP4_old)
#
#    # find first unused blocks
#    pos = np.argmin(used)
#    if pos < 10:
#        break
#    data = mybytes[pos*cluster_size:(pos+1)*cluster_size]
#
#    # try adding it to the LRV movie
#    with LRV.open('r+b') as f:
#        block = f.read(cluster_size)
#        while block != zero_cluster:
#            block = f.read(cluster_size)
#        f.seek(-cluster_size, 1)
#        f.write(data)
#    s = input(f'block {pos}: check LRV, is it better (y/n)?')
#    if s == 'n':
#        # undo change
#        shutil.copyfile(LRV_old, LRV)
#        # add to other file
#        with MP4.open('r+b') as f:
#            block = f.read(cluster_size)
#            while block != zero_cluster:
#                block = f.read(cluster_size)
#            f.seek(-cluster_size, 1)
#            f.write(data)
#    used[pos] = True
#
