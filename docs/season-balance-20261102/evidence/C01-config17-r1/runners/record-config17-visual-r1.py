from pathlib import Path
import json,hashlib,datetime
base=Path(__file__).parent;out=base/'config17-visual-review-r1.derived.json';assert not out.exists()
selected=[('r1','zh-CN',960,'sustain_details_bottom'),('r1','zh-CN',960,'sustain_old_card'),('r1','en',960,'sustain_new_card'),('r1','en',960,'sustain_details_bottom'),('r1','en',1920,'sustain_hud_full'),('r1','fr',960,'sustain_details'),('r1','pt',960,'sustain_details_bottom'),('r1','id',960,'sustain_hud_full'),('r1','es',960,'sustain_new_card'),('r1','hi',960,'sustain_hud_full'),('r1','hi',960,'sustain_details'),('r2','ar',960,'sustain_details'),('r2','ru',960,'sustain_hud_full'),('r2','ru',1280,'sustain_details'),('r2','ja',960,'sustain_new_card'),('r2','ko',960,'sustain_details_bottom')]
entries=[]
for version,locale,width,scene in selected:
 p=base/f'config17-ui-final-{version}-{locale}'/f'{locale}_{width}_{scene}.png';entries.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),directly_viewed=True))
out.write_text(json.dumps(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=True,reviewed=entries,observed='Shared panel and typography remain consistent; credit and5percent fully visible in narrow HUD including Hindi/Russian; Arabic numerals isolate correctly; description scroll reaches last stat and close button stays clear; new/old MAG10 descriptions differ exactly in printed draw. No new artwork needed.',limitation='Representative direct visual review plus all231frames automated geometry/glyph/content checks; not human-play or new gameplay balance acceptance.'),indent=2)+'\n',encoding='utf-8')
print('16 directly viewed final representatives recorded.')
