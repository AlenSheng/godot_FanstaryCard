"""Owned loopback TCP origins with real, distinct client source addresses.

The relay forwards unchanged bytes, including WebSocket frames. It never adds
forwarding headers or changes server limits. Each connection and buffer is bounded.
"""
import asyncio
import ipaddress
import threading
from urllib.parse import urlparse


class LocalOrigins:
    def __init__(self, upstream, clients, *, connections_per_client=16):
        target = urlparse(upstream)
        if (target.scheme != "http" or target.hostname != "127.0.0.1" or target.path not in ("", "/")
                or target.username or target.password or target.query or target.fragment):
            raise ValueError("Owned diagnostic origins require an HTTP loopback upstream")
        if type(clients) is not int or not 1 <= clients <= 100:
            raise ValueError("Local client origins are bounded to 1-100")
        if type(connections_per_client) is not int or not 1 <= connections_per_client <= 32:
            raise ValueError("Per-client connection budget must be 1-32")
        self.host, self.port = target.hostname, target.port or 80
        self.clients, self.limit = clients, connections_per_client
        self.origins, self.records, self.errors = [], [], []
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True, name="pr13-owned-origins")
        self.servers, self.tasks = [], set()
        self.active = [0] * clients
        self.closed = False

    def __enter__(self):
        self.thread.start()
        try:
            asyncio.run_coroutine_threadsafe(self._start(), self.loop).result(timeout=10)
        except BaseException:
            self.close()
            raise
        return self

    async def _start(self):
        for index in range(self.clients):
            source = str(ipaddress.ip_address("127.0.0.2") + index)
            server = await asyncio.start_server(lambda reader, writer, slot=index: self._accept(reader, writer, slot), "127.0.0.1", 0)
            self.servers.append(server)
            port = server.sockets[0].getsockname()[1]
            self.origins.append(f"http://127.0.0.1:{port}")
            self.records.append({"slot": index, "proxy_port": port, "upstream_source_ip": source,
                                 "upstream": f"http://{self.host}:{self.port}", "headers_modified": False})

    def _accept(self, reader, writer, index):
        task = self.loop.create_task(self._relay(reader, writer, index))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _relay(self, reader, writer, index):
        if self.active[index] >= self.limit:
            self.errors.append({"slot": index, "reason": "connection_budget_exceeded"})
            writer.close()
            await writer.wait_closed()
            return
        self.active[index] += 1
        back_writer = None
        transfers = []
        try:
            back_reader, back_writer = await asyncio.wait_for(asyncio.open_connection(
                self.host, self.port, local_addr=(self.records[index]["upstream_source_ip"], 0)), timeout=5)

            async def pump(source, target):
                while True:
                    data = await asyncio.wait_for(source.read(65536), timeout=120)
                    if not data:
                        return
                    target.write(data)
                    await target.drain()

            transfers = [self.loop.create_task(pump(reader, back_writer)), self.loop.create_task(pump(back_reader, writer))]
            await asyncio.wait(transfers, return_when=asyncio.FIRST_COMPLETED)
        except (OSError, asyncio.TimeoutError) as error:
            self.errors.append({"slot": index, "reason": type(error).__name__})
        finally:
            for task in transfers:
                task.cancel()
            if transfers:
                await asyncio.gather(*transfers, return_exceptions=True)
            writer.close()
            if back_writer is not None:
                back_writer.close()
            try:
                await asyncio.wait_for(asyncio.gather(writer.wait_closed(), *( [back_writer.wait_closed()] if back_writer is not None else []), return_exceptions=True), timeout=2)
            except asyncio.TimeoutError:
                self.errors.append({"slot": index, "reason": "close_deadline"})
            self.active[index] -= 1

    async def _close(self):
        for server in self.servers:
            server.close()
        await asyncio.gather(*(server.wait_closed() for server in self.servers))
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.thread.is_alive():
            try:
                asyncio.run_coroutine_threadsafe(self._close(), self.loop).result(timeout=10)
            finally:
                self.loop.call_soon_threadsafe(self.loop.stop)
                self.thread.join(timeout=5)
                if self.thread.is_alive():
                    raise RuntimeError("Owned network thread did not stop")
        self.loop.close()

    def __exit__(self, *args):
        self.close()
