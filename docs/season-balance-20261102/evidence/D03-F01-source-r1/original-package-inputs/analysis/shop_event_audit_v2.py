#!/usr/bin/env python3
"""Reproduce the shop/event budget audit; no game server or workbook is edited.

All existing shop values are transcribed from GDD_BASE_v0.69 section 6.2.
Difficulty, route, enhancement and event values are candidate assumptions.
Run: python shop_event_audit_v2.py [season_model.json] [output_directory]
"""
from __future__ import annotations
import json
import sys
from fractions import Fraction as Q
from math import ceil, floor
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / 'season_model.json'
OUT = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else HERE
MODEL = json.loads(INPUT.read_text())
OUT.mkdir(parents=True, exist_ok=True)

def q(value):
    return Q(str(value))

def n(value):
    if isinstance(value, Q):
        return int(value) if value.denominator == 1 else round(float(value), 9)
    if isinstance(value, dict):
        return {k:n(v) for k,v in value.items()}
    if isinstance(value, list):
        return [n(v) for v in value]
    return value

SHOP = {
    'fragment': {'price':120, 'quantity':20, 'daily_cap':3},
    'warrior_soul': {'price':180, 'quantity':20, 'daily_cap':3},
    'class_soul': {'price':400, 'quantity':12, 'daily_cap':1},
    'card_pack': {'price':250, 'quantity':3, 'daily_cap':5},
    'potion': {'price':100, 'quantity':1, 'daily_cap':4, 'inventory_cap':8, 'carry_cap':2},
    'advanced_bag': {'price':800, 'capacity':28, 'safe_slots':1},
    'top_bag': {'price':2200, 'capacity':36, 'safe_slots':3},
}
EVENT = {
    'status':'proposed_not_current', 'season_days':42, 'event_count':2,
    'duration_days_each':3, 'tokens_per_event':12,
    'participation':q('.6'), 'completion_conditional':q('.8'), 'redemption_conditional':q('.9'),
    'direct_gold':0, 'direct_diamonds':0, 'direct_equipment':0,
}
P = q(MODEL['assumptions']['extractionRate'])
T = q(MODEL['assumptions']['minutesPerAttempt'])
DIFF = next(d for d in MODEL['difficulties'] if d['id']=='D2')
LAYERS = MODEL['layers']
COUNTS = MODEL['route']['counts']
GOLD = sum(c*floor(q(l['gold'])*q(DIFF['goldScale'])) for c,l in zip(COUNTS,LAYERS))
FRAG = sum(c*sum(floor(i*q(DIFF['fragmentScale'])) for i in range(l['fragmentMin'],l['fragmentMax']+1))/Q(l['fragmentMax']-l['fragmentMin']+1) for c,l in zip(COUNTS,LAYERS))
FRAG_UNIT_GOLD = Q(SHOP['fragment']['price'], SHOP['fragment']['quantity'])
CHOICE = {'gear_rate':q('.75'),'fragment_rate':q('.15'),'healing_rate':q('.10'),
          'double_bias_conditional_rate':q('.5'),'status':'proposed_not_measured'}
FRAG_DOUBLE = sum(c*sum(floor(i*q(DIFF['fragmentScale'])*2) for i in range(l['fragmentMin'],l['fragmentMax']+1))/Q(l['fragmentMax']-l['fragmentMin']+1) for c,l in zip(COUNTS,LAYERS))
CHOICE_FRAG_PER_ATTEMPT = P*CHOICE['fragment_rate']*((1-CHOICE['double_bias_conditional_rate'])*FRAG+CHOICE['double_bias_conditional_rate']*FRAG_DOUBLE)

def enhancement(quality, level=5, days=42, old=False):
    e=next(e for e in MODEL['equipment'] if e['id']==quality)
    if old:
        return sum(e['oldCosts'][:level])
    scale=min(Q(1),Q(days,42))
    return sum(ceil(q(v)*scale) for v in e['costs'][:level])

def set_cost(level=3, days=42, old=False):
    return 4*enhancement('purple',level,days,old)+enhancement('orange',level,days,old)

REBUILD = set_cost()+MODEL['rebuild']['fullSetReforgeCost']

def attempts(minutes, mode):
    a=Q(minutes)/T
    return Q(floor(a)) if mode=='whole_daily' else a

