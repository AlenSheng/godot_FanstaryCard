using System.Globalization;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

// Current contracts in real BattleRoom trajectories. This tool never activates
// candidates, and a one-item quality pair is not an isolated cap-effect estimate.
internal static class CapEffectiveExperiment
{
    private static readonly string[] Slots = ["Head", "Chest", "Hands", "Legs", "Feet"];
    private static readonly string[] Common = ["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C12", "C18", "C25", "C26", "C29"];
    private static readonly bool[] UpgradeArms = [false, true];
    internal static string Hash(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));

    public static int Run(string[] args)
    {
        if (args.Contains("--help", StringComparer.Ordinal))
        {
            Console.WriteLine("--cap-effective-experiment --source-sha <40hex> --output <new-directory> --hero Mage|Priest|Guardian --group O1|O6|E1|BOSS --element Fire|Wood|Earth|Metal|Water --equipment-level 0|5 --block-index 0|1|2 --samples 3|1000");
            return 0;
        }
        string Option(string key)
        {
            var index = Array.IndexOf(args, key);
            if (index < 0 || index + 1 >= args.Length) throw new ArgumentException("Missing frozen option: " + key);
            return args[index + 1];
        }
        var sha = Option("--source-sha"); var output = Path.GetFullPath(Option("--output"));
        var hero = Enum.Parse<HeroClass>(Option("--hero")); var element = Enum.Parse<CardElement>(Option("--element"));
        var group = Option("--group"); var level = int.Parse(Option("--equipment-level"), CultureInfo.InvariantCulture);
        var block = int.Parse(Option("--block-index"), CultureInfo.InvariantCulture); var samples = int.Parse(Option("--samples"), CultureInfo.InvariantCulture);
        if (!Regex.IsMatch(sha, "^[0-9a-f]{40}$") || Directory.Exists(output) || !Enum.IsDefined(hero) ||
            !Enum.IsDefined(element) || element == CardElement.None || group is not ("O1" or "O6" or "E1" or "BOSS") ||
            level is not (0 or 5) || block is < 0 or > 2 || samples is not (3 or 1000))
            throw new ArgumentException("Exact source, new output and declared bounded cap stratum required.");
        var config = GameConfigCatalog.Current; var catalog = CombatCardCatalog.CreatePrototype();
        var prefix = hero switch { HeroClass.Mage => "MAG", HeroClass.Priest => "PRI", _ => "GUA" };
        var deck = Common.Concat(Enumerable.Range(1, 6).Select(i => $"{prefix}-{i:D2}")).ToArray();
        CombatExperience.ValidateDeck(config, hero, deck); Directory.CreateDirectory(output);
        var seedStart = 440001 + 1000 * block; var rows = 0; var errors = 0; long encounterBytes = 0;
        using var encounterHash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        using var events = new CapEventParts(output);
        var counters = new Dictionary<string, long>(StringComparer.Ordinal);
        var equipment = UpgradeArms.Select(upgraded => Slots.Select((slot, index) =>
            new CombatEquipmentItem(new Guid(440001, 0, 0, 0, 0, 0, 0, 0, 0, 0, (byte)(index + 1)), slot,
                upgraded && index == 0 ? "Orange" : "Purple", level, element, "Bulwark", "DrawInterval")).ToArray()).ToArray();
        var profiles = equipment.Select(EquipmentCombatRules.Calculate).ToArray();
        var rawResistance = equipment.Select(items => items.Sum(item => config.EquipmentQuality(item.Quality).Resistance + item.Level * config.EquipmentQuality(item.Quality).ResistancePerLevel)).ToArray();
        File.WriteAllText(Path.Combine(output, "manifest.json"), JsonSerializer.Serialize(new
        {
            schema = "actual_cap_effective_experiment_v1", source_sha = sha, hero = hero.ToString(), group,
            element = element.ToString(), equipment_level = level, weapon_level = level, block_index = block,
            samples, seed_start = seedStart, deck, strategy = "basic", card_level = 0, cutoff_seconds = 600,
            equipment, profiles, raw_resistance = rawResistance, candidate_activation = false,
            quality_data = new { Purple = config.EquipmentQuality("Purple"), Orange = config.EquipmentQuality("Orange") },
            config_version = config.Version, config_sha256 = Hash(JsonSerializer.SerializeToUtf8Bytes(config)),
            shield_policy = "CurrentSteps", fenxian_policy = "CurrentRhythm", single_item_quality_change = true,
            outcome_effects_descriptive_only = true, independent_draw_oracle = "piecewise current state integration, full-hand reset"
        }));
        var rawPath = Path.Combine(output, "encounters.jsonl.gz");
        using (var gzip = new GZipStream(new FileStream(rawPath, FileMode.CreateNew), CompressionLevel.Fastest))
        for (var seed = seedStart; seed < seedStart + samples; seed++)
        for (var arm = 0; arm < 2; arm++)
        {
            var profileName = arm == 0 ? "BaselinePurple" : "SingleOrangeHead";
            var audit = new CapEncounterAudit(profiles[arm], element, rawResistance[arm], rawResistance[1] - rawResistance[0],
                Math.Min(.6, rawResistance[1]) - Math.Min(.6, rawResistance[0]), events, counters);
            var row = CombatExperience.Simulate(config, catalog, hero, "CapLegalTwenty", deck, group, "basic", profileName,
                config.Numerics, seed, block, 600, level, marginalAudit: true, capAudit: audit);
            if (row.Outcome == "Error") errors++;
            if (events.BudgetExceeded) throw new InvalidOperationException("Frozen event budget exceeded; preserve original partial files.");
            var bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(row) + "\n"); encounterBytes += bytes.Length;
            if (encounterBytes > 128 * 1024 * 1024) throw new InvalidOperationException("Encounter raw budget exceeded.");
            gzip.Write(bytes); encounterHash.AppendData(bytes); rows++;
        }
        events.Dispose();
        var passed = errors == 0 && rows == samples * 2 && !counters.Keys.Any(k => k.EndsWith("mismatch", StringComparison.Ordinal));
        var summary = new
        {
            passed, source_sha = sha, rows, errors, actual_casts = events.Casts, actual_ticks = events.Ticks,
            raw_bytes = encounterBytes, raw_sha256 = Convert.ToHexStringLower(encounterHash.GetHashAndReset()),
            stored_bytes = new FileInfo(rawPath).Length, stored_sha256 = Hash(File.ReadAllBytes(rawPath)),
            case_denominators = counters, event_parts = events.Parts, full_unit = samples == 1000,
            full_experiment_complete = false, required_cases_accepted = false, main_acceptance_granted = false
        };
        File.WriteAllText(Path.Combine(output, "summary.json"), JsonSerializer.Serialize(summary));
        Console.WriteLine(JsonSerializer.Serialize(summary)); return passed ? 0 : 1;
    }
}

