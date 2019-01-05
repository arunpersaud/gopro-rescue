import sys

cluster_size = 256*512
movie_header = b'\x00\x00\x00\x14\x66\x74\x79\x70\x6d\x70\x34\x31\x20\x13\x10\x18'

status = ''


def find_second_moov(datafile, cluster_id, last_cluster):

    #print('search start stop', cluster_id, last_cluster)
    datafile.seek(cluster_id*cluster_size)
    mybytes = datafile.read((last_cluster-cluster_id+1)*cluster_size)
    #print(f'length of data: {len(mybytes)}')
    clusters = []

    submoov = [b'mvhd', b'udta', b'iods', b'trak', b'trak', b'trak', b'trak', b'trak']

    pos = mybytes.find(b'moov')
    moov_length = int.from_bytes(mybytes[pos-4:pos], byteorder='big')
    #print('moov length', moov_length)

    submoov_length = []
    for i in submoov:
        pos = mybytes.find(i, pos+1)
        #print(i, pos, pos % cluster_size)
        l = int.from_bytes(mybytes[pos-4:pos], byteorder='big')
        submoov_length.append(l)
        clusters.append((pos//cluster_size)+cluster_id)
        clusters.append(((pos-4+l)//cluster_size)+cluster_id)
        # print(
        #    f'found {i} at {pos}, with length {l} in cluster {clusters[-1]}, end in cluster {((pos-4+l)//cluster_size)+cluster_id}')

    clusters = set(clusters)
    return clusters


with open('/sdimage-p1.img', 'rb') as datafile:
    with open('done.txt', 'r') as f:
        lines = f.readlines()

        for l in lines:
            if 'not working' in l:
                status = 'not working'
            elif 'todo' in l:
                status = 'todo'

            good = True
            pos = l.find('#')
            if pos > 0:
                l = l[:pos-1]
            numbers = l.split()
            if len(numbers) != 3:
                continue
            print('-'*20)
            numbers = [int(n) for n in numbers]
            start, header, stop = numbers

            print(f'checking {start} {header} {stop}')

            # check header

            datafile.seek(start*cluster_size, 0)
            mybytes = datafile.read(len(movie_header))
            if mybytes != movie_header:
                print('wrong header')
                good = False
            datafile.seek(start*cluster_size+20, 0)
            mybytes = datafile.read(4)
            mdat1_length = int.from_bytes(mybytes, byteorder='big')

            datafile.seek(header*cluster_size, 0)
            mybytes = datafile.read(len(movie_header))
            if mybytes != movie_header:
                print('wrong header for 2nd movie')
                good = False
            datafile.seek(header*cluster_size+20, 0)
            mybytes = datafile.read(4)
            mdat2_length = int.from_bytes(mybytes, byteorder='big')

            # check moov

            datafile.seek((stop-10)*cluster_size, 0)
            mybytes = datafile.read(cluster_size*10)
            pos = mybytes.find(b'moov')
            if (pos % cluster_size) != ((mdat1_length+24) % cluster_size):
                print('wrong moov1 pos', stop-2, pos % cluster_size, (mdat1_length+20) % cluster_size)
                good = False
            if (pos % cluster_size) > cluster_size - 10:
                print('moov1 too close to end')
                good = False
            moov1_length = int.from_bytes(mybytes[pos-4:pos], byteorder='big')
            ids1 = [1]
            if (pos % cluster_size) + moov1_length > cluster_size:
                print('moov1 in more than one cluster!')
                ids1 = find_second_moov(datafile, pos//cluster_size + stop - 10, stop)
                print('complete moov1: ', ids1)
                #good = False

            datafile.seek((stop-10+pos//cluster_size+1)*cluster_size, 0)
            mybytes = datafile.read(cluster_size*6)
            pos = mybytes.find(b'moov')
            if (pos % cluster_size) != ((mdat2_length+24) % cluster_size):
                print('wrong moov2 pos', stop-1, pos % cluster_size, (mdat2_length+20) % cluster_size)
                good = False
            if (pos % cluster_size) > cluster_size - 10:
                print('moov2 too close to end')
                good = False
            moov2_length = int.from_bytes(mybytes[pos-4:pos], byteorder='big')
            ids2 = [1]
            if (pos % cluster_size) + moov2_length > cluster_size:
                print('moov2 in more than one cluster!')
                ids2 = find_second_moov(datafile, pos//cluster_size + stop - 10, stop)
                print('complete moov2: ', ids2)
                #good = False

            # check number of clusters

            total = (mdat1_length+20)//cluster_size + (mdat2_length+20)//cluster_size + len(ids1) + len(ids2)
            if total != stop-start:
                print(f'wrong number of clusters, need {total}, got {stop-start}')
                good = False

            if good:
                print('All good', status)
