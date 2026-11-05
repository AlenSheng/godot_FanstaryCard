from pathlib import Path
import gzip,hashlib,json

repo=Path.cwd();base=Path(__file__).parent;docs=repo/'docs/season-balance-20261102';out=docs/'evidence/D02-routes-r1';assert not out.exists()
audit=json.loads((base/'d02-routes-inspection-r1.derived.json').read_bytes());assert audit['cases']==audit['extracted']==18 and audit['snapshot_recoveries']==36
reuse=json.loads((base/'d02-control-reuse-r1/result.derived.json').read_bytes());assert len(reuse['passed_contracts'])==21
files=[]
root=base/'d02-route-preflight-r1';files.extend(p for p in root.iterdir() if p.is_file())
files.extend(root/relative for relative in ['results/contracts.trx','config/FantasyCard_Config.xlsx'])
for label in ['d02-routes-pilot-r1','d02-routes-unstarted-r1','d02-control-reuse-r1','d02-pg-readonly-r1']:
    files.extend(p for p in (base/label).rglob('*') if p.is_file())
for name in ['run-d02-route-preflight-r1.py','run-d02-route-roster-r1.py','inspect-d02-routes-r1.py','d02-routes-inspection-r1.derived.json','d02-routes-all-roster-r1.original.json','d02-routes-pilot-roster-r1.original.json','d02-routes-unstarted-roster-r1.original.json','derive-d02-control-reuse-r1.py','inspect-d02-pg-readonly-r1.py','record-d02-route-progress-r1.py']:
    files.append(base/name)
assert len(files)==len(set(files));out.mkdir(parents=True);source={}
for path in files:
    relative=path.relative_to(base).as_posix();data=path.read_bytes();compressed=path.suffix=='.jsonl' or path.suffix=='.json' and len(data)>200000
    archived=relative+('.gz' if compressed else '');target=out/archived;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(gzip.compress(data,mtime=0) if compressed else data)
    assert (gzip.decompress(target.read_bytes()) if compressed else target.read_bytes())==data;source[relative]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'archive':archived,'gzip':compressed}
(out/'source-byte-manifest.json').write_text(json.dumps(source,indent=2)+'\n')
(out/'result.json').write_text(json.dumps(dict(audit,reused_old_control_contracts=21,old_contracts_not_new_executions=True,whole_D02_complete=False,whole_goal_complete=False,original_route_stage_D02_total=91,local_reserve_GiB=2,startup_GiB=1,production_modified=False),indent=2)+'\n')
(out/'manifest.json').write_text(json.dumps({'files':{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}},indent=2)+'\n')
(docs/'D02-ROUTE-RECOVERY-PROGRESS.md').write_text('''# D02 自然路线与撤离恢复子项

状态：路线与恢复子项通过，D02整体在本阶段仍未完成。正式候选15，三职业×六难度共18场全部由原生成出生点沿合法路径击败原Boss并完成真实3秒撤离，3场D2先导与未开始15场各一次执行。累计新增18场，本阶段D02从73到91/300、余209，后续死亡重建的新增场次继续按现行D02-BUDGET记账。

原种子970001至970006，不按胜负选种子；地图、出生、Boss、怪组和数值完全未编辑，逐条核对四邻且不向外。实际路径4或5格，共清81格、108次真实击杀、3649次施法。它们是完整出生到Boss再撤离的合法短路线，不是提案条件八格R1、全图扫描或随机人群平均路线；不替代D03收益/效率/P50/P90，也不更名重跑B05原失败。

永久卡/武器假设+5，实际生效按D；防具+3，D0蓝无效果、D1紫、D2以上一橙四紫。合法20张混色已拥有卡，无红装/生命与牌库重置。准备了两瓶已拥有药剂，但本批实际消耗药剂0、泉水0，不据此宣称它们本批已运行。三选一实际一次回血，其余奖励照实际选项领取，未强造某奖励。

每场在首次成功施法后和撤离读条100ms后各JSON恢复一次，共36次完整快照等价检查；第一次的同ID回放不重复伤害或进手。撤离恢复时真实剩余2.9秒，最后完成时间等于请求时间加3秒，不跳过读条。怪物卡按实际物种+0加入弃牌、原20底牌实例保持；126条HP/盾资源变化与3649施法按每格初始/新增/移除/剩余独立守恒，出牌至少500ms，预览前后全快照不变。

12个实际Boss独立红装判定按原Roll记录，未命中才走Miss；若命中，事先明确的“该逻辑服当周配额已用”领域夹具只返回Exhausted，不铸红。没有伪造Miss、删除判定或声称该夹具是一次真实数据库周配额验证。C11原PG配额证据保持独立。

为核查控制/返牌边界，按原r22公共包SHA取出完整原TRX，复用其中21项已通过合同：11法师消耗约束、8动作时钟/回放、眩晕递减和转换阻断各1。三测试文件、动作账本及接口源共5文件逐字节相同，PlayerCombatState六个相关方法相同；实际Cards和CardLevels Protobuf表消息与旧包字节完全相同。整个PlayerCombatState文件有变化，不描述为未改：Advance只新增命名间隔上下限及可选红连抽回调；选中的眩晕例不推进自然抽牌，转换阻断例无红/速抽/连抽、上下限1.8/6与空回调，路径等价。本批新PVP72场景/144施法及新路线是当前正式目录兼容证据；旧21项不算新执行或新场次。

原件、源/程序集清单、源快照、TRX、逐动作/资源/恢复及独立对账见[evidence/D02-routes-r1/result.json](evidence/D02-routes-r1/result.json)。所有JSONL无损压缩并核对原字节SHA；完整二进制与共享原输入仍在G:/PR13Evidence/season-balance-20261102-r1。

本机2GiB持续保留加1GiB启动预算，三点3GiB、单重进程无窗口/BelowNormal。既有隔离PG只读预检通过原500MiB RAM、3GiB且5%磁盘门槛，未读取凭据或启动云端SDK；真正死亡重建验证另行收口。B05/C16/D01不重跑，100人、已验收UI和原正常结算不补测；生产未部署、激活或重启。
''',encoding='utf-8')
progress=json.loads((docs/'PROGRESS.json').read_bytes());item=next(x for x in progress['items'] if x['id']=='D02');assert item['status']=='in_progress'
item['note']+=' 自然路线子项另新增18/18真实撤离：三职业六难度、原图原出生原Boss、4/5格短合法路径共81格108杀3649施法，36JSON恢复及3秒撤离截止、126资源变化独立核对。不是R1或人群均值。另以源文件/方法和Cards/CardLevels原始Protobuf消息等价复用旧21控制/返牌合同，非重跑。该路线阶段累计91/300；当前死亡重建后续计账以D02-BUDGET为准，整项仍待最终审计。'
item['evidence']+=['D02-ROUTE-RECOVERY-PROGRESS.md','evidence/D02-routes-r1/result.json','evidence/D02-routes-r1/manifest.json','evidence/D02-routes-r1/d02-routes-inspection-r1.derived.json','evidence/D02-routes-r1/d02-control-reuse-r1/result.derived.json']
(docs/'PROGRESS.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(immutable_original_files=len(source),routes=18,old_contracts_reused=21,D02_complete=False)))
