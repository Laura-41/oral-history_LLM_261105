#!/usr/bin/env python3
"""从权威语料清单编排后续51份正式语料批次；不调用API。

生成内容：
  - batch_plan.csv / batch_plan.md：51份语料到 BATCH02–BATCH07 的分批编排
  - batchNN_documents.json / batchNN_source_segments.jsonl / batchNN_manifest.csv
  - inputs/<window_id>.json：模型窗口输入包
  - source_extraction/<技术文档ID>/：DOCX无损提取结果
  - converted_docx/：4份旧版DOC的转换副本（原始语料不修改）
  - corpus_inventory_with_batches.csv：填好批次号的清单副本（原清单不覆盖）

分窗规则直接复用 prepare_formal_batch.py，保证与首批3份完全一致。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
PARENT_DIR = PROJECT_DIR.parent
BATCH_ROOT = PROJECT_DIR / "04_54份正式语料批处理"
EXTRACTION_ROOT = BATCH_ROOT / "source_extraction"
INPUT_ROOT = BATCH_ROOT / "inputs"
CONVERTED_ROOT = BATCH_ROOT / "converted_docx"

DEFAULT_INVENTORY = (
    PARENT_DIR / "现行标注" / "00_模板" / "corpus_inventory.csv"
)
DEFAULT_CORPUS_ROOT = PARENT_DIR / "语料"

sys.path.insert(0, str(SCRIPT_DIR))
from prepare_formal_batch import (  # noqa: E402
    convert_segments,
    make_windows,
    write_json,
)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}

BATCH_SIZES: tuple[int, ...] = (9, 9, 9, 9, 9, 6)
BATCH_NAMES: tuple[str, ...] = tuple(
    f"BATCH{number:02d}" for number in range(2, 2 + len(BATCH_SIZES))
)

NOTE_PART_FILES = (
    ("word/footnotes.xml", "footnotes"),
    ("word/endnotes.xml", "endnotes"),
    ("word/comments.xml", "comments"),
)


def qn(tag: str) -> str:
    return f"{{{W}}}{tag}"


def paragraph_text(paragraph: ET.Element) -> str:
    pieces: list[str] = []
    for node in paragraph.iter():
        if node.tag == qn("t"):
            pieces.append(node.text or "")
        elif node.tag == qn("tab"):
            pieces.append("\t")
        elif node.tag in {qn("br"), qn("cr")}:
            pieces.append("\n")
        elif node.tag == qn("noBreakHyphen"):
            pieces.append("-")
        elif node.tag == qn("softHyphen"):
            pieces.append("\u00ad")
    return "".join(pieces)


def paragraph_style(paragraph: ET.Element) -> str:
    style = paragraph.find("./w:pPr/w:pStyle", NS)
    return style.get(qn("val"), "") if style is not None else ""


def extract_part(xml_bytes: bytes, part_name: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    if part_name == "document":
        container = root.find(".//w:body", NS)
        children = list(container) if container is not None else []
    elif part_name in {"footnotes", "endnotes", "comments"}:
        item_tag = {
            "footnotes": "footnote",
            "endnotes": "endnote",
            "comments": "comment",
        }[part_name]
        blocks: list[dict[str, Any]] = []
        order = 0
        for item in root.findall(f"./w:{item_tag}", NS):
            item_id = item.get(qn("id"), "")
            paragraphs = [
                paragraph_text(p) for p in item.findall(".//w:p", NS)
            ]
            text = "\n".join(p for p in paragraphs if p)
            if not text:
                continue
            order += 1
            blocks.append(
                {
                    "order": order,
                    "block_type": item_tag,
                    "style": "",
                    "text": text,
                    "part": part_name,
                    "item_id": item_id,
                }
            )
        return blocks
    else:
        children = list(root)

    blocks = []
    order = 0
    for child in children:
        if child.tag == qn("p"):
            text = paragraph_text(child)
            if text or part_name != "document":
                order += 1
                blocks.append(
                    {
                        "order": order,
                        "block_type": "paragraph",
                        "style": paragraph_style(child),
                        "text": text,
                        "part": part_name,
                    }
                )
        elif child.tag == qn("tbl"):
            rows: list[str] = []
            for table_row in child.findall("./w:tr", NS):
                cells: list[str] = []
                for cell in table_row.findall("./w:tc", NS):
                    paragraphs = [
                        paragraph_text(p) for p in cell.findall(".//w:p", NS)
                    ]
                    cells.append("\n".join(paragraphs))
                rows.append("\t".join(cells))
            text = "\n".join(rows)
            order += 1
            blocks.append(
                {
                    "order": order,
                    "block_type": "table",
                    "style": "",
                    "text": text,
                    "part": part_name,
                }
            )
    return blocks


def count_tags(xml_bytes: bytes) -> dict[str, int]:
    root = ET.fromstring(xml_bytes)
    return {
        "paragraphs": len(root.findall(".//w:p", NS)),
        "tables": len(root.findall(".//w:tbl", NS)),
        "text_nodes": len(root.findall(".//w:t", NS)),
        "insertions": len(root.findall(".//w:ins", NS)),
        "deletions": len(root.findall(".//w:del", NS)),
        "comment_refs": len(root.findall(".//w:commentReference", NS)),
        "footnote_refs": len(root.findall(".//w:footnoteReference", NS)),
        "endnote_refs": len(root.findall(".//w:endnoteReference", NS)),
        "textboxes": len(root.findall(".//w:txbxContent", NS)),
    }


def extract_docx(input_path: Path, doc_id: str) -> dict[str, Any]:
    """纯标准库实现，输出结构与现行标注的 extract_docx_blocks.py 一致。"""
    with zipfile.ZipFile(input_path) as archive:
        names = set(archive.namelist())
        document_xml = archive.read("word/document.xml")
        body_blocks = extract_part(document_xml, "document")
        parts: dict[str, list[dict[str, Any]]] = {"document": body_blocks}
        for filename, part_name in NOTE_PART_FILES:
            if filename in names:
                parts[part_name] = extract_part(archive.read(filename), part_name)

        extra_files = sorted(
            name
            for name in names
            if re.fullmatch(r"word/(header|footer)\d+\.xml", name)
        )
        for filename in extra_files:
            part_name = Path(filename).stem
            parts[part_name] = extract_part(archive.read(filename), part_name)

        stats = count_tags(document_xml)
        stats["has_comments_part"] = "word/comments.xml" in names
        stats["has_footnotes_part"] = "word/footnotes.xml" in names
        stats["has_endnotes_part"] = "word/endnotes.xml" in names

    blocks: list[dict[str, Any]] = []
    char_offset = 0
    for index, block in enumerate(body_blocks, start=1):
        text = block["text"]
        item = {
            "block_id": f"{doc_id}-B{index:04d}",
            "doc_id": doc_id,
            **block,
            "start_offset": char_offset,
            "end_offset": char_offset + len(text),
        }
        blocks.append(item)
        char_offset += len(text) + 1

    raw_text = "\n".join(block["text"] for block in body_blocks)
    return {
        "doc_id": doc_id,
        "source_file": str(input_path),
        "body_character_count": len(raw_text),
        "body_block_count": len(blocks),
        "xml_stats": stats,
        "blocks": blocks,
        "additional_parts": {
            key: value for key, value in parts.items() if key != "document"
        },
    }


def write_extraction(output_dir: Path, payload: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "extracted_blocks.json", payload)
    raw_text = "\n".join(block["text"] for block in payload["blocks"])
    (output_dir / "extracted_body.txt").write_text(raw_text, encoding="utf-8")
    with (output_dir / "extracted_blocks_readable.txt").open(
        "w", encoding="utf-8"
    ) as handle:
        for block in payload["blocks"]:
            handle.write(
                f"[{block['block_id']}][{block['block_type']}]"
                f"[{block['style']}]\n{block['text']}\n\n"
            )
    write_json(
        output_dir / "extraction_summary.json",
        {
            "doc_id": payload["doc_id"],
            "source_file": payload["source_file"],
            "body_character_count": payload["body_character_count"],
            "body_block_count": payload["body_block_count"],
            "xml_stats": payload["xml_stats"],
            "additional_parts": {
                key: len(value)
                for key, value in payload["additional_parts"].items()
            },
        },
    )


def convert_legacy_doc(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "/usr/bin/textutil",
            "-convert",
            "docx",
            "-output",
            str(destination),
            str(source),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0 or not destination.exists():
        raise RuntimeError(
            f"旧版DOC转换失败：{source.name}；{result.stderr.strip()}"
        )


def stratified_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按受访者分层交错，保证每批尽量覆盖三位受访者。"""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["interviewee"]].append(row)
    sequence: list[tuple[float, int, dict[str, Any]]] = []
    for group in groups.values():
        total = len(group)
        for index, row in enumerate(group):
            sequence.append(((index + 0.5) / total, row["_row_index"], row))
    sequence.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in sequence]


