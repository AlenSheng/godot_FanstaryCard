"""Build the separate 132-task runtime register from explicit evidence records."""
import argparse
from collections import Counter
import hashlib
import json
import re
from pathlib import Path
import subprocess
import time
try:
    from .pr13_review_policy import execution_state, HUMAN_TASKS
except ImportError:
    from pr13_review_policy import execution_state, HUMAN_TASKS

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def plan_identity(path, metadata, root=ROOT):
    """Retain raw hashes; permit only Git-proven LF/CRLF equivalents."""
    raw=path.read_bytes();canonical=raw.replace(b'\r\n',b'\n')
    actual=hashlib.sha256(raw).hexdigest();recorded=metadata.get('plan_sha256')
    identity=dict(recorded_sha256=recorded,current_bytes_sha256=actual,
                  canonical_lf_sha256=hashlib.sha256(canonical).hexdigest(),line_endings_equivalent=False)
    if recorded==actual:return identity
    permitted={hashlib.sha256(canonical).hexdigest(),hashlib.sha256(canonical.replace(b'\n',b'\r\n')).hexdigest()}
    source=metadata.get('source_sha','')
    if recorded not in permitted or not isinstance(source,str) or re.fullmatch(r'[0-9a-f]{40}',source) is None:
        raise ValueError('Case evidence uses a different acceptance plan')
    relative=path.resolve().relative_to(root.resolve()).as_posix()
    result=subprocess.run(['git','-C',str(root),'show',source+':'+relative],capture_output=True,timeout=15)
    if result.returncode or result.stdout.replace(b'\r\n',b'\n')!=canonical:
        raise ValueError('Acceptance plan newline equivalence is not proven by its executed Git source')
    source_canonical=result.stdout.replace(b'\r\n',b'\n')
    if recorded not in {hashlib.sha256(result.stdout).hexdigest(),hashlib.sha256(source_canonical).hexdigest(),
                        hashlib.sha256(source_canonical.replace(b'\n',b'\r\n')).hexdigest()}:
        raise ValueError('Executed acceptance plan byte hash differs')
    return dict(identity,line_endings_equivalent=True,verified_source_sha=source,
                verified_git_plan_sha256=hashlib.sha256(result.stdout).hexdigest())


def review_scope(path, root=ROOT):
    if path is None:return dict(in_scope=True, authority='original_plan')
    source=path.resolve()
    if not source.is_relative_to(root.resolve()):raise ValueError('Scope decision escaped the repository')
    decision=json.loads(source.read_text(encoding='utf8'))
    experience=decision.get('human_experience',{})
    if decision.get('authority')!='human' or experience.get('in_scope') is not False or experience.get('automated_combat_render_and_metrics_remain_required') is not True or experience.get('do_not_claim_human_tests_passed') is not True:
        raise ValueError('Explicit human-only exclusion with retained automated acceptance required')
    return dict(in_scope=False,authority='human',source=dict(path=source.relative_to(root).as_posix(),bytes=source.stat().st_size,sha256=digest(source)))


def missing_case_profiles(task, records):
    """A passed OFFLINE case does not discharge its real database/live layers."""
    return {r['case_id']:sorted(set(task['profiles'])-set(r.get('profiles_executed',[])))
            for r in records if r['status']=='Passed' and set(task['profiles'])-set(r.get('profiles_executed',[]))}


