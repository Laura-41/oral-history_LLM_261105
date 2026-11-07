#!/usr/bin/env python3
"""把研究者在《BATCH02 双模型同题对照》里填写的 1/2/3/4 落成人工裁决记录 + 导入视图。

编码（研究者 2026-11-07 17:10 说明「标的是是否是人物经历，事件边界没管」）：
    2 = 改判 NARRATED_CONTEXT（讲述背景）
    3 = 改判 UNCERTAIN（不确定）
    4 = 暂缓（补上下文，不落盘）
    1 = 存在歧义，由 --mode 决定，默认零改动：
        keep      = 「维持／通过，不改动」（报告栏位字面写的是「维持 PERSONAL_EXPERIENCE」）
        absolute  = 「最终判为 PERSONAL_EXPERIENCE」（与逐条复核清单的用法一致）

歧义来源：本报告 §5.1 的裁决栏沿用了《逐条复核清单》的措辞，但对照表里同一对
两模型判定可能都不是 PERSONAL_EXPERIENCE，「维持」在部分对上没有明确对象。
助手呈现缺陷，2026-11-07 留痕；两种解读的落地差异已在裁决单中逐项列出。

裁决值同时施加到该对两条线各自的事件节点上；事件边界／归并粒度一律不动。

**最终口径（研究者 2026-11-07 17:26 确认）**：「1 是都算个人经历」，即 `absolute`。
17:2x 曾按 `keep` 做过一次过渡落盘，最终以 `--mode absolute --write` 的结果为准；
两者在标 2 的两条上结论一致，故过渡版视图无需撤回，直接合并。

安全边界：
    - 不动 validated_json/ 的任何模型原始结果，只写 human_adjudicated/ 导入视图
    - 不动冻结的提示词／契约／Schema／校验器，不调用 API、不重跑
    - 与既有导入视图合并，不覆盖上一轮 39 条清单的裁决；同事件冲突则跳过并报告
    - 默认只预览，加 --write 才写文件；撤回只需删除本次生成／更新的视图

用法：
    python3 scripts/apply_dual_model_adjudications.py                       # 预览（默认 keep）
    python3 scripts/apply_dual_model_adjudications.py --write               # 落盘（默认 keep）
    python3 scripts/apply_dual_model_adjudications.py --mode absolute       # 看另一种解读的影响
    python3 scripts/apply_dual_model_adjudications.py --mode absolute --write
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "04_54份正式语料批处理" / "document_consolidation"
REPORT = BASE / "review" / "BATCH02_双模型同题对照_20261107.md"
NOTE = BASE / "review" / "BATCH02_双模型范围裁决记录与判例_20261107.md"
MODELS = ("cuc/deepseek", "cuc/qwen")

CODE_SCOPE_CHANGE = {
    "2": "NARRATED_CONTEXT",
    "3": "UNCERTAIN",
}
CODE_SCOPE_ABSOLUTE = {
    "1": "PERSONAL_EXPERIENCE",
    **CODE_SCOPE_CHANGE,
}
CODE_LABEL = {
    "1": "`keep` 维持不改／`absolute` 判为个人经历 `PERSONAL_EXPERIENCE`",
    "2": "改判讲述背景 `NARRATED_CONTEXT`",
    "3": "改判不确定 `UNCERTAIN`",
    "4": "暂缓（补上下文）",
}


def parse_report(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"(?=^#### \[)", text, flags=re.M)[1:]
    rows = []
    for block in blocks:
        head = re.match(r"#### \[(\d+)\]\s+(\S+)\s+([AB]) 类", block)
        if not head:
            continue
        ds = re.search(r"- \*\*DeepSeek\*\* `(\S+)`", block)
        qw = re.search(r"- \*\*Qwen\*\* `(\S+)`", block)
        dec_line = re.search(r"^- 最终裁决（写数字即可）：.*$", block, flags=re.M)
        code = None
        if dec_line:
            tail = re.search(r"([1234])\s*$", dec_line.group(0))
            code = tail.group(1) if tail else None
        rows.append({
            "index": int(head.group(1)),
            "doc": head.group(2),
            "cls": head.group(3),
            "ds_event": ds.group(1) if ds else None,
            "qw_event": qw.group(1) if qw else None,
            "code": code or "?",
        })
    return rows


def load_events(model: str, doc: str) -> tuple[dict, dict]:
    """返回 (原始结果 dict, 事件字典)；导入视图存在时以视图为基底。"""
    mdir = model.replace("/", "_")
    src = BASE / "validated_json" / mdir / f"{doc}.json"
    result = json.loads(src.read_text(encoding="utf-8"))
    view_path = BASE / "human_adjudicated" / mdir / f"{doc}.json"
    if view_path.exists():
        view = json.loads(view_path.read_text(encoding="utf-8"))
    else:
        view = {
            "adjudication_version": "human-review-v1.0",
            "adjudicated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "adjudicated_by": "研究者",
            "model_id": model,
            "technical_document_id": doc,
            "document_id": result.get("document_id"),
            "source_validated_result": str(src.relative_to(ROOT)),
            "source_raw_response": result.get("source_raw_response"),
            "status": "HUMAN_CONFIRMED_WITH_SCOPE_OVERRIDE",
            "note": (
                "原始模型输出与自动校验结果永久保留不变；本文件仅为人工复核后的图谱导入视图。"
                "HUMAN_CONFIRMED 不在自动校验器枚举内，故本视图不参与自动评分。"
            ),
            "unchanged_policy": (
                "冻结的提示词／输出契约／Schema／校验器均未改动；未调用 API、未重跑、"
                "未覆盖 validated_json；口径维持契约 v0.3。"
            ),
            "adjudications": [],
            "decision_sources": [],
            "consolidated_output": copy.deepcopy(result["consolidated_output"]),
        }
    events = {e["document_event_id"]: e
              for e in view["consolidated_output"]["document_events"]}
    return view, events


def metrics_of(output: dict) -> dict:
    ev = output["document_events"]
    return {
        "document_event_count": len(ev),
        "personal_event_count": sum(1 for e in ev if e["experience_scope"] == "PERSONAL_EXPERIENCE"),
        "context_event_count": sum(1 for e in ev if e["experience_scope"] == "NARRATED_CONTEXT"),
        "uncertain_event_count": sum(1 for e in ev if e["experience_scope"] == "UNCERTAIN"),
        "needs_review_count": sum(1 for e in ev if e["review_status"] == "NEEDS_REVIEW"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="按双模型对照报告的数字裁决生成人工导入视图")
    ap.add_argument("--report", type=Path, default=REPORT)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--mode", choices=("keep", "absolute"), default="keep",
                    help="数字 1 的解读：keep=维持不改（默认），absolute=判为个人经历")
    args = ap.parse_args()
    code_scope = CODE_SCOPE_ABSOLUTE if args.mode == "absolute" else CODE_SCOPE_CHANGE

    if not args.report.exists():
        print(f"找不到对照报告：{args.report}")
        return 1
    rows = parse_report(args.report)
    if not rows:
        print("报告里没有解析到裁决条目")
        return 1
    codes = Counter(r["code"] for r in rows)
    print(f"报告：{args.report.name}　解读模式：{args.mode}"
          f"（{'1=维持不改' if args.mode == 'keep' else '1=判为 PERSONAL_EXPERIENCE'}）")
    print("解析 %d 对：" % len(rows)
          + "、".join(f"{k}={v}" for k, v in sorted(codes.items())))
    bad = [r["index"] for r in rows if r["code"] == "?"]
    if bad:
        print(f"!! 未解析到裁决数字的序号：{bad}（按暂缓处理）")

    # 逐对核对两模型原始判定，并计算与人工值的一致率
    details = []
    hits = {m: 0 for m in MODELS}
    for r in rows:
        target = code_scope.get(r["code"])                    # 本模式下的落地目标
        abs_target = CODE_SCOPE_ABSOLUTE.get(r["code"])       # 绝对判定解读下的参考值
        pair = {"ds": None, "qw": None}
        for key, model in (("ds", MODELS[0]), ("qw", MODELS[1])):
            eid = r[f"{key}_event"]
            if not eid:
                continue
            mdir = model.replace("/", "_")
            src = BASE / "validated_json" / mdir / f"{r['doc']}.json"
            if not src.exists():
                print(f"  !! 找不到 {src}")
                continue
            raw = json.loads(src.read_text(encoding="utf-8"))
            ev = next((e for e in raw["consolidated_output"]["document_events"]
                       if e["document_event_id"] == eid), None)
            if ev is None:
                print(f"  !! {model}/{eid} 不在原始结果中")
                continue
            pair[key] = (eid, ev["experience_scope"], ev["participation_bases"])
            if abs_target and ev["experience_scope"] == abs_target:
                hits[model] += 1
        details.append({**r, "target": target, "abs_target": abs_target, "pair": pair})

    n_scored = sum(1 for d in details if d["abs_target"])
    print(f"\n参考：若按 absolute 解读，原始判定与人工值一致（{n_scored} 对可计）："
          + "、".join(f"{m} {hits[m]}/{n_scored}" for m in MODELS))

    # 收集改判项（目标值与当前视图值不同才改）
    pending: dict[tuple[str, str], list[dict]] = {}
    conflicts, unchanged = [], []
    for d in details:
        if not d["target"]:
            continue
        for key, model in (("ds", MODELS[0]), ("qw", MODELS[1])):
            if not d["pair"][key]:
                continue
            eid = d["pair"][key][0]
            mdir = model.replace("/", "_")
            view, events = load_events(model, d["doc"])
            ev = events.get(eid)
            if ev is None:
                conflicts.append(f"{model}/{eid} 视图中找不到事件")
                continue
            prior = [a for a in view.get("adjudications", [])
                     if a.get("document_event_id") == eid]
            current = ev["experience_scope"]
            if current == d["target"]:
                # 值已等于人工裁决（可能是过渡版已落地），不重复追加裁决记录
                unchanged.append((d["index"], model, eid, d["target"]))
                continue
            if prior:
                # 已有人工裁决，且这次给了不同值：不覆盖，交研究者处理
                conflicts.append(
                    f"[{d['index']}] {model}/{eid} 已有人工裁决 {current}，"
                    f"本次裁决 {d['target']} 与之冲突，跳过")
                continue
            pending.setdefault((model, d["doc"]), []).append({
                "index": d["index"],
                "cls": d["cls"],
                "code": d["code"],
                "event_id": eid,
                "old_scope": current,
                "old_status": ev.get("review_status"),
                "target": d["target"],
                "pair_event_id": (d["pair"]["qw"][0] if key == "ds" else
                                  d["pair"]["ds"][0]) if all(d["pair"].values()) else None,
            })

    print(f"\n需改判 {sum(len(v) for v in pending.values())} 个事件节点；"
          f"原始判定已等于人工值、无需改写 {len(unchanged)} 个。")
    for (model, doc), items in sorted(pending.items()):
        print(f"  {model} / {doc}:")
        for it in items:
            print(f"    [{it['index']}] {it['event_id']} {it['old_scope']} -> {it['target']}"
                  f" ({it['cls']} 类)")
    if conflicts:
        print("\n冲突／异常（不落盘）：")
        for c in conflicts:
            print("  !! " + c)
    if not args.write:
        print("\n[预览模式] 未写入任何内容；确认后加 --write 执行。")
        return 0

    # ---- 落盘 ----
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    written = []
    for (model, doc), items in sorted(pending.items()):
        mdir = model.replace("/", "_")
        view, events = load_events(model, doc)
        src = BASE / "validated_json" / mdir / f"{doc}.json"
        view.setdefault("decision_sources", [])
        source_note = (
            f"2026-11-07 研究者在 {args.report.name} §5.1 填写数字裁决（mode={args.mode}）："
            "1=维持不改(keep)／判为 PERSONAL_EXPERIENCE(absolute)、2=NARRATED_CONTEXT、"
            "3=UNCERTAIN、4=暂缓；裁决值同时施加于双模型各自事件，事件边界未裁决"
        )
        if source_note not in view["decision_sources"]:
            view["decision_sources"].append(source_note)
        for it in items:
            ev = events[it["event_id"]]
            reason = (
                f"研究者 2026-11-07 双模型同题对照裁决（[{it['index']}] 记 {it['code']}，"
                f"{it['cls']} 类）：范围由 {it['old_scope']} 判定为 {it['target']}。"
                "事件边界／归并粒度未裁决，保持原样；participation_bases、逐字证据、"
                "片段 ID 与 canonical_event 全部保持原值。"
            )
            ev["experience_scope"] = it["target"]
            ev["review_status"] = "HUMAN_CONFIRMED"
            ev["review_reason"] = reason
            view["adjudications"].append({
                "document_event_id": it["event_id"],
                "event_name": ev["canonical_event"]["event_name"],
                "source": "BATCH02_双模型同题对照_20261107.md",
                "comparison_index": it["index"],
                "comparison_class": it["cls"],
                "code": it["code"],
                "paired_event_id_other_model": it["pair_event_id"],
                "field_changes": [
                    {"field": "experience_scope", "from": it["old_scope"], "to": it["target"]},
                    {"field": "review_status", "from": it["old_status"], "to": "HUMAN_CONFIRMED"},
                    {"field": "review_reason", "to": reason},
                ],
                "unchanged_fields_note": (
                    "participation_bases / scope_evidence_segment_ids / scope_evidence_quote / "
                    "source_segment_ids / completeness / canonical_event 全部保持原值"
                ),
                "scope_evidence_quote": ev["scope_evidence_quote"],
            })
        view["metrics_original"] = metrics_of(
            json.loads(src.read_text(encoding="utf-8"))["consolidated_output"])
        view["metrics_after_adjudication"] = metrics_of(view["consolidated_output"])
        view["adjudicated_at"] = now
        outdir = BASE / "human_adjudicated" / mdir
        outdir.mkdir(parents=True, exist_ok=True)
        target_path = outdir / f"{doc}.json"
        target_path.write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        written.append(target_path)

    # ---- 裁决记录与判例 ----
    L = []
    L.append("# BATCH02 双模型同题对照 · 范围裁决记录与判例")
    L.append("")
    L.append(f"> 裁决来源：`review/{args.report.name}` §5.1 的 13 对，研究者 2026-11-07 填写数字。")
    L.append(f"> 落盘时间：{now}。助手只做机械转换，**未代填任何结论**。")
    L.append("")
    L.append("## 一、编码口径与一处待确认的歧义（重要）")
    L.append("")
    L.append(f"**本次落盘采用 `--mode {args.mode}`**："
             + ("数字 1 解读为「维持／通过，不改动」。" if args.mode == "keep" else
                "数字 1 解读为「最终判为 `PERSONAL_EXPERIENCE`」。"))
    L.append("")
    L.append("研究者说明「标的是**是否是人物经历，事件边界我没管**」，即裁决维度是范围判定，")
    L.append("不是事件边界。但报告 §5.1 的裁决栏沿用《逐条复核清单》措辞写作")
    L.append("「**1** 维持 `PERSONAL_EXPERIENCE`」，而对照表里同一对两模型判定可能都不是")
    L.append("`PERSONAL_EXPERIENCE`，「维持」在部分对上没有明确对象——**这是助手的呈现缺陷**，")
    L.append("不是研究者标错。两种解读的落地影响差异如下：")
    L.append("")
    L.append("**研究者 2026-11-07 17:26 明确回复「1 是都算个人经历」→ 最终口径 = `absolute`。**")
    L.append("")
    L.append("| 解读 | 数字 1 的含义 | 累计改判节点数 | 状态 |")
    L.append("|---|---|---:|---|")
    L.append("| `keep` | 该对通过，保留两模型各自原判定 | 2 | 17:2x 过渡版，已被取代 |")
    L.append("| `absolute` | 该对统一判为个人经历 | 14 | **最终采用** |")
    L.append("")
    L.append("`absolute` 会把 8 个 DeepSeek 的背景／不确定节点改回个人经历，其中 `[1]` 与")
    L.append("契约 §1.1 禁止项 4（明确反证「那次我不在」）存在张力；**人工裁决优先于模型与契约默认口径**，")
    L.append("已如实留痕。过渡版 `keep` 的裁决单另存为 `BATCH02_双模型范围裁决记录与判例_20261107_keep过渡版.md`；")
    L.append("其 2 个视图在标 2 的两条上结论一致，无需撤回，直接合并。")
    L.append("")
    L.append("| 数字 | 栏位写法／两种解读 | 条数 |")
    L.append("|---|---|---:|")
    for c in ("1", "2", "3", "4"):
        L.append(f"| {c} | {CODE_LABEL[c]} | {codes.get(c, 0)} |")
    L.append("")
    L.append("裁决值（2／3，及 `absolute` 下的 1）**同时施加于两个模型各自的事件节点**；")
    L.append("两模型的事件名、片段、逐字证据一律不动。**B 类 8 对的事件边界／归并粒度未裁决**，")
    L.append("按研究者说明原样保留，作为独立待办，不阻塞本批范围口径的放行。")
    L.append("")
    L.append("## 二、逐对裁决明细")
    L.append("")
    L.append("| 序 | 类 | 文档 | DeepSeek 事件／原判定 | Qwen 事件／原判定 | 数字 | absolute 参考值 | 本次落地 |")
    L.append("|---:|:--:|---|---|---|:--:|---|---|")
    for d in details:
        ds = d["pair"]["ds"]
        qw = d["pair"]["qw"]
        ds_s = f"`{ds[0].split('-')[-1]}` {ds[1]}" if ds else "—"
        qw_s = f"`{qw[0].split('-')[-1]}` {qw[1]}" if qw else "—"
        L.append(f"| [{d['index']}] | {d['cls']} | `{d['doc'].replace('BATCH02-', '')}` "
                 f"| {ds_s} | {qw_s} | {d['code']} | {d['abs_target'] or '暂缓'} "
                 f"| {d['target'] or '维持不改'} |")
    L.append("")
    L.append(f"**参考**：若按 `absolute` 解读，原始判定与人工值一致（{n_scored} 对可计）："
             + "、".join(f"{m} **{hits[m]}/{n_scored}**" for m in MODELS) + "。")
    L.append("样本仅 13 对、且经片段重叠近似配对，只可作为方法章的观察性证据，")
    L.append("**不能当作 54 份准确率结论**；`keep` 解读下 11 对未形成单一人工金标准值，不计算一致率。")
    L.append("")
    L.append("## 三、口径结论与判例")
    L.append("")
    L.append("- 11 对标 1、2 对标 2（改 `NARRATED_CONTEXT`）、无 3／4；")
    L.append("  与《逐条复核清单》36/39 维持个人经历的方向一致：**维持契约 v0.3 §1.1 口径**，")
    L.append("  不升提示词／契约版本、不改 Schema／校验器、不重跑 BATCH02、不动冻结资产。")
    L.append("- 明确改判为 `NARRATED_CONTEXT` 的两例构成后续 45 份人工抽检的判例标尺：")
    L.append("  `[4]` 新四军医院体系沿革与人员来源、`[7]` 中央指示东进扩军——")
    L.append("  均为「部队／组织层面的情况与上级决策」，本人无具体行动角色。")
    L.append("- 其余「集体『我们』＋动作动词」按 v0.3 §1.1 允许项可计入个人经历，")
    L.append("  与首批 `BATCH01-DOC03-DE004`（接受者关系「他教我们」不计）区分。")
    L.append("- 标 1 的 11 对里，两模型原有分歧**按「分开批改」原则各自保留**；")
    L.append("  这正是双线并行的设计：模型输出不合并、不互相覆盖，人工只做局部改判。")
    L.append("")
    L.append("> ⚠️ **口径留痕**：`[1]` DOC01 后藤勇事件的范围证据含明确反证「那次我不在」，")
    L.append("> 按契约 §1.1 禁止项 4 通常判 `NARRATED_CONTEXT`；研究者确认 `absolute` 后该对")
    L.append("> 统一判为 `PERSONAL_EXPERIENCE`。人工复核层优先于模型输出与契约默认口径，")
    L.append("> 已在 `review_reason` 写明，后续 42 份沿用此判例；若日后要调整，改数字重跑即可。")
    L.append("")
    L.append("> ⚠️ `participation_bases` 研究者未指定新值，本次沿用原值（与上一轮 39 条清单裁决一致）。")
    L.append("> 按 `DE004` 先例，`NARRATED_CONTEXT` 通常配 `THIRD_PARTY_ONLY`；")
    L.append("> 给出取值后可重新生成导入视图。")
    L.append("")
    L.append("## 四、落地文件与状态")
    L.append("")
    L.append("| 用途 | 路径 |")
    L.append("|---|---|")
    L.append(f"| 裁决来源（数字由研究者填写） | `review/{args.report.name}` |")
    L.append("| 模型原始结果（**未改动**） | `validated_json/<模型目录>/` |")
    for w in written:
        L.append(f"| 人工导入视图（新建／合并更新） | `{w.relative_to(ROOT)}` |")
    L.append("")
    L.append(f"本次新增改判 **{sum(len(v) for v in pending.values())}** 个事件节点；"
             f"另有 {len(unchanged)} 个节点的值已等于人工裁决（含 17:2x `keep` 过渡版"
             "已落地的 2 条），不重复写入。**13 对共 26 个事件节点全部达到人工裁决值**："
             "14 个经过人工改判、其余原判已一致。")
    L.append("")
    L.append("## 五、本轮未做／待办")
    L.append("")
    L.append("- 未裁决 B 类 8 对的事件边界与归并粒度（研究者明确「没管」），另案处理；")
    L.append("- 未修改 `validated_json/` 与 `raw_responses/` 的任何模型输出；")
    L.append("- 未调用 API、未重跑、未改动冻结提示词／契约／Schema／校验器；")
    L.append("- 未填写 `01_实验配置/双线批改台账.csv` 的人工列，仍由研究者填写；")
    L.append("- 所有结果在人工放行前仍为 `MODEL_CANDIDATE`，不入库、不进图谱。")
    L.append("")
    L.append("**撤回方法**：删除上表新建的导入视图即可；若该视图合并了上一轮 39 条清单的裁决，")
    L.append("删除后需重跑 `python3 scripts/apply_scope_adjudications.py --write` 恢复上一轮结果。")
    L.append("")
    L.append("## 六、对实验流程的作用")
    L.append("")
    L.append("1. 完成 BATCH02 的**内容门槛抽检**（SOP §6 要求人工核对 `experience_scope` 与逐字证据）；")
    L.append("2. 形成后续批次统一的人工判例尺度，避免每批重新拍脑袋；")
    L.append("3. 记录双模型在同一原文上的判定分布与人工改判，供方法章说明「人工复核层」的必要性"
             "（13 对为观察性小样本，非准确率结论）；")
    L.append("4. 与台账人工列一并构成 BATCH03 的放行依据。")
    L.append("")
    NOTE.write_text("\n".join(L) + "\n", encoding="utf-8")
    written.append(NOTE)
    print("\n已写入：")
    for w in written:
        print(f"  {w.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
