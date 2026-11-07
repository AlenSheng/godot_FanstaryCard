from pathlib import Path
import hashlib,json,re,tarfile,xml.etree.ElementTree as ET,difflib

base=Path(__file__).parent;root=base/'storage-r22';out=base/'d02-control-reuse-r1';assert not out.exists()
assert hashlib.sha256((root/'public-evidence.tar.gz').read_bytes()).hexdigest()=='b36e2d090ffe5e6075c3503537339e8e6d5be6dddd852a314c384021ce3a7dd7'
with tarfile.open(root/'public-evidence.tar.gz') as archive:trx=archive.extractfile('domain.trx').read()
results=[e.attrib for e in ET.fromstring(trx).iter() if e.tag.endswith('UnitTestResult')]
selected=[e for e in results if '.SeasonFenxianTests.' in e['testName'] or '.SeasonCombatActionTests.' in e['testName'] or e['testName'].endswith('.Stun_window_halves_second_stun_ignores_third_and_expires_without_extending') or e['testName'].endswith('.Converted_draw_block_doubles_charge_for_exact_duration_and_survives_snapshot')]
assert len(selected)==21 and all(e['outcome']=='Passed' for e in selected)
paths=['server/tests/FantasyCard.Domain.Tests/Combat/SeasonFenxianTests.cs','server/tests/FantasyCard.Domain.Tests/Combat/SeasonCombatActionTests.cs','server/tests/FantasyCard.Domain.Tests/Combat/CombatAuthoritativeRulesTests.cs','server/src/FantasyCard.Domain/Rooms/CombatActionLedger.cs','server/src/FantasyCard.Domain/Rooms/BattleRoomCombatActions.cs']
with tarfile.open(root/'source.tar.gz') as archive:
    originals={name:archive.extractfile(name).read() for name in paths};player=archive.extractfile('server/src/FantasyCard.Domain/Combat/PlayerCombatState.cs').read();old_bundle=archive.extractfile('server/config/generated/fantasycard.config.bytes').read()
assert all(Path(name).read_bytes()==data for name,data in originals.items())
def method(text,name,return_prefix='(?:public|private|internal) [^\n]*'):
    match=re.search(r'^    '+return_prefix+r'\b'+name+r'\(',text,re.M);assert match;start=match.start();brace=text.index('{',match.end());level=0
    for i in range(brace,len(text)):
        level+=(text[i]=='{')-(text[i]=='}')
        if level==0:return text[start:i+1]
old=player.decode('utf-8-sig').replace('\r\n','\n');current=Path('server/src/FantasyCard.Domain/Combat/PlayerCombatState.cs').read_text('utf-8-sig')
methods={}
for name in ['ResolveTargetStun','SetTargetStunWindow','ResolveControl','UpdateFenxian','ApplyStun','ApplyDrawBlock']:
    a=method(old,name);b=method(current,name);assert a==b;methods[name]=hashlib.sha256(a.encode()).hexdigest()
advance_old=method(old,'Advance');advance_new=method(current,'Advance');expected=advance_old.replace('Equipment.HasRapidDraw ? 1.5 : 1.8, 6.0','MinimumDrawInterval, MaximumDrawInterval').replace('rate, _random);','rate, _random,\n                    Equipment.ChainDrawBasisPoints>0?OnNaturalDraw:null);');assert advance_new==expected
def fields(data):
    i=0
    def varint():
        nonlocal i
        value=shift=0
        while True:
            c=data[i];i+=1;value|=(c&127)<<shift
            if c<128:return value
            shift+=7;assert shift<70
    while i<len(data):
        tag=varint();field=tag>>3;wire=tag&7
        if wire==0:value=varint()
        elif wire==2:
            length=varint();value=data[i:i+length];i+=length
        elif wire in [1,5]:
            length=8 if wire==1 else 4;value=data[i:i+length];i+=length
        else:raise ValueError(wire)
        yield field,wire,value
    assert i==len(data)
def tables(data):return {next(v.decode() for f,w,v in fields(t) if f==1):t for f,w,t in fields(data) if f==3}
old_tables=tables(old_bundle);new_tables=tables(Path('server/config/generated/fantasycard.config.bytes').read_bytes());assert all(old_tables[n]==new_tables[n] for n in ['Cards','CardLevels'])
out.mkdir();(out/'domain.trx').write_bytes(trx)
for name,data in originals.items():
    target=out/'original'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
target=out/'original/server/src/FantasyCard.Domain/Combat/PlayerCombatState.cs';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(player)
for name in ['Cards','CardLevels']:(out/(name+'.table.protobuf')).write_bytes(old_tables[name])
result=dict(scope='Reuse exactly21 old passed mechanics contracts only, not194 new executions or old whole integration acceptance.',passed_contracts=selected,new_D02_encounters=0,source_archive_sha256=hashlib.sha256((root/'source.tar.gz').read_bytes()).hexdigest(),public_archive_sha256=hashlib.sha256((root/'public-evidence.tar.gz').read_bytes()).hexdigest(),whole_files_byte_equal={name:hashlib.sha256(data).hexdigest() for name,data in originals.items()},player_functions_equal=methods,player_entire_file_equal=False,
    advance_changes='Only named min/max interval profile support and optional redChainDraw callback. Selected stun case advances with naturalDraw=false. Converted-block fixture uses no red/rapid/chain, null limits ->1.8/6 and null callback; same path and rates.',
    card_table_messages_byte_equal={n:hashlib.sha256(old_tables[n]).hexdigest() for n in ['Cards','CardLevels']},old_config_version=next(v.decode() for f,w,v in fields(old_bundle) if f==1),current_config_version='season-v1-config-15',
    current_published_compatibility='D02 fresh72published PVP cases /144casts independently verify actual control/return and full frozen-state recovery; actual18natural routes add3649casts, not substituted by these old contracts.',
    current_D02_whole_acceptance=False,remaining='Actual storage-backed death/rebuild outcomes and final wholeD02 evidence audit')
(out/'result.derived.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(reused_contracts=21,matched_whole_files=len(originals),matched_methods=len(methods),card_messages_equal=True,new_matches=0)))
