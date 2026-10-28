"""Bounded statistical projections of individually cloud-validated originals.

This only transforms archived metadata. Native encounters and per-cast checks
remain cloud work; the originals stay on G with complete byte/hash/CRC receipts.
"""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from pr13_tuning_recovery_experiment import require

FIELDS=('Seed','SeedBlock','Profile','Hero','Group','Deck','Outcome','Damage30','ImmediateCardsDrawn','ObservedAliveControlUnionTicks','EffectiveHeal','EffectiveShield','HealOverflow','ShieldOverflow')

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def project(directory,output,receipt,cleanup):
    directory=Path(directory);output=Path(output);receipt=Path(receipt);cleanup=Path(cleanup)
    backup=json.loads(receipt.read_text());cloud=json.loads(cleanup.read_text());native=directory/'native'
    require(backup['ok'] and backup['gzip_CRC_SHA_counts_verified'] and cloud['ok'] and cloud['local_G_verified'],'Verified original backup and cloud cleanup receipts required')
    require((backup['bytes'],backup['sha256'],backup['unit'])==(cloud['bytes'],cloud['sha256'],cloud['unit']),'Backup/cleanup archive identity differs')
    original=json.loads((native/'manifest.json').read_text());summary=json.loads((native/'summary.json').read_text());validation=json.loads((directory/'validation.json').read_text());execution=json.loads((directory/'result.json').read_text())
    require(execution['ok'] and execution['source_inputs_unchanged'] and execution['compiled_runtime_unchanged'] and validation['ok'] and summary['passed'],'Original cloud contract validation failed')
    require(original['source_sha']==validation['source_sha']==execution['source_sha']==backup['source_sha'],'Exact original source differs')
    require(validation['encounters']==backup['raw_encounters_verified']==summary['rows']==2000 and validation['actual_events']==backup['raw_events_verified']==summary['actual_casts'],'Verified original denominators differ')
    require(not output.exists(),'New projection required');output.mkdir(parents=True);raw_hash=hashlib.sha256();projection_hash=hashlib.sha256();raw_bytes=projection_bytes=rows=0
    with gzip.open(native/'encounters.jsonl.gz','rb') as src,gzip.open(output/'metrics.jsonl.gz','wb') as dst:
        for line in src:
            raw_hash.update(line);raw_bytes+=len(line);row=json.loads(line);require(row['Error'] is None and row['Outcome'] in ['Victory','Death','Censored'],'Invalid original encounter')
            encoded=(json.dumps({key:row[key] for key in FIELDS},separators=(',',':'))+'\n').encode();dst.write(encoded);projection_hash.update(encoded);projection_bytes+=len(encoded);rows+=1
    require(raw_hash.hexdigest()==summary['raw_sha256'] and raw_bytes==summary['raw_bytes'] and rows==2000,'Original encounter hash/count differs')
    for path in ['manifest.json','summary.json']:(output/path).write_bytes((native/path).read_bytes())
    for path in ['validation.json','result.json']:(output/path).write_bytes((directory/path).read_bytes())
    (output/'local-backup-receipt.json').write_bytes(receipt.read_bytes());(output/'cloud-cleanup-receipt.json').write_bytes(cleanup.read_bytes())
    proof={'schema':'cloud_validated_tuning_metrics_v1','source_sha':original['source_sha'],'unit':backup['unit'],'original_archive_sha256':backup['sha256'],'original_archive_bytes':backup['bytes'],'original_raw_encounter_sha256':summary['raw_sha256'],'original_raw_encounter_bytes':raw_bytes,'rows':rows,'projection_raw_bytes':projection_bytes,'projection_raw_sha256':projection_hash.hexdigest(),'projection_stored_bytes':(output/'metrics.jsonl.gz').stat().st_size,'projection_stored_sha256':digest(output/'metrics.jsonl.gz'),'original_casts_preserved_on_G':True,'full_native_validation_reperformed_in_projection':False}
    (output/'projection.json').write_text(json.dumps(proof,indent=2)+'\n')
    files=[{'path':p.name,'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(output.iterdir()) if p.is_file()];(output/'projection-manifest.json').write_text(json.dumps({'files':files},indent=2)+'\n');return proof

def validate_input(directory,source):
    directory=Path(directory);ledger=json.loads((directory/'projection-manifest.json').read_text());seen=set()
    for row in ledger['files']:
        p=directory/row['path'];require(p.resolve().is_relative_to(directory.resolve()) and p.name not in seen and p.stat().st_size==row['bytes'] and digest(p)==row['sha256'],'Projection file identity differs');seen.add(p.name)
    require(seen=={'metrics.jsonl.gz','manifest.json','summary.json','validation.json','result.json','local-backup-receipt.json','cloud-cleanup-receipt.json','projection.json'},'Projection evidence set differs')
    original=json.loads((directory/'manifest.json').read_text());summary=json.loads((directory/'summary.json').read_text());v=json.loads((directory/'validation.json').read_text());e=json.loads((directory/'result.json').read_text());p=json.loads((directory/'projection.json').read_text());b=json.loads((directory/'local-backup-receipt.json').read_text());c=json.loads((directory/'cloud-cleanup-receipt.json').read_text())
    require(p['schema']=='cloud_validated_tuning_metrics_v1' and all(d['source_sha']==source for d in [original,summary,v,e,p,b]),'Projection source differs')
    require(e['ok'] and e['source_inputs_unchanged'] and e['compiled_runtime_unchanged'] and e['validation']==v and v['ok'] and summary['passed'] and summary['errors']==0 and b['gzip_CRC_SHA_counts_verified'] and c['local_G_verified'] and c['cloud_raw_removed'],'Original evidence not fully validated and archived')
    require(original['samples']==1000 and original['weapon_level']==original['card_level']==0 and original['equipment']=='Empty' and original['strategy']=='basic' and original['cutoff_seconds']==600 and original['paired_budget_guard_passed'] and not original['candidate_activation'],'Original frozen input differs')
    require(v['encounters']==summary['rows']==p['rows']==b['raw_encounters_verified']==2000 and v['actual_events']==summary['actual_casts']==b['raw_events_verified'],'Original and projection count differs')
    require(v['case_denominators']==summary['case_denominators'] and all(x['rejected'] for x in v['negative_controls']) and len(v['negative_controls'])==4,'Original contract controls/case counts differ')
    require(p['original_archive_sha256']==b['sha256']==c['sha256'] and p['original_archive_bytes']==b['bytes']==c['bytes'] and p['unit']==b['unit']==c['unit'],'Original G archive chain differs')
    require(p['original_raw_encounter_sha256']==summary['raw_sha256'] and p['original_raw_encounter_bytes']==summary['raw_bytes'],'Original encounter parent differs')
    h=hashlib.sha256();n=size=0;identities=set()
    with gzip.open(directory/'metrics.jsonl.gz','rb') as f:
        for line in f:
            h.update(line);size+=len(line);n+=1;row=json.loads(line);require(set(row)==set(FIELDS),'Projection metric fields differ');identity=(row['Seed'],row['Profile']);require(identity not in identities,'Duplicate projection encounter');identities.add(identity)
            require(row['Outcome'] in ['Victory','Death','Censored'] and row['Hero']==original['hero'] and row['Group']==original['group'] and row['Deck']==original['alternative'] and row['SeedBlock']==original['block_index'],'Projection stratum/outcome differs')
    require(identities=={(s,a) for s in range(original['seed_start'],original['seed_start']+1000) for a in ['BaselineGreenWater','SingleGreenReplacement']},'All paired original seeds required')
    require(n==2000 and h.hexdigest()==p['projection_raw_sha256'] and size==p['projection_raw_bytes'] and digest(directory/'metrics.jsonl.gz')==p['projection_stored_sha256'] and (directory/'metrics.jsonl.gz').stat().st_size==p['projection_stored_bytes'],'Projection CRC/hash/count differs')
    return v,original,p

def negative_controls(directory,source):
    directory=Path(directory);rejected=[]
    with tempfile.TemporaryDirectory(prefix='pr13-tuning-projection-controls-') as temporary:
        for name in ['wrong-archive-chain','wrong-source','duplicate-paired-seed','missing-original-encounter']:
            target=Path(temporary)/name;shutil.copytree(directory,target)
            if name in ['duplicate-paired-seed','missing-original-encounter']:
                with gzip.open(target/'metrics.jsonl.gz','rt') as f:rows=[json.loads(s) for s in f]
                if name=='duplicate-paired-seed':rows[1]=copy.deepcopy(rows[0])
                else:rows.pop()
                with gzip.open(target/'metrics.jsonl.gz','wt') as f:
                    for row in rows:f.write(json.dumps(row,separators=(',',':'))+'\n')
                proof=json.loads((target/'projection.json').read_text());raw=gzip.decompress((target/'metrics.jsonl.gz').read_bytes());proof.update(projection_raw_sha256=hashlib.sha256(raw).hexdigest(),projection_raw_bytes=len(raw),projection_stored_sha256=digest(target/'metrics.jsonl.gz'),projection_stored_bytes=(target/'metrics.jsonl.gz').stat().st_size);(target/'projection.json').write_text(json.dumps(proof))
            else:
                proof=json.loads((target/'projection.json').read_text());proof['original_archive_sha256' if name=='wrong-archive-chain' else 'source_sha']='0'*64 if name=='wrong-archive-chain' else '0'*40;(target/'projection.json').write_text(json.dumps(proof))
            files=[{'path':p.name,'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(target.iterdir()) if p.is_file() and p.name!='projection-manifest.json'];(target/'projection-manifest.json').write_text(json.dumps({'files':files}))
            try:validate_input(target,source)
            except ValueError:rejected.append({'name':name,'rejected':True})
            else:raise ValueError('Corrupt original-chain projection accepted: '+name)
    return rejected

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--directory',required=True);a.add_argument('--output');a.add_argument('--receipt');a.add_argument('--cleanup');a.add_argument('--validate-source');a.add_argument('--controls',action='store_true');x=a.parse_args()
    if x.validate_source:
        v,m,p=validate_input(x.directory,x.validate_source);result={'ok':True,'source_sha':x.validate_source,'encounters':v['encounters'],'actual_events':v['actual_events'],'projection':p,'negative_controls':negative_controls(x.directory,x.validate_source) if x.controls else []}
        if x.output:Path(x.output).write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))
    else:
        require(x.output and x.receipt and x.cleanup,'Projection output and archive chain required');print(json.dumps(project(x.directory,x.output,x.receipt,x.cleanup)))
