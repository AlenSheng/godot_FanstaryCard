using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

// Cross-language fixtures use actual room previews and plays. Artificial hand,
// HP and equipment boundaries exercise formulas; they are not expedition results.
internal static class PreviewVectors
{
    public static int Run(string[] args)
    {
        var output = args[Array.IndexOf(args, "--output") + 1];
        var config = GameConfigCatalog.Current;
        var catalog = CombatCardCatalog.CreatePrototype();
        var random = new Random(20260930);
        string[] groups = ["O1", "O2", "O3", "O4", "O5", "O6", "M4", "E1", "E2", "E3", "E4", "E5", "BOSS", "BOX"];
        var vectors = new List<object>();
        for (var index = 0; index < 1800; index++)
        {
            var hero = Enum.GetValues<HeroClass>()[index % 3];
            var candidate = index / 18 % 2 == 0;
            var rules = new NumericalRules(CardsSpentDraw: candidate, FractionalGuardian: candidate);
            var equipment = new CombatEquipmentProfile(new(FireDamageBonus: .14, WoodDamageBonus: .08,
                WaterDamageBonus: .16, EarthDamageBonus: .10, MetalDamageBonus: .12),
                PiercingBonus: index % 3 * .03, BulwarkShieldBonus: .20,
                VitalityHealBonus: .15, VitalityOvercapBonus: index % 3 * .20);
            var room = new BattleRoom(Guid.NewGuid(), config.Version, catalog, index, rules);
            var player = room.AddPlayer(new(Guid.NewGuid(), hero, Enumerable.Repeat("C01", 20).ToArray(), null,
                WeaponLevel: index / 3 % 6, Equipment: equipment));
            var map = ChaosMapGenerator.Generate(index, 1).Capture();
            var cell = map.Cells.First(c => c.Layer == ChaosMapLayer.Outer);
            var group = groups[index % groups.Length];
            room.InitializeMap(ChaosMapState.Restore(map with
            {
                Cells = map.Cells.Select(c => c.Position == cell.Position ? c with { MonsterGroupId = group, IsBoss = group == "BOSS", TreasureElement = (CardElement)(1 + index % 5) } : c).ToArray(),
                SpawnPositions = [cell.Position]
            }));
            var combat = player.Combat.Capture();
            var candidates = config.Cards.Where(c => c.Enabled && (c.HeroClass is null || c.HeroClass == hero)).ToArray();
            var hand = Enumerable.Range(0, 1 + index % 5).Select(_ =>
            {
                var card = candidates[random.Next(candidates.Length)];
                var levels = config.CardLevels.Where(l => l.CardId == card.CardId).Select(l => l.Level).Append(0).Distinct().ToArray();
                return new CombatCardInstance(Guid.NewGuid(), card.CardId, levels[random.Next(levels.Length)],
                    card.CardId == "M-BOXSPIRIT" ? Enum.GetValues<CardElement>()[random.Next(6)] : null);
            }).ToArray();
            combat = combat with
            {
                Hp = index % 4 == 0 ? combat.MaximumHp : random.Next(1, combat.MaximumHp + 1),
                Shield = random.Next(combat.MaximumHp / 2 + 1),
                Deck = combat.Deck with { Hand = hand }, FenxianCombo = random.Next(8), LastFenxianCore = CardElement.Fire,
                GuardianShieldRemainderTenths = hero == HeroClass.Guardian && rules.FractionalGuardian ? random.Next(10) : 0
            };
            var snapshot = room.Capture();
            snapshot = snapshot with { Players = snapshot.Players.Select(p => p with
            {
                Combat = combat,
                Pve = p.Pve! with { Monsters = p.Pve.Monsters.Select(m => m with
                {
                    Hp = random.Next(1, m.MaximumHp + 1), Shield = random.Next(21),
                    IntentIndex = index % m.Intents.Count, BossPhase = 1 + index % 2
                }).ToArray() }
            }).ToArray() };
            room = BattleRoom.Restore(snapshot, catalog, index);
            player = room.GetPlayer(player.PlayerId);
            var pve = player.Pve!;
            var monster = pve.Monsters[0];
            pve.SelectTarget(monster.MonsterId);
            var intent = monster.Intents[monster.IntentIndex % monster.Intents.Count];
            var bonuses = new Dictionary<string, double>
            {
                ["piercing"] = equipment.PiercingBonus, ["bulwark_shield"] = equipment.BulwarkShieldBonus,
                ["vitality_heal"] = equipment.VitalityHealBonus, ["vitality_overcap"] = equipment.VitalityOvercapBonus
            };
            foreach (var element in Enum.GetValues<CardElement>()) bonuses["damage_" + element] = equipment.DamageBonus(element);
            var input = new
            {
                room_id = room.RoomId, allowed_actions = new[] { "battle.play_cards" },
                player = new
                {
                    hero_class = hero.ToString(), weapon_level = combat.WeaponLevel,
                    combat = new { hp = combat.Hp, shield = combat.Shield, maximum_hp = combat.MaximumHp },
                    hand = hand.Select(c => new { instance_id = c.InstanceId, card_id = c.CardId, level = c.Level, element_override = c.ElementOverride?.ToString() ?? "" }),
                    battle_status = new { combo = combat.FenxianCombo, core_element = combat.LastFenxianCore?.ToString(), bonuses = bonuses.Select(p => new { key = p.Key, value = p.Value }) },
                    numerical_state = new { fenxian_policy = combat.FenxianPolicy.ToString(), guardian_policy = combat.GuardianPolicy.ToString(), guardian_remainder_tenths = combat.GuardianShieldRemainderTenths }
                },
                pve = new { battle_id = pve.BattleId, current_target_id = monster.MonsterId, monsters = new[]
                {
                    new { monster_id = monster.MonsterId, hp = monster.Hp, shield = monster.Shield, intent_element = intent.Element.ToString(), boss_phase = monster.BossPhase }
                } }
            };
            var ids = hand.Select(c => c.InstanceId).ToArray();
            var before = JsonSerializer.Serialize(room.Capture());
            var expected = room.PreviewCards(player.PlayerId, pve.BattleId, monster.MonsterId, ids, room.Revision, DateTimeOffset.UnixEpoch);
            if (before != JsonSerializer.Serialize(room.Capture())) throw new InvalidOperationException("Preview changed authoritative state.");
            var played = room.PlayCards(player.PlayerId, pve.BattleId, monster.MonsterId, ids, room.Revision, DateTimeOffset.UnixEpoch);
            if (expected with { RoomRevision = played.RoomRevision } != played && JsonSerializer.Serialize(expected with { RoomRevision = played.RoomRevision }) != JsonSerializer.Serialize(played))
                throw new InvalidOperationException("Authoritative preview/play mismatch.");
            vectors.Add(new { index, room = input, ids, expected = new
            {
                damage = expected.Damage, shield_damage = expected.ShieldDamage, hp_damage = expected.HpDamage,
                heal = expected.Heal, shield_gain = expected.ShieldGain, health_cost = expected.HealthCost,
                draw_charge = expected.DrawCharge, immediate_draw = expected.ImmediateDraw,
                stun_seconds = expected.StunSeconds, draw_block_seconds = expected.DrawBlockSeconds,
                draw_block_speed_seconds = expected.DrawBlockSpeedSeconds,
                core_count = expected.CoreCount, core_element = expected.CoreElement?.ToString() ?? "",
                resonance_multiplier = expected.ResonanceMultiplier, conflict_pair_count = expected.ConflictPairCount,
                conflict_cancellation = expected.ConflictCancellation,
                damage_segments = expected.DamageSegments!.Select(s => new { kind = s.Kind, amount = s.Amount })
            } });
        }
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        File.WriteAllText(output, JsonSerializer.Serialize(new { schema_version = 1, seed = 20260930, count = vectors.Count, vectors }));
        Console.WriteLine($"Exported {vectors.Count} authoritative preview/play vectors");
        return 0;
    }
}
