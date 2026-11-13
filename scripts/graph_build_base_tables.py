#!/usr/bin/env python3
"""图谱补齐 L0：从既有正式批次产物确定性生成标注底座表（零 API）。

只读取既有结果，不修改 validated_json/、冻结资产与原始语料；
输出写到 document_consolidation/graph_layers/<模型目录>/<文档>/.

用法：
    python3 scripts/graph_build_base_tables.py --document BATCH02-DOC01            # 预览
    python3 scripts/graph_build_base_tables.py --document BATCH02-DOC01 --write    # 落盘
    python3 scripts/graph_build_base_tables.py --document BATCH02-DOC01 --model cuc/qwen --write
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
BATCH_ROOT = PROJECT_DIR / "04_54份正式语料批处理"
STAGE_ROOT = BATCH_ROOT / "document_consolidation"
GRAPH_ROOT = STAGE_ROOT / "graph_layers"
DEMO_ROOT = PROJECT_DIR.parent / "现行标注"
TEMPLATE_DIR = DEMO_ROOT / "00_模板"

SEGMENT_TYPE_MAP = {
    "ORAL_TESTIMONY": "EVENT_EVIDENCE",
    "INTERVIEWER_PROMPT": "INTERVIEWER_PROMPT",
    "EDITORIAL_NOTE": "DOCUMENT_NOTE",
    "BIOGRAPHICAL_PROFILE": "DOCUMENT_NOTE",
    "RECORDING_TIMESTAMP": "RECORDING_TIMESTAMP",
    "UNCLASSIFIED_BODY": "UNCERTAIN",
}
EVENT_TYPE_MAP = {
    "MATERIAL": "MATERIAL_EVENT",
    "MENTAL": "MENTAL_EVENT",
    "RELATIONAL": "RELATIONAL_EVENT",
    "VERBAL": "VERBAL_EVENT",
    "BEHAVIORAL": "BEHAVIOURAL_EVENT",
    "EXISTENTIAL": "EXISTENTIAL_EVENT",
}
STATUS_MAP = {
    "AUTO_VALIDATED": "MODEL_CANDIDATE",
    "HUMAN_CONFIRMED": "CONFIRMED",
    "NEEDS_REVIEW": "NEEDS_REVIEW",
    "MODEL_CANDIDATE": "MODEL_CANDIDATE",
    "CONFIRMED": "CONFIRMED",
    "REJECTED": "REJECTED",
}
PERSON_ENTITY = {"陈海峰": "PER-CHF", "陈锐霆": "PER-CRT", "杨永松": "PER-YYS"}
SPEAKER_ENTITY = {
    "INTERVIEWEE": "",
    "INTERVIEWER": "PER-INTERVIEWER",
    "EDITOR": "PER-EDITOR",
    "OTHER": "",
    "UNKNOWN": "",
}
BASE_TABLES = (
    "documents",
    "source_segments",
    "source_attachments",
    "coverage_audit",
    "document_annotations",
    "event_nodes",
    "event_processes",
    "event_participants",
    "event_circumstances",
    "event_next",
)


def safe_model_name(model: str) -> str:
    return model.replace("/", "_")


def display_path(path: Path) -> str:
    """工程内显示相对路径，工程外（如 /tmp 自测）安全回退为绝对路径。"""
    try:
        return str(path.relative_to(PROJECT_DIR))
    except ValueError:
        return str(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def template_header(table: str) -> list[str]:
    with (TEMPLATE_DIR / f"{table}.csv").open(encoding="utf-8-sig", newline="") as handle:
        return list(next(csv.reader(handle)))


def write_table(folder: Path, table: str, rows: list[dict[str, Any]]) -> None:
    header = template_header(table)
    with (folder / f"{table}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in header})


def batch_of(technical_id: str) -> str:
    match = re.match(r"(BATCH\d+)-", technical_id)
    if not match:
        raise ValueError(f"无法从 {technical_id} 解析批次号")
    return match.group(1).lower()


def load_context(technical_id: str, model: str) -> dict[str, Any]:
    batch = batch_of(technical_id)
    model_dir = safe_model_name(model)

    segments = [
        row for row in read_jsonl(BATCH_ROOT / f"{batch}_source_segments.jsonl")
        if row["technical_document_id"] == technical_id
    ]
    if not segments:
        raise ValueError(f"{batch}_source_segments.jsonl 里找不到 {technical_id}")

    docs = read_json(BATCH_ROOT / f"{batch}_documents.json")
    doc_meta = next((row for row in docs if row["technical_document_id"] == technical_id), None)
    if doc_meta is None:
        raise ValueError(f"{batch}_documents.json 里找不到 {technical_id}")

    block_path = BATCH_ROOT / "source_extraction" / technical_id / "extracted_blocks.json"
    blocks: dict[str, dict[str, Any]] = {}
    if block_path.exists():
        extracted = read_json(block_path)
        for block in extracted.get("blocks", []):
            blocks[block["block_id"]] = block

    result_path = STAGE_ROOT / "validated_json" / model_dir / f"{technical_id}.json"
    if not result_path.exists():
        raise ValueError(f"找不到该模型线的归并结果：{result_path}")
    result = read_json(result_path)

    view_path = STAGE_ROOT / "human_adjudicated" / model_dir / f"{technical_id}.json"
    events = result["consolidated_output"]["document_events"]
    if view_path.exists():
        events = read_json(view_path)["consolidated_output"]["document_events"]

    return {
        "batch": batch,
        "model": model,
        "model_dir": model_dir,
        "technical_id": technical_id,
        "segments": segments,
        "doc_meta": doc_meta,
        "blocks": blocks,
        "result": result,
        "events": events,
        "has_view": view_path.exists(),
        "view_path": view_path if view_path.exists() else None,
        "result_path": result_path,
    }


def parse_timecode(text: str) -> tuple[str, str]:
    times = re.findall(r"\d{1,2}[:：]\d{2}(?:[:：]\d{2})?", text)
    if len(times) >= 2:
        return times[0].replace("：", ":"), times[1].replace("：", ":")
    if times:
        return times[0].replace("：", ":"), ""
    return "", ""


def build_tables(ctx: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    technical_id = ctx["technical_id"]
    meta = ctx["doc_meta"]
    segments = sorted(ctx["segments"], key=lambda row: int(row["segment_order"]))
    events = ctx["events"]
    doc_id = meta.get("doc_id")
    if not doc_id:
        raise ValueError(
            f"{technical_id} 的文档元数据缺 doc_id；"
            "请按 04_54份正式语料批处理/corpus_inventory_with_batches.csv 的 filename 反查补齐"
        )
    interviewee = meta["interviewee"]
    blocks = ctx["blocks"]
    person_id = PERSON_ENTITY.get(interviewee, "")

    tables: dict[str, list[dict[str, Any]]] = {name: [] for name in BASE_TABLES}
    warnings: list[str] = []

    tables["documents"].append({
        "doc_id": doc_id,
        "title": meta["document_id"].rsplit(".", 1)[0],
        "interviewee": interviewee,
        "interview_date": "",
        "visit_no": "",
        "version": "",
        "source_file": meta["source_path"],
        "total_characters": meta.get("body_character_count", ""),
        "data_role": "BATCH_APPLICATION",
        "include_in_study": "YES",
        "review_status": "MODEL_CANDIDATE",
    })

    segment_order = {row["segment_id"]: int(row["segment_order"]) for row in segments}
    for row in segments:
        raw_type = row.get("segment_type", "")
        mapped = SEGMENT_TYPE_MAP.get(raw_type, "UNCERTAIN")
        block = blocks.get(row.get("source_block_id", ""), {})
        start_tc, end_tc = ("", "")
        if raw_type == "RECORDING_TIMESTAMP":
            start_tc, end_tc = parse_timecode(row.get("verbatim_text", ""))
        speaker_id = SPEAKER_ENTITY.get(row.get("speaker_type", ""), "")
        if row.get("speaker_type") == "INTERVIEWEE":
            speaker_id = person_id
        tables["source_segments"].append({
            "segment_id": row["segment_id"],
            "doc_id": doc_id,
            "segment_order": row["segment_order"],
            "source_part": row.get("part", "document"),
            "source_ref_id": "",
            "source_block_id": row.get("source_block_id", ""),
            "speaker_id": speaker_id,
            "speaker_type": row.get("speaker_type", ""),
            "start_timecode": start_tc,
            "end_timecode": end_tc,
            "start_offset": block.get("start_offset", ""),
            "end_offset": block.get("end_offset", ""),
            "segment_type": mapped,
            "verbatim_text": row.get("verbatim_text", ""),
            "normalized_text": "",
            "transcription_status": "VISIBLE_CURRENT_TEXT",
            "review_status": "MODEL_CANDIDATE",
        })
        if not block:
            warnings.append(f"{row['segment_id']} 未找到块级偏移，start_offset 留空")
        if raw_type not in SEGMENT_TYPE_MAP:
            warnings.append(f"{row['segment_id']} 未知 segment_type={raw_type}，映射为 UNCERTAIN")

    annotation_types = {
        "BIOGRAPHICAL_PROFILE": "BIOGRAPHICAL_PROFILE",
        "EDITORIAL_NOTE": "EDITORIAL_NOTE",
        "RECORDING_TIMESTAMP": "RECORDING_TIMESTAMP",
    }
    annotation_index = 0
    for row in segments:
        raw_type = row.get("segment_type", "")
        if raw_type not in annotation_types and row.get("part") != "footnotes":
            continue
        annotation_index += 1
        tables["document_annotations"].append({
            "annotation_id": f"{doc_id}-AN{annotation_index:04d}",
            "doc_id": doc_id,
            "annotation_type": annotation_types.get(raw_type, "FOOTNOTE"),
            "annotation_text": row.get("verbatim_text", ""),
            "author_or_editor": "原文编校者",
            "source_status": "EDITORIAL_PROFILE" if raw_type == "BIOGRAPHICAL_PROFILE" else "EDITORIAL_NOTE",
            "target_type": "DOCUMENT",
            "target_id": doc_id,
            "source_segment_id": row["segment_id"],
        })

    def first_order(event: dict[str, Any]) -> int:
        ids = event.get("source_segment_ids", [])
        return min((segment_order.get(sid, 10**9) for sid in ids), default=10**9)

    ordered = sorted(events, key=first_order)
    event_by_segment: dict[str, list[str]] = defaultdict(list)
    for event in ordered:
        for sid in event.get("source_segment_ids", []):
            event_by_segment[sid].append(event["document_event_id"])

    for index, event in enumerate(ordered, start=1):
        event_id = event["document_event_id"]
        canonical = event["canonical_event"]
        status = STATUS_MAP.get(event.get("review_status", ""), "MODEL_CANDIDATE")
        tables["event_nodes"].append({
            "event_id": event_id,
            "doc_id": doc_id,
            "event_name": canonical.get("event_name", ""),
            "narrative_order": index,
            "historical_order": index,
            "result_state": "",
            "factuality": "",
            "confidence": "",
            "boundary_note": "",
            "boundary_confidence": "",
            "review_status": status,
        })
        evidence_ids = event.get("scope_evidence_segment_ids") or event.get("source_segment_ids", [])
        tables["event_processes"].append({
            "process_id": f"{event_id}-PROC",
            "event_id": event_id,
            "event_type_id": EVENT_TYPE_MAP.get(canonical.get("event_type", ""), ""),
            "process_text": canonical.get("core_process", ""),
            "process_normalized": canonical.get("core_process", ""),
            "evidence_segment_id": evidence_ids[0] if evidence_ids else "",
            "confidence": "MEDIUM",
        })
        for participant in canonical.get("participants", []):
            tables["event_participants"].append({
                "event_id": event_id,
                "entity_id": "",
                "entity_name": participant.get("normalized_entity") or participant.get("mention", ""),
                "entity_type": "",
                "role": participant.get("role", ""),
                "participation_status": "主要参与者",
                "evidence_segment_id": evidence_ids[0] if evidence_ids else "",
                "confidence": participant.get("certainty", "MEDIUM"),
            })
        for number, circumstance in enumerate(canonical.get("circumstances", []), start=1):
            tables["event_circumstances"].append({
                "circumstance_id": f"{event_id}-C{number:02d}",
                "event_id": event_id,
                "kind": circumstance.get("kind", ""),
                "value_text": circumstance.get("value", ""),
                "normalized_value": circumstance.get("normalized_value") or "",
                "entity_id": "",
                "evidence_segment_id": evidence_ids[0] if evidence_ids else "",
                "confidence": "MEDIUM",
            })

    for current, following in zip(ordered, ordered[1:]):
        tables["event_next"].append({
            "source_event_id": current["document_event_id"],
            "target_event_id": following["document_event_id"],
            "chain_id": f"{doc_id}-MAIN",
            "basis": "contextual_inference",
            "confidence": "MEDIUM",
            "review_status": "MODEL_CANDIDATE",
        })

    attachment_index = 0
    attached: set[str] = set()
    document_only = 0
    function_by_type = {
        "INTERVIEWER_PROMPT": "INTERVIEWER_PROMPT",
        "EDITORIAL_NOTE": "DOCUMENT_NOTE",
        "BIOGRAPHICAL_PROFILE": "COMMENT",
        "RECORDING_TIMESTAMP": "DOCUMENT_NOTE",
    }
    for row in segments:
        sid = row["segment_id"]
        targets = event_by_segment.get(sid, [])
        if targets:
            for event_id in targets:
                attachment_index += 1
                tables["source_attachments"].append({
                    "attachment_id": f"{doc_id}-AT{attachment_index:04d}",
                    "segment_id": sid,
                    "target_type": "EVENT",
                    "target_id": event_id,
                    "function": "EVIDENCE",
                    "quote_start_offset": "",
                    "quote_end_offset": "",
                    "confidence": "HIGH",
                    "review_status": "MODEL_CANDIDATE",
                })
        else:
            attachment_index += 1
            document_only += 1
            tables["source_attachments"].append({
                "attachment_id": f"{doc_id}-AT{attachment_index:04d}",
                "segment_id": sid,
                "target_type": "DOCUMENT",
                "target_id": doc_id,
                "function": function_by_type.get(row.get("segment_type", ""), "DOCUMENT_ONLY"),
                "quote_start_offset": "",
                "quote_end_offset": "",
                "confidence": "HIGH",
                "review_status": "MODEL_CANDIDATE",
            })
        attached.add(sid)

    total_segments = len(segments)
    coverage = "1.0000" if len(attached) == total_segments else f"{len(attached) / total_segments:.4f}"
    tables["coverage_audit"].append({
        "doc_id": doc_id,
        "total_characters": meta.get("body_character_count", ""),
        "segmented_characters": sum(len(row.get("verbatim_text", "")) for row in segments),
        "uncovered_characters": 0 if coverage == "1.0000" else "",
        "overlap_characters": 0,
        "total_segments": total_segments,
        "attached_segments": len(attached),
        "document_only_segments": document_only,
        "coverage_rate": coverage,
        "audit_status": "PASS" if coverage == "1.0000" else "FAIL",
    })

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "layer": "L0_BASE_TABLES",
        "technical_document_id": technical_id,
        "doc_id": doc_id,
        "model_id": ctx["model"],
        "source_result": str(ctx["result_path"].relative_to(PROJECT_DIR)),
        "human_adjudicated_view": str(ctx["view_path"].relative_to(PROJECT_DIR)) if ctx["view_path"] else None,
        "api_calls": 0,
        "tables": {name: len(rows) for name, rows in tables.items()},
        "segments": total_segments,
        "events": len(ordered),
        "event_referenced_segments": len(event_by_segment),
        "coverage_rate": coverage,
        "warnings": warnings,
    }
    return tables, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", required=True, help="技术文档ID，如 BATCH02-DOC01")
    parser.add_argument("--model", default="cuc/deepseek")
    parser.add_argument("--write", action="store_true", help="落盘；默认只预览")
    args = parser.parse_args()

    try:
        ctx = load_context(args.document, args.model)
        tables, report = build_tables(ctx)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 2

    print(f"{'[落盘]' if args.write else '[预览]'} {args.document} / {args.model}")
    print(f"  原文片段 {report['segments']}｜一级事件 {report['events']}｜覆盖率 {report['coverage_rate']}")
    print(f"  人工视图：{report['human_adjudicated_view'] or '无'}")
    for name, count in report["tables"].items():
        print(f"    {name:<22} {count:>5} 行")
    if report["warnings"]:
        print(f"  警告 {len(report['warnings'])} 条（详见 L0_report.json）")

    if args.write:
        folder = GRAPH_ROOT / ctx["model_dir"] / args.document
        folder.mkdir(parents=True, exist_ok=True)
        for name, rows in tables.items():
            write_table(folder, name, rows)
        (folder / "L0_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"  已写入：{display_path(folder)}")
    return 0 if report["coverage_rate"] == "1.0000" else 1


if __name__ == "__main__":
    raise SystemExit(main())
