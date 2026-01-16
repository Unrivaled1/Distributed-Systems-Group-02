#!/usr/bin/env python3
"""
Simple single-machine distributed node simulation.

Features:
- UDP multicast discovery
- Ring formation (each node learns left/right neighbors)
- LCR leader election over TCP ring links
- Leader broadcasts HEARTBEAT token around ring
- Leader accepts chat clients; leader broadcasts client messages to connected clients

Run multiple copies on one machine to simulate nodes.
"""
import argparse
import socket
import struct
import threading
import time
import random
import sys

MCAST_GRP = '224.1.1.1'
MCAST_PORT = 50000
HELLO_INTERVAL = 1.0
HEARTBEAT_INTERVAL = 2.0
HEARTBEAT_TIMEOUT = 6.0


def get_local_ip():
    """Detect local IP address by connecting to a non-routable multicast address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((MCAST_GRP, MCAST_PORT))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


class Node:
    def __init__(self, node_id=None):
        self.id = node_id if node_id is not None else random.randint(1, 10000)
        self.local_ip = get_local_ip()
        self.known = {}  # id -> (host, ring_port, client_port, last_seen)
        self.known[self.id] = (self.local_ip, None, None, time.time())
        self.ring_port = None
        self.client_port = None

        self.neighbor = None  # (id, host, ring_port)
        self.left = None

        self.leader_id = None
        self.last_heartbeat = 0

        self.in_election = False   # hinzugefügt Eletion state avoid getting stuck
        self.last_election_start = 0.0 # hinzugefügt


        self._stop = threading.Event()

        # TCP servers
        self._ring_server_sock = None
        self._client_server_sock = None

        # connected chat clients (only at leader)
        self.clients = []

    def start(self):
        # start TCP servers
        self._start_tcp_servers()

        # start discovery listener/sender
        threading.Thread(target=self._discovery_sender, daemon=True).start()
        threading.Thread(target=self._discovery_listener, daemon=True).start()

        # start ring acceptor
        threading.Thread(target=self._ring_accept_loop, daemon=True).start()

        # start client acceptor
        threading.Thread(target=self._client_accept_loop, daemon=True).start()

        # background ring builder
        threading.Thread(target=self._ring_maintainer, daemon=True).start()

        # heartbeat & monitor
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

        # start initial election after short delay to allow discovery
        threading.Timer(2.0, self.start_election).start()

    def stop(self):
        self._stop.set()

    def _start_tcp_servers(self):
        # ring server: used to talk to neighbor nodes
        rs = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        rs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        rs.bind(('0.0.0.0', 0))
        rs.listen()
        self.ring_port = rs.getsockname()[1]
        self._ring_server_sock = rs

        # client server: only leader accepts
        cs = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        cs.bind(('0.0.0.0', 0))
        cs.listen()
        self.client_port = cs.getsockname()[1]
        self._client_server_sock = cs

        # register our actual ports and IP in known table for correct ring formation
        self.known[self.id] = (self.local_ip, self.ring_port, self.client_port, time.time())
        print(f"Node {self.id} listening: ring_port={self.ring_port} client_port={self.client_port}")

    def _discovery_sender(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # set TTL so multicast stays local
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        while not self._stop.is_set():
            msg = f"HELLO {self.id} {self.local_ip} {self.ring_port} {self.client_port}"
            sock.sendto(msg.encode(), (MCAST_GRP, MCAST_PORT))
            time.sleep(HELLO_INTERVAL)

    def _discovery_listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', MCAST_PORT))
        mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        while not self._stop.is_set():
            try:
                data, addr = sock.recvfrom(1024)
            except OSError:
                break
            s = data.decode().strip().split()
            if len(s) >= 5 and s[0] == 'HELLO':
                nid = int(s[1])
                host = s[2]
                ring_p = int(s[3])
                client_p = int(s[4])
                # record last seen, host, and ports
                self.known[nid] = (host, ring_p, client_p, time.time())

    def _ring_maintainer(self):
        # periodically trim stale nodes and recompute ring neighbors
        while not self._stop.is_set():
            now = time.time()
            # remove nodes not seen for a while
            torem = [nid for nid, v in list(self.known.items()) if now - v[2] > 10 and nid != self.id]
            for nid in torem:
                del self.known[nid]

            ids = sorted([nid for nid in self.known.keys()])
            if ids:
                # find our index
                if self.id in ids:
                    i = ids.index(self.id)
                    right = ids[(i + 1) % len(ids)]
                    left = ids[(i - 1) % len(ids)]
                    right_host, rp, cp, _ = self.known[right]
                    left_host, lp, lcp, _ = self.known[left]
                    # neighbor info: use actual host
                    if rp is not None:
                        new_neighbor = (right, right_host, rp)
                    else:
                        new_neighbor = None
                    new_left = (left, left_host, lp) if lp is not None else None
                    # log neighbor changes
                    if new_neighbor != self.neighbor or new_left != self.left:
                        self.neighbor = new_neighbor
                        self.left = new_left
                        print(f"Node {self.id} neighbors updated: left={self.left} right={self.neighbor}")

                        # --- NEW: if leader is unknown after a topology change, (re)start election ---
                        if self.leader_id is None and self.neighbor is not None: # ab hier hinzugefügt bis time sleep
                            now2 = time.time()
                            # cooldown avoids spamming elections every second
                            if (not self.in_election) and (now2 - self.last_election_start > 2.0):
                                self.in_election = True
                                self.last_election_start = now2
                                print(f"Node {self.id} no leader after neighbor update -> starting election")
                                self.start_election()
            time.sleep(1.0)

    def _connect_to_neighbor(self):
        if not self.neighbor:
            return None
        nid, host, port = self.neighbor
        try:
            s = socket.create_connection((host, port), timeout=2)
            return s
        except Exception:
            print(f"Node {self.id} failed connect to neighbor {self.neighbor}")
            return None

    def _ring_accept_loop(self):
        sock = self._ring_server_sock
        while not self._stop.is_set():
            try:
                conn, addr = sock.accept()
            except OSError:
                break
            print(f"Node {self.id} accepted ring connection from {addr}")
            threading.Thread(target=self._handle_ring_conn, args=(conn,), daemon=True).start()

    def _handle_ring_conn(self, conn):
        with conn:
            f = conn.makefile('r')
            for line in f:
                line = line.strip()
                if not line:
                    continue
                print(f"Node {self.id} received ring msg: {line}")
                parts = line.split()
                cmd = parts[0]
                if cmd == 'ELECTION':
                    eid = int(parts[1])
                    self._on_election_msg(eid)
                elif cmd == 'LEADER':
                    lid = int(parts[1])
                    self._on_leader_msg(lid)
                elif cmd == 'HEARTBEAT':
                    lid = int(parts[1])
                    self._on_heartbeat(lid)

    def _client_accept_loop(self):
        sock = self._client_server_sock
        while not self._stop.is_set():
            try:
                conn, addr = sock.accept()
            except OSError:
                break
            # Only leader handles clients
            if self.leader_id == self.id:
                try:
                    conn.sendall(b"WELCOME\n")
                except Exception:
                    pass
                print(f"Leader {self.id} accepted client {addr}")
                self.clients.append(conn)
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
            else:
                # politely close
                conn.sendall(b"NOT_LEADER\n")
                conn.close()

    def _handle_client(self, conn):
        with conn:
            f = conn.makefile('r')
            for line in f:
                msg = line.rstrip('\n')
                if msg:
                    self._broadcast_to_clients(f"[{self.id}] {msg}")

    def _broadcast_to_clients(self, text):
        dead = []
        for c in list(self.clients):
            try:
                c.sendall((text + "\n").encode())
            except Exception:
                dead.append(c)
        for d in dead:
            try:
                d.close()
            except Exception:
                pass
            if d in self.clients:
                self.clients.remove(d)

    def start_election(self):
        print(f"Node {self.id} initiating election")
        self._send_ring_message(f"ELECTION {self.id}")

    def _send_ring_message(self, text):
        s = self._connect_to_neighbor()
        if not s:
            # couldn't reach neighbor; try later
            return
        try:
            s.sendall((text + "\n").encode())
        except Exception:
            pass
        finally:
            s.close()

    def _on_election_msg(self, eid):
        if eid == self.id:
            # I'm leader
            self.leader_id = self.id
            self.in_election = False
            print(f"Node {self.id} became leader")
            # announce
            self._send_ring_message(f"LEADER {self.id}")
        elif eid > self.id:
            # forward the larger id
            self._send_ring_message(f"ELECTION {eid}")
        else:
            # received smaller id: LCR rule -> send our own id
            self._send_ring_message(f"ELECTION {self.id}")

    def _on_leader_msg(self, lid):
        self.leader_id = lid
        self.in_election = False 
        self.last_heartbeat = time.time()
        # forward if not originated by us
        if lid != self.id:
            self._send_ring_message(f"LEADER {lid}")

    def _on_heartbeat(self, lid):
        self.leader_id = lid
        self.last_heartbeat = time.time()
        # forward
        if lid != self.id:
            self._send_ring_message(f"HEARTBEAT {lid}")

    def _heartbeat_loop(self):
        while not self._stop.is_set():
            if self.leader_id == self.id:
                # leader sends heartbeat around ring
                self._send_ring_message(f"HEARTBEAT {self.id}")
                # also announce leader client readiness
                # leader will accept clients automatically
            else:
                # check timeout
                if self.leader_id and time.time() - self.last_heartbeat > HEARTBEAT_TIMEOUT:
                    print(f"Node {self.id} detects leader timeout; starting election")
                    self.leader_id = None
                    self.start_election()
            time.sleep(HEARTBEAT_INTERVAL)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--id', type=int, help='Optional node id (integer)')
    args = p.parse_args()
    node = Node(node_id=args.id)
    try:
        node.start()
        # run until ctrl-c
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('Shutting down')
        node.stop()


if __name__ == '__main__':
    main()