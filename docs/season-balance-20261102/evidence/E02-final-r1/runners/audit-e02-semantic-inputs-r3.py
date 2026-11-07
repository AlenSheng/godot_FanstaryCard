from pathlib import Path
import json,hashlib,subprocess,datetime,sys
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent
source=repo/'docs/season-balance-20261102/evidence/E02-source-audit-r1/e02-ui-source-dependencies-r1.derived.json'
inputs=json.loads(source.read_bytes())['sources'];history={};blobs={};cache={}
def original(name,expected):
 key=(name,expected)
 if key in cache:return cache[key]
 if name not in history:history[name]=subprocess.check_output(['git','log','HEAD','--format=%H','--',name]).decode().splitlines()
 for rev in history[name]:
  k=(rev,name)
  if k not in blobs:blobs[k]=subprocess.check_output(['git','show',rev+':'+name])
  raw=blobs[k];lf=raw.replace(b'\r\n',b'\n')
  for mode,value in [('git',raw),('CRLF',lf.replace(b'\n',b'\r\n')),('LF',lf)]:
   if hashlib.sha256(value).hexdigest()==expected:
    answer=(rev,mode,lf);cache[key]=answer;return answer
 raise RuntimeError('Pinned original unavailable: '+name)
reports={}
for group,entry in inputs.items():
 if group=='config17-current':continue
 pin=json.loads((repo/entry['source']).read_bytes());rows=[]
 for name in entry['changed_product_files']:
  if not (name.endswith('.json') or name.endswith('.import')):continue
  expected=pin.get(name.replace('/','\\'),pin.get(name));rev,mode,raw=original(name,expected);current=(repo/name).read_bytes().replace(b'\r\n',b'\n')
  row={'path':name,'original_pin_sha256':expected,'original_commit':rev,'byte_form':mode,'normalized_same':raw==current,'current_sha256':hashlib.sha256((repo/name).read_bytes()).hexdigest()}
  if name.endswith('.json'):
   old=json.loads(raw);new=json.loads(current);row['JSON_semantically_same']=old==new
   if '/locales/' in name:
    assert isinstance(old['strings'],dict) and isinstance(new['strings'],dict)
    a=old['strings'];z=new['strings'];row.update(pack_metadata_same={k:v for k,v in old.items() if k!='strings'}=={k:v for k,v in new.items() if k!='strings'},added_keys=sorted(set(z)-set(a)),removed_keys=sorted(set(a)-set(z)),changed_values={k:{'old':a[k],'new':z[k]} for k in a.keys()&z.keys() if a[k]!=z[k]})
   elif name.endswith('localization_templates.json'):
    row['per_language']={}
    for lang,pack in old['languages'].items():
     assert lang in new['languages'];a=pack['strings'];z=new['languages'][lang]['strings']
     row['per_language'][lang]={'added_keys':sorted(set(z)-set(a)),'removed_keys':sorted(set(a)-set(z)),'changed_values':{k:{'old':a[k],'new':z[k]} for k in a.keys()&z.keys() if a[k]!=z[k]}}
   elif name.endswith('_schema.json'):
    changes=[]
    for message,fields in old['messages'].items():
     if message not in new['messages']:changes.append({'message':message,'kind':'removed'});continue
     for tag,field in fields.items():
      if new['messages'][message].get(tag)!=field:changes.append({'message':message,'tag':tag,'old':field,'new':new['messages'][message].get(tag)})
    row.update(old_field_changes=changes,added_messages=sorted(set(new['messages'])-set(old['messages'])),added_field_tags={m:sorted(set(new['messages'][m])-set(f)) for m,f in old['messages'].items() if m in new['messages'] and set(new['messages'][m])-set(f)})
   elif name.endswith('http_endpoints.json'):
    row.update(protocol_version_same=old['protocol_version']==new['protocol_version'],media_type_same=old['media_type']==new['media_type'],error_same=old['error']==new['error'])
    if isinstance(old['endpoints'],dict):row.update(changed_existing_endpoints=[k for k in old['endpoints'] if new['endpoints'].get(k)!=old['endpoints'][k]],added_endpoints=sorted(set(new['endpoints'])-set(old['endpoints'])))
    else:row.update(old_endpoint_rows_preserved=all(r in new['endpoints'] for r in old['endpoints']),new_endpoint_rows=[r for r in new['endpoints'] if r not in old['endpoints']])
   elif name=='client/data/catalog.json':
    row.update(changed_tables=sorted(k for k in old['tables'].keys()&new['tables'].keys() if old['tables'][k]!=new['tables'][k]),removed_tables=sorted(set(old['tables'])-set(new['tables'])),added_tables=sorted(set(new['tables'])-set(old['tables'])))
   else:
    row.update(changed_top_keys=sorted(k for k in old.keys()&new.keys() if old[k]!=new[k]),removed_top_keys=sorted(set(old)-set(new)),added_top_keys=sorted(set(new)-set(old)))
  rows.append(row)
 reports[group]=rows
proof={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_index_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'groups':reports,'interpretation':'Pinned original bytes reconstructed exactly before semantic comparison. This classifies dependencies; it is not by itself rendered acceptance.','E02_complete':False}
p=base/'e02-semantic-inputs-r3.derived.json';assert not p.exists();p.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for group,rows in reports.items():
 print(group)
 for r in rows:
  if '/locales/' in r['path']:print(r['path'],len(r['added_keys']),r['removed_keys'],list(r['changed_values']))
  elif r['path'].endswith('localization_templates.json'):print(r['path'],{lang:{'added':len(v['added_keys']),'removed':v['removed_keys'],'changed':list(v['changed_values'])} for lang,v in r['per_language'].items()})
  else:print(r['path'],{k:v for k,v in r.items() if k in ['normalized_same','JSON_semantically_same','old_field_changes','old_endpoint_rows_preserved','changed_tables','removed_tables','changed_top_keys']})
