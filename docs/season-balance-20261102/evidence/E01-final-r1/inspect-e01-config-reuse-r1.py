from pathlib import Path
import hashlib,json,struct

repo=Path.cwd(); base=Path(__file__).parent
def fields(data):
    pos=0
    def varint():
        nonlocal pos
        value=shift=0
        while True:
            byte=data[pos];pos+=1;value|=(byte&127)<<shift
            if byte<128:return value
            shift+=7;assert shift<70
    while pos<len(data):
        start=pos;tag=varint();number,wire=tag>>3,tag&7
        if wire==0:value=varint()
        elif wire in [1,5]:size=8 if wire==1 else 4;value=data[pos:pos+size];pos+=size
        elif wire==2:size=varint();value=data[pos:pos+size];pos+=size
        else:raise ValueError(wire)
        yield number,wire,value,data[start:pos]
def bundle(path):
    data=path.read_bytes();ff=list(fields(data));declared=next(v for n,w,v,raw in ff if n==2)
    assert hashlib.sha256(b''.join(raw for n,w,v,raw in ff if n!=2)).digest()==declared
    tables={}
    for n,w,v,raw in ff:
        if n==3:
            name=next(x.decode() for k,_,x,_ in fields(v) if k==1);tables[name]=v
    return dict(version=next(v.decode() for n,w,v,raw in ff if n==1),binary_sha256=hashlib.sha256(data).hexdigest(),content_hash=declared.hex(),tables=tables)
current=bundle(repo/'server/config/generated/fantasycard.config.bytes');old3=bundle(repo/'server/config/archive/season-v1-config-3/fantasycard.config.bytes');old4=bundle(repo/'server/config/archive/season-v1-config-4/fantasycard.config.bytes')
comparisons=[]
for old in [old3,old4]:
    common=set(old['tables'])&set(current['tables']);same=sorted(n for n in common if old['tables'][n]==current['tables'][n]);different=sorted(common-set(same))
    comparisons.append(dict(original=old['version'],current=current['version'],byte_identical_tables=same,changed_tables=different))
required={'season-v1-config-3':['EquipmentQuality','SeasonEquipment','Cards','CardLevels','Backpacks'], 'season-v1-config-4':['EquipmentQuality','SeasonEquipment','SeasonCrafting','Cards','CardLevels','Backpacks']}
for result in comparisons:
    for table in required[result['original']]:assert table in result['byte_identical_tables'],(result['original'],table)
output=base/'e01-config-reuse-inspection-r1.derived.json';assert not output.exists()
output.write_text(json.dumps(dict(scope='Relevant material/crafting/permanentcards/backpack table bodies, not whole historical runtime equivalence',comparisons=comparisons,originals=[{k:v for k,v in x.items() if k!='tables'} for x in [old3,old4,current]],required_table_equality_verified=True,new_matches=0,old_results_not_relabelled_as_new_runs=True),indent=2)+'\n')
print(json.dumps(comparisons))
