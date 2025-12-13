#!/usr/bin/env python3
"""
Simple chat client that discovers nodes via multicast and connects to the leader.

Behavior:
- Listens on multicast for a short period to learn nodes and their client ports
- Tries connecting to known nodes; the leader accepts clients, others reply with "NOT_LEADER"
- After connecting to a leader, read stdin lines and send them; print incoming broadcast messages
"""
import socket
import struct
import time
import threading

MCAST_GRP = '224.1.1.1'
MCAST_PORT = 50000


def discover(timeout=2.0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', MCAST_PORT))
    mreq = struct.pack('4sl', socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.settimeout(timeout)
    nodes = {}
    t0 = time.time()
    try:
        while time.time() - t0 < timeout:
            data, addr = sock.recvfrom(1024)
            parts = data.decode().strip().split()
            if len(parts) >= 4 and parts[0] == 'HELLO':
                nid = int(parts[1])
                rp = int(parts[2])
                cp = int(parts[3])
                nodes[nid] = ('127.0.0.1', cp)
    except socket.timeout:
        pass
    return nodes


def try_connect(nodes):
    for nid, (host, port) in sorted(nodes.items()):
        try:
            s = socket.create_connection((host, port), timeout=1)
            s.settimeout(1.0)
            try:
                data = s.recv(32)
                if data.strip() == b'NOT_LEADER':
                    s.close()
                    continue
                if data.strip() == b'WELCOME':
                    s.settimeout(None)
                    return s
                # unknown response: close and continue
                s.close()
                continue
            except socket.timeout:
                # no immediate response — assume this is a leader (best-effort)
                s.settimeout(None)
                return s
        except Exception:
            continue
    return None


def main():
    print('Discovering nodes...')
    nodes = discover()
    if not nodes:
        print('No nodes discovered')
        return
    print('Known nodes:', nodes)
    s = try_connect(nodes)
    if not s:
        print('Could not find leader to connect to')
        return
    print('Connected to leader. Type messages and press Enter.')

    def recv_loop(sock):
        f = sock.makefile('r')
        for line in f:
            print(line.rstrip('\n'))

    threading.Thread(target=recv_loop, args=(s,), daemon=True).start()
    try:
        while True:
            line = input()
            s.sendall((line + '\n').encode())
    except (KeyboardInterrupt, EOFError):
        s.close()


if __name__ == '__main__':
    main()
