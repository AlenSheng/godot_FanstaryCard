"""Offline status snapshot and heartbeat evidence regression controls."""
import json
import sys
from pathlib import Path
import tempfile
import unittest
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pr13_status_snapshot import SerializedStatusCache
from gameplay_load_test import read_owned_statuses

class Process:
    pid=41
    def poll(self):return None

class SnapshotTests(unittest.TestCase):
    def snapshot(self):
        return {'client_id':'c','pid':41,'run_id':'r','process_epoch':'e','status_seq':1,
                'event_seq_max':0,'telemetry':[],'operations':[],'errors':[],
                'opaque':{'text':'牧师80/70🙂','surrogate':'\ud800','large':2**80,'bool':True,'none':None},
                '_received_at_monotonic_ms':1234.5}

    def test_complete_nested_roundtrip(self):
        row=self.snapshot();cache=SerializedStatusCache();cache['c']=row
        self.assertEqual(cache['c'],row)

    def test_stored_snapshot_is_independent_of_mutation(self):
        row=self.snapshot();cache=SerializedStatusCache();cache['c']=row
        row['opaque']['text']='changed';decoded=cache['c'];decoded['opaque']['text']='other'
        self.assertEqual(cache['c']['opaque']['text'],'牧师80/70🙂')

    def test_mapping_default_update_delete_and_payload_scope(self):
        cache=SerializedStatusCache();self.assertIsNone(cache.get('missing'));cache.update({'c':self.snapshot()})
        self.assertEqual(list(cache),['c']);self.assertLess(cache.retained_bytes,cache.decoded_snapshot_bytes)
        del cache['c'];self.assertEqual((len(cache),cache.retained_bytes),(0,0))

    def test_invalid_bounds_and_non_object_are_rejected(self):
        for bound in (True,0,-1,32*1024*1024+1):
            with self.subTest(bound=bound),self.assertRaises(ValueError):SerializedStatusCache(max_snapshot_bytes=bound)
        with self.assertRaises(ValueError):SerializedStatusCache().__setitem__('c',[])
        with self.assertRaises(ValueError):SerializedStatusCache(max_snapshot_bytes=8).__setitem__('c',{'text':'oversize'})

    def test_corrupt_truncated_extra_and_wrong_sizes_are_rejected(self):
        for record in ((9,zlib.compress(b'{"x":123}')[:-1]),(9,zlib.compress(b'{"x":123}')+b'extra'),
                       (2,zlib.compress(b'{"x":123}')),(999999999,b'')):
            with self.subTest(record=record):
                cache=SerializedStatusCache();cache._entries['c']=record
                with self.assertRaises(ValueError):cache['c']

    def test_reader_same_results_and_clock_for_both_cache_types(self):
        results=[]
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'c.json';path=Path(str(report)+'.status.json')
            entry={'client_id':'c','run_id':'r','process_epoch':'e','process':Process(),'report':report}
            row=self.snapshot();row.pop('_received_at_monotonic_ms');row['now_unix_ms']=1
            for factory in (dict,SerializedStatusCache):
                cache=factory();observed=[];path.write_text(json.dumps(row))
                observed.append(read_owned_statuses([entry],cache,1000))
                observed.append(read_owned_statuses([entry],cache,9000))
                newer=dict(row,status_seq=2,now_unix_ms=2);path.write_text(json.dumps(newer))
                observed.append(read_owned_statuses([entry],cache,10000))
                path.unlink();observed.append(read_owned_statuses([entry],cache,11000))
                path.write_text(json.dumps(newer|{'opaque':{'text':'tampered'}}));observed.append(read_owned_statuses([entry],cache,12000))
                path.write_text(json.dumps(row));observed.append(read_owned_statuses([entry],cache,13000));results.append(observed)
        self.assertEqual(results[0],results[1]);rows=results[1]
        self.assertEqual(rows[1][0][0]['_received_at_monotonic_ms'],1000)
        self.assertEqual(rows[3][0][0]['_received_at_monotonic_ms'],10000)
        self.assertEqual((rows[4][1],rows[5][1]),(1,1))

if __name__=='__main__':unittest.main()
