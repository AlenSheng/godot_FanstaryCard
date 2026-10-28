#!/usr/bin/env python3
"""Root-dispatched Tencent fixture lifecycle attempt. No automatic dispatch/retry.

prepare freezes every current tracked client Git blob and render_runtime.py into
an independent source tree. Old .godot files are separately labelled derived
cache inputs; hardlinks never get chmod or in-place writes. Failed old sources
and metadata are rehashed before/after. Native driver uses Godot only.

Root first completes tuning R2 terminal/G cleanup and releases its pool hold.
prepare creates a fresh source only when queues are closed; run requires the
exact live lease and a separately root-created hold owned by that same lease.
The helper never creates/transfers/removes a scheduling hold or starts systemd.
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request

BASE=Path('/home/ubuntu/pr13-acceptance-20261009')
GIT=Path('/opt/fantasycard-github')
ATTEMPT='b08-fixture-lifecycle-r4-20261011'
OWNER='pr13-cap-'+ATTEMPT
E=BASE/'evidence'/ATTEMPT
W=BASE/'work'/ATTEMPT
SOURCE=W/'source'
RAM=Path('/dev/shm/pr13-'+ATTEMPT)
LOCK=BASE/'evidence/shared-resource-coordination.lock'
HOLD=BASE/'evidence/pool-render-segments-r3/scheduling-hold.json'
R2=BASE/'evidence/tuning-current-equivalence-r2-20261011'
R2_UNIT='pr13-cap-tuning-current-equivalence-r2-20261011'
R2_GC_LITERAL_SHA='d15b3316b903a3dddb2ed4c07d872ed1e2c2c44aa7d3e55b47c07094a9f9d264'
R2_MANIFEST_SHA='329e5af015b9a37cf3f292ddedb7824754dfde6c4689d87ccca1a1a57736bea8'
R2_GC_PROOF_SHA='b385889808a52e8151b1b12ea6ccb9394a965ec5f3a7993da7e47ea8cab96470'
R2_G_RECEIPT_SHA='00745112b303d9c804f85249f212ff486545bfe640f3f242aee140ad87523c5d'
R2_CLEANUP_SHA='924c8f0f7a1a4b31998bc522747baedb5241b3b380f88c60334a1df68c84413f'
IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
MONITOR='2734235cbfa1f9d8f1352cd9a925251f6356021d86ede341f80c6196e799149a'
FAILED_INPUTS_SHA='a2bbfbac0bb332232c9085f65e6385e4d87cbbcca73c272374aeb5bae8e2be5f'
OLD=[('audio',BASE/'evidence/audio-release-regression-r2',
      'ffcbedb6e6b7dfee11f8b889e5ae15bcf4a0448baa646d1a3118f876920bf64b'),
     ('element',BASE/'evidence/element-marginal-native-render-r6',
      'edb61a481d1906dd469f79e18b7a2b9696c73635a57fc98be74fccc6c8fd0d46')]
CACHE_SOURCE=BASE/'evidence/cloud-render-development/source-actual-pixels'
CACHE_PEER=BASE/'evidence/pool-render-segments-r2/shared-source'
RUNTIME_TOOL='tools/cloud/pr13/render_runtime.py'
WITNESS='client/tests/data/element_marginal_boundaries_native.json'
WITNESS_SHA='59298cc5611cff0f21d3ed795fdefc2cc0d1bf2bebb81900d585c0932ed003e0'
WITNESS_BYTES=1020093
WITNESS_SOURCE='e371315d283f581819d7090b606dc529f61d26fa'
MEMORY=1536*1024**2
FLOOR=500000000
OUTPUT_BUDGET=64*1024**2
METADATA_RESERVE=16*1024**2
CASES=[('REST','res://tests/pr13_audio_release_regression.tscn',120,None,None),
       ('PR13-B08.2-T01','res://tests/pr13_element_marginal_t01.tscn',600,18,1),
       ('PR13-B08.2-T02','res://tests/pr13_element_marginal_t02.tscn',600,18,1),
       ('PR13-B08.2-T03','res://tests/pr13_element_marginal_t03.tscn',600,18,1)]
DIRTY=('SCRIPT ERROR','Parse Error','Failed to load script','ObjectDB instances were leaked','resources still in use')


class Deferred(RuntimeError):
    pass


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(65536),b''):h.update(b)
    return h.hexdigest()


def read(path):return json.loads(Path(path).read_bytes())


def write_new(path,value):
    p=Path(path);require(not p.exists(),'Immutable attempt file already exists: '+str(p))
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write((json.dumps(value,indent=2,allow_nan=False)+'\n').encode())


def cmd(args,timeout=30,check=True):
    p=subprocess.run([str(x) for x in args],capture_output=True,timeout=timeout)
    require(not check or p.returncode==0,'Command failed: '+str(args[0])+' '+p.stderr.decode(errors='replace')[-2000:])
    return p


def docker(*args,**kw):return cmd(['sudo','-n','docker',*args],**kw)


def host():
    require(platform.system()=='Linux' and BASE.is_dir() and GIT.is_dir(),'Tencent acceptance host required')
    require(E.resolve()==BASE/'evidence'/ATTEMPT and W.resolve()==BASE/'work'/ATTEMPT
            and RAM.resolve()==Path('/dev/shm')/('pr13-'+ATTEMPT),'Owned absolute paths changed')
    require(not any(p.is_symlink() for p in (E,W,SOURCE,RAM,LOCK,HOLD)),'Owned paths/queue locks may not be symlinks')


@contextlib.contextmanager
def coordination():
    import fcntl
    require(not LOCK.is_symlink(),'Shared coordination lock symlink rejected')
    with LOCK.open('a') as f:
        try:fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Deferred('Shared resource coordination is busy; no startup created')
        yield


def health():
    with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:
        require(h.status==200,'Production health must remain 200')
    return 200


def resources(start=False,disk_reserve=METADATA_RESERVE):
    mem=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
    stat=os.statvfs(BASE);disk_free=stat.f_bavail*stat.f_frsize;disk_total=stat.f_blocks*stat.f_frsize
    used=sum(p.stat().st_size for p in RAM.rglob('*') if p.is_file()) if RAM.exists() else 0
    shm=shutil.disk_usage('/dev/shm')
    record={'at':time.time(),'memory_available_bytes':mem,'root_free_ratio':disk_free/disk_total,
            'root_free_bytes':disk_free,'owned_tmpfs_output_bytes':used,'tmpfs_free_bytes':shm.free}
    if start and (mem<FLOOR+MEMORY+OUTPUT_BUDGET or disk_free-disk_reserve<.15*disk_total
                  or shm.free<OUTPUT_BUDGET):
        raise Deferred('500MB/1536MiB/64MiB memory, root 15% or metadata reservation unavailable')
    require(mem>=FLOOR and disk_free-disk_reserve>=.15*disk_total and used<=OUTPUT_BUDGET,'Live resource/output safety floor crossed')
    health();return record


def unit_state(name):
    p=cmd(['systemctl','show',name,'--property=Id,LoadState,MainPID,ActiveState,SubState,ExecMainStatus,InvocationID'],check=False)
    v=dict(x.split('=',1) for x in p.stdout.decode().splitlines() if '=' in x)
    expected=name if name.endswith('.service') else name+'.service'
    complete=(p.returncode==0 and v.get('Id')==expected and 'LoadState' in v
              and all(k in v for k in ('MainPID','ActiveState','SubState','ExecMainStatus'))
              and v.get('MainPID','').isdigit() and v.get('ExecMainStatus','').isdigit())
    if complete:v.update(MainPID=int(v['MainPID']),ExecMainStatus=int(v['ExecMainStatus']))
    return {'authoritative':complete and v.get('LoadState')=='loaded','complete_observation':complete,'returncode':p.returncode,**v}


def current_boot():
    value=Path('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-','')
    require(re.fullmatch('[0-9a-f]{32}',value),'Actual current Linux boot identity required')
    return value


def no_owned_containers(unit):
    owner=unit.removesuffix('.service')
    for cid in docker('ps','-a','-q','--no-trunc').stdout.decode().splitlines():
        require(re.fullmatch('[0-9a-f]{64}',cid),'Full current Docker identity required')
        info=json.loads(docker('inspect',cid).stdout)[0];require(info.get('Id')==cid,'Current container identity uncertain')
        labels=info.get('Config',{}).get('Labels') or {}
        require(labels.get('codex.owner')!=owner and not info.get('Name','').lstrip('/').startswith(owner),
                'GC terminal proof cannot leave an owned container')


def manager_success(unit,context):
    """Actual PID1 journal, never a zero/default status or stale boolean proof."""
    boot=current_boot();name=unit if unit.endswith('.service') else unit+'.service'
    require(context.get('boot_id',boot)==boot,'Frozen execution belongs to another boot')
    completed=cmd(['journalctl','--no-pager','-o','json','_PID=1','UNIT='+name,'_BOOT_ID='+boot],timeout=30)
    require(len(completed.stdout)<=2*1024**2,'Exact manager journal projection exceeds bounded metadata size')
    rows=[json.loads(line) for line in completed.stdout.splitlines() if line]
    require(rows and all(row.get('_PID')=='1' and row.get('UNIT')==name and row.get('_BOOT_ID')==boot for row in rows),
            'Only exact unit/currentboot/PID1 manager records may prove GC termination')
    invocations={row.get('INVOCATION_ID') for row in rows if row.get('INVOCATION_ID')}
    require(len(invocations)==1 and re.fullmatch('[0-9a-f]{32}',next(iter(invocations))),
            'Exact successful invocation is absent/ambiguous or has a later different invocation')
    invocation=next(iter(invocations))
    require(not context.get('invocation_id') or context['invocation_id']==invocation,'Frozen/live invocation identity differs')
    require(all(row.get('INVOCATION_ID')==invocation for row in rows),
            'Unbound/different PID1 unit activity may not be hidden by a GC state')
    require(not any(re.search(r'\b(failed|failure|killed|oom|timeout)\b',row.get('MESSAGE',''),re.I) for row in rows),
            'Any exact unit manager failure rejects GC terminal proof, including rows without invocation metadata')
    rows=[row for row in rows if row.get('INVOCATION_ID')==invocation]
    success=[row for row in rows if row.get('MESSAGE_ID')=='7ad2d189f7e94e70a38c781354912448'
             and row.get('MESSAGE')==name+': Deactivated successfully.']
    require(len(success)==1 and not any(re.search(r'\b(failed|failure|killed|oom|timeout)\b',row.get('MESSAGE',''),re.I) for row in rows),
            'Exact PID1 success required and any failure manager record rejects terminal proof')
    end=int(success[0]['__REALTIME_TIMESTAMP'])
    start=[row for row in rows if row.get('MESSAGE_ID')=='7d4958e842da4a758f6c1cdc7b36dcc5']
    started=[row for row in rows if row.get('MESSAGE_ID')=='39f53479d3a045ac8e11786248231fbf']
    require(len(start)==len(started)==1 and int(start[0]['__REALTIME_TIMESTAMP'])<=int(started[0]['__REALTIME_TIMESTAMP'])<=end,
            'Exact manager start/started/success lifecycle required')
    at=int(context['at']*1000000)
    if context['timestamp_role']=='before-dispatch':
        require(at<=int(start[0]['__REALTIME_TIMESTAMP'])<=at+120*1000000,'Journal start must bind the exact frozen dispatch metadata time')
    else:
        require(int(start[0]['__REALTIME_TIMESTAMP'])<=at<=end,'Frozen observed live runner must fall inside that exact invocation')
    no_owned_containers(name)
    return {'authority':'exact-systemd-manager-journal','unit':name,'boot_id':boot,'invocation_id':invocation,
            'startup_context':context,'successful_PID1_journal':success[0],
            'manager_projection_sha256':hashlib.sha256(completed.stdout).hexdigest(),'manager_rows':len(rows),
            'no_later_different_invocation':True,'no_failed_manager_journal':True,'no_owned_native_containers':True}


def exact_terminal(unit,context):
    state=unit_state(unit)
    if state['authoritative']:
        require(state['MainPID']==0 and state['ActiveState'] not in ('active','activating','deactivating','reloading')
                and state['ExecMainStatus']==0,'Exact loaded unit is not successfully terminal')
        return {'authority':'exact-loaded-systemd-state','current_state':state}
    require(state.get('complete_observation') is True and state.get('LoadState')=='not-found'
            and state.get('MainPID')==0 and state.get('ExecMainStatus')==0 and state.get('ActiveState')=='inactive'
            and state.get('SubState')=='dead','Incomplete/ambiguous/current live status cannot use GC terminal fallback')
    require(context is not None,'GC unit needs frozen actual execution binding, never not-found defaults')
    return {**manager_success(unit,context),'current_state':state,'mode':'garbage-collected-after-exact-success'}


def r2_gc_terminal():
    # Reuse the independently reviewed exact original R2 verifier literal,
    # without importing or invoking its transport/cleanup driver or writer.
    code=Path(__file__).with_name('b08_fixture_R2_GC_verifier.reviewed.py')
    require(code.is_file() and sha(code)==R2_GC_LITERAL_SHA,'Frozen reviewed readonly R2 GC verifier companion required')
    def fixed(path):
        p=Path(path);require(p.resolve(strict=True)==p and not p.is_symlink() and p.is_relative_to(BASE),
                             'GC verifier original path escaped acceptance root');return p
    def ordinary(path):
        p=fixed(path);require(p.is_file(),'GC verifier original metadata must be a regular file');return p.stat()
    namespace={'B':BASE,'A':'tuning-current-equivalence-r2-20261011','E':R2,
               'W':BASE/'work/tuning-current-equivalence-r2-20261011','UNIT':R2_UNIT,'EXPECTED':R2_MANIFEST_SHA,
               'command':lambda args:cmd(args,timeout=30).stdout,'ordinary':ordinary,'fixed':fixed,'sha':sha,'require':require,
               'json':json,'hashlib':hashlib,'sys':sys,'os':os,'Path':Path}
    exec(compile(code.read_bytes(),str(code),'exec'),namespace)
    proof,projection=namespace['gc_terminal_proof']()  # Fresh actual read-only authorities.
    original=BASE/'evidence/tuning-current-equivalence-r2-terminal-proof-20261011/terminal.json'
    journal=original.with_name('unit-journal-projection.json')
    if not original.is_file() or not journal.is_file():raise Deferred('Root separately derived exact R2 journal proof is not yet closed')
    require(original.read_bytes()==namespace['canonical'](proof) and journal.read_bytes()==projection,
            'Original frozen derived R2 proof differs from fresh actual authorities')
    require(sha(original)==R2_GC_PROOF_SHA,'Root-verified exact R2 derived proof original bytes changed')
    return {'authority':proof['terminal_authority'],'proof_path':str(original),'proof_sha256':sha(original),
            'journal_projection_sha256':sha(journal),'invocation_ID':proof['invocation_ID'],
            'current_state':proof['current_state_observed'],'readonly_verifier_literal_sha256':R2_GC_LITERAL_SHA}


def predecessor_closed():
    state=unit_state(R2_UNIT)
    if state['authoritative']:
        if state['MainPID']!=0 or state['ActiveState'] in ('active','activating','deactivating','reloading') or state['ExecMainStatus']!=0:
            raise Deferred('Tuning R2 exact authoritative terminal state is not closed')
        terminal={'authority':'exact-loaded-systemd-state','current_state':state}
    else:
        if not (state.get('complete_observation') is True and state.get('LoadState')=='not-found'
                and state.get('MainPID')==0 and state.get('ExecMainStatus')==0 and state.get('ActiveState')=='inactive'):
            raise Deferred('R2 current state is incomplete/live/failed; GC zero defaults cannot prove closure')
        terminal=r2_gc_terminal()
    files={k:R2/name for k,name in [('result','run-result.json'),('backup','local-backup-receipt.json'),
                                   ('cleanup','local-storage-cleanup.json'),('manifest','delivery-manifest.json')]}
    if not all(p.is_file() for p in files.values()):raise Deferred('Tuning R2 original G backup/cleanup still pending')
    require(sha(files['backup'])==R2_G_RECEIPT_SHA and sha(files['cleanup'])==R2_CLEANUP_SHA,
            'Root-verified R2 G receipt/cleanup original byte anchors changed')
    result,backup,cleanup,manifest=[read(files[k]) for k in ('result','backup','cleanup','manifest')]
    require(result.get('ok') is True and result.get('families_completed')==36
            and result.get('total_unique_native_encounters')==432 and state['ExecMainStatus']==0,
            'Exact all-36/all-432 R2 gate must be terminal; failed R2 requires root separate closure review')
    require(backup.get('ok') is True and backup.get('attempt')=='tuning-current-equivalence-r2-20261011'
            and backup.get('manifest_sha256')==sha(files['manifest'])
            and backup.get('members_verified')==len(manifest['files'])
            and backup.get('families_verified')==36 and backup.get('unique_encounters_verified')==432
            and all(backup.get(k) is True for k in ('archive_gzip_CRC_verified','all_original_members_sha256_verified','inner_gzip_CRC_raw_SHA_counts_verified'))
            and cleanup.get('ok') is True and cleanup.get('attempt')=='tuning-current-equivalence-r2-20261011'
            and cleanup.get('local_G_archive_sha256')==backup.get('sha256')
            and cleanup.get('local_G_archive_bytes')==backup.get('bytes')
            and cleanup.get('failed_originals_retained') is True
            and cleanup.get('runtime_and_retained_metadata_preserved') is True,
            'Original R2 G proof/cleanup byte chain incomplete')
    return {'systemd':state,'terminal_authority':terminal,'original_files':{k:{'path':str(p),'sha256':sha(p)} for k,p in files.items()}}


def previous_pool_closed(segment):
    # Equivalent retained proof gates to pool_segment_controller.cleaned and
    # backup_validate. Presence alone never substitutes for G byte closure.
    root=BASE/'evidence/pool-render-segments-r3';metadata=root/segment['id']
    output=BASE/'work/pool-render-segments-r3'/segment['id']
    required=[metadata/name for name in ('delivery-manifest.json','local-backup-receipt.json','local-storage-cleanup.json','result.json')]
    if not all(p.is_file() for p in required):raise Deferred('Earlier renderer original still awaits complete G backup/cleanup')
    plan=read(root/'plan.json');manifest,backup,cleanup,result=[read(p) for p in required]
    unit='pr13-pool-segment-r3-'+segment['id'].lower()
    state=unit_state(unit)
    if state['authoritative']:exact_terminal(unit,None)
    else:
        # This fixed attempt uses the exact current closed segment independently
        # observed by root. No arbitrary GC segment is silently adopted.
        require(segment['id']=='Guardian-3-T02-en','Unknown GC renderer needs a separately frozen exact invocation proof')
        startup=read(metadata/'startup.json')
        require(startup.get('unit')==unit and startup.get('segment')==segment
                and startup.get('created_at_unix')==1791685292.0536804
                and startup.get('dispatch_returncode')==0 and startup.get('retry_launch_forbidden') is True,
                'Exact original pool dispatch timestamp/identity required')
        exact_terminal(unit,{'at':startup['created_at_unix'],'timestamp_role':'before-dispatch',
                            'boot_id':'349714762b35423fa8dec83b08346ffe','invocation_id':'bbf5f406a041435c90d7c9bda0337c8e',
                            'startup_sha256':sha(metadata/'startup.json')})
    require(manifest.get('segment')==segment and backup.get('ok') is True and backup.get('segment')==segment
            and backup.get('manifest_sha256')==sha(required[0])
            and backup.get('members')==backup.get('members_verified')==len(manifest['files'])
            and backup.get('render_source_sha')==plan['render_source_sha']
            and backup.get('native_source_sha')==plan['native_source_sha']=='1341e160afc67ba826d4b37250c9ec58f8c99462'
            and backup.get('matrix_rows_verified')==backup.get('independent_wire_command_rows_verified')==segment['expected_rows']
            and backup.get('PNG_CRC_deflate_verified')==9 and backup.get('normal_shutdown_clean') is True
            and backup.get('archive_gzip_CRC_verified') is True and backup.get('no_native_business_executed_locally') is True
            and backup.get('whole_task_accepted') is False and backup.get('full_matrix_accepted') is False
            and backup.get('scope')=='one cloud software-rendered fixture language segment'
            and re.fullmatch('[0-9a-f]{64}',backup.get('sha256',''))
            and type(backup.get('bytes')) is int and backup['bytes']>0
            and all(re.match(r'^G:[\\/]',backup.get(k,''),re.IGNORECASE) for k in ('local_archive','local_directory')),
            'Previous renderer original G/native/PNG/wire/source proof is incomplete')
    require(cleanup.get('ok') is True and cleanup.get('segment')==segment['id']
            and cleanup.get('manifest_sha256')==backup['manifest_sha256']
            and cleanup.get('local_G_archive_sha256')==backup['sha256'] and cleanup.get('local_G_archive_bytes')==backup['bytes']
            and cleanup.get('render_source_sha')==plan['render_source_sha'] and cleanup.get('output_directory')==str(output)
            and not output.exists() and result.get('ok') is True and result.get('source_sha')==plan['render_source_sha'],
            'Previous renderer exact cleanup/source byte anchors failed')
    require(len({r['path'] for r in manifest['files']})==len(manifest['files']),'Duplicate previous renderer original member')
    for row in manifest['files']:
        name=PurePosixPath(row['path']);require(not name.is_absolute() and '..' not in name.parts,'Unsafe prior renderer member')
        if row['path'].startswith('metadata/'):
            path=Path(row['source'])
            require(path.resolve().is_relative_to(metadata.resolve()) and path.is_file() and not path.is_symlink()
                    and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],'Retained prior renderer metadata changed')


def queue_gate(running):
    if HOLD.exists():
        h=read(HOLD)
        require(h.get('active') is True and h.get('whole_task_accepted') is False,'Malformed/unresolved pool hold')
        if h.get('owner')!=OWNER:raise Deferred('Another root-owned pool hold exists; never replace/release it')
    elif running:raise Deferred('Root must explicitly create the exact lifecycle scheduling hold before run')
    rows=cmd(['systemctl','list-units','--state=running','--no-legend','--plain','pr13-cap-*','pr13-pool-segment-*'],timeout=15).stdout.decode().splitlines()
    if any(row.split()[0].removesuffix('.service')!=OWNER for row in rows if row.split()):
        raise Deferred('Earlier cap/render/tuning lease is still running')
    for cid in docker('ps','-q','--no-trunc').stdout.decode().splitlines():
        info=json.loads(docker('inspect',cid).stdout)[0]
        require(info.get('Id')==cid,'Exact active container identity uncertain')
        if info.get('Name','').lstrip('/').startswith(('pr13-cap-','pr13-pool-segment-')):
            raise Deferred('Earlier owned cap/render container still running')
    for p in (BASE/'evidence/cap-experiment-full-r3/units').glob('*/resource-reservation.json'):
        v=read(p)
        if not (v.get('status')=='Ended' and v.get('G_backup_verified') is True and v.get('output_cleaned') is True):
            raise Deferred('Earlier cap reservation is not naturally terminal/G-verified/cleaned')
    # A pool current segment may have ended yet still await original G delivery.
    state_path=BASE/'evidence/pool-render-segments-r3/current-segment.json'
    if state_path.exists():
        current=read(state_path)
        if current is not None:
            require(isinstance(current,dict) and isinstance(current.get('id'),str),'Exact pool current segment schema required')
            segment=current['id']
            previous_pool_closed(current)


def active_bind_guard(targets):
    for cid in docker('ps','-q','--no-trunc').stdout.decode().splitlines():
        require(re.fullmatch('[0-9a-f]{64}',cid),'Authoritative full active container ID required')
        info=json.loads(docker('inspect',cid).stdout)[0];require(info.get('Id')==cid,'Active identity changed')
        for mount in info.get('Mounts',[]):
            if mount.get('Type')!='bind':continue
            if cid==MONITOR and mount.get('Source')=='/' and mount.get('RW') is False:continue
            source=Path(mount['Source']).resolve()
            require(not any(source==t or source.is_relative_to(t) or t.is_relative_to(source) for t in targets),
                    'Active bind touches protected source/work: '+cid)


def tree(source):
    require(source.is_dir() and not source.is_symlink(),'Original source directory required')
    values={}
    for p in sorted(source.rglob('*')):
        require(not p.is_symlink(),'Source/cache symlink rejected')
        if p.is_file():values[p.relative_to(source).as_posix()]=sha(p)
    return values


def old_sources(expected_inputs_sha):
    require(expected_inputs_sha==FAILED_INPUTS_SHA,'Exact original failed-input manifest anchor required')
    originals={}
    for role,evidence,result_sha in OLD:
        inputs=evidence/'inputs.json';source=evidence/'source';result=evidence/'result.json'
        require(sha(inputs)==expected_inputs_sha and sha(result)==result_sha,'Original failed metadata bytes changed: '+role)
        values=read(inputs);require(isinstance(values,dict) and len(values)==2100,'Original 2100 input members required')
        for name,value in values.items():
            p=(source/name).resolve()
            require(p.is_relative_to(source.resolve()) and p.is_file() and not p.is_symlink() and sha(p)==value,
                    'Original failed source member missing/changed: '+name)
        require((source/'client/.godot/imported').is_dir(),'Preserved imported cache required; no import generation')
        originals[role]={'source':str(source),'input_sha256':sha(inputs),'result_sha256':sha(result),'files':tree(source)}
    return originals


def current_git(release):
    require(re.fullmatch('[0-9a-f]{40}',release or ''),'Explicit final published --release-sha required')
    require(cmd(['git','-C',GIT,'rev-parse','HEAD']).stdout.decode().strip()==release,'Cloud HEAD must equal the final published release')
    require(not cmd(['git','-C',GIT,'status','--porcelain','--untracked-files=no']).stdout.strip(),'Cloud tracked checkout must be clean')
    listing=cmd(['git','-C',GIT,'ls-tree','-r','-z','--full-tree',release,'--','client',RUNTIME_TOOL]).stdout
    records=[];fetched_text_bytes=0
    for item in listing.split(b'\0'):
        if not item:continue
        meta,name=item.split(b'\t',1);mode,kind,blob=meta.decode().split();name=name.decode()
        require(kind=='blob' and mode in ('100644','100755') and (name.startswith('client/') or name==RUNTIME_TOOL)
                and '.godot' not in PurePosixPath(name).parts,'Current Git tracked client/tool must be ordinary source files, not derived cache')
        cached=BASE/'evidence/element-marginal-native-render-r6/source'/name
        cached_match=False;blob_bytes=0;blob_sha256=''
        if cached.is_file() and not cached.is_symlink():
            size=cached.stat().st_size;identity=hashlib.sha1(b'blob '+str(size).encode()+b'\0');digest=hashlib.sha256();count=0
            with cached.open('rb') as handle:
                for block in iter(lambda:handle.read(65536),b''):
                    identity.update(block);digest.update(block);count+=len(block)
            require(count==size and cached.stat().st_size==size,'Cached source changed during Git identity hashing')
            if identity.hexdigest()==blob:
                cached_match=True;blob_bytes=size;blob_sha256=digest.hexdigest()
        if not cached_match:
            # This release changes text/test source only. Large asset blobs must
            # come from the frozen cache with their exact commit object identity.
            require(PurePosixPath(name).suffix in ('.gd','.tscn','.json','.md','.py','.uid','.import')
                    or PurePosixPath(name).name=='.gitignore','Uncached non-text asset cannot trigger a lazy download')
            size=int(cmd(['git','-C',GIT,'cat-file','-s',blob]).stdout.decode().strip())
            require(0<=size<=16*1024**2 and fetched_text_bytes+size<=64*1024**2,
                    'Bounded new text-source blob budget exceeded')
            body=cmd(['git','-C',GIT,'cat-file','blob',blob]).stdout
            require(len(body)==size and hashlib.sha1(b'blob '+str(size).encode()+b'\0'+body).hexdigest()==blob,
                    'Actual new Git text blob byte anchor differs')
            fetched_text_bytes+=size;blob_bytes=size;blob_sha256=hashlib.sha256(body).hexdigest()
        checkout=GIT/name
        if checkout.exists():
            require(checkout.is_file() and not checkout.is_symlink() and sha(checkout)==blob_sha256,
                    'Present checkout input differs from the selected Git source: '+name)
            presence='present-and-byte-verified'
        else:
            require(cmd(['git','-C',GIT,'config','--get','core.sparseCheckout']).stdout.decode().strip()=='true',
                    'Missing input is permitted only by an explicit sparse checkout')
            flag=cmd(['git','-C',GIT,'ls-files','-v','--',name]).stdout.decode().splitlines()
            require(flag==['S '+name], 'Missing input must be the exact indexed skip-worktree file: '+name)
            presence='indexed-sparse-input-materialized-from-verified-Git-blob'
        records.append({'path':name,'bytes':blob_bytes,'sha256':blob_sha256,'git_blob_sha1':blob,
                        'mode':mode,'cloud_checkout_presence':presence,
                        'source_byte_authority':'cached-byte-exact-Git-object-identity' if cached_match else 'bounded-selected-Git-text-blob'})
    require(records and len({r['path'] for r in records})==len(records)
            and len([r for r in records if r['path']==RUNTIME_TOOL])==1,'All current tracked client plus renderer tool required')
    witness=[r for r in records if r['path']==WITNESS]
    require(len(witness)==1 and witness[0]['sha256']==WITNESS_SHA and witness[0]['bytes']==WITNESS_BYTES,
            'Original e371 native boundary witness must remain exact original bytes; never generate replacement values')
    return records


def output_mount():
    found=[]
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        left,right=line.split(' - ',1);fields=left.split();details=right.split()
        if fields[4]==str(RAM):found.append({'mount_id':int(fields[0]),'mountpoint':fields[4],
                                          'fstype':details[0],'source':details[1],'super_options':details[2]})
    require(len(found)==1 and found[0]['fstype']=='tmpfs' and found[0]['source']==OWNER,
            'Exact owned 64MiB output tmpfs mount required')
    stat=os.statvfs(RAM)
    require(stat.f_blocks*stat.f_frsize<=OUTPUT_BUDGET,'Owned output tmpfs exceeds frozen 64MiB size')
    return found[0]


def derived_cache():
    require(CACHE_SOURCE.is_dir() and CACHE_PEER.is_dir() and not CACHE_SOURCE.is_symlink() and not CACHE_PEER.is_symlink(),
            'Declared independent preserved cache sources required')
    primary={'client/.godot/'+k:v for k,v in tree(CACHE_SOURCE/'client/.godot').items()}
    peer={'client/.godot/imported/'+k:v for k,v in tree(CACHE_PEER/'client/.godot/imported').items()}
    imported={k:v for k,v in primary.items() if k.startswith('client/.godot/imported/')}
    require(len(primary)==1246 and len(imported)==1244 and imported==peer,
            'All 1244 preserved imported-cache bytes must match the independently preserved peer')
    require(set(primary)-set(imported)=={'client/.godot/global_script_class_cache.cfg','client/.godot/uid_cache.bin'},
            'Only two explicitly declared script/UID caches may accompany the full import cache')
    return primary


def prepare(args):
    host()
    with coordination():
        predecessor=predecessor_closed();queue_gate(False)
        require(not E.exists() and not W.exists() and not RAM.exists(),'Fresh independent attempt only')
        resources(start=True)
        originals=old_sources(args.failed_inputs_sha256);records=current_git(args.release_sha)
        old_source=Path(originals['element']['source'])
        active_bind_guard([old_source,Path(originals['audio']['source']),CACHE_SOURCE,CACHE_PEER,W,RAM])
        cache=derived_cache()
        require(cache and any(k.startswith('client/.godot/imported/') for k in cache),'Complete declared derived import cache required')
        changed=[r for r in records if originals['element']['files'].get(r['path'])!=r['sha256']]
        required=sum(r['bytes'] for r in changed)+METADATA_RESERVE
        resources(start=True,disk_reserve=required)
        E.mkdir();SOURCE.mkdir(parents=True)
        linked=0;written=0
        for r in records:
            target=SOURCE/r['path'];old=old_source/r['path'];target.parent.mkdir(parents=True,exist_ok=True)
            if old.is_file():os.link(old,target)
            if not target.exists() or sha(target)!=r['sha256']:
                # A reused path must be detached before any write; never mutate an
                # inode still linked into either failed source/cache directory.
                if target.exists():target.unlink()
                body=cmd(['git','-C',GIT,'cat-file','blob',r['git_blob_sha1']]).stdout
                with target.open('xb') as f:f.write(body)
                target.chmod(0o755 if r['mode']=='100755' else 0o644);written+=1
            else:linked+=1
            require(sha(target)==r['sha256'],'New independent current Git source differs')
        for name,value in cache.items():
            target=SOURCE/name;target.parent.mkdir(parents=True,exist_ok=True)
            require(not target.exists(),'Derived cache must not alias a tracked Git source path')
            os.link(CACHE_SOURCE/name,target);require(sha(target)==value,'Reused derived cache changed')
        full=tree(SOURCE)
        require(set(full)=={r['path'] for r in records}|set(cache),'New source contains undeclared inputs')
        require(old_sources(args.failed_inputs_sha256)==originals,'Preparation changed old failed source/cache/metadata')
        write_new(E/'inputs.json',full)  # Plain top-level hashmap accepted by frozen render_runtime.
        write_new(E/'current-Git-source.json',{'source_sha':args.release_sha,'files':records,'client_all_tracked_Git_blob_bytes_verified':True,
                  'renderer_tool_actual_Git_blob_bytes_verified':True,'whole_server_Git_tree_identity_claimed':False,'cloud_checkout_is_sparse':True,'all_new_test_source_bytes_from_selected_Git_blobs':True})
        write_new(E/'derived-cache-inputs.json',{'kind':'reused-old-derived-Godot-cache-not-current-Git-source',
                  'original_source':str(CACHE_SOURCE),'independent_imported_cache_peer':str(CACHE_PEER),'all_1244_imported_bytes_match_peer':True,'original_failed_inputs_sha256':args.failed_inputs_sha256,'files':cache,
                  'hardlinked_readonly_inputs':True,'new_import_or_numeric_generation_executed':False})
        write_new(E/'old-failed-preservation-before.json',originals)
        write_new(E/'tuning-R2-closure-observed.json',predecessor)
        shutil.copyfile(__file__,E/'runner.original.py')
        gc_literal=Path(__file__).with_name('b08_fixture_R2_GC_verifier.reviewed.py')
        require(sha(gc_literal)==R2_GC_LITERAL_SHA,'Reviewed GC literal changed')
        shutil.copyfile(gc_literal,E/'R2-GC-verifier.original.py')
        prereg={'schema_version':1,'attempt':ATTEMPT,'systemd_unit':OWNER,'release_sha':args.release_sha,'image_sha':IMAGE,
                'input_sha256':sha(E/'inputs.json'),'input_files':len(full),'current_tracked_source_files':len(records),
                'derived_cache_files':len(cache),'new_source_files_written':written,'unchanged_source_files_hardlinked':linked,
                'source_directory':str(SOURCE),'helper_sha256':sha(E/'runner.original.py'),
                'R2_GC_verifier_literal_sha256':sha(E/'R2-GC-verifier.original.py'),
                'current_Git_source_manifest_sha256':sha(E/'current-Git-source.json'),'derived_cache_manifest_sha256':sha(E/'derived-cache-inputs.json'),
                'old_preservation_manifest_sha256':sha(E/'old-failed-preservation-before.json'),
                'failed_inputs_sha256':args.failed_inputs_sha256,'original_native_witness_source_sha':WITNESS_SOURCE,
                'original_native_witness_path':WITNESS,'original_native_witness_bytes':WITNESS_BYTES,'original_native_witness_sha256':WITNESS_SHA,
                'cases':[{'id':case,'scene':scene,'deadline_seconds':deadline,'expected_rows':rows,'expected_png':png} for case,scene,deadline,rows,png in CASES],
                'memory_floor_bytes':FLOOR,'container_memory_bytes':MEMORY,'root_free_ratio_floor':.15,
                'tmpfs_output_max_bytes':OUTPUT_BUDGET,'metadata_reserve_bytes':METADATA_RESERVE,
                'health_timeout_seconds':10,'network':'none','source_and_cache_mounts':'readonly',
                'driver':'This frozen helper; Godot command follows frozen current render_runtime.py, which is an input source and is not invoked as an alternate driver',
                'Godot_only_no_NET_or_business_numeric_generation':True,'automatic_dispatch_or_retry':False,
                'failed_old_inputs_retained':True,'MAIN_accepted':False,'whole_task_accepted':False}
        write_new(E/'preregistration.json',prereg)
        return {'ok':True,'prepared':True,'source_sha':args.release_sha,'input_files':len(full),'inputs_sha256':sha(E/'inputs.json'),
                'preregistration_sha256':sha(E/'preregistration.json'),'source':str(SOURCE),'no_native_executed':True,'MAIN_accepted':False}


def frozen(args):
    p=read(E/'preregistration.json')
    require(p['release_sha']==args.release_sha and p['systemd_unit']==OWNER and p['helper_sha256']==sha(__file__)
            and p['R2_GC_verifier_literal_sha256']==R2_GC_LITERAL_SHA==sha(E/'R2-GC-verifier.original.py')
            and p['input_sha256']==sha(E/'inputs.json') and p['current_Git_source_manifest_sha256']==sha(E/'current-Git-source.json')
            and p['derived_cache_manifest_sha256']==sha(E/'derived-cache-inputs.json')
            and p['old_preservation_manifest_sha256']==sha(E/'old-failed-preservation-before.json'),'Frozen metadata/helper drift')
    require(tree(SOURCE)==read(E/'inputs.json'),'All actual frozen source/cache inputs must be unchanged')
    require(derived_cache()==read(E/'derived-cache-inputs.json')['files'],'Independent preserved import cache bytes changed')
    require(current_git(args.release_sha)==read(E/'current-Git-source.json')['files'],'Entire current tracked Git source changed')
    require(old_sources(p['failed_inputs_sha256'])==read(E/'old-failed-preservation-before.json'),'Original failed source/cache/metadata changed')
    return p


def inspect_owned(cid):
    require(re.fullmatch('[0-9a-f]{64}',cid),'Exact immutable full owned container ID required')
    info=json.loads(docker('inspect',cid).stdout)[0]
    require(info.get('Id')==cid and info.get('Config',{}).get('Labels',{}).get('codex.owner')==OWNER
            and info['Config']['Labels'].get('pr13.attempt')==ATTEMPT,'Owned container identity differs; no foreign teardown')
    return info


def stop_remove_owned(cid):
    info=inspect_owned(cid)
    if info['State']['Running']:docker('stop','--time','10',cid,timeout=30)
    require(inspect_owned(cid)['State']['Running'] is False,'Owned container stop uncertain')
    docker('rm',cid)


def one_case(case,scene,deadline,rows,png):
    output=RAM/case;output.mkdir();os.chmod(output,0o777)
    output_mount();require(resources(start=True)['owned_tmpfs_output_bytes']<=OUTPUT_BUDGET,'Owned aggregate tmpfs budget')
    cid=None;process=None;result={'ok':False,'case_id':case,'scene':scene,'source_sha':read(E/'preregistration.json')['release_sha'],
        'original_native_witness_source_sha':WITNESS_SOURCE,'display_is_software_fixture_only':True,'MAIN_accepted':False}
    try:
        cid=docker('create','--name',OWNER+'-'+case.lower().replace('.','-'),'--label','codex.owner='+OWNER,
                   '--label','pr13.attempt='+ATTEMPT,'--network','none','--memory','1536m','--memory-swap','1536m',
                   '--cpus','1','--shm-size','128m','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=268435456',
                   '--user','1000:1000','-e','HOME=/tmp/render-home','-e','XDG_DATA_HOME=/tmp/render-data',
                   '-e','XDG_CONFIG_HOME=/tmp/render-config','-e','XDG_CACHE_HOME=/tmp/render-cache',
                   '-e','FANTASYCARD_SERVER_URL=http://127.0.0.1:1','-e','FANTASYCARD_ART_EVIDENCE=/evidence',
                   '-v',str(SOURCE/'client')+':/work/client:ro','-v',str(output)+':/evidence',IMAGE,'sleep',str(deadline+120)).stdout.decode().strip()
        inspect_owned(cid);result['owned_container_id']=cid;docker('start',cid)
        command=['sudo','-n','docker','exec',cid,'xvfb-run','-a','-s','-screen 0 1920x1080x24 -nolisten tcp',
                 'godot','--verbose','--path','/work/client','--display-driver','x11','--rendering-method','gl_compatibility',
                 '--audio-driver','Dummy','--max-fps','30','--windowed',scene]
        with (output/'engine.log').open('xb') as f:
            process=subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT)
            write_new(output/'native-started.json',{'case_id':case,'owned_container_id':cid,
                      'docker_exec_PID':process.pid,'scene':scene,'at':time.time(),
                      'native_started_is_not_a_completed_passing_case':True})
            until=time.monotonic()+deadline
            while process.poll() is None:
                require(time.monotonic()<until,'Owned fixture deadline reached; preserve output')
                sample=resources();sample['case_id']=case
                with (RAM/'resource-observations.jsonl').open('ab') as observations:
                    observations.write((json.dumps(sample)+'\n').encode())
                time.sleep(2)
        result['exit_code']=process.returncode
        text=(output/'engine.log').read_text(errors='replace')
        result['native_clean']=not any(marker.lower() in text.lower() for marker in DIRTY)
        result['shutdown_resources_clean']=not any(marker.lower() in text.lower() for marker in DIRTY[-2:])
        path=output/('audio-regression.json' if case=='REST' else 'native-result.json')
        native=read(path) if path.is_file() else {};result['native']=native
        result['ok']=process.returncode==0 and native.get('ok') is True and result['native_clean'] and result['shutdown_resources_clean']
        if rows is not None:
            result.update(observations=len(native.get('observations',[])),screenshots=len(list(output.glob('*.png'))),
                          display_driver=native.get('display_driver'),adapter=native.get('adapter'))
            result['ok']=result['ok'] and result['observations']==rows and result['screenshots']==png and result['display_driver'] not in (None,'headless')
        result['output_bytes']=sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
        require(result['output_bytes']<=16*1024**2,'Per-case original output limit 16 MiB crossed')
    except Exception as exc:
        result.update(ok=False,error=type(exc).__name__,detail=str(exc),failed_raw_preserved=True)
    finally:
        if cid:
            info=inspect_owned(cid);result['oom_killed']=info['State']['OOMKilled']
            stop_remove_owned(cid);result['owned_container_removed']=True
        if process is not None and process.poll() is None:
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)
        result['source_inputs_unchanged']=tree(SOURCE)==read(E/'inputs.json')
        result['ok']=result['ok'] and result.get('owned_container_removed',False) and not result.get('oom_killed',True) and result['source_inputs_unchanged']
        require(resources()['owned_tmpfs_output_bytes']+len(json.dumps(result).encode())<=OUTPUT_BUDGET,'Aggregate output guard before case metadata write')
        write_new(output/'result.json',result)
    return result


def run(args):
    host();p=frozen(args)
    with coordination():
        predecessor_closed();queue_gate(True)
        require(os.environ.get('PR13_FIXTURE_LIFECYCLE_SYSTEMD_UNIT')==OWNER,'Exact root-dispatched lease env required')
        state=unit_state(OWNER)
        require(state['authoritative'] and state['MainPID']==os.getpid() and state['ActiveState']=='active','Exact live systemd MainPID must be this driver')
        require(re.fullmatch('[0-9a-f]{32}',state.get('InvocationID','')) and state['InvocationID']!='0'*32,
                'Actual live systemd invocation ID must be captured before native work')
        require(not (E/'run-started.json').exists() and not (E/'run-result.json').exists() and not RAM.exists(),'Never retry an uncertain/ended attempt')
        active_bind_guard([SOURCE,RAM]);resources(start=True)
        require(json.loads(docker('image','inspect',IMAGE).stdout)[0]['Id']==IMAGE,'Frozen existing renderer image required; never pull/build')
        write_new(E/'run-started.json',{'attempt':ATTEMPT,'owner':OWNER,'at':time.time(),'MainPID':os.getpid(),
                  'boot_id':current_boot(),'invocation_id':state['InvocationID'],'live_systemd_state_observed':state,
                  'inputs_sha256':sha(E/'inputs.json'),'preregistration_sha256':sha(E/'preregistration.json'),
                  'startup_identity_uncertain_means_observe_only':True})
        # A dedicated owned kernel quota bounds evidence even between samples.
        # Failed output mounts are retained for root/G recovery, never retried.
        RAM.mkdir(mode=0o777)
        cmd(['sudo','-n','mount','-t','tmpfs','-o','size=67108864,mode=0777,nosuid,nodev',OWNER,RAM])
        write_new(E/'output-tmpfs.json',output_mount())
    # Exact live pr13-cap-* lease and the root-owned pool hold protect native work
    # after releasing the short shared coordination lock. No auto lease dispatch.
    cases=[];result={'ok':False,'attempt':ATTEMPT,'release_sha':args.release_sha,'Godot_only':True,
                    'NET_executed':False,'numeric_or_statistical_generation_executed':False,'MAIN_accepted':False}
    try:
        health()
        for case,scene,deadline,rows,png in CASES:
            with coordination():
                require(read(HOLD).get('owner')==OWNER,'Lifecycle own hold changed during native sequence')
                frozen(args)
            r=one_case(case,scene,deadline,rows,png);cases.append(r)
            if not r['ok']:raise RuntimeError('Fixture native/display/shutdown gate failed: '+case)
        frozen(args);health();result['ok']=len(cases)==4
    except Exception as exc:result.update(error=type(exc).__name__,detail=str(exc),failed_all_raw_preserved=True)
    finally:
        native_started=[case for case,_,_,_,_ in CASES if (RAM/case/'native-started.json').is_file()]
        result.update(completed_case_results_count=len(cases),native_started_case_count=len(native_started),
                      run_started_sha256=sha(E/'run-started.json'),
                      native_started_cases=native_started,cases=cases,expected_cases=4,
                      expected_element_rows=54,expected_element_PNG=3,
                      original_failed_sources_preserved=old_sources(p['failed_inputs_sha256'])==read(E/'old-failed-preservation-before.json'),
                      complete_all_source_inputs_unchanged=tree(SOURCE)==read(E/'inputs.json'),
                      tmpfs_output_bytes=sum(x.stat().st_size for x in RAM.rglob('*') if x.is_file()),
                      raw_on_owned_tmpfs_retained=True,G_backup_verified=False,pool_hold_release_owned_by_root=True,
                      whole_task_accepted=False,full_EXPERIMENT_accepted=False,LIVE_accepted=False)
        result['ok']=result['ok'] and result['original_failed_sources_preserved'] and result['complete_all_source_inputs_unchanged']
        require(result['tmpfs_output_bytes']<=OUTPUT_BUDGET,'Aggregate original output budget before final persistence')
        resources(disk_reserve=METADATA_RESERVE)
        write_new(E/'old-failed-preservation-after.json',old_sources(p['failed_inputs_sha256']))
        write_new(E/'run-result.json',result)
    return result


def status(args):
    host()
    started=read(E/'run-started.json') if (E/'run-started.json').exists() else None
    state=unit_state(OWNER) if started else None
    return {'ok':True,'attempt':ATTEMPT,'prepared':(E/'preregistration.json').is_file(),'started':started,'systemd':state,
            'result':read(E/'run-result.json') if (E/'run-result.json').exists() else None,
            'uncertain_observe_only':bool(started and not state['authoritative']),
            'redispatch_permitted':False,'owned_tmpfs_exists':RAM.exists(),'MAIN_accepted':False}


def prepare_delivery(args):
    host();p=frozen(args);started=read(E/'run-started.json');result=read(E/'run-result.json')
    require(result.get('run_started_sha256')==sha(E/'run-started.json') and started.get('owner')==OWNER
            and started.get('live_systemd_state_observed',{}).get('MainPID')==started.get('MainPID'),
            'Original exact live runner/invocation startup byte binding required')
    if result['ok']:
        terminal=exact_terminal(OWNER,{'at':started['at'],'timestamp_role':'observed-live',
                  'boot_id':started['boot_id'],'invocation_id':started['invocation_id'],'startup_sha256':sha(E/'run-started.json')})
    else:
        state=unit_state(OWNER)
        require(state.get('complete_observation') is True and state.get('MainPID')==0
                and state.get('ActiveState') not in ('active','activating','deactivating','reloading'),
                'Failed/uncertain unit must be authoritatively stopped before preserving its delivery')
        no_owned_containers(OWNER);terminal={'authority':'stopped-failed-output-preservation-only','current_state':state}
    active_bind_guard([W,RAM])
    terminal_path=E/'terminal-proof.original.json'
    binding={'kind':'fixture-lifecycle-original-terminal-authority','attempt':ATTEMPT,'unit':OWNER,
             'startup_sha256':sha(E/'run-started.json'),'passed':result['ok'],'observed_authority':terminal}
    if terminal_path.exists():
        prior=read(terminal_path)
        require(all(prior.get(k)==binding[k] for k in ('kind','attempt','unit','startup_sha256','passed')),
                'Original lifecycle terminal binding changed; current authority was independently rechecked')
    else:write_new(terminal_path,binding)
    # Delivery preserves failed outputs too. Failed native results never become
    # a passing lifecycle result or qualify for cleanup-passed.
    files=[]
    for directory,prefix in ((E,'metadata'),(SOURCE,'source'),(RAM,'outputs')):
        for member in sorted(directory.rglob('*')):
            if member.is_file() and member.name not in ('delivery-manifest.json','local-backup-receipt.json','local-storage-cleanup.json'):
                require(not member.is_symlink(),'Archive member symlink rejected')
                files.append({'source':str(member),'path':prefix+'/'+member.relative_to(directory).as_posix(),
                              'bytes':member.stat().st_size,'sha256':sha(member)})
    value={'kind':'b08-fixture-lifecycle-r1','attempt':ATTEMPT,'release_sha':args.release_sha,
           'inputs_sha256':sha(E/'inputs.json'),'original_native_witness_source_sha':WITNESS_SOURCE,
           'native_lifecycle_passed':result['ok'],'terminal_proof_original_sha256':sha(terminal_path),'files':files,'MAIN_accepted':False}
    target=E/'delivery-manifest.json'
    if target.exists():require(read(target)==value,'Immutable original delivery members changed')
    else:write_new(target,value)
    return {'ok':True,'manifest':str(target),'manifest_sha256':sha(target),'members':len(files),
            'bytes':sum(x['bytes'] for x in files),'native_lifecycle_passed':result['ok'],'cloud_archive_created':False}


def cleanup_passed(args):
    host();require(read(E/'run-result.json')['ok'] is True,'Failed lifecycle prefix cannot be cleaned')
    delivery=prepare_delivery(args);receipt=read(args.backup_receipt)
    require(receipt.get('ok') is True and receipt.get('attempt')==ATTEMPT and receipt.get('release_sha')==args.release_sha
            and receipt.get('manifest_sha256')==delivery['manifest_sha256']
            and receipt.get('members_verified')==receipt.get('members')==delivery['members']
            and all(receipt.get(k) is True for k in ('archive_gzip_CRC_verified','all_original_members_sha256_verified','fixture_lifecycle_outputs_verified'))
            and str(receipt.get('local_archive','')).replace('\\','/').lower().startswith('g:/')
            and receipt.get('MAIN_accepted') is False,'Complete original local G lifecycle archive proof required')
    require(RAM.resolve()==Path('/dev/shm')/('pr13-'+ATTEMPT) and not RAM.is_symlink(),'Exact owned output cleanup path required')
    active_bind_guard([RAM]);before=old_sources(FAILED_INPUTS_SHA);health()
    saved=E/'local-backup-receipt.json'
    if saved.exists():require(sha(saved)==sha(args.backup_receipt),'Immutable original G receipt differs')
    else:shutil.copyfile(args.backup_receipt,saved)
    mount=output_mount()
    require(mount==read(E/'output-tmpfs.json'),'Exact owned tmpfs mount identity changed')
    removed=sum(p.stat().st_size for p in RAM.rglob('*') if p.is_file())
    cmd(['sudo','-n','umount',RAM])  # Only passed/G-verified exact owned new tmpfs.
    RAM.rmdir()  # The underlying fresh owned mountpoint has no source/raw files.
    require(old_sources(FAILED_INPUTS_SHA)==before,'Cleanup changed old failed originals');health()
    value={'ok':True,'attempt':ATTEMPT,'passed_owned_tmpfs_removed':True,'bytes_removed':removed,
           'manifest_sha256':delivery['manifest_sha256'],'local_G_archive_sha256':receipt['sha256'],
           'local_G_archive_bytes':receipt['bytes'],'new_source_and_all_old_failed_originals_retained':True,
           'pool_hold_not_modified':True,'pool_hold_release_owned_by_root':True,'MAIN_accepted':False}
    write_new(E/'local-storage-cleanup.json',value);return value


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('prepare','prepare-run','run','status','prepare-delivery','cleanup-passed'))
    p.add_argument('--release-sha',required=True);p.add_argument('--failed-inputs-sha256',default=FAILED_INPUTS_SHA)
    p.add_argument('--backup-receipt',type=Path);a=p.parse_args()
    require(re.fullmatch('[0-9a-f]{40}',a.release_sha),'Explicit final published --release-sha required')
    if a.phase=='cleanup-passed':require(a.backup_receipt,'Original verified G receipt required')
    try:
        if a.phase=='prepare-run':
            # Explicit root-selected single systemd command: prepare first, then
            # run in the same exact MainPID lease. This is never self-dispatch.
            prepare(a);result=run(a)
        elif a.phase in ('prepare','prepare-delivery','cleanup-passed'):
            if a.phase=='prepare':result=prepare(a)
            else:
                host()
                with coordination():result={'prepare-delivery':prepare_delivery,'cleanup-passed':cleanup_passed}[a.phase](a)
        else:result={'run':run,'status':status}[a.phase](a)
    except Deferred as exc:
        result={'ok':True,'launch_deferred':True,'no_startup_created':not (E/'run-started.json').exists(),
                'reason':str(exc),'automatic_dispatch_or_retry':False,'MAIN_accepted':False}
    print(json.dumps(result,allow_nan=False))
    return 0 if result.get('ok') is True else 1


if __name__=='__main__':raise SystemExit(main())
