import pandas as pd
from tqdm import tqdm
from pathlib import Path


cluster_size = 512*256

DB = pd.read_msgpack('cluster-db.msg')

print('get list of all files')
files = set(DB['used'])
for x in ['', 'IMG', 'ZEROS']:
    files.discard(x)

print('get last used cluster for each file')
todo = {}
for f in tqdm(files):
    tmp = DB[DB['used'] == f]
    todo[f] = tmp.index[-1]

print('search and mark segments')
not_found = {}
with open('/sdimage-p1.img', 'rb') as IN:
    for f, c_id in todo.items():
        found = False
        t = Path(f)
        size = t.stat().st_size
        length = size % cluster_size
        last = size // cluster_size
        assert size == last*cluster_size + length, 'wrong size'
        if length == 0:
            continue
        with open(f, 'rb') as TEST:
            TEST.seek(last*cluster_size)
            data = TEST.read(length)
        for cluster_id in range(c_id-255, c_id+255):
            IN.seek(cluster_id*cluster_size)
            tmpdata = IN.read(length)
            if tmpdata == data:
                print('found ', f, ' at', cluster_id, c_id, length)
                found = True
                if DB.loc[cluster_id, 'used'] == '':
                    print('saving')
                    DB.loc[cluster_id, 'used'] = f
                else:
                    print('already got a filename', DB.loc[cluster_id, 'used'])
        if not found:
            print('not found:', f)
            not_found[f] = c_id

print('not_found', not_found)
print('save db')
DB.to_msgpack('cluster-db.msg')
