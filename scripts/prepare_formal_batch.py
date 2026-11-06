#!/usr/bin/env python3
"""把首批三份DOCX提取结果转换为正式批处理窗口；不调用API。"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
BATCH_ROOT = PROJECT_DIR / "04_54份正式语料批处理"
EXTRACTION_ROOT = BATCH_ROOT / "source_extraction"
INPUT_ROOT = BATCH_ROOT / "inputs"

TARGET_WINDOW_CHARS = 1700
MIN_INTERVIEWEE_SEGMENTS = 3
OVERLAP_INTERVIEWEE_SEGMENTS = 2

DOCUMENTS: tuple[dict[str, str], ...] = (
    {
        "technical_document_id": "BATCH01-DOC01",
        "document_id": "02.陈海峰（一访）（一校后 阅读版）.docx",
        "interviewee": "陈海峰",
        "source_path": "0920_01/语料/C 陈海峰_4+8+23/1访/02.陈海峰（一访）（一校后 阅读版）.docx",
    },
    {
        "technical_document_id": "BATCH01-DOC02",
        "document_id": "03.陈锐霆 090423（二校后 阅读版）.docx",
        "interviewee": "陈锐霆",
        "source_path": "0920_01/语料/C 陈锐霆_15/03.陈锐霆 090423（二校后 阅读版）.docx",
    },
    {
        "technical_document_id": "BATCH01-DOC03",
        "document_id": "02.杨永松100506（二校后 阅读版）.docx",
        "interviewee": "杨永松",
        "source_path": "0920_01/语料/Y 杨永松_10/02.杨永松100506（二校后 阅读版）.docx",
    },
)

TIMESTAMP_RE = re.compile(r"^\s*\d{1,2}\s*[：:]\s*\d{2}")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def classify_body(text: str, interviewee: str, order: int) -> tuple[str, str]:
    stripped = text.strip()
    if order == 1 and stripped.startswith("嘉宾名称"):
        return "EDITOR", "BIOGRAPHICAL_PROFILE"
    if TIMESTAMP_RE.match(stripped):
        return "EDITOR", "RECORDING_TIMESTAMP"
    if stripped.startswith(("记者：", "采访者：", "问：")):
        return "INTERVIEWER", "INTERVIEWER_PROMPT"
    if stripped.startswith((f"{interviewee}：", "答：")):
        return "INTERVIEWEE", "ORAL_TESTIMONY"
    if "您" in stripped and (stripped.endswith(("？", "?")) or stripped.startswith("您")):
        return "INTERVIEWER", "INTERVIEWER_PROMPT"
    return "UNKNOWN", "UNCLASSIFIED_BODY"


def convert_segments(payload: dict[str, Any], config: dict[str, str]) -> list[dict[str, Any]]:
    technical_id = config["technical_document_id"]
    segments: list[dict[str, Any]] = []
    last_spoken_speaker: str | None = None
    for order, block in enumerate(payload["blocks"], start=1):
        speaker_type, segment_type = classify_body(
            block["text"], config["interviewee"], order
        )
        if speaker_type == "UNKNOWN" and last_spoken_speaker in {
            "INTERVIEWEE",
            "INTERVIEWER",
        }:
            speaker_type = last_spoken_speaker
            segment_type = (
                "ORAL_TESTIMONY"
                if speaker_type == "INTERVIEWEE"
                else "INTERVIEWER_PROMPT"
            )
        if speaker_type in {"INTERVIEWEE", "INTERVIEWER"}:
            last_spoken_speaker = speaker_type
        segments.append(
            {
                "segment_id": f"{technical_id}-S{order:04d}",
                "document_id": config["document_id"],
                "technical_document_id": technical_id,
                "segment_order": order,
                "part": "document",
                "source_block_id": block["block_id"],
                "speaker_type": speaker_type,
                "segment_type": segment_type,
                "verbatim_text": block["text"],
            }
        )

    note_order = 0
    for part_name in ("footnotes", "endnotes", "comments"):
        for note in payload.get("additional_parts", {}).get(part_name, []):
            note_order += 1
            segments.append(
                {
                    "segment_id": f"{technical_id}-N{note_order:04d}",
                    "document_id": config["document_id"],
                    "technical_document_id": technical_id,
                    "segment_order": len(payload["blocks"]) + note_order,
                    "part": part_name,
                    "source_block_id": f"{part_name}:{note.get('item_id', '')}",
                    "speaker_type": "EDITOR",
                    "segment_type": "EDITORIAL_NOTE",
                    "verbatim_text": note["text"],
                }
            )
    return segments


def make_windows(
    segments: list[dict[str, Any]], config: dict[str, str]
) -> list[dict[str, Any]]:
    eligible = [
        row
        for row in segments
        if row["part"] == "document"
        and row["segment_type"] != "BIOGRAPHICAL_PROFILE"
    ]
    windows: list[dict[str, Any]] = []
    start = 0
    while start < len(eligible):
        end = start
        characters = 0
        interviewee_count = 0
        while end < len(eligible):
            row = eligible[end]
            characters += len(row["verbatim_text"])
            if row["speaker_type"] == "INTERVIEWEE":
                interviewee_count += 1
            end += 1
            if (
                characters >= TARGET_WINDOW_CHARS
                and interviewee_count >= MIN_INTERVIEWEE_SEGMENTS
            ):
                break

        selected = eligible[start:end]
        if not selected:
            raise RuntimeError(f"{config['technical_document_id']}生成了空窗口")
        window_number = len(windows) + 1
        window_id = f"{config['technical_document_id']}-W{window_number:03d}"
        windows.append(
            {
                "packet_version": "formal-batch-v1.0",
                "window_id": window_id,
                "technical_document_id": config["technical_document_id"],
                "document_id": config["document_id"],
                "source_path": config["source_path"],
                "interviewee": config["interviewee"],
                "window_number": window_number,
                "is_first_window": start == 0,
                "is_last_window": end == len(eligible),
                "task_scope": "正式语料连续窗口盲抽取；事件数量和边界未知。",
                "source_segments": selected,
            }
        )
        if end == len(eligible):
            break

        interviewee_positions = [
            index
            for index in range(start, end)
            if eligible[index]["speaker_type"] == "INTERVIEWEE"
        ]
        if len(interviewee_positions) >= OVERLAP_INTERVIEWEE_SEGMENTS:
            next_start = interviewee_positions[-OVERLAP_INTERVIEWEE_SEGMENTS]
            while (
                next_start > start
                and eligible[next_start - 1]["segment_type"]
                in {"RECORDING_TIMESTAMP", "INTERVIEWER_PROMPT"}
            ):
                next_start -= 1
        else:
            next_start = max(start + 1, end - 3)
        if next_start <= start:
            next_start = start + 1
        start = next_start
    return windows


def main() -> int:
    manifest_rows: list[dict[str, Any]] = []
    document_records: list[dict[str, Any]] = []
    all_segments: list[dict[str, Any]] = []

    for config in DOCUMENTS:
        extracted_path = (
            EXTRACTION_ROOT
            / config["technical_document_id"]
            / "extracted_blocks.json"
        )
        if not extracted_path.exists():
            raise FileNotFoundError(f"缺少DOCX提取结果：{extracted_path}")
        payload = json.loads(extracted_path.read_text(encoding="utf-8"))
        if payload["doc_id"] != config["document_id"]:
            raise RuntimeError(
                f"文档ID不一致：{payload['doc_id']} != {config['document_id']}"
            )
        segments = convert_segments(payload, config)
        windows = make_windows(segments, config)
        all_segments.extend(segments)

        profile_ids = [
            row["segment_id"]
            for row in segments
            if row["segment_type"] == "BIOGRAPHICAL_PROFILE"
        ]
        editorial_note_ids = [
            row["segment_id"]
            for row in segments
            if row["part"] != "document"
        ]
        covered_ids = {
            row["segment_id"]
            for window in windows
            for row in window["source_segments"]
        }
        body_event_input_ids = {
            row["segment_id"]
            for row in segments
            if row["part"] == "document"
            and row["segment_type"] != "BIOGRAPHICAL_PROFILE"
        }
        if covered_ids != body_event_input_ids:
            missing = sorted(body_event_input_ids - covered_ids)
            extra = sorted(covered_ids - body_event_input_ids)
            raise RuntimeError(
                f"{config['technical_document_id']}窗口覆盖异常：missing={missing}, extra={extra}"
            )

        for window in windows:
            input_path = INPUT_ROOT / f"{window['window_id']}.json"
            write_json(input_path, window)
            manifest_rows.append(
                {
                    "window_id": window["window_id"],
                    "technical_document_id": config["technical_document_id"],
                    "document_id": config["document_id"],
                    "interviewee": config["interviewee"],
                    "window_number": window["window_number"],
                    "is_first_window": window["is_first_window"],
                    "is_last_window": window["is_last_window"],
                    "segment_count": len(window["source_segments"]),
                    "source_characters": sum(
                        len(row["verbatim_text"])
                        for row in window["source_segments"]
                    ),
                    "first_segment_id": window["source_segments"][0]["segment_id"],
                    "last_segment_id": window["source_segments"][-1]["segment_id"],
                    "input_file": f"inputs/{window['window_id']}.json",
                }
            )

        document_records.append(
            {
                **config,
                "body_character_count": payload["body_character_count"],
                "body_block_count": payload["body_block_count"],
                "segment_count": len(segments),
                "window_count": len(windows),
                "excluded_profile_segment_ids": profile_ids,
                "editorial_note_segment_ids": editorial_note_ids,
                "window_input_coverage": 1.0,
            }
        )

    write_json(BATCH_ROOT / "batch01_documents.json", document_records)
    source_segments_path = BATCH_ROOT / "batch01_source_segments.jsonl"
    source_segments_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in all_segments
        ),
        encoding="utf-8",
    )
    manifest_path = BATCH_ROOT / "batch01_manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]))
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"已准备{len(document_records)}份文档、{len(manifest_rows)}个重叠窗口。")
    for record in document_records:
        print(
            f"  {record['technical_document_id']} | {record['document_id']} | "
            f"{record['segment_count']}片段 | {record['window_count']}窗口"
        )
    print("文档ID保留完整DOCX文件名；未调用API。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
