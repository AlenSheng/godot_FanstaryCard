"""Prospective capacity-budget controls; no server, player or capacity claims."""
import copy
import json
import unittest

from tools.pr13_authority_transitions import (
    AUTHORITY_TRANSITION_POLICY, CAPACITY_RECOVERY_POLICY_V2 as V2,
    DETAIL_STUN, review_authority_refusals)
from tools.tests.test_pr13_authority_transitions import (
    CTX, authority, combo, fixture, response, sent)


def review(events, natives, policy=V2):
    return review_authority_refusals(events, natives, policy=policy, cutoff_clock_qualified=True)


def error(request, at, detail=DETAIL_STUN):
    body = dict(code='COMMAND_REJECTED', detail=detail, _request_id=request,
        _origin_context=copy.deepcopy(CTX), _command_action='battle.play_cards',
        _command_result='rejected', _replayed=False, _state_refresh_handled=True, _sequence=10)
    return [dict(at_unix_ms=10000+at, message='command_rejected: '+json.dumps(body)),
            dict(at_unix_ms=10001+at, message=detail), dict(at_unix_ms=10002+at, message=detail)]


def short_control(padding=99):
    events, natives = fixture(stun=True, padding=padding)
    events = [e for e in events if e['event_type'] != 'room.command_state_observed']
    times = {'command.sent':700, 'realtime':800, 'battle.combo_resolved':801}
    for e in events:
        if e.get('request_id') == 'next':
            e['monotonic_ms'] = times[e['event_type']]
            e['at_unix_ms'] = 10000+e['monotonic_ms']
    captured = authority(500, rev=12)
    captured['authority_state']['post_refusal_revision_capture'] = True
    events.append(captured)
    return events, natives


def chain():
    events, natives = fixture(padding=199)
    events = [e for e in events if not (e['event_type']=='battle.combo_resolved' and e.get('request_id')=='next')]
    reply = next(e for e in events if e['event_type']=='realtime' and e.get('request_id')=='next')
    reply.update(result='rejected', response_type='error.command_rejected')
    natives[0]['errors'] += error('next',500)
    captured = authority(600,rev=12)
    captured['authority_state']['post_refusal_revision_capture'] = True
    events += [captured, sent('final',700,'Pvp','duel',12),
               response('final',800), combo('final',801)]
    return events, natives


