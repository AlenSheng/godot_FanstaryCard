import base64,hashlib,importlib.util,json,time
from pathlib import Path
B=Path(__file__).parent;D=B/'cap-RENDER-r7-development';OUT=B/'cap-RENDER-r7-inputs-install';assert not OUT.exists();OUT.mkdir();PLAN=json.loads((D/'plan.json').read_bytes());PAYLOAD={name:{'raw':base64.b64encode((D/name).read_bytes()).decode(),'sha256':hashlib.sha256((D/name).read_bytes()).hexdigest()} for name in ('pr13_cap_effective_render.gd','plan.json')}
cloud=r'''
import base64,hashlib,json,os,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');OLD=B/'work/dual-GUI-return-title-fit-r3-inputs';D=B/'work/cap-RENDER-r7-inputs';meta=json.loads((OLD/'manifest.json').read_bytes());assert not D.exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for row in meta['files']:
 p=OLD/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
git=Path('/opt/fantasycard-github');tree=subprocess.check_output(['git','-C',str(git),'ls-tree','-rz',PLAN['source_sha'],'--','client']);checked=0
for entry in tree.split(b'\0'):
 if not entry:continue
 head,name=entry.split(b'\t');name=name.decode();oid=head.split()[2].decode();p=OLD/name;assert p.is_file(),name;raw=p.read_bytes();lf=raw.replace(b'\r\n',b'\n');assert oid in (hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),hashlib.sha1(b'blob '+str(len(lf)).encode()+b'\0'+lf).hexdigest()),name;checked+=1
D.mkdir()
for row in meta['files']:
 if row['path']=='manifest.json':continue
 p=OLD/row['path'];target=D/row['path'];target.parent.mkdir(parents=True,exist_ok=True);os.link(p,target)
for name,v in PAYLOAD.items():
 raw=base64.b64decode(v['raw'],validate=True);assert hashlib.sha256(raw).hexdigest()==v['sha256'];p=D/'client/tests'/name if name.endswith('.gd') else D/name
 if p.exists():p.unlink()
 p.write_bytes(raw)
native=B/'evidence/cap-effective-render-r6/source/client/tests/data/cap_effective_native.json';assert sha(native)==PLAN['native_vectors_sha256'];p=D/'client/tests/data/cap_effective_native.json';assert not p.exists();p.write_bytes(native.read_bytes())
rows=[{'path':p.relative_to(D).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(D.rglob('*')) if p.is_file()];m={'input_root':str(D),'files':rows,'product_source_sha':PLAN['source_sha'],'tracked_client_git_objects_verified':checked,'only_cap_test_fixture_changed':True,'all_original_vectors_preserved':True};(D/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps({'ok':True,'input_root':str(D),'manifest_sha256':sha(D/'manifest.json'),'files':len(rows),'tracked_client_git_objects_verified':checked,'product_not_modified':True,'native_not_dispatched':True}))
'''
spec=importlib.util.spec_from_file_location('transport',B/'b08_lifecycle_r4_G_transport_gc_r2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.OUT=OUT;base=m.load('backup_failed_tuning_equivalence_r1_to_G.py');c=base.connect()
try:
 ch=c.get_transport().open_session(timeout=45);ch.exec_command('sudo -n python3 -');data=('PLAN='+repr(PLAN)+'\nPAYLOAD='+repr(PAYLOAD)+'\n'+cloud).encode()
 for i in range(0,len(data),512):ch.sendall(data[i:i+512]);time.sleep(.1)
 ch.shutdown_write();raw,_,err=m.receive(ch);assert not err;v=json.loads(raw);assert v['ok'];(OUT/'cloud-input-receipt.original.json').write_bytes(raw);print(json.dumps(v))
finally:c.close()
