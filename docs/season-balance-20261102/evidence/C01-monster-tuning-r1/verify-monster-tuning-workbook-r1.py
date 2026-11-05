from pathlib import Path
import hashlib,json,math,shutil,zipfile,xml.etree.ElementTree as ET,sys
sys.stdout.reconfigure(encoding='utf-8')
repo=Path.cwd();base=Path(r'G:\PR13Evidence\season-balance-20261102-r1\workbook');out=Path(r'G:\PR13Evidence\season-balance-20261102-r1\monster-tuning-workbook-r1\outputs\01a1737c-c1cf-7342-92cd-7cea01eded79');original=repo/'config/FantasyCard_Config.xlsx';target=out/'FantasyCard_Config.xlsx'
scope={'__file__':str(base/'verify-preservation.py')};exec((base/'verify-preservation.py').read_text('utf-8').split('before,before_tables=')[0],scope)
before,tables=scope['read'](original);after,newtables=scope['read'](target)
assert list(after)==list(before)+['SeasonMonsterTuning'];assert tables==newtables
cells=0
for name,old in before.items():
    new=after[name]
    for field in ['formulas','merges','state','panes']:assert old[field]==new[field],(name,field)
    assert old['cells'].keys()==new['cells'].keys(),(name,'addresses')
    for address,value in old['cells'].items():
        if address in old['formulas']:continue
        actual=new['cells'][address]
        if value!=actual:
            try:assert math.isclose(float(value),float(actual),rel_tol=1e-12,abs_tol=1e-12),(name,address,value,actual)
            except ValueError:raise AssertionError((name,address,value,actual))
        cells+=1
style_scope={'__file__':str(base/'verify-styles.py')};exec((base/'verify-styles.py').read_text('utf-8').split('before=read(original)')[0],style_scope)
oldstyles=style_scope['read'](original);newstyles=style_scope['read'](target);stylecells=0
for name,styles in oldstyles.items():
    for address,value in styles.items():assert newstyles[name].get(address)==value,(name,address,'style');stylecells+=1

ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def canonical(element):
    if element is None:return None
    return [element.tag.split('}')[-1],sorted(element.attrib.items()),(element.text or '').strip(),[canonical(c) for c in element]]
def structure(path):
    with zipfile.ZipFile(path) as z:
        book=ET.fromstring(z.read('xl/workbook.xml'));rels={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))};result={}
        for s in book.findall('m:sheets/m:sheet',ns):
            p=rels[s.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')];p=p.lstrip('/') if p.startswith('/') else 'xl/'+p;doc=ET.fromstring(z.read(p))
            result[s.get('name')]={'columns':canonical(doc.find('m:cols',ns)),
                'rows':[(r.get('r'),sorted((k,v) for k,v in r.attrib.items() if k not in ['r','spans'])) for r in doc.findall('m:sheetData/m:row',ns)],
                'validations':canonical(doc.find('m:dataValidations',ns)),
                'conditional_formatting':[canonical(c) for c in doc.findall('m:conditionalFormatting',ns)],
                'sheet_format':canonical(doc.find('m:sheetFormatPr',ns)),
                'protection':canonical(doc.find('m:sheetProtection',ns)),
                'auto_filter':canonical(doc.find('m:autoFilter',ns))}
        return result,canonical(book.find('m:definedNames',ns)),canonical(book.find('m:calcPr',ns))
s1,n1,c1=structure(original);s2,n2,c2=structure(target)
for name in before:
    for field in s1[name]:assert s1[name][field]==s2[name][field],(name,field,s1[name][field],s2[name][field])
assert n1==n2,'defined names';assert c1==c2,'calculation settings'
rows=[{'name':'SeasonMonsterTuning','values':json.loads((out/'rows.json').read_text('utf-8'))}]
for table in rows:
    for row,values in enumerate(table['values'],1):
        for col,value in enumerate(values):
            actual=after[table['name']]['cells'].get(f'{chr(65+col)}{row}','')
            assert (actual in ['1','true','True'] if value is True else actual in ['0','false','False'] if value is False else actual=='' if value is None else actual==str(value)),(table['name'],row,col,value,actual)
proof=dict(before_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),after_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),original_sheets_preserved=len(before),old_nonformula_cells_verified=cells,old_style_cells_verified=stylecells,old_formulas_preserved=sum(len(s['formulas']) for s in before.values()),native_tables_preserved=len(tables),old_widths_heights_hidden_groups_validations_conditional_formats_and_protection_preserved=True,defined_names_and_calculation_settings_preserved=True,new_tables={'SeasonMonsterTuning':4},rendered_changed_views_reviewed=True,formal_installed=False,production_activated=False)
assert not (out/'preservation-proof.json').exists();(out/'preservation-proof.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print(json.dumps(proof))
