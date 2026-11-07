from pathlib import Path
import zipfile,xml.etree.ElementTree as E,json,hashlib,datetime,sys,posixpath
sys.stdout.reconfigure(encoding='utf-8');base=Path(__file__).parent;source=Path.cwd()/'config/FantasyCard_Config.xlsx';raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()=='cad81ea021cf00184e9e5edc9b40fae337ed92c5febaa7f9262bcf4dd3c4d032'
ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'};rn='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
with zipfile.ZipFile(source) as z:
 strings=[]
 if 'xl/sharedStrings.xml' in z.namelist():strings=[''.join(n.itertext()) for n in E.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',ns)]
 rels={r.attrib['Id']:r.attrib['Target'] for r in E.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
 selected={'SeasonShopRules','SeasonShopProducts','SeasonActivityCalendar','SeasonActivityExchange','SeasonJourneyRules','SeasonJourneyRewards','SeasonWeeklyContracts','SeasonCrafting','SeasonBlueprintSources','SeasonDifficulty','SeasonLootRules'}
 tables={}
 for sh in E.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet',ns):
  name=sh.attrib['name']
  if name not in selected:continue
  target=rels[sh.attrib[rn]];path=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target);rows=[]
  for row in E.fromstring(z.read(path)).findall('s:sheetData/s:row',ns):
   cells=[]
   for c in row.findall('s:c',ns):
    t=c.get('t');v=c.find('s:v',ns);f=c.find('s:f',ns);text=v.text if v is not None else None
    if t=='s' and text is not None:value=strings[int(text)]
    elif t=='inlineStr':value=''.join(c.find('s:is',ns).itertext())
    elif t=='b':value=text=='1'
    elif text is None:value=None
    elif t in ['str','e']:value=text
    else:value=float(text) if '.' in text or 'e' in text.lower() else int(text)
    cells.append({'cell':c.attrib['r'],'value':value,'formula':f.text if f is not None else None})
   rows.append({'row':int(row.attrib['r']),'cells':cells})
  tables[name]=rows
proof={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':str(source),'source_sha256':hashlib.sha256(raw).hexdigest(),'read_only':True,'cached_formula_values_not_recalculated':True,'sheets':tables,'source_unchanged':hashlib.sha256(source.read_bytes()).hexdigest()==hashlib.sha256(raw).hexdigest()}
out=base/'f01-current-workbook-source-r1.derived.json';assert not out.exists();out.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name,rows in tables.items():
 print(name,'rows',len(rows))
 for row in rows[1:3]+rows[5:7]:print(row['row'],[(c['cell'],c['value']) for c in row['cells']][:16])
