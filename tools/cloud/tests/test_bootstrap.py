"""Run the real Start shell with tiny tool fixtures, including failed SQL."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class Bootstrap(unittest.TestCase):
    def test_repeat_start_without_rg_and_sql_failure_propagation(self):
        script=Path(__file__).resolve().parents[1]/'start.sh'
        with tempfile.TemporaryDirectory(prefix='fc-start-',dir='/tmp') as directory:
            root=Path(directory);pg=root/'postgres/bin';pg.mkdir(parents=True)
            (root/'postgres-test/data').mkdir(parents=True)
            (root/'postgres-test/data/PG_VERSION').write_text('18\n')
            dotnet=root/'dotnet/dotnet';dotnet.parent.mkdir()
            dotnet.write_text('#!/bin/sh\nexit 0\n');dotnet.chmod(0o755)
            for name in ('pg_ctl','pg_isready'):
                (pg/name).write_text('#!/bin/sh\nexit 0\n');(pg/name).chmod(0o755)
            (pg/'psql').write_text('''#!/bin/sh
case "$*" in
*listen_addresses*) exit 0 ;;
*) [ -z "${FAIL_SQL:-}" ] || exit 2
   [ ! -f "$FANTASYCARD_CLOUD_TOOLS/database.exists" ] || printf '1\\n' ;;
esac
''');(pg/'psql').chmod(0o755)
            (pg/'createdb').write_text('''#!/bin/sh
[ ! -f "$FANTASYCARD_CLOUD_TOOLS/database.exists" ] || exit 1
printf 'created\\n' >> "$FANTASYCARD_CLOUD_TOOLS/create.calls"
touch "$FANTASYCARD_CLOUD_TOOLS/database.exists"
''');(pg/'createdb').chmod(0o755)
            context=dict(os.environ,FANTASYCARD_CLOUD_TOOLS=str(root))
            for _ in range(2):
                result=subprocess.run(['bash',str(script)],env=context,capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((root/'create.calls').read_text(),'created\n')
            (root/'database.exists').unlink()
            result=subprocess.run(['bash',str(script)],env=dict(context,FAIL_SQL='true'),capture_output=True,text=True,timeout=15)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((root/'database.exists').exists())
            self.assertEqual((root/'create.calls').read_text(),'created\n')
            self.assertNotIn('rg ',script.read_text())


if __name__=='__main__':unittest.main()
