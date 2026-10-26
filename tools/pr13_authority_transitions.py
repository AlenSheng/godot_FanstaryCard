"""Conservative review of documented authority changes, never a capacity verdict.

Original native errors remain untouched. The default is strict. The optional
policy requires actual packet/hand evidence, a new same-owner authority state
and a successful new intent. V2 labels unobserved short control as inferred;
unknown ownership or missing required recovery evidence still fails.
"""
from collections import Counter, defaultdict
import json
import math
import uuid

STRICT_POLICY = 'strict'
AUTHORITY_TRANSITION_POLICY = 'documented-authority-transition-v1'
CAPACITY_RECOVERY_POLICY_V2 = 'capacity-budgeted-authority-recovery-v2'
POLICY_SOURCE_FILES = ('tools/pr13_authority_transitions.py', 'tools/pr13_distributed_load.py',
                       'tools/pr13_distributed_capacity.py')
DETAIL_DUEL = 'Duel is not active in this room.'
DETAIL_STUN = 'A stunned player cannot play cards.'
IDENTITY = ('run_id', 'client_id', 'process_epoch', 'cycle_id', 'room_id', 'match_id',
            'session_generation', 'room_context_epoch')


def _number(x):
    return type(x) in (int, float) and math.isfinite(x) and x >= 0


def _text(x):
    return isinstance(x, str) and bool(x) and x != 'Unknown'


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _context(e, origin, *, unsolicited=False):
    if not isinstance(e,dict) or not isinstance(origin,dict):
        return False
    for key in IDENTITY:
        value = e.get(key)
        if key == 'cycle_id' and unsolicited and value == 'Unknown':
            continue  # Same match/room/epochs bind an unsolicited state; no invented cycle.
        if key in ('session_generation', 'room_context_epoch'):
            if type(value) is not int or value < 0:
                return False
        elif not _text(value):
            return False
        if value != origin.get(key):
            return False
    return True


def _when(e):
    value = e.get('monotonic_ms')
    _require(_number(value) and type(e.get('event_seq')) is int and e['event_seq'] > 0,
             'missing_monotonic_or_sequence')
    return value, e['event_seq']


def _uid(x):
    try:
        value = uuid.UUID(str(x))
        return value.hex if value.int else None
    except (ValueError, TypeError, AttributeError):
        return None


def _valid_send(e, native):
    """Only independently witnessed, locally legal packets enter the denominator."""
    try:
        _when(e)
        _require(e.get('event_type') == 'command.sent' and e.get('action') == 'battle.play_cards', 'not_play')
        _require(e.get('observation_phase') == 'active' and _text(e.get('request_id')), 'not_active_play')
        for key in ('run_id', 'client_id', 'process_epoch'):
            _require(e.get(key) == native.get(key) and _text(e.get(key)), 'foreign_native')
        _require(_context(e, e), 'missing_send_context')
        d = e['dispatch_state']; _require(isinstance(d,dict),'invalid_dispatch_object')
        s = d['local_snapshot']; p = d['play_input_evidence']
        _require(isinstance(s,dict) and isinstance(p,dict),'invalid_dispatch_state_or_inputs')
        _require(d['identity_binding'] == 'SameCurrentRoute' and d['battle_relation'] == 'SameActiveBattle' and
                 d['revision_relation'] in ('SameSnapshotRevision', 'EarlierSnapshotRevision'), 'unknown_dispatch')
        _require(s['room_id'] == e['room_id'] == e['packet_room_id'] and
                 s['match_id'] == e['match_id'] == e['packet_match_id'] and
                 _uid(s['player_id']) is not None and _uid(s['player_id']) == _uid(native['user_id']), 'wrong_dispatch_actor')
        _require(s['stun_field_present'] is True and type(s['stun_remaining_ms']) is int and s['stun_remaining_ms'] == 0,
                 'known_or_unknown_stun')
        _require(s['allowed_actions_valid'] is True and isinstance(s['allowed_actions'],list) and
                 all(isinstance(v,str) for v in s['allowed_actions']) and 'battle.play_cards' in s['allowed_actions'], 'not_locally_allowed')
        _require(type(s['room_revision']) is int and s['room_revision'] >= 0 and
                 type(e['packet_expected_revision']) is int and e['packet_expected_revision'] >= s['room_revision'], 'invalid_revision')
        _require(s['active_battle_id'] == e['packet_battle_id'] and _text(s['active_battle_id']) and
                 (s['player_phase'], s['active_battle_kind']) in (('Pve', 'Pve'), ('Pvp', 'Duel')), 'wrong_battle')
        hand, chosen = s['hand_instance_ids'], e['packet_card_instance_ids']
        _require(s['hand_instance_ids_valid'] is True and e['packet_card_instance_ids_valid'] is True and
                 isinstance(hand, list) and isinstance(chosen, list) and bool(chosen) and
                 all(_text(v) for v in hand + chosen) and len(set(hand)) == len(hand) and
                 len(set(chosen)) == len(chosen) and set(chosen) <= set(hand), 'unproved_hand_or_selection')
        _require(all(p.get(k) is True for k in ('hand_valid', 'selection_valid', 'selected_ids_in_current_hand',
                                               'target_alive_in_current_view')) and
                 _text(e['packet_target_id']) and p['target_id'] == e['packet_target_id'], 'unproved_target')
        return True
    except (KeyError, TypeError, ValueError):
        return False


