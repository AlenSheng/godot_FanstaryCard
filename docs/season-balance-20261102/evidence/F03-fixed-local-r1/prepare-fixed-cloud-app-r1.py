from pathlib import Path
import ast

b = Path(__file__).parent
old_label = 'season-balance-20261107-f03-minimal-app-r5'
label = 'season-balance-20261107-f03-fixed-app-r1'
worker = (b / 'f03-minimal-app-worker-r5.py').read_text('utf-8')
worker = worker.replace(old_label, label).replace('fc-f03-app5-', 'fc-f03-fixed1-').replace('app-candidate-r5', 'app-candidate-fixed1')
tree = ast.parse(worker)
probe_nodes = [node.args[0] for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and node.func.attr == 'write_text' and node.args and isinstance(node.args[0], ast.Constant)
               and isinstance(node.args[0].value, str) and 'def request(method,path' in node.args[0].value]
assert len(probe_nodes) == 1
literal = ast.get_source_segment(worker, probe_nodes[0]); probe = probe_nodes[0].value
needle = "bootstrap=request('GET','/api/v1/bootstrap');check('unauthenticated typed bootstrap',bootstrap,401,'protobuf' in bootstrap['headers'].get('Content-Type',''))\n"
assert needle in probe
addition = """for query in ['', '?seasonId=season&recipeId=invalid&bodyEquipmentId=invalid']:
    response=request('GET','/api/v1/season-crafting/reforge-quote'+query)
    check('reforge quote authenticates before query '+('missing' if not query else 'malformed'),response,401,'protobuf' in response['headers'].get('Content-Type',''))
"""
probe = probe.replace(needle, needle + addition)
worker = worker.replace(literal, repr(probe), 1)
assert "len(http['checks'])==12" not in worker and 'len(http["checks"])==12' not in worker
compile(worker, 'fixed-cloud-worker', 'exec')
worker_path = b / 'f03-fixed-app-worker-r1.py'; assert not worker_path.exists(); worker_path.write_text(worker, encoding='utf-8')
prepare = (b / 'prepare-f03-minimal-app-input-r5.py').read_text('utf-8')
prepare = prepare.replace('f03-minimal-app-input-r5', 'f03-fixed-app-input-r1').replace(old_label, label).replace('f03-protected-build-r2/result.json', 'f03-protected-build-r3/result.json')
prepare = prepare.replace('no_SDK_no_DB_no_gameplay=True', 'no_cloud_SDK=True,no_new_PG_daemon=True,no_gameplay=True,uses_owned_isolated_schema=True')
prepare_path = b / 'prepare-f03-fixed-app-input-r1.py'; assert not prepare_path.exists(); prepare_path.write_text(prepare, encoding='utf-8')
runner = (b / 'run-f03-minimal-app-cloud-r5.py').read_text('utf-8')
runner = runner.replace('f03-minimal-app-cloud-r5', 'f03-fixed-app-cloud-r1').replace('f03-minimal-app-input-r5', 'f03-fixed-app-input-r1').replace('f03-minimal-app-worker-r5.py', 'f03-fixed-app-worker-r1.py').replace(old_label, label)
needle = "b=Path(__file__).parent;repo=Path.cwd();out=b/'f03-fixed-app-cloud-r1';assert not out.exists();out.mkdir()"
replacement = """b=Path(__file__).parent;repo=Path.cwd();out=b/'f03-fixed-app-cloud-r1';assert not out.exists()
ordinary=json.loads((b/'f03-fixed-ordinary-r1/result.json').read_bytes());probes=json.loads((b/'f03-fixed-probes-r1/result.json').read_bytes())
assert ordinary['ok'] and ordinary['own_job_closed'] and ordinary['own_PG_stopped']
assert probes['public_surface_equal'] and probes['snapshot_canonical_results_equal']
out.mkdir()"""
assert needle in runner; runner = runner.replace(needle, replacement)
runner_path = b / 'run-f03-fixed-app-cloud-r1.py'; assert not runner_path.exists(); runner_path.write_text(runner, encoding='utf-8')
for path in [prepare_path, runner_path]: compile(path.read_text('utf-8'), str(path), 'exec')
print('Prepared new-source cold-start worker and guarded transport only; no cloud operation performed.')
