"""Positive/negative audit fixtures, not gameplay or server-capacity evidence."""
import copy
import json
import unittest
from pathlib import Path

from tools.pr13_authority_transitions import (AUTHORITY_TRANSITION_POLICY as POLICY,
    DETAIL_DUEL, DETAIL_STUN, review_authority_refusals)

UID = '12345678123456781234567812345678'
CTX = dict(run_id='run', client_id='client', process_epoch='epoch', cycle_id='client:1',
           room_id='room', match_id='match', session_generation=1, room_context_epoch=2)


def snapshot(phase='Pve', battle='pve', rev=10, stun=0):
    return dict(room_id='room', match_id='match', player_id=UID, player_phase=phase,
        active_battle_kind='Duel' if phase == 'Pvp' else 'Pve', active_battle_id=battle,
        room_revision=rev, stun_field_present=True, stun_remaining_ms=stun,
        allowed_actions_valid=True, allowed_actions=[] if stun else ['battle.play_cards'],
        hand_instance_ids=['card'], hand_instance_ids_valid=True, player_hp=80,
        base_maximum_hp=70, effective_maximum_hp=80)


def row(kind, mono, **extra):
    return dict(CTX, event_type=kind, monotonic_ms=mono, at_unix_ms=10000+mono,
                event_seq=1, observation_phase='active', **extra)


def sent(request, mono, phase='Pve', battle='pve', rev=10):
    return row('command.sent', mono, action='battle.play_cards', request_id=request,
        packet_room_id='room', packet_match_id='match', packet_battle_id=battle,
        packet_expected_revision=rev, packet_card_instance_ids=['card'], packet_card_instance_ids_valid=True,
        packet_target_id='target', dispatch_state=dict(identity_binding='SameCurrentRoute',
            battle_relation='SameActiveBattle', revision_relation='SameSnapshotRevision',
            local_snapshot=snapshot(phase, battle, rev), play_input_evidence=dict(hand_valid=True,
                selection_valid=True, selected_ids_in_current_hand=True, target_id='target', target_alive_in_current_view=True)))


def response(request, mono, result='completed'):
    return row('realtime', mono, action='battle.play_cards', request_id=request, result=result,
        replayed=False, response_type='error.command_rejected' if result=='rejected' else 'battle.combo_resolved')


def combo(request, mono, battle='duel'):
    return row('battle.combo_resolved', mono, request_id=request, battle_id=battle, gameplay_progress=True)


def authority(mono, rev=11, stun=0):
    return row('room.command_state_observed', mono, _origin_context=copy.deepcopy(CTX), authority_state=dict(
        identity_binding='SameCurrentRoute', state_evidence_quality='Complete', missing_fields=[], replayed=False,
        sequence=rev, local_session_generation_at_capture=1, local_room_context_epoch_at_capture=2,
        snapshot=snapshot('Pvp', 'duel', rev, stun)))


def fixture(stun=False, padding=99):
    detail = DETAIL_STUN if stun else DETAIL_DUEL
    body = dict(code='COMMAND_REJECTED', detail=detail, _request_id='rejected', _origin_context=copy.deepcopy(CTX),
                _command_action='battle.play_cards', _command_result='rejected', _replayed=False, _state_refresh_handled=True,_sequence=10)
    errors = [dict(at_unix_ms=10200, message='command_rejected: '+json.dumps(body)),
              dict(at_unix_ms=10201, message=detail), dict(at_unix_ms=10202, message=detail)]
    native = dict(client_id='client', run_id='run', process_epoch='epoch', user_id=UID, audit_lost_count=0, errors=errors)
    events = [sent('rejected', 100, 'Pvp' if stun else 'Pve', 'duel' if stun else 'pve'),
              response('rejected', 200, 'rejected'), authority(300, stun=500 if stun else 0)]
    if stun:
        events.append(authority(3600, rev=12))
    next_time = 3700 if stun else 400
    events += [sent('next', next_time, 'Pvp', 'duel', 12 if stun else 11),
               response('next', next_time+100), combo('next', next_time+101)]
    # The next success is already one completed request, so98 additional
    # successes plus one refusal make100 independently witnessed completions.
    for i in range(max(0, padding-1)):
        request = 'pad'+str(i); t=5000+i*10
        events += [sent(request,t,'Pvp','duel',20), response(request,t+2), combo(request,t+3)]
    return events, [native]


