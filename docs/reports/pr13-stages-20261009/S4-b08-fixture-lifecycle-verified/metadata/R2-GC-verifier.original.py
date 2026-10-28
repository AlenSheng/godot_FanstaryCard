
import decimal,re
BOOT_R2=B/'evidence/tuning-current-equivalence-bootstrap-r2-20261011'
DERIVED=B/'evidence/tuning-current-equivalence-r2-terminal-proof-20261011'
SERVICE=UNIT+'.service'
EXPECTED_INVOCATION='95cbc362c8634a9aa37734f7378b6ad3'
EXPECTED_BOOT='34971476-2b35-423f-a8de-c83b08346ffe'
EXPECTED_BOOT_HEX='349714762b35423fa8dec83b08346ffe'
EXPECTED_RUNNER_PID=317623
SUCCESS_TIMESTAMP='1791689977453996'
SUCCESS_MESSAGE_ID='7ad2d189f7e94e70a38c781354912448'
FINAL_RUNNER_TIMESTAMPS=('1791689977435794','1791689977437144',
                         '1791689977438421','1791689977439144')
UPLOADED_HASHES={
 'runner.py':'9aa5f6cebf59bf2d8ab354eab12be9b0cf3cb5e2a131f8b17b8026742f688720',
 'equivalence.py':'65764b8640c1795a325274ecac97c541b9e97c3dd35a63cb34fd8bcfeca4b1a5',
 'plan.json':'99f66a2412c734a788655503854a38e9b4af4fd5e6c4b3cf34d921c28770d6fd',
 'restoration-proof.json':'3f6eb8947f6dc06f3dae63169ca59208c12bae6a484fe4d65fc2bec1527d8906',
 'lease-wrapper.py':'89a7dcd3af18763c5597b1e93fdac2b74780b104287c18456bba5005c435fca2'}

def canonical(v):return (json.dumps(v,sort_keys=True,indent=2,ensure_ascii=False)+'\n').encode('utf-8')

def gc_current_state():
 raw=command(['systemctl','show',UNIT,'--property=Id,LoadState,MainPID,ActiveState,ExecMainStatus,InvocationID'])
 state=dict(x.split('=',1) for x in raw.decode('utf-8').splitlines() if '=' in x)
 require(state=={'Id':SERVICE,'LoadState':'not-found','MainPID':'0','ActiveState':'inactive',
                 'ExecMainStatus':'0','InvocationID':''},'Exact GC not-found/inactive/0/0/empty-invocation state required')
 return state

def gc_no_owned_containers():
 for line in command(['sudo','-n','docker','ps','-a','--no-trunc','--format','{{json .}}']).decode('utf-8').splitlines():
  item=json.loads(line)
  require(not any(n==UNIT or n.startswith(UNIT+'-') for n in item.get('Names','').split(','))
   and not any(x.startswith('codex.owner='+UNIT) for x in item.get('Labels','').split(',')),
   'Owned R2 native container still exists; GC authority cannot permit backup')

def gc_original_anchor(manifest,path):
 rows=[x for x in manifest['files'] if x['source']==str(path)]
 require(len(rows)==1,'Original terminal metadata must be a unique frozen manifest member')
 row=rows[0];s=ordinary(path);raw=path.read_bytes()
 require(s.st_size==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],
         'Original terminal metadata changed from the immutable 697-member manifest')
 return raw,json.loads(raw)

def gc_related(row):
 return any(row.get(key)==SERVICE for key in ('UNIT','_SYSTEMD_UNIT','OBJECT_SYSTEMD_UNIT','COREDUMP_UNIT'))

def gc_invocations(row):
 values=[]
 if row.get('UNIT')==SERVICE and row.get('INVOCATION_ID'):values.append(row['INVOCATION_ID'])
 if row.get('_SYSTEMD_UNIT')==SERVICE and row.get('_SYSTEMD_INVOCATION_ID'):values.append(row['_SYSTEMD_INVOCATION_ID'])
 if row.get('OBJECT_SYSTEMD_UNIT')==SERVICE and row.get('OBJECT_SYSTEMD_INVOCATION_ID'):values.append(row['OBJECT_SYSTEMD_INVOCATION_ID'])
 return values

