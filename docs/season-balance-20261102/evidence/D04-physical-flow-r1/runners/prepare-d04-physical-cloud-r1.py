from pathlib import Path
import io,json,hashlib,tarfile
base=Path(__file__).parent;repo=Path.cwd();out=base/'d04-physical-flow-cloud-input-r1';assert not out.exists()
binary=base/'d04-physical-flow-server-r2/build/bin/FantasyCard.Server.Tests/debug';assert json.loads((base/'d04-physical-flow-server-r2/result.json').read_bytes())['exit']==0
seed=json.loads((base/'d04-build-dimensions-cloud-r2-file/public/dependency-cache-seed.original.json').read_bytes());assert seed['seeded'] and seed['cap_bytes']==64*1024**2
probe=json.loads((base/'d04-physical-cache-readback-before-r1.derived.json').read_bytes());assert probe['verified'] and probe['root']==seed['cache_root']
out.mkdir();files={};cached={};payload_names={};expanded=0
for path in sorted(binary.rglob('*')):
    if not path.is_file():continue
    name='bin/'+path.relative_to(binary).as_posix();digest=hashlib.sha256(path.read_bytes()).hexdigest();files[name]=digest;expanded+=path.stat().st_size
    if seed['verified_files'].get(name)==digest:cached[name]=digest
    else:payload_names[name]=path
path=repo/'server/src/FantasyCard.Server/FantasyCard.Server.csproj';name=path.relative_to(repo).as_posix();files[name]=hashlib.sha256(path.read_bytes()).hexdigest();expanded+=path.stat().st_size;payload_names[name]=path
with tarfile.open(out/'payload.tar.gz','w:gz') as bundle:
    for name,path in payload_names.items():
        raw=path.read_bytes();info=tarfile.TarInfo(name);info.size=len(raw);bundle.addfile(info,io.BytesIO(raw))
body=(out/'payload.tar.gz').read_bytes();manifest=dict(payload_sha256=hashlib.sha256(body).hexdigest(),payload_bytes=len(body),expanded_bytes=expanded,files=files,cached_files=cached,cache_root=seed['cache_root'])
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
source=(base/'start-d04-room-events-cloud-r1.py').read_text(encoding='utf-8').replace('d04-room-events-r1','d04-physical-flow-r1')
old=['FantasyCard.Server.Tests.Persistence.PostgresRoomEventTelemetryTests.NewestCheckpointPreservesCumulativeEventsAndRestartContinuesOriginalIdsWithoutChangingAssetsOnQuery','FantasyCard.Server.Tests.Persistence.PostgresRoomEventTelemetryTests.OldMissingAndCorruptObservationsRemainExplicitGapsAndReadQueriesDoNotRepairThem','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_admin_economy_report_keeps_existing_HTTPS_key_and_no_store_boundary','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_actual17_preparation_READY_and_active_credit_resume_after_abrupt_restart_without_player_casts']
new=['FantasyCard.Server.Tests.Persistence.PostgresPhysicalEquipmentTelemetryTests.RealCraftReforgeMarketAndDiscardCountOneMintAndDestroyWhileOriginalCreatorSurvivesOwnerAndSourceChanges', 'FantasyCard.Server.Tests.Persistence.PostgresPhysicalEquipmentTelemetryTests.CommittedRecyclingUsesItsExactOriginalHoldAndReceiptWhileOtherItemCannotBorrowItsBuild', 'FantasyCard.Server.Tests.Persistence.PostgresPhysicalEquipmentTelemetryTests.UnknownTerminalTimeAndDuplicateDestructionClaimsRemainCoverageGapsRatherThanNewSupply', 'FantasyCard.Server.Tests.Persistence.PostgresPhysicalEquipmentTelemetryTests.ArchiveMarkersCoverWalletRecipeWishAndLoadoutsWithoutBackdatingLateCreditAmounts', 'FantasyCard.Server.Tests.Persistence.PostgresPhysicalEquipmentTelemetryTests.RealPreparationCancelAndMatchAdmissionRetainSelfOwnershipLegsWithoutChangingGameRules', 'FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_admin_economy_report_keeps_existing_HTTPS_key_and_no_store_boundary']
needle=','.join("'-method',"+repr(x) for x in old);assert source.count(needle)==1;source=source.replace(needle,','.join("'-method',"+repr(x) for x in new)).replace('planned_report_cases=4','planned_report_cases=6')
needle="    assert all(hashlib.sha256((root/'input'/n).read_bytes()).hexdigest()==h for n,h in manifest['files'].items())";assert source.count(needle)==1
insert='''    dependency_cache=Path('/home/ubuntu/season-balance-20261102-dependency-cache-v1')
    assert manifest['cache_root']==str(dependency_cache) and dependency_cache.resolve()==dependency_cache and not dependency_cache.is_symlink()
    assert json.loads((dependency_cache/'ownership.original.json').read_text())=={'task':'season-balance-20261102','schema':1,'cap_bytes':64*1024**2}
    copied=0
    for name,digest in manifest['cached_files'].items():
        assert name.startswith('bin/') and name.lower().endswith('.dll') and not Path(name).name.startswith('FantasyCard.') and '..' not in Path(name).parts and not Path(name).is_absolute()
        assert manifest['files'][name]==digest and re.fullmatch('[0-9a-f]{64}',digest)
        blob=dependency_cache/digest;assert blob.is_file() and not blob.is_symlink() and blob.stat().st_mode&0o222==0
        raw=blob.read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
        target=root/'input'/name;assert not target.exists();target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);copied+=len(raw)
    (public/'dependency-cache-reuse.original.json').write_text(json.dumps({'cache_root':str(dependency_cache),'reused_files':len(manifest['cached_files']),'materialized_bytes':copied,'all_reused_hashes_verified':True,'task_assemblies_reused':False,'credentials_cached':False})+'\\n')
'''
source=source.replace(needle,insert+needle)
needle='finally:\n    stop.set(); thread.join(timeout=5)';assert source.count(needle)==1
safe='''except BaseException as error:
    proof={'exit':90,'guard_ok':not breached.is_set(),'owned_schemas':[],'schemas_still_present':[],'input_unchanged':False,'new_completed_gameplay_encounters':0,'planned_report_cases':6,'production_database_used':False,'SDK_started':False,'worker_error_type':type(error).__name__}
    (public/'result.json').write_text(json.dumps(proof,indent=2)+'\\n')
'''
source=source.replace(needle,safe+needle)
path=base/'start-d04-physical-cloud-r1.py';assert not path.exists();compile(source,str(path),'exec');path.write_text(source,encoding='utf-8')
source=(base/'run-d04-room-events-file-r1.py').read_text(encoding='utf-8').replace('d04-room-events-r1','d04-physical-flow-r1').replace('d04-room-events-cloud-r1-file','d04-physical-flow-cloud-r1-file').replace('d04-room-events-cloud-input-r1','d04-physical-flow-cloud-input-r1').replace('start-d04-room-events-cloud-r1.py','start-d04-physical-cloud-r1.py').replace('d04-room-events-server-r2','d04-physical-flow-server-r2').replace("'-R','4','-B','32768'","'-R','64','-B','32768'")
path=base/'run-d04-physical-cloud-r1.py';assert not path.exists();compile(source,str(path),'exec');path.write_text(source,encoding='utf-8')
print(json.dumps(dict(cases=6,payload_bytes=len(body),expanded_bytes=expanded,reused_files=len(cached),all_task_assemblies_fresh=True,transport_window_bytes=64*32768,remote_execution=False)))
