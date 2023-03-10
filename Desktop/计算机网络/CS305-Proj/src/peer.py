import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import select
import util.simsocket as simsocket
import struct
import socket
import util.bt_utils as bt_utils
import hashlib
import argparse
import pickle
import time

"""
This is CS305 project skeleton code.
Please refer to the example files - example/dumpreceiver.py and example/dumpsender.py - to learn how to play with this skeleton.
"""

BUF_SIZE = 1400
HEADER_LEN = struct.calcsize("HBBHHII")
CHUNK_DATA_SIZE = 512 * 1024
MAX_PAYLOAD = 1024
config = None
ex_output_file = None
ex_received_chunk = dict()
ex_downloading_chunkhash = {}
ex_downloading_index = {}

finish=False
fromaddToindex={}
cwnd = 1.
ssthresh = 64
dupack = 0
cnt = {}
preack = {}
preseq = {}
tim=0
acks={}

chunkf=None
outf=None
def process_download(sock, chunkfile, outputfile):
    '''
    if DOWNLOAD is used, the peer will keep getting files until it is done
    '''
    # print('PROCESS GET SKELETON CODE CALLED.  Fill me in! I\'ve been doing! (', chunkfile, ',     ', outputfile, ')')
    global ex_output_file
    global ex_received_chunk
    global ex_downloading_chunkhash
    global ex_downloading_index
    global cwnd
    global ssthresh
    global dupack
    global cnt
    global preack
    global preseq
    global fromaddToindex
    global acks
    fromaddToindex={}
    cwnd = 1.
    ssthresh = 64
    dupack = 0
    cnt = {}
    preack = {}
    preseq = {}
    acks={}

    ex_output_file = outputfile
    
    # Step 1: read chunkhash to be downloaded from chunkfile
    download_hash = bytes()
    with open(chunkfile, 'r') as cf:
        ijk=cf.readline()
        while ijk !="":
            index, datahash_str = ijk.strip().split(" ")
            ex_received_chunk[datahash_str] = bytes()
            ex_downloading_chunkhash[index] = datahash_str
            ex_downloading_index[datahash_str]=index
            # hex_str to bytes
            datahash = bytes.fromhex(datahash_str)
            download_hash = bytes() + datahash
            whohas_header = struct.pack("HBBHHII", socket.htons(52305), 35, 0, socket.htons(HEADER_LEN),
                                        socket.htons(HEADER_LEN + len(download_hash)), socket.htonl(0), socket.htonl(0))
            whohas_pkt = whohas_header + download_hash

            # Step3: flooding whohas to all peers in peer list
            peer_list = config.peers
            for p in peer_list:
                if int(p[0]) != config.identity:
                    sock.sendto(whohas_pkt, (p[1], int(p[2])))
            ijk = cf.readline()


