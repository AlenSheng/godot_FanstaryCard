"""Bridge a validated task-owned Docker PostgreSQL to portable local fixtures."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.pr13_local_runtime import owned_database_info


class OwnedPostgres:
    def __init__(self, container):
        self.container = container
        self.info = owned_database_info(container)
        self.created = []

    def sql(self, statement, database='postgres'):
        fresh = r'ready_stop_[0-9a-f]{32}'
        if database == 'postgres':
            creation = re.fullmatch('CREATE DATABASE (' + fresh + ')', statement)
            deletion = re.fullmatch('DROP DATABASE IF EXISTS (' + fresh + r') WITH \(FORCE\)', statement)
            if statement != 'SELECT version()' and not creation and not (deletion and deletion[1] in self.created):
                raise ValueError('Only fixture creation, owned cleanup or version queries allowed')
        elif not re.fullmatch(fresh, database):
            raise ValueError('Only disposable READY fixture databases allowed')
        result = subprocess.run(['docker', 'exec', self.info['container_id'], 'psql', '-X', '-A', '-t',
            '-v', 'ON_ERROR_STOP=1', '-U', self.info['user'], '-d', database, '-c', statement],
            capture_output=True, timeout=30, text=True, encoding='utf8',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode: raise RuntimeError('Owned fixture database query failed')
        if database == 'postgres' and statement.startswith('CREATE DATABASE '):
            self.created.append(statement.removeprefix('CREATE DATABASE '))
        return result.stdout.strip()

    def connection(self, database):
        if database not in self.created: raise ValueError('Only this fixture-created database is allowed')
        return f"Host=127.0.0.1;Port={self.info['port']};Database={database};Username={self.info['user']};Password={self.info['password']};Timeout=10;Command Timeout=30"

    def close(self):
        for database in self.created[:]:
            self.sql('DROP DATABASE IF EXISTS ' + database + ' WITH (FORCE)')
            self.created.remove(database)
