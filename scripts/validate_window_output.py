#!/usr/bin/env python3
"""校验连续窗口盲抽取的包装结构、片段覆盖和单事件Schema。"""

from __future__ import annotations

from typing import Any

from validate_event_candidate import validate_event


def validate_window_output(
    output: Any, packet: dict[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    metrics: dict[str, Any] = {
        "event_count": 0,
        "assigned_segment_count": 0,
        "unassigned_segment_count": 0,
        "input_segment_count": len(packet.get("source_segments", [])),
    }
    if not isinstance(output, dict):
        return ["顶层必须是JSON对象"], metrics
    if set(output) != {"window_id", "events", "unassigned_segment_ids"}:
        errors.append("顶层字段必须且只能是window_id、events、unassigned_segment_ids")
    if output.get("window_id") != packet.get("window_id"):
        errors.append("window_id与输入不一致")

    source_segments = packet.get("source_segments", [])
    input_ids = [row.get("segment_id") for row in source_segments]
    input_id_set = set(input_ids)
    text_by_id = {
        row.get("segment_id"): row.get("verbatim_text", "")
        for row in source_segments
    }

    events = output.get("events")
    candidate_ids: set[str] = set()
    assigned_ids: set[str] = set()
    if not isinstance(events, list):
        errors.append("events必须是数组")
        events = []
    metrics["event_count"] = len(events)
    for index, candidate in enumerate(events):
        prefix = f"events[{index}]"
        if not isinstance(candidate, dict):
            errors.append(f"{prefix}必须是对象")
            continue
        if set(candidate) != {"candidate_id", "source_segment_ids", "event"}:
            errors.append(
                f"{prefix}字段必须且只能是candidate_id、source_segment_ids、event"
            )
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            errors.append(f"{prefix}.candidate_id必须是非空字符串")
        elif candidate_id in candidate_ids:
            errors.append(f"{prefix}.candidate_id重复")
        else:
            candidate_ids.add(candidate_id)

        segment_ids = candidate.get("source_segment_ids")
        if not isinstance(segment_ids, list) or not segment_ids:
            errors.append(f"{prefix}.source_segment_ids必须是非空数组")
            segment_ids = []
        if len(segment_ids) != len(set(segment_ids)):
            errors.append(f"{prefix}.source_segment_ids存在重复")
        unknown_ids = set(segment_ids) - input_id_set
        if unknown_ids:
            errors.append(f"{prefix}.source_segment_ids存在输入外ID：{sorted(unknown_ids)}")
        expected_order = [segment_id for segment_id in input_ids if segment_id in segment_ids]
        if segment_ids != expected_order:
            errors.append(f"{prefix}.source_segment_ids未按输入顺序排列")
        assigned_ids.update(segment_ids)

        event = candidate.get("event")
        for event_error in validate_event(event):
            errors.append(f"{prefix}.event：{event_error}")
        if isinstance(event, dict):
            evidence_quote = event.get("evidence_quote")
            if isinstance(evidence_quote, str) and evidence_quote:
                if not any(
                    evidence_quote in text_by_id.get(segment_id, "")
                    for segment_id in segment_ids
                ):
                    errors.append(
                        f"{prefix}.event.evidence_quote不在该事件所列原文片段中"
                    )

    unassigned = output.get("unassigned_segment_ids")
    if not isinstance(unassigned, list):
        errors.append("unassigned_segment_ids必须是数组")
        unassigned = []
    if len(unassigned) != len(set(unassigned)):
        errors.append("unassigned_segment_ids存在重复")
    unknown_unassigned = set(unassigned) - input_id_set
    if unknown_unassigned:
        errors.append(f"unassigned_segment_ids存在输入外ID：{sorted(unknown_unassigned)}")
    overlap = assigned_ids & set(unassigned)
    if overlap:
        errors.append(f"片段同时被分配和未分配：{sorted(overlap)}")
    uncovered = input_id_set - assigned_ids - set(unassigned)
    if uncovered:
        errors.append(f"存在未处理输入片段：{sorted(uncovered)}")

    metrics["assigned_segment_count"] = len(assigned_ids)
    metrics["unassigned_segment_count"] = len(set(unassigned))
    metrics["all_input_segments_accounted_for"] = not uncovered
    return errors, metrics
