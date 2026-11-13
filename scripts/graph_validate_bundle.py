#!/usr/bin/env python3
"""图谱补齐验收：复用六份人工 Demo 的完整性校验器，并追加工程侧检查（零 API）。

用法：
    python3 scripts/graph_validate_bundle.py --document BATCH02-DOC01 --model cuc/qwen
    python3 scripts/graph_validate_bundle.py --document BATCH02-DOC01 --model cuc/qwen --write-report
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(PROJECT_DIR.parent / "现行标注" / "脚本"))

from validate_annotation_bundle import TABLES as DEMO_TABLES  # noqa: E402
from validate_annotation_bundle import validate as demo_validate  # noqa: E402
from graph_build_base_tables import (  # noqa: E402
    GRAPH_ROOT,
    TEMPLATE_DIR,
    display_path,
    safe_model_name,
)


def check_headers(folder: Path) -> list[str]:
    errors = []
    for table in DEMO_TABLES:
        path = folder / f"{table}.csv"
        if not path.exists():
            errors.append(f"缺表 {table}.csv")
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            actual = next(csv.reader(handle), [])
        with (TEMPLATE_DIR / f"{table}.csv").open(encoding="utf-8-sig", newline="") as handle:
            expected = next(csv.reader(handle), [])
        if actual != expected:
            errors.append(f"{table}.csv 表头与人工模板不一致")
    return errors


def check_stage_boundary(folder: Path) -> list[str]:
    """自上而下路线锁定：二级阶段引用的原文片段，不得越出所属一级事件的片段集合。

    研究者 2026-11-07 19:57 裁决「技术路线以自上而下为准，之前的不动」：
    一级事件边界已经确认，阶段只能在这条事件内部拆分，不能借阶段之名改动一级边界。
    人工校验器只查 stage_next 是否跨事件、阶段是否引用已知事件，未查此项，故在此补。
    没有阶段数据时返回空列表（缺表由 check_headers / demo_validate 报）。
    """
    path = folder / "source_attachments.csv"
    stages_path = folder / "process_stages.csv"
    if not path.exists() or not stages_path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        attachments = list(csv.DictReader(handle))
    with stages_path.open(encoding="utf-8-sig", newline="") as handle:
        stages = list(csv.DictReader(handle))

    event_segments: dict[str, set[str]] = defaultdict(set)
    stage_segments: dict[str, set[str]] = defaultdict(set)
    stage_to_event = {row["stage_id"]: row["event_id"] for row in stages}
    for row in attachments:
        if row.get("target_type") == "EVENT":
            event_segments[row.get("target_id", "")].add(row.get("segment_id", ""))
        elif row.get("target_type") == "STAGE":
            stage_segments[row.get("target_id", "")].add(row.get("segment_id", ""))

    errors = []
    for stage_id, segs in sorted(stage_segments.items()):
        event_id = stage_to_event.get(stage_id)
        if not event_id:
            continue  # 未知阶段由人工校验器报错
        outside = sorted(segs - event_segments.get(event_id, set()))
        if outside:
            errors.append(
                f"阶段 {stage_id} 越出一级事件 {event_id} 的原文边界：{', '.join(outside)}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", required=True)
    parser.add_argument("--model", default="cuc/qwen")
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    folder = GRAPH_ROOT / safe_model_name(args.model) / args.document
    if not folder.exists():
        print(f"失败：找不到 {folder}", file=sys.stderr)
        return 2

    extra: list[str] = check_headers(folder) + check_stage_boundary(folder)
    try:
        result: dict[str, Any] = demo_validate(folder)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"人工校验器执行失败：{exc}", file=sys.stderr)
        return 2
    errors = list(result.get("errors", [])) + extra

    l0 = folder / "L0_report.json"
    l12 = folder / "L1L2_report.json"
    if not l0.exists():
        errors.append("缺 L0_report.json")
    if not l12.exists():
        errors.append("缺 L1L2_report.json")
    else:
        report = json.loads(l12.read_text(encoding="utf-8"))
        if not report.get("complete"):
            errors.append("L1/L2 原始响应不齐全，未达端到端验证要求")
        if report.get("model_id") != args.model:
            errors.append(f"模型线不一致：报告={report.get('model_id')}，本次={args.model}")
    if l0.exists():
        report0 = json.loads(l0.read_text(encoding="utf-8"))
        if report0.get("model_id") != args.model:
            errors.append(f"L0 模型线不一致：{report0.get('model_id')}")

    if result.get("coverage_rate") != "1.0000":
        errors.append("覆盖率不是 1.0000")

    report_out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "technical_document_id": args.document,
        "model_id": args.model,
        "layer": "GRAPH_VALIDATION",
        "demo_validator": result,
        "extra_errors": extra,
        "all_errors": errors,
        "valid": not errors,
        "api_calls": 0,
    }
    print(f"{'[通过]' if not errors else '[未通过]'} {args.document} / {args.model}")
    print(f"  片段 {result.get('segments')}｜事件 {result.get('events')}｜阶段 {result.get('stages')}"
          f"｜实体 {result.get('entities')}｜提及 {result.get('entity_mentions')}"
          f"｜时间表达 {result.get('time_expressions')}｜覆盖率 {result.get('coverage_rate')}")
    if errors:
        for err in errors[:30]:
            print(f"  - {err}")
        if len(errors) > 30:
            print(f"  …… 另有 {len(errors) - 30} 条，详见报告")
    if args.write_report:
        (folder / "VALIDATION_report.json").write_text(
            json.dumps(report_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"  报告：{display_path(folder / 'VALIDATION_report.json')}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
