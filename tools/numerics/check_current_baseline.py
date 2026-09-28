#!/usr/bin/env python3
"""Independent arithmetic fixtures for the approved b7a6154 CombatResolver.
Not a replacement for executing the production C# resolver or whole-game tests.
Run with Python 3.10+: python tools/numerics/check_current_baseline.py
"""
from __future__ import annotations
import json
import math
from dataclasses import dataclass
from pathlib import Path

SOURCE_COMMIT = 'b7a6154f7ca3a2a95993a1c7592c4ffef4aa134e'
SOURCE_BLOB = '5ae7074f0c36d394043e6c33c862792c5da1eccf'
CONFLICTS = {frozenset(pair) for pair in [('Wood','Earth'),('Earth','Water'),
    ('Water','Fire'),('Fire','Metal'),('Metal','Wood')]}

@dataclass(frozen=True)
class Card:
    element: str = 'None'
    damage: int = 0
    tune: bool = False
    fuel: int = 0
    direct: int = 0
    secondary_element: str = 'None'
    secondary: int = 0
    resonance_bonus: int = 0
    cancel_bonus: float = 0.0
    heal_coefficient: float = 0.0
    reveal: bool = False


def resolve(cards: list[Card], bonus: dict[str,float] | None = None,
            resistance: dict[str,float] | None = None, piercing: float = 0.0,
            vitality: float = 0.0, display_element: str = 'Fire') -> dict:
    if not cards or len(cards) > 5:
        raise ValueError('Fixtures must contain one to five cards.')
    bonus, resistance = bonus or {}, resistance or {}
    singles = [c for c in cards if c.damage > 0 and c.element != 'None' and c.secondary == 0]
    counts = {e: sum(c.element == e for c in singles) for e in {c.element for c in singles}}
    reveal = any(c.reveal for c in cards)
    bases = []
    for c in cards:
        value = c.damage + c.fuel * max(0, counts.get(c.element, 0) - 3)
        bases.append(math.floor(value * 1.3) if reveal and c.element == display_element else value)
    core, r, p, k, d, conflict_heal = None, 0, 0, 1.0, 0.0, 0
    segments: list[int] = []
    def conflict(a: str, b: str) -> bool:
        return a != b and frozenset((a,b)) in CONFLICTS
    def multiplier(e: str) -> float:
        return (1 + bonus.get(e, 0)) * (1 - resistance.get(e, 0))
    if singles:
        core = singles[0].element
        r = counts[core]
        p = sum(c.element != core and not c.tune and conflict(core,c.element) for c in singles)
        b = int(any(c.resonance_bonus > 0 for c in cards))
        k = 1 + .20 * max(0, r - 1 + b - p)
        s = multiplier(core)
        d = 0 if p == 0 else min(.80, .20 * p + max(c.cancel_bonus for c in cards))
        core_base = sum(v for c,v in zip(cards,bases)
                        if c.element == core and c.secondary == 0 and not c.tune)
        if p:
            coefficient = max(.50, max(c.heal_coefficient for c in cards))
            conflict_heal = math.floor((math.floor(core_base * s * k * d * coefficient) + 2*p) * (1+vitality))
        for c,v in zip(cards,bases):
            if c.damage <= 0 or c.element == 'None' or c.secondary != 0:
                continue
            branch = k if c.element == core else 1-d if conflict(core,c.element) and not c.tune else 1
            segments.append(max(0, math.floor(v * s * branch)))
    for c,v in zip(cards,bases):
        if c.secondary <= 0:
            continue
        secondary = math.floor(c.secondary * 1.3) if reveal and c.secondary_element == display_element else c.secondary
        for e,value in [(c.element,v),(c.secondary_element,secondary)]:
            segments.append(max(0, math.floor(value * multiplier(core or e))))
    direct = sum(c.direct for c in cards)
    for c,v in zip(cards,bases):
        secondary = math.floor(c.secondary * 1.3) if reveal and c.secondary_element == display_element else c.secondary
        direct += math.floor((v + secondary + c.direct) * piercing)
    return dict(core=core, R=r, P=p, K=k, D=d, elemental=sum(segments), direct=direct,
                damage=sum(segments)+direct, conflict_heal=conflict_heal)


