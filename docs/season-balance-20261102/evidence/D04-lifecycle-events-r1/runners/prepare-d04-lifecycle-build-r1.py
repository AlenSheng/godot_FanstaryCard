from pathlib import Path
base=Path(__file__).parent
source=(base/'build-d04-crafting-r1.py').read_text(encoding='utf-8').replace("out=base/'d04-crafting-build-r1'","out=base/'d04-lifecycle-build-r1'")
target=base/'build-d04-lifecycle-r1.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8')
print('Prepared one guarded compile; no gameplay campaign.')
