using System.Net;
using System.Net.Http.Headers;
using Google.Protobuf;
using FantasyCard.Contracts.Http;
using System.Net.WebSockets;
using System.Text.Json;
using FantasyCard.Contracts.Realtime;
using Npgsql;

using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(60));
var ct = timeout.Token;
using var client = new HttpClient { BaseAddress = new Uri("http://server:8080") };
var checks = new List<string>();
var phase = args.Single();
const string statePath = "/evidence/smoke-state.json";
var json = new JsonSerializerOptions(JsonSerializerDefaults.Web);
void Check(bool condition, string description)
{
    if (!condition) throw new InvalidOperationException(description);
    checks.Add(description);
}
async Task<JsonElement> Request(HttpMethod method, string path, object? body = null, string? idempotency = null)
{
    var contract = HttpProtocolRegistry.Find(method.Method, path)
        ?? throw new InvalidOperationException("Missing HTTP contract: " + path);
    using var request = new HttpRequestMessage(method, path);
    request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
    if (idempotency is not null) request.Headers.Add("Idempotency-Key", idempotency);
    if (body is not null)
    {
        request.Content = new ByteArrayContent(HttpDtoMapper.FromDto(contract.RequestDescriptor, body).ToByteArray());
        request.Content.Headers.ContentType = new MediaTypeHeaderValue(HttpProtocolRegistry.MediaType);
    }
    using var response = await client.SendAsync(request, ct);
    response.EnsureSuccessStatusCode();
    Check(response.Content.Headers.ContentType?.MediaType == HttpProtocolRegistry.MediaType, "HTTP protobuf " + path);
    var message = contract.ResponseDescriptor.Parser.ParseFrom(await response.Content.ReadAsByteArrayAsync(ct));
    return JsonSerializer.SerializeToElement(message, message.GetType(), json);
}
async Task<JsonElement> Purchase(string product)
{
    return await Request(HttpMethod.Post, "/api/v1/shop/purchases", new { productId = product, quantity = 1 }, "docker-acceptance-purchase");
}

Check((await client.GetAsync("/health/live", ct)).StatusCode == HttpStatusCode.OK, "liveness");
Check((await client.GetAsync("/health/ready", ct)).StatusCode == HttpStatusCode.OK, "database readiness");
Check((await client.GetAsync("/api/v1/bootstrap", ct)).StatusCode == HttpStatusCode.Unauthorized,
    "unauthenticated bootstrap rejected");
