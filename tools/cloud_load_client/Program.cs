using System.Diagnostics;
using System.Net.Http.Headers;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading.Channels;
using FantasyCard.Contracts.Realtime;

var options = new LoadOptions();
var client = new CloudLoadClient(options);
return await client.RunAsync();

sealed class LoadOptions
{
    public string ServerUrl { get; } = (Environment.GetEnvironmentVariable("FANTASYCARD_SERVER_URL") ?? "https://www.relicbound.cn").TrimEnd('/');
    public string ClientId { get; } = Environment.GetEnvironmentVariable("FANTASYCARD_LOAD_CLIENT_ID") ?? ("client-" + Guid.NewGuid().ToString("N")[..8]);
    public int Group { get; } = int.TryParse(Environment.GetEnvironmentVariable("FANTASYCARD_LOAD_GROUP"), out var group) && group > 0 ? group : 1;
    public string ReportPath { get; } = Environment.GetEnvironmentVariable("FANTASYCARD_LOAD_REPORT") ?? Path.Combine(Environment.CurrentDirectory, "cloud-load-client.json");
    public string StopFile { get; } = Environment.GetEnvironmentVariable("FANTASYCARD_LOAD_STOP_FILE") ?? string.Empty;
}

sealed class CloudLoadClient(LoadOptions options)
{
    private readonly Stopwatch _lifetime = Stopwatch.StartNew();
    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(15) };
    private readonly List<Dictionary<string, object?>> _operations = [];
    private readonly List<Dictionary<string, object?>> _telemetry = [];
    private readonly List<Dictionary<string, object?>> _checks = [];
    private readonly List<Dictionary<string, object?>> _errors = [];
    private readonly Dictionary<string, int> _events = [];
    private readonly Dictionary<string, (long Timestamp, string Action)> _pendingCommands = [];
    private readonly JsonSerializerOptions _json = new(JsonSerializerDefaults.Web) { WriteIndented = true };
    private readonly CancellationTokenSource _shutdown = new();
    private readonly Channel<ServerEvent> _eventChannel = Channel.CreateUnbounded<ServerEvent>();
    private Task _receiverTask;
    private ClientWebSocket _socket;
    private string _token = string.Empty;
    private string _userId = string.Empty;
    private long _roomRevision;
    private RoomSnapshotEventPayload _snapshot;
    private string _settlementId = string.Empty;
    private bool _scenarioStarted;
    private bool _scenarioFinished;
    private bool _online;
    private bool _inRoom;
    private bool _legacyEconomy;
    private bool _aggregateEconomy;
    private JsonElement? _lastMarketListings;

    public async Task<int> RunAsync()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(options.ReportPath))!);
        var statusTask = StatusLoopAsync();
        var ok = false;
        var message = "";
        try
        {
            await LoginAsync();
            await ConnectAsync();
            if (!_online) throw new InvalidOperationException("WebSocket session did not connect.");
            await ReadEconomyAsync("initial");
            _scenarioStarted = true;
            await RunExpeditionAsync();
            await ReadEconomyAsync("post_expedition");
            await EconomyActionsAsync("post_expedition");
            _scenarioFinished = true;
            while (!StopRequested)
            {
                await ReadEconomyAsync("steady_state");
                await TryMarketPurchaseAsync();
                await PingAsync();
                await Task.Delay(TimeSpan.FromSeconds(15));
            }
            await GracefulCleanupAsync();
            ok = true;
            message = "Stopped by load-test coordinator";
        }
        catch (Exception exception)
        {
            AddError(exception.GetType().Name + ": " + exception.Message);
            message = exception.Message;
            await GracefulCleanupAsync();
        }
        finally
        {
            _shutdown.Cancel();
            try { await statusTask; } catch { }
            await WriteReportAsync(ok, message);
            _http.Dispose();
            _socket?.Dispose();
        }
        return ok ? 0 : 1;
    }

    private bool StopRequested => !string.IsNullOrWhiteSpace(options.StopFile) && File.Exists(options.StopFile);

    private async Task LoginAsync()
    {
        var suffix = Guid.NewGuid().ToString("N")[..8];
        var name = ("L" + options.ClientId.Replace("_", "", StringComparison.Ordinal) + suffix)[..Math.Min(20, ("L" + options.ClientId.Replace("_", "", StringComparison.Ordinal) + suffix).Length)];
        var signIn = await SendHttpAsync("login", "/api/v1/auth/local", HttpMethod.Post, new { deviceId = "load-" + options.ClientId + "-" + Guid.NewGuid().ToString("N"), displayName = name }, true);
        if (!signIn.Ok) throw new InvalidOperationException("Cloud local login failed: " + signIn.Status);
        _token = signIn.Data.GetProperty("accessToken").GetString() ?? throw new InvalidOperationException("Missing access token");
        _userId = signIn.Data.GetProperty("player").GetProperty("userId").GetString() ?? "";
        AddCheck(true, "login_and_bootstrap");
    }

    private async Task ConnectAsync()
    {
        _socket = new ClientWebSocket();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        var uri = new Uri(options.ServerUrl.Replace("https://", "wss://", StringComparison.OrdinalIgnoreCase).Replace("http://", "ws://", StringComparison.OrdinalIgnoreCase) + "/ws/v1/session?access_token=" + Uri.EscapeDataString(_token));
        await _socket.ConnectAsync(uri, timeout.Token);
        var connected = await ReceiveFrameAsync(timeout.Token);
        _online = connected.Type == "session.connected";
        AddCheck(_online, "realtime_connected");
        _receiverTask = Task.Run(ReceiveLoopAsync);
    }

    private async Task RunExpeditionAsync()
    {
        var bootstrap = await SendHttpAsync("bootstrap", "/api/v1/bootstrap", HttpMethod.Get, null, false);
        if (!bootstrap.Ok) throw new InvalidOperationException("Bootstrap failed: " + bootstrap.Status);
        var deckVersion = 1L;
        foreach (var deck in bootstrap.Data.GetProperty("decks").EnumerateArray())
            if (deck.GetProperty("heroClass").GetString() == "Mage") deckVersion = deck.GetProperty("version").GetInt64();
        var preparation = await SendHttpAsync("create_free_preparation", "/api/v1/preparations", HttpMethod.Post,
            new { heroClass = "Mage", deckVersion, equipmentIds = new string?[] { null, null, null, null, null }, backpackTier = "Free", safeSlotIndexes = Array.Empty<int>(), potionCount = 0, difficulty = "Standard" }, true);
        AddCheck(preparation.Ok, "create_free_preparation");
        if (!preparation.Ok) return;
        var preparationId = preparation.Data.GetProperty("preparationId").GetString();
        var enqueue = await SendHttpAsync("enqueue_match", "/api/v1/matches/enqueue", HttpMethod.Post, new { preparationId }, true);
        AddCheck(enqueue.Ok, "enqueue_match");
        if (!enqueue.Ok) return;
        var deadline = DateTimeOffset.UtcNow.AddMinutes(2);
        while (!_inRoom && DateTimeOffset.UtcNow < deadline && !StopRequested)
        {
            ServerEvent eventMessage;
            try { eventMessage = await ReceiveAsync(TimeSpan.FromSeconds(10)); }
            catch (OperationCanceledException) { continue; }
            if (eventMessage.Type == "room.ready_required")
            {
                await SendAndDrainAsync("room.ready", new RoomReadyCommandPayload(), null, 10);
            }
            if (eventMessage.Type == "room.started") _inRoom = true;
        }
        if (!_inRoom || _snapshot is null) throw new InvalidOperationException("Match did not enter a room.");
        deadline = DateTimeOffset.UtcNow.AddMinutes(4);
        while (string.IsNullOrWhiteSpace(_settlementId) && DateTimeOffset.UtcNow < deadline && !StopRequested)
        {
            if (_snapshot is null)
            {
                await RefreshSnapshotAsync();
                continue;
            }
            var action = ChooseRoomAction(_snapshot);
            if (action is null)
            {
                await PingAsync();
                await Task.Delay(300);
                continue;
            }
            await SendAndDrainAsync(action.Value.Type, action.Value.Payload, _snapshot.RoomRevision, 8);
            if (string.IsNullOrWhiteSpace(_settlementId)) await RefreshSnapshotAsync();
        }
        if (string.IsNullOrWhiteSpace(_settlementId) && _snapshot is not null && _snapshot.AllowedActions.Contains("action.extract"))
        {
            await SendAndDrainAsync("action.extract", new ActionExtractCommandPayload(), _snapshot.RoomRevision, 10);
            var settlementDeadline = DateTimeOffset.UtcNow.AddSeconds(12);
            while (string.IsNullOrWhiteSpace(_settlementId) && DateTimeOffset.UtcNow < settlementDeadline)
            {
                try { await ReceiveAsync(TimeSpan.FromSeconds(3)); }
                catch (OperationCanceledException) { }
            }
        }
        if (!string.IsNullOrWhiteSpace(_settlementId))
        {
            await SendHttpAsync("settlement_ack", "/api/v1/settlements/" + _settlementId + "/acknowledge", HttpMethod.Post, new { }, true);
            _inRoom = false;
            _snapshot = null;
            _roomRevision = 0;
            AddCheck(true, "settlement_acknowledged");
        }
    }

    private (string Type, object Payload)? ChooseRoomAction(RoomSnapshotEventPayload snapshot)
    {
        if (snapshot.Pve is not null)
        {
            var target = snapshot.Pve.Monsters.FirstOrDefault(monster => monster.MonsterId == snapshot.Pve.CurrentTargetId);
            if (target is not null && target.Hp <= 0)
            {
                var next = snapshot.Pve.Monsters.FirstOrDefault(monster => monster.Hp > 0);
                if (next is not null && snapshot.AllowedActions.Contains("battle.select_target"))
                    return ("battle.select_target", new BattleSelectTargetCommandPayload(snapshot.Pve.BattleId, next.MonsterId));
            }
            if (snapshot.AllowedActions.Contains("battle.play_cards") && snapshot.Player.Hand.Count > 0)
                return ("battle.play_cards", new BattlePlayCardsCommandPayload(snapshot.Pve.BattleId, snapshot.Pve.CurrentTargetId ?? "", snapshot.Player.Hand.Select(card => card.InstanceId).ToArray()));
        }
        if (snapshot.RewardChoice is not null && snapshot.AllowedActions.Contains("reward.choice.claim"))
        {
            var option = snapshot.RewardChoice.Options.LastOrDefault();
            if (option is not null) return ("reward.choice.claim", new RewardChoiceClaimCommandPayload(option.OptionId));
        }
        if (snapshot.AllowedActions.Contains("action.extract")) return ("action.extract", new ActionExtractCommandPayload());
        if (snapshot.AllowedActions.Contains("action.spring")) return ("action.spring", new ActionSpringCommandPayload());
        if (snapshot.AllowedActions.Contains("room.move") && snapshot.LegalMoves.Count > 0)
            return ("room.move", new RoomMoveCommandPayload(snapshot.LegalMoves[0].Row, snapshot.LegalMoves[0].Column));
        return null;
    }

    private async Task RefreshSnapshotAsync()
    {
        await SendAndDrainAsync("room.snapshot.read", new RoomSnapshotCommandPayload(), null, 8);
    }

    private async Task SendAndDrainAsync(string type, object payload, long? revision, int seconds)
    {
        var requestId = "load-" + Guid.NewGuid().ToString("N");
        _pendingCommands[requestId] = (Stopwatch.GetTimestamp(), type);
        var bytes = RealtimeProtobufCodec.EncodeClient(new ClientCommand(type, requestId, revision, payload));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(seconds));
        await _socket.SendAsync(bytes, WebSocketMessageType.Binary, true, timeout.Token);
        try
        {
            while (!timeout.IsCancellationRequested && !StopRequested)
            {
                var eventMessage = await ReceiveAsync(TimeSpan.FromSeconds(seconds));
                if (eventMessage.RequestId == requestId || eventMessage.Type is "settlement.ready" or "match.settled") return;
            }
        }
        catch (OperationCanceledException) { }
    }

    private async Task PingAsync()
    {
        if (!_online || _socket.State != WebSocketState.Open) return;
        var requestId = "ping-" + Guid.NewGuid().ToString("N");
        var started = Stopwatch.GetTimestamp();
        var bytes = RealtimeProtobufCodec.EncodeClient(new ClientCommand("ping", requestId, null, null));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        await _socket.SendAsync(bytes, WebSocketMessageType.Binary, true, timeout.Token);
        try
        {
            while (!timeout.IsCancellationRequested)
            {
                var eventMessage = await ReceiveAsync(TimeSpan.FromSeconds(10));
                if (eventMessage.Type == "pong" && eventMessage.RequestId == requestId)
                {
                    AddTelemetry("rtt", "ping", ElapsedMs(started));
                    return;
                }
            }
        }
        catch (OperationCanceledException) { }
    }

    private async Task ReceiveLoopAsync()
    {
        try
        {
            while (_socket?.State == WebSocketState.Open)
                _eventChannel.Writer.TryWrite(await ReceiveFrameAsync(CancellationToken.None));
        }
        catch (Exception exception)
        {
            if (!StopRequested) AddError("realtime_receive: " + exception.Message);
        }
        finally
        {
            _eventChannel.Writer.TryComplete();
        }
    }

    private async Task<ServerEvent> ReceiveAsync(TimeSpan timeout)
    {
        while (true)
        {
            var ready = _eventChannel.Reader.WaitToReadAsync().AsTask();
            if (await Task.WhenAny(ready, Task.Delay(timeout)) != ready)
                throw new OperationCanceledException("Timed out waiting for a realtime event.");
            if (_eventChannel.Reader.TryRead(out var eventMessage)) return eventMessage;
        }
    }

    private async Task<ServerEvent> ReceiveFrameAsync(CancellationToken cancellationToken)
    {
        using var message = new MemoryStream();
        var buffer = new byte[16 * 1024];
        while (true)
        {
            var result = await _socket.ReceiveAsync(buffer, cancellationToken);
            if (result.MessageType == WebSocketMessageType.Close) throw new WebSocketException("Cloud closed the realtime socket.");
            if (result.MessageType != WebSocketMessageType.Binary) throw new InvalidDataException("Expected binary protobuf frame.");
            message.Write(buffer, 0, result.Count);
            if (!result.EndOfMessage) continue;
            var eventMessage = RealtimeProtobufCodec.DecodeServer(message.ToArray());
            _events[eventMessage.Type] = _events.GetValueOrDefault(eventMessage.Type) + 1;
            ApplyEvent(eventMessage);
            if (!string.IsNullOrWhiteSpace(eventMessage.RequestId) && _pendingCommands.Remove(eventMessage.RequestId, out var pending))
                AddTelemetry("realtime", pending.Action, ElapsedMs(pending.Timestamp));
            return eventMessage;
        }
    }

    private void ApplyEvent(ServerEvent eventMessage)
    {
        switch (eventMessage.Type)
        {
            case "room.started" when eventMessage.Payload is RoomStartedEventPayload started:
                _inRoom = true;
                if (started.Snapshot is not null) ApplySnapshot(started.Snapshot);
                break;
            case "room.snapshot" when eventMessage.Payload is RoomSnapshotEventPayload snapshot:
                ApplySnapshot(snapshot);
                break;
            case "settlement.ready" or "match.settled" when eventMessage.Payload is SettlementReadyEventPayload settlement:
                _settlementId = settlement.SettlementId.ToString("D");
                break;
        }
    }

    private void ApplySnapshot(RoomSnapshotEventPayload snapshot)
    {
        _snapshot = snapshot;
        _roomRevision = snapshot.RoomRevision;
        _inRoom = true;
    }

    private async Task ReadEconomyAsync(string label)
    {
        if (_aggregateEconomy)
        {
            var context = await SendHttpAsync(label + ":economy_context", "/api/v1/economy/context", HttpMethod.Get, null, false);
            if (context.Ok && context.Data.TryGetProperty("market", out var listings))
                _lastMarketListings = listings.Clone();
            return;
        }

        if (!_legacyEconomy && label == "initial")
        {
            var aggregate = await SendHttpAsync(label + ":economy_context", "/api/v1/economy/context", HttpMethod.Get, null, false);
            if (aggregate.Ok && aggregate.Data.TryGetProperty("market", out var listings))
            {
                _aggregateEconomy = true;
                _lastMarketListings = listings.Clone();
                return;
            }
        }

        if (_legacyEconomy)
        {
            await SendHttpAsync(label + ":shop", "/api/v1/shop/", HttpMethod.Get, null, false);
            var market = await SendHttpAsync(label + ":market", "/api/v1/market/", HttpMethod.Get, null, false);
            if (market.Ok) _lastMarketListings = market.Data.Clone();
        }
        else
        {
            var shop = await SendHttpAsync(label + ":shop_context", "/api/v1/shop/context", HttpMethod.Get, null, false);
            _legacyEconomy = shop.Status == 404;
            if (_legacyEconomy) await SendHttpAsync(label + ":shop", "/api/v1/shop/", HttpMethod.Get, null, false);
            var market = await SendHttpAsync(label + ":market_context", "/api/v1/market/context", HttpMethod.Get, null, false);
            if (market.Status == 404) _legacyEconomy = true;
            if (_legacyEconomy)
            {
                var legacyMarket = await SendHttpAsync(label + ":market", "/api/v1/market/", HttpMethod.Get, null, false);
                if (legacyMarket.Ok) _lastMarketListings = legacyMarket.Data.Clone();
            }
            else if (market.Ok && market.Data.TryGetProperty("listings", out var listings))
            {
                _lastMarketListings = listings.Clone();
            }
        }
        await SendHttpAsync(label + ":inventory", "/api/v1/inventory", HttpMethod.Get, null, false);
    }

    private async Task EconomyActionsAsync(string label)
    {
        JsonElement shopData = default;
        JsonElement inventoryData = default;
        if (_aggregateEconomy)
        {
            var context = await SendHttpAsync(label + ":economy_context", "/api/v1/economy/context", HttpMethod.Get, null, false);
            if (context.Ok)
            {
                context.Data.TryGetProperty("shop", out shopData);
                context.Data.TryGetProperty("inventory", out inventoryData);
            }
        }
        else
        {
            var shopPath = _legacyEconomy ? "/api/v1/shop/" : "/api/v1/shop/context";
            var shop = await SendHttpAsync(label + ":shop_read", shopPath, HttpMethod.Get, null, false);
            if (shop.Ok) shopData = shop.Data;
        }

        if (shopData.ValueKind == JsonValueKind.Object && shopData.TryGetProperty("products", out var products))
        {
            foreach (var product in products.EnumerateArray())
            {
                if (product.TryGetProperty("alreadyOwned", out var owned) && owned.GetBoolean()) continue;
                if (product.GetProperty("priceGold").GetInt64() > 0) continue;
                await SendHttpAsync(label + ":shop_purchase", "/api/v1/shop/purchases", HttpMethod.Post, new { productId = product.GetProperty("productId").GetString(), quantity = 1 }, true);
                break;
            }
        }

        if (!_aggregateEconomy)
        {
            var inventory = await SendHttpAsync(label + ":inventory_read", "/api/v1/inventory", HttpMethod.Get, null, false);
            if (inventory.Ok) inventoryData = inventory.Data;
        }
        if (inventoryData.ValueKind == JsonValueKind.Object && inventoryData.TryGetProperty("items", out var items))
        {
            var equipment = items.EnumerateArray().FirstOrDefault(item => item.TryGetProperty("kind", out var kind) && kind.GetString() == "Equipment");
            if (equipment.ValueKind != JsonValueKind.Undefined)
            {
                var itemId = equipment.GetProperty("instanceId").GetString() ?? equipment.GetProperty("itemId").GetString();
                if (!string.IsNullOrWhiteSpace(itemId))
                {
                    var listing = await SendHttpAsync(label + ":market_list", "/api/v1/market/listings", HttpMethod.Post, new { equipmentId = itemId, priceGold = 100 }, true);
                    if (listing.Ok && listing.Data.TryGetProperty("listingId", out var listingId))
                        await SendHttpAsync(label + ":market_cancel", "/api/v1/market/listings/" + listingId.GetString(), HttpMethod.Delete, null, true);
                }
            }
        }
    }

    private async Task TryMarketPurchaseAsync()
    {
        if (!_lastMarketListings.HasValue || _lastMarketListings.Value.ValueKind != JsonValueKind.Array) return;
        foreach (var listing in _lastMarketListings.Value.EnumerateArray())
        {
            if (listing.GetProperty("sellerId").GetString() == _userId) continue;
            await SendHttpAsync("steady_state:market_purchase", "/api/v1/market/" + listing.GetProperty("listingId").GetString() + "/purchase?expectedVersion=" + listing.GetProperty("version").GetInt64(), HttpMethod.Post, new { }, true);
            break;
        }
    }

    private async Task GracefulCleanupAsync()
    {
        try
        {
            if (_snapshot is not null && _snapshot.AllowedActions.Contains("action.extract"))
                await SendAndDrainAsync("action.extract", new ActionExtractCommandPayload(), _snapshot.RoomRevision, 6);
            if (_socket?.State == WebSocketState.Open) await _socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "load-test-stop", CancellationToken.None);
        }
        catch { }
        _online = false;
        _inRoom = false;
    }

    private async Task<HttpResult> SendHttpAsync(string label, string path, HttpMethod method, object payload, bool idempotent)
    {
        var started = Stopwatch.GetTimestamp();
        using var request = new HttpRequestMessage(method, options.ServerUrl + path);
        request.Headers.UserAgent.Add(new ProductInfoHeaderValue("FantasyCard-CloudLoad", "1.0"));
        if (!string.IsNullOrWhiteSpace(_token)) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _token);
        request.Headers.Add("X-Trace-Id", "load-" + Guid.NewGuid().ToString("N"));
        if (idempotent) request.Headers.Add("Idempotency-Key", "load-" + Guid.NewGuid().ToString("N"));
        if (payload is not null) request.Content = new StringContent(JsonSerializer.Serialize(payload, _json), Encoding.UTF8, "application/json");
        using var response = await _http.SendAsync(request);
        var body = await response.Content.ReadAsStringAsync();
        JsonElement data = default;
        try { data = JsonDocument.Parse(string.IsNullOrWhiteSpace(body) ? "{}" : body).RootElement.Clone(); } catch { }
        var ok = (int)response.StatusCode is >= 200 and < 300;
        var op = new Dictionary<string, object?> { ["at_unix_ms"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), ["label"] = label, ["path"] = path, ["method"] = method.Method, ["duration_ms"] = ElapsedMs(started), ["status"] = (int)response.StatusCode, ["ok"] = ok };
        _operations.Add(op);
        if (_operations.Count > 300) _operations.RemoveAt(0);
        return new HttpResult(ok, (int)response.StatusCode, data);
    }

    private async Task StatusLoopAsync()
    {
        while (!_shutdown.IsCancellationRequested)
        {
            await WriteStatusAsync();
            try { await Task.Delay(5000, _shutdown.Token); } catch { }
        }
    }

    private async Task WriteStatusAsync()
    {
        var status = new { client_id = options.ClientId, group = options.Group, pid = Environment.ProcessId, started_at_unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() - _lifetime.ElapsedMilliseconds, now_unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), online = _online, room = _inRoom, scenario_started = _scenarioStarted, scenario_finished = _scenarioFinished, checks = _checks, operations = _operations, telemetry = _telemetry, events = _events, errors = _errors };
        await File.WriteAllTextAsync(options.ReportPath + ".status.json", JsonSerializer.Serialize(status, _json));
    }

    private async Task WriteReportAsync(bool ok, string message)
    {
        var report = new { ok, message, client_id = options.ClientId, group = options.Group, pid = Environment.ProcessId, user_id = _userId, started_at_unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() - _lifetime.ElapsedMilliseconds, ended_at_unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), elapsed_ms = _lifetime.ElapsedMilliseconds, checks = _checks, operations = _operations, telemetry = _telemetry, events = _events, errors = _errors };
        await File.WriteAllTextAsync(options.ReportPath, JsonSerializer.Serialize(report, _json));
        await WriteStatusAsync();
    }

    private void AddCheck(bool passed, string name) => _checks.Add(new Dictionary<string, object?> { ["name"] = name, ["passed"] = passed, ["at_unix_ms"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() });
    private void AddError(string message) { _errors.Add(new Dictionary<string, object?> { ["at_unix_ms"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), ["message"] = message }); if (_errors.Count > 100) _errors.RemoveAt(0); }
    private void AddTelemetry(string type, string action, double duration) { _telemetry.Add(new Dictionary<string, object?> { ["type"] = type, ["action"] = action, ["duration_ms"] = duration, ["at_unix_ms"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() }); if (_telemetry.Count > 400) _telemetry.RemoveAt(0); }
    private static double ElapsedMs(long started) => Math.Round((Stopwatch.GetTimestamp() - started) * 1000.0 / Stopwatch.Frequency, 2);
    private readonly record struct HttpResult(bool Ok, int Status, JsonElement Data);
}
