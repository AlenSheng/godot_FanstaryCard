import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

root = Path('/home/ubuntu/season-balance-20261102-a03-storage-r73')
name = 'fc-season-a03-storage-20261102-r73'
pg = '803968e390014540be88f60b9ac43203946d0145bf886fc61d9d9d4d04bc3b1a'
assert subprocess.check_output(['docker','inspect','--format','{{.State.Status}}',pg],text=True).strip() == 'running'
assert subprocess.check_output(['docker','inspect','--format','{{index .Config.Labels "com.fantasycard.task"}}',pg],text=True).strip() == 'season-balance-20261102-a03-storage-r1'
assert not subprocess.check_output(['docker','ps','-aq','--filter','name=^'+name+'$'],text=True).strip()
memory = {line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()
          if len(line.split())>=2 and line.split()[1].isdigit()}
disk = shutil.disk_usage(root)
assert memory['MemAvailable'] >= 1800*1024**2
assert disk.free >= 3*1024**3+256*1024**2 and disk.free/disk.total >= .05
manifest = json.loads((root/'input-manifest.json').read_text())
assert hashlib.sha256((root/'source.tar.gz').read_bytes()).hexdigest() == manifest['archive_sha256']
work = root/'input'
work.mkdir()
with tarfile.open(root/'source.tar.gz') as source:
    members=source.getmembers()
    assert {member.name for member in members} == set(manifest['files'])
    for member in members:
        assert member.isfile() and (work/member.name).resolve().is_relative_to(work.resolve())
    source.extractall(work)
for relative,checksum in manifest['files'].items():
    assert hashlib.sha256((work/relative).read_bytes()).hexdigest() == checksum
for directory,folders,files in os.walk(work):
    os.chown(directory,1000,1000)
    for filename in files: os.chown(Path(directory)/filename,1000,1000)
credentials=json.loads(Path('/home/ubuntu/season-balance-20261102-a03-storage-r1/test-connection.private.json').read_text())
connection='Host=127.0.0.1;Port=5432;Database=season_stage;Username=season_stage;Password='+credentials['password']+';MaxPoolSize=16;Timeout=10;CommandTimeout=30'
env=root/'sdk.env'
env.write_text('FANTASYCARD_TEST_POSTGRES='+connection+'\n');env.chmod(0o600)
server_command='dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --filter "FullyQualifiedName~PostgresSeason|FullyQualifiedName~PostgresEnhancementQuoteTests|FullyQualifiedName~FantasyCard.Server.Tests.Config|FullyQualifiedName~SeasonWallet|FullyQualifiedName~PostgresDifficultyUnlockTests|FullyQualifiedName~Settlement|FullyQualifiedName~PostgresConfigVersionRoomTests|FullyQualifiedName~PostgresLifecycleRecoveryTests|FullyQualifiedName~PostgresCombatActionTests|FullyQualifiedName~TerminalCommandContextTests|FullyQualifiedName~LootPreferenceEncodingTests|FullyQualifiedName~Four_humans_enqueue_ready_and_launch_one_persisted_room|FullyQualifiedName~SeasonCrafting_binary_session_uses_all_five_routes_and_preserves_asset_identity" --logger "trx;LogFileName=bot-server.trx" --results-directory /workspace/results --verbosity minimal -m:1 -p:UseSharedCompilation=false'
domain_command='true'
image='sha256:4beef5b8919dcaa2dc924233bd069257e883cc7a061e09088a97d152d6a48510'
cache='/home/ubuntu/season-balance-20261102-a02-r1/input/.nuget/packages'
args=['docker','run','-d','--name',name,'--label','com.fantasycard.task=season-balance-20261102-a03-storage-r73',
      '--network','container:'+pg,'--memory','1200m','--memory-swap','1200m','--cpus','1','--pids-limit','256',
      '--cap-drop','ALL','--security-opt','no-new-privileges:true','--read-only',
      '--tmpfs','/tmp:rw,noexec,nosuid,size=128m,mode=1777','--user','1000:1000',
      '-v',str(work)+':/workspace','-v',cache+':/workspace/.nuget/packages','-w','/workspace/server',
      '--env-file',str(env),'-e','DOTNET_CLI_HOME=/workspace/.dotnet','-e','NUGET_PACKAGES=/workspace/.nuget/packages',
      '-e','DOTNET_CLI_TELEMETRY_OPTOUT=1','-e','DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1','-e','NUGET_XMLDOC_MODE=skip',
      image,'sh','-c',domain_command+' && '+server_command]
container=subprocess.check_output(args,text=True,timeout=15).strip()
proof={'container_id':container,'name':name,'database_container':pg,'source_base':manifest['source_base'],
       'archive_sha256':manifest['archive_sha256'],'image_id':image,'cpu':1,'memory_mib':1200,
       'server_command':server_command,'server_evidence_source':None,'domain_command':domain_command,'domain_evidence_source':'local-bot-domain-r2 593 + r3 corrected4, targeted union594','production_database_used':False,
       'available_ram_before':memory['MemAvailable'],'free_disk_before':disk.free}
(root/'sdk-handle.json').write_text(json.dumps(proof,indent=2)+'\n');os.chown(root/'sdk-handle.json',1000,1000)
print(json.dumps(proof,indent=2))
