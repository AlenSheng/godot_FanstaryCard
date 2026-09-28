using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Net.WebSockets;
using System.Text.Json;
using System.Text.RegularExpressions;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Tests.Persistence;
using Google.Protobuf;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Fact(Skip = "Set isolated PostgreSQL database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Migration_default_binary_routes_ticket_security_and_real_sample_benchmark()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: false);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(120));
        var ct = timeout.Token;
        var port = ReserveLoopbackPort();
        var start = new ProcessStartInfo("dotnet") { WorkingDirectory = FindServerProjectDirectory(), UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true };
        start.ArgumentList.Add(typeof(FantasyCard.Server.Persistence.DatabaseMigrator).Assembly.Location);
        start.Environment["ASPNETCORE_ENVIRONMENT"] = "Development";
        start.Environment["ASPNETCORE_URLS"] = $"http://127.0.0.1:{port}";
        start.Environment["ConnectionStrings__Postgres"] = database.ConnectionString;
        start.Environment["Identity__EnableLocalAuth"] = "true";
        start.Environment["ProtobufHttp__AllowLegacyJson"] = "false";
        start.Environment["Realtime__AllowLegacyAccessTokenQuery"] = "false";
        await using var server = NetworkServerProcess.Start(start);
        using var client = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}"), Timeout = TimeSpan.FromSeconds(15) };
        await server.WaitUntilReadyAsync(client, ct);
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        using var loginResponse = await client.PostAsync("/api/v1/auth/local", PbContent(new Wire.LocalSignInRequest { DeviceId = Guid.NewGuid().ToString(), DisplayName = "Independent QA" }), ct);
        loginResponse.EnsureSuccessStatusCode();
        var login = Wire.LocalSignInResponse.Parser.ParseFrom(await loginResponse.Content.ReadAsByteArrayAsync(ct));
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", login.AccessToken);
        using var bootstrapResponse = await client.GetAsync("/api/v1/bootstrap", ct);
        bootstrapResponse.EnsureSuccessStatusCode();
        var bytes = await bootstrapResponse.Content.ReadAsByteArrayAsync(ct);
        var sample = Wire.BootstrapResponse.Parser.ParseFrom(bytes);
        var dto = HttpDtoMapper.ToDto(sample, typeof(FantasyCard.Contracts.Bootstrap.BootstrapResponse));
        var json = JsonSerializer.SerializeToUtf8Bytes(dto, WebJson);
        var directory = Path.Combine(FindServerProjectDirectory(), "..", "..", ".artifacts", "qa-migration", "samples");
        Directory.CreateDirectory(directory);
        await File.WriteAllBytesAsync(Path.Combine(directory, "bootstrap.pb"), bytes, ct);
        await File.WriteAllBytesAsync(Path.Combine(directory, "bootstrap.json"), json, ct);
        var measurements = new List<object>();
        void Measure(string name, Action operation)
        {
            for (var i = 0; i < 20; i++) operation();
            var before = GC.GetAllocatedBytesForCurrentThread();
            var timer = Stopwatch.StartNew();
            for (var i = 0; i < 100; i++) operation();
            timer.Stop();
            measurements.Add(new { name, iterations = 100, microsecondsPerOperation = timer.Elapsed.TotalMicroseconds / 100, allocatedBytesPerOperation = (GC.GetAllocatedBytesForCurrentThread() - before) / 100 });
        }
        Measure("protobuf encode DTO", () => HttpDtoMapper.EncodeResponse(HttpProtocolRegistry.Find("GET", "/api/v1/bootstrap")!, dto));
        Measure("protobuf decode DTO", () => HttpDtoMapper.ToDto(Wire.BootstrapResponse.Parser.ParseFrom(bytes), dto.GetType()));
        Measure("JSON encode DTO", () => JsonSerializer.SerializeToUtf8Bytes(dto, WebJson));
        Measure("JSON decode DTO", () => JsonSerializer.Deserialize(json, dto.GetType(), WebJson));
        await File.WriteAllTextAsync(Path.Combine(directory, "codec-benchmark.json"), JsonSerializer.Serialize(measurements, WebJson), ct);
        var timings = new List<double>();
        for (var i = 0; i < 35; i++)
        {
            var timer = Stopwatch.StartNew();
            using var response = await client.GetAsync("/api/v1/bootstrap", ct);
            response.EnsureSuccessStatusCode();
            _ = await response.Content.ReadAsByteArrayAsync(ct);
            if (i >= 5) timings.Add(timer.Elapsed.TotalMilliseconds);
        }
        var jsonTimings = new List<double>();
        var jsonPort = ReserveLoopbackPort();
        await using (var jsonServer = StartServer(database.ConnectionString, jsonPort))
        {
            using var jsonClient = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{jsonPort}"), Timeout = TimeSpan.FromSeconds(15) };
            await jsonServer.WaitUntilReadyAsync(jsonClient, ct);
            jsonClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", login.AccessToken);
            jsonClient.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            for (var i = 0; i < 35; i++)
            {
                var timer = Stopwatch.StartNew();
                using var response = await jsonClient.GetAsync("/api/v1/bootstrap", ct);
                response.EnsureSuccessStatusCode();
                Assert.Equal("application/json", response.Content.Headers.ContentType?.MediaType);
                _ = await response.Content.ReadAsByteArrayAsync(ct);
                if (i >= 5) jsonTimings.Add(timer.Elapsed.TotalMilliseconds);
            }
        }
        jsonTimings.Sort();
        timings.Sort();
        await File.WriteAllTextAsync(Path.Combine(directory, "benchmark.json"), JsonSerializer.Serialize(new { runtime = Environment.Version.ToString(), compression = "none; no Accept-Encoding", protobufBytes = bytes.Length, jsonBytes = json.Length, measurements, jsonE2e = new { samples = jsonTimings.Count, p50 = jsonTimings[14], p95 = jsonTimings[28], p99 = jsonTimings[29] }, e2e = new { samples = timings.Count, p50 = timings[14], p95 = timings[28], p99 = timings[29] } }, WebJson), ct);
        // Every registered game route is actually called without credentials; this verifies auth/typed boundary coverage, not business success.
        using var anonymous = new HttpClient { BaseAddress = client.BaseAddress };
        anonymous.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        foreach (var route in HttpProtocolRegistry.Endpoints.Where(e => !e.Path.StartsWith("/api/v1/auth/", StringComparison.Ordinal)))
        {
            var path = Regex.Replace(route.Path.Replace("{heroClass}", "Priest", StringComparison.Ordinal).Replace("{cardId}", "GW08", StringComparison.Ordinal), "\\{[^}]+\\}", "00000000-0000-0000-0000-000000000001");
            using var request = new HttpRequestMessage(new HttpMethod(route.Method), path);
                        if (route.Method != "GET")
            {
                IMessage body = route.Request switch
                {
                    "CreatePreparationRequest" => new Wire.CreatePreparationRequest { HeroClass = "Priest", BackpackTier = "Free", Difficulty = "Standard", DeckVersion = 1 },
                    "CreateMarketListingRequest" => new Wire.CreateMarketListingRequest { EquipmentId = "00000000-0000-0000-0000-000000000001", PriceGold = 1 },
                    "EnqueueMatchRequest" => new Wire.EnqueueMatchRequest { PreparationId = "00000000-0000-0000-0000-000000000001" },
                    "PurchaseShopRequest" => new Wire.PurchaseShopRequest { ProductId = "warrior_soul", Quantity = 1 },
                    _ => route.RequestDescriptor.Parser.ParseFrom(Array.Empty<byte>())
                };
                request.Content = PbContent(body);
            }
            using var response = await anonymous.SendAsync(request, ct);
            Assert.True(response.StatusCode == HttpStatusCode.Unauthorized, route.Method + " " + path + " " + response.StatusCode);
            Assert.Equal(HttpProtocolRegistry.MediaType, response.Content.Headers.ContentType?.MediaType);
            Assert.Equal((int)response.StatusCode, Wire.HttpError.Parser.ParseFrom(await response.Content.ReadAsByteArrayAsync(ct)).Status);
        }
        async Task<string> Ticket()
        {
            using var response = await client.PostAsync("/api/v1/realtime/ticket", PbContent(new Wire.Empty()), ct);
            response.EnsureSuccessStatusCode();
            return Wire.RealtimeTicketResponse.Parser.ParseFrom(await response.Content.ReadAsByteArrayAsync(ct)).Ticket;
        }
        var ticket = await Ticket();
        var uri = new Uri($"ws://127.0.0.1:{port}/ws/v1/session?ticket={Uri.EscapeDataString(ticket)}");
        using var socket = new ClientWebSocket();
        await socket.ConnectAsync(uri, ct);
        Assert.Equal("session.connected", RealtimeProtobufCodec.DecodeServer(await ReceiveBinaryAsync(socket, ct)).Type);
        using var reuse = new ClientWebSocket();
        await Assert.ThrowsAsync<WebSocketException>(() => reuse.ConnectAsync(uri, ct));
        using var query = new ClientWebSocket();
        await Assert.ThrowsAsync<WebSocketException>(() => query.ConnectAsync(new Uri($"ws://127.0.0.1:{port}/ws/v1/session?access_token={Uri.EscapeDataString(login.AccessToken)}"), ct));
        var ping = RealtimeProtobufCodec.EncodeClient(new ClientCommand("ping", "qa-ticket-ping", null, null));
        await socket.SendAsync(ping, WebSocketMessageType.Binary, true, ct);
        Assert.Equal("pong", RealtimeProtobufCodec.DecodeServer(await ReceiveBinaryAsync(socket, ct)).Type);
        using var replacement = new ClientWebSocket();
        await replacement.ConnectAsync(new Uri($"ws://127.0.0.1:{port}/ws/v1/session?ticket={Uri.EscapeDataString(await Ticket())}"), ct);
        Assert.Equal("session.connected", RealtimeProtobufCodec.DecodeServer(await ReceiveBinaryAsync(replacement, ct)).Type);
        socket.Abort();
        await using (var expire = database.DataSource.CreateCommand("UPDATE player_sessions SET expires_at=now()-interval '1 minute' WHERE player_id=$1"))
        { expire.Parameters.AddWithValue(Guid.Parse(login.Player.UserId)); await expire.ExecuteNonQueryAsync(ct); }
        await replacement.SendAsync(ping, WebSocketMessageType.Binary, true, ct);
        var close = await replacement.ReceiveAsync(new byte[16384], ct);
        Assert.Equal(WebSocketMessageType.Close, close.MessageType);
        using var expired = await client.PostAsync("/api/v1/realtime/ticket", PbContent(new Wire.Empty()), ct);
        Assert.Equal(HttpStatusCode.Unauthorized, expired.StatusCode);
    }
}
