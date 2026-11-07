#!/usr/bin/env python3
"""把研究者在逐条复核清单里填写的数字裁决，落成 human_adjudicated 导入视图 + 裁决单。

编码（研究者 2026-11-07 定义，写在清单顶部）：
    1 = 维持 PERSONAL_EXPERIENCE（不生成改判）
    2 = 改判 NARRATED_CONTEXT
    3 = 改判 UNCERTAIN
    4 = 暂缓（补上下文，不生成改判）

安全边界：
    - 只读 validated_json/ 与清单；**不覆盖任何模型原始结果**
    - 不动冻结的提示词／契约／Schema／校验器，不调用 API，不重跑
    - 默认只预览，加 --write 才写文件
    - participation_bases 研究者未指定新值，本次保持原值，在裁决单中标注待确认

用法：
    python3 scripts/apply_scope_adjudications.py                 # 预览
    python3 scripts/apply_scope_adjudications.py --write         # 落盘
    python3 scripts/apply_scope_adjudications.py --checklist <md> --model cuc/qwen --write
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "04_54份正式语料批处理" / "document_consolidation"

CODE_SCOPE = {"2": "NARRATED_CONTEXT", "3": "UNCERTAIN"}
CODE_LABEL = {
    "1": "维持 PERSONAL_EXPERIENCE",
    "2": "改判 NARRATED_CONTEXT",
    "3": "改判 UNCERTAIN",
    "4": "暂缓（补上下文）",
}


def parse_checklist(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"(?=^### \[)", text, flags=re.M)[1:]
    rows: list[dict] = []
    for block in blocks:
        head = re.match(r"### \[(\d+)\]\s+(\S+)", block)
        if not head:
            continue
        note = re.search(r"^- 裁决依据／备注：(.*)$", block, flags=re.M)
        raw = note.group(1) if note else ""
        codes = re.findall(r"(?<![0-9])[1234](?![0-9])", raw)
        remark = re.sub(r"[_\s\d]", "", raw).strip()
        rows.append({
            "index": int(head.group(1)),
            "event_id": head.group(2),
            "code": codes[0] if len(codes) == 1 else ("?" if not codes else "|".join(codes)),
            "remark": remark,
        })
    return rows


def metrics_of(output: dict) -> dict:
    events = output["document_events"]
    return {
        "document_event_count": len(events),
        "candidate_decision_count": len(output["candidate_decisions"]),
        "personal_event_count": sum(
            1 for e in events if e["experience_scope"] == "PERSONAL_EXPERIENCE"),
        "context_event_count": sum(
            1 for e in events if e["experience_scope"] == "NARRATED_CONTEXT"),
        "uncertain_event_count": sum(
            1 for e in events if e["experience_scope"] == "UNCERTAIN"),
        "needs_review_count": sum(
            1 for e in events if e["review_status"] == "NEEDS_REVIEW"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="按清单数字裁决生成人工导入视图")
    ap.add_argument("--checklist", type=Path, default=None)
    ap.add_argument("--model", default="cuc/deepseek")
    ap.add_argument("--batch", default="BATCH02")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    mdir = args.model.replace("/", "_")
    checklist = args.checklist or (
        BASE / "review"
        / f"{args.batch}_{mdir}_COLLECTIVE_WITH_ROLE_逐条复核清单_20261107.md"
    )
    if not checklist.exists():
        print(f"找不到清单：{checklist}")
        return 1
    rows = parse_checklist(checklist)
    if not rows:
        print("清单里没有解析到裁决条目")
        return 1

    # 按文档归集改判
    by_doc: dict[str, list[dict]] = {}
    for row in rows:
        if row["code"] not in CODE_SCOPE:
            continue
        doc = row["event_id"].rsplit("-DE", 1)[0]
        by_doc.setdefault(doc, []).append(row)

    counts = {k: 0 for k in CODE_LABEL}
    for row in rows:
        counts[row["code"]] = counts.get(row["code"], 0) + 1

    print(f"清单：{checklist.name}")
    print(f"解析 {len(rows)} 条："
          + "、".join(f"{CODE_LABEL.get(k, '异常 ' + k)} {v} 条" for k, v in counts.items()))
    for doc, items in by_doc.items():
        for row in items:
            print(f"  改判 {doc}/{row['event_id']} -> {CODE_SCOPE[row['code']]}"
                  + (f"　备注：{row['remark']}" if row["remark"] else ""))
    pending = [r for r in rows if r["code"] == "4"]
    if pending:
        print("  暂缓（不落盘）：" + ", ".join(r["event_id"] for r in pending))
    if not args.write:
        print("\n[预览模式] 未写入任何内容；确认后加 --write 执行。")
        return 0

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    outdir = BASE / "human_adjudicated" / mdir
    outdir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    doc_summaries: list[dict] = []

    for doc, items in sorted(by_doc.items()):
        src = BASE / "validated_json" / mdir / f"{doc}.json"
        result = json.loads(src.read_text(encoding="utf-8"))
        original = result["consolidated_output"]
        updated = copy.deepcopy(original)
        event_by_id = {e["document_event_id"]: e for e in updated["document_events"]}

        adjudications = []
        for row in items:
            event = event_by_id.get(row["event_id"])
            if event is None:
                print(f"  !! 找不到事件 {row['event_id']}，跳过")
                continue
            old_scope = event["experience_scope"]
            old_status = event["review_status"]
            old_reason = event.get("review_reason")
            new_scope = CODE_SCOPE[row["code"]]
            reason = (
                f"研究者 2026-11-07 裁决（清单 [{row['index']}] 记 {row['code']}）："
                + (row["remark"] + "；" if row["remark"] else "未填写具体依据，待补；")
                + f"范围由 {old_scope} 改判为 {new_scope}。"
                + "participation_bases 研究者未指定新值，本次保持原值；逐字证据与其余字段不变。"
            )
            event["experience_scope"] = new_scope
            event["review_status"] = "HUMAN_CONFIRMED"
            event["review_reason"] = reason
            adjudications.append({
                "document_event_id": row["event_id"],
                "event_name": event["canonical_event"]["event_name"],
                "checklist_index": row["index"],
                "checklist_code": row["code"],
                "field_changes": [
                    {"field": "experience_scope", "from": old_scope, "to": new_scope},
                    {"field": "review_status", "from": old_status, "to": "HUMAN_CONFIRMED"},
                    {"field": "review_reason", "from": old_reason, "to": reason},
                ],
                "unchanged_fields_note": (
                    "participation_bases / scope_evidence_segment_ids / scope_evidence_quote / "
                    "source_segment_ids / completeness / canonical_event 全部保持原值"
                ),
                "evidence_segment_ids": event["scope_evidence_segment_ids"],
                "scope_evidence_quote": event["scope_evidence_quote"],
                "researcher_remark": row["remark"] or None,
            })

        metrics_before = metrics_of(original)
        metrics_after = metrics_of(updated)
        view = {
            "adjudication_version": "human-review-v1.0",
            "adjudicated_at": now,
            "adjudicated_by": "研究者",
            "decision_source": (
                f"2026-11-07 研究者在 {checklist.name} 的「裁决依据／备注」栏填写数字："
                "1=维持、2=改 NARRATED_CONTEXT、3=改 UNCERTAIN、4=暂缓"
            ),
            "model_id": args.model,
            "technical_document_id": doc,
            "document_id": result.get("document_id"),
            "source_validated_result": str(src.relative_to(ROOT)),
            "source_raw_response": result.get("source_raw_response"),
            "status": "HUMAN_CONFIRMED_WITH_SCOPE_OVERRIDE",
            "note": (
                "原始模型输出与自动校验结果永久保留不变；本文件仅为人工复核后的图谱导入视图。"
                "HUMAN_CONFIRMED 不在自动校验器枚举内，故本视图不参与 validate_document_consolidation 评分。"
            ),
            "unchanged_policy": (
                "冻结的提示词／输出契约／Schema／校验器均未改动；未调用 API、未重跑、"
                "未覆盖 validated_json；口径维持契约 v0.3。"
            ),
            "pending_confirmation": (
                "participation_bases 的新值研究者尚未指定：2 条改判均保留原 "
                "COLLECTIVE_WITH_ROLE。如需改为 THIRD_PARTY_ONLY / INSUFFICIENT_EVIDENCE 等，"
                "请明确后重新生成本视图。"
            ),
            "adjudications": adjudications,
            "metrics_original": metrics_before,
            "metrics_after_adjudication": metrics_after,
            "consolidated_output": updated,
        }
        target = outdir / f"{doc}.json"
        target.write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(target)
        doc_summaries.append({"doc": doc, "before": metrics_before, "after": metrics_after,
                              "items": items})

    # 裁决单
    lines: list[str] = []
    lines.append(f"# {args.batch} / {args.model} · 范围判定人工裁决单")
    lines.append("")
    lines.append(f"> 裁决依据：`review/{checklist.name}` 中研究者填写的数字；落盘时间 {now}。")
    lines.append("> 裁决人：研究者；助手只负责按裁决生成文件，**未代填任何结论**。")
    lines.append("")
    lines.append("## 一、裁决编码与汇总")
    lines.append("")
    lines.append("| 数字 | 含义 | 条数 |")
    lines.append("|---|---|---:|")
    for code, label in CODE_LABEL.items():
        lines.append(f"| {code} | {label} | {counts.get(code, 0)} |")
    lines.append("")
    changed_count = sum(len(v) for v in by_doc.values())
    lines.append(
        f"共 **{len(rows)}** 条：维持 {counts.get('1', 0)} 条、改判 {changed_count} 条、"
        f"暂缓 {counts.get('4', 0)} 条。维持项不生成导入视图（原始结果即最终结果）。"
    )
    lines.append("")
    lines.append("**口径结论**：39 条中 36 条维持 `PERSONAL_EXPERIENCE`，说明研究者**维持契约 v0.3 §1.1 口径**；")
    lines.append("不升提示词／契约版本、不重跑 BATCH02、不改冻结资产与校验器。")
    lines.append("")
    lines.append("## 二、改判明细")
    lines.append("")
    lines.append("| 文档 | 事件 ID | 清单序号 | 原范围 | 新范围 | 研究者备注 |")
    lines.append("|---|---|---:|---|---|---|")
    for doc, items in sorted(by_doc.items()):
        for row in items:
            lines.append(
                f"| `{doc}` | `{row['event_id']}` | [{row['index']}] | `PERSONAL_EXPERIENCE` "
                f"| `{CODE_SCOPE[row['code']]}` | {row['remark'] or '—'} |"
            )
    lines.append("")
    lines.append("每条改判只变更 `experience_scope`、`review_status`（→ `HUMAN_CONFIRMED`）、`review_reason` 三个字段；")
    lines.append("`participation_bases`、逐字证据、事件片段、`canonical_event` 全部保持原值。")
    lines.append("")
    lines.append("> ⚠️ **待研究者确认**：`participation_bases` 的新值你还没有指定。")
    lines.append("> 目前 2 条改判仍是 `COLLECTIVE_WITH_ROLE`。按 `DE004` 先例，改 `NARRATED_CONTEXT` 通常配 ")
    lines.append("> `THIRD_PARTY_ONLY`；改 `UNCERTAIN` 通常配 `INSUFFICIENT_EVIDENCE`。")
    lines.append("> 你给出取值后我重新生成导入视图即可（原始结果始终不动）。")
    lines.append("")
    if pending:
        lines.append("## 三、暂缓项（本次不落盘）")
        lines.append("")
        for r in pending:
            lines.append(
                f"- `[{r['index']}]` `{r['event_id']}`：补上下文后再裁"
                + (f"；备注 {r['remark']}" if r["remark"] else "")
            )
        lines.append("")
    lines.append("## 四、文档级指标变化")
    lines.append("")
    lines.append("| 文档 | 个人（前→后） | 背景（前→后） | 不确定（前→后） | 待复核（前→后） |")
    lines.append("|---|---|---|---|---|")
    for s in doc_summaries:
        b, a = s["before"], s["after"]
        lines.append(
            f"| `{s['doc']}` | {b['personal_event_count']}→{a['personal_event_count']} "
            f"| {b['context_event_count']}→{a['context_event_count']} "
            f"| {b['uncertain_event_count']}→{a['uncertain_event_count']} "
            f"| {b['needs_review_count']}→{a['needs_review_count']} |"
        )
    lines.append("")
    lines.append("## 五、文件与状态")
    lines.append("")
    lines.append("| 用途 | 路径 |")
    lines.append("|---|---|")
    lines.append(f"| 裁决来源清单 | `review/{checklist.name}` |")
    lines.append(f"| 模型原始结果（**未改动**） | `validated_json/{mdir}/` |")
    for w in written:
        lines.append(f"| 人工导入视图（本次新建） | `{w.relative_to(ROOT)}` |")
    lines.append("")
    lines.append("## 六、本轮未做的操作")
    lines.append("")
    lines.append("- 未修改 `validated_json/` 与 `raw_responses/` 的任何模型输出；")
    lines.append("- 未改动冻结的提示词／契约／Schema／校验器，未调用 API、未重跑；")
    lines.append("- 未填写 `01_实验配置/双线批改台账.csv` 的人工列（`human_review_status` / `release_status` / `notes`），仍由研究者填写；")
    lines.append("- 暂缓项未生成改判；所有结果在人工放行前仍为 `MODEL_CANDIDATE`。")
    lines.append("")
    lines.append("如需撤回：删除本次新建的导入视图即可，原始结果完全不受影响。")

    note_path = BASE / "review" / f"{args.batch}_{mdir}_范围裁决单_20261107.md"
    note_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    written.append(note_path)
    print("\n已写入：")
    for w in written:
        print(f"  {w.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