def process_inbound_udp(sock):
    # Receive pkt
    global config
    global ex_sending_chunkhash
    global cwnd
    global ssthresh
    global dupack
    global cnt
    global preack
    global preseq
    global fromaddToindex
    global tim
    global acks
    global finish
    pkt, from_addr = sock.recvfrom(BUF_SIZE)
    Magic, Team, Type, hlen, plen, Seq, Ack = struct.unpack("HBBHHII", pkt[:HEADER_LEN])
    data = pkt[HEADER_LEN:]
    if Type == 1:
        preseq[from_addr]=0
        # received an IHAVE pkt
        # see what chunk the sender has
        get_chunk_hash = data[:20]
        if fromaddToindex.get(from_addr) is None:
            fromaddToindex[from_addr]=ex_downloading_index.get(bytes.hex(get_chunk_hash))
            # send back GET pkt
            get_header = struct.pack("HBBHHII", socket.htons(52305), 35, 2, socket.htons(HEADER_LEN),
                                    socket.htons(HEADER_LEN + len(get_chunk_hash)), socket.htonl(0), socket.htonl(0))
            get_pkt = get_header + get_chunk_hash
            sock.sendto(get_pkt, from_addr)
    elif Type == 0:
        # received an WHOHAS pkt
        # see what chunk the sender has
        whohas_chunk_hash = data[:20]
        # bytes to hex_str
        chunkhash_str = bytes.hex(whohas_chunk_hash)
        

        print(f"whohas: {chunkhash_str}, has: {list(config.haschunks.keys())}")
        if chunkhash_str in config.haschunks:
            ex_sending_chunkhash = chunkhash_str
            # send back IHAVE pkt
            ihave_header = struct.pack("HBBHHII", socket.htons(52305), 35, 1, socket.htons(HEADER_LEN),
                                       socket.htons(HEADER_LEN + len(whohas_chunk_hash)), socket.htonl(0),
                                       socket.htonl(0))
            ihave_pkt = ihave_header + whohas_chunk_hash
            sock.sendto(ihave_pkt, from_addr)

    elif Type == 2:
        cnt[from_addr] = 1
        preack[from_addr]=-1
        # received a GET pkt
        chunk_data = config.haschunks[ex_sending_chunkhash][:MAX_PAYLOAD]

        # send back DATA
        data_header = struct.pack("HBBHHII", socket.htons(52305), 35, 3, socket.htons(HEADER_LEN),
                                  socket.htons(HEADER_LEN), socket.htonl(1), 0)
        sock.sendto(data_header + chunk_data, from_addr)
    elif Type == 3:
        # received a DATA pkt
        if preseq[from_addr] + 1 == socket.ntohl(Seq):
            preseq[from_addr] = socket.ntohl(Seq)
            ex_received_chunk[ex_downloading_chunkhash[fromaddToindex[from_addr]]] += data
            
            # send back ACK
            ack_pkt = struct.pack("HBBHHII", socket.htons(52305), 35, 4, socket.htons(HEADER_LEN),
                                  socket.htons(HEADER_LEN),
                                  0, socket.htonl(preseq[from_addr]))
            sock.sendto(ack_pkt, from_addr)
        else:
            ack_pkt = struct.pack("HBBHHII", socket.htons(52305), 35, 4, socket.htons(HEADER_LEN),
                                  socket.htons(HEADER_LEN),
                                  0, socket.htonl(preseq[from_addr]))
            sock.sendto(ack_pkt, from_addr)

        # see if finished
        if len(ex_received_chunk[ex_downloading_chunkhash[fromaddToindex[from_addr]]]) == CHUNK_DATA_SIZE:
            # finished downloading this chunkdata!
            # dump your received chunk to file in dict form using pickle
            with open(ex_output_file, "wb") as wf:
                pickle.dump(ex_received_chunk, wf)
            finish=True
            # add to this peer's haschunk:
            config.haschunks[ex_downloading_chunkhash[fromaddToindex[from_addr]]] = ex_received_chunk[ex_downloading_chunkhash[fromaddToindex[from_addr]]]

            # you need to print "GOT" when finished downloading all chunks in a DOWNLOAD file
            print(f"GOT {ex_output_file}")

            # The following things are just for illustration, you do not need to print out in your design.
            sha1 = hashlib.sha1()
            sha1.update(ex_received_chunk[ex_downloading_chunkhash[fromaddToindex[from_addr]]])
            received_chunkhash_str = sha1.hexdigest()
            print(f"Expected chunkhash: {ex_downloading_chunkhash[fromaddToindex[from_addr]]}")
            print(f"Received chunkhash: {received_chunkhash_str}")
            success = ex_downloading_chunkhash[fromaddToindex[from_addr]] == received_chunkhash_str
            print(f"Successful received: {success}")
            if success:
                print("Congrats! You have completed the example!")
            else:
                print("Example fails. Please check the example files carefully.")

    elif Type == 4:
        
        # received an ACK pkt
        ack_num = socket.ntohl(Ack)
        if preack[from_addr] == ack_num:
            dupack += 1

            if dupack == 3:
                left = (ack_num - 1) * MAX_PAYLOAD
                right = min((ack_num) * MAX_PAYLOAD, CHUNK_DATA_SIZE)
                next_data = config.haschunks[ex_sending_chunkhash][left: right]
                # send next data
                data_header = struct.pack("HBBHHII", socket.htons(52305), 35, 3, socket.htons(HEADER_LEN),
                                          socket.htons(HEADER_LEN + len(next_data)),
                                          socket.htonl(ack_num + 1), 0)
                sock.sendto(data_header + next_data, from_addr)
                cnt[from_addr] = ack_num + 1
                ssthresh = max(int(cwnd / 2), 2)
                cwnd = 1
                # print(time.time()-tim)
                # print(cwnd)


        else:
            preack[from_addr] = ack_num
            if cwnd >= ssthresh:
                cwnd = cwnd + 1 / cwnd
            else:
                cwnd = cwnd + 1
            # print(time.time()-tim)
            # print(cwnd)
            if cnt[from_addr] == ack_num:
                for i in range(int(cwnd)):
                    if (ack_num + i) * MAX_PAYLOAD >= CHUNK_DATA_SIZE:
                        # finished
                        print(f"finished sending {ex_sending_chunkhash}")
                        break
                    else:
                        left = (ack_num + i) * MAX_PAYLOAD
                        right = min((ack_num + i + 1) * MAX_PAYLOAD, CHUNK_DATA_SIZE)
                        next_data = config.haschunks[ex_sending_chunkhash][left: right]
                        # send next data
                        data_header = struct.pack("HBBHHII", socket.htons(52305), 35, 3, socket.htons(HEADER_LEN),
                                                  socket.htons(HEADER_LEN + len(next_data)),
                                                  socket.htonl(ack_num + i + 1), 0)
                        sock.sendto(data_header + next_data, from_addr)
                        cnt[from_addr] = ack_num + i + 1
                        acks[(from_addr,ack_num+i+1)]=time.time()

    


