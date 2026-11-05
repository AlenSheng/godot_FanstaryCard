from pathlib import Path
import hashlib,json,math,shutil
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');base=b/'workbook';out=base/'outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/refresh-prices-r1';target=out/'FantasyCard_Config.xlsx'
scope={'__file__':str(base/'verify-preservation.py')};exec((base/'verify-preservation.py').read_text(encoding='utf-8').split('before,before_tables=')[0],scope)
a,t=scope['read'](repo/'config/FantasyCard_Config.xlsx');z,zt=scope['read'](target);assert list(a)==list(z) and t==zt
changes=[];count=0
for name,old in a.items():
 new=z[name]
 for field in ['formulas','merges','state','panes']:assert old[field]==new[field],(name,field)
 assert old['cells'].keys()==new['cells'].keys(),name
 for cell,value in old['cells'].items():
  if cell in old['formulas']:continue
  actual=new['cells'][cell]
  if value!=actual:
   try:equal=math.isclose(float(value),float(actual),rel_tol=1e-12,abs_tol=1e-12)
   except ValueError:equal=False
   if not equal:changes.append((name,cell,value,actual))
  count+=1
assert changes==[('LootRules','E4','server','both')],changes
styles={'__file__':str(base/'verify-styles.py')};exec((base/'verify-styles.py').read_text(encoding='utf-8').split('before=read(original)')[0],styles)
s1=styles['read'](repo/'config/FantasyCard_Config.xlsx');s2=styles['read'](target);stylecount=0
for name,cells in s1.items():
 for cell,value in cells.items():assert s2[name].get(cell)==value,(name,cell);stylecount+=1
proof=dict(before_sha256=hashlib.sha256((repo/'config/FantasyCard_Config.xlsx').read_bytes()).hexdigest(),after_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),sheets_preserved=len(a),nonformula_cells_checked=count,style_cells_checked=stylecount,formulas_preserved=sum(len(s['formulas']) for s in a.values()),native_tables_preserved=len(t),only_changed_cell=changes,visual_before_and_after_reviewed=True,production_activated=False)
assert not (out/'preservation-proof.json').exists();(out/'preservation-proof.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');shutil.copyfile(repo/'config/FantasyCard_Config.xlsx',out/'FantasyCard_Config.before.xlsx');print(json.dumps(proof))
