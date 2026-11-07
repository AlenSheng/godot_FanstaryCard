from pathlib import Path

b=Path(__file__).parent;source=(b/'audit-f01-existing-same-tier-efficiency-r1.py').read_text('utf-8')
needle='assert len(rows)==84 and all(s==signatures[0] for s in signatures)'
replacement="""diagnostic=dict(rows=len(rows),varying_fields=[k for k in signatures[0] if any(s[k]!=signatures[0][k] for s in signatures)],groups=[dict(actor=actor,signature_groups=dict(collections.Counter(json.dumps(s,sort_keys=True) for r,s in zip(rows,signatures) if r['actor']==actor))) for actor in sorted({r['actor'] for r in rows})])
(b/'f01-same-tier-signature-diagnostic-r1.derived.json').write_text(json.dumps(diagnostic,indent=2)+'\\n')
print(json.dumps(diagnostic));raise SystemExit(0)"""
assert needle in source;exec(compile(source.replace(needle,replacement),str(Path(__file__)),'exec'))
