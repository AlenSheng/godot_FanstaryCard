from pathlib import Path
import json, shlex

b=Path(__file__).parent; out=b/'runtime-r116'
d=json.loads((out/'delta-manifest.json').read_bytes());m=json.loads((out/'manifest.json').read_bytes())
d.update(staging_method='tmpfs_byte_verified_full_copy',staging_allocation_bytes=len(m['files'])*4096,tmpfs_allocation_bytes=64*1024**2)
(out/'delta-manifest.json').write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8')
source=(b/'runtime-r115/start-delta-runtime.py').read_text('utf-8').replace('runtime-r115','runtime-r116')
begin=source.index("command=['-c',");end=source.index('\nargs=',begin)
command=['dotnet','/workspace/bin/FantasyCard.Server.Tests.dll','-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-trx','/results/group-a.trx','-xml','/results/group-a.xml','-method','FantasyCard.Server.Tests.Persistence.PostgresConfigVersionRoomTests.*']
source=source[:begin]+'command='+repr(['-c',shlex.join(command)+'\n'])+source[end:]
p=out/'start-delta-runtime.py';assert not p.exists();compile(source,str(p),'exec');p.write_text(source,encoding='utf-8')
for old,new in [('setup-asset-runtime115-file-transfer.py','setup-asset-runtime116-file-transfer.py'),('transfer-r115-stream-sftp.py','transfer-r116-stream-sftp.py'),('verify-r115-complete-stream.py','verify-r116-complete-stream.py'),('start-r115-from-verified-file.py','start-r116-from-verified-file.py'),('observe-asset-composite-r115.py','observe-asset-composite-r116.py')]:
 p=b/new;assert not p.exists();s=(b/old).read_text('utf-8').replace('runtime-r115','runtime-r116');compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
s=(b/'collect-asset-grouped-r115.py').read_text('utf-8').replace('runtime-r115','runtime-r116')
for before,after in [("for key in ['a','b','c']:","for key in ['a']:"),('len(group_counts)==3','len(group_counts)==1'),("['passed']=='114'","['passed']=='5'"),('declared_114_grouped_checks_accepted','targeted_5_checks_accepted')]:
 assert before in s;s=s.replace(before,after)
p=b/'collect-asset-targeted-r116.py';assert not p.exists();compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
(out/'declared-groups.json').write_text(json.dumps({'groups':{'a':['PostgresConfigVersionRoomTests']},'expected_counts':{'a':5},'total':5,'reuse_r115_passed':116,'prior_r115_total':121,'prior_r115_failed':5,'no_production_changes':True,'no_temporary_PG_WAL_adjustment_for_this_small_batch':True},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'targeted':5,'existing_passed_reused':116,'union_expected':121}))
