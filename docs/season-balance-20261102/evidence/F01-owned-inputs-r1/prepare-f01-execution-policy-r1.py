from pathlib import Path
import json, hashlib

b = Path(__file__).parent
repo = Path.cwd()
out = b / 'f01-execution-policy-r1.original.json'
assert not out.exists()
actor_file = b / 'f01-owned-input-preflight-r2/observations/declared-actors.original.json'
actors = json.loads(actor_file.read_bytes())
tables = json.loads((repo / 'client/data/catalog.json').read_bytes())['tables']
products = {row['product_id']: row for row in tables['SeasonShopProducts']}
assert products['equipment_fragments']['amount'] == 20 and products['equipment_fragments']['price_gold'] == 120
assert products['health_potion']['price_gold'] == 100 and products['health_potion']['daily_limit'] == 4
assert products['card_pack']['amount'] == 3 and products['card_pack']['price_gold'] == 250
assert len(actors['actors']) == 9
for actor in actors['actors']:
    assert len(actor['Cards']) == len(set(actor['Cards'])) == 20
    assert set(actor['PermanentCardLevels']) == ({0} if actor['Cohort'] == 'novice' else {5})
    assert actor['HistoricalOwnershipAssumed'] == (actor['Cohort'] != 'novice')
proposal = b / 'f01-14day-proposal-r1.original.json'
data = {
    'schema': 'f01-current17-runtime-policy-r1',
    'status': 'declared_for_controller_implementation_and_review; not executed or accepted',
    'config': actors['Version'], 'content_hash': actors['ContentHash'],
    'actor_file': str(actor_file), 'actor_sha256': hashlib.sha256(actor_file.read_bytes()).hexdigest(),
    'schedule': {'original_proposal': str(proposal), 'sha256': hashlib.sha256(proposal.read_bytes()).hexdigest(),
        'actors': 9, 'days': 14, 'per_actor_daily_start_limit': 2, 'maximum_starts': 252,
        'shanghai_hours': [9, 18], 'measurement_days': [1, 7, 14], 'shared_class_seeds': True,
        'maximum_simulated_seconds_per_attempt': 1200,
        'daily_timed_budget_seconds': 2400,
        'nonterminal': 'Retain the exact held assets/snapshot and censor the actor; never reset or requeue as a fresh account.'},
    'starting_assets': {'source': 'actual provisioning preflight plus explicitly declared historical permanent ownership',
        'season_gold': 0, 'season_fragments': 0, 'equipment': [], 'blueprints': 0, 'orange_blueprints': 0,
        'novice_permanent_levels': 0, 'returning_skilled_permanent_levels': 5,
        'old_D03_capital_imported': False, 'no_free_replacement_or_development_income': True},
    'entry': {'context': 'Bind original F01 season/config/stats and actual scheduled UTC start to every room.',
        'unlocks': 'Read actual player unlock progress and global published maximum; an input projection at D5 is not an unlock.',
        'levels': 'Use SeasonContext.ProjectPermanentLevel for each actually owned card/weapon; no automatic novice2.',
        'gear': 'Only current owned IDs, exact season domain, production entry quality checks and actual preparation holds.',
        'inventory': 'Bind actual preparation backpack/safe-slot/potion inputs. Do not carry D03 model50 warehouse cap as production capacity.',
        'borrowed': 'Baseline uses owned cards; no borrowed template or free borrowed levels are silently substituted.'},
    'risk_selection': {'order': 'Highest personally/global unlocked difficulty satisfying the registered risk profile and production entry checks.',
        'D0': 'Fallback when no higher profile is satisfied.',
        'D1': 'At least three blue-or-better distinct legal slots.',
        'D2': 'Five blue-or-better distinct legal slots, at least three purple-or-better and an actual activated equipment effect.',
        'D3_to_D5': 'Five legal slots, one orange and four purple-or-better, all+3, at least one actually active effect. No red requirement.',
        'consecutive_two_deaths': 'Reduce the eligible risk tier by one until the next successful extraction, respecting remaining owned gear.'},
    'route': {'name': 'natural-shortest', 'map': 'Actual generated map; no forced enemy groups, geometry, clears or drop results.',
        'path': 'Shortest path from actual spawn to actual boss, using fixed row/column order for ties.',
        'early_extract': 'Novice D0 with fewer than three worn pieces takes the first actual evacuation on that path.',
        'reaction_seconds': {'novice': 1.0, 'returning': 0.7, 'skilled': 0.5},
        'interpretation': 'Mechanical solo policies, not humans, native capacity, queues or PVP coverage.'},
    'lobby': {'ordering': ['collect only actual committed receipts', 'claim only earned available journey rewards',
        'exchange only earned shared activity tokens', 'learn owned eligible samples',
        'rebuild using real same-quality bodies and current mark/wish costs', 'enhance selected gear using real fragment costs',
        'perform affordable registered shop purchases', 'upgrade novice owned cards/weapon with actual earned soul/copy payments'],
        'marks': 'Use current SeasonCrafting.Payment/Wish and exact IDs. No body from a learned template without a physical input.',
        'enhancement': 'Use current actual armor costs; never project legal armor+3/+5 down to a card/weapon cap.',
        'permanent_upgrade': 'Novice upgrades only after exact current cost/copy payment, in deck-slot order; no fabricated level or initial soul budget.',
        'market': 'Self-sufficient baseline makes no market trades; do not invent counterparties or treat price/limit as revenue.'},
    'shop': {'actual_products': products,
        'priority': ['If insufficient rebuild fragments and gold>=120, at most one equipment_fragments product per actor/day.',
            'If no potion is owned and gold>=220, at most one health_potion product per actor/day, keeping120 gold for rebuilding.',
            'For novice only, warrior_soul then own-class soul if an actual next-level shortfall exists and payment leaves120 gold.'],
        'no_unpaid_or_limit_grants': True, 'baseline_card_pack_purchases': 0, 'baseline_bag_purchases': 0,
        'reset': 'Actual EconomySchedule.GetDailyResetKey at Shanghai04 and shared quota groups, not season midnight.'},
    'journey': {'sources': 'Only unique actual cleared-cell, extracted and earned weekly-contract sources with original occurrence times.',
        'dead_event_xp': 0, 'reference_experience_is_not_granted': True,
        'claim_policy': 'Claim earned levels immediately; own-hero class-soul choice and normal configured pack draws, with duplicates retained.',
        'no_automatic_full20_rewards': True},
    'activities': {'window': 'Actual configured12-14 and33-35 natural-day windows; no tokens outside the relevant event.',
        'novice': 'If six earned tokens are available, at most one event-potion; spend remaining affordable tokens on fragments.',
        'returning_skilled': 'Affordable fragment exchanges only.',
        'shared_budget': 'Use one event token balance/cap across all branches; unearned tokens and daily shop limits are not inventory.'},
    'potions': 'Use at most one actually prepared potion per attempt when Hp/MaximumHp<0.30; record actual consumption and recovery. No potion if none was paid/earned.',
    'red': 'Bind actual mint/quota admission or stop/censor on an unhandled red request; do not reuse D03 exhausted-quota assumption.',
    'measurements': ['day1/7/14 wallets, physical IDs and active holds', 'all permanent soul/copy/level changes separately from season currencies',
        'basic usable green/blue five-slot availability separately from first target piece, quality set and strict target diagnostic',
        'per-cohort nearest-rank P10/P50/P90 including right censoring; small named simulations, not population estimates',
        'actual source-minus-recovery per simulated hour; no wall-clock or queue extrapolation',
        'global/per-player unlocks and highest-open recommendation supported by actual successful/death/rebuild outcomes'],
    'acceptance': {'class_ratio_limit': 1.15, 'no_new_B05': True, 'D03_budget_not_reset': True,
        'F01_budget_answer_pending': True, 'new_gameplay_starts': 0,
        'unchanged_failures': 'Preserve old pacing, class-ratio, capacity and censored records; never pool development with independent holdouts.'},
    'controller_missing_before_timed_runs': ['F01-specific calendar/actual owned-input controller, not old fixed-Epoch D03 Run.',
        'Actual preparation inventory/potion/hold binding and paid novice permanent progression.',
        'Actual per-source journey/shop/activity claims and item/currency receipts, with no duplicated grants.',
        'Actual personal unlock and red admission binding; immutable per-start budget journal and checkpoints.',
        'Explicit F01 budget-accounting answer.']
}
out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'actors': 9, 'proposed_starts': 252, 'executed': 0, 'policy': str(out), 'controller_still_required': True}))
