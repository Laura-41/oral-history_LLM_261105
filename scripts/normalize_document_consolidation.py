#!/usr/bin/env python3
"""将已知的等价文档归并输出结构规范化为Schema v1.0。"""

from __future__ import annotations

import copy
from typing import Any


CANONICAL_TOP_FIELDS = {
    "schema_version",
    "technical_document_id",
    "document_id",
    "interviewee",
    "document_events",
    "candidate_decisions",
}
ALTERNATIVE_TOP_FIELDS = {
    "packet_version",
    "technical_document_id",
    "document_id",
    "interviewee",
    "candidate_decisions",
    "canonical_events",
}
ALTERNATIVE_DECISION_FIELDS = {
    "candidate_id",
    "action",
    "canonical_event_ids",
    "source_segment_ids",
    "reason",
}
EVENT_FIELDS = {
    "event_name",
    "event_type",
    "event_type_zh",
    "core_process",
    "participants",
    "circumstances",
    "projected_content",
    "evidence_quote",
    "type_basis",
    "alternative_event_type",
    "ambiguity_reason",
    "review_status",
}
ALTERNATIVE_EVENT_EXTRA_FIELDS = {
    "event_id",
    "experience_scope",
    "participation_bases",
    "completeness",
    "source_segment_ids",
    "scope_evidence_quote",
    "scope_evidence_segment_ids",
    "source_candidate_ids",
}


def normalize_document_consolidation_output(
    output: Any,
) -> tuple[Any, bool]:
    """返回(规范化输出, 是否应用了兼容转换)。"""
    if not isinstance(output, dict):
        return output, False
    if set(output) == CANONICAL_TOP_FIELDS:
        return copy.deepcopy(output), False
    if set(output) != ALTERNATIVE_TOP_FIELDS:
        raise ValueError("顶层不是Schema v1.0或已知等价结构")
    if output.get("packet_version") != "document-consolidation-output-v1.0":
        raise ValueError("未知的等价输出版本")

    document_events: list[dict[str, Any]] = []
    canonical_events = output.get("canonical_events")
    if not isinstance(canonical_events, list):
        raise ValueError("canonical_events必须是数组")
    expected_event_fields = EVENT_FIELDS | ALTERNATIVE_EVENT_EXTRA_FIELDS
    for index, item in enumerate(canonical_events):
        if not isinstance(item, dict) or set(item) != expected_event_fields:
            raise ValueError(f"canonical_events[{index}]字段不符合已知结构")
        document_status = item["review_status"]
        if document_status not in {"AUTO_VALIDATED", "NEEDS_REVIEW"}:
            raise ValueError(f"canonical_events[{index}].review_status无效")
        canonical_event = {key: copy.deepcopy(item[key]) for key in EVENT_FIELDS}
        canonical_event["review_status"] = (
            "NEEDS_REVIEW"
            if document_status == "NEEDS_REVIEW"
            else "MODEL_CANDIDATE"
        )
        review_reason = None
        if document_status == "NEEDS_REVIEW":
            review_reason = item.get("ambiguity_reason") or "模型标记需人工复核。"
        document_events.append(
            {
                "document_event_id": item["event_id"],
                "source_candidate_ids": copy.deepcopy(
                    item["source_candidate_ids"]
                ),
                "source_segment_ids": copy.deepcopy(item["source_segment_ids"]),
                "experience_scope": item["experience_scope"],
                "participation_bases": copy.deepcopy(
                    item["participation_bases"]
                ),
                "scope_evidence_segment_ids": copy.deepcopy(
                    item["scope_evidence_segment_ids"]
                ),
                "scope_evidence_quote": item["scope_evidence_quote"],
                "completeness": item["completeness"],
                "canonical_event": canonical_event,
                "review_status": document_status,
                "review_reason": review_reason,
            }
        )

    candidate_decisions: list[dict[str, Any]] = []
    decisions = output.get("candidate_decisions")
    if not isinstance(decisions, list):
        raise ValueError("candidate_decisions必须是数组")
    for index, item in enumerate(decisions):
        if not isinstance(item, dict) or set(item) != ALTERNATIVE_DECISION_FIELDS:
            raise ValueError(f"candidate_decisions[{index}]字段不符合已知结构")
        candidate_decisions.append(
            {
                "candidate_id": item["candidate_id"],
                "action": item["action"],
                "document_event_ids": copy.deepcopy(item["canonical_event_ids"]),
                "reason": item["reason"],
            }
        )

    return (
        {
            "schema_version": "document-consolidation-v1.0",
            "technical_document_id": output["technical_document_id"],
            "document_id": output["document_id"],
            "interviewee": output["interviewee"],
            "document_events": document_events,
            "candidate_decisions": candidate_decisions,
        },
        True,
    )