class CapacityRecoveryV2Tests(unittest.TestCase):
    def test_v1_observed_duel_and_stun_controls_keep_passing(self):
        for stun in (False,True):
            e,n=fixture(stun=stun)
            self.assertTrue(review(e,n)['passed'])

    def test_short_control_is_explicitly_inferred_and_never_capacity_verdict(self):
        e,n=short_control();original=copy.deepcopy(n);r=review(e,n)
        self.assertTrue(r['passed'],r)
        self.assertEqual(100,r['verified_completed_play_requests'])
        self.assertEqual([{'client_id':'client','request_id':'rejected'}],r['inferred_short_stun_requests'])
        self.assertFalse(r['positive_stun_observed_for_all_stun_refusals'])
        self.assertEqual('NotObserved',r['server_execution_state'])
        self.assertFalse(r['capacity_acceptance']);self.assertEqual(original,n)

    def test_old_v1_and_default_strict_do_not_adopt_new_budget(self):
        e,n=short_control()
        self.assertFalse(review(e,n,AUTHORITY_TRANSITION_POLICY)['passed'])
        self.assertFalse(review_authority_refusals(e,n)['passed'])

    def test_two_distinct_kinds_can_close_through_two_bounded_requests(self):
        e,n=chain();r=review(e,n)
        self.assertTrue(r['passed'],r);self.assertEqual(2,len(r['expected_requests']))
        parent=next(x for x in r['expected_requests'] if x['request_id']=='rejected')
        self.assertEqual(['rejected','next','final'],parent['recovery_path'])
        self.assertTrue(parent['contains_inferred_recovery_hop'])
        self.assertEqual(601,parent['recovery_success_ms'])

    def test_same_kind_twice_in_cycle_is_not_a_two_kind_exception(self):
        e,n=short_control(padding=199)
        captured=authority(1300,rev=21);captured['authority_state']['post_refusal_revision_capture']=True
        e += [sent('again',1100,'Pvp','duel',20),response('again',1200,'rejected'),
              captured,sent('again-next',1400,'Pvp','duel',21),
              response('again-next',1500),combo('again-next',1501)]
        n[0]['errors'] += error('again',1200)
        r=review(e,n);self.assertFalse(r['passed'])
        self.assertIn({'reason':'repeated_refusal_kind_in_actor_cycle'},r['evidence_errors'])

    def test_missing_or_stale_zero_authority_fails(self):
        for mode in ('missing','same-revision','old-owner','old-sequence','late'):
            e,n=short_control();a=next(x for x in e if x['event_type']=='room.command_state_observed')
            if mode=='missing':e.remove(a)
            elif mode=='same-revision':a['authority_state']['snapshot']['room_revision']=10
            elif mode=='old-owner':a['_origin_context']['process_epoch']='old'
            elif mode=='old-sequence':a['authority_state']['sequence']=9
            else:a['monotonic_ms']=3301;a['at_unix_ms']=13301
            with self.subTest(mode=mode):self.assertFalse(review(e,n)['passed'])

    def test_zero_authority_from_another_duel_or_unplayable_view_fails(self):
        for mode in ('other-duel','unplayable','replayed'):
            e,n=short_control();a=next(x for x in e if x['event_type']=='room.command_state_observed')
            if mode=='other-duel':a['authority_state']['snapshot']['active_battle_id']='other'
            elif mode=='unplayable':a['authority_state']['snapshot']['allowed_actions']=[]
            else:a['authority_state']['replayed']=True
            with self.subTest(mode=mode):self.assertFalse(review(e,n)['passed'])

    def test_next_intent_cannot_precede_the_new_authority(self):
        e,n=short_control();x=next(x for x in e if x['event_type']=='command.sent' and x['request_id']=='next')
        x['monotonic_ms']=400;x['at_unix_ms']=10400
        self.assertFalse(review(e,n)['passed'])

    def test_unregistered_legacy_zero_snapshot_is_not_a_new_recovery_capture(self):
        e,n=short_control()
        a=next(x for x in e if x['event_type']=='room.command_state_observed')
        del a['authority_state']['post_refusal_revision_capture']
        self.assertFalse(review(e,n)['passed'])

    def test_each_original_request_keeps_3000ms_deadline(self):
        e,n=short_control();x=next(x for x in e if x['event_type']=='command.sent' and x['request_id']=='rejected')
        x['monotonic_ms']=0;x['at_unix_ms']=10000
        r=next(x for x in e if x['event_type']=='realtime' and x['request_id']=='rejected')
        r['monotonic_ms']=3001;r['at_unix_ms']=13001
        result=review(e,n);self.assertFalse(result['passed'])
        self.assertTrue(any(x['reason']=='original_request_3000ms_boundary' for x in result['evidence_errors']))

    def test_recovery_effective_combo_not_transport_only(self):
        for mode in ('replayed','no-effect','wrong-battle','http-word','missing-reply'):
            e,n=short_control();reply=next(x for x in e if x['event_type']=='realtime' and x['request_id']=='next')
            c=next(x for x in e if x['event_type']=='battle.combo_resolved' and x['request_id']=='next')
            if mode=='replayed':reply['replayed']=True
            elif mode=='no-effect':c['gameplay_progress']=False
            elif mode=='wrong-battle':c['battle_id']='other'
            elif mode=='http-word':reply['result']='success'
            else:e.remove(reply)
            with self.subTest(mode=mode):self.assertFalse(review(e,n)['passed'])

    def test_invalid_hand_target_known_stun_or_foreign_actor_fails(self):
        for mode in ('hand','target','known-stun','actor'):
            e,n=short_control();s=next(x for x in e if x['event_type']=='command.sent' and x['request_id']=='rejected')
            if mode=='hand':s['packet_card_instance_ids']=['not-in-hand']
            elif mode=='target':s['dispatch_state']['play_input_evidence']['target_alive_in_current_view']=False
            elif mode=='known-stun':s['dispatch_state']['local_snapshot']['stun_remaining_ms']=1
            else:s['dispatch_state']['local_snapshot']['player_id']='87654321876543218765432187654321'
            with self.subTest(mode=mode):self.assertFalse(review(e,n)['passed'])

    def test_parallel_send_before_refusal_is_not_recovery(self):
        e,n=short_control();e.append(sent('parallel',150,'Pvp','duel',10))
        self.assertFalse(review(e,n)['passed'])

    def test_request_retry_or_duplicate_success_fails(self):
        for mode in ('retry-original','duplicate-success'):
            e,n=short_control()
            if mode=='retry-original':e.append(sent('rejected',450,'Pvp','duel',11))
            else:e.append(response('next',802))
            with self.subTest(mode=mode):self.assertFalse(review(e,n)['passed'])

    def test_refusal_fraction_still_requires_witnessed_completions(self):
        e,n=short_control(padding=98)
        self.assertFalse(review(e,n)['passed'])
        for i in range(100):e.append(sent('unanswered'+str(i),7000+i,'Pvp','duel',30))
        self.assertFalse(review(e,n)['passed'])

    def test_unknown_and_READY_errors_stay_failed(self):
        for detail,code in [('other','COMMAND_REJECTED'),('The player has no pending ready lobby.','READY_NOT_FOUND')]:
            e,n=short_control();b=json.loads(n[0]['errors'][0]['message'][len('command_rejected: '):]);b.update(detail=detail,code=code)
            n[0]['errors'][0]['message']='command_rejected: '+json.dumps(b)
            with self.subTest(code=code):self.assertFalse(review(e,n)['passed'])

    def test_known_positive_stun_cannot_be_ignored_as_unobserved(self):
        e,n=short_control();a=authority(400,rev=9,stun=500);e.append(a)
        self.assertFalse(review(e,n)['passed'])

    def test_unrelated_positive_stun_after_recovery_is_not_original_episode(self):
        e,n=short_control();e.append(authority(1500,rev=30,stun=500))
        self.assertTrue(review(e,n)['passed'])

    def test_chain_does_not_cross_cycle_or_repeat_stun_hops(self):
        e,n=chain();s=next(x for x in e if x['event_type']=='command.sent' and x['request_id']=='final')
        s['cycle_id']='client:2';self.assertFalse(review(e,n)['passed'])

    def test_late_final_recovery_cannot_extend_chain(self):
        e,n=chain();r=next(x for x in e if x['event_type']=='realtime' and x['request_id']=='final')
        r['monotonic_ms']=7000;r['at_unix_ms']=17000
        self.assertFalse(review(e,n)['passed'])

    def test_duplicate_notice_limit_is_retained(self):
        e,n=short_control();n[0]['errors'].append(copy.deepcopy(n[0]['errors'][1]))
        self.assertFalse(review(e,n)['passed'])

    def test_scoped_unsolicited_receiver_does_not_invent_business_origin(self):
        e,n=short_control();a=next(x for x in e if x['event_type']=='room.command_state_observed')
        a['_origin_context']={};a['cycle_id']='Unknown'
        a['context_capture_kind']='uncorrelated_receive';a['record_owner_source']='gateway_receive'
        a.pop('session_generation');a.pop('room_context_epoch')
        a['authority_state']['receive_owner']=copy.deepcopy(CTX)
        original=copy.deepcopy(e);r=review(e,n)
        self.assertTrue(r['passed'],r)
        self.assertEqual('scoped_unsolicited_receiver',r['expected_requests'][0]['authority_owner_basis'])
        self.assertEqual(original,e)
        self.assertFalse(review(e,n,AUTHORITY_TRANSITION_POLICY)['passed'])

    def test_unsolicited_missing_foreign_or_contradictory_epoch_fails(self):
        for mode in ('missing','foreign-session','foreign-room','contradictory','foreign-origin','wrong-source','malformed-origin'):
            e,n=short_control();a=next(x for x in e if x['event_type']=='room.command_state_observed')
            a['_origin_context']={};a['cycle_id']='Unknown'
            a['context_capture_kind']='uncorrelated_receive';a['record_owner_source']='gateway_receive'
            a.pop('session_generation');a.pop('room_context_epoch')
            a['authority_state']['receive_owner']=copy.deepcopy(CTX)
            if mode=='missing':a['authority_state']['receive_owner'].pop('session_generation')
            elif mode=='foreign-session':a['authority_state']['receive_owner']['session_generation']=2
            elif mode=='foreign-room':a['authority_state']['receive_owner']['room_id']='foreign'
            elif mode=='contradictory':a['session_generation']=2
            elif mode=='foreign-origin':a['_origin_context']=dict(CTX,process_epoch='foreign')
            elif mode=='wrong-source':a['record_owner_source']='dispatch'
            else:a['_origin_context']=''
            with self.subTest(mode=mode):self.assertFalse(review(e,n)['passed'])


if __name__=='__main__':unittest.main()
