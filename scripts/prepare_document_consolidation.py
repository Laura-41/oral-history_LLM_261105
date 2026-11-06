#!/usr/bin/env python3
"""准备文档级跨窗口归并与经历范围分类输入；不调用API。"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
BATCH_ROOT = PROJECT_DIR / "04_54份正式语料批处理"
STAGE_ROOT = BATCH_ROOT / "document_consolidation"
INPUT_ROOT = STAGE_ROOT / "inputs"


def safe_model_name(model: str) -> str:
    return model.replace("/", "_")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.batch:
        lower = args.batch.lower()
        documents = BATCH_ROOT / f"{lower}_documents.json"
        segments = BATCH_ROOT / f"{lower}_source_segments.jsonl"
    else:
        documents = BATCH_ROOT / (
            args.documents or "batch01_documents.json"
        )
        segments = BATCH_ROOT / (
            args.segments or "batch01_source_segments.jsonl"
        )
    for path in (documents, segments):
        if not path.exists():
            raise FileNotFoundError(
                f"找不到{path.name}，请先运行对应的批次准备程序"
            )
    return documents, segments


def read_source_segments(path: Path) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        grouped[row["technical_document_id"]].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: int(row["segment_order"]))
    return grouped


def dialogue_segments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "segment_id": row["segment_id"],
            "segment_order": row["segment_order"],
            "speaker_type": row["speaker_type"],
            "segment_type": row["segment_type"],
            "verbatim_text": row["verbatim_text"],
        }
        for row in rows
        if row["part"] == "document"
        and row["segment_type"]
        not in {"BIOGRAPHICAL_PROFILE", "RECORDING_TIMESTAMP"}
    ]


def collect_candidates(
    technical_document_id: str, model: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    model_dir = safe_model_name(model)
    validated_root = BATCH_ROOT / "validated_json" / model_dir
    paths = sorted(validated_root.glob(f"{technical_document_id}-W*.json"))
    if not paths:
        raise FileNotFoundError(
            f"缺少{model} / {technical_document_id}的窗口技术通过结果"
        )
    candidates: list[dict[str, Any]] = []
    for path in paths:
        record = read_json(path)
        if not record.get("technical_passed"):
            raise RuntimeError(f"窗口未通过技术校验：{path}")
        window_number = int(record["window_id"].rsplit("W", 1)[1])
        edge_ids = set(record.get("edge_candidate_ids", []))
        for candidate in record["postprocessed_output"].get("events", []):
            candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "window_id": record["window_id"],
                    "window_number": window_number,
                    "edge_candidate": candidate["candidate_id"] in edge_ids,
                    "source_segment_ids": candidate["source_segment_ids"],
                    "event": candidate["event"],
                }
            )
    candidates.sort(key=lambda row: (row["window_number"], row["candidate_id"]))
    queue_path = (
        BATCH_ROOT
        / "review_queue"
        / model_dir
        / f"{technical_document_id}.json"
    )
    if not queue_path.exists() and model == "cuc/deepseek":
        legacy_queue_path = (
            BATCH_ROOT / "review_queue" / f"{technical_document_id}.json"
        )
        if legacy_queue_path.exists():
            queue_path = legacy_queue_path
    queue = read_json(queue_path) if queue_path.exists() else {
        "adjacent_candidate_pairs": [],
        "terminal_candidate_ids": [],
    }
    return candidates, queue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="准备指定模型的文档级归并输入；不调用API"
    )
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--batch",
        help="批次号，如BATCH02；自动使用该批次的documents与segments文件",
    )
    parser.add_argument(
        "--documents",
        help="文档记录文件名；默认batch01_documents.json",
    )
    parser.add_argument(
        "--segments",
        help="源片段文件名；默认batch01_source_segments.jsonl",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--document", help="技术文档ID，如BATCH02-DOC01")
    group.add_argument(
        "--all-first-batch",
        "--all",
        action="store_true",
        help="为所选文档记录内的全部文档生成输入包",
    )
    return parser.parse_args()


def select_documents(
    documents: list[dict[str, Any]], args: argparse.Namespace
) -> list[dict[str, Any]]:
    if args.document:
        selected = [
            row
            for row in documents
            if row["technical_document_id"] == args.document
        ]
    else:
        selected = list(documents)
    if not selected:
        raise ValueError("没有找到符合条件的文档")
    return selected


def main() -> int:
    args = parse_args()
    model_dir = safe_model_name(args.model)
    try:
        documents_path, segments_path = resolve_paths(args)
    except FileNotFoundError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(
        f"文档记录：{documents_path.name}；源片段：{segments_path.name}"
    )
    documents = select_documents(read_json(documents_path), args)
    segments_by_document = read_source_segments(segments_path)
    manifest_path = STAGE_ROOT / f"manifest_{model_dir}.csv"
    existing_manifest: dict[str, dict[str, str]] = {}
    if manifest_path.exists():
        with manifest_path.open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            existing_manifest = {
                row["technical_document_id"]: row
                for row in csv.DictReader(handle)
            }

    for document in documents:
        technical_id = document["technical_document_id"]
        candidates, queue = collect_candidates(technical_id, args.model)
        segments = dialogue_segments(segments_by_document[technical_id])
        known_segment_ids = {row["segment_id"] for row in segments}
        referenced_ids = {
            segment_id
            for candidate in candidates
            for segment_id in candidate["source_segment_ids"]
        }
        missing = referenced_ids - known_segment_ids
        if missing:
            raise RuntimeError(
                f"{technical_id}候选引用了输入外片段：{sorted(missing)}"
            )

        packet = {
            "packet_version": "document-consolidation-input-v1.0",
            "technical_document_id": technical_id,
            "document_id": document["document_id"],
            "interviewee": document["interviewee"],
            "source_model_id": args.model,
            "source_prompt_version": "system-v0.3-frozen+window-v0.5",
            "task_scope": (
                "归并同一文档的窗口候选，并区分个人经历、"
                "讲述背景和范围不确定项。"
            ),
            "dialogue_segments": segments,
            "window_candidates": candidates,
            "adjacent_candidate_pairs": queue.get(
                "adjacent_candidate_pairs", []
            ),
            "terminal_candidate_ids": queue.get(
                "terminal_candidate_ids", []
            ),
        }
        input_path = INPUT_ROOT / model_dir / f"{technical_id}.json"
        write_json(input_path, packet)
        existing_manifest[technical_id] = {
            "technical_document_id": technical_id,
            "document_id": document["document_id"],
            "interviewee": document["interviewee"],
            "source_model_id": args.model,
            "dialogue_segment_count": len(segments),
            "candidate_count": len(candidates),
            "adjacent_pair_count": len(
                packet["adjacent_candidate_pairs"]
            ),
            "input_characters": len(
                json.dumps(packet, ensure_ascii=False)
            ),
            "input_file": str(input_path.relative_to(BATCH_ROOT)),
        }

    manifest = sorted(
        existing_manifest.values(),
        key=lambda row: row["technical_document_id"],
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)

    print(
        f"已准备{args.model}的{len(documents)}份文档级归并输入；"
        "未调用API。"
    )
    selected_ids = {
        row["technical_document_id"] for row in documents
    }
    for row in manifest:
        if row["technical_document_id"] not in selected_ids:
            continue
        print(
            f"  {row['technical_document_id']} | "
            f"{row['dialogue_segment_count']}对话片段 | "
            f"{row['candidate_count']}候选 | "
            f"{row['adjacent_pair_count']}相邻候选对 | "
            f"{row['input_characters']}字符"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
