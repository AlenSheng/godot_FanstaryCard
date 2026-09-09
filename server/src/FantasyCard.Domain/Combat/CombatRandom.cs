namespace FantasyCard.Domain.Combat;

public sealed class CombatRandom : Random
{
    private const ulong Multiplier = 2685821657736338717UL;
    private ulong _state;

    public CombatRandom(int seed)
    {
        var value = unchecked((ulong)(uint)seed) + 0x9E3779B97F4A7C15UL;
        value = (value ^ (value >> 30)) * 0xBF58476D1CE4E5B9UL;
        value = (value ^ (value >> 27)) * 0x94D049BB133111EBUL;
        _state = value ^ (value >> 31);
        if (_state == 0)
        {
            _state = 0xA0761D6478BD642FUL;
        }
    }

    public ulong State => _state;

    public void Restore(ulong state)
    {
        if (state == 0)
        {
            throw new ArgumentOutOfRangeException(nameof(state), "Combat RNG state cannot be zero.");
        }
        _state = state;
    }

    public override int Next() => Next(int.MaxValue);

    public override int Next(int maxValue)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(maxValue);
        return maxValue == 0 ? 0 : (int)(NextUInt64() % (uint)maxValue);
    }

    public override int Next(int minValue, int maxValue)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(maxValue, minValue);
        var range = (long)maxValue - minValue;
        return range == 0 ? minValue : (int)(minValue + (long)(NextUInt64() % (ulong)range));
    }

    public override double NextDouble() => Sample();

    protected override double Sample() =>
        (NextUInt64() >> 11) * (1.0 / (1UL << 53));

    private ulong NextUInt64()
    {
        var value = _state;
        value ^= value >> 12;
        value ^= value << 25;
        value ^= value >> 27;
        _state = value;
        return value * Multiplier;
    }
}
