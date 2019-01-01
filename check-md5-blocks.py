"""
Usage: check-md5-blocks.py <files>...
"""


import docopt
import hashlib
import mmap
import pandas as pd
from tqdm import tqdm
from pathlib import Path
import sys

commands = docopt.docopt(__doc__)
print(commands)

DB_file = Path('/home/arun/tmp/recup_dir.1/cluster-db.msg')  # storage for panda dataframe
if DB_file.is_file():
    DB = pd.read_msgpack(DB_file)
else:
    print('DB missing')
    # sys.exit(1)
    print('using dummy data')
    DB = pd.DataFrame(index=[0, 1, 2, 3, 4])
    DB['md5'] = 'test'

for f in tqdm(commands['<files>']):
    myfile = Path(f)
    if not myfile.is_file():
        print('File missing')
        sys.exit(2)
    size = myfile.stat().st_size

    cluster_size = 512*256

    pos = 0
    with tqdm(total=size//cluster_size) as pbar:
        pbar.set_description(f)
        with myfile.open('rb') as myf:
            while pos < size:

                chunk = myf.read(cluster_size)
                pos += cluster_size

                mymd5 = hashlib.md5()
                mymd5.update(chunk)
                hexmd5 = mymd5.hexdigest()

                if hexmd5 in DB['md5'].values:
                    print('found it')
                pbar.update(1)
