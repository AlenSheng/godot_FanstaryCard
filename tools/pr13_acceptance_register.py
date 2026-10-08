"""Build the separate 132-task runtime register from explicit evidence records."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-reports',nargs='+',type=Path,required=True)
    parser.add_argument('--support',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    plan=json.loads(PLAN.read_text(encoding='utf8'));support=json.loads(args.support.read_text(encoding='utf8'))
    expected={c['id']:c for p in plan['packages'] for s in p['subtasks'] for c in s['test_cases']}
    known={s['id'] for p in plan['packages'] for s in p['subtasks']};executed={};files={PLAN,args.support.resolve()}
    for file in args.case_reports:
        files.add(file.resolve()); report=file.parent/'report.json'
        if not report.is_file():raise ValueError('Case source report missing: '+str(file))
        files.add(report.resolve());metadata=json.loads(report.read_text(encoding='utf8'))
        if metadata.get('plan_sha256')!=digest(PLAN):raise ValueError('Case evidence uses a different acceptance plan')
        for line in file.read_text(encoding='utf8').splitlines():
            record=json.loads(line);case_id=record['case_id']
            if case_id not in expected or case_id in executed:raise ValueError('Unknown/duplicate case: '+case_id)
            if record.get('status') not in ('Passed','Failed') or record.get('executed') is not True:
                raise ValueError('Invalid case result: '+case_id)
            executed[case_id]=dict(record,evidence=str(file.resolve().relative_to(ROOT)),
                                 source_sha=metadata.get('source_sha'),source=metadata.get('source'))
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
            state=('Failed' if 'Failed' in statuses else 'ReadyForAcceptance' if all(s=='Passed' for s in statuses)
                   else 'Partial' if any(s=='Passed' for s in statuses) or supporting.get(task['id']) else 'Queued')
            if observation.get('state') in ('Blocked','InProgress','Failed','Deferred','Partial'):state=observation['state']
            tasks.append(dict(task_id=task['id'],title=task['title'],package_id=package['id'],state=state,
                accepted_by=None,owner='MAIN',case_counts=dict(Counter(statuses)),
                profiles=task['profiles'],gates=task['gate_refs'],dependencies=task['requires_before_integration'],
                evidence=supporting.get(task['id'],[]),case_ids=[c['id'] for c in task['test_cases']],
                missing_cases=[r['case_id'] for r in task_cases if r['status']!='Passed'],
                pass_criteria=task['pass_criteria'],next_action=observation.get('next_action',
                    '复核逐用例证据、依赖与当前CI后由MAIN裁决。' if state=='ReadyForAcceptance' else task['implementation_steps']),
                observation=observation))
    gates=[dict(gate_id=g['id'],name=g['name'],state='NotAccepted',pass_criteria=g['pass'],
                unfinished=[t['task_id'] for t in tasks if t['task_id'] in g['tasks'] and t['state'] not in ('Accepted','NoChangeWithEvidence')]) for g in plan['gates']]
    manifest=[]
    for file in sorted(files):
        manifest.append(dict(path=str(file.relative_to(ROOT)).replace('\\','/'),bytes=file.stat().st_size,sha256=digest(file)))
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    counts=dict(packages=len(plan['packages']),tasks=len(tasks),cases=len(cases),
                task_states=dict(Counter(t['state'] for t in tasks)),case_states=dict(Counter(c['status'] for c in cases)))
    register=dict(schema_version=1,kind='runtime_execution_register',generated_at=time.time(),integration_source_sha=head,
        plan_sha256=digest(PLAN),release_base=plan['release_base'],counts=counts,all_accepted=False,
        user_experience_override=support.get('human_experience_decision',
            '机器人模拟仅作补充；真人验收仍待补。'),
        delivery_policy=support.get('delivery_policy', {'state': 'NotRecorded'}),
        production_runtime=support.get('production_runtime'),session_closeout=support.get('session_closeout'),tasks=tasks,gates=gates)
    (output/'register.json').write_text(json.dumps(register,ensure_ascii=False,indent=2),encoding='utf8')
    (output/'cases.jsonl').write_text(''.join(json.dumps(c,ensure_ascii=False,allow_nan=False)+'\n' for c in cases),encoding='utf8')
    (output/'manifest.json').write_text(json.dumps(dict(source_sha=head,files=manifest),indent=2),encoding='utf8')
    lines=['# PR13 执行与验收登记','','这是运行记录；原有规范文件保持原义。尚未完成全部验收。','',
           f"集成源码：`{head}`。132 子项、396 用例；逐用例已通过 {counts['case_states'].get('Passed',0)} 个。",'',
           '已通过的独立测试和模拟作为支持材料列出；未逐用例执行的细则仍保留待执行。ReadyForAcceptance 尚需 MAIN 检查完整判据、依赖和适用 CI。','',
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
