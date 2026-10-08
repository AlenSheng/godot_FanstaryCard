# -*- coding: utf-8 -*-
"""Validate and render the PR13 specification; never execute its test commands."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json"
GUIDE = SPEC.with_suffix(".md")
QUEUES = [
    ROOT / "docs/plans/GAMEPLAY_LOAD_EXECUTION_20260929.json",
    ROOT / "docs/plans/PR13_REMAINING_QUEUE_20260930.json",
    ROOT / "docs/plans/PR13_COMBAT_EXPERIENCE_QUEUE_20260930.json",
]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate(data):
    errors = []

    def require(ok, message):
        if not ok:
            errors.append(message)

    expected = {
        f"{prefix}{i:02}.{j}"
        for prefix, count in (("LOAD-", 11), ("PR13-A", 10), ("PR13-B", 12))
        for i in range(1, count + 1) for j in range(1, 5)
    }
    packages = data.get("packages", [])
    tasks = [t for p in packages for t in p.get("subtasks", [])]
    ids = [t.get("id") for t in tasks]
    require(len(packages) == 33 and len(tasks) == 132, "Expected 33 packages / 132 subtasks")
    require(len(set(ids)) == len(ids), "Duplicate subtask IDs")
    require(set(ids) == expected, "LOAD44 / A40 / B48 coverage mismatch")
    require(data.get("counts") == {"packages":33,"subtasks":132,"LOAD":44,"A":40,"B":48,"test_cases":396}, "Count metadata mismatch")
    stages = {s["id"] for s in data["stages"]}
    require(stages == {f"S{i}" for i in range(7)}, "All seven stages must be defined")
    gates = {g["id"] for g in data["gates"]}
    require(gates == {f"G{i}" for i in range(6)}, "All six gates must be defined")
    for p in packages:
        require(len(p["subtasks"]) == 4, f"{p['id']}: requires four subtasks")
        require(bool(p.get("owner_role")) and p.get("file_lock_required") is True, f"{p['id']}: missing ownership")
        for path in p.get("write_scope", []):
            require((ROOT / path).exists(), f"{p['id']}: nonexistent ownership path {path}")
        require(set(p.get("related_evidence_tasks", [])) <= expected, f"{p['id']}: unknown shared evidence task")
    case_ids = []
    for t in tasks:
        tid = t["id"]
        for field in ("title", "inputs", "implementation_steps", "pass_criteria", "failure_rule", "rollback", "source_instruction", "evidence_root", "runtime_stage_reason"):
            require(isinstance(t.get(field), str) and bool(t[field].strip()), f"{tid}: missing {field}")
        require(set(t.get("stage_refs", [])) == stages, f"{tid}: incomplete stages")
        require(bool(t.get("gate_refs")) and set(t["gate_refs"]) <= gates, f"{tid}: missing/invalid gate")
        require(bool(t.get("profiles")) and set(t["profiles"]) <= set(data["profiles"]), f"{tid}: invalid profiles")
        require(bool(t.get("command_refs")) and set(t["command_refs"]) <= set(data["commands"]), f"{tid}: invalid command refs")
        require(set(t.get("requires_before_integration", [])) <= expected, f"{tid}: unresolved dependency")
        require(tid not in t.get("requires_before_integration", []), f"{tid}: self dependency")
        require(len(t.get("test_cases", [])) >= 3, f"{tid}: normal/boundary/fault cases required")
        require(t.get("runtime_stage") in ("Required", "NotApplicableWithReason"), f"{tid}: runtime disposition required")
        require(t.get("accepted_by") is None, f"{tid}: documentation update cannot invent acceptance")
        for case in t.get("test_cases", []):
            case_ids.append(case["id"])
            require(bool(case.get("setup_and_injection")) and bool(case.get("expected")), f"{case['id']}: setup/expected missing")
            require(case.get("executed") is False and case.get("evidence") is None, f"{case['id']}: invented execution")
    require(len(case_ids) == len(set(case_ids)), "Duplicate test case IDs")
    require(len(case_ids) == data["counts"]["test_cases"], "Test case count metadata mismatch")
    for gate in data["gates"]:
        require(set(gate["tasks"]) <= expected, f"{gate['id']}: unknown critical task")
        require(any(gate["id"] in t["gate_refs"] for t in tasks), f"{gate['id']}: no coverage")
    graph = {t["id"]: t["requires_before_integration"] for t in tasks}
    visited, active = set(), []

    def visit(tid):
        if tid in active:
            errors.append("Dependency cycle: " + " -> ".join(active + [tid]))
            return
        if tid in visited or tid not in graph:
            return
        active.append(tid)
        for dependency in graph[tid]:
            visit(dependency)
        active.pop()
        visited.add(tid)

    for tid in graph:
        visit(tid)
    index = {t["id"]: t for t in tasks}
    queue_ids = []
    for path in QUEUES:
        queue = read(path)
        require(queue.get("acceptance_details") == SPEC.relative_to(ROOT).as_posix(), f"{path.name}: missing canonical specification link")
        for package in queue["tasks"]:
            for subtask in package["subtasks"]:
                tid = subtask.get("acceptance_detail_id")
                queue_ids.append(tid)
                require(tid in expected, f"{path.name}: unknown detail {tid}")
                if subtask.get("state") in ("Accepted", "NoChangeWithEvidence"):
                    require(bool(subtask.get("accepted_by")) and bool(subtask.get("acceptance_record")), f"{tid}: final queue state requires reviewer and acceptance record")
    require(set(queue_ids) == expected and len(queue_ids) == 132, "Queues do not map to all 132 details exactly once")
    for source in data["sources"]:
        require((ROOT / source).is_file(), f"Missing source document {source}")
    return errors


def clean(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def render(data):
    out = [
        "# PR13 全范围实施与分阶段验收细则",
        "",
        f"日期：{data['date']}。范围：LOAD 44 + A 40 + B 48 = **33个处理包、132个子项、396条检查**。",
        "",
        "本轮完成验收规格，不代表运行实现或测试已经通过。原 LOAD/B 运行状态保留，A 队列重新入库，全部细项的 accepted_by 仍为空。规范 Ready 与运行 Accepted 分开记录。",
        "",
        f"读取的PR head：`{data['source_pr_head']}`；运行代码复核点：`{data['runtime_review_sha']}`；release基线：`{data['release_base']}`。后续运行在独立 manifest 记录实际集成SHA，不沿用文档提交当作服务器构建。",
        "",
        "规范唯一数据源为 [验收细则JSON](PR13_ACCEPTANCE_DETAILS_20260930.json)，本手册由 `python tools/pr13_plan.py --render` 生成。 [LOAD状态](GAMEPLAY_LOAD_EXECUTION_20260929.json)、[A收尾队列](PR13_REMAINING_QUEUE_20260930.json)、[B体验队列](PR13_COMBAT_EXPERIENCE_QUEUE_20260930.json) 均逐子项链接此规格。",
        "",
        "A01～A10来自可访问的《读取PR13报告》对话正文，原sandbox附件未取得。本轮保留其10个职责并重新明确四子项，不宣称恢复了原附件的逐字内容。A与LOAD是补充反例/收尾，共用合格case和artifact；B复用现有NUM策略，避免重复编码。",
        "",
        "历史云端有界部署/测试授权保留；本次只完善规格和文档校验，不执行新部署、压测、数值启用或合并。后续在既有授权内可继续有界正确性测试；冻结数值正式启用和新增范围必须有对应决策。工作角色仅是计划分工，本次未启动代理。",
        "",
        "## 七个可验收阶段",
        "",
        "每个子项按S0～S6分别交回状态和证据。依赖只约束所需集成产物，S0/S1测试设计可提前；不能要求整个父任务先Accepted而产生循环。运行层不适用时写理由，由MAIN审核，不默认跳过。",
        "",
        "| 阶段 | 进入条件 | 执行与通过条件 | 必备证据 | 失败/阻塞 |",
        "|---|---|---|---|---|",
    ]
    for s in data["stages"]:
        out.append(f"| {s['id']} {s['name']} | {clean(s['entry'])} | {clean(s['action'])} 通过：{clean(s['exit'])} | {clean('；'.join(s['evidence']))} | {clean(s['failure'])} |")
    out += ["", "可用执行状态：Queued/InProgress/NotRevalidated/ReadyForAcceptance/Accepted/NoChangeWithEvidence/Failed/Blocked/Partial。只有MAIN根据当前集成证据签Accepted。NoChange仍须当前正确性、剖析或配对结果与明确无需改动理由；缺环境、没跑测试不能写NoChange。Blocked必须写阶段、缺失输入、影响门、解除条件、责任人和下一步。", "", "## 冻结规则与结果合同", "", "保留现行首张合格单元素定核、R/P/B/K与逐卡floor、生命70/80/100、职业护盾帽、自然抽牌地板、20/5/3牌数、死亡装备掉落和价格投放。候选沿用CoreCardsSpent/FractionalRemainder/OptionalMonsterPool，正式默认保留；不自动启用红装、厄运、钻石、机器人或其他冻结玩法。", "", "规范中性能/体验预算是待预登记的验收条件，不是已测最优值或正式SLO。原项目停止线继续保留："]
    for key, value in data["fixed_stop_contract"].items():
        out.append(f"- **{key}**：{value}")
    out += ["", "各运行独立给出 execution/evidence/load/gameplay/performance/cleanup 六维结果，不能只读exit0。运行窗口、STOP后收尾增量、最终累计是三套截止点；不把130与至少139、86与至少90自动改成较大值，A01须逐事件解释。", ""]
    for value in data["evidence_contract"]["count_invariants"]:
        out.append(f"- {value}")
    out += ["", "## 执行档案与实验预算", "", "| Profile | 目的 | 前置条件 | 初始预算/判断限制 |", "|---|---|---|---|"]
    for pid, profile in data["profiles"].items():
        out.append(f"| {pid} | {clean(profile['purpose'])} | {clean(profile['prerequisite'])} | {clean(profile['budget'])} |")
    out += ["", "容量合同在运行前固定profile hash。循环模型允许准备/排队/结算间隙，但active目标必须明写；声明100人在房时目标不能偷换成group_size=50。建议覆盖率等初始预算需在S0完成预登记；阈值缺失时验收函数拒绝运行，而非测试后选值。延迟分位数从同集合原样本计算；低样本、未完成尾延迟和删失必须单列。", "", "数值候选对照记录所有种子及配对单位，95%区间按seed/对局聚类；主要指标和多重比较方案测前冻结。高删失或不识别P95时不得仅用完成样本判达标。三次/1000样本只是首轮预算，精度不足时给Inconclusive，不能保证收益。真人反馈计划与模拟/机器人数据分别存放。", "", "## 六道汇总验收门", "", "| 门 | 本轮通过条件 | 关键子项 | 全覆盖子项数 |", "|---|---|---|---|"]
    all_tasks = [t for p in data["packages"] for t in p["subtasks"]]
    for g in data["gates"]:
        n = sum(g["id"] in t["gate_refs"] for t in all_tasks)
        out.append(f"| {g['id']} {g['name']} | {clean(g['pass'])} | {clean('、'.join(g['tasks']))} | {n} |")
    out += ["", "每道门须检查全部带gate_refs的子项；表中关键项不替代全部覆盖。当前无新运行结果，所有G0～G5的运行验收仍须按证据裁决。", "", "## 排程与文件写入约束", "", "同文件单写入者。授权并行实施时最多3个worker；B06/B07/B08共享PlayerCombatState，B10/B11与LOAD04/05共享game_store，runner由AG-01统一写，协议生成只交AG-05。不要因计划列出角色就填写虚假运行ID。", "", "| 波次 | 工作 | 退出条件 |", "|---|---|---|"]
    for w in data["schedule"]:
        out.append(f"| {w['id']} | {clean('、'.join(w['work']))} | {clean(w['exit'])} |")
    out += ["", "波次是工作安排，真正进入S4/S5以逐项依赖为准。A08.1/LOAD11.1先冻结，LOAD11.4最后交付；B02只需基线输入即可修合同，不等待LOAD10全父包完成。", "", "## 132项详细任务", "", "每项的三条检查分别覆盖正常路径、边界或故障；case编号与预期唯一。下面的步骤与输入足够建立fixture，实施时将实际状态、日志/DB/route/资产比较写入同编号case。尚未存在的CLI或fixture由所属任务实现后登记，不用示例冒充已跑命令。"]
    for p in data["packages"]:
        out += ["", f"### {p['id']} {p['title']}", "", f"负责：{p['owner_role']}。文件：" + "、".join(f"`{path}`" for path in p["write_scope"]) + "。"]
        if p["related_evidence_tasks"]:
            out += ["", "可复用同SHA/profile合格证据：" + "、".join(p["related_evidence_tasks"]) + "；本包新增反例仍需逐条验证。"]
        for t in p["subtasks"]:
            out += ["", f"#### {t['id']} {t['title']}", "", f"输入：{t['inputs']}。进入集成前所需子项：{('、'.join(t['requires_before_integration']) or '无；此项为根前置')}。", "", f"实施：{t['implementation_steps']}。", "", "| 检查 | 操作/注入 | 预期结果 |", "|---|---|---|"]
            for c in t["test_cases"]:
                out.append(f"| {c['id']} | {clean(c['setup_and_injection'])} | {clean(c['expected'])} |")
            out += ["", f"通过：{t['pass_criteria']}", "", f"执行：{'、'.join(t['profiles'])}；命令入口：{'、'.join(t['command_refs'])}；关联门：{'、'.join(t['gate_refs'])}。S5：{t['runtime_stage']}，{t['runtime_stage_reason']}", "", f"交付：`{t['evidence_root']}`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：{t['execution_state']}，历史状态仅作来源：{t['historical_execution_state']}，未签署Accepted；后续真实状态写入对应队列与acceptance_record。", "", f"失败：{t['failure_rule']} 回滚：{t['rollback']}"]
    out += ["", "## 命令与未实现入口", "", "以下是执行阶段的入口目录，本次只运行C-PLAN文档校验。command为空的条目须先完成指定控制/fixture，再提交真实--help和启动命令；不可猜参数或把未存在的战斗仿真命令写成已执行。", "", "| ID | 工作目录 | 入口/状态 | 用途与约束 |", "|---|---|---|---|"]
    for cid, command in data["commands"].items():
        entry = (f"`{command['command']}`" if command["command"] else "尚需实现/冻结实际步骤") + "；" + command["status"]
        out.append(f"| {cid} | `{command['cwd']}` | {clean(entry)} | {clean(command['purpose'])} |")
    out += ["", "## 证据报告与最终关闭", "", "每个阶段report.json至少包含：", "", "、".join(f"`{f}`" for f in data["evidence_contract"]["report_fields"]) + "。", "", data["evidence_contract"]["unavailable"], "", data["evidence_contract"]["public_private"], "", data["evidence_contract"]["new_sha_rule"], "", "MAIN签署每项时给task/stage、证据hash、复跑case、结论/默认值/风险/回滚。Failed/Blocked/Partial必须说明解除条件；NoChange需现行正确且候选无必要/无可靠收益的证据。只有所有适用运行门通过或有效NoChange才可宣称PR13验收完成；完整的规格交付不自动把运行状态改为通过。合并release仍由用户决定。", ""]
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--render", action="store_true")
    args = parser.parse_args()
    data = read(SPEC)
    errors = validate(data)
    rendered = render(data)
    if args.check and (not GUIDE.exists() or GUIDE.read_text(encoding="utf-8") != rendered):
        errors.append("Handbook differs from JSON; run --render")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if args.render:
        GUIDE.write_text(rendered, encoding="utf-8")
    print("PR13 specification valid: 33 packages, 132 subtasks, 396 cases; seven stages, six gates; dependency graph acyclic. Runtime acceptance unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