def apply_main_decisions(tasks, decisions, head, root=ROOT):
    if decisions.get('authority')!='MAIN' or decisions.get('stage')!='S6' or decisions.get('integration_source_sha')!=head:
        raise ValueError('Current explicit MAIN S6 decision record required')
    known={t['task_id']:t for t in tasks};seen=set()
    for decision in decisions.get('task_decisions',[]):
        task_id=decision['task_id']
        if task_id not in known or task_id in seen:raise ValueError('Unknown/duplicate MAIN task')
        seen.add(task_id);task=known[task_id]
        if decision.get('state')!='Accepted' or task['state']!='ReadyForAcceptance' or task['missing_cases'] or task['missing_case_profiles']:
            raise ValueError('MAIN acceptance requires every mandatory case and profile: '+task_id)
        for key in ('reason','evidence','rollback','runtime_review_sha'):
            if not decision.get(key):raise ValueError('Incomplete MAIN decision: '+key)
        if set(task.get('case_source_shas',{}).values())!={decision['runtime_review_sha']}:
            raise ValueError('MAIN runtime review differs from executed case sources')
        for item in decision['evidence']:
            path=(root/item['path']).resolve()
            if not path.is_relative_to(root.resolve()) or path.stat().st_size!=item['bytes'] or digest(path)!=item['sha256']:
                raise ValueError('MAIN evidence changed or escaped the workspace')
        task.update(state='Accepted',accepted_by='MAIN',main_decision=decision,next_action='本子项适用层已裁决；全范围门槛另行汇总。')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-reports',nargs='+',type=Path,required=True)
    parser.add_argument('--support',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--main-decisions',type=Path)
    parser.add_argument('--scope-decision',type=Path,help='Explicit current user scope decision; excludes human participation only')
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    plan=json.loads(PLAN.read_text(encoding='utf8'));support=json.loads(args.support.read_text(encoding='utf8'))
    human_scope=review_scope(args.scope_decision)
    expected={c['id']:c for p in plan['packages'] for s in p['subtasks'] for c in s['test_cases']}
    known={s['id'] for p in plan['packages'] for s in p['subtasks']};executed={};files={PLAN,args.support.resolve()};plan_sources=[]
    if args.scope_decision:files.add(args.scope_decision.resolve())
    for file in args.case_reports:
        files.add(file.resolve()); report=file.parent/'report.json'
        if not report.is_file():raise ValueError('Case source report missing: '+str(file))
        files.add(report.resolve());metadata=json.loads(report.read_text(encoding='utf8'))
        identity=plan_identity(PLAN,metadata)
        plan_sources.append(dict(report=str(report.resolve().relative_to(ROOT)),**identity))
        for line in file.read_text(encoding='utf8').splitlines():
            record=json.loads(line);case_id=record['case_id']
            if case_id not in expected or case_id in executed:raise ValueError('Unknown/duplicate case: '+case_id)
            if record.get('status') not in ('Passed','Failed') or record.get('executed') is not True:
                raise ValueError('Invalid case result: '+case_id)
            profiles=record.get('profiles_executed',metadata.get('profiles_executed',
                ['OFFLINE'] if metadata.get('scope')=='explicit offline cases only' else []))
            if not isinstance(profiles,list) or any(p not in ('OFFLINE','POSTGRES','LIVE','CAPACITY','EXPERIMENT','RENDER','AUDIT') for p in profiles):
                raise ValueError('Invalid explicit execution profiles: '+case_id)
            executed[case_id]=dict(record,profiles_executed=profiles,evidence=str(file.resolve().relative_to(ROOT)),
                                 source_sha=metadata.get('source_sha'),source=metadata.get('source'),acceptance_plan_identity=identity)
    supporting={};observations={}
    for item in support['evidence']:
        if set(item['tasks'])-known:raise ValueError('Unknown supporting task')
        item_files=[]
        for pattern in item['paths']:
            matches=sorted(ROOT.glob(pattern))
            if not matches:raise ValueError('Supporting evidence missing: '+pattern)
            for file in matches:
                if not file.is_file():continue
                resolved=file.resolve()
                resolved.relative_to(ROOT)  # Never include outside files or secrets by accident.
                files.add(resolved);item_files.append(str(resolved.relative_to(ROOT)).replace('\\','/'))
        for task in item['tasks']:supporting.setdefault(task,[]).append(dict(id=item['id'],scope=item['scope'],paths=item_files))
    for item in support.get('observations',[]):
        if item['task_id'] not in known:raise ValueError('Unknown observation task')
        observations[item['task_id']]=item
    tasks=[];cases=[]
    for package in plan['packages']:
        for task in package['subtasks']:
            task_cases=[]
            for case in task['test_cases']:
                record=executed.get(case['id'],dict(case_id=case['id'],executed=False,status='NotExecuted',actual=None,evidence=None))
                record=dict(record,setup=case['setup_and_injection'],expected=case['expected'],task_id=task['id'])
                task_cases.append(record);cases.append(record)
            observation=observations.get(task['id'],{})
            statuses=[r['status'] for r in task_cases]
            missing_profiles=missing_case_profiles(task,task_cases)
            state=execution_state(task_cases, task['profiles'], human_required=task['id'] in HUMAN_TASKS,
                                  human_evidence=support.get('human_experience_evidence'),human_in_scope=human_scope['in_scope'])
            if state=='Queued' and supporting.get(task['id']):state='Partial'
            if observation.get('state') in ('Blocked','InProgress','Failed','Deferred','Partial'):state=observation['state']
            tasks.append(dict(task_id=task['id'],title=task['title'],package_id=package['id'],state=state,
                accepted_by=None,owner='MAIN',case_counts=dict(Counter(statuses)),
                profiles=task['profiles'],gates=task['gate_refs'],dependencies=task['requires_before_integration'],
                evidence=supporting.get(task['id'],[]),case_ids=[c['id'] for c in task['test_cases']],
                missing_cases=[r['case_id'] for r in task_cases if r['status']!='Passed'],
                missing_case_profiles=missing_profiles,
                case_source_shas={r['case_id']:r.get('source_sha') for r in task_cases if r['status']=='Passed'},
                pass_criteria=task['pass_criteria'],next_action=observation.get('next_action',
                    '复核逐用例证据、依赖与当前CI后由MAIN裁决。' if state=='ReadyForAcceptance' else task['implementation_steps']),
                observation=observation))
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if args.main_decisions:
        files.add(args.main_decisions.resolve())
        apply_main_decisions(tasks,json.loads(args.main_decisions.read_text(encoding='utf8')),head)
    gates=[dict(gate_id=g['id'],name=g['name'],state='NotAccepted',pass_criteria=g['pass'],
                unfinished=[t['task_id'] for t in tasks if t['task_id'] in g['tasks'] and t['state'] not in ('Accepted','NoChangeWithEvidence')]) for g in plan['gates']]
    manifest=[]
    for file in sorted(files):
        manifest.append(dict(path=str(file.relative_to(ROOT)).replace('\\','/'),bytes=file.stat().st_size,sha256=digest(file)))
    counts=dict(packages=len(plan['packages']),tasks=len(tasks),cases=len(cases),
                task_states=dict(Counter(t['state'] for t in tasks)),case_states=dict(Counter(c['status'] for c in cases)))
    register=dict(schema_version=1,kind='runtime_execution_register',generated_at=time.time(),integration_source_sha=head,
        plan_sha256=digest(PLAN),source_plan_identities=plan_sources,release_base=plan['release_base'],counts=counts,all_accepted=False,
        human_experience_scope=human_scope,
        user_experience_override=('按用户本次范围决定移除真人体验；自动战斗、实验、渲染和指标验收仍保留。'
            if not human_scope['in_scope'] else support.get('human_experience_decision',
            '机器人模拟仅作补充；真人验收仍待补。')),
        delivery_policy=support.get('delivery_policy', {'state': 'NotRecorded'}),
        production_runtime=support.get('production_runtime'),session_closeout=support.get('session_closeout'),tasks=tasks,gates=gates)
    (output/'register.json').write_text(json.dumps(register,ensure_ascii=False,indent=2),encoding='utf8')
    (output/'cases.jsonl').write_text(''.join(json.dumps(c,ensure_ascii=False,allow_nan=False)+'\n' for c in cases),encoding='utf8')
    (output/'manifest.json').write_text(json.dumps(dict(source_sha=head,files=manifest),indent=2),encoding='utf8')
    lines=['# PR13 执行与验收登记','','这是运行记录；原有规范文件保持原义。尚未完成全部验收。','',
           f"集成源码：`{head}`。132 子项、396 用例；已有明确实际范围的通过记录 {counts['case_states'].get('Passed',0)} 个。",'',
           '通过记录仅覆盖各用例声明的实际执行范围。缺少的适用运行层见 register.json 中 missing_case_profiles；Passed 不代表整个子项或验收门已通过。ReadyForAcceptance 尚需 MAIN 检查完整判据、依赖和适用 CI。','',
           '候选数值开关仍为关闭。发布去向和授权由本次 support.delivery_policy 记录；真人体验状态由 support.human_experience_decision 记录，不从历史模板推断。','',
           '| 子项 | 状态 | 已通过用例 | 后续动作 |','| --- | --- | ---: | --- |']
    if support.get('session_closeout'):
        lines[2:2]=['本轮已按用户要求结束。未完成项保留，不再自动执行。详见 [收尾报告](CLOSEOUT.md) 与 [完整任务清单](TASK_CHECKLIST.md)。','']
    for t in tasks:lines.append(f"| {t['task_id']} {t['title']} | {t['state']} | {t['case_counts'].get('Passed',0)}/3 | {t['next_action'].replace('|','/')} |")
    lines+=['','## 未达验收门槛','']
    for observation in support.get('observations',[]):
        lines.append(f"- {observation['task_id']}：{observation.get('reason',observation.get('next_action'))}")
    (output/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps(counts));return 0


if __name__=='__main__':raise SystemExit(main())
