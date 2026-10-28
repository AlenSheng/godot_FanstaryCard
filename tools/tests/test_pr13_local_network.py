import socket
import threading
import unittest
from urllib.parse import urlparse

from tools.pr13_local_network import LocalOrigins


class LocalOriginTests(unittest.TestCase):
    def test_binary_payload_and_actual_client_ips_are_preserved(self):
        peers, payloads = [], []
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)
        listener.settimeout(5)

        def receive():
            for _ in range(2):
                connection, peer = listener.accept()
                with connection:
                    connection.settimeout(5)
                    data = connection.recv(65536)
                    peers.append(peer[0])
                    payloads.append(data)
                    connection.sendall(data)

        thread = threading.Thread(target=receive)
        thread.start()
        payload = b"\x82\x05binary\x00\xff"
        try:
            with LocalOrigins(f"http://127.0.0.1:{listener.getsockname()[1]}", 2) as origins:
                for address in origins.origins:
                    target = urlparse(address)
                    with socket.create_connection((target.hostname, target.port), timeout=5) as connection:
                        connection.sendall(payload)
                        self.assertEqual(connection.recv(65536), payload)
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(peers, ["127.0.0.2", "127.0.0.3"])
            self.assertEqual(payloads, [payload, payload])
            self.assertTrue(origins.closed)
            self.assertFalse(origins.thread.is_alive())
        finally:
            listener.close()
            thread.join(timeout=5)

    def test_remote_upstream_and_unbounded_client_count_are_refused(self):
        for url, count in [("http://example.com", 1), ("https://127.0.0.1", 1), ("http://127.0.0.1", 101)]:
            with self.subTest(url=url, count=count), self.assertRaises(ValueError):
                LocalOrigins(url, count)


if __name__ == "__main__":
    unittest.main()
