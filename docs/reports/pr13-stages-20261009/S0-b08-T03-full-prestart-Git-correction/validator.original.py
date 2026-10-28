"""Cloud-only independent witness quota and exact source/stratum checks."""
import gzip,hashlib,importlib.util,json,sys
from pathlib import Path
def main():
 a=sys.argv[1:];root=Path(a[0]);samples=int(a[1]);block=int(a[2]);expected=[a[3],a[4],a[5],int(a[6])];source=a[7]
 require=(lambda v:None if v else (_ for _ in ()).throw(ValueError('Exact frozen input differs')))
 spec=importlib.util.spec_from_file_location('independent','/independent_validator.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);v=m.validate(root,samples,block,1)
 count=0
 with gzip.open(root/'witnesses.original.jsonl.gz','rt',encoding='utf-8') as f:
  for line in f:
   w=json.loads(line);require(w['schema']=='controlled_room_T03_boundary_v1' and w['source_sha']==source and [w['hero'],w['group'],w['element'],w['level']]==expected and w['twenty_original_instances'] is True);count+=1
 require(count==8000 and samples==1000 and block in (0,1,2));v.update(exact_stratum=expected,source_sha=source,independent_original_validator_sha256=hashlib.sha256(Path('/independent_validator.py').read_bytes()).hexdigest())
 p=root/'independent-validation.original.json';require(not p.exists());p.write_bytes((json.dumps(v,indent=2)+'\n').encode());print(json.dumps(v))
if __name__=='__main__':main()