def _authority(e, origin, native):
    try:
        _when(e)
        _require(e.get('event_type') == 'room.command_state_observed' and
                 e.get('observation_phase') == 'active' and _context(e, origin, unsolicited=True), 'foreign_authority_context')
        a = e['authority_state']; _require(isinstance(a,dict),'invalid_authority_object')
        s = a['snapshot']; _require(isinstance(s,dict),'invalid_authority_snapshot')
        _require(a['identity_binding'] == 'SameCurrentRoute' and a['state_evidence_quality'] == 'Complete' and
                 a['missing_fields'] == [] and a['replayed'] is False and
                 type(a['sequence']) is int and a['sequence'] >= 0, 'unqualified_authority')
        _require(a['local_session_generation_at_capture'] == origin['session_generation'] and
                 a['local_room_context_epoch_at_capture'] == origin['room_context_epoch'], 'changed_authority_epoch')
        physical = e.get('_origin_context') or a.get('receive_owner')
        _require(isinstance(physical, dict) and all(physical.get(k) == origin[k] for k in
                 ('run_id', 'client_id', 'process_epoch')), 'missing_physical_authority_owner')
        for key in ('session_generation', 'room_context_epoch', 'room_id', 'match_id'):
            _require(key not in physical or physical[key] == origin[key], 'old_physical_authority_owner')
        _require(s['room_id'] == origin['room_id'] and s['match_id'] == origin['match_id'] and
                 _uid(s['player_id']) == _uid(native['user_id']) and _uid(s['player_id']) is not None,
                 'wrong_authority_actor')
        _require(type(s['room_revision']) is int and s['room_revision'] >= 0 and
                 type(s['stun_remaining_ms']) is int and 0 <= s['stun_remaining_ms'] <= 8000 and
                 s['stun_field_present'] is True and s['allowed_actions_valid'] is True and
                 isinstance(s['allowed_actions'], list) and all(isinstance(v,str) for v in s['allowed_actions']), 'incomplete_authority_fields')
        return s
    except (KeyError, TypeError, ValueError):
        return None


def _decode_error(message):
    def unique(pairs):
        d = {}
        for k, v in pairs:
            _require(k not in d, 'duplicate_error_key')
            d[k] = v
        return d
    _require(isinstance(message, str) and len(message) <= 65536 and message.startswith('command_rejected: '),
             'not_structured_rejection')
    return json.loads(message[len('command_rejected: '):], object_pairs_hook=unique)