def assign_batches(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    docx_rows = [row for row in rows if row["source_format"] == "DOCX"]
    doc_rows = [row for row in rows if row["source_format"] == "DOC"]
    other_rows = [
        row for row in rows if row["source_format"] not in {"DOCX", "DOC"}
    ]
    if other_rows:
        raise RuntimeError(
            f"存在未识别的源格式：{[row['doc_id'] for row in other_rows]}"
        )
    ordered = stratified_order(docx_rows) + sorted(
        doc_rows, key=lambda row: row["_row_index"]
    )
    if len(ordered) != sum(BATCH_SIZES):
        raise RuntimeError(
            f"待处理份数{len(ordered)}与批次容量{sum(BATCH_SIZES)}不一致"
        )
    batches: dict[str, list[dict[str, Any]]] = {}
    cursor = 0
    for batch_name, size in zip(BATCH_NAMES, BATCH_SIZES):
        batches[batch_name] = ordered[cursor : cursor + size]
        cursor += size
    return batches


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从语料清单编排后续51份批次；不调用API"
    )
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只核对清单和源文件，不写任何文件",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory_path = args.inventory.resolve()
    corpus_root = args.corpus_root.resolve()
    if not inventory_path.exists():
        print(f"错误：找不到语料清单：{inventory_path}", file=sys.stderr)
        return 2
    if not corpus_root.is_dir():
        print(f"错误：找不到语料根目录：{corpus_root}", file=sys.stderr)
        return 2

    with inventory_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        inventory_fields = list(reader.fieldnames or [])
        inventory_rows = list(reader)
    for index, row in enumerate(inventory_rows):
        row["_row_index"] = index

    pending = [
        row
        for row in inventory_rows
        if row["processing_status"] == "PENDING"
        and row["include_in_study"].strip().upper() == "YES"
    ]
    if not pending:
        print("错误：清单中没有待处理语料。", file=sys.stderr)
        return 2
    existing_done = [
        row
        for row in inventory_rows
        if row["processing_status"] in {"VALIDATED", "CONFIRMED"}
    ]
    print(
        f"清单共{len(inventory_rows)}份：已完成{len(existing_done)}份，"
        f"待处理{len(pending)}份。"
    )

    missing_sources = [
        row["doc_id"]
        for row in pending
        if not (corpus_root / row["relative_path"]).is_file()
    ]
    if missing_sources:
        print(
            f"错误：{len(missing_sources)}份源文件缺失：{missing_sources}",
            file=sys.stderr,
        )
        return 2
    print(f"源文件核对通过：{len(pending)}份均可定位。")
    if args.dry_run:
        batches = assign_batches(pending)
        for batch_name, rows in batches.items():
            print(
                f"  {batch_name}: {len(rows)}份 / "
                f"{dict(Counter(row['interviewee'] for row in rows))}"
            )
        print("dry-run 结束，未写入任何文件。")
        return 0

    batches = assign_batches(pending)
    plan_rows: list[dict[str, Any]] = []
    batch_stats: list[dict[str, Any]] = []
    assignment: dict[str, dict[str, str]] = {}

    for batch_name, batch_rows in batches.items():
        batch_documents: list[dict[str, Any]] = []
        batch_segments: list[dict[str, Any]] = []
        batch_manifest: list[dict[str, Any]] = []

        for position, row in enumerate(batch_rows, start=1):
            technical_id = f"{batch_name}-DOC{position:02d}"
            filename = row["filename"]
            source_path = corpus_root / row["relative_path"]
            effective_source = source_path
            conversion_note = ""
            if row["source_format"] == "DOC":
                effective_source = CONVERTED_ROOT / f"{technical_id}.docx"
                convert_legacy_doc(source_path, effective_source)
                conversion_note = (
                    "textutil转换副本；转换副本不含独立脚注部件，"
                    "需人工核对脚注与编者注"
                )

            payload = extract_docx(effective_source, filename)
            if payload["body_character_count"] <= 0:
                raise RuntimeError(f"{technical_id}提取结果为空")
            write_extraction(EXTRACTION_ROOT / technical_id, payload)

            config = {
                "technical_document_id": technical_id,
                "document_id": filename,
                "interviewee": row["interviewee"],
                "source_path": f"0920_01/语料/{row['relative_path']}",
            }
            segments = convert_segments(payload, config)
            windows = make_windows(segments, config)
            profile_ids = [
                item["segment_id"]
                for item in segments
                if item["segment_type"] == "BIOGRAPHICAL_PROFILE"
            ]
            editorial_note_ids = [
                item["segment_id"] for item in segments if item["part"] != "document"
            ]
            covered_ids = {
                item["segment_id"]
                for window in windows
                for item in window["source_segments"]
            }
            body_event_input_ids = {
                item["segment_id"]
                for item in segments
                if item["part"] == "document"
                and item["segment_type"] != "BIOGRAPHICAL_PROFILE"
            }
            if covered_ids != body_event_input_ids:
                raise RuntimeError(
                    f"{technical_id}窗口覆盖异常："
                    f"missing={sorted(body_event_input_ids - covered_ids)}"
                )
            unknown_count = sum(
                1 for item in segments if item["speaker_type"] == "UNKNOWN"
            )
            for window in windows:
                write_json(INPUT_ROOT / f"{window['window_id']}.json", window)
                batch_manifest.append(
                    {
                        "window_id": window["window_id"],
                        "technical_document_id": technical_id,
                        "document_id": filename,
                        "interviewee": row["interviewee"],
                        "window_number": window["window_number"],
                        "is_first_window": window["is_first_window"],
                        "is_last_window": window["is_last_window"],
                        "segment_count": len(window["source_segments"]),
                        "source_characters": sum(
                            len(item["verbatim_text"])
                            for item in window["source_segments"]
                        ),
                        "first_segment_id": window["source_segments"][0]["segment_id"],
                        "last_segment_id": window["source_segments"][-1]["segment_id"],
                        "input_file": f"inputs/{window['window_id']}.json",
                    }
                )
            batch_segments.extend(segments)
            batch_documents.append(
                {
                    **config,
                    "doc_id": row["doc_id"],
                    "source_format": row["source_format"],
                    "effective_source": str(effective_source),
                    "conversion_note": conversion_note,
                    "body_character_count": payload["body_character_count"],
                    "body_block_count": payload["body_block_count"],
                    "segment_count": len(segments),
                    "window_count": len(windows),
                    "unknown_segment_count": unknown_count,
                    "profile_detected": bool(profile_ids),
                    "excluded_profile_segment_ids": profile_ids,
                    "editorial_note_segment_ids": editorial_note_ids,
                    "window_input_coverage": 1.0,
                }
            )
            assignment[row["doc_id"]] = {
                "technical_document_id": technical_id,
                "assigned_batch_id": batch_name,
            }
            plan_rows.append(
                {
                    "batch_id": batch_name,
                    "batch_position": position,
                    "technical_document_id": technical_id,
                    "doc_id": row["doc_id"],
                    "interviewee": row["interviewee"],
                    "visit_no": row["visit_no"],
                    "file_no": row["file_no"],
                    "filename": filename,
                    "relative_path": row["relative_path"],
                    "source_format": row["source_format"],
                    "conversion_status": row["conversion_status"],
                    "effective_source": str(effective_source),
                    "sha256": row["sha256"],
                    "segment_count": len(segments),
                    "window_count": len(windows),
                    "unknown_segment_count": unknown_count,
                    "profile_detected": bool(profile_ids),
                    "plan_status": "READY",
                    "notes": conversion_note or row["notes"],
                }
            )

        batch_lower = batch_name.lower()
        write_json(
            BATCH_ROOT / f"{batch_lower}_documents.json", batch_documents
        )
        (BATCH_ROOT / f"{batch_lower}_source_segments.jsonl").write_text(
            "".join(
                json.dumps(item, ensure_ascii=False) + "\n"
                for item in batch_segments
            ),
            encoding="utf-8",
        )
        manifest_path = BATCH_ROOT / f"{batch_lower}_manifest.csv"
        with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=list(batch_manifest[0])
            )
            writer.writeheader()
            writer.writerows(batch_manifest)

        batch_stats.append(
            {
                "batch_id": batch_name,
                "document_count": len(batch_documents),
                "interviewee_counts": dict(
                    Counter(row["interviewee"] for row in batch_rows)
                ),
                "segment_count": len(batch_segments),
                "window_count": len(batch_manifest),
                "legacy_doc_count": sum(
                    1 for row in batch_rows if row["source_format"] == "DOC"
                ),
                "unknown_segment_total": sum(
                    row["unknown_segment_count"] for row in batch_documents
                ),
                "profile_detected_count": sum(
                    1 for row in batch_documents if row["profile_detected"]
                ),
            }
        )

    plan_path = BATCH_ROOT / "batch_plan.csv"
    with plan_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(plan_rows[0]))
        writer.writeheader()
        writer.writerows(plan_rows)

    inventory_copy_path = BATCH_ROOT / "corpus_inventory_with_batches.csv"
    extra_fields = ["technical_document_id", "assigned_batch_id"]
    with inventory_copy_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=inventory_fields + extra_fields
        )
        writer.writeheader()
        for row in inventory_rows:
            output_row = {
                key: value for key, value in row.items() if key != "_row_index"
            }
            assigned = assignment.get(row["doc_id"], {})
            output_row["technical_document_id"] = assigned.get(
                "technical_document_id", ""
            )
            output_row["assigned_batch_id"] = assigned.get(
                "assigned_batch_id", row["batch_id"]
            )
            writer.writerow(output_row)

    lines = [
        "# 后续51份语料分批编排",
        "",
        "> 生成方式：`python3 scripts/prepare_batch_from_inventory.py`；不调用API，不修改原始语料。",
        "> 编排规则：按受访者分层交错，旧版DOC统一后置到最后一批；每批9份，末批6份。",
        "",
        "## 批次总览",
        "",
        "| 批次 | 份数 | 受访者分布 | 原文片段 | 窗口 | 旧版DOC | 未识别说话人 |",
        "|---|---:|---|---:|---:|---:|---:|",
    ]
    for item in batch_stats:
        distribution = "、".join(
            f"{name}{count}" for name, count in item["interviewee_counts"].items()
        )
        lines.append(
            f"| `{item['batch_id']}` | {item['document_count']} | {distribution} | "
            f"{item['segment_count']} | {item['window_count']} | "
            f"{item['legacy_doc_count']} | {item['unknown_segment_total']} |"
        )
    total_documents = sum(item["document_count"] for item in batch_stats)
    total_segments = sum(item["segment_count"] for item in batch_stats)
    total_windows = sum(item["window_count"] for item in batch_stats)
    lines += [
        "",
        f"合计：{total_documents}份、{total_segments}个原文片段、{total_windows}个重叠窗口。",
        "",
        "## 说明",
        "",
        "- `BATCH01` 首批3份已由 DeepSeek 完成窗口抽取与文档级回归，不在本编排内。",
        "- 6份 `WORKFLOW_DEMO` 不重复运行。",
        "- 4份旧版 `.doc` 通过 `textutil` 生成 `.docx` 转换副本，存于 `converted_docx/`，原始语料不变；"
        "转换副本不含独立脚注部件，需人工核对脚注与编者注。",
        "- `未识别说话人` 为 `UNKNOWN` 片段数，供分窗前抽检；不改变首批已冻结的分类规则。",
        "- `corpus_inventory_with_batches.csv` 是填好批次号的清单副本，原始 `corpus_inventory.csv` 未被覆盖。",
        "",
    ]
    (BATCH_ROOT / "batch_plan.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )

    print(
        f"\n已编排{len(batches)}批、{total_documents}份文档、"
        f"{total_windows}个重叠窗口。"
    )
    for item in batch_stats:
        print(
            f"  {item['batch_id']}: {item['document_count']}份 / "
            f"{item['window_count']}窗口 / "
            f"DOC{item['legacy_doc_count']}份"
        )
    print("未调用API；原始语料、首批结果与冻结提示词均未改动。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
