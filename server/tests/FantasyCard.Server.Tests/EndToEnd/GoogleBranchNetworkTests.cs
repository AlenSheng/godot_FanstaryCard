using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Runtime.CompilerServices;
using FantasyCard.Contracts.Http;
using FantasyCard.Server.Tests.Persistence;
using Google.Protobuf;
using Wire = FantasyCard.Contracts.Http.V1;
using RealtimeWire = FantasyCard.Contracts.Wire.Realtime.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed class GoogleBranchNetworkTests
{
    public static bool HasTestDatabase => !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES"));

    [Fact(Skip = "Requires an owned PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Actual_server_accepts_the_legacy_ticket_alias_once_and_keeps_binary_session_frames()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(60));
        var ct = timeout.Token;
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        var start = new ProcessStartInfo("dotnet")
        {
            WorkingDirectory = ServerSource(), UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardOutput = true, RedirectStandardError = true
        };
        start.ArgumentList.Add(Environment.GetEnvironmentVariable("FANTASYCARD_E2E_SERVER_DLL")
            ?? throw new InvalidOperationException("An exact built server assembly is required."));
        start.Environment["ASPNETCORE_ENVIRONMENT"] = "Development";
        start.Environment["ASPNETCORE_URLS"] = $"http://127.0.0.1:{port}";
        start.Environment["ConnectionStrings__Postgres"] = database.ConnectionString;
        start.Environment["Identity__EnableLocalAuth"] = "true";
        start.Environment["Identity__Google__Enabled"] = "false";
        start.Environment["ProtobufHttp__AllowLegacyJson"] = "false";
        start.Environment["Realtime__AllowLegacyAccessTokenQuery"] = "false";
        start.Environment.Remove("OTEL_EXPORTER_OTLP_ENDPOINT");
        var evidence = Environment.GetEnvironmentVariable("FANTASYCARD_BRANCH_TEST_EVIDENCE")
            ?? throw new InvalidOperationException("Owned process evidence directory is required.");
        Directory.CreateDirectory(evidence);
        using var process = Process.Start(start) ?? throw new InvalidOperationException("Owned test server did not start.");
        var stdout = process.StandardOutput.ReadToEndAsync(CancellationToken.None);
        var stderr = process.StandardError.ReadToEndAsync(CancellationToken.None);
        try
        {
            using var client = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}") };
            client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
            while (true)
            {
                Assert.False(process.HasExited, "Owned server exited before readiness; see retained process evidence.");
                try
                {
                    using var ready = await client.GetAsync("/health/ready", ct);
                    if (ready.StatusCode == HttpStatusCode.OK) break;
                }
                catch (HttpRequestException) { }
                await Task.Delay(100, ct);
            }
            using var body = new ByteArrayContent(new Wire.LocalSignInRequest { DeviceId = "branch-network-device", DisplayName = "Branch network" }.ToByteArray());
            body.Headers.ContentType = new MediaTypeHeaderValue(HttpProtocolRegistry.MediaType);
            using var login = await client.PostAsync("/api/v1/auth/local", body, ct);
            Assert.Equal(HttpStatusCode.OK, login.StatusCode);
            var identity = Wire.LocalSignInResponse.Parser.ParseFrom(await login.Content.ReadAsByteArrayAsync(ct));
            client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", identity.AccessToken);
            using var empty = new ByteArrayContent([]);
            empty.Headers.ContentType = new MediaTypeHeaderValue(HttpProtocolRegistry.MediaType);
            using var response = await client.PostAsync("/api/v1/auth/ws-ticket", empty, ct);
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            var ticket = Wire.RealtimeTicketResponse.Parser.ParseFrom(await response.Content.ReadAsByteArrayAsync(ct));
            var uri = new Uri($"ws://127.0.0.1:{port}/ws/v1/session?ws_ticket={Uri.EscapeDataString(ticket.Ticket)}");
            using var socket = new ClientWebSocket();
            await socket.ConnectAsync(uri, ct);
            var buffer = new byte[16384];
            var received = await socket.ReceiveAsync(buffer.AsMemory(), ct);
            Assert.Equal(WebSocketMessageType.Binary, received.MessageType);
            Assert.True(received.EndOfMessage);
            Assert.Equal("session.connected", RealtimeWire.ServerEnvelope.Parser.ParseFrom(buffer.AsSpan(0, received.Count)).Type);
            using var replay = new ClientWebSocket();
            await Assert.ThrowsAsync<WebSocketException>(() => replay.ConnectAsync(uri, ct));
            await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "finished", ct);
        }
        finally
        {
            if (!process.HasExited) process.Kill(entireProcessTree: true);
            await process.WaitForExitAsync(CancellationToken.None);
            var prefix = Path.Combine(evidence, Guid.NewGuid().ToString("N"));
            await File.WriteAllTextAsync(prefix + ".stdout.log", await stdout, CancellationToken.None);
            await File.WriteAllTextAsync(prefix + ".stderr.log", await stderr, CancellationToken.None);
        }
    }

    private static string ServerSource([CallerFilePath] string source = "") =>
        Path.GetFullPath(Path.Combine(Path.GetDirectoryName(source)!, "..", "..", "..", "src", "FantasyCard.Server"));
}
