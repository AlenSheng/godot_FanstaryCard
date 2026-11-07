from pathlib import Path

b=Path(__file__).parent;source=(b/'audit-f01-calendar-private-db-r1.py').read_text('utf-8')
source=source.replace("out=b/'f01-calendar-independent-db-audit-r1'","out=b/'f01-skill-db-audit-r1'").replace("control=private/'f01-calendar-r1/control.private.json'","control=private/'f01-skill-correction/control.private.json'").replace('f01-final-audit','f01-skill-audit')
source=source.replace("state['NextIndex']==252","state['NextIndex']==3").replace("len(state['Finished'])==252","len(state['Finished'])==3")
source=source.replace("facts['human_settlements']==252","facts['human_settlements']==255").replace("'human_settlements':252","'human_settlements':255")
source=source.replace("facts=json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))","facts,_=json.JSONDecoder().raw_decode(result.stdout[result.stdout.index('{'):])")
source=source.replace("assert all(0<=row['spent']<=row['earned']<=12 for row in facts['activity_accounts'])","assert all(0<=row['spent']<=row['earned']<=12 for row in facts['activity_accounts']);assert facts['match_statuses']=={'Completed':255}")
target=b/'audit-f01-skill-db-r1.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8');print(str(target))