State state;
if (phase == "before")
{
    var signIn = await Request(HttpMethod.Post, "/api/v1/auth/local",
        new { deviceId = "docker-acceptance-" + Guid.NewGuid().ToString("N"), displayName = "Docker Acceptance" });
    var token = signIn.GetProperty("accessToken").GetString()!;
    var userId = signIn.GetProperty("player").GetProperty("userId").GetGuid();
    Check(userId != Guid.Empty && token.Length > 0, "local sign-in");
    client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
    var bootstrap = await Request(HttpMethod.Get, "/api/v1/bootstrap");
    Check(bootstrap.GetProperty("decks").GetArrayLength() == 3 &&
        bootstrap.GetProperty("classWeapons").GetArrayLength() == 3, "bootstrap decks and class weapons");
    await using var database = NpgsqlDataSource.Create(Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES")!);
    await using (var seed = database.CreateCommand("UPDATE player_wallets SET gold=1000 WHERE player_id=$1"))
    {
        seed.Parameters.AddWithValue(userId);
        Check(await seed.ExecuteNonQueryAsync(ct) == 1, "isolated purchase fixture");
    }
    var shop = await Request(HttpMethod.Get, "/api/v1/shop/");
    var product = shop.GetProperty("products").EnumerateArray().Single(p => p.GetProperty("productId").GetString() == "daily_card_1");
    var productId = product.GetProperty("productId").GetString()!;
    var gold = 1000 - product.GetProperty("priceGold").GetInt64();
    var cardId = product.GetProperty("payload").GetProperty("cardId").GetString()!;
    await using var copies = database.CreateCommand("SELECT copy_count FROM player_cards WHERE player_id=$1 AND card_id=$2");
    copies.Parameters.AddWithValue(userId);
    copies.Parameters.AddWithValue(cardId);
    var expectedCopies = Convert.ToInt32(await copies.ExecuteScalarAsync(ct)) + 1;
    var purchase = await Purchase(productId);
    Check(purchase.GetProperty("goldAfter").GetInt64() == gold, "purchase charges correct gold");
    var retry = await Purchase(productId);
    Check(retry.GetProperty("goldAfter").GetInt64() == gold &&
        Convert.ToInt32(await copies.ExecuteScalarAsync(ct)) == expectedCopies, "purchase retry grants once");
    state = new State(token, userId, productId, cardId, gold, expectedCopies);
    await File.WriteAllTextAsync(statePath, JsonSerializer.Serialize(state, json), ct);
}
else if (phase == "after")
{
    state = JsonSerializer.Deserialize<State>(await File.ReadAllTextAsync(statePath, ct), json)!;
    client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", state.Token);
    var bootstrap = await Request(HttpMethod.Get, "/api/v1/bootstrap");
    Check(bootstrap.GetProperty("player").GetProperty("userId").GetGuid() == state.UserId, "session persists after container restart");
    var retry = await Purchase(state.Product);
    Check(retry.GetProperty("goldAfter").GetInt64() == state.Gold, "purchase replay after container restart");
    await using var database = NpgsqlDataSource.Create(Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES")!);
    await using var balance = database.CreateCommand("SELECT gold FROM player_wallets WHERE player_id=$1");
    balance.Parameters.AddWithValue(state.UserId);
    Check(Convert.ToInt64(await balance.ExecuteScalarAsync(ct)) == state.Gold, "gold persists without duplicate charge");
    await using var copies = database.CreateCommand("SELECT copy_count FROM player_cards WHERE player_id=$1 AND card_id=$2");
    copies.Parameters.AddWithValue(state.UserId);
    copies.Parameters.AddWithValue(state.Card);
    Check(Convert.ToInt32(await copies.ExecuteScalarAsync(ct)) == state.Copies, "cards persist without duplicate grant");
}
else throw new ArgumentException("Expected before or after phase.");

using var socket = new ClientWebSocket();
var ticket = await Request(HttpMethod.Post, "/api/v1/realtime/ticket", new { });
await socket.ConnectAsync(new Uri("ws://server:8080/ws/v1/session?ticket=" + Uri.EscapeDataString(ticket.GetProperty("ticket").GetString()!)), ct);
async Task<ServerEvent> Receive()
{
    using var message = new MemoryStream();
    var buffer = new byte[16384];
    ValueWebSocketReceiveResult result;
    do
    {
        result = await socket.ReceiveAsync(buffer.AsMemory(), ct);
        if (result.MessageType != WebSocketMessageType.Binary || message.Length + result.Count > 65536)
            throw new InvalidDataException("Expected a bounded binary WebSocket message.");
        message.Write(buffer, 0, result.Count);
    } while (!result.EndOfMessage);
    return RealtimeProtobufCodec.DecodeServer(message.ToArray());
}
var connected = await Receive();
Check(connected.Type == "session.connected" &&
    connected.Payload is SessionConnectedEventPayload session && session.PlayerId == state.UserId, "protobuf session connected");
var pingId = "docker-" + phase;
await socket.SendAsync(RealtimeProtobufCodec.EncodeClient(new ClientCommand("ping", pingId, null, null)),
    WebSocketMessageType.Binary, true, ct);
var pong = await Receive();
Check(pong.Type == "pong" && pong.RequestId == pingId && pong.Sequence > connected.Sequence, "protobuf ping/pong sequence");
await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "acceptance complete", ct);
var resultJson = JsonSerializer.Serialize(new { ok = true, phase, checks }, json);
await File.WriteAllTextAsync($"/evidence/smoke-{phase}.json", resultJson, ct);
Console.WriteLine(resultJson);

record State(string Token, Guid UserId, string Product, string Card, long Gold, int Copies);
