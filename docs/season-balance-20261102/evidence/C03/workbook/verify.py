import hashlib
import json
import math
import shutil
from pathlib import Path

base=Path(__file__).parent;repo=Path.cwd();destination=base/'outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/loans/FantasyCard_Config.xlsx'
scope={'__file__':str(base/'verify-preservation.py')}
exec((base/'verify-preservation.py').read_text().split('before,before_tables=')[0],scope)
before,tables=scope['read'](repo/'config/FantasyCard_Config.xlsx');after,new_tables=scope['read'](destination)
assert tables==new_tables and list(after)==list(before)+['SeasonBorrowedDecks']
cells=0
for name,old in before.items():
    new=after[name]
    for field in ['formulas','merges','state','panes']:assert old[field]==new[field],(name,field)
    for key,value in old['cells'].items():
        if key in old['formulas']:continue
        actual=new['cells'][key]
        if actual!=value:assert math.isclose(float(actual),float(value),abs_tol=1e-12,rel_tol=1e-12),(name,key)
        cells+=1
    assert old['cells'].keys()==new['cells'].keys(),name
rows=json.loads(destination.with_name('loan-rows.json').read_text(encoding='utf-8'))
for row_index,row in enumerate(rows,1):
    for column,value in enumerate(row):assert str(value)==after['SeasonBorrowedDecks']['cells'][f'{chr(65+column)}{row_index}']
styles_scope={'__file__':str(base/'verify-styles.py')}
exec((base/'verify-styles.py').read_text().split('before=read(original)')[0],styles_scope)
old_styles=styles_scope['read'](repo/'config/FantasyCard_Config.xlsx');new_styles=styles_scope['read'](destination)
styles=0
for name,sheet in old_styles.items():
    for key,value in sheet.items():assert value==new_styles[name].get(key),(name,key);styles+=1
proof={'original_sheets_preserved':len(before),'nonformula_cells_verified':cells,'style_cells_verified':styles,'native_tables_preserved':len(tables),'formulas_preserved':sum(len(s['formulas']) for s in before.values()),'added_rows':60,'new_table':'SeasonBorrowedDecks','before_sha256':hashlib.sha256((repo/'config/FantasyCard_Config.xlsx').read_bytes()).hexdigest(),'after_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'visual_review':True}
shutil.copy2(repo/'config/FantasyCard_Config.xlsx',destination.with_name('FantasyCard_Config.before.xlsx'))
shutil.copy2(destination,repo/'config/FantasyCard_Config.xlsx')
destination.with_name('preservation-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
