import json
import math
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

root = Path(r'C:\Users\SHENGJIAHAO\.codex\worktrees\sync-release-targets\godot_FanstaryCard')
base = Path(__file__).parent
target = base / 'outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/FantasyCard_Config.xlsx'
ns = {'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def read(path):
    with zipfile.ZipFile(path) as archive:
        strings = [''.join(x.itertext()) for x in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('m:si',ns)] if 'xl/sharedStrings.xml' in archive.namelist() else []
        rels = {r.get('Id'):r.get('Target') for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        result = {}
        for s in ET.fromstring(archive.read('xl/workbook.xml')).findall('m:sheets/m:sheet',ns):
            path = rels[s.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')]
            path = path.lstrip('/') if path.startswith('/') else 'xl/'+path
            doc = ET.fromstring(archive.read(path))
            cells = {}; formulas = {}
            for c in doc.findall('.//m:c',ns):
                v=c.find('m:v',ns); value = '' if v is None else v.text or ''
                if c.get('t') == 's':value=strings[int(value)]
                elif c.get('t') == 'inlineStr':value=''.join(c.find('m:is',ns).itertext())
                if value:cells[c.get('r')]=value
                f=c.find('m:f',ns)
                if f is not None:formulas[c.get('r')]=f.text
            result[s.get('name')]={'cells':cells,'formulas':formulas,'merges':[m.get('ref') for m in doc.findall('m:mergeCells/m:mergeCell',ns)],'state':s.get('state','visible'),
                 'panes':[p.attrib for p in doc.findall('m:sheetViews/m:sheetView/m:pane',ns)]}
        tables=[ET.fromstring(archive.read(p)) for p in archive.namelist() if p.startswith('xl/tables/') and p.endswith('.xml')]
        return result, [{ 'name':t.get('name'),'ref':t.get('ref'),'columns':[(c.get('name'),c.get('totalsRowFunction')) for c in t.findall('m:tableColumns/m:tableColumn',ns)]} for t in tables]

before,before_tables=read(root/'config/FantasyCard_Config.xlsx'); after,after_tables=read(target)
assert list(after)[:len(before)] == list(before)
assert before_tables==after_tables, (before_tables,after_tables)
checked=0
for name, old in before.items():
    new=after[name]
    for field in ['formulas','merges','state']:assert old[field]==new[field],(name,field)
    old_cells={k:v for k,v in old['cells'].items() if k not in old['formulas']}
    new_cells={k:v for k,v in new['cells'].items() if k not in new['formulas']}
    assert old_cells.keys()==new_cells.keys(),(name,'cell addresses')
    for key,value in old_cells.items():
        actual=new_cells[key]
        if actual!=value:
            try:assert math.isclose(float(actual),float(value),abs_tol=1e-12,rel_tol=1e-12),(name,key,value,actual)
            except ValueError:raise AssertionError((name,key,value,actual)) from None
        checked+=1
    # Excel panes may omit default activePane/topLeftCell; compare the split positions.
    assert [{k:v for k,v in p.items() if k in ['xSplit','ySplit','state']} for p in old['panes']]==[{k:v for k,v in p.items() if k in ['xSplit','ySplit','state']} for p in new['panes']],(name,'panes')
payload=json.loads((base/'payload.json').read_text(encoding='utf-8'))
assert len(after)==len(before)+len(payload)
for table in payload:
    name=table['name']; actual=after[name]['cells']
    for r,row in enumerate(table['values'],1):
        for c,value in enumerate(row):
            address=f'{chr(65+c)}{r}'; text=actual.get(address,'')
            if isinstance(value,bool):assert text==str(int(value)),(name,address)
            elif isinstance(value,(int,float)):assert float(text)==value,(name,address)
            else:assert text==value,(name,address)
print(json.dumps({'original_sheets_preserved':len(before),'original_nonformula_cells_verified':checked,'original_formulas_preserved':sum(len(s['formulas']) for s in before.values()),'native_tables_preserved':len(before_tables),'new_tables':{t['name']:len(t['values'])-5 for t in payload}},ensure_ascii=False))