def process_user_input(sock):
    global chunkf
    global outf
    command, chunkf, outf = input().split(' ')
    if command == 'DOWNLOAD':
        process_download(sock, chunkf, outf)
    else:
        pass


def peer_run(config):
    global tim
    global chunkf
    global outf
    addr = (config.ip, config.port)
    sock = simsocket.SimSocket(config.identity, addr, verbose=config.verbose)
    tim=time.time()
    tio=time.time()
    try:
        while True:
            ready = select.select([sock, sys.stdin], [], [], 0.1)
            read_ready = ready[0]
            if len(read_ready) > 0:
                if sock in read_ready:
                    process_inbound_udp(sock)
                if sys.stdin in read_ready:
                    process_user_input(sock)
                tio=time.time()
            else:
                if finish:
                    pass
                if time.time()-tio>10:
                    process_download(sock,chunkf,outf)
                    
                # No pkt nor input arrives during this period
                
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


if __name__ == '__main__':
    """
    -p: Peer list file, it will be in the form "*.map" like nodes.map.
    -c: Chunkfile, a dictionary dumped by pickle. It will be loaded automatically in bt_utils. The loaded dictionary has the form: {chunkhash: chunkdata}
    -m: The max number of peer that you can send chunk to concurrently. If more peers ask you for chunks, you should reply "DENIED"
    -i: ID, it is the index in nodes.map
    -v: verbose level for printing logs to stdout, 0 for no verbose, 1 for WARNING level, 2 for INFO, 3 for DEBUG.
    -t: pre-defined timeout. If it is not set, you should estimate timeout via RTT. If it is set, you should not change this time out.
        The timeout will be set when running test scripts. PLEASE do not change timeout if it set.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', type=str, help='<peerfile>     The list of all peers', default='nodes.map')
    parser.add_argument('-c', type=str, help='<chunkfile>    Pickle dumped dictionary {chunkhash: chunkdata}')
    parser.add_argument('-m', type=int, help='<maxconn>      Max # of concurrent sending')
    parser.add_argument('-i', type=int, help='<identity>     Which peer # am I?')
    parser.add_argument('-v', type=int, help='verbose level', default=0)
    parser.add_argument('-t', type=int, help="pre-defined timeout", default=0)
    args = parser.parse_args()

    config = bt_utils.BtConfig(args)
    peer_run(config)
