"""Save read-only GitHub workflow results for an exact PR13 source SHA."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--head')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();head=args.head or subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if len(head)!=40 or any(c not in '0123456789abcdef' for c in head):raise ValueError('Full source SHA required')
    credential=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,timeout=15)
    fields=dict(line.split('=',1) for line in credential.stdout.splitlines() if '=' in line)
    headers={'Accept':'application/vnd.github+json','User-Agent':'PR13-acceptance'}
    if fields.get('password'):headers['Authorization']='Bearer '+fields['password']
    base='https://api.github.com/repos/AlenSheng/godot_FanstaryCard'
    def fetch(path):
        with urllib.request.urlopen(urllib.request.Request(base+path,headers=headers),timeout=20) as response:return json.load(response)
    runs=fetch('/actions/runs?'+urllib.parse.urlencode({'head_sha':head,'per_page':50}))['workflow_runs']
    records=[]
    for run in runs:
        record={k:run.get(k) for k in ('id','name','status','conclusion','head_sha','html_url','event','created_at','updated_at')}
        jobs=fetch('/actions/runs/'+str(run['id'])+'/jobs?per_page=100')['jobs']
        record['jobs']=[dict(id=job['id'],name=job['name'],status=job['status'],conclusion=job['conclusion'],html_url=job['html_url'],
            steps=[{k:step.get(k) for k in ('name','status','conclusion','number')} for step in job['steps']]) for job in jobs]
        records.append(record)
    report=dict(checked_at=time.time(),head_sha=head,workflow_runs=records,
        all_returned_workflows_passed=bool(records) and all(r['status']=='completed' and r['conclusion']=='success' for r in records))
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(head_sha=head,workflows=[dict(name=r['name'],status=r['status'],conclusion=r['conclusion']) for r in records])))
    return 0


if __name__=='__main__':raise SystemExit(main())
