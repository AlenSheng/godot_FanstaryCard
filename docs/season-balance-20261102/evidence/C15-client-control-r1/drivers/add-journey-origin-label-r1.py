from pathlib import Path
import json

base=Path(__file__).parent;proof=base/'journey-origin-label-additions-r1.json';assert not proof.exists()
values={
 'en':'Originating season: %s','zh-CN':'来源赛季：%s','ja':'獲得シーズン：%s',
 'ko':'획득 시즌: %s','es':'Temporada de origen: %s','fr':'Saison d’origine : %s',
 'pt':'Temporada de origem: %s','ru':'Сезон получения: %s','ar':'الموسم الأصلي: %s',
 'hi':'प्राप्ति का सीज़न: %s','id':'Musim asal: %s'}
audit={}
for lang,value in values.items():
 path=Path('client/data/locales')/(lang+'.json');d=json.loads(path.read_text('utf-8'));old=json.loads(path.read_text('utf-8'))
 assert 'journey_origin_season' not in d['strings']
 d['strings']['journey_origin_season']=value
 path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 assert all(d['strings'][k]==v for k,v in old['strings'].items())
 assert all(d[k]==v for k,v in old.items() if k!='strings')
 audit[lang]={'key':'journey_origin_season','value':value,'keys':len(d['strings'])}
proof.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'languages':len(audit),'keys_per_language':list({row['keys'] for row in audit.values()})}))
