#!/usr/bin/env python3
"""从已保存的原始响应规范化并恢复文档级技术通过结果；不调用API。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
BATCH_ROOT = PROJECT_DIR / "04_54份正式语料批处理"
STAGE_ROOT = BATCH_ROOT / "document_consolidation"

sys.path.insert(0, str(SCRIPT_DIR))
from normalize_document_consolidation import (  # noqa: E402
    normalize_document_consolidation_output,
)
from validate_document_consolidation import (  # noqa: E402
    validate_document_consolidation,
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从已保存原始响应恢复文档级规范化结果"
    )
    parser.add_argument("--document", required=True)
    parser.add_argument("--model", default="cuc/deepseek")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_dir = args.model.replace("/", "_")
    raw_root = STAGE_ROOT / "raw_responses" / model_dir
    paths = sorted(raw_root.glob(f"*_{args.document}.json"))
    if not paths:
        print("错误：找不到已保存原始响应。", file=sys.stderr)
        return 2
    raw_path = paths[-1]
    raw_record = json.loads(raw_path.read_text(encoding="utf-8"))
    parsed = raw_record.get("parsed_output")
    try:
        normalized, normalization_applied = (
            normalize_document_consolidation_output(parsed)
        )
    except ValueError as exc:
        print(f"规范化失败：{exc}", file=sys.stderr)
        return 1
    packet_path = STAGE_ROOT / "inputs" / f"{args.document}.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    errors, metrics = validate_document_consolidation(normalized, packet)
    if errors:
        print("技术校验失败：", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 3
    output_path = STAGE_ROOT / "validated_json" / model_dir / f"{args.document}.json"
    write_json(
        output_path,
        {
            "validated_at": datetime.now().isoformat(timespec="seconds"),
            "source_raw_response": str(raw_path.relative_to(PROJECT_DIR)),
            "source_input": str(packet_path.relative_to(PROJECT_DIR)),
            "model_id": args.model,
            "technical_document_id": args.document,
            "document_id": packet["document_id"],
            "technical_passed": True,
            "recovered_without_api_call": True,
            "normalization_applied": normalization_applied,
            "metrics": metrics,
            "consolidated_output": normalized,
            "usage": raw_record.get("usage"),
        },
    )
    print(
        f"恢复通过：{metrics['input_candidate_count']}个输入候选 → "
        f"{metrics['document_event_count']}个文档事件；"
        "未调用API，原始响应未修改。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