def wallet_run(minutes=60, mode='whole_daily', days=42, potions=0, card_packs=0, reserve=0):
    """Expected-cash scenario with real integer packs and carried cash.

    Gold income remains an expectation, not a realized success-sequence simulation.
    Reserved gold stays player wealth; it is not counted as a global gold sink.
    """
    a=attempts(minutes,mode)
    income=a*P*GOLD
    fixed=Q(potions*SHOP['potion']['price']+card_packs*SHOP['card_pack']['price'])
    free_cash=Q(0); packs=0; shortage=Q(0)
    ledger=[]
    for day in range(1,days+1):
        available=free_cash+income
        requested=fixed+reserve
        if available<requested:
            shortage += requested-available
            # No credit or invented currency: required bundle is unaffordable.
            ledger.append({'day':day,'gold_in':income,'unaffordable_priority_budget':requested-available})
            free_cash=available
            continue
        available-=requested
        bought=min(SHOP['fragment']['daily_cap'],floor(available/SHOP['fragment']['price']))
        free_cash=available-bought*SHOP['fragment']['price']
        packs+=bought
        ledger.append({'day':day,'gold_in':income,'fixed_sink':fixed,'reserved_gold':reserve,'fragment_packs':bought,'free_cash_close':free_cash})
    affordable=shortage==0
    drop=a*P*FRAG*days
    loss=a*(1-P)*REBUILD*days
    return {
        'minutes':minutes,'mode':mode,'days':days,'potions_per_day':potions,'card_packs_per_day':card_packs,
        'reserve_per_day':reserve,'attempts_per_day':a,'gross_gold_per_day':income,
        'requested_fixed_gold_per_day':fixed,'priority_budget_feasible':affordable,
        'fragment_packs':packs,'shop_fragments':packs*20,'shop_fragment_gold_sink':packs*120,
        'other_shop_gold_sink':fixed*days if affordable else None,
        'reserved_gold_not_sink':reserve*days if affordable else None,'free_gold_close':free_cash,
        'drop_fragments':drop,'regular_rebuild_fragments':loss,
        'choice_fragments_included':False,
        'fragment_close_after_regular_rebuild':drop+packs*20-loss,
        'average_shop_fragments_per_day':Q(packs*20,days),'ledger':ledger,
    }

unit_prices = [
    {'product':k, 'price':v['price'], 'quantity':v.get('quantity',1),
     'gold_per_unit':Q(v['price'],v.get('quantity',1)), 'daily_cap':v.get('daily_cap'),
     'daily_gold_max':v['price']*v['daily_cap'] if 'daily_cap' in v else None}
    for k,v in SHOP.items()
]

purchase_ceiling=[]
for minutes in [30,60,120,150,180]:
    for mode in ['continuous','whole_daily']:
        a=attempts(minutes,mode); g=a*P*GOLD
        purchase_ceiling.append({'minutes':minutes,'mode':mode,'attempts':a,'gold_per_day':g,
            'fragment_3packs_share_of_gold':Q(360)/g if g else None,
            'gold_after_3packs_1potion':g-460,'gold_after_3packs_2potions':g-560,
            'gold_after_all_resource_packs':g-1300})

cost_pressure=[]
for days in [30,42,60]:
    for label,cost in [('regular_plus3',set_cost(3,days)),('regular_plus3_reforge',set_cost(3,days)+6),('max_plus5',set_cost(5,days)),('weapon_plus5',248)]:
        packs=ceil(Q(cost,20))
        cost_pressure.append({'days':days,'target':label,'fragments':cost,
            'gold_shadow_cost':cost*FRAG_UNIT_GOLD,'packs_from_zero_stock':packs,
            'gold_outlay_from_zero_stock':packs*120,'min_shop_reset_windows':ceil(Q(packs,3)),
            'unspent_fragments_from_last_pack':packs*20-cost})

wallet_scenarios=[wallet_run(minutes=m,mode=mode,potions=potions,card_packs=cards,reserve=reserve)
 for m,mode,potions,cards,reserve in [
    (30,'whole_daily',0,0,0),(30,'whole_daily',1,0,0),
    (60,'continuous',0,0,0),(60,'whole_daily',0,0,0),(60,'whole_daily',1,0,0),
    (60,'whole_daily',2,0,0),(60,'whole_daily',1,0,100),(60,'whole_daily',1,1,0),
    (120,'whole_daily',1,1,0),
 ]]

accumulation=[]
for mode in ['continuous','whole_daily']:
    a=attempts(60,mode)
    base_net=a*(P*FRAG-(1-P)*REBUILD)
    for daily_shop_frag in [0,40,60]:
        net=base_net+daily_shop_frag
        gap=set_cost(5)-set_cost(3)
        accumulation.append({'mode':mode,'shop_fragments_per_day':daily_shop_frag,
            'net_while_wearing_plus3':net,'upgrade_from_plus3_to_plus5_gap':gap,
            'expected_saving_days_for_gap':Q(gap)/net if net>0 else None,
            'net_if_already_wearing_plus5':a*(P*FRAG-(1-P)*(set_cost(5)+6))+daily_shop_frag,
            'break_even_plus5_with_shop':Q(set_cost(5)+6)-Q(daily_shop_frag)/a})
        accumulation[-1]['break_even_plus5_with_shop']/=Q(set_cost(5)+6)+FRAG

