#!/usr/bin/env python3
import socket
import threading

HOST = '127.0.0.1'
PORT = 12345

clients = []
clients_lock = threading.Lock()


def broadcast(message, sender_sock=None):
    with clients_lock:
        for c in clients:
            if c is sender_sock:
                continue
            try:
                c.sendall(message.encode('utf-8'))
            except Exception:
                pass


def handle_client(conn, addr):
    print(f"Connected: {addr}")
    name = None
    try:
        with conn:
            # First message from client is the user name (terminated by newline)
            name = conn.recv(1024).decode().strip()
            if not name:
                name = f"{addr}"
            welcome = f"Server: {name} joined the chat.\n"
            broadcast(welcome, conn)
            conn.sendall(f"Welcome {name}! Type messages and press enter.\n".encode())
            with clients_lock:
                clients.append(conn)

            while True:
                data = conn.recv(1024)
                if not data:
                    break
                msg = data.decode().strip()
                if msg.lower() == '/quit':
                    break
                full = f"{name}: {msg}\n"
                print(full.strip())
                broadcast(full, conn)
    except Exception as e:
        print("Error handling client:", e)
    finally:
        with clients_lock:
            if conn in clients:
                clients.remove(conn)
        if name:
            leave = f"Server: {name} left the chat.\n"
            broadcast(leave, None)
        print(f"Disconnected: {addr}")


def main():
    serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serv.bind((HOST, PORT))
    serv.listen()
    print(f"Server listening on {HOST}:{PORT}")
    try:
        while True:
            conn, addr = serv.accept()
            thr = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            thr.start()
    except KeyboardInterrupt:
        print("Shutting down server")
    finally:
        serv.close()


if __name__ == '__main__':
    main()
