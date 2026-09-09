using System.Net.WebSockets;
using System.Text;
using System.Text.Json;

// Minimal repro: text-frame rejection on a fresh WS connection.
var http = new HttpClient { BaseAddress = new Uri("http://127.0.0.1:5080") };
var body = JsonSerializer.Serialize(new { deviceId = "proto-harness-01", displayName = "ProtoHarness" });
using var response = await http.PostAsync("/api/v1/auth/local",
    new StringContent(body, Encoding.UTF8, "application/json"));
response.EnsureSuccessStatusCode();
var json = await response.Content.ReadAsStringAsync();
using var doc = JsonDocument.Parse(json);
var token = doc.RootElement.GetProperty("accessToken").GetString();
Console.WriteLine("login ok");

var wsUrl = "ws://127.0.0.1:5080/ws/v1/session?access_token=" + Uri.EscapeDataString(token);
using var ws = new ClientWebSocket();
await ws.ConnectAsync(new Uri(wsUrl), CancellationToken.None);
Console.WriteLine($"ws connected, state={ws.State}");

// drain session.connected immediately
var first = await ws.ReceiveAsync(new byte[4096], CancellationToken.None);
Console.WriteLine($"first frame: type={first.MessageType} endOfMessage={first.EndOfMessage} bytes={first.Count} close={first.CloseStatus}");

// send text frame
using (var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5)))
{
    try
    {
        await ws.SendAsync(new ArraySegment<byte>(Encoding.UTF8.GetBytes("{\"type\":\"ping\"}")),
            WebSocketMessageType.Text, true, timeout.Token);
        Console.WriteLine("text frame sent");
    }
    catch (Exception ex)
    {
        Console.WriteLine($"text send threw: {ex.GetType().Name}: {ex.Message} (state={ws.State})");
    }
}

// receive close
using (var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5)))
{
    try
    {
        var result = await ws.ReceiveAsync(new byte[4096], timeout.Token);
        Console.WriteLine($"close frame: type={result.MessageType} close={result.CloseStatus} desc={result.CloseStatusDescription}");
    }
    catch (Exception ex)
    {
        Console.WriteLine($"receive threw: {ex.GetType().Name}: {ex.Message} (state={ws.State})");
    }
}
Console.WriteLine("done");
