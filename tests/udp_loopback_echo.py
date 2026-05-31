#!/usr/bin/env python3
import selectors
import socket
import sys
import time


def run_connected_echo() -> None:
    selector = selectors.EpollSelector()
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.setblocking(False)

        port = server.getsockname()[1]
        client.setblocking(False)
        client.connect(("127.0.0.1", port))

        selector.register(server, selectors.EVENT_READ)
        selector.register(client, selectors.EVENT_READ | selectors.EVENT_WRITE)

        payload = b"webrtc-phase2-connected"
        sent = False
        deadline = time.monotonic() + 2.0
        got_echo = False

        while time.monotonic() < deadline and not got_echo:
            for key, mask in selector.select(timeout=0.2):
                sock = key.fileobj
                if sock is client and (mask & selectors.EVENT_WRITE) and not sent:
                    written = client.send(payload)
                    if written != len(payload):
                        raise RuntimeError("connected short send")
                    sent = True
                if sock is server and (mask & selectors.EVENT_READ):
                    data, addr = server.recvfrom(2048)
                    if data != payload:
                        raise RuntimeError("connected payload mismatch")
                    server.sendto(data, addr)
                if sock is client and (mask & selectors.EVENT_READ):
                    data = client.recv(2048)
                    if data != payload:
                        raise RuntimeError("connected echo mismatch")
                    got_echo = True

        if not got_echo:
            raise RuntimeError("connected echo timeout")
    finally:
        selector.close()
        client.close()
        server.close()


def run_fallback_echo() -> None:
    selector = selectors.EpollSelector()
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.setblocking(False)
        client.bind(("127.0.0.1", 0))
        client.setblocking(False)

        port = server.getsockname()[1]
        selector.register(server, selectors.EVENT_READ)
        selector.register(client, selectors.EVENT_READ | selectors.EVENT_WRITE)

        payload = b"webrtc-phase2-fallback"
        sent = False
        deadline = time.monotonic() + 2.0
        got_echo = False

        while time.monotonic() < deadline and not got_echo:
            for key, mask in selector.select(timeout=0.2):
                sock = key.fileobj
                if sock is client and (mask & selectors.EVENT_WRITE) and not sent:
                    written = client.sendto(payload, ("127.0.0.1", port))
                    if written != len(payload):
                        raise RuntimeError("fallback short send")
                    sent = True
                if sock is server and (mask & selectors.EVENT_READ):
                    data, addr = server.recvfrom(2048)
                    if data != payload:
                        raise RuntimeError("fallback payload mismatch")
                    server.sendto(data, addr)
                if sock is client and (mask & selectors.EVENT_READ):
                    data, _addr = client.recvfrom(2048)
                    if data != payload:
                        raise RuntimeError("fallback echo mismatch")
                    got_echo = True

        if not got_echo:
            raise RuntimeError("fallback echo timeout")
    finally:
        selector.close()
        client.close()
        server.close()


if __name__ == "__main__":
    try:
        run_connected_echo()
        run_fallback_echo()
    except PermissionError:
        sys.stderr.write("skip: sandbox blocks AF_INET/SOCK_DGRAM socket creation\n")
