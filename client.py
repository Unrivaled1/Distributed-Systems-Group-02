#!/usr/bin/env python3
import socket
import threading
import sys

HOST = '127.0.0.1'
PORT = 12345


def recv_thread(sock):
    try:
        while True:
            data = sock.recv(1024)
            if not data:
                print("\n[Disconnected from server]")
                break
            # Print server messages as-is (they include trailing newlines)
            print(data.decode(), end='')
    except Exception as e:
        print("Receive error:", e)
    finally:
        try:
            sock.close()
        except Exception:
            pass
        sys.exit(0)


def main():
    name = input("Enter your name: ").strip()
    if not name:
        name = "Anonymous"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))

    # Send name as first message
    sock.sendall((name + '\n').encode())

    thr = threading.Thread(target=recv_thread, args=(sock,), daemon=True)
    thr.start()

    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.rstrip('\n')
            sock.sendall((line + '\n').encode())
            if line.lower() == '/quit':
                break
    except KeyboardInterrupt:
        try:
            sock.sendall(b'/quit\n')
        except Exception:
            pass
    finally:
        sock.close()


if __name__ == '__main__':
    main()