def gc_manager_failure(row):
 # Native negative-control output is deliberately excluded: only PID 1 records
 # targeting this exact service may constitute systemd terminal failure.
 if row.get('_PID')!='1' or row.get('UNIT')!=SERVICE:return False
 for key in ('RESULT','SERVICE_RESULT'):
  if key in row and row[key] not in ('success','done'):return True
 if 'JOB_RESULT' in row and row['JOB_RESULT']!='done':return True
 if 'EXIT_STATUS' in row and str(row['EXIT_STATUS'])!='0':return True
 text=row.get('MESSAGE','')
 return isinstance(text,str) and re.search(
  r'\b(?:failed|failure|timed out|watchdog|killed|oom|core dump|start request repeated|main process exited|control process exited)\b',
  text,re.IGNORECASE) is not None

def gc_terminal_proof():
 require(sys.platform.startswith('linux') and B.resolve(strict=True)==B,'Fixed Linux acceptance host required')
 current=gc_current_state();gc_no_owned_containers()
 boot_path=Path('/proc/sys/kernel/random/boot_id');boot=boot_path.read_text().strip()
 require(boot==EXPECTED_BOOT and boot.replace('-','')==EXPECTED_BOOT_HEX,'Actual current boot differs from exact successful R2 boot')
 manifest_path=E/'delivery-manifest.json';ordinary(manifest_path);manifest_raw=manifest_path.read_bytes()
 require(hashlib.sha256(manifest_raw).hexdigest()==EXPECTED,'Original immutable R2 manifest SHA changed')
 manifest=json.loads(manifest_raw)
 require(manifest['attempt']==A and len(manifest['files'])==697
  and manifest['total_unique_native_encounters']==432,'Actual frozen R2 limited-result manifest required')
 started_raw,started=gc_original_anchor(manifest,E/'run-started.json')
 inputs_raw,inputs=gc_original_anchor(manifest,E/'inputs.json')
 result_raw,result=gc_original_anchor(manifest,E/'run-result.json')
 require(started['owner']==UNIT and started['runner_pid']==EXPECTED_RUNNER_PID and started['boot_id']==boot
  and started['inputs_sha256']==hashlib.sha256(inputs_raw).hexdigest()==manifest['inputs_sha256']
  and inputs['attempt']==A and inputs['systemd_unit']==UNIT,'Frozen actual R2 run-started PID/boot/owner/input binding differs')
 require(result['ok'] is True and result['attempt']==A and result['families_completed']==36
  and result['total_unique_native_encounters']==432 and result['reused_R1_native_encounters']==12
  and result['new_native_encounters']==420 and result['old_encounters']==result['current_encounters']==216
  and result['source_and_runtime_unchanged'] is True and result['numeric_tolerance_used'] is False
  and result['old_216000_relabelled'] is False and result['main_acceptance_granted'] is False,
  'Frozen successful limited 432-encounter result is necessary but not independent terminal authority')
 require(inputs['old_source_sha']==manifest['old_source_sha']=='3a984bc64f5346b7f1d134926deec54be928a060'
  and inputs['current_native_source_sha']==manifest['current_native_source_sha']=='581cd9f74962dd61424e77c529b1259afbb39fe7'
  and inputs['current_release_source_sha']==manifest['current_release_source_sha']=='18ae9d4e949cbdb4882b6469aff016f6568fb0fd',
  'Exact original/current native/release source anchors changed')
 dispatch_path=BOOT_R2/'lease-dispatch.json';intent_path=BOOT_R2/'lease-dispatch-intent.json'
 ordinary(dispatch_path);dispatch_raw=dispatch_path.read_bytes();dispatch=json.loads(dispatch_raw)
 ordinary(intent_path);intent_raw=intent_path.read_bytes();intent=json.loads(intent_raw)
 expected_stderr='Running as unit: '+SERVICE+'; invocation ID: '+EXPECTED_INVOCATION+'\n'
 require(dispatch['ok'] is True and dispatch['unit']==UNIT and dispatch['lease_dispatched'] is True
  and dispatch['exit_code']==0 and dispatch['no_retry'] is True and dispatch['stdout']==''
  and dispatch['stderr']==expected_stderr and dispatch['uploaded_hashes']==UPLOADED_HASHES,
  'Actual original successful one-shot lease dispatch/stderr invocation binding differs')
 for name,value in UPLOADED_HASHES.items():
  source=BOOT_R2/name;ordinary(source);require(sha(source)==value,'Original BOOT R2 uploaded tool changed')
 require(intent['unit']==UNIT and intent['no_retry'] is True
  and intent['wrapper_sha256']==UPLOADED_HASHES['lease-wrapper.py'],'Actual original dispatch intent/lease wrapper anchor differs')
 start_us=int(decimal.Decimal(str(started['at']))*1000000)
 intent_us=int(decimal.Decimal(str(intent['at']))*1000000)
 require(0<intent_us<=start_us<int(SUCCESS_TIMESTAMP),'Original one-shot intent/run/success timestamps are not ordered')
 journal_raw=command(['journalctl','--unit='+SERVICE,'--boot='+EXPECTED_BOOT_HEX,'--no-pager','--output=json','--all'])
 require(0<len(journal_raw)<=64*1024**2,'Complete current-boot unit journal is missing or exceeds its metadata bound')
 rows=[json.loads(line) for line in journal_raw.decode('utf-8').splitlines() if line]
 related=[x for x in rows if gc_related(x)]
 require(related and all(x.get('_BOOT_ID')==EXPECTED_BOOT_HEX and str(x.get('__REALTIME_TIMESTAMP','')).isdigit() for x in related),
  'Complete exact-unit journal lacks boot/timestamp bindings')
 require(all(all(value==EXPECTED_INVOCATION for value in gc_invocations(x)) for x in related),
  'Different exact-unit invocation exists in the current boot; preserve originals without retry')
 require(not any(gc_manager_failure(x) for x in related),'A PID 1 failed-manager record exists for the exact R2 unit')
 success=[x for x in related if x.get('_PID')=='1' and x.get('UNIT')==SERVICE
  and x.get('INVOCATION_ID')==EXPECTED_INVOCATION and x.get('MESSAGE_ID')==SUCCESS_MESSAGE_ID
  and x.get('MESSAGE')==SERVICE+': Deactivated successfully.' and x.get('__REALTIME_TIMESTAMP')==SUCCESS_TIMESTAMP]
 require(len(success)==1,'Unique actual PID 1 exact successful-deactivation journal record required')
 require(not any(x.get('_PID')=='1' and x.get('UNIT')==SERVICE and x.get('MESSAGE_ID')==SUCCESS_MESSAGE_ID
  and x is not success[0] for x in related),'Another exact-unit successful-deactivation record exists')
 final=[]
 for stamp in FINAL_RUNNER_TIMESTAMPS:
  found=[x for x in related if x.get('_PID')==str(EXPECTED_RUNNER_PID)
   and x.get('_SYSTEMD_UNIT')==SERVICE and x.get('_SYSTEMD_INVOCATION_ID')==EXPECTED_INVOCATION
   and x.get('__REALTIME_TIMESTAMP')==stamp]
  require(len(found)==1 and start_us<=int(stamp)<int(SUCCESS_TIMESTAMP),'Original final runner PID/boot/invocation journal binding missing')
  final.append({key:found[0][key] for key in ('_PID','_SYSTEMD_UNIT','_SYSTEMD_INVOCATION_ID','_BOOT_ID','__REALTIME_TIMESTAMP')})
 for row in related:
  if int(row['__REALTIME_TIMESTAMP'])<=int(SUCCESS_TIMESTAMP):continue
  # The only later records permitted are PID 1 resource-consumption records of
  # this same invocation. New runs, unbound manager activity and late native
  # output must never be hidden by a current not-found/zero state.
  require(row.get('_PID')=='1' and row.get('UNIT')==SERVICE and row.get('INVOCATION_ID')==EXPECTED_INVOCATION
   and row.get('MESSAGE_ID')=='ae8f7b866b0347b9af31fe1c80b127c0',
   'Later exact-unit journal activity is not the original same-invocation resource-consumption record')
 projection=[]
 keys=('__REALTIME_TIMESTAMP','__CURSOR','_BOOT_ID','_PID','UNIT','_SYSTEMD_UNIT','INVOCATION_ID',
       '_SYSTEMD_INVOCATION_ID','OBJECT_SYSTEMD_UNIT','OBJECT_SYSTEMD_INVOCATION_ID','MESSAGE_ID',
       'RESULT','SERVICE_RESULT','JOB_RESULT','EXIT_STATUS')
 for row in related:
  item={key:row[key] for key in keys if key in row}
  item['MESSAGE_JSON_sha256']=hashlib.sha256(canonical(row.get('MESSAGE'))).hexdigest()
  if row.get('_PID')=='1' and row.get('UNIT')==SERVICE:item['MESSAGE']=row.get('MESSAGE')
  projection.append(item)
 projection.sort(key=lambda x:(int(x['__REALTIME_TIMESTAMP']),x.get('__CURSOR','')))
 journal_projection=canonical(projection)
 require(gc_current_state()==current and boot_path.read_text().strip()==boot,'Actual terminal state/boot changed during independent journal verification')
 gc_no_owned_containers()
 proof={'ok':True,'kind':'pr13-exact-successful-GC-terminal-proof','attempt':A,'unit':UNIT,'systemd_service':SERVICE,
  'mode':'garbage_collected_after_exact_success_journal','terminal_authority':'exact-systemd-manager-journal',
  'MainPID':0,'ExecMainStatus':0,'ActiveState':'inactive','actual_current_LoadState':'not-found',
  'current_state_observed':current,'invocation_ID':EXPECTED_INVOCATION,'boot_id':boot,'boot_id_hex':EXPECTED_BOOT_HEX,
  'runner_pid':EXPECTED_RUNNER_PID,'success_message_id':SUCCESS_MESSAGE_ID,
  'successful_PID1_journal':success[0],'wrapper_final_binding_rows':final,
  'lease_dispatch':{'source':str(dispatch_path),'raw_sha256':hashlib.sha256(dispatch_raw).hexdigest(),
    'parsed_stderr_invocation_id':EXPECTED_INVOCATION,'stderr_sha256':hashlib.sha256(dispatch['stderr'].encode()).hexdigest()},
  'lease_dispatch_intent':{'source':str(intent_path),'raw_sha256':hashlib.sha256(intent_raw).hexdigest(),'at':intent['at'],
    'wrapper_sha256':intent['wrapper_sha256']},
  'run_started':{'source':str(E/'run-started.json'),'raw_sha256':hashlib.sha256(started_raw).hexdigest(),
    'owner':started['owner'],'runner_pid':started['runner_pid'],'boot_id':started['boot_id'],
    'inputs_sha256':started['inputs_sha256'],'at':started['at']},
  'original_inputs_sha256':hashlib.sha256(inputs_raw).hexdigest(),'original_run_result_sha256':hashlib.sha256(result_raw).hexdigest(),
  'manifest_sha256':EXPECTED,'original_manifest_members':697,'limited_unique_native_encounters':432,
  'old_source_sha':manifest['old_source_sha'],'current_native_source_sha':manifest['current_native_source_sha'],
  'current_release_source_sha':manifest['current_release_source_sha'],'bootstrap_uploaded_hashes':UPLOADED_HASHES,
  'unit_journal_projection_sha256':hashlib.sha256(journal_projection).hexdigest(),'unit_journal_related_rows':len(related),
  'complete_current_boot_unit_journal_read':True,'no_later_different_invocation':True,'no_other_current_boot_invocation':True,
  'no_failed_manager_journal':True,'no_owned_native_containers':True,'fresh_actual_authorities_rechecked':True,
  'native_reexecuted':False,'original_697_manifest_changed':False,'cloud_raw_cleaned':False,
  'hold_released':False,'main_acceptance_granted':False}
 return proof,journal_projection

