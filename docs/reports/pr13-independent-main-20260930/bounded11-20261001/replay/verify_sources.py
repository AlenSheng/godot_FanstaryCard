"""Compare materialized non-generated tracked files to the exact Git blobs."""
import hashlib,json,pathlib,subprocess,tarfile
B=pathlib.Path(__file__).resolve().parent
groups=json.loads((B/'PACKETS.json').read_text())
results=[]
for g in groups:
    root=pathlib.Path(g['packet'])/'source'
    if not root.exists():continue
    overlays=set()
    if g['group']=='A05':
        overlays={e['path'] for e in json.loads((root/'A05_REPLAY_SOURCE.json').read_text())['harness_files']}
    command=['git','-C','/workspace/godot_FanstaryCard','archive',g['source_sha']]
    proc=subprocess.Popen(command,stdout=subprocess.PIPE)
    entries=[];errors=[];generated=[]
    with tarfile.open(fileobj=proc.stdout,mode='r|') as tf:
        for member in tf:
            if not member.isfile():continue
            name=member.name
            if any(x in {'bin','obj','.godot','__pycache__','validation-bin','validation-obj'} for x in pathlib.Path(name).parts) or name.endswith('.import'):
                generated.append(name);continue
            data=tf.extractfile(member).read();actual=root/name
            expected=hashlib.sha256(data).hexdigest()
            if name in overlays:
                errors.append(dict(path=name,error='overlay replaced tracked file'));continue
            if not actual.exists() or hashlib.sha256(actual.read_bytes()).hexdigest()!=expected:
                errors.append(dict(path=name,error='byte mismatch'))
            entries.append(dict(path=name,bytes=len(data),sha256=expected))
    assert proc.wait()==0
    assert not errors,(g['group'],errors)
    result=dict(group=g['group'],source_sha=g['source_sha'],files_verified=len(entries),generated_excluded=len(generated),overlay_paths=sorted(overlays),errors=errors,files=entries)
    (B/(g['group'].replace('/','-')+'-SOURCE-MANIFEST.json')).write_text(json.dumps(result,indent=2)+'\n')
    results.append({k:v for k,v in result.items() if k!='files'})
(B/'SOURCE_CHECK.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results))
