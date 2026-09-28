using System.Net;
using System.Net.Http.Headers;
using System.Net.WebSockets;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Tests.Persistence;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Theory(Skip = "Set isolated PostgreSQL database.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData("ticket-expiry")]
    [InlineData("ban-idle")]
    [Trait("Category", "PostgresIntegration")]
    public async Task Migration_ticket_lifecycle_rejects_expiry_and_idle_ban(string scenario)
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: false);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(70));
        var ct = timeout.Token;
        var port = ReserveLoopbackPort();
        await using var server = StartServer(database.ConnectionString, port);
        using var client = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}"), Timeout = TimeSpan.FromSeconds(12) };
        await server.WaitUntilReadyAsync(client, ct);
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        using var loginResponse = await client.PostAsync("/api/v1/auth/local", PbContent(new Wire.LocalSignInRequest { DeviceId = Guid.NewGuid().ToString(), DisplayName = "QA Lifecycle" }), ct);
        loginResponse.EnsureSuccessStatusCode();
        var login = Wire.LocalSignInResponse.Parser.ParseFrom(await loginResponse.Content.ReadAsByteArrayAsync(ct));
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", login.AccessToken);
        using var ticketResponse = await client.PostAsync("/api/v1/realtime/ticket", PbContent(new Wire.Empty()), ct);
        ticketResponse.EnsureSuccessStatusCode();
        var ticket = Wire.RealtimeTicketResponse.Parser.ParseFrom(await ticketResponse.Content.ReadAsByteArrayAsync(ct));
        var uri = new Uri($"ws://127.0.0.1:{port}/ws/v1/session?ticket={Uri.EscapeDataString(ticket.Ticket)}");
        using var socket = new ClientWebSocket();
        if (scenario == "ticket-expiry")
        {
            await Task.Delay(TimeSpan.FromSeconds(31), ct);
            await Assert.ThrowsAsync<WebSocketException>(() => socket.ConnectAsync(uri, ct));
        }
        else
        {
            await socket.ConnectAsync(uri, ct);
            Assert.Equal("session.connected", RealtimeProtobufCodec.DecodeServer(await ReceiveBinaryAsync(socket, ct)).Type);
            await using var ban = database.DataSource.CreateCommand("INSERT INTO player_bans(player_id,reason,banned_at,banned_by) VALUES($1,'QA',now(),'isolated-test')");
            ban.Parameters.AddWithValue(Guid.Parse(login.Player.UserId));
            await ban.ExecuteNonQueryAsync(ct);
            using var idleTimeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
            idleTimeout.CancelAfter(TimeSpan.FromSeconds(12));
            var close = await socket.ReceiveAsync(new byte[16384], idleTimeout.Token);
            Assert.Equal(WebSocketMessageType.Close, close.MessageType);
            using var denied = await client.PostAsync("/api/v1/realtime/ticket", PbContent(new Wire.Empty()), ct);
            Assert.Equal(HttpStatusCode.Unauthorized, denied.StatusCode);
        }
    }
}
