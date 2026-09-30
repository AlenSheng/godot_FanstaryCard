using System.Buffers.Binary;
using System.Net;
using System.Net.Sockets;
using System.Text;

// Copied unchanged from the frozen source test; observes PostgreSQL ReadyForQuery I.
internal sealed class CommitResponseDropProxy : IAsyncDisposable
{
    private readonly Socket _listener = new(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
    private readonly CancellationTokenSource _shutdown = new();
    private readonly Task _acceptor;
    private readonly List<Task> _connections = [];
    private readonly EndPoint _upstream;
    private readonly string _statement;
    private int _armed = 1;
    private int _dropped;

    public CommitResponseDropProxy(string upstreamDirectory, int port, string statement = "UPDATE matches SET status='Running'")
    {
        SocketDirectory = Path.Combine(Path.GetTempPath(), "fc-launch-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(SocketDirectory);
        _upstream = upstreamDirectory.StartsWith('/')
            ? new UnixDomainSocketEndPoint(Path.Combine(upstreamDirectory, $".s.PGSQL.{port}"))
            : new DnsEndPoint(upstreamDirectory, port);
        _statement = statement;
        _listener.Bind(new UnixDomainSocketEndPoint(Path.Combine(SocketDirectory, $".s.PGSQL.{port}")));
        _listener.Listen(8);
        _acceptor = AcceptAsync();
    }

    public string SocketDirectory { get; }
    public bool DroppedCommittedResponse => Volatile.Read(ref _dropped) == 1;

    private async Task AcceptAsync()
    {
        try
        {
            while (!_shutdown.IsCancellationRequested)
            {
                var client = await _listener.AcceptAsync(_shutdown.Token);
                _connections.Add(RelayAsync(client));
            }
        }
        catch (OperationCanceledException) when (_shutdown.IsCancellationRequested) { }
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
                await server.ConnectAsync(_upstream, _shutdown.Token);
                await using var frontend = new NetworkStream(client, ownsSocket: false);
                await using var backend = new NetworkStream(server, ownsSocket: false);
                var startupLength = new byte[4];
                await frontend.ReadExactlyAsync(startupLength, _shutdown.Token);
                var startup = new byte[BinaryPrimitives.ReadInt32BigEndian(startupLength) - 4];
                await frontend.ReadExactlyAsync(startup, _shutdown.Token);
                await backend.WriteAsync(startupLength, _shutdown.Token);
                await backend.WriteAsync(startup, _shutdown.Token);
                var dropResponse = 0;
                var request = ForwardAsync(frontend, backend, inspectRequest: true);
                var response = ForwardAsync(backend, frontend, inspectRequest: false);
                await Task.WhenAny(request, response);
                client.Close();
                server.Close();
                await Task.WhenAll(request, response);

                async Task ForwardAsync(Stream source, Stream destination, bool inspectRequest)
                {
                    var header = new byte[5];
                    while (true)
                    {
                        await source.ReadExactlyAsync(header, _shutdown.Token);
                        var payload = new byte[BinaryPrimitives.ReadInt32BigEndian(header.AsSpan(1)) - 4];
                        await source.ReadExactlyAsync(payload, _shutdown.Token);
                        if (inspectRequest && (header[0] == 'P' || header[0] == 'Q') &&
                            Encoding.UTF8.GetString(payload).Split('\0').Any(part =>
                                part.TrimStart().StartsWith(_statement, StringComparison.Ordinal)) &&
                            Interlocked.Exchange(ref _armed, 0) == 1)
                            Volatile.Write(ref dropResponse, 1);
                        if (!inspectRequest && Volatile.Read(ref dropResponse) == 1)
                        {
                            if (header[0] == 'Z')
                            {
                                if (payload[0] == 'I') Interlocked.Exchange(ref _dropped, 1);
                                return;
                            }
                            continue;
                        }
                        await destination.WriteAsync(header, _shutdown.Token);
                        await destination.WriteAsync(payload, _shutdown.Token);
                    }
                }
            }
            catch (Exception exception) when (exception is IOException or SocketException or OperationCanceledException or ObjectDisposedException) { }
        }
    }

    public async ValueTask DisposeAsync()
    {
        await _shutdown.CancelAsync();
        await _acceptor;
        await Task.WhenAll(_connections);
        _listener.Dispose();
        _shutdown.Dispose();
        Directory.Delete(SocketDirectory, recursive: true);
    }
}
