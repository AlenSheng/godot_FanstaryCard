using System.Text.Json;
using FantasyCard.Contracts.Realtime;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class MonsterPoolCapacityGodotWireTests
{
    private static readonly bool[] Decisions = [false, true];
    [Fact]
    public void Client_choices_are_decoded_by_the_native_server_codec()
    {
        var path = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_POOL_CAPACITY_GODOT_COMMANDS");
        if (string.IsNullOrWhiteSpace(path))
        {
            // Ordinary CI retains a codec check; the cloud interoperability
            // profile separately requires all original Godot-produced commands.
            foreach (var accept in Decisions)
            {
                var command = new ClientCommand("monster.choose", "ci-choice", 1,
                    new MonsterCardChooseCommandPayload(Guid.NewGuid(), accept));
                Assert.Equivalent(command, RealtimeProtobufCodec.DecodeClient(RealtimeProtobufCodec.EncodeClient(command)), strict: true);
            }
            return;
        }
        var count = 0;
        var counts = new Dictionary<string, int>();
        var originalsPath = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_POOL_CAPACITY_NATIVE_COMMANDS");
        Assert.False(string.IsNullOrWhiteSpace(originalsPath));
        var originals = File.ReadLines(originalsPath!).Select(line =>
            RealtimeProtobufCodec.DecodeClient(Convert.FromBase64String(JsonSerializer.Deserialize<JsonElement>(line).GetProperty("request_wire").GetString()!)))
            .ToDictionary(command => (command.RoomId, command.RequestId));
        Assert.Equal(279, originals.Count);
        foreach (var line in File.ReadLines(path))
        {
            var row = JsonSerializer.Deserialize<JsonElement>(line);
            Assert.Equal(Environment.GetEnvironmentVariable("FANTASYCARD_PR13_SOURCE_SHA"), row.GetProperty("source_sha").GetString());
            var decoded = RealtimeProtobufCodec.DecodeClient(Convert.FromBase64String(row.GetProperty("wire").GetString()!));
            Assert.Equal("monster.choose", decoded.Type);
            Assert.Equal(Guid.Parse(row.GetProperty("room_id").GetString()!), decoded.RoomId);
            Assert.Equal(row.GetProperty("request_id").GetString(), decoded.RequestId);
            Assert.Equal(row.GetProperty("expected_revision").GetInt64(), decoded.ExpectedRevision);
            Assert.True(originals.Remove((decoded.RoomId, decoded.RequestId), out var expected));
            Assert.Equivalent(expected, decoded, strict: true);
            var choice = Assert.IsType<MonsterCardChooseCommandPayload>(decoded.Payload);
            Assert.Equal(Guid.Parse(row.GetProperty("candidate_id").GetString()!), choice.CandidateId);
            Assert.Equal(row.GetProperty("accept").GetBoolean(), choice.Accept);
            var replacement = row.GetProperty("replacement").GetString();
            Assert.Equal(string.IsNullOrEmpty(replacement) ? (Guid?)null : Guid.Parse(replacement), choice.ReplaceInstanceId);
            var caseId = row.GetProperty("case_id").GetString()!;
            counts[caseId] = counts.GetValueOrDefault(caseId) + 1;
            count++;
        }
        Assert.Equal(279, count);
        Assert.Empty(originals);
        Assert.Equal(144, counts["PR13-B09.2-T01"]); Assert.Equal(81, counts["PR13-B09.2-T02"]); Assert.Equal(54, counts["PR13-B09.2-T03"]);
        var result = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_POOL_CAPACITY_GODOT_RECEIPT");
        Assert.False(string.IsNullOrWhiteSpace(result));
        File.WriteAllText(result!, JsonSerializer.Serialize(new { ok = true, source_sha = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_SOURCE_SHA"),
            original_Godot_commands_decoded = count, case_rows = counts, fallback_native_CI_used = false }));
    }
}