card_weights=[Q(50,100),Q(30,100),Q(15,100),Q(5,100)]
card_soul_costs=[10,25,50,100]
card_rotating_prices=[80,150,280,500]
card_pack={
    'expected_counts_per_pack':[3*w for w in card_weights],
    'prob_at_least_one_purple_per_pack':1-(1-card_weights[-1])**3,
    'prob_at_least_one_purple_at_daily_cap':1-(1-card_weights[-1])**15,
    'expected_soul_replacement_upper_bound':3*sum(w*c for w,c in zip(card_weights,card_soul_costs)),
    'expected_rotating_price_reference':3*sum(w*c for w,c in zip(card_weights,card_rotating_prices)),
    'expected_unique_unlocks':'unknown_without_per_card_probabilities_and_collection_state',
}

event_effective=EVENT['participation']*EVENT['completion_conditional']*EVENT['redemption_conditional']
event_branches=[]
branches=[
 ('all_fragments',40,0,0,0,12),
 ('all_warrior_souls',0,24,0,0,12),
 ('all_class_souls',0,0,8,0,12),
 ('mixed_resources',20,6,2,0,12),
 ('potion_and_fragments',20,0,0,1,12),
]
for label,f,w,c,p,tokens in branches:
    full={'fragments':f,'warrior_souls':w,'class_souls':c,'potions':p}
    event_branches.append({'branch':label,'tokens_spent_per_event':tokens,'per_event_full':full,
        'per_season_full':{k:v*EVENT['event_count'] for k,v in full.items()},
        'per_eligible_account_season_expected':{k:v*EVENT['event_count']*event_effective for k,v in full.items()},
        'gold_shop_replacement_reference_per_event':6*f+9*w+Q(100,3)*c+100*p,
        'actual_direct_gold_issued':0})
frag_expected=40*EVENT['event_count']*event_effective
event_peak={
    'effective_fraction':event_effective,
    'max_fragment_claim_single_event':40,
    'max_fragments_per_full_participant_season':40*EVENT['event_count'],
    'expected_fragments_per_eligible_account_season':frag_expected,
    'season_average_fragments_per_eligible_account_day':frag_expected/EVENT['season_days'],
    'event_uniform_three_day_average':40*event_effective/EVENT['duration_days_each'],
    'event_concentrated_one_day_peak':40*event_effective,
    '1000_eligible_season_fragments':1000*frag_expected,
    '1000_eligible_single_claim_day_fragments':1000*40*event_effective,
    '1000_eligible_season_shop_gold_sink_reduction_upper_bound':1000*frag_expected*6,
}
combined_v2={
    'mode':'whole_daily','minutes':60,'attempts':3,'shop_fragment_packs_per_day':1,
    'base_route_fragments':FRAG,'double_choice_route_fragments':FRAG_DOUBLE,
    'choice_fragments_per_attempt':CHOICE_FRAG_PER_ATTEMPT,
    'choice_fragments_per_day':3*CHOICE_FRAG_PER_ATTEMPT,
    'base_fragments_net_after_plus3_rebuild_per_day':3*(P*FRAG-(1-P)*REBUILD),
    'shop_fragments_per_day':20,'activity_fragments_per_day':frag_expected/EVENT['season_days'],
    'full_fragment_net_per_day':3*(P*FRAG-(1-P)*REBUILD)+3*CHOICE_FRAG_PER_ATTEMPT+20+frag_expected/EVENT['season_days'],
    'gold_after_one_fragment_pack_one_potion_per_day':3*P*GOLD-120-100,
}

bag_pressure=[]
for kind in ['advanced_bag','top_bag']:
    price=SHOP[kind]['price']
    bag_pressure.append({'kind':kind,'purchase_price':price,'expected_cost_per_attempt_at_p70':(1-P)*price,
        'gross_gold_per_attempt_no_safety':P*GOLD,
        'net_before_other_spend_no_safety':P*GOLD-(1-P)*price,
        'break_even_success_no_safety':Q(price,price+GOLD),
        'max_possible_failure_gold_if_full_route_before_death':GOLD,
        'cost_per_attempt_even_if_all_route_gold_secured':GOLD-(1-P)*price})

