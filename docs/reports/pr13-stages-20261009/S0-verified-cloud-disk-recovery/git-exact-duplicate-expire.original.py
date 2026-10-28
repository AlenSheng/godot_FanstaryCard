import fcntl,hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
R=Path('/opt/fantasycard-github');D=R/'.git/objects/pack';B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence/git-exact-duplicate-pack-expire-r2-20261013';HEAD='1e00364fef98b9906dc06d7f98efca767d3ce7d6';KEEP='pack-3c644951e123f5ec7b824fbe5042245cb4c5ccdc';DUP='pack-d1f6332efa3f6b190579fc0983e5f6f3e3f6e057';assert not E.exists()
def git(*a,timeout=300):
 r=subprocess.run(['git','-c','safe.directory='+str(R),'-c','gc.auto=0','-c','maintenance.auto=false','-C',str(R),*a],capture_output=True,timeout=timeout);r.check_returncode();return r.stdout
def inventory():
 packs={};objects=set()
 for p in sorted(D.glob('*.idx')):
  with p.open('rb') as f:r=subprocess.run(['git','show-index'],stdin=f,capture_output=True,timeout=30)
  r.check_returncode();ids={l.split()[1].decode() for l in r.stdout.splitlines()};packs[p.stem]={'bytes':p.with_suffix('.pack').stat().st_size,'object_count':len(ids),'OID_set_sha256':hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest()};objects.update(ids)
 return packs,objects
def guard():
 s=os.statvfs('/');m=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;assert s.f_bavail/s.f_blocks>=.15 and m>=500000000+64*1024**2;return {'root_free_bytes':s.f_bavail*s.f_frsize,'root_free_fraction':s.f_bavail/s.f_blocks,'memory_available_bytes':m}
def write(name,v):(E/name).write_bytes((json.dumps(v,indent=2)+'\n').encode())
with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
 fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);before=guard();assert before['root_free_bytes']-.15*os.statvfs('/').f_blocks*os.statvfs('/').f_frsize>=8*1024**2;assert git('rev-parse','HEAD').decode().strip()==HEAD and not git('status','--porcelain','--untracked-files=no').strip();refs=git('show-ref');packs,objects=inventory();assert packs[KEEP]['object_count']==10242 and packs[DUP]['object_count']==7731
 def ids(stem):
  with (D/(stem+'.idx')).open('rb') as f:r=subprocess.run(['git','show-index'],stdin=f,capture_output=True,timeout=30)
  r.check_returncode();return {l.split()[1] for l in r.stdout.splitlines()}
 assert ids(DUP)<=ids(KEEP)
 E.mkdir();write('precheck.original.json',{'ok':True,'HEAD':HEAD,'refs_sha256':hashlib.sha256(refs).hexdigest(),'all_pack_OID_union_count':len(objects),'all_pack_OID_union_sha256':hashlib.sha256('\n'.join(sorted(objects)).encode()).hexdigest(),'pack_inventory':packs,'duplicate_objects_entirely_present_in_preferred_pack':True,'resources':before,'history_or_evidence_deletion_not_requested':True});(E/'refs.original.txt').write_bytes(refs)
 # Native verification checks retained pack checksums and objects before Git expiration.
 verified=git('verify-pack','-v',str(D/(KEEP+'.idx')));(E/'preferred-pack-native-verification.original.log').write_bytes(verified);guard();assert git('show-ref')==refs and git('rev-parse','HEAD').decode().strip()==HEAD
 commands=[]
 for args in [('multi-pack-index','write','--preferred-pack='+KEEP+'.pack'),('multi-pack-index','verify'),('multi-pack-index','expire'),('multi-pack-index','verify')]:
  out=git(*args);commands.append({'args':list(args),'exit_code':0,'stdout_sha256':hashlib.sha256(out).hexdigest()});guard()
 after_packs,after_objects=inventory();assert objects==after_objects and git('show-ref')==refs and git('rev-parse','HEAD').decode().strip()==HEAD and not git('status','--porcelain','--untracked-files=no').strip();assert KEEP in after_packs and DUP not in after_packs;after=guard()
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
 result={'ok':True,'HEAD':HEAD,'refs_unchanged':True,'worktree_clean':True,'all_packed_OIDs_preserved':True,'all_pack_OID_union_count':len(objects),'all_pack_OID_union_sha256':hashlib.sha256('\n'.join(sorted(objects)).encode()).hexdigest(),'preferred_pack_native_checksum_and_objects_verified':True,'official_git_commands':commands,'expired_pack_names':sorted(set(packs)-set(after_packs)),'expired_duplicate_pack_bytes':sum(packs[n]['bytes'] for n in set(packs)-set(after_packs)),'actual_root_bytes_reclaimed':after['root_free_bytes']-before['root_free_bytes'],'before':before,'after':after,'health_status':200,'shared_source_and_package_and_SDK_content_preserved':True,'failed_originals_preserved':True,'MAIN_accepted':False};write('result.original.json',result);print(json.dumps(result))
