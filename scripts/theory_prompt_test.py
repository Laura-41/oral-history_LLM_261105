#!/usr/bin/env python3
"""使用项目操作性提示词测试单句事件分类。

第一次默认只测试“到上海印书馆做排字工人”，验证裸提示词的类型错误
是否得到纠正。密钥优先从环境变量读取，缺失时从macOS钥匙串读取。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
PROMPT_DIR = PROJECT_DIR / "02_Schema与提示词"
RESULT_DIR = PROJECT_DIR / "03_六份Demo对照实验" / "理论提示词最小测试"

sys.path.insert(0, str(SCRIPT_DIR))
from api_test import (  # noqa: E402
    extract_content,
    get_api_key,
    print_usage,
    request_json,
)


TEST_CASES: dict[str, dict[str, Any]] = {
    "material_work": {
        "text": "1931年他到上海印书馆做排字工人。",
        "expected_type": "MATERIAL",
        "reason": "突出到达并从事职业劳动。",
        "expected_roles": ["Actor"],
        "forbidden_roles": ["Scope"],
    },
    "mental": {
        "text": "他想起了在家乡的哥哥。",
        "expected_type": "MENTAL",
        "reason": "内在认知过程及其现象。",
        "expected_roles": ["Senser", "Phenomenon"],
    },
    "relational": {
        "text": "他是印书馆的排字工人。",
        "expected_type": "RELATIONAL",
        "reason": "建立职业身份。",
    },
    "verbal": {
        "text": "他告诉我部队已经出发了。",
        "expected_type": "VERBAL",
        "reason": "有言说者、受话者和明确言语内容。",
        "expected_roles": ["Sayer", "Receiver"],
        "forbidden_roles": ["Verbiage"],
        "forbidden_circumstances": [{"kind": "CONTENT", "value": "部队已经出发"}],
        "required_projected_text": "部队已经出发",
    },
    "behavioral": {
        "text": "他听完以后笑了笑。",
        "expected_type": "BEHAVIORAL",
        "reason": "情感状态的可见外显。",
        "expected_roles": ["Behaver"],
        "forbidden_roles": ["Actor"],
    },
    "existential": {
        "text": "村里出现了一支队伍。",
        "expected_type": "EXISTENTIAL",
        "reason": "引入存在者的出现。",
        "expected_roles": ["Existent"],
    },
    "relational_attributive": {
        "text": "他是一名排字工人。",
        "expected_type": "RELATIONAL",
        "reason": "把人物归入职业类别，属于归属式而非识别式。",
        "expected_roles": ["Carrier", "Attribute"],
        "forbidden_roles": ["Token", "Value"],
    },
    "relational_identifying": {
        "text": "他就是印书馆里那位唯一的排字工人。",
        "expected_type": "RELATIONAL",
        "reason": "确定特定身份，属于识别式。",
        "expected_roles": ["Token", "Value"],
        "forbidden_roles": ["Carrier", "Attribute"],
    },
    "mental_perception": {
        "text": "他看见远处来了一支队伍。",
        "expected_type": "MENTAL",
        "reason": "表达感知结果及其现象。",
        "expected_roles": ["Senser", "Phenomenon"],
        "forbidden_circumstances": [
            {"kind": "LOCATION", "value": "远处"},
            {"kind": "DIRECTION", "value": "远处"},
        ],
    },
    "behavioral_perception": {
        "text": "他一直望着远处。",
        "expected_type": "BEHAVIORAL",
        "reason": "突出可观察的感知行为，未陈述感知结果。",
        "expected_roles": ["Behaver"],
        "forbidden_roles": ["Senser", "Phenomenon"],
        "expected_circumstances": [{"kind": "DIRECTION", "value": "远处"}],
        "forbidden_circumstances": [{"kind": "LOCATION", "value": "远处"}],
    },
    "behavioral_chat": {
        "text": "他们在路上闲谈了一会儿。",
        "expected_type": "BEHAVIORAL",
        "reason": "只突出交谈行为，没有明确命题内容。",
        "expected_roles": ["Behaver"],
        "forbidden_roles": ["Sayer", "Verbiage"],
    },
    "existential_robbery": {
        "text": "村里发生了一次抢劫。",
        "expected_type": "EXISTENTIAL",
        "reason": "引入一个作为存在者的事件。",
        "expected_roles": ["Existent"],
    },
    "material_robbery": {
        "text": "一伙人抢劫了村庄。",
        "expected_type": "MATERIAL",
        "reason": "突出行动者、行动过程和受影响目标。",
        "expected_roles": ["Actor", "Goal"],
    },
    "existential_school": {
        "text": "村里有一所学校。",
        "expected_type": "EXISTENTIAL",
        "reason": "引入学校的存在，地点是环境。",
        "expected_roles": ["Existent"],
    },
    "relational_belonging": {
        "text": "这所学校属于县政府。",
        "expected_type": "RELATIONAL",
        "reason": "建立学校与县政府的属有关系。",
        "expected_roles": ["Carrier", "Attribute"],
        "forbidden_roles": ["Possessed", "Possessor", "Owner", "Owned"],
    },
}


ALLOWED_ROLES: dict[str, set[str]] = {
    "MATERIAL": {"Actor", "Goal", "Client", "Recipient", "Scope"},
    "MENTAL": {"Senser", "Phenomenon"},
    "RELATIONAL": {"Carrier", "Attribute", "Token", "Value"},
    "VERBAL": {"Sayer", "Receiver", "Target", "Verbiage"},
    "BEHAVIORAL": {"Behaver", "BehaviourScope"},
    "EXISTENTIAL": {"Existent"},
}


def strip_json_fence(content: str) -> str:
    content = content.strip()
    if not content.startswith("```"):
        return content
    lines = content.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="六类过程操作性提示词测试")
    parser.add_argument("--model", default="cuc/deepseek")
    parser.add_argument(
        "--prompt-version",
        choices=("v0.1", "v0.2", "v0.3"),
        default="v0.3",
        help="默认使用加入封闭角色、成分去重和方向判定的v0.3。",
    )
    parser.add_argument(
        "--case",
        choices=tuple(TEST_CASES),
        default="material_work",
        help="第一次使用默认 material_work；确认后再测试其他类型。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = get_api_key()
    base_url = os.environ.get(
        "CUC_BASE_URL", "https://openai.cuc.edu.cn/v1"
    ).rstrip("/")
    if not api_key:
        print("错误：环境变量和钥匙串均没有API密钥。", file=sys.stderr)
        return 2
    prompt_path = PROMPT_DIR / f"system_prompt_{args.prompt_version}.md"
    if not prompt_path.exists():
        print(f"错误：找不到提示词：{prompt_path}", file=sys.stderr)
        return 2

    system_prompt = prompt_path.read_text(encoding="utf-8")
    case = TEST_CASES[args.case]
    user_prompt = (
        "请分析以下单句，将它作为一个候选一级事件，并严格按照系统提示词中的JSON结构输出。\n"
        f"原文片段ID：TEST-{args.case}\n"
        f"原文：{case['text']}"
    )
    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "stream": False,
    }

    try:
        response = request_json(
            method="POST",
            url=f"{base_url}/chat/completions",
            api_key=api_key,
            payload=payload,
            timeout=180,
        )
        raw_content = extract_content(response)
    except RuntimeError as exc:
        print(f"测试失败：{exc}", file=sys.stderr)
        return 1

    clean_content = strip_json_fence(raw_content)
    try:
        parsed: dict[str, Any] = json.loads(clean_content)
        json_valid = True
    except json.JSONDecodeError:
        parsed = {}
        json_valid = False

    actual_type = parsed.get("event_type") if json_valid else None
    actual_roles = (
        [item.get("role") for item in parsed.get("participants", [])]
        if json_valid
        else []
    )
    expected_roles = case.get("expected_roles", [])
    forbidden_roles = case.get("forbidden_roles", [])
    actual_circumstances = parsed.get("circumstances", []) if json_valid else []
    expected_circumstances = case.get("expected_circumstances", [])
    forbidden_circumstances = case.get("forbidden_circumstances", [])
    required_projected_text = case.get("required_projected_text")

    def circumstance_matches(actual: dict[str, Any], rule: dict[str, str]) -> bool:
        """规则值可匹配模型返回值中的完整或包含关系。"""
        if actual.get("kind") != rule.get("kind"):
            return False
        expected_value = rule.get("value", "")
        actual_value = str(actual.get("value", ""))
        return not expected_value or expected_value in actual_value

    roles_present = all(role in actual_roles for role in expected_roles)
    forbidden_absent = all(role not in actual_roles for role in forbidden_roles)
    circumstances_present = all(
        any(circumstance_matches(actual, rule) for actual in actual_circumstances)
        for rule in expected_circumstances
    )
    forbidden_circumstances_absent = all(
        not any(circumstance_matches(actual, rule) for actual in actual_circumstances)
        for rule in forbidden_circumstances
    )
    allowed_roles = ALLOWED_ROLES.get(str(actual_type), set())
    unexpected_roles = [role for role in actual_roles if role not in allowed_roles]
    roles_allowed = not unexpected_roles
    evidence_exact = json_valid and parsed.get("evidence_quote") == case["text"]
    projected_content = parsed.get("projected_content") if json_valid else None
    projected_content_present = (
        not required_projected_text
        or required_projected_text in str(projected_content or "")
    )
    passed = (
        json_valid
        and actual_type == case["expected_type"]
        and roles_present
        and forbidden_absent
        and circumstances_present
        and forbidden_circumstances_absent
        and roles_allowed
        and evidence_exact
        and projected_content_present
    )

    print("\n六类过程操作性提示词测试")
    print(f"  模型：{args.model}")
    print(f"  用例：{args.case}")
    print(f"  原文：{case['text']}")
    print(f"  预期：{case['expected_type']}（{case['reason']}）")
    print(f"  实际：{actual_type}")
    if expected_roles:
        print(f"  预期角色：{', '.join(expected_roles)}")
        print(f"  实际角色：{', '.join(str(role) for role in actual_roles)}")
    if forbidden_roles:
        print(f"  禁止角色：{', '.join(forbidden_roles)}")
    if expected_circumstances:
        print(f"  预期环境：{json.dumps(expected_circumstances, ensure_ascii=False)}")
    if forbidden_circumstances:
        print(f"  禁止环境：{json.dumps(forbidden_circumstances, ensure_ascii=False)}")
    if unexpected_roles:
        print(f"  表外角色：{', '.join(str(role) for role in unexpected_roles)}")
    if required_projected_text:
        print(f"  必需投射内容：{required_projected_text}")
    print(f"  证据逐字一致：{'是' if evidence_exact else '否'}")
    print(f"  JSON：{'合法' if json_valid else '不合法'}")
    print(f"  结果：{'通过' if passed else '未通过'}")
    if json_valid:
        print("\n模型输出：")
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
    else:
        print("\n模型原始输出：")
        print(raw_content)
    print_usage(response)

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_model = args.model.replace("/", "_")
    result_path = RESULT_DIR / f"{timestamp}_{safe_model}_{args.case}.json"
    result_record = {
        "run_time": datetime.now().isoformat(timespec="seconds"),
        "model_id": args.model,
        "prompt_version": args.prompt_version,
        "case_id": args.case,
        "source_text": case["text"],
        "expected_type": case["expected_type"],
        "expected_reason": case["reason"],
        "actual_type": actual_type,
        "expected_roles": expected_roles,
        "forbidden_roles": forbidden_roles,
        "actual_roles": actual_roles,
        "expected_circumstances": expected_circumstances,
        "forbidden_circumstances": forbidden_circumstances,
        "actual_circumstances": actual_circumstances,
        "required_projected_text": required_projected_text,
        "projected_content": projected_content,
        "roles_present": roles_present,
        "forbidden_absent": forbidden_absent,
        "circumstances_present": circumstances_present,
        "forbidden_circumstances_absent": forbidden_circumstances_absent,
        "roles_allowed": roles_allowed,
        "unexpected_roles": unexpected_roles,
        "evidence_exact": evidence_exact,
        "projected_content_present": projected_content_present,
        "json_valid": json_valid,
        "passed": passed,
        "parsed_output": parsed if json_valid else None,
        "raw_content": raw_content,
        "usage": response.get("usage"),
    }
    result_path.write_text(
        json.dumps(result_record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n结果已保存：{result_path}")
    print("结果文件不包含API密钥。")
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())