result={
 'scope':'document audit + deterministic expected-budget arithmetic; not live simulation',
 'source_model':INPUT.name,'source_status':'v1 candidate route/enhancement; existing shop rules; v2 event proposal',
 'baseline':{'difficulty':'D2','route_gold':GOLD,'route_fragments':FRAG,'success':P,'minutes_per_attempt':T,'rebuild_fragments':REBUILD},
 'shop':SHOP,'unit_prices':unit_prices,'purchase_ceiling':purchase_ceiling,
 'cost_pressure':cost_pressure,'old_set_costs':{'plus3':set_cost(3,old=True),'plus5':set_cost(5,old=True)},
 'wallet_scenarios':wallet_scenarios,'accumulation':accumulation,'card_pack':card_pack,
 'event':EVENT,'event_branches':event_branches,'event_peak':event_peak,'bag_pressure':bag_pressure,
 'choice_proposal':CHOICE,'combined_v2':combined_v2,
}
assert GOLD==223 and FRAG==40 and REBUILD==66
assert set_cost(3)==60 and set_cost(5)==780
assert frag_expected==q('34.56')
assert wallet_run(potions=1)['free_gold_close']==q('348.6')
assert wallet_run(potions=2)['fragment_packs']==93
assert card_pack['expected_soul_replacement_upper_bound']==75
assert sum(CHOICE[k] for k in ['gear_rate','fragment_rate','healing_rate'])==1
assert FRAG_DOUBLE==q('86.5')
assert CHOICE_FRAG_PER_ATTEMPT==q('6.64125')
(OUT/'shop_event_audit_v2_results.json').write_text(json.dumps(n(result),ensure_ascii=False,indent=2)+'\n')

def table(headers,rows):
    def fmt(v):
        if isinstance(v,Q):
            return str(v.numerator) if v.denominator==1 else f'{float(v):.4f}'.rstrip('0').rstrip('.')
        return str(v)
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
      ['| '+' | '.join(fmt(v) for v in row)+' |' for row in rows])

tables=[
 '# 商店与活动预算复算表',
 '\n以下均为现行商店参数叠加候选 D2 R1 的条件预算，非真实对局结果。',
 '\n## 每日金币可负担性\n',
 table(['分钟','口径','日局数','金币/日','3碎片包+1药后余额','3碎片包+2药后余额','买满三种资源包后余额'],[[r['minutes'],r['mode'],r['attempts'],r['gold_per_day'],r['gold_after_3packs_1potion'],r['gold_after_3packs_2potions'],r['gold_after_all_resource_packs']] for r in purchase_ceiling]),
 '\n## 42 日有余额结转的碎片购买\n',
 table(['分钟','口径','药/日','卡包/日','另留金/日','购碎包数','商店碎片','剩余可动金','季末净碎片'],[[r['minutes'],r['mode'],r['potions_per_day'],r['card_packs_per_day'],r['reserve_per_day'],r['fragment_packs'],r['shop_fragments'],r['free_gold_close'],r['fragment_close_after_regular_rebuild']] for r in wallet_scenarios]),
 '\n## 价格与限购约束\n',
 table(['季长','目标','碎片','按6金/碎估值','零碎库存购买包数','实际购包金币','至少日切窗口数'],[[r['days'],r['target'],r['fragments'],r['gold_shadow_cost'],r['packs_from_zero_stock'],r['gold_outlay_from_zero_stock'],r['min_shop_reset_windows']] for r in cost_pressure]),
 '\n## 继续穿 +3 时，储蓄全套 +4/+5 的 720 碎增量\n',
 table(['口径','商店碎/日','穿+3净碎/日','储蓄720所需条件均值天','穿上+5后净碎/日','+5片账平衡撤离率'],[[r['mode'],r['shop_fragments_per_day'],r['net_while_wearing_plus3'],r['expected_saving_days_for_gap'],r['net_if_already_wearing_plus5'],r['break_even_plus5_with_shop']] for r in accumulation]),
 '\n## 活动兑换分支（互斥预算，不可整行叠加）\n',
 table(['分支','每期碎/勇魂/职魂/药','两期满额','全服每名符合资格账号季期望'],[[r['branch'],n(r['per_event_full']),n(r['per_season_full']),n(r['per_eligible_account_season_expected'])] for r in event_branches]),
 '\n## 活动集中发放\n',
 table(['指标','数值'],[[k,v] for k,v in event_peak.items()]),
 '\n## 统一v2基础+三选一+商店+活动片账\n',
 table(['指标','数值'],[[k,v] for k,v in combined_v2.items()]),
 '\n注意：商店金币被回收；市场买卖是转移，只有手续费回收。活动商店影子金价不是真金币投放或回收。',
]
(OUT/'shop_event_audit_v2_tables.md').write_text('\n'.join(tables)+'\n')
print(json.dumps(n({'baseline':result['baseline'],'checks':'9 assertions passed','wallet_rows':len(wallet_scenarios),'event_peak':event_peak,'combined_v2':combined_v2,'output':str(OUT/'shop_event_audit_v2_results.json')}),ensure_ascii=False,indent=2))
