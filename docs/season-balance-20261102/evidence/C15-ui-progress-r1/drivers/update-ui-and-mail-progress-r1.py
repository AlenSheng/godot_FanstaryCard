from pathlib import Path
import json

root=Path('docs/season-balance-20261102');p=root/'PROGRESS.json';data=json.loads(p.read_text('utf-8'))
assert sum(i['status']=='complete' for i in data['items'])==20
ui=' 本批实际首轮画面已推进到六语言三宽12状态216帧、18301自动检查，另有20试验帧，共236原图保留。修复账户栏末行、职业缩写、卡组夹具重绘及动态Label类型；完整ISO收藏日期的RTL隔离新修正与原生第17断言仍待运行，资源再次低于门槛，未启动该原生导入。最终需固定修正源码完成11语言396帧及直接效果审查，首轮不是当前最终通过。'
mail=' 综合来源审计识别邮件Card附件未接永久副本；已准备按原mailId聚合数量、账号先锁、事务储备/账本及8项隔离PG用例。旧账号激活语义保留，无版本邮件不按当前季猜测归属；本修正尚未编译/PG验证，不计通过，且其余邮件/资产来源审计仍待。'
for item in data['items']:
 if item['id'] in ('C15','E02'):
  assert '六语言三宽12状态216帧' not in item.get('note','');item['note']=item.get('note','')+ui
  for n in ['C15-UI-REVIEW-PROGRESS.md','evidence/C15-ui-progress-r1/result.json']:
   if n not in item.setdefault('evidence',[]):item['evidence'].append(n)
 if item['id'] in ('A03','A04'):
  assert '邮件Card附件未接永久副本' not in item.get('note','');item['note']=item.get('note','')+mail
  item.setdefault('evidence',[]).append('A03-MAIL-COPY-DRAFT.md')
p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=root/'C15-REWARDS-IMPLEMENTATION.md';text=p.read_text('utf-8')
text+='\n## 当前：六语言首轮画面及邮件副本审计\n\n首轮216帧、18301项自动检查和代表图已完成，236原图保留。当前最终接续改以`C15-UI-REVIEW-PROGRESS.md`为准：修正完整RTL时间后需再固定源码完成12状态／11语言／三宽396最终帧；17项控制器校验在导入准入被拒绝，没有启动Godot。其余邮件副本修正及8项PG用例尚未编译，见`A03-MAIL-COPY-DRAFT.md`。目前没有存活Godot句柄，不并发启动负载。资源保护与20/35状态保持，生产未部署或重启。\n'
p.write_text(text,encoding='utf-8')
p=root/'README.md';text=p.read_text('utf-8');needle='详见[C15客户端接续](C15-CLIENT-CONTROL.md)和[独立预算](C15-REWARD-BUDGET.md)。';assert needle in text
text=text.replace(needle,needle+'最新首轮画面／未复验日期修正见[C15画面接续](C15-UI-REVIEW-PROGRESS.md)，邮件永久副本的待验修正见[来源审计草稿](A03-MAIL-COPY-DRAFT.md)。',1);p.write_text(text,encoding='utf-8')
print(json.dumps({'completed':20,'total':35,'UI_first_matrix':216,'mail_PG_passed':0}))
