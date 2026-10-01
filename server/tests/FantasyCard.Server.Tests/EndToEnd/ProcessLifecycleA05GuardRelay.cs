using System.Collections.Concurrent;
using System.Net.WebSockets;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Hosting;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    private sealed record A05GuardAckAttempt(int Index, string KeySha256, string BodySha256, bool Forwarded, bool Dropped, int? BackendStatus, string? ResponseSha256);
    private sealed record A05GuardBootstrap(int Index, int AfterAckAttempts, string? UnfinishedSettlementId, string BodySha256);
    private sealed class A05GuardRelay : IAsyncDisposable
    {
        private readonly IHost _listener;
        private readonly HttpClient _backend;
        private readonly CancellationTokenSource _stop = new();
        private readonly string _outcome;
        private readonly string _label;
        private readonly TaskCompletionSource _releaseGet = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource _releasePoll = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource _releaseAck = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int _getHeld; private int _pollHeld; private int _ackIndex; private int _bootstrapIndex;
        private volatile bool _faultReleased; private volatile bool _restart;
        public int Port { get; } = ReservePort();
        public ConcurrentQueue<A05GuardAckAttempt> Attempts { get; } = new();
        public ConcurrentQueue<A05GuardBootstrap> Bootstraps { get; } = new();
        public ConcurrentQueue<string> Errors { get; } = new();
        public ConcurrentQueue<string> ExpectedRestartTransportFailures { get; } = new();
        public TaskCompletionSource SettlementGetHeld { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource PollHeld { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource AckHeld { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public A05GuardRelay(int backendPort, string outcome, string label)
        {
            _outcome = outcome; _label = label;
            _backend = new() { BaseAddress = new Uri($"http://127.0.0.1:{backendPort}"), Timeout = TimeSpan.FromSeconds(15) };
            _listener = new HostBuilder().ConfigureWebHost(web => web.UseKestrel().UseUrls($"http://127.0.0.1:{Port}")
                .Configure(app => { app.UseWebSockets(); app.Run(HandleAsync); })).Build(); _listener.Start();
        }
        public void BeginRestart() => _restart = true;
        public void EndRestart() => _restart = false;
        public void ReleaseSettlementGet() => _releaseGet.TrySetResult();
        public void ReleasePoll() => _releasePoll.TrySetResult();
        public void ReleaseAck() => _releaseAck.TrySetResult();
        public void ReleaseFault() => _faultReleased = true;
        private async Task HandleAsync(HttpContext context)
        {
            try
            {
                if (context.WebSockets.IsWebSocketRequest) { await BridgeAsync(context); return; }
                var path = context.Request.Path.Value!;
                using var body = new MemoryStream(); await context.Request.Body.CopyToAsync(body, _stop.Token);
                var bytes = body.ToArray();
                var ack = path.EndsWith("/acknowledge", StringComparison.Ordinal);
                var index = ack ? Interlocked.Increment(ref _ackIndex) : 0;
                var keyHash = A05Sha(context.Request.Headers["Idempotency-Key"].ToString());
                if (ack && index == 1)
                {
                    Record("A05-guard-ACK-held", new { label = _label, path, bodySha256 = A05Sha(bytes), keySha256 = keyHash });
                    AckHeld.TrySetResult(); await _releaseAck.Task.WaitAsync(_stop.Token);
                }
                var drop = ack && !_faultReleased && _outcome != "success";
                if (drop && _outcome == "uncommitted-loss")
                {
                    Attempts.Enqueue(new(index, keyHash, A05Sha(bytes), false, true, null, null));
                    Record("A05-guard-ACK-unforwarded", new { label = _label, index, keyHash, bodySha256 = A05Sha(bytes) });
                    context.Abort(); return;
                }
                using var request = new HttpRequestMessage(new HttpMethod(context.Request.Method), context.Request.Path + context.Request.QueryString);
                if (bytes.Length > 0 || context.Request.Method == "POST") request.Content = new ByteArrayContent(bytes);
                foreach (var (name, values) in context.Request.Headers)
                {
                    if (name is "Host" or "Content-Length" or "Connection") continue;
                    if (!request.Headers.TryAddWithoutValidation(name, values.ToArray())) request.Content?.Headers.TryAddWithoutValidation(name, values.ToArray());
                }
                using var response = await _backend.SendAsync(request, _stop.Token);
                var payload = await response.Content.ReadAsByteArrayAsync(_stop.Token);
                if (ack)
                {
                    Attempts.Enqueue(new(index, keyHash, A05Sha(bytes), true, drop, (int)response.StatusCode, A05Sha(payload)));
                    Record("A05-guard-ACK-backend", new { label = _label, index, status = (int)response.StatusCode, drop, bodySha256 = A05Sha(payload) });
                    if (drop) { context.Abort(); return; }
                }
                if (response.IsSuccessStatusCode && context.Request.Method == "GET" && path.StartsWith("/api/v1/settlements/", StringComparison.Ordinal) && Interlocked.CompareExchange(ref _getHeld, 1, 0) == 0)
                {
                    await File.WriteAllBytesAsync(Path.Combine(EvidenceDirectory, _label + "-settlement-get.pb"), payload, _stop.Token);
                    Record("A05-guard-GET-held", new { label = _label, path, bodySha256 = A05Sha(payload) });
                    SettlementGetHeld.TrySetResult(); await _releaseGet.Task.WaitAsync(_stop.Token);
                }
                if (response.IsSuccessStatusCode && path == "/api/v1/bootstrap")
                {
                    var ready = Wire.BootstrapResponse.Parser.ParseFrom(payload).UnfinishedSettlement;
                    var bootIndex = Interlocked.Increment(ref _bootstrapIndex);
                    Bootstraps.Enqueue(new(bootIndex, Volatile.Read(ref _ackIndex), ready?.SettlementId, A05Sha(payload)));
                    await File.WriteAllBytesAsync(Path.Combine(EvidenceDirectory, _label + "-bootstrap-" + bootIndex + ".pb"), payload, _stop.Token);
                    Record("A05-guard-bootstrap-authority", new { label = _label, bootIndex, afterAckAttempts = Volatile.Read(ref _ackIndex), ready = ready?.SettlementId, bodySha256 = A05Sha(payload) });
                    if (ready is not null && Interlocked.CompareExchange(ref _pollHeld, 1, 0) == 0)
                    { PollHeld.TrySetResult(); await _releasePoll.Task.WaitAsync(_stop.Token); }
                }
                context.Response.StatusCode = (int)response.StatusCode;
                if ((int)response.StatusCode == StatusCodes.Status204NoContent)
                {
                    context.Response.ContentType = null;
                    context.Response.ContentLength = null;
                    Record("A05-guard-no-content-forwarded", new { label = _label, path, method = context.Request.Method, status = 204, backendBytes = payload.Length });
                    return;
                }
                context.Response.ContentType = response.Content.Headers.ContentType?.ToString();
                context.Response.ContentLength = payload.Length; await context.Response.Body.WriteAsync(payload, _stop.Token);
            }
            catch (Exception error) when (_stop.IsCancellationRequested || error is IOException or OperationCanceledException or WebSocketException) { context.Abort(); }
            catch (HttpRequestException error) when (_restart)
            { ExpectedRestartTransportFailures.Enqueue(error.GetType().Name); context.Abort(); }
            catch (Exception error) { Errors.Enqueue(error.ToString()); context.Abort(); }
        }
        private async Task BridgeAsync(HttpContext context)
        {
            using var upstream = new ClientWebSocket();
            var uri = new UriBuilder(_backend.BaseAddress!) { Scheme = "ws", Path = context.Request.Path, Query = context.Request.QueryString.Value?.TrimStart('?') }.Uri;
            await upstream.ConnectAsync(uri, _stop.Token); using var downstream = await context.WebSockets.AcceptWebSocketAsync();
            using var linked = CancellationTokenSource.CreateLinkedTokenSource(_stop.Token);
            var forward = PumpAsync(upstream, downstream, linked.Token); var reverse = PumpAsync(downstream, upstream, linked.Token);
            await Task.WhenAny(forward, reverse); linked.Cancel();
            try { await Task.WhenAll(forward, reverse); } catch (Exception error) when (error is OperationCanceledException or WebSocketException) { }
        }
        private static async Task PumpAsync(WebSocket source, WebSocket destination, CancellationToken ct)
        {
            var buffer = new byte[65536];
            while (source.State == WebSocketState.Open && destination.State == WebSocketState.Open)
            {
                var read = await source.ReceiveAsync(new ArraySegment<byte>(buffer), ct);
                if (read.MessageType == WebSocketMessageType.Close) break;
                await destination.SendAsync(new ArraySegment<byte>(buffer, 0, read.Count), read.MessageType, read.EndOfMessage, ct);
            }
        }
        public async ValueTask DisposeAsync()
        { _stop.Cancel(); await _listener.StopAsync(); _listener.Dispose(); _backend.Dispose(); _stop.Dispose(); }
    }
}
