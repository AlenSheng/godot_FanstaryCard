"""Bounded cloud-only phase runner; no deployment or fabricated native vectors."""
import json,os,subprocess,sys,xml.etree.ElementTree as ET
from pathlib import Path
SOURCE=Path('/work');OUT=Path('/evidence');SHA=os.environ['FANTASYCARD_PR13_SOURCE_SHA']
assert sys.platform.startswith('linux') and len(SHA)==40 and OUT.is_dir() and SOURCE.is_dir()
PROJECT=SOURCE/'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'
FILTER='FullyQualifiedName~MonsterPoolLegalRouteWireTests'
dirty=('SCRIPT ERROR','Parse Error','Failed to load script','ObjectDB instances were leaked','resources still in use')
results=[]
def run(name,args,env=None,budget=300,godot=False):
 log=OUT/(name+'.log');assert not log.exists()
 with log.open('xb') as f:p=subprocess.run(args,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=budget)
 record={'phase':name,'exit_code':p.returncode,'source_sha':SHA};results.append(record)
 (OUT/'phase-progress.json').write_text(json.dumps(results,indent=2)+'\n')
 assert p.returncode==0,'Actual cloud phase failed: '+name
 if godot:assert not any(s.lower() in log.read_text(errors='replace').lower() for s in dirty),'Dirty Godot load/shutdown: '+name
def native(phase):
 env=os.environ.copy();env['FANTASYCARD_PR13_LEGAL_ROUTE_PHASE']=phase;env['FANTASYCARD_PR13_LEGAL_ROUTE_DIRECTORY']=str(OUT)
 trx=phase+'.trx';run('native-'+phase,['dotnet','test',str(PROJECT),'-c','Release','--no-build','--no-restore','--filter',FILTER,'--results-directory',str(OUT/'test-results'),'--logger','trx;LogFileName='+trx],env,budget=300)
 ns='{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}'
 counters=ET.parse(OUT/'test-results'/trx).getroot().find(ns+'ResultSummary/'+ns+'Counters').attrib
 assert all(int(counters.get(s,'0'))==0 for s in ('failed','notExecuted','error','timeout','aborted')) and int(counters['passed'])==int(counters['total'])==1
 rows=[json.loads(s) for s in (OUT/(phase+'-native-receipt.jsonl')).read_text().splitlines()];assert len(rows)==1 and rows[0]['ok'] is True and rows[0]['source_sha']==SHA and rows[0]['phase']==phase and rows[0]['fixture_rows']==9
 return rows[0]
def godot(mode,batch=None):
 name='godot-'+mode+('-'+batch if batch else '');env=os.environ.copy();env['PR13_LEGAL_ROUTE_GODOT_MODE']=mode;env['PR13_LEGAL_ROUTE_SOURCE']=SHA;env['PR13_LEGAL_ROUTE_GODOT_RESULT']=str(OUT/(name+'.json'));env['PR13_LEGAL_ROUTE_DIRECTORY']=str(OUT)
 if batch:
  env['PR13_LEGAL_ROUTE_BATCH']=batch;env['PR13_LEGAL_ROUTE_DESCRIPTORS']=str(OUT/(batch+'-descriptors.jsonl'));env['PR13_LEGAL_ROUTE_COMMANDS']=str(OUT/(batch+'-godot-commands.jsonl'))
 run(name,['godot','--headless','--audio-driver','Dummy','--path',str(SOURCE/'client'),'--script','res://tests/run_monster_pool_legal_route_vectors.gd'],env,budget=180,godot=True)
 v=json.loads((OUT/(name+'.json')).read_bytes());assert v['ok'] is True and v['source_sha']==SHA and v['mode']==mode and not v['failures']
 if batch:assert v['commands_encoded']=={'kill':9,'choose':27,'final':27}[batch]
 else:assert v['native_rows_received']==72 and v['original_native_frames_received']==189 and v['original_replay_frames_received']==45
 return v
try:
 run('build',['dotnet','build',str(PROJECT),'-c','Release','-m:1','-p:UseSharedCompilation=false','-p:RestoreIgnoreFailedSources=true','-p:NuGetAudit=false','-p:BuildInParallel=false'],budget=900)
 receipts=[native('prepare')]
 for phase in ('kill','choose','final'):godot('encode',phase);receipts.append(native(phase))
 client=godot('receive')
 assert sum(x['native_routes'] for x in receipts)==99
 commands=sum(len((OUT/(phase+'-godot-commands.jsonl')).read_text().splitlines()) for phase in ('kill','choose','final'));assert commands==63
 result={'ok':True,'source_sha':SHA,'original_Godot_commands':63,'native_routes_including_replays':99,'native_event_rows':72,'original_native_frames':189,'original_replay_frames':45,'additional_native_peer_finishing_controls':9,'native_receipts':receipts,'Godot_receive':client,'MAIN_accepted':False,'LIVE_accepted':False,'cloud_only_native_execution':True}
except Exception as e:result={'ok':False,'source_sha':SHA,'error':type(e).__name__,'detail':str(e),'partial_originals_retained':True,'phases':results,'MAIN_accepted':False,'LIVE_accepted':False}
(OUT/'inner-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
