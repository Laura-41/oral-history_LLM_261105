#!/usr/bin/env python3
"""校验文档级归并、候选去向和个人经历范围输出。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from validate_event_candidate import validate_event  # noqa: E402


TOP_LEVEL_FIELDS = {
    "schema_version",
    "technical_document_id",
    "document_id",
    "interviewee",
    "document_events",
    "candidate_decisions",
}
DOCUMENT_EVENT_FIELDS = {
    "document_event_id",
    "source_candidate_ids",
    "source_segment_ids",
    "experience_scope",
    "participation_bases",
    "scope_evidence_segment_ids",
    "scope_evidence_quote",
    "completeness",
    "canonical_event",
    "review_status",
    "review_reason",
}
DECISION_FIELDS = {
    "candidate_id",
    "action",
    "document_event_ids",
    "reason",
}
SCOPES = {"PERSONAL_EXPERIENCE", "NARRATED_CONTEXT", "UNCERTAIN"}
BASES = {
    "DIRECT_FIRST_PERSON",
    "DIRECTLY_AFFECTED",
    "COLLECTIVE_WITH_ROLE",
    "COLLECTIVE_WITHOUT_ROLE",
    "REPORTED_BY_OTHERS",
    "EXPLICIT_NON_PARTICIPATION",
    "THIRD_PARTY_ONLY",
    "EDITORIAL_SOURCE",
    "INSUFFICIENT_EVIDENCE",
}
PERSONAL_BASES = {
    "DIRECT_FIRST_PERSON",
    "DIRECTLY_AFFECTED",
    "COLLECTIVE_WITH_ROLE",
}
ACTIONS = {
    "MERGED",
    "KEPT",
    "SPLIT",
    "CONTEXT_ONLY",
    "REJECTED_AS_NON_EVENT",
}


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_document_consolidation(
    output: Any, packet: dict[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    metrics: dict[str, Any] = {
        "input_candidate_count": len(packet.get("window_candidates", [])),
        "document_event_count": 0,
        "candidate_decision_count": 0,
        "personal_event_count": 0,
        "context_event_count": 0,
        "uncertain_event_count": 0,
        "needs_review_count": 0,
    }
    if not isinstance(output, dict):
        return ["顶层必须是JSON对象"], metrics
    if set(output) != TOP_LEVEL_FIELDS:
        errors.append("顶层字段不完整或存在额外字段")
    if output.get("schema_version") != "document-consolidation-v1.0":
        errors.append("schema_version必须为document-consolidation-v1.0")
    for field in ("technical_document_id", "document_id", "interviewee"):
        if output.get(field) != packet.get(field):
            errors.append(f"{field}与输入不一致")

    candidate_by_id = {
        row["candidate_id"]: row
        for row in packet.get("window_candidates", [])
    }
    segment_text = {
        row["segment_id"]: row["verbatim_text"]
        for row in packet.get("dialogue_segments", [])
    }

    events = output.get("document_events")
    if not isinstance(events, list):
        errors.append("document_events必须是数组")
        events = []
    metrics["document_event_count"] = len(events)
    event_by_id: dict[str, dict[str, Any]] = {}
    event_candidate_links: set[tuple[str, str]] = set()
    for index, row in enumerate(events):
        prefix = f"document_events[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix}必须是对象")
            continue
        if set(row) != DOCUMENT_EVENT_FIELDS:
            errors.append(f"{prefix}字段不完整或存在额外字段")
        event_id = row.get("document_event_id")
        if not nonempty_string(event_id):
            errors.append(f"{prefix}.document_event_id必须是非空字符串")
            continue
        if event_id in event_by_id:
            errors.append(f"{prefix}.document_event_id重复")
        event_by_id[event_id] = row

        candidate_ids = row.get("source_candidate_ids")
        if not isinstance(candidate_ids, list) or not candidate_ids:
            errors.append(f"{prefix}.source_candidate_ids必须是非空数组")
            candidate_ids = []
        if len(candidate_ids) != len(set(candidate_ids)):
            errors.append(f"{prefix}.source_candidate_ids存在重复")
        unknown_candidates = set(candidate_ids) - set(candidate_by_id)
        if unknown_candidates:
            errors.append(
                f"{prefix}.source_candidate_ids存在输入外ID："
                f"{sorted(unknown_candidates)}"
            )
        for candidate_id in candidate_ids:
            event_candidate_links.add((candidate_id, event_id))

        source_ids = row.get("source_segment_ids")
        if not isinstance(source_ids, list) or not source_ids:
            errors.append(f"{prefix}.source_segment_ids必须是非空数组")
            source_ids = []
        if len(source_ids) != len(set(source_ids)):
            errors.append(f"{prefix}.source_segment_ids存在重复")
        unknown_segments = set(source_ids) - set(segment_text)
        if unknown_segments:
            errors.append(
                f"{prefix}.source_segment_ids存在输入外ID："
                f"{sorted(unknown_segments)}"
            )

        scope = row.get("experience_scope")
        if scope not in SCOPES:
            errors.append(f"{prefix}.experience_scope无效")
        else:
            key = {
                "PERSONAL_EXPERIENCE": "personal_event_count",
                "NARRATED_CONTEXT": "context_event_count",
                "UNCERTAIN": "uncertain_event_count",
            }[scope]
            metrics[key] += 1

        bases = row.get("participation_bases")
        if not isinstance(bases, list) or not bases:
            errors.append(f"{prefix}.participation_bases必须是非空数组")
            bases = []
        if len(bases) != len(set(bases)):
            errors.append(f"{prefix}.participation_bases存在重复")
        if set(bases) - BASES:
            errors.append(f"{prefix}.participation_bases存在表外值")
        if scope == "PERSONAL_EXPERIENCE" and not (set(bases) & PERSONAL_BASES):
            errors.append(
                f"{prefix}为PERSONAL_EXPERIENCE但缺少直接参与依据"
            )
        if scope == "PERSONAL_EXPERIENCE" and set(bases) & {
            "EXPLICIT_NON_PARTICIPATION",
            "THIRD_PARTY_ONLY",
        }:
            errors.append(
                f"{prefix}个人经历与明确未参与/纯他人主体矛盾"
            )

        scope_ids = row.get("scope_evidence_segment_ids")
        if not isinstance(scope_ids, list) or not scope_ids:
            errors.append(
                f"{prefix}.scope_evidence_segment_ids必须是非空数组"
            )
            scope_ids = []
        if len(scope_ids) != len(set(scope_ids)):
            errors.append(f"{prefix}.scope_evidence_segment_ids存在重复")
        if set(scope_ids) - set(segment_text):
            errors.append(f"{prefix}.scope_evidence_segment_ids存在输入外ID")
        scope_quote = row.get("scope_evidence_quote")
        if not nonempty_string(scope_quote):
            errors.append(f"{prefix}.scope_evidence_quote必须是非空字符串")
        elif not any(scope_quote in segment_text.get(sid, "") for sid in scope_ids):
            errors.append(f"{prefix}.scope_evidence_quote不在所列原文片段中")

        if row.get("completeness") not in {"COMPLETE", "INCOMPLETE", "UNCERTAIN"}:
            errors.append(f"{prefix}.completeness无效")
        for event_error in validate_event(row.get("canonical_event")):
            errors.append(f"{prefix}.canonical_event：{event_error}")
        canonical = row.get("canonical_event")
        if isinstance(canonical, dict):
            quote = canonical.get("evidence_quote")
            if nonempty_string(quote) and not any(
                quote in segment_text.get(sid, "") for sid in source_ids
            ):
                errors.append(
                    f"{prefix}.canonical_event.evidence_quote"
                    "不在所列事件片段中"
                )

        review_status = row.get("review_status")
        if review_status not in {"AUTO_VALIDATED", "NEEDS_REVIEW"}:
            errors.append(f"{prefix}.review_status无效")
        if review_status == "NEEDS_REVIEW":
            metrics["needs_review_count"] += 1
            if not nonempty_string(row.get("review_reason")):
                errors.append(f"{prefix}.NEEDS_REVIEW必须填review_reason")
        if review_status == "AUTO_VALIDATED":
            if scope == "UNCERTAIN" or row.get("completeness") != "COMPLETE":
                errors.append(
                    f"{prefix}.AUTO_VALIDATED不能用于范围或完整性不确定项"
                )
            if row.get("review_reason") is not None:
                errors.append(f"{prefix}.AUTO_VALIDATED的review_reason应为null")

    decisions = output.get("candidate_decisions")
    if not isinstance(decisions, list):
        errors.append("candidate_decisions必须是数组")
        decisions = []
    metrics["candidate_decision_count"] = len(decisions)
    decision_ids: set[str] = set()
    decision_links: set[tuple[str, str]] = set()
    for index, row in enumerate(decisions):
        prefix = f"candidate_decisions[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix}必须是对象")
            continue
        if set(row) != DECISION_FIELDS:
            errors.append(f"{prefix}字段不完整或存在额外字段")
        candidate_id = row.get("candidate_id")
        if candidate_id not in candidate_by_id:
            errors.append(f"{prefix}.candidate_id不在输入候选中")
        if candidate_id in decision_ids:
            errors.append(f"{prefix}.candidate_id重复决策")
        if isinstance(candidate_id, str):
            decision_ids.add(candidate_id)
        action = row.get("action")
        if action not in ACTIONS:
            errors.append(f"{prefix}.action无效")
        target_ids = row.get("document_event_ids")
        if not isinstance(target_ids, list):
            errors.append(f"{prefix}.document_event_ids必须是数组")
            target_ids = []
        if len(target_ids) != len(set(target_ids)):
            errors.append(f"{prefix}.document_event_ids存在重复")
        if set(target_ids) - set(event_by_id):
            errors.append(f"{prefix}.document_event_ids存在未定义事件")
        for event_id in target_ids:
            decision_links.add((candidate_id, event_id))
        if action == "REJECTED_AS_NON_EVENT" and target_ids:
            errors.append(f"{prefix}REJECTED_AS_NON_EVENT不得指向文档事件")
        if action != "REJECTED_AS_NON_EVENT" and not target_ids:
            errors.append(f"{prefix}非拒绝决策必须指向文档事件")
        if action in {"KEPT", "CONTEXT_ONLY"} and len(target_ids) != 1:
            errors.append(f"{prefix}{action}必须恰好指向一个文档事件")
        if action == "SPLIT" and len(target_ids) < 2:
            errors.append(f"{prefix}SPLIT必须指向至少两个文档事件")
        if action == "CONTEXT_ONLY" and target_ids:
            if event_by_id.get(target_ids[0], {}).get("experience_scope") != "NARRATED_CONTEXT":
                errors.append(f"{prefix}CONTEXT_ONLY必须指向NARRATED_CONTEXT")
        if not nonempty_string(row.get("reason")):
            errors.append(f"{prefix}.reason必须是非空字符串")

    expected_ids = set(candidate_by_id)
    if decision_ids != expected_ids:
        errors.append(
            "candidate_decisions未恰好覆盖全部输入候选："
            f"missing={sorted(expected_ids - decision_ids)}, "
            f"extra={sorted(decision_ids - expected_ids)}"
        )
    if decision_links != event_candidate_links:
        errors.append("候选决策与文档事件的来源候选链接不一致")
    referenced_event_ids = {event_id for _, event_id in decision_links}
    orphan_events = set(event_by_id) - referenced_event_ids
    if orphan_events:
        errors.append(f"存在无候选来源的文档事件：{sorted(orphan_events)}")
    return errors, metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="校验文档级归并与经历范围输出"
    )
    parser.add_argument("output", type=Path)
    parser.add_argument("packet", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output = json.loads(args.output.read_text(encoding="utf-8"))
        packet = json.loads(args.packet.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读取失败：{exc}", file=sys.stderr)
        return 2
    errors, metrics = validate_document_consolidation(output, packet)
    if errors:
        print("校验失败：")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("校验通过：" + json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
