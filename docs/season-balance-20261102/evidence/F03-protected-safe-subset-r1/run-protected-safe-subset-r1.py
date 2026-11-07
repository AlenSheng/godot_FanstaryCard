from pathlib import Path
import datetime,gzip,hashlib,importlib.util,json,os,re,subprocess,xml.etree.ElementTree as ET
b=Path(__file__).parent; repo=Path.cwd(); out=b/'f03-protected-safe-subset-r1'
assert not out.exists();out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=json.loads((b/'f03-protected-build-r2/result.json').read_bytes());package=Path(report['output']); suites=[Path(p) for p in report['test_assemblies']]
inventory=json.loads(gzip.decompress((repo/'docs/season-balance-20261102/evidence/F03-protected-test-inventory-r1/inventory/eligibility-review.derived.json.gz').read_bytes()))
prefix=('FantasyCard.Domain.Tests.Cards.','FantasyCard.Domain.Tests.Seasons.','FantasyCard.Server.Tests.ProtobufHttp.')
rows=[r for r in inventory['groups']['no_attribute_gate'] if r['type'].startswith(prefix) and r['type'].split('.')[-1]!='CardUpgradeTests']
assert len(rows)==80
sources=[]
for t in sorted({r['type'] for r in rows}):
 p=next(p for p in (repo/'server/tests').rglob(t.split('.')[-1]+'.cs') if 'obj' not in p.parts and 'bin' not in p.parts)
 raw=subprocess.check_output(['git','show',report['source_commit']+':'+p.relative_to(repo).as_posix()]);s=raw.decode('utf-8-sig')
 assert not re.search(r'\b(?:BattleRoom|Process|Postgres|File|Directory|Environment)\b',s),p
 q=out/'source';q.mkdir(exist_ok=True);(q/p.name).write_bytes(raw)
 sources.append(dict(type=t,path=p.relative_to(repo).as_posix(),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
# These are DTO round trips/pure rules plus a localhost middleware-only app, not the game host.
for t in [r for r in rows if r['type'].endswith('ServerApiBoundaryTests')]: pass
pins={str(p):sha(p) for p in suites}
for n,h in report['assemblies'].items():
 assert sha(package/n)==h['protected_sha256']
 for s in suites:
  dep=s.parent/n
  if dep.exists():assert sha(dep)==h['protected_sha256'];pins[str(dep)]=sha(dep)
for s in suites:
 for p in s.parent.iterdir():
  if p.is_file() and p.suffix in ('.dll','.json'):pins[str(p)]=sha(p)
plan=dict(source_commit=report['source_commit'],selected_method_definitions=80,selected_types=sorted({r['type'] for r in rows}),selected_methods=rows,sources=sources,input_pins=pins,new_gameplay_starts=0,PG_started=False,coverage='Explicit protected pure-rule/DTO/middleware subset; no full-suite certificate',other_definitions_excluded=1197-80,budgets=dict(D03_used=308,D03_max=308,F01_used=300,F01_max=300,B05_used=330,B05_max=330),candidate_marker_retained=True)
(out/'plan.original.json').write_text(json.dumps(plan,indent=2)+'\n')
settings=out/'single.runsettings';settings.write_text('<RunSettings><RunConfiguration><MaxCpuCount>1</MaxCpuCount></RunConfiguration></RunSettings>')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
env={k:v for k,v in os.environ.items() if not k.startswith('FANTASYCARD_')};env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',DOTNET_CLI_UI_LANGUAGE='en')
results=[]
try:
 for suite in suites:
  types=[t for t in plan['selected_types'] if t.startswith('FantasyCard.Domain.Tests.' if 'Domain' in suite.name else 'FantasyCard.Server.Tests.')]
  filt='|'.join('FullyQualifiedName~'+t+'.' for t in types)
  target=out/suite.stem;target.mkdir()
  run=guard.guarded_run(['dotnet','vstest',str(suite),'--TestCaseFilter:'+filt,'--Settings:'+str(settings),'--Logger:trx','--ResultsDirectory:'+str(target)],env=env,timeout=180,wait_seconds=30)
  (target/'run.original.log').write_text(run.stdout+run.stderr,encoding='utf-8')
  trxs=list(target.glob('*.trx'));assert trxs,'No TRX'
  total={k:0 for k in ('total','passed','failed','notExecuted')}
  for trx in trxs:
   tree=ET.parse(trx);c=tree.find('.//{*}Counters');assert c is not None
   for k in total:total[k]+=int(c.get(k,'0'))
   actual=[x.get('testName','') for x in tree.findall('.//{*}UnitTestResult')]
   assert all(any(n.startswith(t+'.') for t in types) for n in actual),'Unexpected selected test'
  results.append(dict(assembly=suite.name,returncode=run.returncode,tests=total))
  assert run.returncode==0 and total['total']>0 and total['passed']==total['total'] and total['notExecuted']==0,results[-1]
 assert all(sha(Path(p))==h for p,h in pins.items())
 assert (package/'CANDIDATE-NOT-YET-VALIDATED.txt').is_file()
 result=dict(ok=True,scope=plan['coverage'],runs=results,selected_method_definitions=80,input_hashes_unchanged=True,new_gameplay_starts=0,PG_started=False,production_changed=False,candidate_marker_retained=True,full_suite_certificate_written=False,progress='33/35',completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
except BaseException as e:
 (out/'failure.original.json').write_text(json.dumps(dict(error=type(e).__name__,message=str(e),runs=results),indent=2)+'\n');raise
