from pathlib import Path
import ast,json,struct

base=Path(__file__).parent;repo=Path.cwd();original=base/'inspect-e01-config-reuse-r1.py'
tree=ast.parse(original.read_text());definitions=ast.Module(body=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.Import,ast.ImportFrom))],type_ignores=[])
scope={'__file__':str(original)};exec(compile(definitions,str(original),'exec'),scope);fields=scope['fields'];bundle=scope['bundle']
def table_rows(raw):
    columns=[];rows=[]
    for n,w,v,_ in fields(raw):
        if n==2:columns.append(next(x.decode() for k,_,x,_ in fields(v) if k==1))
        if n==3:
            values=[]
            for k,_,value,_ in fields(v):
                assert k==1;entries=list(fields(value));assert len(entries)==1
                kind,wire,data,_=entries[0]
                values.append(data.decode() if kind==1 else data if kind==2 else struct.unpack('<d',data)[0] if kind==3 else bool(data) if kind==4 else None)
            assert len(values)==len(columns);rows.append(dict(zip(columns,values)))
    return rows
current=bundle(repo/'server/config/generated/fantasycard.config.bytes');records=[]
for version in ['season-v1-config-3','season-v1-config-4']:
    old=bundle(repo/'server/config/archive'/version/'fantasycard.config.bytes')
    cols=['difficulty_id','quality_cap','entry_quality_cap'];before=[{k:r[k] for k in cols} for r in table_rows(old['tables']['SeasonDifficulty'])];after=[{k:r[k] for k in cols} for r in table_rows(current['tables']['SeasonDifficulty'])]
    assert before==after
    before_prices=table_rows(old['tables']['LootRules']);after_prices=table_rows(current['tables']['LootRules']);assert before_prices==after_prices
    assert old['tables']['SeasonEquipmentRules']==current['tables']['SeasonEquipmentRules']
    assert old['tables']['SeasonBorrowedDecks']==current['tables']['SeasonBorrowedDecks']
    records.append(dict(source=version,current=current['version'],six_difficulty_quality_caps_unchanged=after,all_LootRules_values_unchanged=True,LootRules_scope_metadata_change_not_a_price_change=True,SeasonEquipmentRules_and_SeasonBorrowedDecks_byte_equal=True))
out=base/'e01-caps-prices-reuse-r1.derived.json';assert not out.exists();out.write_text(json.dumps(dict(records=records,scope='Data equivalence only; historical runtime/UI evidence remains scoped to original batches',new_matches=0),indent=2)+'\n');print('Twooriginals: allsix caps, LootRulesprices/values, borrowedtemplates andequipmentrules unchanged.')
