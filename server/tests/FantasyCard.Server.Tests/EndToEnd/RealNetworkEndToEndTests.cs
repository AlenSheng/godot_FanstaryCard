using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Contracts.Bootstrap;
using FantasyCard.Contracts.Identity;
using FantasyCard.Contracts.Progression;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Tests.Persistence;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed class RealNetworkEndToEndTests
{
    private static readonly JsonSerializerOptions WebJson = CreateWebJson();

    public static bool HasTestDatabase => !string.IsNullOrWhiteSpace(
        Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES"));

    private static JsonSerializerOptions CreateWebJson()
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        options.Converters.Add(new JsonStringEnumConverter());
        return options;
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Real_process_supports_login_bootstrap_and_websocket_ping()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: false);
        var cancellationToken = TestContext.Current.CancellationToken;
        var port = ReserveLoopbackPort();
        await using var server = StartServer(database.ConnectionString, port);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(60));
        using var client = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}") };

        await server.WaitUntilReadyAsync(client, timeout.Token);

        using var signInResponse = await client.PostAsJsonAsync(
            "/api/v1/auth/local",
            new LocalSignInRequest($"network-e2e-{Guid.NewGuid():N}", "Network E2E"),
            WebJson,
            timeout.Token);
        signInResponse.EnsureSuccessStatusCode();
        var signIn = Assert.IsType<LocalSignInResponse>(
            await signInResponse.Content.ReadFromJsonAsync<LocalSignInResponse>(WebJson, timeout.Token));
        Assert.NotEqual(Guid.Empty, signIn.Player.UserId);
        Assert.False(string.IsNullOrWhiteSpace(signIn.AccessToken));

        using var bootstrapRequest = new HttpRequestMessage(HttpMethod.Get, "/api/v1/bootstrap");
        bootstrapRequest.Headers.Authorization = new AuthenticationHeaderValue("Bearer", signIn.AccessToken);
        using var bootstrapResponse = await client.SendAsync(bootstrapRequest, timeout.Token);
        bootstrapResponse.EnsureSuccessStatusCode();
        var bootstrap = Assert.IsType<BootstrapResponse>(
            await bootstrapResponse.Content.ReadFromJsonAsync<BootstrapResponse>(WebJson, timeout.Token));
        Assert.Equal(signIn.Player.UserId, bootstrap.Player.UserId);
        Assert.False(string.IsNullOrWhiteSpace(bootstrap.ConfigVersion));
        Assert.Equal(3, bootstrap.ClassWeapons.Count);
        Assert.Equal(3, bootstrap.Decks.Count);

        await using (var gold = database.DataSource.CreateCommand(
            "UPDATE player_wallets SET gold=1000 WHERE player_id=$1"))
        {
            gold.Parameters.AddWithValue(signIn.Player.UserId);
            Assert.Equal(1, await gold.ExecuteNonQueryAsync(timeout.Token));
        }
        using var shopRequest = new HttpRequestMessage(HttpMethod.Get, "/api/v1/shop/");
        shopRequest.Headers.Authorization = new AuthenticationHeaderValue("Bearer", signIn.AccessToken);
        using var shopResponse = await client.SendAsync(shopRequest, timeout.Token);
        shopResponse.EnsureSuccessStatusCode();
        var shop = Assert.IsType<ShopResponse>(
            await shopResponse.Content.ReadFromJsonAsync<ShopResponse>(WebJson, timeout.Token));
        var dailyCard = Assert.Single(shop.Products, product => product.ProductId == "daily_card_1");
        using var dailyPayload = JsonDocument.Parse(dailyCard.Payload);
        var dailyCardId = dailyPayload.RootElement.GetProperty("cardId").GetString()!;
        var copiesBefore = await database.ScalarAsync<int>(
            "SELECT copy_count FROM player_cards WHERE player_id=$1 AND card_id=$2",
            signIn.Player.UserId,
            dailyCardId);

        using var purchaseRequest = new HttpRequestMessage(HttpMethod.Post, "/api/v1/shop/purchases");
        purchaseRequest.Headers.Authorization = new AuthenticationHeaderValue("Bearer", signIn.AccessToken);
        purchaseRequest.Headers.Add("Idempotency-Key", "network-daily-card");
        purchaseRequest.Content = JsonContent.Create(new PurchaseShopRequest(dailyCard.ProductId), options: WebJson);
        using var purchaseResponse = await client.SendAsync(purchaseRequest, timeout.Token);
        purchaseResponse.EnsureSuccessStatusCode();
        var purchase = Assert.IsType<ShopPurchaseResponse>(
            await purchaseResponse.Content.ReadFromJsonAsync<ShopPurchaseResponse>(WebJson, timeout.Token));
        Assert.Equal(dailyCard.ProductId, purchase.ProductId);
        Assert.Equal(1000 - dailyCard.PriceGold, purchase.GoldAfter);
        Assert.Equal(copiesBefore + 1, await database.ScalarAsync<int>(
            "SELECT copy_count FROM player_cards WHERE player_id=$1 AND card_id=$2",
            signIn.Player.UserId,
            dailyCardId));

        using var socket = new ClientWebSocket();
        var socketUri = new Uri(
            $"ws://127.0.0.1:{port}/ws/v1/session?access_token={Uri.EscapeDataString(signIn.AccessToken)}");
        await socket.ConnectAsync(socketUri, timeout.Token);

        var connected = RealtimeProtobufCodec.DecodeServer(await ReceiveBinaryAsync(socket, timeout.Token));
        Assert.Equal("session.connected", connected.Type);
        Assert.Equal(signIn.Player.UserId, Assert.IsType<SessionConnectedEventPayload>(connected.Payload).PlayerId);

        var ping = RealtimeProtobufCodec.EncodeClient(new ClientCommand("ping", "network-ping", null, null));
        await socket.SendAsync(ping, WebSocketMessageType.Binary, true, timeout.Token);
        var pong = RealtimeProtobufCodec.DecodeServer(await ReceiveBinaryAsync(socket, timeout.Token));
        Assert.Equal("pong", pong.Type);
        Assert.Equal("network-ping", pong.RequestId);
        Assert.IsType<PongEventPayload>(pong.Payload);
        Assert.True(pong.Sequence > connected.Sequence);

        await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "test complete", timeout.Token);
    }

    private static int ReserveLoopbackPort()
    {
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }

    private static NetworkServerProcess StartServer(string connectionString, int port)
    {
        var serverProjectDirectory = FindServerProjectDirectory();
        var serverDll = Path.Combine(
            serverProjectDirectory,
            "bin",
            "Release",
            "net10.0",
            "FantasyCard.Server.dll");
        Assert.True(File.Exists(serverDll), $"Server assembly was not built: {serverDll}");

        var startInfo = new ProcessStartInfo
        {
            FileName = "dotnet",
            WorkingDirectory = serverProjectDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        startInfo.ArgumentList.Add(serverDll);
        startInfo.Environment["ASPNETCORE_ENVIRONMENT"] = "Development";
        startInfo.Environment["ASPNETCORE_URLS"] = $"http://127.0.0.1:{port}";
        startInfo.Environment["ConnectionStrings__Postgres"] = connectionString;
        startInfo.Environment["Identity__EnableLocalAuth"] = "true";
        startInfo.Environment.Remove("OTEL_EXPORTER_OTLP_ENDPOINT");
        return NetworkServerProcess.Start(startInfo);
    }

    private static string FindServerProjectDirectory()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            var candidate = Path.Combine(directory.FullName, "src", "FantasyCard.Server");
            if (File.Exists(Path.Combine(candidate, "FantasyCard.Server.csproj"))) return candidate;
            directory = directory.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate the FantasyCard.Server project directory.");
    }

    private static async Task<byte[]> ReceiveBinaryAsync(
        ClientWebSocket socket,
        CancellationToken cancellationToken)
    {
        var buffer = new byte[16 * 1024];
        var count = 0;
        while (true)
        {
            var result = await socket.ReceiveAsync(buffer.AsMemory(count), cancellationToken);
            Assert.Equal(WebSocketMessageType.Binary, result.MessageType);
            count += result.Count;
            Assert.True(count < buffer.Length || result.EndOfMessage, "WebSocket message exceeded 16 KiB.");
            if (result.EndOfMessage) return buffer.AsSpan(0, count).ToArray();
        }
    }

    private sealed class NetworkServerProcess : IAsyncDisposable
    {
        private readonly Process _process;
        private readonly StringBuilder _output = new();
        private readonly object _outputLock = new();

        private NetworkServerProcess(Process process)
        {
            _process = process;
            _process.OutputDataReceived += CaptureOutput;
            _process.ErrorDataReceived += CaptureOutput;
            _process.BeginOutputReadLine();
            _process.BeginErrorReadLine();
        }

        public static NetworkServerProcess Start(ProcessStartInfo startInfo)
        {
            var process = Process.Start(startInfo)
                ?? throw new InvalidOperationException("Failed to start the server process.");
            return new NetworkServerProcess(process);
        }

        public async Task WaitUntilReadyAsync(HttpClient client, CancellationToken cancellationToken)
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                if (_process.HasExited)
                {
                    throw new InvalidOperationException(
                        $"Server exited with code {_process.ExitCode} before readiness.\n{GetOutput()}");
                }

                try
                {
                    using var response = await client.GetAsync("/health/ready", cancellationToken);
                    if (response.StatusCode == HttpStatusCode.OK) return;
                }
                catch (HttpRequestException)
                {
                    // Kestrel has not started listening yet.
                }

                await Task.Delay(TimeSpan.FromMilliseconds(100), cancellationToken);
            }

            cancellationToken.ThrowIfCancellationRequested();
        }

        public async ValueTask DisposeAsync()
        {
            if (!_process.HasExited)
            {
                _process.Kill(entireProcessTree: true);
                await _process.WaitForExitAsync();
            }

            _process.OutputDataReceived -= CaptureOutput;
            _process.ErrorDataReceived -= CaptureOutput;
            _process.Dispose();
        }

        private void CaptureOutput(object sender, DataReceivedEventArgs eventArgs)
        {
            if (eventArgs.Data is null) return;
            lock (_outputLock) _output.AppendLine(eventArgs.Data);
        }

        private string GetOutput()
        {
            lock (_outputLock) return _output.ToString();
        }
    }
}
