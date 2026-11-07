from pathlib import Path
import gzip,hashlib,io,json,struct,tarfile

b=Path(__file__).parent;out=b/'f03-minimal-app-input-r5';assert not out.exists();out.mkdir()
report=json.loads((b/'f03-protected-build-r2/result.json').read_bytes());package=Path(report['output'])
buffer=io.BytesIO();files={};total=0
with tarfile.open(fileobj=buffer,mode='w') as tar:
    for name,record in sorted(report['package_files'].items()):
        p=package/name;raw=p.read_bytes();digest=hashlib.sha256(raw).hexdigest();assert digest==record['sha256'] and p.name==name
        assert p.suffix.lower() not in ('.cs','.pdb','.key','.dpapi','.xml')
        member=tarfile.TarInfo(name);member.size=len(raw);member.mode=0o644;member.uid=member.gid=1654;member.mtime=0
        files[name]=digest;total+=len(raw)
        if name.startswith('FantasyCard.') or not name.endswith('.dll'):tar.addfile(member,io.BytesIO(raw))
payload=buffer.getvalue();compressed=gzip.compress(payload,mtime=0)
manifest=dict(task='season-balance-20261107-f03-minimal-app-r5',base_image='sha256:b34b01ff381aa920264e3920d7a7a49e6c1056091999dfc6268107d07029b9f4',
    compiled_source=report['source_commit'],payload_files=files,expanded_bytes=total,tar_bytes=len(payload),payload_bytes=len(compressed),payload_sha256=hashlib.sha256(compressed).hexdigest(),
    transport_files={n:h for n,h in files.items() if n.startswith('FantasyCard.') or not n.endswith('.dll')},parent_reuse_verified_before_program_start=True,canonical_file_mode='0644',file_uid=1654,file_gid=1654,candidate_marker_retained=True,not_a_production_deployment=True,
    no_SDK_no_DB_no_gameplay=True,guard=dict(ram_reserve_bytes=500*1024**2,disk_reserve_bytes=3*1024**3,min_disk_fraction=.05,required_extra_disk_bytes=64*1024**2))
header=json.dumps(manifest).encode();stream=struct.pack('!I',len(header))+header+compressed
(out/'stream.bin').write_bytes(stream);(out/'manifest.original.json').write_text(json.dumps(manifest,indent=2)+'\n')
(out/'transport.original.json').write_text(json.dumps(dict(bytes=len(stream),sha256=hashlib.sha256(stream).hexdigest()),indent=2)+'\n')
print(json.dumps(dict(files=len(files),expanded_bytes=total,transport_bytes=len(stream),required_extra_disk_MiB=64,production_deployment=False)))
