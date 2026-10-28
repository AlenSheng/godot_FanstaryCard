#!/usr/bin/env python3
"""Tencent-only, bounded readonly projection statistics runner. Never launches native units.

Copy this runner beside analysis.py (tools/pr13_cap_full_statistics.py).
prepare is metadata/hash only; run executes the preregistered full statistics in Docker.
All startup resources are deferred without killing other PR13 jobs. A failed attempt
is preserved and requires a new attempt name. Root dispatches this tool explicitly.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time

ROOT = Path('/home/ubuntu/pr13-acceptance-20261009')
GIT = Path('/opt/fantasycard-github')
IMAGE = 'sha256:6ea92944e8779a5bb6e5c40faca53a40a1b02b5a0dcd47fff0815ba9cfbded1f'
MONITOR = '2734235cbfa1f9d8f1352cd9a925251f6356021d86ede341f80c6196e799149a'
OWNER = 'pr13-cap-full-statistics'
MEMORY_FLOOR = 500000000
CONTAINER_MEMORY = 950 * 1024 ** 2
DISK_FLOOR = .15
OUTPUT_LIMIT = 64 * 1024 ** 2
DIAGNOSTIC_LIMIT = 24 * 1024 ** 2
DEADLINE = 1800


def require(condition, message):
    if not condition: raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(65536), b''): h.update(b)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_bytes())


def write_new(path, value):
    p = Path(path); require(not p.exists(), 'Immutable attempt file already exists: ' + str(p))
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as f: f.write((json.dumps(value, indent=2, allow_nan=False) + '\n').encode())


def command(args, timeout=30, check=True):
    p = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=timeout)
    require(not check or p.returncode == 0, 'Command failed: ' + str(args[0]) + ' rc=' + str(p.returncode) + ' ' + p.stderr[-2000:])
    return p


def analysis():
    p = Path(__file__).with_name('analysis.py')
    require(p.is_file(), 'Frozen analysis.py must be copied beside runner')
    spec = importlib.util.spec_from_file_location('pr13_cap_full_statistics_analysis', p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m, p


def host_guard():
    require(platform.system() == 'Linux' and ROOT.is_dir() and GIT.is_dir(), 'Tencent acceptance host/root required')
    require(Path('/proc/meminfo').is_file() and Path('/dev/shm').is_dir(), 'Linux bounded resources required')


def exact(path, parent):
    p = Path(path).resolve(); require(p.is_relative_to(Path(parent).resolve()) and p != Path(parent).resolve(), 'Owned path escaped')
    return p


def paths(attempt):
    require(re.fullmatch(r'cap-full-statistics-r[1-9][0-9]*-[0-9]{8}', attempt), 'Explicit unique statistics attempt required')
    return exact(ROOT/'evidence'/attempt, ROOT/'evidence'), exact(ROOT/'work'/attempt, ROOT/'work'), Path('/dev/shm')/('pr13-'+attempt)


def resources(extra_memory=0, extra_disk=0):
    available = next(int(x.split()[1]) * 1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
    disk = shutil.disk_usage(ROOT); shm = shutil.disk_usage('/dev/shm')
    return {'memory_available_bytes': available, 'root_free_bytes': disk.free, 'root_total_bytes': disk.total,
            'root_free_ratio_after_reserve': (disk.free-extra_disk)/disk.total, 'shm_free_bytes': shm.free,
            'ok': available >= MEMORY_FLOOR+extra_memory and (disk.free-extra_disk)/disk.total >= DISK_FLOOR}


def active_binds(targets):
    p = command(['docker', 'ps', '-q', '--no-trunc'])
    for cid in p.stdout.split():
        require(re.fullmatch('[0-9a-f]{64}', cid), 'Authoritative full container ID required')
        info = json.loads(command(['docker', 'inspect', cid]).stdout)[0]
        require(info.get('Id') == cid and info.get('State', {}).get('Running') is True, 'Docker running identity uncertain')
        for mount in info.get('Mounts', []):
            if mount.get('Type') != 'bind': continue
            if cid == MONITOR and mount.get('Source') == '/' and mount.get('RW') is False: continue
            source = Path(mount.get('Source', '')).resolve()
            require(not any(source == t or source.is_relative_to(t) or t.is_relative_to(source) for t in targets),
                    'Active bind touches owned statistics input/work: ' + cid)


def systemd_status(name):
    p = command(['systemctl', 'show', name, '--property=Id,LoadState,MainPID,ActiveState,ExecMainStatus'], check=False)
    fields = dict(x.split('=', 1) for x in p.stdout.splitlines() if '=' in x)
    expected = name if name.endswith('.service') else name+'.service'
    authoritative = (p.returncode == 0 and fields.get('Id') == expected and fields.get('LoadState') == 'loaded'
                     and all(x in fields for x in ('MainPID', 'ActiveState', 'ExecMainStatus')))
    if authoritative:
        try: fields['MainPID'] = int(fields['MainPID']); fields['ExecMainStatus'] = int(fields['ExecMainStatus'])
        except ValueError: authoritative = False
    return {'authoritative': authoritative, 'returncode': p.returncode, **fields}


def git_bytes(revision, filename):
    require(re.fullmatch('[0-9a-f]{40}', revision) and not filename.startswith('/') and '..' not in Path(filename).parts, 'Unsafe frozen Git member')
    p = subprocess.run(['git', '-C', str(GIT), 'show', revision+':'+filename], capture_output=True, timeout=30)
    require(p.returncode == 0, 'Frozen Git source member unavailable: ' + filename)
    return p.stdout


def source_proof(a, gate):
    inp = gate['inputs']; require(command(['git','-C',GIT,'rev-parse',a.MIXED+'^']).stdout.strip() == a.BUSINESS,
                                'Mixed Git parent is not original business source')
    checked = []
    for path, mixed_hash in sorted(inp['source_hashes'].items()):
        original_hash = inp['original_source_hashes'][path]
        require(hashlib.sha256(git_bytes(a.MIXED, path)).hexdigest() == mixed_hash
                and hashlib.sha256(git_bytes(a.BUSINESS, path)).hexdigest() == original_hash,
                'Actual 372 original/mixed Git member bytes differ: ' + path)
        if path in a.OVERRIDES:
            require(hashlib.sha256(git_bytes(a.INSTRUMENTATION, path)).hexdigest() == mixed_hash, 'Instrumentation override differs')
        checked.append({'path': path, 'original_sha256': original_hash, 'mixed_sha256': mixed_hash})
    return {'ok': True, 'source_files_verified': 372, 'original_business_files_unchanged': 370,
            'exact_two_overrides_verified': sorted(a.OVERRIDES), 'source_sha': a.MIXED,
            'business_source_sha': a.BUSINESS, 'instrumentation_source_sha': a.INSTRUMENTATION, 'files': checked}


def tree_ledger(directory):
    root = Path(directory).resolve(); values = []
    for p in sorted(root.rglob('*')):
        require(not p.is_symlink(), 'Statistics projection/tool symlink rejected')
        if p.is_file(): values.append({'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)})
    return values


def prepare(args):
    host_guard(); a, tool = analysis(); evidence, work, ram = paths(args.attempt)
    require(not evidence.exists() and not work.exists() and not ram.exists(), 'Fresh immutable attempt required')
    projection = exact(args.projection, ROOT/'work')
    require(sha(projection/'dataset.json') == args.dataset_sha256, 'Explicit projected dataset byte anchor differs')
    require(re.fullmatch('[0-9a-f]{40}', args.analysis_source_sha or ''), 'Published/private frozen analysis Git source required')
    require(hashlib.sha256(git_bytes(args.analysis_source_sha, 'tools/pr13_cap_full_statistics.py')).hexdigest() == sha(tool)
            and hashlib.sha256(git_bytes(args.analysis_source_sha, 'tools/cloud/pr13/cap_full_statistics.py')).hexdigest() == sha(__file__),
            'Actual executed analysis/runner Git bytes differ')
    dataset, units, gate = a.validate_projection(projection, args.prereg_sha256, args.formal_plan_sha256)
    status = resources(CONTAINER_MEMORY+OUTPUT_LIMIT, OUTPUT_LIMIT+DIAGNOSTIC_LIMIT+16*1024**2)
    if not status['ok'] or status['shm_free_bytes'] < OUTPUT_LIMIT+DIAGNOSTIC_LIMIT:
        return {'ok': True, 'prepare_deferred_resources': True, 'no_startup_created': True, 'resources': status}
    active_binds([projection, work, ram])
    actual_sources = source_proof(a, gate)
    image = json.loads(command(['docker','image','inspect',IMAGE]).stdout)[0]
    require(image.get('Id') == IMAGE, 'Exact frozen image required; no pulls')
    ledger = tree_ledger(projection)
    require(sum(x['bytes'] for x in ledger) <= 256*1024**2, 'Full encounter-only projection must stay within 256 MiB')
    evidence.mkdir(parents=True); work.mkdir(parents=True)
    write_new(evidence/'source-proof.json', actual_sources)
    inputs = {'schema_version': 1, 'attempt': args.attempt, 'projection_path': str(projection),
              'dataset_sha256': args.dataset_sha256, 'prereg_sha256': args.prereg_sha256,
              'formal_plan_sha256': args.formal_plan_sha256, 'analysis_source_sha': args.analysis_source_sha,
              'analysis_sha256': sha(tool), 'runner_sha256': sha(__file__), 'image_sha': IMAGE,
              'projection_ledger': ledger, 'source_proof_sha256': sha(evidence/'source-proof.json'),
              'source_gate_refs': dataset['source_gate'], 'logical_units': len(units), 'encounters': 720000,
              'pairs': 360000, 'memory_floor_bytes': MEMORY_FLOOR, 'container_memory_bytes': CONTAINER_MEMORY,
              'root_free_ratio_floor': DISK_FLOOR, 'output_limit_bytes': OUTPUT_LIMIT,
              'deadline_seconds': DEADLINE, 'MAIN_accepted': False}
    write_new(evidence/'inputs.json', inputs)
    return {'ok': True, 'prepared': True, 'inputs_sha256': sha(evidence/'inputs.json'), 'evidence': str(evidence), 'work': str(work)}


def inspect_owned(cid, attempt):
    info = json.loads(command(['docker','inspect',cid]).stdout)[0]
    require(info.get('Id') == cid and info.get('Config',{}).get('Labels',{}).get('pr13.owner') == OWNER
            and info['Config']['Labels'].get('pr13.attempt') == attempt, 'Refuse foreign container action')
    return info


def check_inputs(inputs, tool, evidence):
    require(sha(tool) == inputs['analysis_sha256'] and sha(__file__) == inputs['runner_sha256']
            and sha(evidence/'source-proof.json') == inputs['source_proof_sha256'], 'Executed tool/source proof changed')
    require(tree_ledger(inputs['projection_path']) == inputs['projection_ledger'], 'Readonly projection original bytes changed')


def run(args):
    host_guard(); a, tool = analysis(); evidence, work, ram = paths(args.attempt)
    require((evidence/'inputs.json').is_file() and not (evidence/'startup.json').exists()
            and not (evidence/'result.json').exists() and not ram.exists(), 'Prepared fresh attempt required; never redispatch uncertain startup')
    inputs = read(evidence/'inputs.json'); projection = Path(inputs['projection_path'])
    check_inputs(inputs, tool, evidence)
    status = resources(CONTAINER_MEMORY+OUTPUT_LIMIT, OUTPUT_LIMIT+DIAGNOSTIC_LIMIT+16*1024**2)
    if not status['ok'] or status['shm_free_bytes'] < OUTPUT_LIMIT+DIAGNOSTIC_LIMIT:
        return {'ok': True, 'run_deferred_resources': True, 'no_startup_created': True, 'resources': status}
    active_binds([projection, work, ram]); ram.mkdir(mode=0o777); os.chmod(ram,0o777)
    container = OWNER+'-'+args.attempt; cidfile = work/'container.cid'
    write_new(evidence/'startup.json', {'attempt':args.attempt,'container_name':container,'systemd_unit':args.systemd_unit,
                                      'inputs_sha256':sha(evidence/'inputs.json'),'dispatch_state':'startup_written_never_redispatch'})
    logs=[]; cid=None; stop_reason=None; error=None; start=time.monotonic()
    try:
        command(['docker','create','--name',container,'--cidfile',cidfile,'--label','pr13.owner='+OWNER,
                 '--label','pr13.attempt='+args.attempt,'--network','none','--cpus','1','--memory','950m',
                 '--memory-swap','950m','--pids-limit','256','--read-only','--user','1000:1000',
                 '--tmpfs','/tmp:rw,nosuid,nodev,size=16777216','-e','PYTHONDONTWRITEBYTECODE=1',
                 '-e','PR13_CAP_STATISTICS_CLOUD=tencent-readonly-v1','-v',str(tool.parent)+':/work:ro',
                 '-v',str(projection)+':/inputs:ro','-v',str(ram)+':/ram',IMAGE,
                 'python3','/work/analysis.py','--input','/inputs','--output','/ram/statistics.json',
                 '--prereg-sha256',inputs['prereg_sha256'],'--formal-plan-sha256',inputs['formal_plan_sha256']],timeout=60)
        cid=cidfile.read_text().strip(); require(re.fullmatch('[0-9a-f]{64}',cid), 'Full owned CID required')
        inspect_owned(cid,args.attempt); command(['docker','start',cid],timeout=30)
        while True:
            info=inspect_owned(cid,args.attempt)
            if not info['State']['Running']: break
            r=resources(); r['elapsed_seconds']=round(time.monotonic()-start,3); logs.append(r)
            size=sum(p.stat().st_size for p in ram.rglob('*') if p.is_file())
            if not r['ok'] or size>OUTPUT_LIMIT or time.monotonic()-start>DEADLINE:
                stop_reason='resource_floor_or_owned_output_budget_or_deadline'
                command(['docker','stop','--time','10',cid],timeout=30)
                break
            time.sleep(5)
        info=inspect_owned(cid,args.attempt); require(not info['State']['Running'], 'Owned container termination uncertain')
        process=command(['docker','logs',cid],check=False)
        diagnostics=(process.stdout+process.stderr).encode()
        require(len(diagnostics)<=DIAGNOSTIC_LIMIT, 'Diagnostics exceed reserved 24 MiB; preserve container/scratch')
        state=info['State']; check_inputs(inputs,tool,evidence)
        success=not stop_reason and state.get('ExitCode')==0 and state.get('OOMKilled') is False
        report=read(ram/'statistics.json') if success else None
        if success:
            require(report.get('full_data_complete') is True and report.get('logical_units')==360
                    and report.get('encounters')==720000 and report.get('paired_encounters')==360000
                    and report.get('statistical_computation_complete') is True
                    and report.get('MAIN_accepted') is False, 'Full statistics result contract differs')
        required=sum(p.stat().st_size for p in ram.rglob('*') if p.is_file())+len(diagnostics)+1024**2
        require(required<=OUTPUT_LIMIT+DIAGNOSTIC_LIMIT+1024**2 and resources(extra_disk=required)['ok'],
                'Root disk/memory floor rejected final persistence; preserve scratch/container')
        for p in ram.iterdir():
            require(p.is_file() and not p.is_symlink(), 'Only owned result files allowed'); shutil.copyfile(p,work/p.name)
        (work/'container.log').write_bytes(diagnostics)
        write_new(evidence/'resource-observations.json',logs)
        result={'ok':success,'attempt':args.attempt,'exit_code':state.get('ExitCode'),'oom_killed':state.get('OOMKilled'),
                'stop_reason':stop_reason,'owned_container_id':cid,'readonly_projection_and_tools_unchanged':True,
                'source_files_verified':372,'inputs_sha256':sha(evidence/'inputs.json'),
                'statistics_sha256':sha(work/'statistics.json') if success else None,
                'gap_count':len(report['gaps']) if success else None,
                'all_registered_case_predicates_observed':report['all_registered_case_predicates_observed'] if success else False,
                'full_data_complete':success,'required_cases_accepted':False,'MAIN_accepted':False,
                'diagnostic_bytes':len(diagnostics),'scratch_retained_for_G':str(ram)}
        # Only remove an authoritative stopped container owned by this attempt.
        require(not inspect_owned(cid,args.attempt)['State']['Running'],'Owned stop must precede removal')
        command(['docker','rm',cid]); result['owned_container_removed']=True
        write_new(evidence/'result.json',result); return result
    except Exception as exc:
        error=str(exc)
        # Never fabricate success or remove uncertain/foreign container/scratch.
        if cid:
            try:
                if inspect_owned(cid,args.attempt)['State']['Running']: command(['docker','stop','--time','10',cid],timeout=30)
            except Exception: pass
        if not (evidence/'attention.json').exists():
            write_new(evidence/'attention.json',{'ok':False,'attempt':args.attempt,'error':error,'owned_container_id':cid,
                                               'preserve_all_scratch':True,'never_redispatch':True,'MAIN_accepted':False})
        raise


def status(args):
    host_guard(); evidence,work,ram=paths(args.attempt)
    startup=read(evidence/'startup.json') if (evidence/'startup.json').exists() else None
    unit=systemd_status(startup['systemd_unit']) if startup else None
    return {'ok':True,'attempt':args.attempt,'prepared':(evidence/'inputs.json').is_file(),'startup':startup,
            'systemd':unit,'result':read(evidence/'result.json') if (evidence/'result.json').exists() else None,
            'attention':read(evidence/'attention.json') if (evidence/'attention.json').exists() else None,
            'startup_uncertain':bool(startup and (not unit or not unit['authoritative'])),
            'redispatch_permitted':False,'scratch_exists':ram.exists(),'MAIN_accepted':False}


def prepare_delivery(args):
    host_guard(); evidence,work,ram=paths(args.attempt)
    s=status(args); unit=s['systemd']; result=s['result']
    require(unit and unit['authoritative'] and unit['MainPID']==0 and unit['ExecMainStatus']==0
            and unit['ActiveState'] in ('inactive','failed') and result and result.get('ok') is True,
            'Authoritative final successful systemd/native result required before delivery')
    active_binds([work,ram]); files=[]
    for base,prefix in ((evidence,'metadata'),(work,'outputs')):
        for p in sorted(base.rglob('*')):
            if p.is_file() and p.name not in ('delivery-manifest.json','local-backup-receipt.json','local-storage-cleanup.json'):
                require(not p.is_symlink(),'Owned member symlink rejected')
                files.append({'source':str(p),'path':prefix+'/'+p.relative_to(base).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    manifest={'schema_version':1,'kind':OWNER,'attempt':args.attempt,'files':files,
              'source_files_verified':372,'logical_units':360,'encounters':720000,'pairs':360000,
              'MAIN_accepted':False,'full_formal_pending':True}
    path=evidence/'delivery-manifest.json'
    if path.exists():require(read(path)==manifest,'Immutable delivery members changed')
    else:write_new(path,manifest)
    return {'ok':True,'manifest':str(path),'manifest_sha256':sha(path),'members':len(files),'bytes':sum(x['bytes'] for x in files)}


def cleanup(args):
    host_guard(); evidence,work,ram=paths(args.attempt); delivery=prepare_delivery(args)
    receipt=read(args.receipt_file)
    require(receipt.get('ok') is True and receipt.get('attempt')==args.attempt
            and receipt.get('manifest_sha256')==delivery['manifest_sha256']
            and receipt.get('members')==receipt.get('members_verified')==delivery['members']
            and all(receipt.get(k) is True for k in ('archive_gzip_CRC_verified','all_original_members_sha256_verified',
                                                   'full_statistics_original_bytes_verified'))
            and str(receipt.get('local_archive','')).replace('\\','/').lower().startswith('g:/')
            and receipt.get('MAIN_accepted') is False,'Complete local G statistics proof required before owned cleanup')
    active_binds([work,ram])
    if not (evidence/'local-backup-receipt.json').exists():shutil.copyfile(args.receipt_file,evidence/'local-backup-receipt.json')
    else:require(sha(args.receipt_file)==sha(evidence/'local-backup-receipt.json'),'Immutable original G receipt changed')
    exact(work,ROOT/'work'); exact(ram,Path('/dev/shm'))
    removed=sum(p.stat().st_size for base in (work,ram) if base.exists() for p in base.rglob('*') if p.is_file())
    if work.exists():shutil.rmtree(work)
    if ram.exists():shutil.rmtree(ram)
    result={'ok':True,'attempt':args.attempt,'owned_work_and_scratch_removed':True,'bytes_removed':removed,
            'input_projection_and_original_sources_retained':True,'manifest_sha256':delivery['manifest_sha256'],
            'local_G_archive_sha256':receipt['sha256'],'MAIN_accepted':False}
    write_new(evidence/'local-storage-cleanup.json',result); return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('prepare','run','status','prepare-delivery','cleanup'))
    p.add_argument('--attempt',required=True);p.add_argument('--projection');p.add_argument('--dataset-sha256')
    p.add_argument('--prereg-sha256');p.add_argument('--formal-plan-sha256');p.add_argument('--analysis-source-sha')
    p.add_argument('--systemd-unit');p.add_argument('--receipt-file');a=p.parse_args()
    if a.phase=='prepare':require(all((a.projection,a.dataset_sha256,a.prereg_sha256,a.formal_plan_sha256,a.analysis_source_sha)),'Five explicit input/source anchors required')
    if a.phase=='run':require(a.systemd_unit in ('pr13-'+a.attempt, 'pr13-'+a.attempt+'.service'),'Exact owned systemd unit/attempt identity required')
    if a.phase=='cleanup':require(a.receipt_file,'Original G receipt file required')
    print(json.dumps({'prepare':prepare,'run':run,'status':status,'prepare-delivery':prepare_delivery,'cleanup':cleanup}[a.phase](a),allow_nan=False))


if __name__=='__main__':main()
