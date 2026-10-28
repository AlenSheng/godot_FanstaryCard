import pathlib,subprocess,json,time,os,hashlib,sys,traceback
O=pathlib.Path('/home/ubuntu/pr13-normal-mixed-current-20261025-r20');P=pathlib.Path('/home/ubuntu/pr13-resource100-admission-20261025-r18/project');S=pathlib.Path('/home/ubuntu/pr13-acceptance-20261009/source/.git');mode=sys.argv[1];assert mode=='normal-mixed3';assert json.loads((O/'prepare-terminal.original.json').read_text())['ok'];J=O/'results'/mode;J.mkdir();(J/'audit-spool').mkdir();tag='pr13-normal-mixed-r20-'+mode;owner='01a152f7-f2a2-7b12-a4c5-a22b38ee9cd3';image='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520';os.nice(10)
base=['/opt/pr13-venv/bin/python3','-B',str(P/'tools/gameplay_load_test.py'),'--godot','/usr/local/bin/godot','--server-url','http://127.0.0.1:18591','--prometheus','http://127.0.0.1:18596','--client-project',str(P/'client'),'--minimum-generator-memory-bytes','500000000','--minimum-cloud-memory-bytes','500000000','--minimum-cloud-disk-percent','5','--launch-interval-seconds','1','--stop-file','/owned/'+mode+'/STOP','--output','/owned/'+mode+'/coordinator']
if mode=='normal-mixed3':args=[*base,'--smoke','--smoke-clients','10','--smoke-cycles','3','--load-profile','cyclic-gameplay','--distinct-local-client-ips','--hero-class','mixed','--strategy','baseline_all_hand','--strategy-seed','20260930','--cycle-limit-seconds','2400','--max-seconds','7500'];limit=7680;memory='1536m'
else:
 assert (O/'study-spec-binding.original.json').exists();assert (O/'results/warmup/terminal.original.json').exists();assert json.loads((O/'results/warmup/terminal.original.json').read_text())['ok']
 args=[*base,'--run','--max-groups','1','--group-size','25','--group-interval','1','--max-seconds','960','--load-profile','active-hold','--hold-seconds','720','--target-online','25','--target-active','25','--minimum-continuous-seconds','120','--minimum-coverage','0.95','--maximum-sample-gap','20','--minimum-command-rate','1','--hero-class','Guardian','--strategy','baseline_all_hand','--strategy-seed','20260955','--cycle-limit-seconds','240'];limit=1140;memory='2560m'