def main() -> None:
    cases = []
    def add(name, cards, expected_damage, **kwargs):
        actual = resolve(cards, **kwargs)
        assert actual['damage'] == expected_damage, (name, actual, expected_damage)
        cases.append(dict(name=name, expected=actual))
    for n,expected in [(1,10),(2,24),(3,42),(4,64),(5,90)]:
        add(f'pure_R{n}', [Card('Fire',10)]*n, expected)
    gear = dict(bonus={'Fire':.14}, resistance={'Fire':-.30})
    add('A_three_fire', [Card('Fire',8),Card('Fire',3),Card('Fire',12,fuel=2)],46,**gear)
    add('A_four_fire', [Card('Fire',8),Card('Fire',3),Card('Fire',12,fuel=2),Card('Fire',6)],72,**gear)
    add('A_five_fire', [Card('Fire',8),Card('Fire',3),Card('Fire',12,fuel=2),Card('Fire',6),Card('Fire',10)],113,**gear)
    add('first_not_majority', [Card('Fire',8),Card('Water',7),Card('Water',7)],23,**gear)
    add('tie_fire_first', [Card('Fire',8),Card('Water',7)],19,**gear)
    add('tie_water_first', [Card('Water',7),Card('Fire',8)],6,
        bonus={'Fire':.14},resistance={'Fire':-.30,'Water':.50})
    add('unrelated_retains_damage', [Card('Fire',8),Card('Wood',7)],21,**gear)
    add('tune_can_be_core', [Card('Fire',4,tune=True),Card('Fire',8)],13)
    add('noncore_tune_no_P', [Card('Fire',8),Card('Water',5,tune=True)],13)
    add('tune_excluded_from_conflict_heal', [Card('Fire',8),Card('Fire',4,tune=True),Card('Water',7)],17)
    assert cases[-1]['expected']['conflict_heal'] == 2
    add('P4_D80', [Card('Fire',8),Card('Water',7),Card('Water',7),Card('Metal',7),Card('Metal',7)],12)
    add('resonance_bonus_does_not_stack', [Card('Fire',10),Card('Fire',10),Card(resonance_bonus=1),Card(resonance_bonus=1)],28)
    add('cancel_bonus_ignored_without_P', [Card('Fire',10),Card(cancel_bonus=.50)],10)
    boss = Card('Fire',8,secondary_element='Metal',secondary=8)
    add('boss_without_core_own_resistance', [boss],14,
        bonus={'Fire':.14},resistance={'Fire':-.30,'Metal':.60})
    add('boss_with_core_shared_resistance', [Card('Water',7),boss],12,
        bonus={'Water':.20},resistance={'Water':.50,'Fire':-.30,'Metal':.60})
    add('direct_and_piercing', [Card('Fire',8),Card(direct=6)],19,piercing=.24,**gear)
    add('reveal_before_branch', [Card('Fire',8),Card('Water',8),Card(reveal=True)],16)
    add('tune_counts_towards_fuel', [Card('Fire',8),Card('Fire',4,tune=True),Card('Fire',6),Card('Fire',12,fuel=2)],49)
    add('floor_each_not_total', [Card('Fire',3)]*3,12,bonus={'Fire':.14})
    add('no_element_no_core', [Card()],0)
    # A bounded-card-consumption property of the PROPOSED mage change only.
    candidate = []
    for r in range(1,6):
        immediate = (r-1)//2
        rebate = immediate + .50
        assert rebate < r
        candidate.append(dict(R=r,immediate=immediate,max_passive_card_equivalent=rebate,spent=r))
    result = dict(source_commit=SOURCE_COMMIT, source_blob=SOURCE_BLOB,
                  validation='Independent Python arithmetic; production C# NOT executed',
                  case_count=len(cases), cases=cases, proposed_mage_bound=candidate)
    output = Path(__file__).with_name('baseline_results.json')
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(cases)} arithmetic fixtures passed; 5 proposed mage cost bounds passed.')
    print('Production C# execution, card catalog legality, end-to-end and balance simulations remain pending.')
    print(output)

if __name__ == '__main__':
    main()
