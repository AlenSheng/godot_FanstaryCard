import ast,json,pathlib,subprocess,hashlib
B=pathlib.Path(__file__).resolve().parent;R=B/'release';rows=[]
for p in sorted((R/'tools/cloud').rglob('*.py')):
    ast.parse(p.read_text(),filename=str(p));rows.append({'path':str(p.relative_to(R)),'kind':'Python AST','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'exit_code':0})
assert len(rows)==13
scripts=list(sorted((R/'tools/cloud').glob('*.sh')));assert len(scripts)==5
for p in scripts:
    r=subprocess.run(['bash','-n',str(p)],capture_output=True,text=True);assert r.returncode==0,(p,r.stderr)
    rows.append({'path':str(p.relative_to(R)),'kind':'bash -n','argv':r.args,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'exit_code':r.returncode})
(B/'evidence/SYNTAX.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps({'Python_files':13,'Bash_files':5,'status':'Passed'}))
