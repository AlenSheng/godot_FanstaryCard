"""Owned loopback relay: discard real WebSocket PB frames, never encode events.

HTTP (including authentication) is forwarded without logging headers or bodies.
Only selected gameplay envelopes are retained as immutable binary evidence.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time


def fields(packet):
    result = {}
    cursor = 0

    def varint():
        nonlocal cursor
        value = 0
        for shift in range(0, 70, 7):
            byte = packet[cursor]
            cursor += 1
            value |= (byte & 127) << shift
            if not byte & 128:
                return value
        raise ValueError("Invalid Protobuf varint")

    while cursor < len(packet):
        tag = varint()
        field, wire = tag >> 3, tag & 7
        if wire == 0:
            value = varint()
        elif wire == 2:
            size = varint()
            value = packet[cursor:cursor + size]
            if len(value) != size:
                raise ValueError("Truncated Protobuf field")
            cursor += size
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            value = packet[cursor:cursor + size]
            cursor += size
        else:
            raise ValueError("Unsupported Protobuf wire type")
        result[field] = value
    return result


async def frame(reader):
    prefix = await reader.readexactly(2)
    size = prefix[1] & 127
    extra = b""
    if size in (126, 127):
        extra = await reader.readexactly(2 if size == 126 else 8)
        size = int.from_bytes(extra, "big")
    if size > 2 * 1024 * 1024:
        raise ValueError("Fixture frame bound exceeded")
    mask = await reader.readexactly(4) if prefix[1] & 128 else b""
    body = await reader.readexactly(size)
    payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(body)) if mask else body
    return prefix + extra + mask + body, payload, prefix[0] & 15, bool(prefix[0] & 128)


class Relay:
    def __init__(self, args):
        self.args = args
        self.directory = Path(args.evidence)
        self.directory.mkdir()
        self.ordinal = 0
        self.connection = 0
        self.dropped = {}
        self.writers = set()
        self.tasks = set()
        self.fault_complete = False

    def record(self, event, **data):
        entry = {"event": event, "at_monotonic_ms": int(time.monotonic() * 1000), **data}
        with (self.directory / "trace.jsonl").open("a") as output:
            output.write(json.dumps(entry) + "\n")
        return entry

    def snapshot(self):
        query = "SELECT coalesce(json_agg(json_build_object('match_id',m.match_id,'room_id',m.room_id,'status',m.status,'player_state',p.state,'ready_deadline_seconds',extract(epoch from m.ready_deadline-m.created_at))), '[]'::json) FROM matches m JOIN match_players p ON p.match_id=m.match_id WHERE NOT p.is_bot"
        result = subprocess.run(["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-d", self.args.database, "-c", query], capture_output=True, timeout=15)
        if result.returncode:
            raise RuntimeError("Owned proxy boundary SQL failed")
        return json.loads(result.stdout)

    async def pipe(self, reader, writer):
        while chunk := await reader.read(65536):
            writer.write(chunk)
            await writer.drain()

    async def frames(self, reader, writer, direction, connection):
        retained = {"room.ready", "room.ready_required", "room.ready_accepted", "room.started", "room.snapshot", "session.connected", "session.resume"}
        while True:
            raw, payload, opcode, final = await frame(reader)
            kind = ""
            envelope = {}
            if opcode == 2 and final:
                envelope = fields(payload)
                kind = envelope.get(2, b"").decode("utf-8")
            drop = False
            disconnect = False
            case = self.args.case
            if direction == "client_to_server" and kind == "room.ready":
                drop = case == "ready_send_all_lost_stop" or (case == "ready_send_lost_reconnect" and not self.fault_complete)
                disconnect = drop and case == "ready_send_lost_reconnect"
            if direction == "server_to_client":
                if kind == "room.ready_accepted":
                    drop = (case == "ready_accepted_lost_resume" and not self.dropped.get(kind)) or (case == "ready_replies_lost_reconnect" and not self.fault_complete)
                if kind == "room.started" and case in ("ready_started_lost_reconnect", "ready_replies_lost_reconnect") and not self.fault_complete:
                    drop = disconnect = True
            if kind in retained:
                self.ordinal += 1
                filename = f"{self.ordinal:04d}-{direction}-{kind}.pb"
                (self.directory / filename).write_bytes(payload)
                data = {"kind": kind, "direction": direction, "connection": connection, "ordinal": self.ordinal,
                        "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "file": filename,
                        "sequence": envelope.get(6, 0) if direction == "server_to_client" else None,
                        "request_id": envelope.get(8 if direction == "server_to_client" else 3, b"").decode("utf-8")}
                if drop:
                    self.dropped[kind] = self.dropped.get(kind, 0) + 1
                    data["postgres_at_drop"] = self.snapshot()
                    data["drop_no"] = self.dropped[kind]
                self.record("frame_dropped" if drop else "frame_forwarded", **data)
                if case == "ready_send_all_lost_stop" and self.dropped.get("room.ready", 0) == 3:
                    (self.directory / "request-stop.json").write_text(json.dumps({"boundary": "three_actual_ready_frames_dropped"}) + "\n")
            if disconnect:
                self.fault_complete = True
                self.record("fault_disconnect", connection=connection, kind=kind)
                return
            if not drop:
                writer.write(raw)
                await writer.drain()

    async def accept(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        upstream = None
        pipes = []
        self.writers.add(writer)
        try:
            header = await reader.readuntil(b"\r\n\r\n")
            upstream_reader, upstream = await asyncio.open_connection("127.0.0.1", self.args.upstream_port)
            self.writers.add(upstream)
            upstream.write(header)
            await upstream.drain()
            is_websocket = b"upgrade: websocket" in header.lower()
            if is_websocket:
                response = await upstream_reader.readuntil(b"\r\n\r\n")
                writer.write(response)
                await writer.drain()
                if not response.startswith(b"HTTP/1.1 101"):
                    return
                self.connection += 1
                connection = self.connection
                self.record("websocket_connected", connection=connection)
                pipes = [asyncio.create_task(self.frames(reader, upstream, "client_to_server", connection)),
                         asyncio.create_task(self.frames(upstream_reader, writer, "server_to_client", connection))]
            else:
                pipes = [asyncio.create_task(self.pipe(reader, upstream)), asyncio.create_task(self.pipe(upstream_reader, writer))]
            done, pending = await asyncio.wait(pipes, return_when=asyncio.FIRST_COMPLETED)
            for pipe in pending:
                pipe.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for pipe in done:
                pipe.result()
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            pass
        except Exception as exc:
            self.record("proxy_error", reason=str(exc))
        finally:
            for pipe in pipes:
                if not pipe.done():
                    pipe.cancel()
            await asyncio.gather(*pipes, return_exceptions=True)
            for peer in (writer, upstream):
                if peer is not None:
                    peer.close()
                    self.writers.discard(peer)
            self.tasks.discard(task)

    async def run(self):
        shutdown = asyncio.Event()
        loop = asyncio.get_running_loop()
        for name in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(name, shutdown.set)
        server = await asyncio.start_server(self.accept, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        self.record("proxy_ready", listen_host="127.0.0.1", port=port, upstream_host="127.0.0.1", upstream_port=self.args.upstream_port)
        (self.directory / "ready.json").write_text(json.dumps({"port": port}) + "\n")
        await shutdown.wait()
        server.close()
        await server.wait_closed()
        for peer in tuple(self.writers):
            peer.close()
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        self.record("proxy_stopped", remaining_connections=len(self.writers), synthetic_envelopes=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-port", required=True, type=int)
    parser.add_argument("--case", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--database", required=True)
    asyncio.run(Relay(parser.parse_args()).run())


if __name__ == "__main__":
    main()
