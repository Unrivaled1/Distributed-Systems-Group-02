Simple Python Chat (one server, one-or-more clients)

Files:
 - `server.py`: Simple TCP chat server (supports multiple clients).
 - `client.py`: Simple TCP client to connect to the server.

How it works:
 - Start the server. It listens on `127.0.0.1:12345` by default.
 - Start one or more clients. Each client sends a username as the first message.
 - Clients type messages and press Enter; messages are broadcast to other clients.
 - Type `/quit` or press Ctrl+C to exit a client.

Run (in separate terminals):

```bash
 python3 server.py
```

```bash
 python3 client.py
```

Quick example:

 - Terminal 1 (server):

```bash
 python3 server.py
```

 - Terminal 2 (client):

```bash
 python3 client.py
 # enter name when prompted, then type messages
```

Commands:
 - `/quit`: disconnect the client cleanly.

Notes:
 - Uses only Python standard library — no external dependencies.
 - To change host or port, edit the `HOST` / `PORT` constants in the files.
# Distributed-Systems-Group-02