"""Bounded, opaque TCP relay on a private Docker bridge; no public listener."""
import argparse
import ipaddress
import json
from pathlib import Path
import selectors
import signal
import socket
import time

BUFFER_LIMIT = 65536
PORTS = {28082: 28081, 19191: 19190}


class Endpoint:
    def __init__(self, sock):
        self.sock = sock
        self.peer = None
        self.pending = bytearray()
        self.read_open = self.write_open = True
        self.shutdown_pending = self.closed = self.registered = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', required=True)
    parser.add_argument('--state', type=Path, required=True)
    args = parser.parse_args()
    address = ipaddress.ip_address(args.bind)
    assert address.version == 4 and address.is_private and not address.is_unspecified and not address.is_multicast
    assert args.state.is_absolute()
    selector = selectors.DefaultSelector()
    endpoints = set()
    listeners = []
    running = True
    counts = {'connections': 0, 'connect_errors': 0, 'io_errors': 0, 'forwarded_bytes': 0}

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def close_pair(endpoint):
        for item in (endpoint, endpoint.peer):
            if item is None or item.closed:
                continue
            item.closed = True
            if item.registered:
                selector.unregister(item.sock)
                item.registered = False
            item.sock.close()
            endpoints.discard(item)

    def refresh(endpoint):
        if endpoint.closed:
            return
        if endpoint.shutdown_pending and not endpoint.pending and endpoint.write_open:
            endpoint.sock.shutdown(socket.SHUT_WR)
            endpoint.write_open = False
        if not endpoint.read_open and not endpoint.peer.read_open and not endpoint.pending and not endpoint.peer.pending:
            close_pair(endpoint)
            return
        mask = 0
        if endpoint.read_open and len(endpoint.peer.pending) < BUFFER_LIMIT:
            mask |= selectors.EVENT_READ
        if endpoint.pending and endpoint.write_open:
            mask |= selectors.EVENT_WRITE
        if mask:
            if endpoint.registered:
                selector.modify(endpoint.sock, mask, endpoint)
            else:
                selector.register(endpoint.sock, mask, endpoint)
                endpoint.registered = True
        elif endpoint.registered:
            selector.unregister(endpoint.sock)
            endpoint.registered = False

    def state(ready):
        data = {'ready': ready, 'at': time.time(), 'bind': args.bind, 'ports': PORTS,
                'active_connections': len(endpoints) // 2, 'buffer_limit_per_direction': BUFFER_LIMIT,
                'counts': counts, 'payload_logging': False}
        temp = args.state.with_suffix('.tmp')
        temp.write_text(json.dumps(data, indent=2) + '\n')
        temp.chmod(0o600)
        temp.replace(args.state)

    try:
        for listen_port, target_port in PORTS.items():
            listener = socket.socket()
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((args.bind, listen_port))
            listener.listen(256)
            listener.setblocking(False)
            listeners.append(listener)
            selector.register(listener, selectors.EVENT_READ, target_port)
        next_state = 0
        while running:
            for key, mask in selector.select(timeout=.5):
                if isinstance(key.data, int):
                    try:
                        client, _ = key.fileobj.accept()
                    except BlockingIOError:
                        continue
                    except OSError:
                        counts['connect_errors'] += 1
                        continue
                    try:
                        upstream = socket.create_connection(('127.0.0.1', key.data), timeout=2)
                    except OSError:
                        counts['connect_errors'] += 1
                        client.close()
                        continue
                    client.setblocking(False)
                    upstream.setblocking(False)
                    left, right = Endpoint(client), Endpoint(upstream)
                    left.peer, right.peer = right, left
                    endpoints.update((left, right))
                    counts['connections'] += 1
                    refresh(left)
                    refresh(right)
                    continue
                endpoint = key.data
                if endpoint.closed:
                    continue
                try:
                    if mask & selectors.EVENT_WRITE:
                        sent = endpoint.sock.send(endpoint.pending)
                        del endpoint.pending[:sent]
                        counts['forwarded_bytes'] += sent
                        refresh(endpoint.peer)
                    if mask & selectors.EVENT_READ:
                        capacity = BUFFER_LIMIT - len(endpoint.peer.pending)
                        if capacity:
                            data = endpoint.sock.recv(min(16384, capacity))
                            if data:
                                endpoint.peer.pending.extend(data)
                            else:
                                endpoint.read_open = False
                                endpoint.peer.shutdown_pending = True
                        refresh(endpoint.peer)
                    refresh(endpoint)
                except BlockingIOError:
                    pass
                except OSError:
                    counts['io_errors'] += 1
                    close_pair(endpoint)
            if time.monotonic() >= next_state:
                state(True)
                next_state = time.monotonic() + 2
    finally:
        for endpoint in list(endpoints):
            close_pair(endpoint)
        for listener in listeners:
            selector.unregister(listener)
            listener.close()
        selector.close()
        state(False)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
