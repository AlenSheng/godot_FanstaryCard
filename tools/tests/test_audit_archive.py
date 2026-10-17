"""Owned local I/O fault cases, not gameplay/capacity experiments."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pr13_audit_archive import (read_owned_audits, validate_storage, OwnedAuditEvents,
                               MAX_DIAGNOSTICS, MAX_SEGMENTS, RECORD_LIMIT_BYTES)
from gameplay_load_validation import request_cutoffs
from pr13_runtime_evidence import reconcile_cycles
from gameplay_load_test import read_native_final_reports, read_owned_statuses


class AuditArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.entry = dict(client_id='client', run_id='run', process_epoch='epoch',
                          report=self.root/'client.json', process=SimpleNamespace(pid=7))

    def row(self, seq, **changes):
        return dict(run_id='run', client_id='client', process_epoch='epoch', event_seq=seq,
                    cycle_id='cycle', match_id='match', type='lifecycle', event_type='room.started',
                    at_unix_ms=1000 + seq, **changes)

    def segment(self, index, rows):
        path = Path(str(self.entry['report']) + '.telemetry' + ('.'+str(index) if index else '') + '.jsonl')
        path.write_bytes(b''.join((json.dumps(r,ensure_ascii=False)+'\n').encode() for r in rows))
        return path

    def final(self, sizes, count, maximum=None, **changes):
        metadata = dict(version=1, record_limit_bytes=RECORD_LIMIT_BYTES, segment_limit_bytes=1024*1024,
                        max_segments=MAX_SEGMENTS, segment_count=len(sizes), segment_bytes=sizes,
                        bytes_written=sum(sizes), events_written=count, buffer_count=0,
                        buffer_serialized_bytes=0, last_error='')
        return dict(client_id='client', event_seq_max=count if maximum is None else maximum,
                    audit_storage=metadata, **changes)

    def read(self, final, **bounds):
        events, errors = read_owned_audits([self.entry], [final], **bounds)
        if hasattr(events,'close'):self.addCleanup(events.close)
        return events, errors

    def test_legacy_single_file_is_replayable_and_original_bytes_unchanged(self):
        path=self.segment(0,[self.row(1),self.row(2)]);before=path.read_bytes()
        events, errors=self.read(dict(client_id='client',event_seq_max=2))
        self.assertEqual(errors,[]);self.assertEqual(list(events),list(events));self.assertEqual(len(events),2)
        self.assertEqual(path.read_bytes(),before)

    def test_segmented_archive_preserves_order_watermark_and_utf8_sizes(self):
        p=self.segment(0,[self.row(1,note='合法80/70')]);q=self.segment(1,[self.row(2)])
        events,errors=self.read(self.final([p.stat().st_size,q.stat().st_size],2))
        self.assertEqual(errors,[]);self.assertEqual([e['event_seq'] for e in events],[1,2])

    def test_missing_middle_segment_is_invalid_even_with_a_matching_final_watermark(self):
        p=self.segment(0,[self.row(1)]);q=self.segment(2,[self.row(3)])
        events,errors=self.read(self.final([p.stat().st_size,0,q.stat().st_size],3))
        self.assertEqual([e['event_seq'] for e in events],[1,3])
        self.assertIn('FileNotFoundError',{e['error'] for e in errors})
        self.assertIn('event_sequence_gap_or_reorder',{e['error'] for e in errors})

    def test_duplicate_or_reordered_rows_are_not_two_events(self):
        p=self.segment(0,[self.row(1),self.row(1),self.row(3),self.row(2)])
        events,errors=self.read(self.final([p.stat().st_size],4,maximum=3))
        self.assertEqual([e['event_seq'] for e in events],[1,3]);self.assertTrue(errors)

    def test_foreign_context_is_excluded_and_cannot_repair_watermark(self):
        row=self.row(1);row['process_epoch']='foreign';p=self.segment(0,[row])
        events,errors=self.read(self.final([p.stat().st_size],1))
        self.assertEqual(list(events),[]);self.assertIn('foreign_event_context',{e['error'] for e in errors})

    def test_corrupt_json_is_invalid_even_when_the_status_is_good(self):
        p=self.segment(0,[]);p.write_bytes(b'{broken\n')
        events,errors=self.read(self.final([p.stat().st_size],1))
        self.assertEqual(len(events),0);self.assertIn('invalid_json',{e['error'] for e in errors})

    def test_declared_segment_size_is_checked_against_actual_file(self):
        p=self.segment(0,[self.row(1)]);events,errors=self.read(self.final([p.stat().st_size+1],1))
        self.assertIn('audit_segment_size_mismatch',{e['error'] for e in errors})

    def test_extra_segment_including_first_forbidden_index_is_not_hidden(self):
        p=self.segment(0,[self.row(1)]);self.segment(MAX_SEGMENTS,[self.row(2)])
        events,errors=self.read(self.final([p.stat().st_size],1))
        self.assertIn('unexpected_audit_segment',{e['error'] for e in errors})

    def test_declared_file_limit_is_enforced_before_reading_body(self):
        p=self.segment(0,[self.row(1)]);final=self.final([p.stat().st_size],1)
        limit=p.stat().st_size-1
        final['audit_storage'].update(segment_limit_bytes=limit,segment_bytes=[limit],bytes_written=limit)
        events,errors=self.read(final)
        self.assertEqual(len(events),0);self.assertIn('audit_segment_size_limit',{e['error'] for e in errors})

    def test_oversized_utf8_record_is_not_read_unbounded(self):
        p=self.segment(0,[self.row(1,note='甲'*RECORD_LIMIT_BYTES)])
        events,errors=self.read(self.final([p.stat().st_size],1))
        self.assertEqual(len(events),0);self.assertIn('audit_record_or_segment_size_limit',{e['error'] for e in errors})

    def test_metadata_cannot_request_unbounded_files_or_fake_boolean_limits(self):
        p=self.segment(0,[self.row(1)]);final=self.final([p.stat().st_size],1)
        for key,value in [('version',True),('segment_count',10**20),('record_limit_bytes',True),('buffer_count',1)]:
            changed=json.loads(json.dumps(final));changed['audit_storage'][key]=value
            self.assertFalse(validate_storage(changed['audit_storage']))
            _,errors=self.read(changed);self.assertIn('audit_storage_invalid',{e['error'] for e in errors})

    def test_wrong_final_watermark_is_not_repaired_from_archive(self):
        p=self.segment(0,[self.row(1)]);_,errors=self.read(self.final([p.stat().st_size],1,maximum=2))
        self.assertIn('final_audit_watermark_mismatch',{e['error'] for e in errors})

    def test_spool_record_quota_fails_explicitly_without_changing_original(self):
        p=self.segment(0,[self.row(1),self.row(2)]);raw=p.read_bytes()
        events,errors=self.read(self.final([len(raw)],2),max_records=1)
        self.assertEqual(len(events),1);self.assertIn('audit_spool_record_limit',{e['error'] for e in errors})
        self.assertEqual(p.read_bytes(),raw)

    def test_spool_byte_quota_fails_explicitly(self):
        p=self.segment(0,[self.row(1),self.row(2)]);row_size=len(p.read_bytes().splitlines(keepends=True)[0])
        events,errors=self.read(self.final([p.stat().st_size],2),max_bytes=row_size+1)
        self.assertEqual(len(events),1);self.assertIn('audit_spool_byte_limit',{e['error'] for e in errors})

    def test_diagnostics_have_a_bound_and_preserve_suppressed_error_totals(self):
        rows=[self.row(i) for i in range(1,601)]
        for row in rows:row['run_id']='foreign'
        p=self.segment(0,rows);_,errors=self.read(self.final([p.stat().st_size],600))
        self.assertLessEqual(len(errors),MAX_DIAGNOSTICS+1)
        self.assertEqual(errors[-1]['error'],'audit_diagnostics_truncated')
        self.assertEqual(errors[-1]['counts_by_error']['foreign_event_context'],600)

    def test_replayed_stream_and_legacy_list_have_identical_cycle_and_latency_results(self):
        rows=[]
        for seq in range(1,25):
            r=self.row(seq)
            if seq%4==0:r.update(type='http',event_type='http',duration_ms=seq,status=200,ok=True,result='success',phase='playing',path='/api/v1/test')
            elif seq==21:r['event_type']='settlement.acknowledged'
            elif seq==22:r['event_type']='cycle.completed'
            rows.append(r)
        p=self.segment(0,rows);events,errors=self.read(self.final([p.stat().st_size],24));self.assertEqual(errors,[])
        for qualified in [True,False]:
            self.assertEqual(reconcile_cycles(events,1015,1030,cutoff_clock_qualified=qualified),reconcile_cycles(rows,1015,1030,cutoff_clock_qualified=qualified))
            self.assertEqual(request_cutoffs(events,1015,1030,started_ms=1000,cutoff_clock_qualified=qualified),request_cutoffs(rows,1015,1030,started_ms=1000,cutoff_clock_qualified=qualified))

    def test_nonbusiness_context_errors_are_not_lost_by_stream_projection(self):
        rows=[self.row(1),self.row(2)];rows[0]['cycle_id']='';rows[1]['match_id']=7
        p=self.segment(0,rows);events,_=self.read(self.final([p.stat().st_size],2))
        self.assertEqual(reconcile_cycles(events,1010,1020),reconcile_cycles(rows,1010,1020))

    def test_spool_tampering_is_detected_and_temporary_file_is_removed(self):
        p=self.segment(0,[self.row(1)]);events,errors=self.read(self.final([p.stat().st_size],1));self.assertEqual(errors,[])
        spool=events.path;spool.write_bytes(spool.read_bytes()+b'{}\n')
        with self.assertRaises(ValueError):list(events)
        events.close();self.assertFalse(spool.exists())

    def test_primary_and_status_storage_metadata_must_agree(self):
        final=self.final([],0);report=dict(final,run_id='run',process_epoch='epoch',pid=7,ok=True,
                                          cycles_completed=0,audit_lost_count=0,errors=[],cleanup={'state':'Passed'},outcome='completed')
        self.entry['report'].write_text(json.dumps(report))
        status=dict(report);status['audit_storage']=dict(report['audit_storage'],last_error='changed')
        _,errors=read_native_final_reports([self.entry],[status])
        self.assertIn('native_final_status_disagreement',{e['error'] for e in errors})

    def test_oversized_status_is_rejected_instead_of_caching_as_new(self):
        path=Path(str(self.entry['report'])+'.status.json')
        with path.open('wb') as f:f.truncate(8*1024*1024+1)
        statuses,invalid=read_owned_statuses([self.entry],require_files=True)
        self.assertEqual(statuses,[]);self.assertEqual(invalid,1)


    def test_actual_coordinator_classifies_spool_corruption_after_verification(self):
        import gameplay_load_test as coordinator
        from unittest.mock import patch
        from tools.tests import test_gameplay_load_sampling_contract as fixtures
        original = coordinator.read_audit_events
        def corrupt(processes, final):
            events, errors = original(processes, final)
            events.path.write_bytes(events.path.read_bytes() + b'{}\n')
            return events, errors
        helper = fixtures.CoordinatorSamplingContractTests()
        with patch.object(coordinator, 'read_audit_events', side_effect=corrupt):
            code, report = helper.run_fixture()
        self.assertEqual(code, 3)
        self.assertEqual(report['result_dimensions']['dimensions']['evidence'], 'Failed')
        self.assertTrue(report['audit_read_errors'])

    def test_spool_flush_failure_returns_invalid_evidence_instead_of_escaping(self):
        from unittest.mock import patch
        p=self.segment(0,[self.row(1)])
        with patch.object(OwnedAuditEvents, 'seal', side_effect=OSError('owned controlled failure')):
            events,errors=self.read(self.final([p.stat().st_size],1))
        self.assertEqual(events,[])
        self.assertIn('audit_spool_finalize_failed',{e['error'] for e in errors})

    def test_spool_disk_floor_is_visible_without_physical_exhaustion(self):
        from unittest.mock import patch
        p=self.segment(0,[self.row(1)])
        with patch('pr13_audit_archive.shutil.disk_usage', return_value=SimpleNamespace(total=1000,free=1)):
            events,errors=self.read(self.final([p.stat().st_size],1))
        self.assertEqual(len(events),0)
        self.assertIn('audit_spool_disk_floor',{e['error'] for e in errors})

if __name__=='__main__':unittest.main()