internal sealed record CapPlayerState(int Hp, int MaximumHp, int Shield, int Hand, int AvailableCards,
    double Charge, double Interval, double SpeedModifier, long SpeedTicks, long ConversionTicks,
    long StunTicks, long BlockTicks, string FenxianPolicy, string ShieldPolicy)
{
    public static CapPlayerState Read(PlayerCombatState player) => new(player.Hp, player.MaximumHp, player.Shield,
        player.Deck.Hand.Count, player.Deck.Library.Count + player.Deck.Discard.Count, player.Deck.DrawCharge,
        player.DrawIntervalSeconds, player.DrawSpeedModifier, player.DrawSpeedRemaining.Ticks,
        player.DrawBlockSpeedRemaining.Ticks, player.StunRemaining.Ticks, player.DrawBlockRemaining.Ticks,
        player.FenxianDrawPolicy.ToString(), player.GuardianShieldPolicy.ToString());
}

internal sealed class CapEncounterAudit(CombatEquipmentProfile equipment, CardElement element,
    double rawResistance, double rawMarginal, double effectiveMarginal, CapEventParts events,
    Dictionary<string, long> counters)
{
    public CombatEquipmentProfile Equipment { get; } = equipment;
    private void Count(string arm, string name) => counters[arm + "/" + name] = counters.GetValueOrDefault(arm + "/" + name) + 1;
    private static bool Near(double a, double b) => Math.Abs(a - b) < 1e-9;
    public void Cast(EncounterSample row, double at, IReadOnlyList<CombatCardInstance> selected,
        IReadOnlyList<CombatCardDefinition> definitions, CapPlayerState before, CapPlayerState after,
        CardResolutionDraft draft, CombatResolution actual)
    {
        var cardShield = definitions.Sum(card => card.Effect.Shield);
        var healthCost = Math.Max(0, draft.HealthCost);
        var multiplier = row.Hero == "Guardian" ? 1 + .45 * Math.Clamp((double)Math.Max(1, before.Hp - healthCost) / before.MaximumHp, 0, 1) : 1;
        var flat = row.Hero != "Guardian" ? 0 : row.WeaponLevel >= 4 ? 3 : row.WeaponLevel >= 2 ? 2 : 1;
        var requested = cardShield <= 0 ? 0 : (int)Math.Floor(cardShield * multiplier * (1 + Equipment.BulwarkShieldBonus)) + flat;
        var effective = Math.Min(requested, before.MaximumHp / 2 - before.Shield);
        var passed = draft.Shield == requested && actual.ShieldGain == effective && after.Shield == before.Shield + effective &&
            after.Shield <= before.MaximumHp / 2 && before.FenxianPolicy == "CurrentRhythm" && before.ShieldPolicy == "CurrentSteps";
        Count(row.Profile, "all_casts");
        Count(row.Profile, cardShield > 0 ? "T03_positive_shield" : "T03_no_shield");
        if (cardShield > 0 && before.Shield == before.MaximumHp / 2) Count(row.Profile, "T03_full_shield");
        if (requested > effective) Count(row.Profile, "T03_overflow");
        if (!passed) Count(row.Profile, "cast_mismatch");
        events.Write(new
        {
            kind = "cast", row.Seed, row.SeedBlock, row.Hero, row.Group, row.Profile, action = row.Actions, at,
            selected = selected.Select((card, index) => new { card.InstanceId, card.CardId, card.Level, shield = definitions[index].Effect.Shield }),
            before, after, equipment = Equipment, weapon_level = row.WeaponLevel, card_shield = cardShield, health_cost = healthCost,
            requested = draft.Shield, effective = actual.ShieldGain, overflow = draft.Shield - actual.ShieldGain,
            independent_requested = requested, independent_effective = effective, candidate_activation = false, passed
        }, true);
        if (!passed) throw new InvalidOperationException("Independent current shield contract differs from actual room cast.");
    }
    public void Tick(EncounterSample row, int step, double at, bool drawEnabled, CapPlayerState before, CapPlayerState after)
    {
        const long delta = TimeSpan.TicksPerMillisecond * 100;
        var boundaries = new[] { 0L, delta, before.SpeedTicks, before.ConversionTicks, before.StunTicks, before.BlockTicks }
            .Where(t => t >= 0 && t <= delta).Distinct().Order().ToArray();
        var charge = before.Charge; var hand = before.Hand; var available = before.AvailableCards;
        foreach (var pair in boundaries.Zip(boundaries.Skip(1)))
        {
            if (!drawEnabled || pair.First < before.StunTicks || pair.First < before.BlockTicks) continue;
            var speed = pair.First < before.SpeedTicks ? before.SpeedModifier : 0;
            var rate = pair.First < before.ConversionTicks ? 2 : 1;
            charge += (pair.Second - pair.First) / (double)TimeSpan.TicksPerSecond / Math.Clamp(4 * (1 + Equipment.DrawIntervalModifier) * (1 + speed), 1.8, 6) * rate;
            while (charge >= 1)
            {
                if (hand >= 5) { charge = 0; break; }
                charge -= 1;
                if (available > 0) { available--; hand++; }
            }
        }
        var interval = Math.Clamp(4 * (1 + Equipment.DrawIntervalModifier) * (1 + before.SpeedModifier), 1.8, 6) / (before.ConversionTicks > 0 ? 2 : 1);
        var passed = !Equipment.HasRapidDraw && Near(Equipment.Resistance(element), Math.Min(.6, rawResistance)) &&
            (rawResistance < .6 || Near(effectiveMarginal, 0)) && Near(interval, before.Interval) && Near(charge, after.Charge) && hand == after.Hand &&
            after.SpeedTicks == Math.Max(0, before.SpeedTicks - delta) && after.ConversionTicks == Math.Max(0, before.ConversionTicks - delta) &&
            after.StunTicks == Math.Max(0, before.StunTicks - delta) && after.BlockTicks == Math.Max(0, before.BlockTicks - delta);
        Count(row.Profile, "all_ticks"); Count(row.Profile, rawResistance >= .6 ? "T01_capped_ticks" : "T01_below_cap_ticks");
        if (Math.Clamp(4 * (1 + Equipment.DrawIntervalModifier), 1.8, 6) == 1.8) Count(row.Profile, "T02_equipment_floor_ticks");
        if (before.SpeedTicks > 0) Count(row.Profile, "T02_card_speed_ticks");
        if (before.ConversionTicks > 0) Count(row.Profile, "T02_PVE_conversion_ticks");
        if (before.SpeedTicks is > 0 and <= delta || before.ConversionTicks is > 0 and <= delta) Count(row.Profile, "T02_expiry_ticks");
        if (!passed) Count(row.Profile, "tick_mismatch");
        events.Write(new
        {
            kind = "tick", row.Seed, row.SeedBlock, row.Hero, row.Group, row.Profile, step, at, draw_enabled = drawEnabled,
            before, after, equipment = Equipment, element = element.ToString(), raw_resistance = rawResistance,
            effective_resistance = Equipment.Resistance(element), raw_marginal = rawMarginal, effective_marginal = effectiveMarginal,
            independent_interval = interval, independent_charge_after = charge, independent_hand_after = hand, passed
        }, false);
        if (!passed) throw new InvalidOperationException("Independent cap/draw contract differs from advancing room tick.");
    }
}

