"""Account for the additional SeasonJourney source, independently of activity.

This is deterministic configuration arithmetic, not a route, cohort, claim or
currency simulation. No workbook, runtime configuration or database is edited.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
from hashlib import sha256
from itertools import product
import json
from pathlib import Path


RESOURCE_KINDS = ("EquipmentFragments", "WarriorSoul", "ClassSoul", "CardPack")
HEROES = ("Mage", "Priest", "Guardian")


def ratio(value: Fraction) -> dict:
    return {"exact": str(value), "decimal": round(float(value), 9)}


def build(catalog: dict) -> dict:
    tables = catalog["tables"]
    rewards = sorted(tables["SeasonJourneyRewards"], key=lambda row: row["level"])
    levels = sorted(tables["SeasonProgression"], key=lambda row: row["level"])
    cosmetics = {row["cosmetic_id"]: row for row in tables["SeasonCosmetics"]}
    shop = {row["product_id"]: row for row in tables["SeasonShopProducts"]}
    rule, = tables["SeasonShopRules"]
    assert [row["level"] for row in rewards] == list(range(1, 31))
    assert [row["level"] for row in levels] == list(range(30))
    assert [row["xp_to_next_42"] for row in levels] == [200 + 15 * level for level in range(30)]
    cycle = [("EquipmentFragments", 10), ("WarriorSoul", 6), ("ClassSoul", 2),
             ("EquipmentFragments", 10), ("CardPack", 1)]
    for row in rewards[:20]:
        assert (row["kind"], row["amount"]) == cycle[(row["level"] - 1) % 5]
        assert row["ownership"] == ("SeasonalBound" if row["kind"] == "EquipmentFragments" else "PermanentBound")
        assert row["requires_class_choice"] is (row["kind"] == "ClassSoul")
        assert row["cosmetic_id"] is None
    bonus_ids = [row["cosmetic_id"] for row in rewards[20:]]
    assert len(set(bonus_ids)) == len(cosmetics) == 10 and set(bonus_ids) == set(cosmetics)
    assert all(row["kind"] == "Cosmetic" and row["amount"] == 1
               and row["ownership"] == "PermanentBound" and not row["requires_class_choice"]
               for row in rewards[20:])
    assert rule["pack_cards"] == 3
    weights = {kind: rule[kind.lower() + "_weight"] for kind in ("White", "Green", "Blue", "Purple")}
    assert all(isinstance(value, int) and value >= 0 for value in weights.values()) and sum(weights.values()) == 100

    cumulative = []
    resources: Counter = Counter()
    for row in [{"level": 0, "kind": None, "amount": 0}] + rewards:
        if row["kind"] in RESOURCE_KINDS:
            resources[row["kind"]] += row["amount"]
        cumulative.append({"level": row["level"],
                           "new_source_if_all_eligible_claimed": {kind: resources[kind] for kind in RESOURCE_KINDS},
                           "actual_card_copies": resources["CardPack"] * rule["pack_cards"],
                           "permanent_cosmetics": max(0, row["level"] - 20)})
    full = cumulative[20]["new_source_if_all_eligible_claimed"]
    assert full == {"EquipmentFragments": 80, "WarriorSoul": 24, "ClassSoul": 8, "CardPack": 4}
    assert cumulative[20]["actual_card_copies"] == 12
    assert all(row["new_source_if_all_eligible_claimed"] == full for row in cumulative[21:])

    # Four separate two-soul awards choose one class each. They never give
    # eight to every class. Enumerate the 81 possible choices, not matches.
    allocations = set()
    for choices in product(range(3), repeat=4):
        amounts = [2 * choices.count(index) for index in range(3)]
        assert sum(amounts) == 8
        allocations.add(tuple(amounts))
    assert len(allocations) == 15

    prices = {
        "EquipmentFragments": Fraction(shop["equipment_fragments"]["price_gold"], shop["equipment_fragments"]["amount"]),
        "WarriorSoul": Fraction(shop["warrior_soul"]["price_gold"], shop["warrior_soul"]["amount"]),
        "ClassSoul": Fraction(shop["mage_soul"]["price_gold"], shop["mage_soul"]["amount"]),
        "CardPack": Fraction(shop["card_pack"]["price_gold"]),
    }
    assert shop["card_pack"]["amount"] == rule["pack_cards"]
    assert all((shop[name + "_soul"]["amount"], shop[name + "_soul"]["price_gold"], shop[name + "_soul"]["quota_group"])
               == (12, 400, "class_soul") for name in ("mage", "priest", "guardian"))
    shadow = sum((prices[kind] * full[kind] for kind in RESOURCE_KINDS), Fraction())
    assert shadow == Fraction(5888, 3)

    duration_rows = []
    for days in (30, 42, 60):
        # Same per-level ceiling as the original source contract. Durations
        # above 42 days do not increase the required experience or rewards.
        costs = [(row["xp_to_next_42"] * min(days, 42) + 41) // 42 for row in levels]
        duration_rows.append({"duration_days": days, "level20_experience": sum(costs[:20]),
                              "level30_experience": sum(costs), "total_if_all_main_claimed": full,
                              "uniform_daily_equivalent_only": {kind: ratio(Fraction(full[kind], days)) for kind in RESOURCE_KINDS}})
    return {
        "scope": "deterministic configuration budget; not live claims, routes, cohorts, P50/P90 or a macroeconomy pass",
        "source": "SeasonJourney", "activity_source_added": False,
        "configuration_version": catalog["version"],
        "levels": cumulative, "main_total_if_all_claimed": full, "card_copies_if_all_packs_claimed": 12,
        "unclaimed_entitlement_minted_assets": 0,
        "cosmetic_counts": dict(sorted(Counter(row["kind"] for row in cosmetics.values()).items())),
        "direct_other_sources": {"Gold": 0, "Diamonds": 0, "Equipment": 0, "RedEquipment": 0, "RedMaterials": 0},
        "class_allocation_choice_sequences": 81,
        "class_allocations": [dict(zip(HEROES, amounts)) for amounts in sorted(allocations)],
        "expected_copy_quality_only": {kind: ratio(Fraction(12 * weight, 100)) for kind, weight in weights.items()},
        "shop_shadow_purchase_cost_gold": ratio(shadow), "shadow_cost_is_minted_gold": False,
        "shadow_cost_is_realized_sink_reduction": False,
        "duration_sensitivity": duration_rows,
        "accounting_rules": [
            "Only successfully committed claims mint assets; pending, rolled-back and replayed claims add no new source.",
            "EquipmentFragments belong to the originating seasonal wallet, including a late archived-season claim.",
            "Soul and actual card-copy assets are permanent and retain their originating season/configuration in their ledgers.",
            "Four two-soul awards select one class each; never add the combined eight to all three classes.",
            "Cosmetics are permanent bound display entitlements, with no salvage, gold, combat or equipment source.",
            "Activity branches retain their shared activity budget; do not count journey rewards as event exchange rewards.",
            "Daily equivalents are smoothing references, not guaranteed completion, daily rewards or a measured cohort.",
            "Do not subtract shop shadow cost from fixed-frequency shop sinks; substitution needs actual stock, demand and integer purchases.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path(__file__).resolve().parents[1] / "client/data/catalog.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.catalog.read_bytes()
    report = build(json.loads(raw))
    report["catalog_sha256"] = sha256(raw).hexdigest()
    report["checker_sha256"] = sha256(Path(__file__).read_bytes()).hexdigest()
    # Evidence is append-only. A revised input or checker needs a new output.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"output": str(args.output), "source": report["source"], "all_main_claimed": report["main_total_if_all_claimed"]}))


if __name__ == "__main__":
    main()
