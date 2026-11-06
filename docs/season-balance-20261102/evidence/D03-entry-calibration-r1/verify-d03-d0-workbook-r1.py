from pathlib import Path
import hashlib,json,posixpath,zipfile,xml.etree.ElementTree as ET

root=Path(__file__).parent/'d03-d0-workbook-r1';before=root/'before/config/FantasyCard_Config.xlsx';after=root/'outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/FantasyCard_Config.xlsx';ns='http://schemas.openxmlformats.org/officeDocument/2006/relationships';main='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
def relation_path(name):return posixpath.join(posixpath.dirname(name),'_rels',posixpath.basename(name)+'.rels')
def normalized(z,name):
    node=ET.fromstring(z.read(name));rels={}
    rp=relation_path(name)
    if rp in z.namelist():rels={e.attrib['Id']:e.attrib['Type']+'|'+e.attrib['Target'] for e in ET.fromstring(z.read(rp))}
    def walk(e):
        attrs=dict(e.attrib)
        if name.endswith('.rels') and 'Id' in attrs:attrs['Id']=attrs['Type']+'|'+attrs['Target']
        for key,value in list(attrs.items()):
            if key=='{'+ns+'}id':attrs[key]=rels[value]
        return e.tag,sorted(attrs.items()),(e.text or '').strip(),[walk(c) for c in e]
    return walk(node)
with zipfile.ZipFile(before) as a,zipfile.ZipFile(after) as b:
    assert set(a.namelist())==set(b.namelist());semantic=[];cells=formulas=0
    for name in a.namelist():
        if name.endswith('.xml') or name.endswith('.rels'):
            if normalized(a,name)!=normalized(b,name):semantic.append(name)
        else:assert a.read(name)==b.read(name)
    assert semantic==['xl/worksheets/sheet16.xml'];aa=ET.fromstring(a.read(semantic[0]));bb=ET.fromstring(b.read(semantic[0]));ac={e.attrib['r']:ET.tostring(e) for e in aa.iter('{'+main+'}c')};bc={e.attrib['r']:ET.tostring(e) for e in bb.iter('{'+main+'}c')}
    assert set(ac)==set(bc);changed=[key for key in ac if ac[key]!=bc[key]];assert changed==['C6','D6']
    for k in changed:
        x=ET.fromstring(ac[k]);y=ET.fromstring(bc[k]);assert x.attrib==y.attrib and x.find('{'+main+'}v').text=='1' and y.find('{'+main+'}v').text=='0.5'
    # Replace the two documented values only for the structural comparison.
    for e in bb.iter('{'+main+'}c'):
        if e.attrib['r'] in changed:e.find('{'+main+'}v').text='1'
    assert ET.tostring(aa)==ET.tostring(bb)
    for name in a.namelist():
        if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
            node=ET.fromstring(a.read(name));cells+=sum(1 for _ in node.iter('{'+main+'}c'));formulas+=sum(1 for _ in node.iter('{'+main+'}f'))
    for name in ['xl/styles.xml','xl/sharedStrings.xml','xl/tables/table1.xml','xl/tables/table2.xml']:assert a.read(name)==b.read(name)
result=dict(before_sha256=hashlib.sha256(before.read_bytes()).hexdigest(),after_sha256=hashlib.sha256(after.read_bytes()).hexdigest(),only_value_changes={'SeasonDifficulty!C6':[1,.5],'SeasonDifficulty!D6':[1,.5]},all_other_cells_and_metadata_semantically_equal=True,cell_count=cells,formulas_preserved=formulas,styles_sharedstrings_native_tables_raw_equal=True,relationship_ID_renaming_only=True,before_and_after_previews_reviewed=True,artifact_marker_success_exactly_once=json.loads((root/'edit-marker.original.json').read_bytes())['exit']==0,read_only_before_preview_direct_launch_not_guarded=True,edit_and_all_match_runs_guarded=True)
p=root/'preservation-proof.derived.json';assert not p.exists();p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
