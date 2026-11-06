#!/usr/bin/env python3
"""生成／更新「双线批改台账」：一行 = 一份文档 × 一个模型。

与实验登记表的关系：
  - 登记表一行 = 一次 API 调用（窗口级 4–5 行 + 文档级 1 行）；
  - 本台账一行 = 一份文档在一个模型下的完整交卷情况，用
    technical_document_id + model_id 与登记表关联。

人工字段（human_review_status / release_status / notes）由研究者填写；
重跑本脚本会保留已填内容，只刷新客观技术列。不调用 API，不改动标注结果。

用法：python3 scripts/build_review_ledger.py
"""

from __future__ import annotations

import csv
import json
import os
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BATCH = ROOT / "04_54份正式语料批处理"
STAGE = BATCH / "document_consolidation"
SHEET = ROOT / "01_实验配置" / "实验登记表.csv"
LEDGER = ROOT / "01_实验配置" / "双线批改台账.csv"
MODELS = ("cuc/qwen", "cuc/deepseek")

FIELDS = [
    "batch_id",
    "technical_document_id",
    "document_title",
    "model_id",
    "run_track",
    "registry_runs",
    "window_calls",
    "window_technical_passed",
    "consolidation_calls",
    "total_tokens",
    "cost_cny",
    "document_events",
    "scope_personal",
    "scope_context",
    "scope_uncertain",
    "needs_review",
    "adjudicated",
    "paired_model_id",
    "paired_model_submitted",
    "paired_document_events",
    "review_reference",
    "adjudication_reference",
    "human_review_status",
    "release_status",
    "notes",
]

HUMAN_FIELDS = ("human_review_status", "release_status", "notes")
DEFAULTS = {
    "human_review_status": "待研究者填写",
    "release_status": "未放行（待抽检）",
    "notes": "",
}


def rel(path: Path) -> str:
    return os.path.relpath(path, ROOT)


