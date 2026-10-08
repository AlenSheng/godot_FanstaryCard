"""Export reviewed exact Domain assertions, never infer whole-suite acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
# Each entry names every required test method. All theory rows must pass.
MAPPING = {
    'PR13-B04.2-T02': ['Rooms.PairedBuildBudgetTests.Higher_rarity_or_level_replacement_is_rejected_before_experiment_entry'],
    'PR13-B03.2-T01': ['Rooms.PairedBuildBudgetTests.Single_published_white_card_swap_preserves_cost_rarity_level_and_twenty_instances'],
    'PR13-B03.2-T02': ['Rooms.PairedBuildBudgetTests.PVP_side_swap_keeps_mirrored_starting_resources_and_restores_each_own_pool'],
    'PR13-B04.2-T01': ['Rooms.PairedBuildBudgetTests.Single_published_white_card_swap_preserves_cost_rarity_level_and_twenty_instances'],
    'PR13-B06.3-T01': ['Combat.PausedDrawLedgerTests.Candidate_passive_alone_cannot_sustain_cards_without_natural_time'],
    'PR13-B06.3-T02': ['Combat.PausedDrawLedgerTests.Printed_double_draw_can_form_a_local_loop_and_action_cap_stays_unfinished'],
    'PR13-B09.3-T03': ['Rooms.MonsterCardPoolTests.PVP_snapshot_restore_and_return_preserve_pool_instance_identity'],
    'PR13-B02.4-T01': ['Rooms.NumericalPolicySnapshotTests.New_source_policy_does_not_change_a_live_default_room_or_its_saved_instances'],
    'PR13-B12.3-T02': ['Rooms.NumericalPolicySnapshotTests.Rolling_source_back_changes_new_rooms_and_preserves_existing_candidate_room_instances'],
    'LOAD-11.4-T03': ['Rooms.NumericalPolicySnapshotTests.Rolling_source_back_changes_new_rooms_and_preserves_existing_candidate_room_instances'],
    'PR13-A07.1-T01': ['Combat.Pr13BoundaryContractTests.Published_policy_contract_has_no_retired_bool_or_remainder_property'],
    'PR13-A07.1-T02': ['Combat.Pr13BoundaryContractTests.Published_policy_contract_has_no_retired_bool_or_remainder_property'],
    'PR13-A07.1-T03': ['Combat.FenxianImmediateDrawPolicyTests.Default_policy_preserves_current_rhythm_based_draws', 'Combat.GuardianShieldBonusPolicyTests.Default_policy_preserves_current_integer_steps'],
    'PR13-B02.1-T02': ['Combat.Pr13BoundaryContractTests.Published_policy_contract_has_no_retired_bool_or_remainder_property'],
    'PR13-B02.1-T03': ['Combat.FenxianImmediateDrawPolicyTests.Cards_spent_policy_does_not_return_a_single_core_card_even_at_max_combo', 'Combat.GuardianShieldBonusPolicyTests.Fractional_policy_delivers_expected_five_play_weapon_contribution'],
    'PR13-B02.2-T01': ['Rooms.CombatSelectionOrderContractTests.Preview_resolves_core_from_selected_instance_order_without_mutating_room', 'Combat.CombatAuthoritativeRulesTests.Selection_order_changes_core_even_when_later_element_is_more_common'],
    'PR13-B02.2-T02': ['Combat.CurrentNumericalBaselineTests.A_three_fire_is_46', 'Combat.CurrentNumericalBaselineTests.A_fuel_four_fire_is_72', 'Combat.CurrentNumericalBaselineTests.A_fuel_five_fire_is_113'],
    'PR13-B02.2-T03': ['Combat.CombatAuthoritativeRulesTests.Conflict_card_healing_uses_priest_then_vitality_but_conflict_recovery_only_uses_vitality', 'Combat.CurrentNumericalBaselineTests.Priest_card_heal_gets_passive_and_weapon_but_conflict_recovery_does_not'],
    'PR13-B02.3-T01': ['Rooms.CombatPreviewAndFeedbackTests.Preview_is_pure_and_matches_actual_health_shield_draw_and_leveled_card_resolution', 'Rooms.CombatPreviewAndFeedbackTests.Lethal_preview_does_not_roll_live_rewards_or_grant_monster_cards', 'Rooms.NumericalPolicySnapshotTests.Guardian_room_preview_preserves_live_remainder_and_matches_committed_gain'],
    'PR13-B02.4-T02': ['Rooms.BattleRoomSnapshotTests.Surviving_duel_restores_complete_player_and_pve_snapshots', 'Rooms.NumericalPolicySnapshotTests.Survived_duel_restores_pve_remainder_and_policy'],
    'PR13-B02.4-T03': ['Rooms.NumericalPolicySnapshotTests.Json_roundtrip_keeps_policy_and_zero_missing_fields_resolve_to_legacy', 'Rooms.NumericalPolicySnapshotTests.Invalid_policy_or_remainder_is_rejected_before_any_state_mutation'],
    'PR13-B06.1-T01': ['Combat.FenxianImmediateDrawPolicyTests.Default_policy_preserves_current_rhythm_based_draws'],
    'PR13-B06.1-T02': ['Combat.Pr13BoundaryContractTests.Full_hand_caps_requested_draw_without_consuming_library_or_copying_instances'],
    'PR13-B06.1-T03': ['Combat.CombatAuthoritativeRulesTests.Existing_fenxian_behavior_remains_the_default'],
    'PR13-B06.2-T01': ['Combat.FenxianImmediateDrawPolicyTests.Cards_spent_policy_does_not_return_a_single_core_card_even_at_max_combo'],
    'PR13-B06.2-T02': ['Combat.FenxianImmediateDrawPolicyTests.Cards_spent_policy_keeps_three_four_five_card_identity'],
    'PR13-B06.2-T03': ['Combat.FenxianImmediateDrawPolicyTests.Cards_spent_policy_keeps_combo_for_charge_but_not_for_draw_count'],
    'PR13-B06.3-T03': ['Combat.Pr13BoundaryContractTests.Exhausted_library_shuffles_discard_without_losing_or_duplicating_instances'],
    'PR13-B06.4-T01': ['Combat.FenxianImmediateDrawPolicyTests.Cards_spent_policy_keeps_three_four_five_card_identity'],
    'PR13-B06.4-T03': ['Rooms.NumericalPolicySnapshotTests.Candidate_mage_preview_and_play_agree_after_room_restore', 'Rooms.NumericalPolicySnapshotTests.Survived_duel_restores_pve_remainder_and_policy'],
    'PR13-B07.1-T01': ['Combat.GuardianShieldBonusPolicyTests.Fractional_policy_delivers_expected_five_play_weapon_contribution'],
    'PR13-B07.1-T02': ['Combat.GuardianShieldBonusPolicyTests.Fractional_policy_delivers_expected_five_play_weapon_contribution'],
    'PR13-B07.1-T03': ['Combat.GuardianShieldBonusPolicyTests.Default_policy_preserves_current_integer_steps'],
    'PR13-B07.3-T01': ['Rooms.NumericalPolicySnapshotTests.Repeated_preview_invalid_play_and_already_spent_cards_cannot_commit_remainder'],
    'PR13-B07.3-T02': ['Combat.GuardianShieldBonusPolicyTests.Full_shield_does_not_generate_or_consume_remainder', 'Combat.GuardianShieldBonusPolicyTests.Shield_cap_truncation_discards_candidate_remainder', 'Combat.GuardianShieldBonusPolicyTests.Leaving_cell_clear_shield_also_clears_candidate_remainder', 'Rooms.NumericalPolicySnapshotTests.Exact_integer_fill_discards_fractional_overflow', 'Rooms.NumericalPolicySnapshotTests.Zero_printed_shield_preserves_existing_remainder_without_free_shield'],
    'PR13-B07.3-T03': ['Combat.GuardianShieldBonusPolicyTests.Candidate_remainder_round_trips_through_combat_snapshot', 'Rooms.NumericalPolicySnapshotTests.Survived_duel_restores_pve_remainder_and_policy'],
    'PR13-B08.1-T01': ['Combat.CombatAuthoritativeRulesTests.Stun_window_halves_second_stun_ignores_third_and_expires_without_extending'],
    'PR13-B08.1-T02': ['Combat.Pr13BoundaryContractTests.Stun_window_expires_at_exactly_eight_seconds_but_not_7999_milliseconds'],
    'PR13-B08.1-T03': ['Combat.Pr13BoundaryContractTests.Restored_stun_windows_keep_target_identity_and_remaining_deadline'],
    'PR13-B08.3-T01': ['Combat.CurrentNumericalBaselineTests.Tuning_card_can_establish_core_and_counts_toward_r'],
    'PR13-B08.3-T02': ['Combat.CombatAuthoritativeRulesTests.Element_tuning_uses_resonance_without_taking_or_creating_conflict_cancellation'],
    'PR13-B08.3-T03': ['Combat.CurrentNumericalBaselineTests.Priest_card_heal_gets_passive_and_weapon_but_conflict_recovery_does_not'],
    'PR13-B09.1-T01': ['Rooms.MonsterCardPoolTests.Current_room_still_grants_monster_cards_automatically'],
    'PR13-B09.1-T02': ['Rooms.CombatPreviewAndFeedbackTests.Every_monster_kill_adds_exactly_one_card_to_discard_and_dead_target_cannot_be_farmed'],
    'PR13-B09.2-T01': ['Rooms.MonsterCardPoolTests.Accept_adds_only_to_discard_and_replay_does_not_add_cards'],
    'PR13-B09.2-T02': ['Rooms.MonsterCardPoolTests.Full_pool_requires_monster_replacement_and_never_removes_base_card', 'Rooms.MonsterCardPoolTests.Replacement_from_hand_does_not_draw_a_compensation_card'],
    'PR13-B09.2-T03': ['Rooms.MonsterCardPoolTests.Skip_gives_no_resource_and_snapshot_roundtrips_receipts_and_provenance'],
    'PR13-B09.3-T01': ['Rooms.MonsterCardPoolTests.Candidate_kill_offer_survives_room_restore_and_only_owner_can_accept_after_combat'],
    'PR13-B09.3-T02': ['Rooms.MonsterCardPoolTests.Accept_adds_only_to_discard_and_replay_does_not_add_cards', 'Rooms.MonsterCardPoolTests.Candidate_kill_offer_survives_room_restore_and_only_owner_can_accept_after_combat'],
}

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value): path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode())

def export(trx, output, source_sha):
    source_sha=subprocess.check_output(['git','rev-parse',source_sha+'^{commit}'],cwd=ROOT,text=True).strip()
    paths=subprocess.check_output(['git','ls-files','server/src/FantasyCard.Domain','server/tests/FantasyCard.Domain.Tests'],cwd=ROOT,text=True).splitlines()
    paths=[p for p in paths if '/bin/' not in p and '/obj/' not in p and (ROOT/p).is_file()]
    changed=subprocess.check_output(['git','diff',source_sha,'--',*paths],cwd=ROOT)
    if changed:raise ValueError('Runtime Domain/test source differs from declared tested commit')
    tree = ET.parse(trx)
    definitions = {n.attrib['id']:n.find('{*}TestMethod').attrib for n in tree.findall('.//{*}UnitTest')}
    results = []
    for n in tree.findall('.//{*}UnitTestResult'):
        method = definitions[n.attrib['testId']]
        stdout=n.findtext('.//{*}StdOut') or ''
        results.append({'method':method['className'].split(',')[0]+'.'+method['name'], 'name':n.attrib['testName'], 'outcome':n.attrib['outcome'],
                        'resource_ledger':[json.loads(line.split('PR13_DRAW_LEDGER ',1)[1]) for line in stdout.splitlines() if line.startswith('PR13_DRAW_LEDGER ')]})
    counters = tree.find('.//{*}Counters').attrib
    if int(counters['executed'])!=int(counters['total']) or int(counters.get('notExecuted',0)) or not int(counters['total']):raise ValueError('Skipped/missing native assertions cannot export Passed')
    plan_path = ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json'
    contracts = {c['id']:c for p in json.loads(plan_path.read_text(encoding='utf8'))['packages'] for t in p['subtasks'] for c in t['test_cases']}
    records=[]
    for case_id, methods in MAPPING.items():
        found=[]
        for name in methods:
            rows=[r for r in results if r['method']=='FantasyCard.Domain.Tests.'+name]
            if not rows: raise ValueError('Required exact assertion method absent: '+name)
            found.extend(rows)
        passed=all(r['outcome']=='Passed' for r in found)
        records.append({'case_id':case_id, 'executed':True, 'status':'Passed' if passed else 'Failed',
            'setup':contracts[case_id]['setup_and_injection'], 'expected':contracts[case_id]['expected'],
            'actual':{'assertion_results':found,'trx_sha256':sha(trx)}, 'profiles_executed':['OFFLINE'],
            'scope':'Actual authoritative Domain/room tests. PostgreSQL, sampled experiments, renderer and live layers remain separate.'
                    + (' Paused draw uses declared local repeated-card controls; its capped loop is unfinished and is not a legal published-deck or whole-pool balance proof.' if case_id.startswith('PR13-B06.3-T0') and case_id[-1] in '12' else '')})
    output.mkdir(parents=True, exist_ok=False)
    (output/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records).encode())
    write(output/'report.json', {'source_sha':source_sha, 'plan_sha256':sha(plan_path), 'source':{'scope':'exact reviewed native authoritative assertions','input_hashes':{p:sha(ROOT/p) for p in paths}},
        'executed':len(records), 'passed':sum(r['status']=='Passed' for r in records), 'native_counters':counters,
        'profiles_executed':['OFFLINE'], 'accepted':False})
    write(output/'artifact-index.json', {'files':[{'path':trx.resolve().relative_to(ROOT).as_posix(),'bytes':trx.stat().st_size,'sha256':sha(trx)}]})
    return records

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trx',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-sha',required=True);args=p.parse_args()
    # Caller must freeze runtime source and keep immutable TRX; old tests cannot become current code evidence.
    rows=export(args.trx,args.output,args.source_sha)
    print(json.dumps({'executed':len(rows),'passed':sum(r['status']=='Passed' for r in rows)}));return 0 if all(r['status']=='Passed' for r in rows) else 1
if __name__=='__main__':raise SystemExit(main())
