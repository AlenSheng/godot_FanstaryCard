"""Real loopback callback receipts must stay usable as public evidence."""
from collections import Counter
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time
import unittest

from tools.pr13_callback_isolation import Handler
from tools.pr13_public_evidence import inspect_public_bytes


class CallbackEvidenceTests(unittest.TestCase):
    def _request_receipt(self, paused):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        server.lock = threading.Lock()
        server.records, server.counts, server.case_id = [], Counter(), "public-receipt"
        gate = threading.Event()
        if not paused:
            gate.set()
        plan = {"path": "/api/v1/bootstrap", "paused": paused, "gate": gate,
                "started": False, "done": False, "account": "callback-A"}
        server.plans = [plan]
        service = threading.Thread(target=server.serve_forever, daemon=True)
        service.start()
        credential = secrets.token_urlsafe(32)
        result = {}

        def request():
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                connection.request("GET", plan["path"], headers={
                    "Accept": "application/protobuf", "Authorization": "Bearer " + credential,
                    "Proxy-Authorization": "Bearer " + credential, "Cookie": "session=" + credential,
                    "X-Trace-Id": "public-callback-trace"})
                response = connection.getresponse()
                result.update(status=response.status, media=response.getheader("Content-Type"),
                              payload_bytes=len(response.read()))
            except Exception as error:
                result["error_type"] = type(error).__name__
            finally:
                connection.close()

        client = threading.Thread(target=request, daemon=True)
        try:
            client.start()
            deadline = time.monotonic() + 2
            while not plan["started"] and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertTrue(plan["started"], "loopback request did not reach the real handler")
            if paused:
                self.assertNotIn("status", result)
            gate.set()
            client.join(timeout=3)
            self.assertFalse(client.is_alive())
            self.assertNotIn("error_type", result)
            self.assertEqual(result["status"], 200)
            self.assertEqual(result["media"], "application/protobuf")
            self.assertGreater(result["payload_bytes"], 0)
            self.assertEqual(len(server.records), 1)
            # Receiving the body precedes the handler's final receipt update.
            # Snapshot after its completion flag under the same record lock.
            deadline = time.monotonic() + 2
            while True:
                with server.lock:
                    done = plan["done"]
                    record = server.records[0].copy() if done else None
                if done:
                    break
                self.assertLess(time.monotonic(), deadline, "handler receipt did not complete")
                time.sleep(0.005)
            self.assertEqual(record["paused"], paused)
            self.assertTrue(record["gate_released"])
            self.assertEqual(record["status"], 200)
            self.assertEqual(record["request_media"], "application/protobuf")
            self.assertEqual(record["trace_id"], "public-callback-trace")
            payload = (json.dumps(record) + "\n").encode()
            inspect_public_bytes(Path("service_requests.jsonl"), payload)
            self.assertTrue(credential.encode() not in payload, "credential bytes reached request metadata")
            self.assertNotIn("authorization", record)
        finally:
            gate.set()
            client.join(timeout=3)
            server.shutdown()
            server.server_close()
            service.join(timeout=2)

    def test_immediate_request_receipt_excludes_credentials(self):
        self._request_receipt(paused=False)

    def test_delayed_request_receipt_excludes_credentials(self):
        self._request_receipt(paused=True)


if __name__ == "__main__":
    unittest.main()
