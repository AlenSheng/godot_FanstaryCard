using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;

internal sealed class DeckDiagnosticObserver(CombatCardCatalog catalog, Action<object> write)
{
    private Dictionary<Guid, (string CardId, int Level)>? _original;
    private CombatDeckSnapshot? _tickBefore;
    private BattleRoomSnapshot? _beforeTickRoom;
    private readonly Dictionary<Guid, (string CardId, int Level)> _legalAdded = new();
    private Dictionary<CardElement, double> _firstCoreReady = new();
    private Dictionary<string, double> _reasonSeconds = new(StringComparer.Ordinal);
    private int _castCount;
    private int _reshuffles;
    private int _fullHpHealCasts;
    private int _lowHpNoDefenseTicks;
    private int _stateChecks;
    private object Identity(EncounterSample row) => new { row.Seed, row.SeedBlock, row.Hero, row.Deck, row.Group, row.Strategy, row.Profile };
    private static CombatCardInstance[] Pool(CombatDeckSnapshot d) => d.Hand.Concat(d.Library).Concat(d.Discard).ToArray();
    private static string Hash(object value) => Convert.ToHexStringLower(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(value)));
    private void Check(CombatDeckSnapshot d)
    {
        var cards = Pool(d);
        if (_original is null || cards.Length != 20+_legalAdded.Count || cards.Select(c => c.InstanceId).Distinct().Count() != cards.Length ||
            cards.Any(c => !(_original.TryGetValue(c.InstanceId, out var expected) || _legalAdded.TryGetValue(c.InstanceId,out expected)) || (c.CardId,c.Level)!=expected) ||
            _original.Keys.Any(id=>!cards.Any(c=>c.InstanceId==id)))
            throw new InvalidOperationException("Original twenty card identities changed during diagnostic encounter");
        _stateChecks++;
    }
    public void Entry(EncounterSample row, BattleRoom room, RoomPlayerState player)
    {
        var deck = player.Combat.Deck.Capture();
        var cards = Pool(deck);
        if (cards.Length != 20 || cards.Select(c => c.InstanceId).Distinct().Count() != 20 || cards.Any(c => c.Level != 0))
            throw new InvalidOperationException("Expected twenty unique level-zero initial instances");
        _original = cards.ToDictionary(c => c.InstanceId, c => (c.CardId, c.Level));
        Check(deck);
        write(new { kind = "entry", identity = Identity(row), original_instances = cards, hand = deck.Hand, library = deck.Library, discard = deck.Discard,
            player.Combat.Hp, player.Combat.MaximumHp, player.Combat.Shield, player.Combat.WeaponLevel, deck.DrawCharge,
            numerical_rules = room.Numerics, snapshot = room.Capture(), snapshot_sha256 = Hash(room.Capture()) });
    }
    public void BeforeTick(EncounterSample row, double time, BattleRoom room, RoomPlayerState player, bool strategyHold)
    {
        var deck = player.Combat.Deck.Capture(); Check(deck); _tickBefore = deck; _beforeTickRoom=room.Capture();
        var effects = deck.Hand.Select(c => catalog.Get(c.CardId, c.Level, c.ElementOverride).Effect).ToArray();
        var lowHp = player.Combat.Hp <= player.Combat.MaximumHp / 4;
        var hasDefense = effects.Any(e => e.Heal > 0 || e.Shield > 0 || e.StunSeconds > 0);
        if (lowHp && !hasDefense) _lowHpNoDefenseTicks++;
        var cores = effects.Where(e => e.ElementalDamage > 0 && e.SecondaryElementalDamage == 0 && e.Element != CardElement.None)
            .GroupBy(e => e.Element).Where(g => g.Count() >= 2).Select(g => g.Key).ToArray();
        foreach (var core in cores) _firstCoreReady.TryAdd(core, time);
        var reason = player.Combat.StunRemaining > TimeSpan.Zero ? "controlled" : deck.Hand.Count == 0 ?
            (deck.Library.Count == 0 && deck.Discard.Count > 0 ? "empty_hand_recyclable_discard" : "empty_hand") :
            strategyHold ? (deck.Hand.Count == CombatDeck.HandLimit ? "strategy_hold_full_hand" : "strategy_hold_building_core") :
            deck.Hand.Count == CombatDeck.HandLimit ? "full_hand_legal_action" : "legal_visible_hand";
        _reasonSeconds[reason] = _reasonSeconds.GetValueOrDefault(reason) + .1;
        // Log boundary transitions and once per second, without changing the simulation's tick or choice.
        if (Math.Abs(time - Math.Round(time)) < .000001 || reason == "empty_hand_recyclable_discard")
            write(new { kind = "waiting", identity = Identity(row), at_seconds = time, reason, strategy_hold = strategyHold,
                low_hp = lowHp, visible_defense = hasDefense, core_ready = cores, hp = player.Combat.Hp, max_hp = player.Combat.MaximumHp,
                shield = player.Combat.Shield, deck.Hand, deck.Library, deck.Discard, deck.DrawCharge,
                stun_ticks = player.Combat.StunRemaining.Ticks, draw_block_ticks = player.Combat.DrawBlockRemaining.Ticks });
    }
    public void AfterCast(EncounterSample row, double time, BattleRoomSnapshot before, BattleRoom room, RoomPlayerState player,
        CombatCardInstance[] selected, CombatCardDefinition[] definitions, CardResolutionDraft draft, CombatResolution result)
    {
        var oldPlayer = before.Players.Single(p => p.PlayerId == player.PlayerId);
        var deck = player.Combat.Deck.Capture(); TrackLegalMonsterAdds(row,time,before,room.Capture(),player); Check(deck); _castCount++;
        if (oldPlayer.Combat.Hp == oldPlayer.Combat.MaximumHp && definitions.Any(c => c.Effect.Heal > 0)) _fullHpHealCasts++;
        write(new { kind = "cast", identity = Identity(row), at_seconds = time, selected_instances = selected,
            before, before_sha256 = Hash(before), after = room.Capture(), after_sha256 = Hash(room.Capture()),
            requested = draft, actual = result, printed_heal = definitions.Sum(c => c.Effect.Heal),
            full_hp_before = oldPlayer.Combat.Hp == oldPlayer.Combat.MaximumHp,
            requested_heal = draft.Heal, effective_heal = result.Heal, heal_overflow = Math.Max(0, draft.Heal-result.Heal),
            core = result.CoreElement, core_count = result.CoreCount });
    }
    public void AfterTick(EncounterSample row, double time, BattleRoom room, RoomPlayerState player)
    {
        var after = player.Combat.Deck.Capture();
        if(_beforeTickRoom is null)throw new InvalidOperationException("Missing original pre-tick room");
        TrackLegalMonsterAdds(row,time,_beforeTickRoom,room.Capture(),player); Check(after);
        if (_tickBefore is null) throw new InvalidOperationException("Missing before-Advance observation");
        var beforeIds = _tickBefore.Hand.Select(c => c.InstanceId).ToHashSet();
        var drawn = after.Hand.Where(c => !beforeIds.Contains(c.InstanceId)).ToArray();
        if (_tickBefore.Library.Count == 0 && _tickBefore.Discard.Count > 0 && drawn.Length > 0)
        {
            if (!drawn.All(c => _tickBefore.Discard.Any(d => d.InstanceId == c.InstanceId)))
                throw new InvalidOperationException("Draw from exhausted library was not a retained discard instance");
            _reshuffles++; write(new { kind = "reshuffle_draw", identity = Identity(row), at_seconds = time, before = _tickBefore,
                after, drawn_original_instances = drawn, all_twenty_original_instances_preserved = true });
        }
        else if (drawn.Length > 0) write(new { kind = "natural_draw", identity = Identity(row), at_seconds = time,
            drawn_original_instances = drawn, hand = after.Hand, library_count = after.Library.Count, discard_count = after.Discard.Count });
        _tickBefore = null;
        _beforeTickRoom=null;
    }
    public void Exit(EncounterSample row)
    {
        write(new { kind = "exit", identity = Identity(row), outcome = row.Outcome, error = row.Error, observed_seconds = row.ObservedSeconds,
            actual_casts = _castCount, original_instance_state_checks = _stateChecks, original_twenty_retained=true,
            legal_kill_added_instances=_legalAdded.Keys, real_reshuffle_draws = _reshuffles,
            full_hp_heal_casts = _fullHpHealCasts, low_hp_no_visible_defense_ticks = _lowHpNoDefenseTicks,
            first_visible_two_card_core_seconds = _firstCoreReady, waiting_reason_seconds = _reasonSeconds,
            row.Actions, row.EffectiveActions, row.ZeroEffectiveActions, row.HealOverflow, row.ShieldOverflow,
            row.CardsSpent, row.NaturalCardsDrawn, row.ImmediateCardsDrawn, row.FinalPoolSize });
    }
    private void TrackLegalMonsterAdds(EncounterSample row,double time,BattleRoomSnapshot before,BattleRoomSnapshot after,RoomPlayerState player)
    {
        var old=before.Players.Single(p=>p.PlayerId==player.PlayerId);var next=after.Players.Single(p=>p.PlayerId==player.PlayerId);
        var oldIds=Pool(old.Combat.Deck).Select(c=>c.InstanceId).ToHashSet();var added=Pool(next.Combat.Deck).Where(c=>!oldIds.Contains(c.InstanceId) && !_legalAdded.ContainsKey(c.InstanceId)).ToArray();
        if(added.Length==0)return;
        var prior=old.Pve?.Monsters ?? [];var current=next.Pve?.Monsters ?? [];
        var defeated=prior.Where(m=>m.Hp>0 && current.Any(n=>n.MonsterId==m.MonsterId && n.Hp<=0)).ToArray();
        if(added.Length>defeated.Length)throw new InvalidOperationException("New pool instances exceed actual newly defeated monsters");
        var remaining=defeated.ToList();
        foreach(var card in added)
        {
            var definition=GameConfigCatalog.Current.Cards.Single(c=>c.CardId==card.CardId);
            var source=remaining.FirstOrDefault(m=>Species(m.MonsterId)==definition.MonsterType);
            if(source is null || definition.MonsterType is null || card.Level!=0 || _original!.ContainsKey(card.InstanceId))
                throw new InvalidOperationException("New card instance has no actual legal matching kill source");
            remaining.Remove(source);_legalAdded.Add(card.InstanceId,(card.CardId,card.Level));
            write(new {kind="legal_kill_card",identity=Identity(row),at_seconds=time,source_monster_id=source.MonsterId,
                source_monster_type=definition.MonsterType,card,original_twenty_retained=true,before_sha256=Hash(before),after_sha256=Hash(after),before,after});
        }
    }
    private static string? Species(string id)
    {
        if(id.EndsWith("-a",StringComparison.Ordinal)||id.EndsWith("-b",StringComparison.Ordinal))id=id[..^2];
        return id switch {"fire-bat"=>"FireBat","thorn-mite"=>"ThornMite","murk-snail"=>"MudHydra","sand-lizard"=>"SandLizard",
            "rust-rat"=>"RustRat","box-spirit"=>"BoxSpirit","metal-guard"=>"GoldGuard","fire-herald"=>"FireReaver",
            "marsh-mother"=>"SwampMother","stone-guard"=>"StoneGuard","thorn-guard"=>"ThornGuard","annihilation-core"=>"VoidCore",_=>null};
    }
}
