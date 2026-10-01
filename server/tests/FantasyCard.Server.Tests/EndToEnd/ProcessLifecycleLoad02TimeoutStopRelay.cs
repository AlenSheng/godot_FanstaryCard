using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Security.Cryptography;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Hosting;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    private sealed record Load02RelayRequest(string Method, string Path, int Attempt, long ReceivedTick,
        string KeySha256, string BodySha256, bool Forwarded, int? BackendStatus, string? ResponseSha256, string Effect);

    private sealed class Load02Relay : IAsyncDisposable
    {
        private readonly IHost _listener;
        private readonly HttpClient _backend;
        private readonly CancellationTokenSource _stop = new();
        private readonly string _mode;
        private readonly string _report;
        private int _prepareAttempts;
        private int _ackAttempts;
        private readonly TaskCompletionSource _gate = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource _release = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public Task Gate => _gate.Task;
        public int Port { get; } = ReservePort();
        public ConcurrentQueue<Load02RelayRequest> Requests { get; } = new();
        public ConcurrentQueue<string> Errors { get; } = new();
        public object? Authority { get; private set; }
        public Load02Relay(int backendPort, string mode, string report)
        {
            _mode = mode; _report = report;
            _backend = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{backendPort}"), Timeout = TimeSpan.FromSeconds(15) };
            _listener = new HostBuilder().ConfigureWebHost(web => web.UseKestrel().UseUrls($"http://127.0.0.1:{Port}")
                .Configure(app => { app.UseWebSockets(); app.Run(HandleAsync); })).Build();
            _listener.Start();
        }
        public void Release() => _release.TrySetResult();
        private async Task HoldAsync()
        {
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(_stop.Token);
            deadline.CancelAfter(TimeSpan.FromSeconds(8));
            await _release.Task.WaitAsync(deadline.Token);
        }
        private async Task HandleAsync(HttpContext context)
        {
            try
            {
                if (context.WebSockets.IsWebSocketRequest) { await BridgeAsync(context); return; }
                var path = context.Request.Path + context.Request.QueryString;
                var method = context.Request.Method;
                var received = System.Diagnostics.Stopwatch.GetTimestamp();
                using var body = new MemoryStream(); await context.Request.Body.CopyToAsync(body, _stop.Token);
                var bytes = body.ToArray();
                var prepare = method == "POST" && path == "/api/v1/preparations";
                var ack = method == "POST" && path.StartsWith("/api/v1/settlements/", StringComparison.Ordinal) && path.EndsWith("/acknowledge", StringComparison.Ordinal);
                var attempt = prepare ? Interlocked.Increment(ref _prepareAttempts) : ack ? Interlocked.Increment(ref _ackAttempts) : 0;
                var key = Hash(System.Text.Encoding.UTF8.GetBytes(context.Request.Headers["Idempotency-Key"].ToString()));
                if (_mode == "timeout-before-stop" && prepare)
                {
                    Requests.Enqueue(new(method, path, attempt, received, key, Hash(bytes), false, null, null, "no_forward_no_response_until_original_timeout"));
                    using var wait = CancellationTokenSource.CreateLinkedTokenSource(_stop.Token, context.RequestAborted);
                    wait.CancelAfter(TimeSpan.FromSeconds(40));
                    try { await Task.Delay(Timeout.InfiniteTimeSpan, wait.Token); } catch (OperationCanceledException) { }
                    context.Abort(); return;
                }
                if (_mode == "normal-wait-stop" && ack && attempt == 1)
                {
                    Requests.Enqueue(new(method, path, attempt, received, key, Hash(bytes), false, null, null, "ACK_precommit_gate"));
                    _gate.TrySetResult(); await HoldAsync();
                }
                using var request = new HttpRequestMessage(new HttpMethod(method), path);
                if (bytes.Length > 0 || method == "POST") request.Content = new ByteArrayContent(bytes);
                foreach (var (name, values) in context.Request.Headers)
                {
                    if (name.Equals("Host", StringComparison.OrdinalIgnoreCase) || name.Equals("Content-Length", StringComparison.OrdinalIgnoreCase) || name.Equals("Connection", StringComparison.OrdinalIgnoreCase)) continue;
                    if (!request.Headers.TryAddWithoutValidation(name, values.ToArray())) request.Content?.Headers.TryAddWithoutValidation(name, values.ToArray());
                }
                using var response = await _backend.SendAsync(request, _stop.Token);
                var responseBytes = await response.Content.ReadAsByteArrayAsync(_stop.Token);
                var drop = _mode == "committed-unknown-stop" && ack && attempt <= 3;
                var holdAuthority = method == "GET" && path == "/api/v1/bootstrap" && !_release.Task.IsCompleted &&
                    (_mode == "timeout-before-stop" && File.Exists(_report + ".first-failure.json") || _mode == "committed-unknown-stop" && Volatile.Read(ref _ackAttempts) >= 3);
                Requests.Enqueue(new(method, path, attempt, received, key, Hash(bytes), true, (int)response.StatusCode,
                    Hash(responseBytes), drop ? "backend_reply_dropped" : holdAuthority ? "authoritative_bootstrap_held" : "forwarded"));
                if (drop) { context.Abort(); return; }
                if (holdAuthority)
                {
                    Assert.Equal(200, (int)response.StatusCode);
                    var authority = Wire.BootstrapResponse.Parser.ParseFrom(responseBytes);
                    Authority = new { authority.ConfigVersion, activePreparation = authority.ActivePreparation?.PreparationId,
                        unfinishedMatch = authority.UnfinishedMatch?.MatchId, unfinishedSettlement = authority.UnfinishedSettlement?.SettlementId,
                        responseBytes = responseBytes.Length, responseSha256 = Hash(responseBytes), backendCompletedTick = System.Diagnostics.Stopwatch.GetTimestamp() };
                    _gate.TrySetResult(); await HoldAsync();
                }
                context.Response.StatusCode = (int)response.StatusCode;
                context.Response.ContentType = response.Content.Headers.ContentType?.ToString();
                foreach (var header in response.Headers)
                    if (header.Key.Equals("Retry-After", StringComparison.OrdinalIgnoreCase)) context.Response.Headers[header.Key] = string.Join(",", header.Value);
                // 204/304/HEAD forbid bodies, including a Content-Length:0 write.
                if ((int)response.StatusCode is not (204 or 304) && method != "HEAD")
                { context.Response.ContentLength = responseBytes.Length; await context.Response.Body.WriteAsync(responseBytes, _stop.Token); }
            }
            catch (Exception error) when (_stop.IsCancellationRequested || context.RequestAborted.IsCancellationRequested || error is WebSocketException or IOException) { context.Abort(); }
            catch (Exception error) { Errors.Enqueue(error.ToString()); _gate.TrySetException(error); context.Abort(); }
        }
        private async Task BridgeAsync(HttpContext context)
        {
            using var upstream = new ClientWebSocket();
            var uri = new UriBuilder(_backend.BaseAddress!) { Scheme = "ws", Path = context.Request.Path, Query = context.Request.QueryString.Value?.TrimStart('?') }.Uri;
            await upstream.ConnectAsync(uri, _stop.Token);
            using var downstream = await context.WebSockets.AcceptWebSocketAsync();
            using var linked = CancellationTokenSource.CreateLinkedTokenSource(_stop.Token);
            var first = PumpAsync(upstream, downstream, linked.Token); var second = PumpAsync(downstream, upstream, linked.Token);
            await Task.WhenAny(first, second); linked.Cancel();
            try { await Task.WhenAll(first, second); } catch (Exception error) when (error is OperationCanceledException or WebSocketException) { }
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
        private static string Hash(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));
        public async ValueTask DisposeAsync()
        {
            Release(); _stop.Cancel(); await _listener.StopAsync(); _listener.Dispose(); _backend.Dispose(); _stop.Dispose();
        }
    }
}
