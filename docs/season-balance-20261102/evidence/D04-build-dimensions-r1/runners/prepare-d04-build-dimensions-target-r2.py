from pathlib import Path
base=Path(__file__).parent
text=(base/'prepare-d04-room-events-cloud-r2.py').read_text(encoding='utf-8').replace('d04-room-events','d04-build-dimensions').replace('d04-build-dimensions-build-r3','d04-build-dimensions-build-r4')
target=base/'prepare-d04-build-dimensions-cloud-r2.py';assert not target.exists();compile(text,str(target),'exec');target.write_text(text,encoding='utf-8')
print('Prepared one fixture-only actualOS recheck; no backend changes and no rerun of3passed cases.')