def gc_store_derived(proof,projection):
 require(DERIVED.parent==B/'evidence' and DERIVED not in (E,W,BOOT_R2),'Derived proof must be outside all original prefixes')
 fixed(DERIVED.parent)
 if not DERIVED.exists():DERIVED.mkdir(mode=0o700)
 require(fixed(DERIVED).is_dir(),'Derived terminal directory is linked or missing')
 require({p.name for p in DERIVED.iterdir()}<= {'terminal.json','unit-journal-projection.json'},'Unexpected derived terminal files; preserve without overwrite')
 for path,raw in ((DERIVED/'unit-journal-projection.json',projection),(DERIVED/'terminal.json',canonical(proof))):
  if path.exists():
   ordinary(path);require(path.read_bytes()==raw,'Differing prior derived terminal proof retained; no overwrite')
  else:
   require(not path.is_symlink(),'Derived metadata symlink rejected')
   with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 return hashlib.sha256(canonical(proof)).hexdigest()

def terminal():
 proof,projection=gc_terminal_proof();proof_sha=gc_store_derived(proof,projection)
 return {'systemd_unit':UNIT,'MainPID':0,'ExecMainStatus':0,'ActiveState':'inactive',
  'actual_current_LoadState':'not-found','InvocationID':'','no_owned_native_containers':True,
  'terminal_authority':'exact-systemd-manager-journal','invocation_ID':EXPECTED_INVOCATION,'boot_id':EXPECTED_BOOT,
  'terminal_proof':str(DERIVED/'terminal.json'),'terminal_proof_sha256':proof_sha}
