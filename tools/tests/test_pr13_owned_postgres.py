"""Ownership and failure tests for the portable PostgreSQL fixture bridge."""
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'client/tests'))
import owned_postgres as bridge

class OwnedPostgresTests(unittest.TestCase):
    def host(self):
        with patch.object(bridge, 'owned_database_info', return_value=dict(container_id='frozen-id', user='postgres', port=54321, password='disposable')):
            return bridge.OwnedPostgres('owned')

    def test_unowned_database_is_rejected_before_query(self):
        host=self.host()
        with patch.object(bridge.subprocess, 'run') as run:
            for statement, database in [('SELECT 1','production'), ('DROP DATABASE production','postgres'), ('CREATE DATABASE unrelated','postgres')]:
                with self.assertRaises(ValueError): host.sql(statement,database)
            run.assert_not_called()

    def test_failed_creation_never_authorizes_connection_or_cleanup(self):
        host=self.host(); database='ready_stop_'+'a'*32
        with patch.object(bridge.subprocess, 'run', return_value=SimpleNamespace(returncode=1,stdout='')) as run:
            with self.assertRaises(RuntimeError): host.sql('CREATE DATABASE '+database)
            with self.assertRaises(ValueError): host.connection(database)
            host.close()
            self.assertEqual(run.call_count,1)
            self.assertEqual(host.created,[])

    def test_cleanup_failure_preserves_unremoved_ownership(self):
        host=self.host(); database='ready_stop_'+'b'*32
        with patch.object(bridge.subprocess, 'run', return_value=SimpleNamespace(returncode=0,stdout='')):
            host.sql('CREATE DATABASE '+database)
        with patch.object(bridge.subprocess, 'run', return_value=SimpleNamespace(returncode=1,stdout='')):
            with self.assertRaises(RuntimeError): host.close()
        self.assertEqual(host.created,[database])
        with patch.object(bridge.subprocess, 'run', return_value=SimpleNamespace(returncode=0,stdout='')) as run:
            host.close()
            self.assertEqual(run.call_args.args[0][2],'frozen-id')
            self.assertEqual(host.created,[])

if __name__ == '__main__': unittest.main()
