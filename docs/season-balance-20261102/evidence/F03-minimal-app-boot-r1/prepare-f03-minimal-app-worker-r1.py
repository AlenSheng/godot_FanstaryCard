from pathlib import Path

b=Path(__file__).parent;source=(b/'f03-minimal-image-worker-r1.py').read_text('utf-8')
source=source.replace('season-balance-20261107-f03-minimal-image-r1','season-balance-20261107-f03-minimal-app-r1').replace('fc-f03-minimal-','fc-f03-app-').replace("new_tag='fantasycard-f03-minimal:candidate-r1'","new_tag='fantasycard-f03-minimal:app-candidate-r1'")
source=source.replace('created=[];new_image=None;','created=[];schema=None;private_env=None;new_image=None;')
anchor="    after=production_state();assert before==after and not breach.is_set();guard()"
probe=(b/'f03-minimal-app-http-probe-r1.py').read_text('utf-8')
block='''    import re,secrets,uuid
    pg='803968e390014540be88f60b9ac43203946d0145bf886fc61d9d9d4d04bc3b1a'
    pginfo=inspect(pg);assert pginfo['State']['Running'] and pginfo['Config']['Labels']['com.fantasycard.task']=='season-balance-20261102-a03-storage-r1'
    schema='fc_f03_minapp_'+uuid.uuid4().hex;assert re.fullmatch('fc_f03_minapp_[a-f0-9]{32}',schema)
    def psql(sql):return run(['docker','exec',pg,'psql','-U','season_stage','-d','season_stage','-XqAt','-v','ON_ERROR_STOP=1','-c',sql]).decode().strip()
    assert psql('SELECT current_user,current_database()')=='season_stage|season_stage'
    assert psql("SELECT count(*) FROM pg_namespace WHERE nspname='"+schema+"'")=='0'
    psql('CREATE SCHEMA '+schema)
    (public/'owned-schema.original.json').write_text(json.dumps(dict(schema=schema,created_for_this_task=True,production_database_used=False))+'\\n')
    password=json.loads(Path('/home/ubuntu/season-balance-20261102-a03-storage-r1/test-connection.private.json').read_text())['password']
    assert '\\n' not in password and '\\r' not in password
    admin=secrets.token_hex(32);port=19073
    dsn='Host=127.0.0.1;Port=5432;Database=season_stage;Username=season_stage;Password="'+password.replace('"','""')+'";Search Path='+schema+';Maximum Pool Size=8;Timeout=10;CommandTimeout=30;Application Name=fc-f03-minapp-r1'
    private_env=root/'runtime.private.env'
    private_env.write_text('ASPNETCORE_ENVIRONMENT=Production\\nASPNETCORE_URLS=http://127.0.0.1:'+str(port)+'\\nDOTNET_EnableDiagnostics=0\\nIdentity__EnableLocalAuth=true\\nIdentity__AllowManagedLocalAuth=false\\nAdmin__ApiKey='+admin+'\\nConnectionStrings__Postgres='+dsn+'\\n')
    private_env.chmod(0o600)
    control=root/'http-control.private.json';control.write_text(json.dumps(dict(admin_key=admin,port=port)));control.chmod(0o600)
    app=run(['docker','run','-d','--name','fc-f03-app-server-r1','--label','com.fantasycard.task='+label,'--network','container:'+pg,
        '--user','1654:1654','--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--cap-drop','ALL','--security-opt','no-new-privileges:true',
        '--cpus','1','--memory','512m','--memory-swap','512m','--pids-limit','192','--log-opt','max-size=5m','--log-opt','max-file=1',
        '--env-file',str(private_env),new_image]).decode().strip();created.append(app)
    probe=root/'http-probe.py';probe.write_text(__PROBE_SOURCE__)
    command=['nsenter','--target',str(pginfo['State']['Pid']),'--net','--','python3','-B',str(probe),str(root)]
    diagnostic=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    (public/'http-driver.stdout.original.log').write_bytes(diagnostic.stdout)
    clean_error=diagnostic.stderr.decode(errors='replace').replace(password,'[REDACTED]').replace(admin,'[REDACTED]')
    (public/'http-driver.stderr.original.log').write_text(clean_error)
    logs=run(['docker','logs',app]).decode(errors='replace');(root/'application.private.log').write_text(logs);(root/'application.private.log').chmod(0o600)
    assert diagnostic.returncode==0,'Isolated HTTP probe failed; inspect redacted public driver result'
    assert inspect(app)['State']['Running']
    facts=json.loads(psql('SET search_path TO '+schema+"; SELECT json_build_object('migration_count',(SELECT count(*) FROM schema_migrations),'migration_max',(SELECT max(version) FROM schema_migrations),'players',(SELECT count(*) FROM players),'matches',(SELECT count(*) FROM matches));"))
    assert facts['migration_count']==52 and facts['migration_max']==55 and facts['players']==facts['matches']==0
    (public/'runtime-db-facts.original.json').write_text(json.dumps(facts,indent=2)+'\\n')
    actual_hashes=run(['docker','exec',app,'sha256sum',*['/app/'+name for name in sorted(files)]]).decode()
    assert {line.split('  ',1)[1].removeprefix('/app/'):line.split('  ',1)[0] for line in actual_hashes.splitlines()}==files
    (public/'running-app-file-hashes.original.log').write_text(actual_hashes)
'''.replace('__PROBE_SOURCE__',repr(probe))
assert anchor in source;source=source.replace(anchor,block+anchor)
source=source.replace('no_game_program_started=True,no_DB_access=True,new_gameplay_starts=0','game_program_started_in_owned_isolation=True,only_owned_test_schema_accessed=True,http_boundaries_verified=True,new_gameplay_starts=0')
anchor='    image_removed=False'
cleanup='''    schema_removed=False
    if schema is not None:
        assert re.fullmatch('fc_f03_minapp_[a-f0-9]{32}',schema)
        psql('DROP SCHEMA '+schema+' CASCADE')
        assert psql("SELECT count(*) FROM pg_namespace WHERE nspname='"+schema+"'")=='0';schema_removed=True
    if private_env is not None and private_env.exists():private_env.unlink()
    if (root/'http-control.private.json').exists():(root/'http-control.private.json').unlink()
'''
assert anchor in source;source=source.replace(anchor,cleanup+anchor)
source=source.replace('owned_candidate_image_removed=image_removed,production_state_unchanged=before==after','owned_candidate_image_removed=image_removed,owned_schema_removed=schema_removed,private_env_removed=private_env is None or not private_env.exists(),production_state_unchanged=before==after')
(b/'f03-minimal-app-worker-r1.py').write_text(source,encoding='utf-8');compile(source,str(b/'f03-minimal-app-worker-r1.py'),'exec')
prepare=(b/'prepare-f03-minimal-image-input-r1.py').read_text('utf-8').replace('f03-minimal-image-input-r1','f03-minimal-app-input-r1').replace('season-balance-20261107-f03-minimal-image-r1','season-balance-20261107-f03-minimal-app-r1')
(b/'prepare-f03-minimal-app-input-r1.py').write_text(prepare,encoding='utf-8')
runner=(b/'run-f03-minimal-image-cloud-r1.py').read_text('utf-8').replace('f03-minimal-image','f03-minimal-app')
(b/'run-f03-minimal-app-cloud-r1.py').write_text(runner,encoding='utf-8');compile(runner,str(b/'run-f03-minimal-app-cloud-r1.py'),'exec');print(str(b/'f03-minimal-app-worker-r1.py'))
