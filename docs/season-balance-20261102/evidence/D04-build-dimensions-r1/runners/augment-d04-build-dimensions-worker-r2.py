from pathlib import Path
base=Path(__file__).parent;path=base/'start-d04-build-dimensions-cloud-r2.py';source=path.read_text(encoding='utf-8')
needle="    resource=sample(); assert resource['guard_ok'] and resource['available_ram']>=1800*1024**2 and not breached.is_set()"
assert source.count(needle)==1
extra='''    # Content-addressed third-party DLL cache only; never cache credentials or
    # task assemblies. Optional seeding cannot change this run's verified input.
    def seed_dependencies():
        dependency_cache=Path('/home/ubuntu/season-balance-20261102-dependency-cache-v1')
        assert dependency_cache.resolve()==dependency_cache and not dependency_cache.is_symlink()
        cap=64*1024**2
        candidates={n:h for n,h in manifest['files'].items() if n.startswith('bin/') and n.lower().endswith('.dll') and not Path(n).name.startswith('FantasyCard.')}
        unique={h:n for n,h in candidates.items()}
        if dependency_cache.exists():
            owner=json.loads((dependency_cache/'ownership.original.json').read_text())
            assert owner=={'task':'season-balance-20261102','schema':1,'cap_bytes':cap}
            assert all(p.name=='ownership.original.json' or re.fullmatch('[0-9a-f]{64}',p.name) for p in dependency_cache.iterdir())
        existing=sum(p.stat().st_size for p in dependency_cache.iterdir() if re.fullmatch('[0-9a-f]{64}',p.name)) if dependency_cache.exists() else 0
        needed=sum((root/'input'/n).stat().st_size for h,n in unique.items() if not (dependency_cache/h).exists())
        disk=shutil.disk_usage('/home/ubuntu');after=disk.free-needed-4*1024**2
        if existing+needed>cap or after<3*1024**3 or after/disk.total<.05:return {'seeded':False,'reason':'disk_or_cache_cap'}
        if not dependency_cache.exists():
            dependency_cache.mkdir(mode=0o755)
            with (dependency_cache/'ownership.original.json').open('x') as f:json.dump({'task':'season-balance-20261102','schema':1,'cap_bytes':cap},f)
        added=0
        for digest,name in unique.items():
            destination=dependency_cache/digest
            if destination.exists():
                assert not destination.is_symlink() and hashlib.sha256(destination.read_bytes()).hexdigest()==digest
                continue
            raw=(root/'input'/name).read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
            temporary=dependency_cache/('seed-'+digest)
            with temporary.open('xb') as f:f.write(raw)
            temporary.chmod(0o444);assert not destination.exists();temporary.rename(destination);added+=len(raw)
        return {'seeded':True,'cache_root':str(dependency_cache),'cap_bytes':cap,'total_blob_bytes':existing+added,'added_bytes':added,'verified_files':candidates,'used_for_current_run':False,'other_projects_modified':False}
    try: cache_report=seed_dependencies()
    except (OSError,ValueError,AssertionError) as error:cache_report={'seeded':False,'error_type':type(error).__name__,'reason':str(error)[:160],'used_for_current_run':False}
    (public/'dependency-cache-seed.original.json').write_text(json.dumps(cache_report,indent=2)+'\\n')
'''
source=source.replace(needle,extra+needle);compile(source,str(path),'exec');path.write_text(source,encoding='utf-8')
print('Added optional own64MiB third-party DLL cache seed; current input remains fully supplied and verified.')
