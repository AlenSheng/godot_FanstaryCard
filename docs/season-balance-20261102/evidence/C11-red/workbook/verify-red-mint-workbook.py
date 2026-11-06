from pathlib import Path
import json,math,hashlib,shutil
base=Path(r'G:\PR13Evidence\season-balance-20261102-r1/workbook');repo=Path.cwd();target=base/'outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/red-mint/FantasyCard_Config.xlsx'
a={'__file__':str(base/'verify-preservation.py')};exec((base/'verify-preservation.py').read_text().split('before,before_tables=')[0],a)
before,tables=a['read'](repo/'config/FantasyCard_Config.xlsx');after,tables_after=a['read'](target);assert list(before)==list(after) and tables==tables_after;count=0
for name,old in before.items():
 new=after[name]
 for field in ['formulas','merges','state','panes']:assert old[field]==new[field],(name,field)
 extra=set(new['cells'])-set(old['cells']);assert extra==({f'I{r}' for r in range(1,7)} if name=='SeasonRedRules' else set()),(name,extra)
 for key,value in old['cells'].items():
  if key in old['formulas']:continue
  actual=new['cells'][key]
  if actual!=value:
   try:assert math.isclose(float(value),float(actual),abs_tol=1e-12,rel_tol=1e-12),(name,key,value,actual)
   except ValueError:raise AssertionError((name,key,value,actual))
  count+=1
st={'__file__':str(base/'verify-styles.py')};exec((base/'verify-styles.py').read_text().split('before=read(original)')[0],st);bs=st['read'](repo/'config/FantasyCard_Config.xlsx');ns=st['read'](target);styles=0
for name,cells in bs.items():
 for key,value in cells.items():assert value==ns[name].get(key),(name,key);styles+=1
assert after['SeasonRedRules']['cells']['I6']=='1'
p={'before_sha256':hashlib.sha256((repo/'config/FantasyCard_Config.xlsx').read_bytes()).hexdigest(),'after_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'original_sheets_preserved':len(before),'old_nonformula_cells_verified':count,'old_style_cells_verified':styles,'old_formulas_preserved':sum(len(s['formulas'])for s in before.values()),'native_tables_preserved':len(tables),'added_cells':'SeasonRedRules!I1:I6 only','production_activated':False}
shutil.copyfile(repo/'config/FantasyCard_Config.xlsx',target.with_name('FantasyCard_Config.before.xlsx'));shutil.copyfile(target,repo/'config/FantasyCard_Config.xlsx');target.with_name('preservation-proof.json').write_text(json.dumps(p,indent=2)+'\n');print(json.dumps(p))
