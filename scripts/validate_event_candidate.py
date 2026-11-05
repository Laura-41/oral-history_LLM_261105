#!/usr/bin/env python3
"""无第三方依赖的候选事件核心约束校验器。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EVENT_TYPE_ZH = {
    "MATERIAL": "物质",
    "MENTAL": "心理",
    "RELATIONAL": "关系",
    "VERBAL": "言语",
    "BEHAVIORAL": "行为",
    "EXISTENTIAL": "存在",
}

ALLOWED_ROLES = {
    "MATERIAL": {"Actor", "Goal", "Client", "Recipient", "Scope"},
    "MENTAL": {"Senser", "Phenomenon"},
    "RELATIONAL": {"Carrier", "Attribute", "Token", "Value"},
    "VERBAL": {"Sayer", "Receiver", "Target", "Verbiage"},
    "BEHAVIORAL": {"Behaver", "BehaviourScope"},
    "EXISTENTIAL": {"Existent"},
}

REQUIRED_ROLE_SETS = {
    "MATERIAL": ({"Actor"},),
    "MENTAL": ({"Senser", "Phenomenon"},),
    "RELATIONAL": ({"Carrier", "Attribute"}, {"Token", "Value"}),
    "VERBAL": ({"Sayer"},),
    "BEHAVIORAL": ({"Behaver"},),
    "EXISTENTIAL": ({"Existent"},),
}

TOP_LEVEL_FIELDS = {
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

CIRCUMSTANCE_KINDS = {
    "TIME",
    "LOCATION",
    "MANNER",
    "CAUSE",
    "PURPOSE",
    "CONTENT",
    "DIRECTION",
    "OTHER",
}


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_event(event: Any, expected_evidence: str | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(event, dict):
        return ["顶层必须是JSON对象"]

    missing = TOP_LEVEL_FIELDS - set(event)
    extra = set(event) - TOP_LEVEL_FIELDS
    if missing:
        errors.append(f"缺少字段：{', '.join(sorted(missing))}")
    if extra:
        errors.append(f"存在未定义字段：{', '.join(sorted(extra))}")

    event_type = event.get("event_type")
    if event_type not in EVENT_TYPE_ZH:
        errors.append(f"event_type无效：{event_type!r}")
        allowed_roles: set[str] = set()
    else:
        allowed_roles = ALLOWED_ROLES[event_type]
        if event.get("event_type_zh") != EVENT_TYPE_ZH[event_type]:
            errors.append("event_type与event_type_zh不一致")

    for field in ("event_name", "core_process", "evidence_quote", "type_basis"):
        if not nonempty_string(event.get(field)):
            errors.append(f"{field}必须是非空字符串")

    if expected_evidence is not None and event.get("evidence_quote") != expected_evidence:
        errors.append("evidence_quote与测试原文不逐字一致")

    participants = event.get("participants")
    roles: list[str] = []
    if not isinstance(participants, list):
        errors.append("participants必须是数组")
    else:
        for index, participant in enumerate(participants):
            prefix = f"participants[{index}]"
            if not isinstance(participant, dict):
                errors.append(f"{prefix}必须是对象")
                continue
            if set(participant) != {"role", "mention", "normalized_entity", "certainty"}:
                errors.append(f"{prefix}字段不完整或存在额外字段")
            role = participant.get("role")
            roles.append(role)
            if role not in allowed_roles:
                errors.append(f"{prefix}.role不属于{event_type}封闭词表：{role!r}")
            if not nonempty_string(participant.get("mention")):
                errors.append(f"{prefix}.mention必须是非空字符串")
            if participant.get("normalized_entity") is not None and not isinstance(
                participant.get("normalized_entity"), str
            ):
                errors.append(f"{prefix}.normalized_entity必须是字符串或null")
            if participant.get("certainty") not in {"HIGH", "MEDIUM", "LOW"}:
                errors.append(f"{prefix}.certainty无效")

    if event_type in REQUIRED_ROLE_SETS:
        role_set = set(roles)
        matches = [required <= role_set for required in REQUIRED_ROLE_SETS[event_type]]
        if event_type == "RELATIONAL":
            if sum(matches) != 1:
                errors.append("RELATIONAL必须且只能使用Carrier＋Attribute或Token＋Value中的一组")
        elif not any(matches):
            required_text = " 或 ".join(
                "＋".join(sorted(required))
                for required in REQUIRED_ROLE_SETS[event_type]
            )
            errors.append(f"{event_type}缺少必需角色：{required_text}")

    circumstances = event.get("circumstances")
    if not isinstance(circumstances, list):
        errors.append("circumstances必须是数组")
    else:
        for index, circumstance in enumerate(circumstances):
            prefix = f"circumstances[{index}]"
            if not isinstance(circumstance, dict):
                errors.append(f"{prefix}必须是对象")
                continue
            if set(circumstance) != {"kind", "value", "normalized_value"}:
                errors.append(f"{prefix}字段不完整或存在额外字段")
            if circumstance.get("kind") not in CIRCUMSTANCE_KINDS:
                errors.append(f"{prefix}.kind无效")
            if not nonempty_string(circumstance.get("value")):
                errors.append(f"{prefix}.value必须是非空字符串")
            if circumstance.get("normalized_value") is not None and not isinstance(
                circumstance.get("normalized_value"), str
            ):
                errors.append(f"{prefix}.normalized_value必须是字符串或null")

    for field in ("projected_content", "ambiguity_reason"):
        if event.get(field) is not None and not isinstance(event.get(field), str):
            errors.append(f"{field}必须是字符串或null")

    alternative = event.get("alternative_event_type")
    if alternative is not None and alternative not in EVENT_TYPE_ZH:
        errors.append("alternative_event_type无效")
    if event.get("review_status") not in {"MODEL_CANDIDATE", "NEEDS_REVIEW"}:
        errors.append("review_status无效")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校验候选事件JSON核心约束")
    parser.add_argument("paths", nargs="+", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failed = 0
    for path in args.paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"失败 {path}: {exc}")
            failed += 1
            continue
        if isinstance(data, dict) and "parsed_output" in data:
            event = data.get("parsed_output")
            expected_evidence = data.get("source_text")
        else:
            event = data
            expected_evidence = None
        errors = validate_event(event, expected_evidence)
        if errors:
            failed += 1
            print(f"失败 {path}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"通过 {path}")
    print(f"\n校验完成：{len(args.paths) - failed}/{len(args.paths)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