internal sealed class CapEventParts(string output) : IDisposable
{
    public List<object> Parts { get; } = [];
    public long Casts { get; private set; }
    public long Ticks { get; private set; }
    public bool BudgetExceeded { get; private set; }
    private long _total, _partBytes, _partCount;
    private string? _path;
    private GZipStream? _gzip;
    private IncrementalHash? _hash;
    public void Write(object value, bool cast)
    {
        var bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(value) + "\n");
        if (_total + bytes.Length > 2147483648L) { BudgetExceeded = true; throw new InvalidOperationException("Original event budget exceeded."); }
        if (_gzip is null || _partBytes + bytes.Length > 128 * 1024 * 1024)
        {
            Close(); _path = Path.Combine(output, $"cap-events-{Parts.Count:D3}.jsonl.gz");
            _gzip = new(new FileStream(_path, FileMode.CreateNew), CompressionLevel.Fastest);
            _hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256); _partBytes = _partCount = 0;
        }
        _gzip.Write(bytes); _hash!.AppendData(bytes); _total += bytes.Length; _partBytes += bytes.Length; _partCount++;
        if (cast) Casts++; else Ticks++;
    }
    private void Close()
    {
        if (_gzip is null) return;
        _gzip.Dispose(); _gzip = null; var digest = Convert.ToHexStringLower(_hash!.GetHashAndReset()); _hash.Dispose(); _hash = null;
        Parts.Add(new { path = Path.GetFileName(_path), events = _partCount, raw_bytes = _partBytes, raw_sha256 = digest,
            stored_bytes = new FileInfo(_path!).Length, stored_sha256 = CapEffectiveExperiment.Hash(File.ReadAllBytes(_path!)) });
    }
    public void Dispose() => Close();
}
