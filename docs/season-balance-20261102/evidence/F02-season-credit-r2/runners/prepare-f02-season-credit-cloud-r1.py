from pathlib import Path
base=Path(__file__).parent
name='f02-season-credit'
p=base/'start-f02-season-credit-cloud-r1.py';assert not p.exists()
s=(base/'start-f02-loot-id-cloud-r1.py').read_text(encoding='utf-8').replace('f02-loot-id','f02-season-credit')
s=s.replace("cid=None","cid=None; input_mounted=False")
s=s.replace("    assert sample()['free_disk']-manifest['expanded_bytes']>=3*1024**3", """    assert manifest['expanded_bytes']<112*1024**2
    work=root/'input'; assert work.resolve()==work and work.parent==root and not work.exists()
    work.mkdir(); run(['mount','-t','tmpfs','-o','size=128m,nosuid,nodev','fc-season17-input',str(work)]); input_mounted=True
    assert run(['findmnt','-n','-o','FSTYPE','--target',str(work)]).decode().strip()=='tmpfs'
    (public/'input-tmpfs.original.json').write_text(json.dumps(dict(path=str(work),size_mib=128,payload_sha256=manifest['payload_sha256'],disk_payload_written=False))+'\\n')""")
old="FANTASYCARD_LOOT_ID_SCHEMA_EVIDENCE=/results/owned-schemas.original.jsonl\\nFANTASYCARD_LOOT_ID_PG_PROOF_OUTPUT=/results/identity.original.jsonl\\n"
assert old in s
s=s.replace(old,"FANTASYCARD_PROCESS_EVIDENCE=/results/process-logs\\nFANTASYCARD_PROCESS_SERVER_DLL=/workspace/bin/FantasyCard.Server.dll\\n")
start="'-method','FantasyCard.Server.Tests.Persistence.PostgresSeasonSettlementTests.SameSeedRoomRewardsCommitToTwoOwnersInOneSchemaAndReplayAfterRepositoryRestart','-method','FantasyCard.Server.Tests.Persistence.PostgresSeasonSettlementTests.PreUpgradeDuplicatePhysicalIdCannotStealAnOwnedItemOrPartiallyCommitTheSecondWallet'"
assert start in s
s=s.replace(start,"'-method','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_original16_and_current17_credit_survive_abrupt_restart_and_bad_archive_isolation'")
old="p=public/'owned-schemas.original.jsonl'; schemas=[json.loads(line)['schema'] for line in p.read_text().splitlines()] if p.exists() else []"
assert old in s
s=s.replace(old,"p=public/'process-logs/receipts.jsonl'; schemas=[row['evidence']['schema'] for line in p.read_text().splitlines() if (row:=json.loads(line))['caseId']=='SEASON17-schema'] if p.exists() else []")
s=s.replace("    if env.exists(): env.unlink()", """    if env.exists(): env.unlink()
    if input_mounted:
        assert (root/'input').resolve()==root/'input'
        run(['umount',str(root/'input')]); input_mounted=False
        assert not list((root/'input').iterdir())
    (public/'input-cache-cleanup.original.json').write_text(json.dumps(dict(tmpfs_unmounted=True,input_files_removed=True,local_source_payload_retained=True,other_projects_modified=False))+'\\n')""")
compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
p=base/'run-f02-season-credit-cloud-r1.py';assert not p.exists()
s=(base/'run-f02-loot-id-cloud-r1.py').read_text(encoding='utf-8').replace('f02-loot-id','f02-season-credit').replace('f02-season-credit-server-build-r1','f02-season-credit-build-r1')
needle="    p=repo/'server/src/FantasyCard.Server/FantasyCard.Server.csproj'"
assert needle in s
insert="""    for suffix in ['bytes','sha256','version.txt']:
        p=repo/('server/config/archive/season-v1-config-16/fantasycard.config.'+suffix);raw=p.read_bytes();name=p.relative_to(repo).as_posix();files[name]=hashlib.sha256(raw).hexdigest();expanded+=len(raw);info=tarfile.TarInfo(name);info.size=len(raw);tar.addfile(info,io.BytesIO(raw))
"""
s=s.replace(needle,insert+needle,1)
compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
print('Prepared existing guarded runtime flow for three exact new process cases; no execution yet. Payload mounts owned128MiB tmpfs and is removed after container termination.')
