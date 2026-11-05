#!/usr/bin/env python3
"""从六份WORKFLOW_DEMO生成受控事件包，模型输入与人工答案分离。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
SOURCE_ROOT = PROJECT_DIR.parent / "现行标注"
OUTPUT_ROOT = PROJECT_DIR / "03_六份Demo对照实验" / "01_受控事件包"

TYPE_MAP = {
    "MATERIAL_EVENT": "MATERIAL",
    "MENTAL_EVENT": "MENTAL",
    "RELATIONAL_EVENT": "RELATIONAL",
    "VERBAL_EVENT": "VERBAL",
    "BEHAVIORAL_EVENT": "BEHAVIORAL",
    "EXISTENTIAL_EVENT": "EXISTENTIAL",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    demo_dirs = sorted(SOURCE_ROOT.glob("0[1-6]_*"))
    if len(demo_dirs) != 6:
        raise RuntimeError(f"预期6份Demo，实际找到{len(demo_dirs)}份")

    inputs_dir = OUTPUT_ROOT / "inputs"
    answer_dir = OUTPUT_ROOT / "answer_key"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    answer_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict[str, Any]] = []
    answer_records: list[dict[str, Any]] = []

    for index, demo_dir in enumerate(demo_dirs, start=1):
        documents = read_csv(demo_dir / "documents.csv")
        events = read_csv(demo_dir / "event_nodes.csv")
        processes = read_csv(demo_dir / "event_processes.csv")
        participants = read_csv(demo_dir / "event_participants.csv")
        segments = read_csv(demo_dir / "source_segments.csv")
        attachments = read_csv(demo_dir / "source_attachments.csv")

        document = documents[0]
        first_event = min(events, key=lambda row: int(row["narrative_order"]))
        event_id = first_event["event_id"]
        process = next(row for row in processes if row["event_id"] == event_id)
        by_segment_id = {row["segment_id"]: row for row in segments}
        evidence_ids = {
            row["segment_id"]
            for row in attachments
            if row["target_type"] == "EVENT"
            and row["target_id"] == event_id
            and row["function"] == "EVIDENCE"
        }
        evidence_segments = sorted(
            (by_segment_id[segment_id] for segment_id in evidence_ids),
            key=lambda row: int(row["segment_order"]),
        )
        packet_id = f"DEMO-P{index:02d}"
        input_record = {
            "packet_version": "v1.0",
            "packet_id": packet_id,
            "doc_id": document["doc_id"],
            "document_title": document["title"],
            "interviewee": document["interviewee"],
            "task_scope": "人工已判定以下片段共同构成一个候选一级事件；请重建其理论类型和结构。",
            "source_segments": [
                {
                    "segment_id": row["segment_id"],
                    "segment_order": int(row["segment_order"]),
                    "speaker_type": row["speaker_type"],
                    "verbatim_text": row["verbatim_text"],
                }
                for row in evidence_segments
            ],
        }
        write_json(inputs_dir / f"{packet_id}.json", input_record)

        gold_participants = [
            {
                "role": row["role"],
                "entity_name": row["entity_name"],
                "participation_status": row["participation_status"],
                "evidence_segment_id": row["evidence_segment_id"],
            }
            for row in participants
            if row["event_id"] == event_id
        ]
        answer_records.append(
            {
                "packet_id": packet_id,
                "doc_id": document["doc_id"],
                "legacy_event_id": event_id,
                "legacy_event_name": first_event["event_name"],
                "expected_type": TYPE_MAP[process["event_type_id"]],
                "legacy_process_text": process["process_text"],
                "legacy_process_normalized": process["process_normalized"],
                "legacy_participants": gold_participants,
                "comparison_note": "事件类型可直接比较；旧版角色需按冻结Schema兼容性人工复核。",
            }
        )
        manifest_rows.append(
            {
                "packet_id": packet_id,
                "doc_id": document["doc_id"],
                "document_title": document["title"],
                "interviewee": document["interviewee"],
                "segment_count": len(evidence_segments),
                "source_characters": sum(
                    len(row["verbatim_text"]) for row in evidence_segments
                ),
                "input_file": f"inputs/{packet_id}.json",
                "answer_file": "answer_key/answer_key.json",
            }
        )

    write_json(
        answer_dir / "answer_key.json",
        {
            "answer_key_version": "v1.0",
            "warning": "本文件仅用于模型运行后的评分，不得拼入API输入。",
            "records": answer_records,
        },
    )
    manifest_path = OUTPUT_ROOT / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]))
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"已生成{len(manifest_rows)}个受控事件包：{OUTPUT_ROOT}")
    print("模型输入与人工答案已分目录保存。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
