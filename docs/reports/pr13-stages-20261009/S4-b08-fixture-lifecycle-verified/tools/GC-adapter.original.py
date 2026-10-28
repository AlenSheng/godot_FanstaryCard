"""Exact successful R4 transient service GC proof, based on actual original journal."""
import hashlib,json,re
from pathlib import Path
SERVICE='pr13-cap-b08-fixture-lifecycle-r4-20261011.service'
INVOCATION='588f15a019ef49e4a7f603f79f7c2387';BOOT='349714762b35423fa8dec83b08346ffe';PID=378674
START='1791692898747665';END='1791693622293035';CONSUMED='1791693622293375'
STARTED_SHA='cf10d5453acf5c6741569235d6b5773f183ba0306247bed799768561891743e5'
INPUT_SHA='6cd9e024319fb9631aba003743a7809df80028b7465725297dd463319eae4f3e'
PREREG_SHA='0eb767e7261fa0f0025cfbee2820575a797cad376547ec9609ab385e23db12c8'
def canonical(v):return (json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
def derive(m,context):
 require=m.require;state=m.unit_state(m.OWNER)
 require(state.get('complete_observation') is True and state.get('LoadState')=='not-found' and state.get('Id')==SERVICE and state.get('MainPID')==0 and state.get('ExecMainStatus')==0 and state.get('ActiveState')=='inactive' and state.get('SubState')=='dead' and state.get('InvocationID')=='','Exact current GC state required')
 require(m.current_boot()==BOOT and context['boot_id']==BOOT and context['invocation_id']==INVOCATION and context['startup_sha256']==STARTED_SHA,'Actual original execution boot/invocation/startup bytes required')
 require(m.sha(m.E/'run-started.json')==STARTED_SHA and m.sha(m.E/'inputs.json')==INPUT_SHA and m.sha(m.E/'preregistration.json')==PREREG_SHA,'Exact original startup/input/preregistration changed')
 started=m.read(m.E/'run-started.json');require(started['MainPID']==PID and started['invocation_id']==INVOCATION and started['inputs_sha256']==INPUT_SHA and started['preregistration_sha256']==PREREG_SHA,'Actual original live PID and input binding required')
 dispatch=m.read(m.BASE/'evidence/b08-fixture-lifecycle-bootstrap-r4-20261011/lease-dispatch.json');require(dispatch['ok'] is True and dispatch['unit']==m.OWNER and dispatch['no_retry'] is True and dispatch['stderr']=='Running as unit: '+SERVICE+'; invocation ID: '+INVOCATION+'\n','Exact one-shot dispatch invocation differs')
 result=m.read(m.E/'run-result.json');require(result['ok'] is True and result['run_started_sha256']==STARTED_SHA and len(result['cases'])==4 and all(c['ok'] and c['exit_code']==0 and c['native_clean'] and c['shutdown_resources_clean'] and c['owned_container_removed'] and not c['oom_killed'] for c in result['cases']),'Four original successful native cases required')
 raw=m.cmd(['journalctl','--unit='+SERVICE,'--boot='+BOOT,'--no-pager','--output=json','--all'],timeout=30).stdout;require(0<len(raw)<=32*1024**2,'Complete exact current-boot service journal bounded')
 rows=[json.loads(line) for line in raw.splitlines() if line]
 related=[r for r in rows if any(r.get(k)==SERVICE for k in ('UNIT','_SYSTEMD_UNIT','OBJECT_SYSTEMD_UNIT','COREDUMP_UNIT'))]
 require(related and all(r.get('_BOOT_ID')==BOOT and str(r.get('__REALTIME_TIMESTAMP','')).isdigit() for r in related),'Every related actual journal row must bind exact boot/time')
 for r in related:
  for uk,ik in (('UNIT','INVOCATION_ID'),('_SYSTEMD_UNIT','_SYSTEMD_INVOCATION_ID'),('OBJECT_SYSTEMD_UNIT','OBJECT_SYSTEMD_INVOCATION_ID')):
   if r.get(uk)==SERVICE and r.get(ik):require(r[ik]==INVOCATION,'Another exact-service invocation exists')
 managers=[r for r in related if r.get('_PID')=='1' and r.get('UNIT')==SERVICE]
 expected=[(START,'39f53479d3a045ac8e11786248231fbf'),(END,'7ad2d189f7e94e70a38c781354912448'),(CONSUMED,'ae8f7b866b0347b9af31fe1c80b127c0')]
 require(len(managers)==3 and [(r['__REALTIME_TIMESTAMP'],r.get('MESSAGE_ID')) for r in managers]==expected and all(r.get('INVOCATION_ID')==INVOCATION for r in managers),'Actual exact Started/success/resource lifecycle required; no hypothetical Starting row')
 require(managers[0]['MESSAGE']=='Started '+SERVICE+' - /usr/bin/python3 /home/ubuntu/pr13-acceptance-20261009/evidence/b08-fixture-lifecycle-bootstrap-r4-20261011/lease-wrapper.py.' and managers[1]['MESSAGE']==SERVICE+': Deactivated successfully.','Exact original start and successful-deactivation messages required')
 require(not any(re.search(r'\b(failed|failure|killed|oom|timeout)\b',r.get('MESSAGE',''),re.I) for r in managers),'Any failed manager event rejects GC success')
 require(int(START)<=int(started['at']*1000000)<int(END),'Original live startup must fall inside actual invocation')
 final=[r for r in related if r.get('_PID')==str(PID) and r.get('_SYSTEMD_UNIT')==SERVICE and r.get('_SYSTEMD_INVOCATION_ID')==INVOCATION and int(r['__REALTIME_TIMESTAMP'])<int(END)]
 require(final,'Original runner PID/invocation output absent')
 require(all(int(r['__REALTIME_TIMESTAMP'])<=int(END) or r is managers[2] for r in related),'Later unrelated/invocation/native activity rejected')
 m.no_owned_containers(SERVICE)
 projection=[{k:r[k] for k in ('__REALTIME_TIMESTAMP','_PID','_BOOT_ID','UNIT','_SYSTEMD_UNIT','INVOCATION_ID','_SYSTEMD_INVOCATION_ID','MESSAGE_ID') if k in r} | {'MESSAGE_sha256':hashlib.sha256(canonical(r.get('MESSAGE'))).hexdigest()} for r in related]
 proof={'authority':'exact-systemd-manager-journal','unit':SERVICE,'mode':'garbage-collected-after-exact-success','boot_id':BOOT,'invocation_id':INVOCATION,'runner_pid':PID,'startup_sha256':STARTED_SHA,'input_sha256':INPUT_SHA,'preregistration_sha256':PREREG_SHA,'run_result_sha256':m.sha(m.E/'run-result.json'),'manager_rows':managers,'complete_unit_journal_projection_sha256':hashlib.sha256(canonical(projection)).hexdigest(),'complete_related_rows':len(related),'no_later_different_invocation':True,'no_failed_manager_journal':True,'no_owned_native_containers':True,'current_state':state,'native_reexecuted':False}
 require(m.unit_state(m.OWNER)==state and m.current_boot()==BOOT,'Actual terminal state changed during journal verification')
 return proof
def install(m):
 previous=m.exact_terminal
 def exact(unit,context):
  if unit==m.OWNER:return derive(m,context)
  return previous(unit,context)
 m.exact_terminal=exact
