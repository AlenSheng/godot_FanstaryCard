"""Byte/SHA/CRC/metadata custody for the human-revised balanced 540 parts."""
import gzip,hashlib,json
from pathlib import Path
B=Path(__file__).parent;G=Path('G:/PR13Evidence/B04-single-factor-reduced-r1')
OUT=B/'B04-reduced-final-original-recovery-index-r2'
TARGET='/home/ubuntu/pr13-acceptance-20261009/evidence/B04-reduced-final-original-inputs-r1-20261014'
NAMES=['manifest.original.json','summary.original.json','encounters.original.jsonl.gz','independent-part-validation.original.json']
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for raw in iter(lambda:f.read(1024**2),b''):h.update(raw)
    return h.hexdigest()
def main():
    assert not OUT.exists()
    final=json.loads((G/'revised-native-and-G-complete.original.json').read_bytes())
    assert final['ok'] and final['original_G_parts']==540 and final['actual_encounters']==21600
    plan=json.loads((G/'common-frozen-inputs/plan.original.json').read_bytes())
    assert len(plan['units'])==540 and plan['expected_encounters']==21600
    parts=[];files=[];members=0;total=0;adopted=0
    for spec in plan['units']:
        selected=G/'units'/spec['unit'];adoption=selected/'adopted-original-G-closure.original.json'
        if adoption.exists():
            a=json.loads(adoption.read_bytes());root=Path(a['original_G_directory']);archive=Path(a['original_archive']);adopted+=1
        else:root=selected;archive=G/'archives'/(spec['unit']+'.original.tar.gz')
        receipt=json.loads((root/'local-G-receipt.original.json').read_bytes())
        cleanup=json.loads((root/'cloud-cleanup.original.json').read_bytes())
        manifest=json.loads((root/'complete-original-manifest.json').read_bytes())
        assert receipt['ok'] and receipt['unit']==spec['unit'] and receipt['all_members_SHA_verified'] and receipt['gzip_CRC_verified']
        assert cleanup['ok'] and cleanup['originals_G_complete'] and cleanup['manifest_sha256']==receipt['manifest_sha256']==sha(root/'complete-original-manifest.json')
        assert receipt['attempt'] in ['B04-single-factor-full-r1-20261013','B04-single-factor-reduced-r1-20261014','B04-single-factor-reduced-ram-r3-20261014']
        assert archive.stat().st_size==receipt['archive_bytes'] and sha(archive)==receipt['archive_sha256']
        with gzip.open(archive,'rb') as stream:
            while stream.read(1024**2):pass
        by={r['path']:r for r in manifest['files']}
        native=root/'outputs/native'
        identity=json.loads((native/'manifest.original.json').read_bytes())
        assert all(identity[k]==spec[k] for k in ['hero','group','strategy','block','offset','samples'])
        for name in NAMES:
            p=native/name;r=by['outputs/native/'+name]
            assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256']
            files.append({'local_source':str(p),'remote_path':TARGET+'/units/'+spec['unit']+'/'+name,
                'bytes':r['bytes'],'sha256':r['sha256'],'original_parent_manifest_sha256':receipt['manifest_sha256']})
            members+=1;total+=r['bytes']
        p=root/'local-G-receipt.original.json'
        files.append({'local_source':str(p),'remote_path':TARGET+'/units/'+spec['unit']+'/local-G-receipt.original.json',
            'bytes':p.stat().st_size,'sha256':sha(p),'original_parent_manifest_sha256':receipt['manifest_sha256']})
        parts.append({'unit':spec['unit'],'directory':TARGET+'/units/'+spec['unit'],'source_G_original_directory':str(root),
            'original_G_archive_sha256':receipt['archive_sha256'],'original_manifest_sha256':receipt['manifest_sha256']})
    assert len(parts)==540 and members==2160 and len(files)==2700 and adopted==115
    proof={'ok':True,'formal_original_parts':540,'formal_original_encounters':21600,'selected_native_original_files_rehashed':2160,
        'selected_native_original_bytes':total,'all540_original_archive_SHA_and_CRC_rechecked':True,
        'native_receipt_and_independent_result_parents_preserved':True,'copy_reference_not_derived_statistical_data':True,
        'local_operations':'byte SHA CRC immutable JSON identity only','target':TARGET,'files':files,
        'human_authorized_sample_reduction_factor':10,'adopted_existing_original_parts':115,'MAIN_accepted':False}
    OUT.mkdir();(OUT/'parts-index.original.json').write_bytes((json.dumps({'parts':parts,'no_original_native_resimulation':True},indent=2)+'\n').encode())
    (OUT/'recovery-input-ledger.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode())
    print(json.dumps({k:v for k,v in proof.items() if k!='files'}))
if __name__=='__main__':main()
