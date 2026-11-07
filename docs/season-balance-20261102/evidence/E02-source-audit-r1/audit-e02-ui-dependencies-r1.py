from pathlib import Path
import hashlib,json,subprocess,datetime
repo=Path.cwd();base=Path(__file__).parent;root=repo/'docs/season-balance-20261102/evidence'
selected={
 'C12-market':root/'C12-market/market-ui-filters-r3/source-pin.original.json',
 'C15-current':next((root/'C15-final-r1').rglob('source-pin.original.json')),
 'E01-archive':root/'E01-season-archive-r1/e01-archive-ui-text-r2-zh-CN/source-pin.original.json',
 'E01-reward-value':next(p for p in (root/'E01-final-r1').rglob('source-pin.original.json') if 'ui' in p.as_posix()),
 'config17-current':root/'C01-config17-r1/ui/zh-CN/source-pin.original.json',
}
out={}
for name,path in selected.items():
    raw=path.read_bytes();pin=json.loads(raw);same=[];changed=[];missing=[]
    for key,value in pin.items():
        key=key.replace('\\','/');digest=value if isinstance(value,str) else value.get('sha256')
        if not key.startswith('client/') or key.startswith('client/tests/') or digest is None:continue
        target=repo/key
        if not target.is_file():missing.append(key)
        elif hashlib.sha256(target.read_bytes()).hexdigest()==digest:same.append(key)
        else:changed.append(key)
    out[name]=dict(source=str(path.relative_to(repo)),source_sha256=hashlib.sha256(raw).hexdigest(),same_product_files=len(same),changed_product_files=changed,missing_product_files=missing,
        broad_pin_not_render_dependency_closure=True,render_reuse_accepted_by_this_audit=False)
proof=dict(at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),head=subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(),sources=out,
    client_changes_since_config17_commit=subprocess.check_output(['git','diff','5fefca3c','--name-only','--','client']).decode().splitlines(),
    E02_complete=False,new_rendered_frames=0,interpretation='Byte differences require scoped dependency/changed-region review, not an automatic visual failure or broad re-render. Existing accepted frame verdicts are immutable. Current backend-only lifecycle WIP is outside these pins.')
path=base/'e02-ui-source-dependencies-r1.derived.json';assert not path.exists();path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(proof,ensure_ascii=True))
