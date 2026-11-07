import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

base=Path(__file__).parent
original=Path(r'C:\Users\SHENGJIAHAO\.codex\worktrees\sync-release-targets\godot_FanstaryCard\config\FantasyCard_Config.xlsx')
target=base/'outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/FantasyCard_Config.xlsx'
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def norm(node):
    if node is None:return None
    attributes=dict(node.attrib)
    if 'rgb' in attributes: attributes['rgb']=attributes['rgb'][-6:]
    return (node.tag.split('}')[-1],attributes,[norm(c) for c in node])

def read(path):
    with zipfile.ZipFile(path) as z:
        styles=ET.fromstring(z.read('xl/styles.xml'))
        xfs=styles.find('m:cellXfs',ns); fonts=styles.find('m:fonts',ns); fills=styles.find('m:fills',ns); borders=styles.find('m:borders',ns)
        numbers={x.get('numFmtId'):x.get('formatCode') for x in styles.findall('m:numFmts/m:numFmt',ns)}
        values=[]
        for xf in xfs:
            font=fonts[int(xf.get('fontId','0'))]
            values.append({'font':[norm(c) for c in font if c.tag.split('}')[-1] not in ['family','charset','scheme']], 'fill':norm(fills[int(xf.get('fillId','0'))]), 'border':norm(borders[int(xf.get('borderId','0'))]), 'number':numbers.get(xf.get('numFmtId','0'),xf.get('numFmtId','0')),'alignment':norm(xf.find('m:alignment',ns))})
        rels={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        result={}
        for s in ET.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',ns):
            p=rels[s.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')]; p=p.lstrip('/') if p.startswith('/') else 'xl/'+p
            doc=ET.fromstring(z.read(p));result[s.get('name')]={c.get('r'):values[int(c.get('s','0'))] for c in doc.findall('.//m:c',ns)}
        return result

before=read(original);after=read(target);different=[];count=0
for name,cells in before.items():
    for address,style in cells.items():
        count+=1
        new=after[name].get(address)
        if style != new:different.append({'sheet':name,'cell':address,'before':style,'after':new})
(base/'style-comparison.json').write_text(json.dumps({'cells_checked':count,'differences':different},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'cells_checked':count,'style_differences':len(different),'first':different[:1]},ensure_ascii=False))