def _authority_v2(event, origin, native):
    if not isinstance(event, dict):
        return None
    dispatch_origin = event.get('_origin_context', {})
    if not isinstance(dispatch_origin, dict):
        return None
    if dispatch_origin:
        return _authority(event, origin, native)
    # Unsolicited pushes explicitly have no business cycle. Their immutable
    # receive-owner still carries real session/room epochs; do not invent a
    # dispatch origin, or replace a contradictory value already on the row.
    if (event.get('cycle_id') != 'Unknown' or event.get('context_capture_kind') != 'uncorrelated_receive' or
            event.get('record_owner_source') != 'gateway_receive'):
        return None
    authority = event.get('authority_state')
    owner = authority.get('receive_owner') if isinstance(authority, dict) else None
    if not isinstance(owner, dict):
        return None
    for key in ('run_id', 'client_id', 'process_epoch', 'room_id', 'match_id',
                'session_generation', 'room_context_epoch'):
        if owner.get(key) != origin.get(key):
            return None
    view = dict(event)
    for key in ('session_generation', 'room_context_epoch'):
        if type(owner.get(key)) is not int or owner[key] < 0:
            return None
        if key in event and (type(event[key]) is not int or event[key] != owner[key]):
            return None
        view[key] = owner[key]
    return _authority(view, origin, native)


