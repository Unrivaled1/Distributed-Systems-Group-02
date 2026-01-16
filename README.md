# Distributed-Systems-Group-02

A Python-based distributed system simulator demonstrating **leader election**, **automatic peer discovery**, and **chat message broadcasting** on a single machine.

## Overview

This project simulates a distributed system where multiple independent node processes:
1. **Discover each other** via UDP multicast without configuration
2. **Form a logical ring** where each node knows only its left and right neighbors
3. **Elect a leader** using the **Le Lann–Chang–Roberts (LCR) algorithm**
4. **Detect leader failures** via periodic heartbeats and trigger new elections
5. **Broadcast chat messages** from clients to all connected nodes through the leader

The system is designed for **clarity and correctness** rather than performance, making it ideal for understanding distributed algorithms.

## Architecture

- **Discovery**: Nodes broadcast `HELLO` packets via UDP multicast (224.1.1.1:50000) to discover peers and learn listening ports.
- **Ring Communication**: Nodes form a ring ordered by ID; messages pass via TCP connections to the right neighbor.
- **Leader Election**: Uses LCR algorithm — nodes forward the highest ID they see around the ring. When a node receives its own ID, it becomes leader and announces via a `LEADER` message.
- **Heartbeats**: The leader periodically sends a `HEARTBEAT` message around the ring. Non-leader nodes detect timeout (> 6 seconds) and trigger a new election.
- **Chat**: Only the leader accepts client connections. Clients send messages; the leader broadcasts them to all connected clients.

## Files

- `nodes/node.py` — the node process. Run multiple instances to simulate a cluster.
- `nodes/chat_client.py` — a simple client that discovers and connects to the leader.

## Quick Start

### Single Machine (Demo)

Open **four terminals** on the same machine and run:

**Terminal 1 – Node 101:**
```bash
python3 nodes/node.py --id 101
```

**Terminal 2 – Node 205:**
```bash
python3 nodes/node.py --id 205
```

**Terminal 3 – Node 330:**
```bash
python3 nodes/node.py --id 330
```

Each node will print:
```
Node 101 listening: ring_port=45019 client_port=38769
Node 101 neighbors updated: left=(330, '192.168.1.10', 43849) right=(205, '192.168.1.10', 36233)
Node 101 received ring msg: ELECTION 330
```

After ~2 seconds, the highest-ID node (330) becomes leader and the others receive the `LEADER` announcement.

**Terminal 4 – Chat Client:**
```bash
python3 nodes/chat_client.py
```

Output:
```
Discovering nodes...
Connected to leader. Type messages and press Enter.
```

Type messages and press Enter. The leader broadcasts them to all connected clients:
```
hello world
[330] hello world
```

### Multiple Machines

The system now supports running on **separate computers** on the same network:

1. **Ensure network connectivity**: All nodes must be on the same LAN and able to reach the multicast address `224.1.1.1:50000`.

2. **Start nodes on different machines**:
   - Machine A (192.168.1.10): `python3 nodes/node.py --id 101`
   - Machine B (192.168.1.20): `python3 nodes/node.py --id 205`
   - Machine C (192.168.1.30): `python3 nodes/node.py --id 330`

3. **Run chat client on any machine** that can reach the network:
   ```bash
   python3 nodes/chat_client.py
   ```

The client automatically discovers all nodes via multicast and connects to the elected leader, regardless of which machine it's on. Messages broadcast correctly across all machines.

## Debug Output

Nodes log:
- **Neighbor updates** when ring topology changes
- **Ring messages** (ELECTION, LEADER, HEARTBEAT) as they pass around
- **Connection attempts** if a node can't reach its neighbor
- **Leader elections** and leadership announcements

This verbose output helps you understand the algorithm's flow; it can be reduced or silenced with a flag in future versions.

## Testing Leader Failure

1. Stop the leader node (Ctrl+C).
2. Within 6 seconds, the remaining nodes detect timeout and start a new election.
3. The next highest-ID node becomes leader.
4. Clients automatically reconnect to the new leader.

## Constraints & Design Decisions

- **LAN only** — requires UDP multicast support (224.1.1.1:50000). Works on single machine and across any LAN.
- **Python + sockets** — no external dependencies; standard library only.
- **Clarity over performance** — straightforward threading and blocking I/O.
- **LCR algorithm** — proven leader election for ring topologies; guarantees exactly one leader when stable.
- **Heartbeat timeout = 6s, interval = 2s** — tuned for LAN networks; adjust for higher latency.

## Extension Ideas

- Add node failures and recovery
- Implement log replication or consensus (Raft, Paxos)
- Add persistent state or snapshots
- Support arbitrary network topologies (not just ring)
- Visualize the ring and message flow in real time