entry=r"""import pathlib,os,json,hashlib,subprocess
p=pathlib.Path('/usr/local/bin/godot').resolve();assert hashlib.sha256(p.read_bytes()).hexdigest()=='8d106cbe6144c2dc7e881d61d2429c1a8a76e6b22ef48bd5e48dcf934953f71e';root=pathlib.Path(os.environ['PR13_PROJECT']);assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD']).decode().strip()=='2eecaf49c1b081bcba5fb5d95d2c620df7e1f9d9';args=json.loads(os.environ['PR13_ARGS']);pathlib.Path(os.environ['PR13_ENTRY']).write_text(json.dumps({'engine_path':str(p),'engine_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'engine_version':subprocess.check_output([str(p),'--headless','--version']).decode().strip(),'source_head':'2eecaf49c1b081bcba5fb5d95d2c620df7e1f9d9','argv':args})+chr(10));os.chdir(root);os.execv(args[0],args)
"""
labels=['--label','pr13.round=current-normal-mixed-r20','--label','pr13.owner='+owner]
common=['--network','host','--user','0:0','--read-only','--tmpfs','/tmp:rw,nosuid,size=1024m','--mount','type=bind,source='+str(P)+',target='+str(P)+',readonly','--mount','type=bind,source='+str(S)+',target='+str(S)+',readonly','--mount','type=bind,source='+str(O/'results')+',target=/owned','--mount','type=bind,source='+str(O/'collectors')+',target=/collectors,readonly','-e','TMPDIR=/tmp','-e','TEMP=/tmp','-e','TMP=/tmp','-e','GODOT_SILENCE_ROOT_WARNING=1','-e','GIT_OPTIONAL_LOCKS=0','-e','GIT_CONFIG_COUNT=1','-e','GIT_CONFIG_KEY_0=safe.directory','-e','GIT_CONFIG_VALUE_0='+str(P),'-e','XDG_CONFIG_HOME=/owned/editor-config','-e','XDG_DATA_HOME=/owned/'+mode+'/userdata','-e','XDG_CACHE_HOME=/owned/engine-cache']
cmd=['docker','run','-d','--init','--pull','never','--name',tag,*labels,*common,'--memory',memory,'--pids-limit','512','--cpu-shares','128','--log-opt','max-size=10m','--log-opt','max-file=2','-e','PR13_PROJECT='+str(P),'-e','PR13_ARGS='+json.dumps(args),'-e','PR13_ENTRY=/owned/'+mode+'/process-entry.original.json','--entrypoint','/opt/pr13-venv/bin/python3',image,'-B','-c',entry]
controls=list(json.loads((O/'source-controls.original.json').read_text()));(J/'preregistered-command.original.json').write_text(json.dumps({'docker':cmd,'driver':args,'maximum_seconds':limit,'minimum_host_memory_bytes':500000000,'minimum_disk_bytes':3000000000,'full_native_no_FPS_override':True},indent=2)+chr(10));resources=[];cid=None;guard=None;inspection=False
def resource():
 m={line.split(':',1)[0]:int(line.split(':',1)[1].split()[0])*1024 for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')};v=os.statvfs('/');r={'at_unix_ms':time.time_ns()/1000000,'monotonic_ms':time.monotonic_ns()/1000000,'memory_available_bytes':m['MemAvailable'],'root_disk_free_bytes':v.f_bavail*v.f_frsize,'root_disk_free_percent':100*v.f_bavail/v.f_blocks};resources.append(r);return r
try:
 r=resource();assert r['memory_available_bytes']>=500000000 and r['root_disk_free_bytes']>=3000000000 and r['root_disk_free_percent']>=5
 cid=subprocess.check_output(cmd).decode().strip();(J/'started.original.json').write_text(json.dumps({'container':cid,'host_controller_pid':os.getpid(),'started_at':time.time()})+chr(10));start=time.monotonic()
 while True:
  r=resource();x=json.loads(subprocess.check_output(['docker','inspect',cid]))[0];assert x['Config']['Labels']['pr13.owner']==owner
  if not x['State']['Running']:break
  if r['memory_available_bytes']<500000000:guard='cloud_memory_below500MB'
  if r['root_disk_free_bytes']<3000000000 or r['root_disk_free_percent']<5:guard='cloud_disk_below3GB'
  if time.monotonic()-start>limit:guard='owned_stage_deadline'
  if (O/'STOP-STUDY').exists():guard='peer_or_parent_stop'
  if mode=='normal-mixed3' and not inspection:
   paths=list((J/'coordinator').glob('*/launch-manifest.json'))
   if paths:
    try:manifest=json.loads(paths[0].read_text())
    except (OSError,ValueError):manifest={}
    if len(manifest.get('launches',[]))==10:
     inside='/owned/'+mode+'/coordinator/'+paths[0].parent.name+'/launch-manifest.json';out='/owned/'+mode+'/processes.original.json';r=subprocess.run(['docker','exec',cid,'/opt/pr13-venv/bin/python3','-B','/collectors/pr13_native_capture.py','processes','--manifest',inside,'--count','10','--output',out],capture_output=True,timeout=15);(J/'process-inspection.stdout.original.log').write_bytes(r.stdout);(J/'process-inspection.stderr.original.log').write_bytes(r.stderr)
     if r.returncode==0:inspection=True
     else:guard='native_OS_process_inspection_failed'
  if guard:
   (J/'STOP').write_text(guard+chr(10));deadline=time.monotonic()+60
   while time.monotonic()<deadline and json.loads(subprocess.check_output(['docker','inspect',cid]))[0]['State']['Running']:resource();time.sleep(1)
   if json.loads(subprocess.check_output(['docker','inspect',cid]))[0]['State']['Running']:subprocess.run(['docker','stop','--time','10',cid],capture_output=True,timeout=20)
   break
  time.sleep(1)
 resource();x=json.loads(subprocess.check_output(['docker','inspect',cid]))[0];logs=subprocess.run(['docker','logs',cid],capture_output=True);(J/'stdout.original.log').write_bytes(logs.stdout);(J/'stderr.original.log').write_bytes(logs.stderr);reports=list((J/'coordinator').glob('*/report.json'));original=json.loads(reports[0].read_text()) if len(reports)==1 else {};result={'original_stop_reason':original.get('stop_reason'),'original_duration_limit_reached':original.get('stop_reason')=='duration_limit','ok':x['State']['ExitCode']==0 and not x['State']['OOMKilled'] and guard is None,'container':cid,'exit':x['State']['ExitCode'],'OOMKilled':x['State']['OOMKilled'],'guard_stop':guard,'native_process_inspection':inspection if mode=='normal-mixed3' else 'NotApplicable_warmup','capacity_verdict_not_inferred_from_exit':True,'mode':mode}
except BaseException as e:result={'ok':False,'error_type':type(e).__name__,'error':str(e),'container':cid,'guard_stop':guard};(J/'error.original.log').write_text(traceback.format_exc())
(J/'resources.original.json').write_text(json.dumps(resources,indent=2)+chr(10));(J/'terminal.original.json').write_text(json.dumps(result,indent=2)+chr(10))