def review_authority_refusals(events, native_reports, *, policy=STRICT_POLICY, cutoff_clock_qualified=False):
    """Return a derived classification, retaining every original error and trace.

    V1 permits one refusal per actor/cycle;V2 permits at most one of each of
    the two registered reasons. Both retain the1% witnessed-completion bound.
    All other acceptance gates are external.
    """
    if policy not in (STRICT_POLICY, AUTHORITY_TRANSITION_POLICY, CAPACITY_RECOVERY_POLICY_V2):
        raise ValueError('unknown_authority_refusal_policy')
    result = dict(policy=policy, passed=False, expected_requests=[], unclassified_errors=[], evidence_errors=[],
                  algorithm_version=policy if policy != STRICT_POLICY else AUTHORITY_TRANSITION_POLICY, original_errors_unchanged=True,
                  capacity_acceptance=False, server_execution_state='NotObserved')
    reports = {}
    try:
        _require(isinstance(native_reports, list) and len(native_reports) <= 300, 'invalid_native_reports')
        for n in native_reports:
            _require(isinstance(n, dict) and _text(n.get('client_id')) and n['client_id'] not in reports and
                     isinstance(n.get('errors'), list), 'invalid_or_duplicate_native_report')
            reports[n['client_id']] = n
        errors = [(cid, i, e) for cid, n in reports.items() for i, e in enumerate(n['errors'])]
        result['original_error_count'] = len(errors)
        if policy == STRICT_POLICY:
            result['unclassified_errors'] = [dict(client_id=c, index=i, reason='strict_policy') for c, i, e in errors]
            result['passed'] = not errors
            return result
        _require(cutoff_clock_qualified is True, 'unqualified_cutoff_clock')
        _require(all(type(n.get('audit_lost_count')) is int and n['audit_lost_count'] == 0 and _uid(n.get('user_id')) for n in reports.values()),
                 'native_audit_or_actor_unqualified')
        targets = {}
        for cid, index, e in errors:
            try:
                _require(isinstance(e, dict) and _number(e.get('at_unix_ms')), 'invalid_error_time')
                body = _decode_error(e.get('message'))
                _require(isinstance(body,dict),'invalid_error_object')
                _require(body.get('code') == 'COMMAND_REJECTED' and body.get('_command_action') == 'battle.play_cards' and
                         body.get('_command_result') == 'rejected' and body.get('_replayed') is False and
                         body.get('_state_refresh_handled') is True and
                         body.get('detail') in (DETAIL_DUEL, DETAIL_STUN) and _text(body.get('_request_id')), 'unexpected_rejection')
                key = cid, body['_request_id']
                _require(key not in targets, 'duplicate_structured_error')
                targets[key] = dict(body=body, at=e['at_unix_ms'], error_index=index)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue  # Plain same-detail notices are associated after exact RPC review.
        sent, responses, combos = defaultdict(list), defaultdict(list), defaultdict(list)
        timelines = defaultdict(list)
        interested = {key[0] for key in targets}
        for e in events:
            _require(isinstance(e, dict) and e.get('client_id') in reports, 'foreign_audit_event')
            cid, request = e['client_id'], e.get('request_id')
            kind = e.get('event_type')
            key = cid, request
            if kind == 'command.sent' and e.get('action') == 'battle.play_cards':
                _require(_text(request), 'missing_play_request_identity')
                sent[key].append(e)
                _require(len(sent) <= 100000, 'play_request_index_bound')
            elif kind == 'realtime' and e.get('action') == 'battle.play_cards':
                responses[key].append(e)
            elif kind == 'battle.combo_resolved':
                combos[key].append(e)
            if cid in interested and kind in ('command.sent', 'room.command_state_observed'):
                if any(k[0] == cid and _number(e.get('at_unix_ms')) and t['at']-3000 <= e['at_unix_ms'] <= t['at'] + 20000
                       for k, t in targets.items()):
                    timelines[cid].append(e)
        valid_sends = {key for key, values in sent.items() if len(values) == 1 and _valid_send(values[0], reports[key[0]])}
        completed = set()
        for key in valid_sends:
            before = sent[key][0]
            if len(responses[key]) != 1:
                continue
            r = responses[key][0]
            good_combo = (len(combos[key]) == 1 and _context(combos[key][0], before) and
                          combos[key][0].get('battle_id') == before['packet_battle_id'] and
                          combos[key][0].get('gameplay_progress') is True and _when(combos[key][0]) >= _when(before))
            if (r.get('replayed') is False and _context(r, before) and _when(r) >= _when(before) and
                    ((r.get('result') == 'completed' and r.get('response_type') == 'battle.combo_resolved' and good_combo) or
                     (r.get('result') == 'rejected' and r.get('response_type') == 'error.command_rejected' and key in targets))):
                completed.add(key)
        result['verified_completed_play_requests'] = len(completed)
        cycles = Counter()
        recovery_cache = {}
        for key, t in targets.items():
            try:
                if policy == CAPACITY_RECOVERY_POLICY_V2:
                    proof = _v2_review_refusal(key, targets, reports, sent, responses, combos,
                        valid_sends, completed, timelines, recovery_cache, set())
                    result['expected_requests'].append(proof)
                    cycles[(key[0], proof['cycle_id'], proof['detail'])] += 1
                    continue
                cid, request = key; native = reports[cid]; body = t['body']; origin = body['_origin_context']
                _require(key in valid_sends and key in completed, 'missing_valid_packet_hand_or_response')
                before = sent[key][0]; dispatch = before['dispatch_state']['local_snapshot']
                _require(_context(origin, before) and _context(before, origin), 'rejection_origin_mismatch')
                _require(len(responses[key]) == 1 and not combos[key], 'rejected_request_succeeded_or_replayed')
                rejected = responses[key][0]
                _require(rejected.get('result') == 'rejected' and rejected.get('response_type') == 'error.command_rejected' and
                         rejected.get('replayed') is False and _context(rejected, origin), 'unbound_rejection_response')
                rejected_time = _when(rejected)
                _require(_when(before) < rejected_time, 'rejection_before_send')
                _require(_number(rejected.get('at_unix_ms')) and abs(rejected['at_unix_ms']-t['at']) <= 100 and
                         type(body.get('_sequence')) is int and body['_sequence'] >= 0,
                         'native_error_not_bound_to_rejection_frame')
                _require(not any(e.get('event_type')=='command.sent' and e.get('action')=='battle.play_cards' and
                         e.get('request_id')!=request and _when(before)<_when(e)<=rejected_time for e in timelines[cid]),
                         'parallel_play_before_rejected_outcome')
                states = []
                for e in timelines[cid]:
                    s = _authority(e, origin, native)
                    if (s is not None and _when(e) > _when(before) and
                            (_when(e) < rejected_time or e['authority_state']['sequence'] >= body['_sequence']) and
                            s['room_revision'] > dispatch['room_revision'] and
                            s['room_revision'] >= before['packet_expected_revision']):
                        states.append((e, s))
                states.sort(key=lambda pair: _when(pair[0]))
                _require(bool(states), 'missing_fresh_authority')
                matching = [(e,s) for e,s in states if s['player_phase']=='Pvp' and s['active_battle_kind']=='Duel' and
                    _text(s['active_battle_id']) and
                    ((body['detail']==DETAIL_DUEL and s['active_battle_id']!=before['packet_battle_id'] and s['stun_remaining_ms']==0) or
                     (body['detail']==DETAIL_STUN and s['active_battle_id']==before['packet_battle_id'] and s['stun_remaining_ms']>0))]
                _require(bool(matching), 'missing_documented_authority_transition')
                first, fresh = matching[0]
                _require(_when(first)[0] - rejected_time[0] <= 3000, 'fresh_authority_late')
                _require(fresh['player_phase'] == 'Pvp' and fresh['active_battle_kind'] == 'Duel' and
                         _text(fresh['active_battle_id']), 'wrong_new_authority_phase')
                release, legal = first, fresh
                if body['detail'] == DETAIL_DUEL:
                    _require(dispatch['player_phase'] == 'Pve' and fresh['active_battle_id'] != before['packet_battle_id'] and
                             fresh['stun_remaining_ms'] == 0, 'not_observed_Pve_to_Pvp')
                else:
                    _require(dispatch['player_phase'] == 'Pvp' and fresh['active_battle_id'] == before['packet_battle_id'] and
                             fresh['stun_remaining_ms'] > 0, 'not_observed_new_stun')
                    releases = [(e, s) for e, s in states if _when(e)>_when(first) and s['active_battle_id'] == fresh['active_battle_id'] and
                                s['player_phase'] == 'Pvp' and s['stun_remaining_ms'] == 0]
                    _require(bool(releases), 'missing_authoritative_stun_release')
                    release, legal = releases[0]
                    _require(_when(release)[0] - _when(first)[0] <= 8000, 'stun_window_unobserved_or_too_long')
                    _require(not any(e.get('event_type') == 'command.sent' and e.get('action') == 'battle.play_cards' and
                        _when(first) <= _when(e) < _when(release) for e in timelines[cid]), 'write_during_known_stun')
                _require('battle.play_cards' in legal['allowed_actions'], 'new_authority_not_playable')
                plays = [e for e in timelines[cid] if e.get('event_type') == 'command.sent' and
                         e.get('action') == 'battle.play_cards' and _when(e) > rejected_time]
                plays.sort(key=_when)
                _require(bool(plays), 'missing_new_intent')
                next_send = plays[0]; next_key = cid, next_send['request_id']
                _require(next_key != key and next_key in valid_sends and _context(next_send, origin) and
                         _when(next_send) >= _when(release) and
                         next_send['packet_battle_id'] == legal['active_battle_id'], 'new_intent_not_bound_to_new_authority')
                _require(len(responses[next_key]) == len(combos[next_key]) == 1, 'missing_unique_new_success')
                reply, combo = responses[next_key][0], combos[next_key][0]
                _require(reply.get('result') == 'completed' and reply.get('response_type') == 'battle.combo_resolved' and
                         reply.get('replayed') is False and _context(reply, origin) and _context(combo, origin) and
                         combo.get('battle_id') == legal['active_battle_id'] and combo.get('gameplay_progress') is True,
                         'new_intent_not_successfully_resolved')
                anchor = _when(release)[0] if body['detail'] == DETAIL_STUN else rejected_time[0]
                _require(_when(next_send) <= _when(reply) and _when(next_send) <= _when(combo) and
                         max(_when(reply)[0], _when(combo)[0]) - anchor <= 3000, 'successful_recovery_late')
                cycles[(cid, origin['cycle_id'])] += 1
                result['expected_requests'].append(dict(client_id=cid, request_id=request, detail=body['detail'],
                    cycle_id=origin['cycle_id'], fresh_authority_ms=_when(first)[0]-rejected_time[0],
                    authority_after_send_ms=_when(first)[0]-_when(before)[0],
                    authority_observation_relation='in_flight_before_rejection' if _when(first)<rejected_time else 'after_rejection',
                    recovery_success_ms=max(_when(reply)[0], _when(combo)[0])-rejected_time[0]))
            except (ValueError, KeyError, TypeError) as exc:
                result['evidence_errors'].append(dict(client_id=key[0], request_id=key[1], reason=str(exc)))
        if any(n > 1 for n in cycles.values()):
            result['evidence_errors'].append(dict(reason='repeated_refusal_kind_in_actor_cycle' if policy == CAPACITY_RECOVERY_POLICY_V2 else 'multiple_refusals_in_actor_cycle'))
        if targets and len(targets) * 100 > len(completed):
            result['evidence_errors'].append(dict(reason='refusal_fraction_exceeds1percent'))
        expected_keys = {(r['client_id'], r['request_id']) for r in result['expected_requests']}
        notice_counts = Counter()
        for cid, index, error in errors:
            candidates = []
            if isinstance(error, dict) and _number(error.get('at_unix_ms')):
                for key in expected_keys:
                    t = targets[key]
                    if key[0] == cid and abs(error['at_unix_ms'] - t['at']) <= 100:
                        if index == t['error_index'] or error.get('message') == t['body']['detail']:
                            candidates.append(key)
            if len(candidates) == 1:
                notice_counts[candidates[0]] += 1
            else:
                result['unclassified_errors'].append(dict(client_id=cid, index=index, reason='unassociated_native_error'))
        if any(n > 3 for n in notice_counts.values()):
            result['evidence_errors'].append(dict(reason='duplicate_notice_bound_exceeded'))
        for key, values in responses.items():
            if any(r.get('result') == 'rejected' for r in values) and key not in targets:
                result['evidence_errors'].append(dict(reason='rejected_play_missing_native_error', client_id=key[0]))
        result['expected_requests'].sort(key=lambda r:(r['client_id'],r['request_id']))
        result['unclassified_errors'].sort(key=lambda r:(r['client_id'],r['index']))
        if policy == CAPACITY_RECOVERY_POLICY_V2:
            result['inferred_short_stun_requests'] = [
                dict(client_id=r['client_id'], request_id=r['request_id'])
                for r in result['expected_requests'] if r.get('inferred_short_stun')]
            stun_keys = {k for k, t in targets.items() if t['body']['detail'] == DETAIL_STUN}
            result['structured_stun_refusals'] = len(stun_keys)
            result['positive_stun_observed_for_all_stun_refusals'] = (
                bool(stun_keys) and stun_keys <= expected_keys and
                not result['inferred_short_stun_requests'] and not result['unclassified_errors'])
            result['capacity_budget_only'] = True
        result['passed'] = not result['evidence_errors'] and not result['unclassified_errors']
    except (ValueError, KeyError, TypeError) as exc:
        result['evidence_errors'].append(dict(reason=str(exc)))
    return result


