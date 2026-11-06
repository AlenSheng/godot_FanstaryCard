from pathlib import Path
import json,hashlib,collections,datetime
base=Path(__file__).parent;repo=Path.cwd();source=base/'f01-current-workbook-source-r1.derived.json';book=json.loads(source.read_bytes());assert book['read_only'] and book['source_unchanged']
def column(ref):return ''.join(c for c in ref if c.isalpha())
def table(name):
 rows=book['sheets'][name];header={column(c['cell']):c['value'] for c in rows[0]['cells']};out=[]
 for row in rows:
  if row['row']<=5:continue
  out.append({'row':row['row'],'values':{header[column(c['cell'])]:c['value'] for c in row['cells'] if column(c['cell']) in header},'cells':{header[column(c['cell'])]:c['cell'] for c in row['cells'] if column(c['cell']) in header}})
 return out
tables={n:table(n) for n in book['sheets']}
rewards=tables['SeasonJourneyRewards'];print('reward columns',list(rewards[0]['values']))
shop=tables['SeasonShopProducts'];print('shop columns',list(shop[0]['values']))
activity=tables['SeasonActivityExchange'];print('activity columns',list(activity[0]['values']))
for name in ['SeasonActivityCalendar','SeasonJourneyRules','SeasonWeeklyContracts']:
 print(name,[r['values'] for r in tables[name]])
proof={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'workbook':book['source'],'workbook_sha256':book['source_sha256'],'tables':tables,'new_matches':0,'formal_workbook_modified':False,'F01_complete':False}
p=base/'f01-source-policy-rows-r1.derived.json';assert not p.exists();p.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
