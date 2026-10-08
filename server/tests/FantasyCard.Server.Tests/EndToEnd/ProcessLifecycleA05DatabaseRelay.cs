using System.Buffers.Binary;
using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Text;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    // An owned PostgreSQL relay selects only an actual settlement INSERT
    // transaction. All business SQL/payloads originate in the frozen host.
    private sealed class A05DatabaseRelay : IAsyncDisposable
    {
        private readonly Socket _listener = new(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
        private readonly EndPoint _upstream;
        private readonly CancellationTokenSource _stop = new();
        private readonly ConcurrentBag<Task> _connections = [];
        private readonly Task _acceptor;
        private readonly string _mode;
        private volatile bool _released;
        private int _dropped;
        public string DirectoryPath { get; }
        public int Dropped => Volatile.Read(ref _dropped);

        public A05DatabaseRelay(string upstreamHost, int port, string mode)
        {
            Assert.True(IsLocalDatabase(upstreamHost), "The relay requires an owned local PostgreSQL database.");
            _mode = mode;
            DirectoryPath = Path.Combine(Path.GetTempPath(), "fc-a05-relay-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(DirectoryPath);
            _upstream = upstreamHost.StartsWith('/')
                ? new UnixDomainSocketEndPoint(Path.Combine(upstreamHost, $".s.PGSQL.{port}"))
                : new DnsEndPoint(upstreamHost, port);
            _listener.Bind(new UnixDomainSocketEndPoint(Path.Combine(DirectoryPath, $".s.PGSQL.{port}")));
            _listener.Listen(16); _acceptor = AcceptAsync();
            Record("A05-db-relay-upstream", new { transport = _upstream is UnixDomainSocketEndPoint ? "Unix" : "Tcp" });
        }
        public void Release() => _released = true;
        private async Task AcceptAsync()
        {
            try { while (!_stop.IsCancellationRequested) _connections.Add(RelayAsync(await _listener.AcceptAsync(_stop.Token))); }
            catch (OperationCanceledException) when (_stop.IsCancellationRequested) { }
        }
        private async Task RelayAsync(Socket client)
        {
            using (client)
            using (var server = _upstream is UnixDomainSocketEndPoint
                ? new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified)
                : new Socket(SocketType.Stream, ProtocolType.Tcp))
            {
                try
                {
                    await server.ConnectAsync(_upstream, _stop.Token);
                    await using var front = new NetworkStream(client, false); await using var back = new NetworkStream(server, false);
                    var length = new byte[4]; await front.ReadExactlyAsync(length, _stop.Token);
                    var startup = new byte[BinaryPrimitives.ReadInt32BigEndian(length) - 4]; await front.ReadExactlyAsync(startup, _stop.Token);
                    await back.WriteAsync(length, _stop.Token); await back.WriteAsync(startup, _stop.Token);
                    var settlement = 0; var commitResponse = 0;
                    var request = PumpAsync(front, back, true); var response = PumpAsync(back, front, false);
                    await Task.WhenAny(request, response); client.Close(); server.Close();
                    await Task.WhenAll(request, response);
                    async Task PumpAsync(Stream source, Stream destination, bool frontend)
                    {
                        var header = new byte[5];
                        while (true)
                        {
                            await source.ReadExactlyAsync(header, _stop.Token);
                            var frameLength = BinaryPrimitives.ReadInt32BigEndian(header.AsSpan(1));
                            Assert.InRange(frameLength, 4, 8 * 1024 * 1024);
                            var payload = new byte[frameLength - 4]; await source.ReadExactlyAsync(payload, _stop.Token);
                            if (frontend && header[0] is (byte)'P' or (byte)'Q')
                            {
                                var statements = Encoding.UTF8.GetString(payload).Split('\0');
                                if (statements.Any(sql => sql.TrimStart().StartsWith("INSERT INTO match_settlements(", StringComparison.Ordinal)))
                                {
                                    if (_mode == "precommit" && !_released)
                                    {
                                        Interlocked.Increment(ref _dropped);
                                        Record("A05-db-precommit-drop", new { boundary = "settlement INSERT Parse/Query not forwarded; real open transaction disconnected", count = Dropped });
                                        return;
                                    }
                                    Volatile.Write(ref settlement, 1);
                                }
                                if (_mode == "committed-response-loss" && Volatile.Read(ref settlement) == 1 &&
                                    statements.Any(sql => sql.Trim().Equals("COMMIT", StringComparison.OrdinalIgnoreCase)) && Volatile.Read(ref _dropped) == 0)
                                    Volatile.Write(ref commitResponse, 1);
                            }
                            if (!frontend && Volatile.Read(ref commitResponse) == 1)
                            {
                                if (header[0] == 'Z')
                                {
                                    Assert.Equal((byte)'I', Assert.Single(payload));
                                    Interlocked.Increment(ref _dropped);
                                    Record("A05-db-committed-response-drop", new { boundary = "backend COMMIT completed; ReadyForQuery Idle withheld from actual host", count = Dropped });
                                    return;
                                }
                                continue;
                            }
                            await destination.WriteAsync(header, _stop.Token); await destination.WriteAsync(payload, _stop.Token);
                        }
                    }
                }
                catch (Exception error) when (error is IOException or SocketException or OperationCanceledException or ObjectDisposedException) { }
            }
        }
        public async ValueTask DisposeAsync()
        {
            await _stop.CancelAsync(); await _acceptor; await Task.WhenAll(_connections);
            _listener.Dispose(); _stop.Dispose(); Directory.Delete(DirectoryPath, true);
            Record("A05-db-relay-cleanup", new { _mode, DirectoryPath, Dropped, removed = !Directory.Exists(DirectoryPath) });
        }
    }
}
