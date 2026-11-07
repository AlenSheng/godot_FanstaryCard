from pathlib import Path
import hashlib,json,math,shutil
base=Path(__file__).parent;repo=Path.cwd()
target=base/'outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/season-themes/FantasyCard_Config.xlsx'
scope={'__file__':str(base/'verify-preservation.py')}
exec((base/'verify-preservation.py').read_text().split('before,before_tables=')[0],scope)
before,tables=scope['read'](repo/'config/FantasyCard_Config.xlsx');after,after_tables=scope['read'](target)
assert list(after)==list(before)+['SeasonThemeRules','SeasonThemes','SeasonThemeGroups'] and tables==after_tables
count=0
for name,old in before.items():
 new=after[name]
 for field in ['formulas','merges','state','panes']:assert old[field]==new[field],(name,field)
 assert old['cells'].keys()==new['cells'].keys(),name
 for key,value in old['cells'].items():
  if key in old['formulas']:continue
  actual=new['cells'][key]
  if actual!=value:
   try:assert math.isclose(float(value),float(actual),abs_tol=1e-12,rel_tol=1e-12),(name,key)
   except ValueError:raise AssertionError((name,key,value,actual))
  count+=1
styles_scope={'__file__':str(base/'verify-styles.py')}
exec((base/'verify-styles.py').read_text().split('before=read(original)')[0],styles_scope)
old_styles=styles_scope['read'](repo/'config/FantasyCard_Config.xlsx');new_styles=styles_scope['read'](target)
styles=0
for name,cells in old_styles.items():
 for key,value in cells.items():assert value==new_styles[name].get(key),(name,key);styles+=1
rows=json.loads(target.with_name('theme-rows.json').read_text(encoding='utf-8'))
for table in rows:
 for r,row in enumerate(table['values'],1):
  for c,value in enumerate(row):
   actual=after[table['name']]['cells'].get(f'{chr(65+c)}{r}','')
   assert (actual in ['1','true','True'] if value is True else actual in ['0','false','False'] if value is False else str(value)==actual),(table['name'],r,c,value,actual)
proof={'before_sha256':hashlib.sha256((repo/'config/FantasyCard_Config.xlsx').read_bytes()).hexdigest(),
 'after_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'original_sheets_preserved':len(before),
 'old_nonformula_cells_verified':count,'old_style_cells_verified':styles,
 'old_formulas_preserved':sum(len(row['formulas']) for row in before.values()),'native_tables_preserved':len(tables),
 'new_tables':{'SeasonThemeRules':1,'SeasonThemes':5,'SeasonThemeGroups':19},'rendered_changed_views_reviewed':'--render-reviewed' in __import__('sys').argv,'production_activated':False}
assert not target.with_name('preservation-proof.json').exists()
shutil.copy2(repo/'config/FantasyCard_Config.xlsx',target.with_name('FantasyCard_Config.before.xlsx'))
# Candidate remains external until the active pinned database run has ended.
proof['installed_to_repository']=False
target.with_name('preservation-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))

