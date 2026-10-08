using System.Collections.Concurrent;
using System.Net.WebSockets;
using FantasyCard.Contracts.Realtime;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Hosting;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    private sealed class A05CallbackRelay : IAsyncDisposable
    {
        private readonly IHost _listener;
        private readonly HttpClient _backend;
        private readonly CancellationTokenSource _stop = new();
        private readonly TaskCompletionSource _release = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly SemaphoreSlim _send = new(1);
        private WebSocket? _client;
        private byte[]? _ready;
        private int _held;
        private volatile bool _restartWindow;
        public int Port { get; } = ReservePort();
        public TaskCompletionSource<byte[]> Held { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public ConcurrentQueue<string> Errors { get; } = new();
        public ConcurrentQueue<string> ExpectedRestartTransportFailures { get; } = new();
        public A05CallbackRelay(int port)
        {
            _backend = new() { BaseAddress = new Uri($"http://127.0.0.1:{port}"), Timeout = TimeSpan.FromSeconds(15) };
            _listener = new HostBuilder().ConfigureWebHost(web => web.UseKestrel().UseUrls($"http://127.0.0.1:{Port}")
                .Configure(app => { app.UseWebSockets(); app.Run(HandleAsync); })).Build();
            _listener.Start();
        }
        public void Release() => _release.TrySetResult();
        public void BeginRestart() => _restartWindow = true;
        public void EndRestart() => _restartWindow = false;
        public async Task DuplicateReadyAsync(CancellationToken ct)
        {
            Assert.NotNull(_ready); Assert.NotNull(_client);
            await _send.WaitAsync(ct);
            try
            {
                for (var i = 1; i <= 3; i++)
                {
                    await _client.SendAsync(_ready, WebSocketMessageType.Binary, true, ct);
                    Record("A05-duplicate-ready-delivery", new { delivery = i, bodySha256 = A05Sha(_ready), original = "unchanged actual authority frame" });
                }
            }
            finally { _send.Release(); }
        }
        private async Task HandleAsync(HttpContext context)
        {
            try
            {
                if (context.WebSockets.IsWebSocketRequest) { await WebSocketAsync(context); return; }
                var path = context.Request.Path + context.Request.QueryString;
                using var body = new MemoryStream(); await context.Request.Body.CopyToAsync(body, _stop.Token);
                using var request = new HttpRequestMessage(new HttpMethod(context.Request.Method), path);
                if (body.Length > 0 || context.Request.Method == "POST") request.Content = new ByteArrayContent(body.ToArray());
                foreach (var (name, values) in context.Request.Headers)
                {
                    if (name is "Host" or "Content-Length" or "Connection") continue;
                    if (!request.Headers.TryAddWithoutValidation(name, values.ToArray())) request.Content?.Headers.TryAddWithoutValidation(name, values.ToArray());
                }
                using var response = await _backend.SendAsync(request, _stop.Token);
                var bytes = await response.Content.ReadAsByteArrayAsync(_stop.Token);
                if (context.Request.Method == "GET" && path.StartsWith("/api/v1/settlements/", StringComparison.Ordinal) && response.IsSuccessStatusCode && Interlocked.CompareExchange(ref _held, 1, 0) == 0)
                {
                    var startedAt = DateTimeOffset.UtcNow;
                    await File.WriteAllBytesAsync(Path.Combine(EvidenceDirectory, "a05-old-callback.pb"), bytes, _stop.Token);
                    Record("A05-old-callback-held", new { path = context.Request.Path.Value, status = (int)response.StatusCode, bodySha256 = A05Sha(bytes), startedAt });
                    Held.TrySetResult(bytes); await _release.Task.WaitAsync(_stop.Token);
                    Record("A05-old-callback-released", new { path = context.Request.Path.Value, status = (int)response.StatusCode, bodySha256 = A05Sha(bytes), durationMs = (DateTimeOffset.UtcNow - startedAt).TotalMilliseconds });
                }
                context.Response.StatusCode = (int)response.StatusCode; context.Response.ContentType = response.Content.Headers.ContentType?.ToString();
                foreach (var header in response.Headers)
                    if (header.Key.Equals("Retry-After", StringComparison.OrdinalIgnoreCase)) context.Response.Headers[header.Key] = string.Join(",", header.Value);
                context.Response.ContentLength = bytes.Length; await context.Response.Body.WriteAsync(bytes, _stop.Token);
            }
            catch (Exception error) when (_stop.IsCancellationRequested || error is IOException or WebSocketException or OperationCanceledException) { context.Abort(); }
            catch (HttpRequestException error) when (_restartWindow)
            {
                ExpectedRestartTransportFailures.Enqueue(error.GetType().FullName!);
                Record("A05-expected-restart-transport-failure", new { path = context.Request.Path.Value,
                    error = error.GetType().FullName, boundary = "actual owned SIGKILL until replacement /health/ready" });
                context.Abort();
            }
            catch (Exception error) { Errors.Enqueue(error.GetType().FullName ?? "unknown"); context.Abort(); }
        }
        private async Task WebSocketAsync(HttpContext context)
        {
            using var upstream = new ClientWebSocket();
            var uri = new UriBuilder(_backend.BaseAddress!) { Scheme = "ws", Path = context.Request.Path, Query = context.Request.QueryString.Value?.TrimStart('?') }.Uri;
            await upstream.ConnectAsync(uri, _stop.Token);
            using var downstream = await context.WebSockets.AcceptWebSocketAsync(); _client = downstream;
            using var linked = CancellationTokenSource.CreateLinkedTokenSource(_stop.Token);
            var forward = PumpAsync(upstream, downstream, true, linked.Token); var reverse = PumpAsync(downstream, upstream, false, linked.Token);
            await Task.WhenAny(forward, reverse); linked.Cancel();
            try { await Task.WhenAll(forward, reverse); } catch (Exception error) when (error is OperationCanceledException or WebSocketException) { }
        }
        private async Task PumpAsync(WebSocket source, WebSocket destination, bool authority, CancellationToken ct)
        {
            var buffer = new byte[65536];
            while (source.State == WebSocketState.Open && destination.State == WebSocketState.Open)
            {
                using var message = new MemoryStream(); WebSocketReceiveResult frame;
                do
                {
                    frame = await source.ReceiveAsync(buffer, ct);
                    if (frame.MessageType == WebSocketMessageType.Close) return;
                    message.Write(buffer, 0, frame.Count);
                } while (!frame.EndOfMessage);
                var bytes = message.ToArray();
                if (authority && frame.MessageType == WebSocketMessageType.Binary)
                {
                    var decoded = RealtimeProtobufCodec.DecodeServer(bytes);
                    if (decoded.Type == "settlement.ready")
                    {
                        _ready ??= bytes;
                        await File.WriteAllBytesAsync(Path.Combine(EvidenceDirectory, "a05-original-ready.pb"), _ready, ct);
                        Record("A05-original-ready", new { decoded.EventId, decoded.Sequence, payload = decoded.Payload, bodySha256 = A05Sha(bytes) });
                    }
                }
                if (authority) await _send.WaitAsync(ct);
                try { await destination.SendAsync(bytes, frame.MessageType, true, ct); }
                finally { if (authority) _send.Release(); }
            }
        }
        public async ValueTask DisposeAsync()
        {
            _stop.Cancel(); await _listener.StopAsync(); _listener.Dispose(); _backend.Dispose(); _stop.Dispose(); _send.Dispose();
            Record("A05-callback-relay-cleanup", new { Port, errors = Errors.ToArray(), expectedRestartTransportFailures = ExpectedRestartTransportFailures.ToArray() });
        }
    }
}
