using System.Net.WebSockets;
using FantasyCard.Contracts.Realtime;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    private static async Task PumpLegacySnapshotReadsAsync(WebSocket source, WebSocket destination,
        Action<ClientCommand, byte[], byte[]> observe, CancellationToken ct)
    {
        // Replay the pre-selector read contract while preserving authentication,
        // request identity, real server execution and every recovery assertion.
        var buffer = new byte[65536];
        using var pending = new MemoryStream();
        while (source.State == WebSocketState.Open && destination.State == WebSocketState.Open)
        {
            var frame = await source.ReceiveAsync(new ArraySegment<byte>(buffer), ct);
            if (frame.MessageType == WebSocketMessageType.Close) break;
            pending.Write(buffer, 0, frame.Count);
            if (pending.Length > 65536) throw new InvalidDataException("The owned fixture frame is too large.");
            if (!frame.EndOfMessage) continue;
            var packet = pending.ToArray(); pending.SetLength(0);
            if (frame.MessageType == WebSocketMessageType.Binary)
            {
                var command = RealtimeProtobufCodec.DecodeClient(packet);
                if (command.Type == "room.snapshot.read")
                {
                    var legacy = RealtimeProtobufCodec.EncodeClient(command with { RoomId = null, MatchId = null });
                    observe(command, packet, legacy);
                    packet = legacy;
                }
            }
            await destination.SendAsync(new ArraySegment<byte>(packet), frame.MessageType, true, ct);
        }
    }
}