def document_title(model_dir: str, doc: str) -> str:
    for path in sorted((BATCH / "raw_responses" / model_dir).glob(f"*{doc}-W*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        return record.get("document_id", "")
    for path in sorted((STAGE / "raw_responses" / model_dir).glob(f"*{doc}.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        return record.get("document_id", "")
    return ""


def review_references(doc: str, model_dir: str) -> tuple[str, str]:
    """只引用本报告所属模型的抽检文档，避免跨模型串口径。

    命名约定：Qwen 报告含 "qwen"；DeepSeek 的历史抽检报告为 v0.x 版本
    或批次技术验证，均不含 "qwen"。
    """
    def normalized(text: str) -> str:
        return text.lower().replace("_", "-")

    reviews = sorted(
        p for p in list((STAGE / "review").glob("*.md")) + list(BATCH.glob("*.md"))
        if normalized(doc) in normalized(p.name)
    )
    is_qwen = model_dir == "cuc_qwen"
    own = [p for p in reviews if ("qwen" in p.name.lower()) == is_qwen]
    picked = own[-2:] if own else []
    report = "; ".join(rel(p) for p in picked)
    adjudication = ""
    adj = STAGE / "human_adjudicated" / model_dir / f"{doc}.json"
    if adj.exists():
        adjudication = rel(adj)
    return report, adjudication


def main() -> int:
    with SHEET.open(encoding="utf-8-sig", newline="") as handle:
        registry = list(csv.DictReader(handle))

    previous: dict[tuple[str, str], dict] = {}
    if LEDGER.exists():
        with LEDGER.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                previous[(row["technical_document_id"], row["model_id"])] = row

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in registry:
        doc = re.sub(r"-W\d+$", "", row["document_id"])
        if not re.fullmatch(r"BATCH\d{2}-DOC\d{2}", doc):
            continue
        groups[(doc, row["model_id"])].append(row)

    all_docs = sorted({doc for doc, _ in groups})
    rows: list[dict] = []
    for doc in all_docs:
        submitted = {m for m in MODELS if (doc, m) in groups}
        for model in MODELS:
            if (doc, model) not in groups:
                continue
            runs = groups[(doc, model)]
            model_dir = model.replace("/", "_")
            window_runs = [r for r in runs if r["stage"] == "FORMAL_BATCH_WINDOW_EXTRACTION"]
            stage_runs = [r for r in runs if r["stage"] == "DOCUMENT_CONSOLIDATION_AND_SCOPE"]
            passed = sum(1 for r in window_runs if r["result_status"].startswith("PASSED"))

            result_path = STAGE / "validated_json" / model_dir / f"{doc}.json"
            events = personal = context = uncertain = needs_review = ""
            if result_path.exists():
                payload = json.loads(result_path.read_text(encoding="utf-8"))
                item_list = payload["consolidated_output"]["document_events"]
                events = len(item_list)
                personal = sum(1 for e in item_list if e["experience_scope"] == "PERSONAL_EXPERIENCE")
                context = sum(1 for e in item_list if e["experience_scope"] == "NARRATED_CONTEXT")
                uncertain = sum(1 for e in item_list if e["experience_scope"] == "UNCERTAIN")
                needs_review = sum(1 for e in item_list if e["review_status"] == "NEEDS_REVIEW")

            adj_path = STAGE / "human_adjudicated" / model_dir / f"{doc}.json"
            adjudicated = ""
            if adj_path.exists():
                payload = json.loads(adj_path.read_text(encoding="utf-8"))
                after = payload.get("metrics_after_adjudication", {})
                adjudicated = (
                    f"是；裁决后 个人{after.get('personal_event_count')}"
                    f"／背景{after.get('context_event_count')}"
                    f"／待复核{after.get('needs_review_count')}"
                )

            other = next((m for m in MODELS if m != model), "")
            other_events = ""
            other_path = STAGE / "validated_json" / other.replace("/", "_") / f"{doc}.json"
            if other_path.exists():
                payload = json.loads(other_path.read_text(encoding="utf-8"))
                other_events = len(payload["consolidated_output"]["document_events"])

            report, adjudication_ref = review_references(doc, model_dir)
            track = "QWEN_MAIN_TRACK" if model == "cuc/qwen" else "DEEPSEEK_PARALLEL_TRACK"
            key = (doc, model)
            row = {
                "batch_id": doc.split("-")[0],
                "technical_document_id": doc,
                "document_title": document_title(model_dir, doc),
                "model_id": model,
                "run_track": track,
                "registry_runs": len(runs),
                "window_calls": len(window_runs),
                "window_technical_passed": f"{passed}/{len(window_runs)}" if window_runs else "",
                "consolidation_calls": len(stage_runs),
                "total_tokens": sum(int(r["total_tokens"]) for r in runs if r["total_tokens"]),
                "cost_cny": f"{sum(float(r['cost_cny']) for r in runs if r['cost_cny']):.6f}",
                "document_events": events,
                "scope_personal": personal,
                "scope_context": context,
                "scope_uncertain": uncertain,
                "needs_review": needs_review,
                "adjudicated": adjudicated,
                "paired_model_id": other,
                "paired_model_submitted": "已交卷" if other in submitted else "未交卷（待补跑）",
                "paired_document_events": other_events,
                "review_reference": report,
                "adjudication_reference": adjudication_ref,
            }
            for field in HUMAN_FIELDS:
                row[field] = (previous.get(key, {}).get(field) or DEFAULTS[field])
            rows.append(row)

    with LEDGER.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print(f"已生成 {rel(LEDGER)}：{len(rows)} 行 / {len(FIELDS)} 列")
    print("覆盖文档：", ", ".join(all_docs))
    for row in rows:
        print(
            f"  {row['technical_document_id']} / {row['model_id']:13s}"
            f" | 窗口{row['window_technical_passed']} | 事件{row['document_events']}"
            f" | 个人{row['scope_personal']} 背景{row['scope_context']}"
            f" | 配对{row['paired_model_submitted']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