def _v2_review_refusal(key, targets, reports, sent, responses, combos,
                       valid_sends, completed, timelines, cache, active):
    """Review at most two distinct refusal kinds; never claim unseen stun as observed."""
    if key in cache:
        return dict(cache[key])
    _require(key not in active and len(active) < 2, 'recovery_chain_exceeds2_refusals')
    active = active | {key}
    cid, request = key
    t = targets[key]; body = t['body']; native = reports[cid]
    origin = body['_origin_context']
    _require(key in valid_sends and key in completed, 'missing_valid_packet_hand_or_response')
    before = sent[key][0]; dispatch = before['dispatch_state']['local_snapshot']
    _require(_context(origin, before) and _context(before, origin), 'rejection_origin_mismatch')
    _require(len(responses[key]) == 1 and not combos[key], 'rejected_request_succeeded_or_replayed')
    rejected = responses[key][0]; rejected_time = _when(rejected)
    _require(rejected.get('result') == 'rejected' and rejected.get('response_type') == 'error.command_rejected' and
             rejected.get('replayed') is False and _context(rejected, origin), 'unbound_rejection_response')
    _require(_when(before) < rejected_time and rejected_time[0] - _when(before)[0] <= 3000,
             'original_request_3000ms_boundary')
    _require(_number(rejected.get('at_unix_ms')) and abs(rejected['at_unix_ms'] - t['at']) <= 100 and
             type(body.get('_sequence')) is int and body['_sequence'] >= 0,
             'native_error_not_bound_to_rejection_frame')
    _require(not any(e.get('event_type') == 'command.sent' and e.get('action') == 'battle.play_cards' and
             e.get('request_id') != request and _when(before) < _when(e) <= rejected_time
             for e in timelines[cid]), 'parallel_play_before_rejected_outcome')
    plays = sorted((e for e in timelines[cid] if e.get('event_type') == 'command.sent' and
                    e.get('action') == 'battle.play_cards' and _when(e) > rejected_time), key=_when)
    _require(bool(plays), 'missing_new_intent')
    next_send = plays[0]; next_key = cid, next_send['request_id']
    qualified = []
    for event in timelines[cid]:
        state = _authority_v2(event, origin, native)
        if state is not None and _when(event) > _when(before):
            qualified.append((event, state))
    states = [(e, s) for e, s in qualified if
              (_when(e) < rejected_time or e['authority_state']['sequence'] >= body['_sequence']) and
              s['room_revision'] > dispatch['room_revision'] and
              s['room_revision'] >= before['packet_expected_revision']]
    states.sort(key=lambda pair: _when(pair[0]))
    inferred = False
    if body['detail'] == DETAIL_DUEL:
        _require(dispatch['player_phase'] == 'Pve', 'not_observed_Pve_to_Pvp')
        matching = [(e, s) for e, s in states if s['player_phase'] == 'Pvp' and
                    s['active_battle_kind'] == 'Duel' and _text(s['active_battle_id']) and
                    s['active_battle_id'] != before['packet_battle_id'] and s['stun_remaining_ms'] == 0]
        _require(bool(matching), 'missing_documented_authority_transition')
        first, fresh = matching[0]; release, legal = first, fresh
        anchor = rejected_time[0]
        basis = 'observed_Pve_to_Pvp'
    else:
        _require(dispatch['player_phase'] == 'Pvp', 'not_locally_legal_Pvp')
        positive = [(e, s) for e, s in states if s['player_phase'] == 'Pvp' and
                    s['active_battle_kind'] == 'Duel' and s['active_battle_id'] == before['packet_battle_id'] and
                    s['stun_remaining_ms'] > 0 and _when(e) <= _when(next_send)]
        if positive:
            first, fresh = positive[0]
            releases = [(e, s) for e, s in states if _when(e) > _when(first) and
                        s['player_phase'] == 'Pvp' and s['active_battle_id'] == fresh['active_battle_id'] and
                        s['stun_remaining_ms'] == 0]
            _require(bool(releases), 'missing_authoritative_stun_release')
            release, legal = releases[0]
            _require(_when(release)[0] - _when(first)[0] <= 8000, 'stun_window_unobserved_or_too_long')
            _require(not any(e.get('event_type') == 'command.sent' and e.get('action') == 'battle.play_cards' and
                     _when(first) <= _when(e) < _when(release) for e in timelines[cid]), 'write_during_known_stun')
            anchor = _when(release)[0]
            basis = 'observed_new_stun_and_release'
        else:
            _require(not any(s['player_phase'] == 'Pvp' and s['active_battle_id'] == before['packet_battle_id'] and
                     s['stun_remaining_ms'] > 0 and _when(e) <= _when(next_send) for e, s in qualified),
                     'positive_stun_present_but_not_fresh')
            zero = [(e, s) for e, s in states if _when(e) > rejected_time and s['player_phase'] == 'Pvp' and
                    s['active_battle_kind'] == 'Duel' and s['active_battle_id'] == before['packet_battle_id'] and
                    s['stun_remaining_ms'] == 0 and e['authority_state'].get('post_refusal_revision_capture') is True]
            _require(bool(zero), 'missing_fresh_playable_zero_stun_authority')
            first, fresh = zero[0]; release, legal = first, fresh
            anchor = rejected_time[0]
            inferred = True
            basis = 'server_reported_stun_with_observed_playable_recovery_not_positive_stun_proof'
    _require(_when(first)[0] - rejected_time[0] <= 3000, 'fresh_authority_late')
    _require('battle.play_cards' in legal['allowed_actions'], 'new_authority_not_playable')
    _require(next_key != key and next_key in valid_sends and _context(next_send, origin) and
             _when(next_send) >= _when(release) and next_send['packet_battle_id'] == legal['active_battle_id'],
             'new_intent_not_bound_to_new_authority')
    contains_inferred = inferred
    if next_key in targets:
        _require(body['detail'] == DETAIL_DUEL and targets[next_key]['body']['detail'] == DETAIL_STUN,
                 'unsupported_refusal_chain')
        child = _v2_review_refusal(next_key, targets, reports, sent, responses, combos,
                    valid_sends, completed, timelines, cache, active)
        _require(_when(responses[next_key][0])[0] - rejected_time[0] <= 3000,
                 'first_recovery_hop_late')
        final_ms = child['recovery_success_monotonic_ms']
        _require(final_ms - rejected_time[0] <= 6000, 'two_hop_recovery_exceeds6000ms')
        path = [request] + child['recovery_path']
        recovery_request = child['recovery_request_id']
        contains_inferred = child['contains_inferred_recovery_hop']
        basis = 'observed_Pve_to_Pvp_then_one_independently_qualified_stun_refusal'
    else:
        _require(len(responses[next_key]) == len(combos[next_key]) == 1, 'missing_unique_new_success')
        reply, combo = responses[next_key][0], combos[next_key][0]
        _require(reply.get('result') == 'completed' and reply.get('response_type') == 'battle.combo_resolved' and
                 reply.get('replayed') is False and _context(reply, origin) and _context(combo, origin) and
                 combo.get('battle_id') == legal['active_battle_id'] and combo.get('gameplay_progress') is True,
                 'new_intent_not_successfully_resolved')
        _require(_when(next_send) <= _when(reply) and _when(next_send) <= _when(combo) and
                 _when(reply)[0] - _when(next_send)[0] <= 3000, 'new_request_3000ms_boundary')
        final_ms = max(_when(reply)[0], _when(combo)[0])
        _require(final_ms - anchor <= 3000, 'successful_recovery_late')
        path = [request, next_send['request_id']]; recovery_request = next_send['request_id']
    proof = dict(client_id=cid, request_id=request, detail=body['detail'], cycle_id=origin['cycle_id'],
        basis=basis, inferred_short_stun=inferred, contains_inferred_recovery_hop=contains_inferred,
        authority_owner_basis='scoped_unsolicited_receiver' if first.get('cycle_id') == 'Unknown' and not first.get('_origin_context') else 'dispatch_origin',
        server_execution_state='NotObserved', fresh_authority_ms=_when(first)[0] - rejected_time[0],
        authority_after_send_ms=_when(first)[0] - _when(before)[0],
        recovery_success_ms=final_ms - rejected_time[0], recovery_success_monotonic_ms=final_ms,
        recovery_request_id=recovery_request, recovery_path=path)
    cache[key] = dict(proof)
    return proof
