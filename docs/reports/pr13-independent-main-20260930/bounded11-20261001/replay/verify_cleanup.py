"""Read-only verification of precisely owned receipt PIDs, PG data dirs and git."""
import collections,datetime,hashlib,json,pathlib,subprocess
B=pathlib.Path(__file__).resolve().parent
groups=[]
for group in ['b02','a05']:
    for p in sorted((B/group/'evidence').rglob('receipts.jsonl')):
        starts=set(); stops=set(); exit_codes=collections.Counter(); all_pids=set()
        for line in p.read_text().splitlines():
            x=json.loads(line); e=x['evidence']; case=x['caseId']
            if case=='process-start':starts.add(e['Id'])
            if case=='process-stop':stops.add(e['ProcessId'])
            if case=='A05-client-start':starts.add(e['Id'])
            if case=='A05-client-stop':stops.add(e['Id'])
            if case in ['ack-runner-process-stop','ack-client-process-stop']:
                stops.add(e['Id'])
            if 'process' in case or case in ['A05-client-start','A05-client-stop']:
                for key in ['Id','ProcessId','previousPid']:
                    if key in e:all_pids.add(e[key])
                if 'ExitCode' in e:exit_codes[str(e['ExitCode'])]+=1
        alive=[pid for pid in sorted(all_pids) if pathlib.Path(f'/proc/{pid}').exists()]
        assert not alive,(str(p),alive)
        assert starts<=stops,(str(p),starts-stops)
        groups.append(dict(path=str(p.relative_to(B)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),started=len(starts),stop_receipts=len(stops),owned_pid_count=len(all_pids),owned_pids_still_present=alive,observed_exit_codes=dict(exit_codes)))
pg=[]
for name in ['b02/owned-pg','b02/original-profile-pg','a05/owned-pg']:
    data=B/name
    if not data.exists():continue
    proc=subprocess.run(['pg_ctl','-D',str(data),'status'],capture_output=True,text=True)
    assert proc.returncode==3,(name,proc.stdout,proc.stderr)
    pg.append(dict(data_directory=name,argv=proc.args,exit_code=proc.returncode,output=proc.stdout.strip(),postmaster_pid_exists=(data/'postmaster.pid').exists()))
repo=pathlib.Path('/workspace/godot_FanstaryCard')
sha=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
status=subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True)
assert sha=='b39841d3f5191c11c9e51c7e6875490789aba53c' and status==''
owned_sql_log=B/'A05-DRIVER.log';sql_text=owned_sql_log.read_text()
assert 'owned_test_schemas' in sql_text and 'other_connections' in sql_text
row=dict(checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),process_receipts=groups,owned_PG=pg,original_checkout=dict(sha=sha,status=status),A05_pre_stop_query=dict(owned_test_schemas=0,other_client_connections=0,log='A05-DRIVER.log',log_sha256=hashlib.sha256(owned_sql_log.read_bytes()).hexdigest()),scope='No global process-name kill. Only precisely owned processes; PG was stopped by owning driver finally. Other workspace processes untouched.')
(B/'CLEANUP.json').write_text(json.dumps(row,indent=2)+'\n')
print(json.dumps(dict(receipt_groups=len(groups),owned_pids=sum(x['owned_pid_count'] for x in groups),remaining_owned=0,PG_stopped=len(pg),original_checkout_clean=True)))