def review(events, reports, **kwargs):
    return review_authority_refusals(events, reports, policy=POLICY, cutoff_clock_qualified=True, **kwargs)


class AuthorityTransitionTests(unittest.TestCase):
    def setUp(self):
        self.events, self.reports = fixture()

    def mutate(self, kind, request=None):
        return next(e for e in self.events if e['event_type']==kind and (request is None or e.get('request_id')==request))

    def rejected(self):
        r=review(self.events,self.reports)
        self.assertFalse(r['passed'],r)
        return r

    def test_complete_duel_transition_keeps_all_original_errors(self):
        original=copy.deepcopy(self.reports);r=review(self.events,self.reports)
        self.assertTrue(r['passed'],r);self.assertEqual(1,len(r['expected_requests']))
        self.assertEqual(100,r['verified_completed_play_requests'])
        self.assertEqual(original,self.reports);self.assertFalse(r['capacity_acceptance'])

    def test_actual_native_completed_response_enters_denominator(self):
        path=Path(__file__).parent/'fixtures/pr13_native_completed_play.json'
        captured=json.loads(path.read_text(encoding='utf-8'))
        original=copy.deepcopy(captured)
        r=review(captured['events'],[captured['native']])
        self.assertTrue(r['passed'],r)
        self.assertEqual(1,r['verified_completed_play_requests'])
        self.assertEqual(original,captured)
        self.assertFalse(r['capacity_acceptance'])

    def test_http_success_word_is_not_a_native_realtime_completion(self):
        path=Path(__file__).parent/'fixtures/pr13_native_completed_play.json'
        captured=json.loads(path.read_text(encoding='utf-8'))
        reply=next(e for e in captured['events'] if e['event_type']=='realtime')
        reply['result']='success'
        r=review(captured['events'],[captured['native']])
        self.assertEqual(0,r['verified_completed_play_requests'])

    def test_complete_new_stun_waits_for_authoritative_release(self):
        e,n=fixture(stun=True);r=review(e,n)
        self.assertTrue(r['passed'],r)
        self.assertGreater(r['expected_requests'][0]['recovery_success_ms'],3000)

    def test_default_remains_strict(self):
        r=review_authority_refusals(self.events,self.reports)
        self.assertFalse(r['passed']);self.assertEqual(3,len(r['unclassified_errors']))

    def test_unknown_policy_is_not_a_compatibility_path(self):
        with self.assertRaises(ValueError):review_authority_refusals([],[],policy='anything')

    def test_unqualified_clock_fails(self):
        self.assertFalse(review_authority_refusals(self.events,self.reports,policy=POLICY)['passed'])

    def test_known_stun_cannot_be_excused(self):
        self.mutate('command.sent','rejected')['dispatch_state']['local_snapshot']['stun_remaining_ms']=1
        self.rejected()

    def test_missing_hand_cannot_be_reconstructed(self):
        del self.mutate('command.sent','rejected')['dispatch_state']['local_snapshot']['hand_instance_ids']
        self.rejected()

    def test_unowned_or_duplicate_cards_fail(self):
        for ids in [['foreign'],['card','card']]:
            with self.subTest(ids=ids):
                self.mutate('command.sent','rejected')['packet_card_instance_ids']=ids;self.rejected()

    def test_invalid_target_is_not_a_race(self):
        self.mutate('command.sent','rejected')['dispatch_state']['play_input_evidence']['target_alive_in_current_view']=False
        self.rejected()

    def test_replayed_rejection_or_authority_fails(self):
        self.mutate('realtime','rejected')['replayed']=True;self.rejected()
        self.mutate('realtime','rejected')['replayed']=False
        self.mutate('room.command_state_observed')['authority_state']['replayed']=True;self.rejected()

    def test_foreign_owner_epoch_or_actor_fails(self):
        a=self.mutate('room.command_state_observed')
        a['authority_state']['local_room_context_epoch_at_capture']=3;self.rejected()
        a['authority_state']['local_room_context_epoch_at_capture']=2
        a['authority_state']['snapshot']['player_id']='87654321876543218765432187654321';self.rejected()

    def test_missing_physical_owner_fails(self):
        del self.mutate('room.command_state_observed')['_origin_context'];self.rejected()

    def test_future_packet_revision_is_not_excused(self):
        self.mutate('command.sent','rejected')['packet_expected_revision']=999;self.rejected()

    def test_late_first_authority_fails(self):
        a=self.mutate('room.command_state_observed');a['monotonic_ms']=4000;a['at_unix_ms']=14000;self.rejected()

    def test_wrong_new_phase_or_unchanged_battle_fails(self):
        a=self.mutate('room.command_state_observed')['authority_state']['snapshot'];a['player_phase']='Pve';self.rejected()
        a['player_phase']='Pvp';a['active_battle_id']='pve';self.rejected()

    def test_old_battle_intent_after_new_authority_fails(self):
        self.mutate('command.sent','next')['packet_battle_id']='pve';self.rejected()

    def test_failed_or_replayed_new_success_fails(self):
        self.mutate('realtime','next')['result']='rejected';self.rejected()
        self.mutate('realtime','next')['result']='completed';self.mutate('realtime','next')['replayed']=True;self.rejected()

    def test_late_new_combo_is_not_ignored(self):
        c=self.mutate('battle.combo_resolved','next');c['monotonic_ms']=3201;c['at_unix_ms']=13201;self.rejected()

    def test_rejected_request_cannot_have_a_successful_combo(self):
        self.events.append(combo('rejected',250,'pve'));self.rejected()

    def test_original_write_retry_fails(self):
        self.events.append(copy.deepcopy(self.mutate('command.sent','rejected')));self.rejected()

    def test_unknown_notice_and_late_duplicate_remain_errors(self):
        self.reports[0]['errors'].append(dict(at_unix_ms=10203,message='unknown failure'));self.rejected()
        self.reports[0]['errors'].pop();self.reports[0]['errors'][1]['at_unix_ms']=10301;self.rejected()

    def test_fourth_duplicate_is_not_suppressed(self):
        self.reports[0]['errors'].append(dict(at_unix_ms=10203,message=DETAIL_DUEL));self.rejected()

    def test_missing_native_error_cannot_hide_rejected_play(self):
        self.reports[0]['errors']=[];self.rejected()

    def test_rate_above1percent_fails(self):
        e,n=fixture(padding=98);self.assertFalse(review(e,n)['passed'])

    def test_unanswered_sends_cannot_inflate_rate_denominator(self):
        e,n=fixture(padding=0)
        e.extend(sent('unanswered'+str(i),6000+i,'Pvp','duel',20) for i in range(100))
        self.assertFalse(review(e,n)['passed'])

    def test_stun_release_required_and_no_known_stun_writes(self):
        e,n=fixture(stun=True);e=[r for r in e if not(r['event_type']=='room.command_state_observed' and r['monotonic_ms']==3600)]
        self.assertFalse(review(e,n)['passed'])
        e,n=fixture(stun=True);e.append(sent('premature',500,'Pvp','duel',11));self.assertFalse(review(e,n)['passed'])

    def test_stun_window_cannot_be_extended(self):
        e,n=fixture(stun=True)
        a=next(r for r in e if r['event_type']=='room.command_state_observed' and r['monotonic_ms']==3600)
        a['monotonic_ms']=9000;a['at_unix_ms']=19000
        self.assertFalse(review(e,n)['passed'])

    def test_foreign_audit_event_and_lost_audit_fail(self):
        self.events.append(dict(client_id='foreign',event_type='other'));self.rejected()
        self.events.pop();self.reports[0]['audit_lost_count']=1;self.rejected()

    def test_unsolicited_same_match_state_does_not_invent_cycle(self):
        self.mutate('room.command_state_observed')['cycle_id']='Unknown'
        self.assertTrue(review(self.events,self.reports)['passed'])

    def test_second_documented_refusal_in_same_cycle_is_still_failure(self):
        e,n=fixture()
        for item in e:
            item['monotonic_ms']+=10000;item['at_unix_ms']+=10000
            if 'request_id' in item:item['request_id']+='-second'
        for item in n[0]['errors']:
            item['at_unix_ms']+=10000
            if item['message'].startswith('command_rejected: '):
                body=json.loads(item['message'].split(': ',1)[1]);body['_request_id']+='-second'
                item['message']='command_rejected: '+json.dumps(body)
        r=review(self.events+e,[dict(self.reports[0],errors=self.reports[0]['errors']+n[0]['errors'])])
        self.assertFalse(r['passed'],r)
        self.assertIn('multiple_refusals_in_actor_cycle',[x['reason'] for x in r['evidence_errors']])

    def test_bool_stun_value_is_not_integer_evidence(self):
        self.mutate('command.sent','rejected')['dispatch_state']['local_snapshot']['stun_remaining_ms']=False
        self.rejected()

    def test_unknown_detail_is_not_a_transition(self):
        e=self.reports[0]['errors'][0]
        body=json.loads(e['message'].split(': ',1)[1]);body['detail']='Some other validation failure'
        e['message']='command_rejected: '+json.dumps(body)
        self.rejected()

    def test_old_authority_sequence_and_unbound_error_time_fail(self):
        a=self.mutate('room.command_state_observed')['authority_state'];a['sequence']=9;self.rejected()
        a['sequence']=11;self.reports[0]['errors'][0]['at_unix_ms']+=101;self.rejected()

    def test_malformed_nested_objects_fail_closed_without_crashing(self):
        for bad in (None,[],"bad",True):
            with self.subTest(bad=bad):
                e,n=fixture();next(r for r in e if r['event_type']=='command.sent')['dispatch_state']['play_input_evidence']=bad
                self.assertFalse(review(e,n)['passed'])
                e,n=fixture();next(r for r in e if r['event_type']=='room.command_state_observed')['authority_state']=bad
                self.assertFalse(review(e,n)['passed'])

    def test_permission_flags_do_not_repair_malformed_permission_data(self):
        self.mutate('command.sent','rejected')['dispatch_state']['local_snapshot']['allowed_actions']='battle.play_cards'
        self.rejected()

    def test_nonobject_error_json_is_not_an_exception(self):
        self.reports[0]['errors'][0]['message']='command_rejected: []';self.rejected()

    def test_authority_update_in_flight_before_rejection_is_valid_evidence(self):
        a=self.mutate('room.command_state_observed');a['monotonic_ms']=150;a['at_unix_ms']=10150
        a['authority_state']['sequence']=9
        r=review(self.events,self.reports)
        self.assertTrue(r['passed'],r)
        self.assertEqual('in_flight_before_rejection',r['expected_requests'][0]['authority_observation_relation'])

    def test_stun_can_be_observed_before_the_rejection_frame(self):
        e,n=fixture(stun=True)
        a=next(v for v in e if v['event_type']=='room.command_state_observed');a['monotonic_ms']=150;a['at_unix_ms']=10150
        self.assertTrue(review(e,n)['passed'])

    def test_old_authority_before_dispatch_does_not_excuse_known_bad_input(self):
        a=self.mutate('room.command_state_observed');a['monotonic_ms']=50;a['at_unix_ms']=10050
        self.rejected()

    def test_gateway_header_may_be_newer_than_local_full_snapshot(self):
        s=self.mutate('command.sent','rejected');s['packet_expected_revision']=11
        s['dispatch_state']['revision_relation']='EarlierSnapshotRevision'
        self.assertTrue(review(self.events,self.reports)['passed'])

    def test_parallel_play_during_rejected_request_cannot_be_hidden(self):
        a=self.mutate('room.command_state_observed');a['monotonic_ms']=150;a['at_unix_ms']=10150
        self.events.append(sent('parallel',175,'Pvp','duel',11));self.rejected()

    def test_unrelated_earlier_state_is_not_the_stun_release(self):
        e,n=fixture(stun=True)
        early=authority(250,rev=11,stun=0)
        for v in e:
            if v['event_type']=='room.command_state_observed':
                v['authority_state']['snapshot']['room_revision']+=1;v['authority_state']['sequence']+=1
            if v.get('request_id')=='next' and v['event_type']=='command.sent':
                v['packet_expected_revision']=13;v['dispatch_state']['local_snapshot']['room_revision']=13
        self.assertTrue(review(e+[early],n)['passed'])
        no_release=[v for v in e if not(v['event_type']=='room.command_state_observed' and v['monotonic_ms']==3600)]
        self.assertFalse(review(no_release+[early],n)['passed'])


if __name__=='__main__':unittest.main()
