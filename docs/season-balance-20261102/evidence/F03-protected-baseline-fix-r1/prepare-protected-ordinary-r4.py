from pathlib import Path

b = Path(__file__).parent
target = b / 'run-protected-ordinary-r4.py'
assert not target.exists()
s = (b / 'run-protected-ordinary-r3.py').read_text('utf-8').replace('protected-ordinary-r3', 'protected-ordinary-r4')
s = s.replace("selected = [r for r in ordinary if (r['type'], r['method']) not in prior_names]",
              "selected = [r for r in ordinary if (r['type'], r['method']) not in prior_names and r['type'].startswith('FantasyCard.Server.Tests.')]")
s = s.replace('assert len(selected) == 1058', 'assert len(selected) == 631')
s = s.replace('original_popen = subprocess.Popen', 'jobs = [job]\nactive_job = [job]\noriginal_popen = subprocess.Popen')
s = s.replace('kernel.AssignProcessToJobObject(job, int(child._handle))', 'kernel.AssignProcessToJobObject(active_job[0], int(child._handle))')
s = s.replace('breached.set(); kernel.TerminateJobObject(job, 91); return',
              'breached.set()\n            for handle in list(jobs): kernel.TerminateJobObject(handle, 91)\n            return')
start = s.index('        target = out / suite.stem; target.mkdir()')
end = s.index('    assert all(sha(Path(p))', start)
inner = '''        failed_batches = []
        for offset in range(0, len(rows), 60):
            batch_rows = rows[offset:offset + 60]
            target = out / (suite.stem + '-b' + str(offset // 60 + 1).zfill(2)); target.mkdir()
            settings = target / 'ordinary.runsettings'
            root = ET.Element('RunSettings'); config = ET.SubElement(root, 'RunConfiguration')
            ET.SubElement(config, 'MaxCpuCount').text = '1'
            ET.SubElement(config, 'TestCaseFilter').text = '|'.join('FullyQualifiedName=' + r['type'] + '.' + r['method'] for r in batch_rows)
            ET.ElementTree(root).write(settings, encoding='utf-8', xml_declaration=True)
            test_job = kernel.CreateJobObjectW(None, None); assert test_job
            assert kernel.SetInformationJobObject(test_job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
            jobs.append(test_job); active_job[0] = test_job
            print(json.dumps(dict(batch=offset // 60 + 1, methods=len(batch_rows), started=True)), flush=True)
            batch_error = None; run = None
            try:
                run = guard.guarded_run(['dotnet', 'vstest', str(suite), '--Settings:' + str(settings), '--Logger:trx', '--ResultsDirectory:' + str(target)], env=env, timeout=600, wait_seconds=30)
                (target / 'run.original.log').write_text(run.stdout + run.stderr, encoding='utf-8')
            except subprocess.TimeoutExpired as exc:
                def as_text(value):
                    return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
                (target / 'run.original.log').write_text(as_text(exc.output) + as_text(exc.stderr), encoding='utf-8')
                batch_error = dict(type='TimeoutExpired', seconds=600)
            finally:
                active_job[0] = job
                kernel.TerminateJobObject(test_job, 93)
                jobs.remove(test_job); kernel.CloseHandle(test_job)
            assert not breached.is_set(), 'Memory reserve breached'
            totals = {k: 0 for k in ('total', 'passed', 'failed', 'notExecuted')}
            trxs = list(target.glob('*.trx')); actual = []
            declared = {(r['type'], r['method']) for r in batch_rows}
            for trx in trxs:
                document = ET.parse(trx); counters = document.find('.//{*}Counters'); assert counters is not None
                for key in totals: totals[key] += int(counters.get(key, '0'))
                for definition in document.findall('.//{*}UnitTest'):
                    method = definition.find('{*}TestMethod'); assert method is not None
                    pair = (method.get('className', '').split(',')[0], method.get('name', ''))
                    assert pair in declared, ('Unexpected test definition', pair)
                    actual.append(pair)
            ok = bool(run is not None and run.returncode == 0 and trxs and totals['total'] > 0 and totals['passed'] == totals['total'] and totals['notExecuted'] == 0 and set(actual) == declared)
            summary = dict(batch=offset // 60 + 1, assembly=suite.name, returncode=run.returncode if run else None,
                           selected_method_definitions=len(batch_rows), actual_method_definitions=len(set(actual)),
                           tests=totals, ok=ok, error=batch_error, own_test_job_closed=True)
            runs.append(summary)
            (target / 'result.json').write_text(json.dumps(summary, indent=2) + '\\n')
            (out / 'runs.checkpoint.json').write_text(json.dumps(runs, indent=2) + '\\n')
            print(json.dumps(summary), flush=True)
            if not ok: failed_batches.append(summary['batch'])
        assert not failed_batches, ('Failed/incomplete batches', failed_batches)
'''
s = s[:start] + inner + s[end:]
s = s.replace('            kernel.TerminateJobObject(job, 92)', '            kernel.TerminateJobObject(job, 92)')
target.write_text(s, encoding='utf-8')
print(target)
