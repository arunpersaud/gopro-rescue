"""
Usage: movie-test <files>...

"""

from docopt import docopt
import json
from pathlib import Path
import subprocess
from tqdm import tqdm

commands = docopt(__doc__)

files = commands['<files>']

header = b'\x00\x00\x00\x14\x66\x74\x79\x70\x6d\x70\x34\x31\x20\x13\x10\x18'
frame_header = b'\x00\x00\x00\x02\t\x10\x00\x00\x00'
CS = 512*256

for f in files:
    try:
        # read video index
        out = subprocess.run(['/home/arun/src/Prog/Bento4/cmakebuild/mp4iframeindex',
                              f], stdout=subprocess.PIPE)
        idx = json.loads(out.stdout)
        offsets = [i['offset'] for i in idx[:-1]]
    except json.decoder.JSONDecodeError:
        print('-'*30)
        print(f'LRV file cannot be parsed for file {f}')
        myfile = Path(f)
        size = myfile.stat().st_size
        with open(f, 'rb') as IN:
            cluster = IN.read(CS)
            if not cluster[:len(header)] == header:
                print(f'  NO LRV: Wrong header')
            mdat_length = int.from_bytes(cluster[20:24], byteorder='big')
            IN.seek(20+mdat_length, 0)
            moov_data = IN.read(4)
            moov_length = int.from_bytes(moov_data, byteorder='big')
            moov_string = IN.read(4)
            if not moov_string == b'moov':
                print(f'  NO LRV: no moov')
            if 20+moov_length+mdat_length != size:
                delta = size - (20+moov_length+mdat_length)
                print(f'  filesize: {size}')
                print(f'  moov_length: {moov_length}')
                print(f'  mdat_length: {mdat_length}')
                print(f'  need: {20+moov_length+mdat_length}')
                print(
                    f'  NO LRV: wrong size: delta= {delta} bytest, {delta//CS} clusters (<0 too short, >0 too long)')

        continue

    with open(f, 'rb') as IN:
        test_header = IN.read(len(header))
        if not test_header == header:
            print(f'Wrong header in {f}')
            continue
        for o in offsets:
            IN.seek(o)
            test_frame_header = IN.read(len(frame_header))
            if not test_header == header:
                print(f'Wrong header in {f}')
                break
