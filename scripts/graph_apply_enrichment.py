#!/usr/bin/env python3
"""图谱补齐后处理：把 L1/L2 原始响应校验后落成 18 张 CSV（零 API、可反复重跑）。

读取 graph_layers/<模型目录>/<文档>/raw/*.json 与 L0 已生成的底座表：
  - 校验任务输出（必填、封闭枚举、引用完整性、逐字证据、每事件恰一条时间）
  - 用 verbatim_text.find() 确定性计算并回验字符偏移，不信任模型给的数字
  - 生成 process_stages / stage_next / event_times / time_expressions / 实体四表
  - 回填 event_nodes 与 event_participants，重算 source_attachments 与 coverage_audit
  - 生成 annotation_bundle.json 供 validate_annotation_bundle.py 使用

用法：
    python3 scripts/graph_apply_enrichment.py --document BATCH02-DOC01 --model cuc/qwen          # 预览
    python3 scripts/graph_apply_enrichment.py --document BATCH02-DOC01 --model cuc/qwen --write   # 落盘
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
sys.path.insert(0, str(SCRIPT_DIR))

from graph_build_base_tables import (  # noqa: E402
    GRAPH_ROOT,
    TEMPLATE_DIR,
    display_path,
    load_context,
    safe_model_name,
    template_header,
    write_table,
)

DEMO_ROOT = PROJECT_DIR.parent / "现行标注"
ENUM_PATH = DEMO_ROOT / "00_模板" / "enumerations.json"
REVIEW_ROOT = PROJECT_DIR / "04_54份正式语料批处理" / "review_queue"

ALL_TABLES = (
    "documents", "source_segments", "source_attachments", "coverage_audit",
    "document_annotations", "event_nodes", "event_processes", "event_participants",
    "event_circumstances", "event_next", "process_stages", "stage_next",
    "event_times", "time_expressions", "entities", "entity_mentions",
    "entity_aliases", "entity_relations",
)
BUNDLE_KEYS = {
    "documents": "document",
    "source_segments": "source_segments",
    "source_attachments": "source_attachments",
    "event_nodes": "events",
    "event_processes": "processes",
    "event_participants": "participants",
    "event_circumstances": "circumstances",
    "process_stages": "stages",
    "stage_next": "stage_next",
    "event_next": "event_next",
    "entities": "entities",
    "entity_mentions": "entity_mentions",
    "entity_aliases": "entity_aliases",
    "entity_relations": "entity_relations",
    "event_times": "event_times",
    "time_expressions": "time_expressions",
    "document_annotations": "document_annotations",
    "coverage_audit": "coverage_audit",
}

# ---- 研究者 2026-11-08 裁决（E2 / T2）----
# 词表严格沿用人工 6 份 Demo 的 5 类，不新增值、不新增列、不嵌套。
# 模型超纲的 DIRECTION / OTHER 按确定性规则就近归入 5 类之一，
# 一律降 confidence=LOW 并出复核清单，留待 E3「后面再标」人工改判。
CIRCUMSTANCE_KINDS = ("TIME", "LOCATION", "MANNER", "CAUSE", "PURPOSE")
TIME_LIKE = re.compile(r"[0-9一二三四五六七八九十两半几]+\s*(?:个?小时|分钟|天|日|年|个月|周|星期)")
PURPOSE_LIKE = re.compile(r"为了|便于|以便|目的是|好让|免得")
CAUSE_LIKE = re.compile(r"因为|由于|鉴于|迫于")


def fold_circumstance_kind(kind: str, value_text: str) -> tuple[str, bool]:
    """返回（人工 5 类中的一类, 是否发生就近归类需人工复核）。"""
    if kind in CIRCUMSTANCE_KINDS:
        return kind, False
    if kind == "DIRECTION":
        return "LOCATION", True
    text = value_text or ""
    if PURPOSE_LIKE.search(text):
        return "PURPOSE", True
    if CAUSE_LIKE.search(text):
        return "CAUSE", True
    if TIME_LIKE.search(text):
        return "TIME", True
    return "MANNER", True


def enrich_circumstances(
    rows: list[dict[str, Any]],
    ctx: dict[str, Any],
    segment_text: dict[str, str],
    entity_by_name: dict[str, dict[str, Any]],
    time_expressions: list[dict[str, Any]],
    event_times: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """按人工 119 条口径补齐 event_circumstances 三字段（零 API、确定性、可反复重跑）。

    人工惯例：normalized_value 只给 TIME / LOCATION，CAUSE / MANNER / PURPOSE 一律留空；
    evidence_segment_id 逐条指向真正逐字命中的原文片段；confidence 按证据强弱给 HIGH/MEDIUM/LOW。
    """
    event_segments = {
        event["document_event_id"]: event.get("source_segment_ids", [])
        for event in ctx["events"]
    }
    # 原始 kind 一律从只读的归并结果恢复，不依赖 L0 表当前状态：
    # 后处理会覆盖 event_circumstances.csv，若从这里读会让第二次重跑丢失「就近归类」留痕。
    original_kinds: dict[str, str] = {}
    for event in ctx["events"]:
        for number, item in enumerate(event.get("canonical_event", {}).get("circumstances", []), start=1):
            original_kinds[f"{event['document_event_id']}-C{number:02d}"] = item.get("kind", "")
    time_by_raw = {item["raw_text"]: item for item in time_expressions if item.get("raw_text")}
    time_by_event = {item["event_id"]: item for item in event_times}

    reclassified: list[dict[str, str]] = []
    for row in rows:
        original_kind = original_kinds.get(row.get("circumstance_id", ""), row.get("kind", ""))
        value = (row.get("value_text") or "").strip()
        kind, changed = fold_circumstance_kind(original_kind, value)
        row["kind"] = kind

        # 1) 证据片段：在该一级事件的原文范围内逐字定位，不再硬塞事件首片段
        hit = next(
            (sid for sid in event_segments.get(row.get("event_id", ""), [])
             if value and value in segment_text.get(sid, "")),
            "",
        )
        if hit:
            row["evidence_segment_id"] = hit
            row["confidence"] = "HIGH"
        else:
            row["confidence"] = "LOW"

        # 2) normalized_value：按人工惯例只给 TIME / LOCATION
        normalized = ""
        entity_id = ""
        if kind == "TIME":
            time_item = time_by_raw.get(value)
            if time_item is None:
                time_item = next(
                    (item for raw, item in time_by_raw.items() if raw and raw in value), None
                )
            if time_item:
                start = time_item.get("normalized_start", "")
                end = time_item.get("normalized_end", "")
                normalized = f"{start}/{end}" if start and end and end != start else start
            else:
                fallback = time_by_event.get(row.get("event_id", ""), {})
                normalized = fallback.get("normalized_start", "")
                if not normalized and row["confidence"] == "HIGH":
                    row["confidence"] = "MEDIUM"
        elif kind == "LOCATION":
            entity = entity_by_name.get(value)
            if entity is None:
                entity = next(
                    (item for name, item in entity_by_name.items()
                     if name and (name in value or value in name)), None
                )
            if entity:
                normalized = entity.get("canonical_name", "")
                entity_id = entity.get("entity_id", "")
        # CAUSE / MANNER / PURPOSE 保持留空，与人工 46 条一致
        row["normalized_value"] = normalized
        row["entity_id"] = entity_id

        reasons: list[str] = []
        if changed:
            row["confidence"] = "LOW"
            reasons.append("就近归类待改判")
        if kind in ("TIME", "LOCATION") and not normalized:
            reasons.append("规范化值待人工补")
        if reasons:
            reclassified.append({
                "circumstance_id": row.get("circumstance_id", ""),
                "event_id": row.get("event_id", ""),
                "original_kind": original_kind,
                "folded_kind": kind,
                "value_text": value,
                "evidence_segment_id": row.get("evidence_segment_id", ""),
                "reason": "；".join(reasons),
            })
    return reclassified


def read_table(folder: Path, table: str) -> list[dict[str, str]]:
    with (folder / f"{table}.csv").open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_raw(folder: Path, task: str) -> list[dict[str, Any]]:
    raw_dir = folder / "raw"
    records = []
    for path in sorted(raw_dir.glob(f"{task}_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("parsed") is not None and not data.get("request_error"):
            records.append({"path": path, "data": data})
    return records


def unique_offset(segment_text: str, needle: str) -> tuple[int, int] | None:
    if not needle or needle not in segment_text:
        return None
    first = segment_text.find(needle)
    if segment_text.find(needle, first + 1) != -1:
        return None
    return first, first + len(needle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", required=True)
    parser.add_argument("--model", default="cuc/qwen")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    folder = GRAPH_ROOT / safe_model_name(args.model) / args.document
    if not (folder / "source_segments.csv").exists():
        print(f"失败：找不到 L0 底座表，请先运行 graph_build_base_tables.py --document {args.document} --model {args.model} --write", file=sys.stderr)
        return 2

    try:
        ctx = load_context(args.document, args.model)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 2

    tables = {name: read_table(folder, name) for name in ALL_TABLES if (folder / f"{name}.csv").exists()}
    for name in ALL_TABLES:
        tables.setdefault(name, [])
    segment_text = {row["segment_id"]: row["verbatim_text"] for row in tables["source_segments"]}
    event_ids = [row["event_id"] for row in tables["event_nodes"]]
    event_set = set(event_ids)
    enums = json.loads(ENUM_PATH.read_text(encoding="utf-8"))

    stage_records = load_raw(folder, "stage")
    entity_records = load_raw(folder, "entity_time")
    issues: list[str] = []
    unresolved: list[str] = []

    if not stage_records or not entity_records:
        print("警告：stage / entity_time 原始响应不齐全，本次只生成占位表头，不算验证通过。", file=sys.stderr)

    # ---- L1: stages ----
    stages: list[dict[str, Any]] = []
    stage_next: list[dict[str, Any]] = []
    stage_segment_map: dict[str, list[str]] = defaultdict(list)
    enrichment: dict[str, dict[str, Any]] = {}
    all_stage_ids: set[str] = set()
    for record in stage_records:
        parsed = record["data"]["parsed"]
        event_id = parsed.get("event_id", "")
        if event_id not in event_set:
            issues.append(f"{record['path'].name}: 未知 event_id={event_id}")
            continue
        enrichment[event_id] = parsed.get("event_enrichment", {})
        local_ids: list[str] = []
        for stage in parsed.get("stages", []):
            sid = stage.get("stage_id", "")
            if sid in all_stage_ids:
                issues.append(f"重复 stage_id={sid}")
                continue
            all_stage_ids.add(sid)
            local_ids.append(sid)
            quote = stage.get("evidence_quote", "")
            hit = any(quote and quote in segment_text.get(seg, "") for seg in stage.get("evidence_segment_ids", []))
            if not hit:
                issues.append(f"{sid}: evidence_quote 未在指定片段内逐字命中，阶段保留但降为 LOW / NEEDS_REVIEW")
            for seg in stage.get("evidence_segment_ids", []):
                if seg in segment_text:
                    stage_segment_map[seg].append(sid)
                else:
                    issues.append(f"{sid}: 引用未知片段 {seg}")
            stages.append({
                "stage_id": sid,
                "event_id": event_id,
                "stage_order": stage.get("stage_order", len(local_ids)),
                "stage_summary": stage.get("stage_summary", ""),
                "process_text": stage.get("process_text", ""),
                "confidence": "LOW" if not hit else stage.get("confidence", "MEDIUM"),
                "review_status": "NEEDS_REVIEW" if not hit else "MODEL_CANDIDATE",
            })
        for link in parsed.get("stage_next", []):
            src, dst = link.get("source_stage_id", ""), link.get("target_stage_id", "")
            if src not in local_ids or dst not in local_ids:
                issues.append(f"{event_id}: stage_next 跨事件或引用未知阶段 {src}->{dst}")
                continue
            logic = link.get("logic", "")
            if logic not in enums["stage_logic"]:
                issues.append(f"{event_id}: 非法 stage_logic={logic}")
                continue
            stage_next.append({
                "source_stage_id": src,
                "target_stage_id": dst,
                "logic": logic,
                "evidence_segment_id": link.get("evidence_segment_id", ""),
                "confidence": link.get("confidence", "MEDIUM"),
                "review_status": "MODEL_CANDIDATE",
            })

    tables["process_stages"] = stages
    tables["stage_next"] = stage_next

    for row in tables["event_nodes"]:
        extra = enrichment.get(row["event_id"], {})
        for key in ("result_state", "factuality", "confidence", "boundary_note", "boundary_confidence"):
            row[key] = extra.get(key, "")

    # ---- L2: entity_time ----
    entities: list[dict[str, Any]] = []
    mentions: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    event_times: list[dict[str, Any]] = []
    time_expressions: list[dict[str, Any]] = []
    entity_ids: set[str] = set()
    time_events: set[str] = set()

    for record in entity_records:
        parsed = record["data"]["parsed"]
        for entity in parsed.get("entities", []):
            if entity.get("entity_type") not in enums["entity_type"]:
                issues.append(f"非法 entity_type={entity.get('entity_type')}")
                continue
            entity_ids.add(entity.get("entity_id", ""))
            entities.append({
                "entity_id": entity.get("entity_id", ""),
                "canonical_name": entity.get("canonical_name", ""),
                "entity_type": entity.get("entity_type", ""),
                "entity_subtype": entity.get("entity_subtype", ""),
                "description": entity.get("description", ""),
                "authority_status": entity.get("authority_status", ""),
                "confidence": entity.get("confidence", "MEDIUM"),
                "review_status": "MODEL_CANDIDATE",
            })
        for mention in parsed.get("entity_mentions", []):
            sid, text = mention.get("segment_id", ""), mention.get("mention_text", "")
            if sid not in segment_text or mention.get("entity_id", "") not in entity_ids:
                issues.append(f"entity_mentions 引用未知片段/实体：{mention.get('mention_id')}")
                continue
            offset = unique_offset(segment_text[sid], text)
            if offset is None:
                unresolved.append(f"mention {mention.get('mention_id')}：'{text[:20]}' 在 {sid} 内未唯一命中，跳过并待人工补")
                continue
            mentions.append({
                "mention_id": mention.get("mention_id", ""),
                "segment_id": sid,
                "entity_id": mention.get("entity_id", ""),
                "mention_text": text,
                "start_offset": offset[0],
                "end_offset": offset[1],
                "mention_function": mention.get("mention_function", ""),
                "source_status": mention.get("source_status", ""),
                "confidence": mention.get("confidence", "MEDIUM"),
                "review_status": "MODEL_CANDIDATE",
            })
        for alias in parsed.get("entity_aliases", []):
            if alias.get("entity_id", "") not in entity_ids:
                issues.append(f"别名引用未知实体 {alias.get('entity_id')}")
                continue
            aliases.append({
                "alias_id": alias.get("alias_id", ""), "entity_id": alias.get("entity_id", ""),
                "alias_text": alias.get("alias_text", ""), "alias_type": alias.get("alias_type", ""),
                "evidence_segment_id": alias.get("evidence_segment_id", ""),
                "confidence": alias.get("confidence", "MEDIUM"), "review_status": "MODEL_CANDIDATE",
            })
        for relation in parsed.get("entity_relations", []):
            if relation.get("source_entity_id", "") not in entity_ids or relation.get("target_entity_id", "") not in entity_ids:
                issues.append(f"实体关系引用未知实体 {relation.get('relation_id')}")
                continue
            relations.append({
                "relation_id": relation.get("relation_id", ""),
                "source_entity_id": relation.get("source_entity_id", ""),
                "relation_type": relation.get("relation_type", ""),
                "target_entity_id": relation.get("target_entity_id", ""),
                "role_label": relation.get("role_label", ""),
                "start_date": relation.get("start_date", ""), "end_date": relation.get("end_date", ""),
                "evidence_segment_id": relation.get("evidence_segment_id", ""),
                "source_status": relation.get("source_status", ""),
                "confidence": relation.get("confidence", "MEDIUM"), "review_status": "MODEL_CANDIDATE",
            })
        for item in parsed.get("event_times", []):
            eid = item.get("event_id", "")
            if eid not in event_set or eid in time_events:
                issues.append(f"event_times 事件不存在或重复：{eid}")
                continue
            time_events.add(eid)
            event_times.append({
                "event_time_id": f"{eid}-T01", "event_id": eid,
                "raw_text": item.get("raw_text", ""),
                "normalized_start": item.get("normalized_start", ""),
                "normalized_end": item.get("normalized_end", ""),
                "precision": item.get("precision", "UNKNOWN"),
                "certainty": item.get("certainty", "UNCERTAIN"),
                "source_status": item.get("source_status", "STRUCTURAL_INFERENCE"),
                "evidence_segment_id": item.get("evidence_segment_id", ""),
                "confidence": item.get("confidence", "LOW"), "review_status": "MODEL_CANDIDATE",
            })
        for number, item in enumerate(parsed.get("time_expressions", []), start=1):
            sid, text = item.get("segment_id", ""), item.get("raw_text", "")
            if sid not in segment_text:
                issues.append(f"time_expression 引用未知片段 {sid}")
                continue
            offset = unique_offset(segment_text[sid], text)
            if offset is None:
                unresolved.append(f"time_expression：'{text[:20]}' 在 {sid} 内未唯一命中，跳过并待人工补")
                continue
            time_expressions.append({
                "time_expression_id": f"{ctx['doc_meta']['doc_id']}-TX{number:04d}",
                "segment_id": sid, "raw_text": text,
                "normalized_start": item.get("normalized_start", ""),
                "normalized_end": item.get("normalized_end", ""),
                "precision": item.get("precision", "UNKNOWN"),
                "expression_type": item.get("expression_type", "DATE"),
                "certainty": item.get("certainty", "UNCERTAIN"),
                "start_offset": offset[0], "end_offset": offset[1],
                "source_status": item.get("source_status", ""),
                "confidence": item.get("confidence", "MEDIUM"), "review_status": "MODEL_CANDIDATE",
            })

    for eid in event_set - time_events:
        issues.append(f"{eid} 缺 event_times，补一条结构性推断记录")
        event_times.append({
            "event_time_id": f"{eid}-T01", "event_id": eid, "raw_text": "",
            "normalized_start": "", "normalized_end": "", "precision": "RELATIVE",
            "certainty": "UNCERTAIN", "source_status": "STRUCTURAL_INFERENCE",
            "evidence_segment_id": "", "confidence": "LOW", "review_status": "NEEDS_REVIEW",
        })

    tables["entities"] = entities
    tables["entity_mentions"] = mentions
    tables["entity_aliases"] = aliases
    tables["entity_relations"] = relations
    tables["event_times"] = event_times
    tables["time_expressions"] = time_expressions

    # import.cypher 的 HAS_PARTICIPANT 用 MATCH (x:Entity {entity_id:row.entity_id})，
    # 空 entity_id 会导致该关系根本不进图谱；同时合并去重键含 entity_id，空值会互相撞键丢行。
    # 因此凡未匹配到实体的参与者，一律建立明确标注的待消歧占位实体，保证外键完整、信息不丢。
    doc_id_for_placeholder = ctx["doc_meta"]["doc_id"]
    entity_by_name: dict[str, dict[str, Any]] = {row["canonical_name"]: row for row in entities}
    placeholder_index = 0
    for row in tables["event_participants"]:
        name = (row.get("entity_name") or "").strip() or "未指名参与者"
        hit = entity_by_name.get(name)
        if hit is None:
            placeholder_index += 1
            hit = {
                "entity_id": f"UNRESOLVED-{doc_id_for_placeholder}-P{placeholder_index:03d}",
                "canonical_name": name,
                "entity_type": "OTHER",
                "entity_subtype": "OTHER",
                "description": "模型给出的参与者未能匹配到实体表，待人工消歧",
                "authority_status": "UNRESOLVED",
                "confidence": "LOW",
                "review_status": "NEEDS_REVIEW",
            }
            entities.append(hit)
            entity_by_name[name] = hit
        row["entity_id"] = hit["entity_id"]
        row["entity_type"] = hit["entity_type"]
        if hit["review_status"] == "NEEDS_REVIEW":
            row["confidence"] = "LOW"
    tables["entities"] = entities

    # ---- E2 / T2：按人工口径整理环境成分（零 API、确定性）----
    reclassified = enrich_circumstances(
        tables["event_circumstances"], ctx, segment_text, entity_by_name,
        time_expressions, event_times,
    )
    if reclassified:
        print(f"  环境成分待人工复核 {len(reclassified)} 条（就近归类／规范值待补，另出清单）")

    # ---- 重算挂接与覆盖 ----
    attachments = [row for row in tables["source_attachments"] if row.get("target_type") != "STAGE"]
    doc_id = ctx["doc_meta"]["doc_id"]
    max_index = max(
        (int(row["attachment_id"].rsplit("AT", 1)[-1]) for row in attachments if "AT" in row["attachment_id"]),
        default=0,
    )
    for sid, stage_ids in sorted(stage_segment_map.items()):
        for stage_id in stage_ids:
            max_index += 1
            attachments.append({
                "attachment_id": f"{doc_id}-AT{max_index:04d}", "segment_id": sid,
                "target_type": "STAGE", "target_id": stage_id, "function": "EVIDENCE",
                "quote_start_offset": "", "quote_end_offset": "",
                "confidence": "MEDIUM", "review_status": "MODEL_CANDIDATE",
            })
    tables["source_attachments"] = attachments

    attached = {row["segment_id"] for row in attachments}
    total = len(tables["source_segments"])
    coverage = "1.0000" if len(attached) == total else f"{len(attached) / total:.4f}"
    tables["coverage_audit"] = [{
        "doc_id": doc_id,
        "total_characters": ctx["doc_meta"].get("body_character_count", ""),
        "segmented_characters": sum(len(row["verbatim_text"]) for row in tables["source_segments"]),
        "uncovered_characters": 0 if coverage == "1.0000" else "",
        "overlap_characters": 0,
        "total_segments": total,
        "attached_segments": len(attached),
        "document_only_segments": sum(1 for row in attachments if row.get("target_type") == "DOCUMENT"),
        "coverage_rate": coverage,
        "audit_status": "PASS" if coverage == "1.0000" else "FAIL",
    }]

    bundle: dict[str, Any] = {}
    for table, key in BUNDLE_KEYS.items():
        rows = tables[table]
        bundle[key] = rows[0] if table in ("documents", "coverage_audit") and rows else rows
    bundle["status_note"] = {
        "layer": "GRAPH_ENRICHMENT_V1.0",
        "model_id": args.model,
        "prompt_version": "graph_enrichment_v1.0",
        "schema_version": "v1.0",
        "review_status": "MODEL_CANDIDATE",
    }

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "layer": "L1_L2_APPLY",
        "technical_document_id": args.document,
        "model_id": args.model,
        "api_calls": 0,
        "raw_stage_records": len(stage_records),
        "raw_entity_time_records": len(entity_records),
        "tables": {name: len(tables[name]) for name in ALL_TABLES},
        "coverage_rate": coverage,
        "circumstance_kind": "人工 5 值（TIME/LOCATION/MANNER/CAUSE/PURPOSE）",
        "circumstances_needs_review": len(reclassified),
        "issues": issues,
        "unresolved_offsets": unresolved,
        "complete": bool(stage_records and entity_records),
    }

    print(f"{'[落盘]' if args.write else '[预览]'} {args.document} / {args.model}")
    print(f"  stage 响应 {len(stage_records)}｜entity_time 响应 {len(entity_records)}｜覆盖率 {coverage}")
    for name in ALL_TABLES:
        print(f"    {name:<22} {len(tables[name]):>5} 行")
    print(f"  校验问题 {len(issues)} 条｜偏移待核 {len(unresolved)} 条")

    if args.write:
        for name in ALL_TABLES:
            write_table(folder, name, tables[name])
        (folder / "annotation_bundle.json").write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (folder / "L1L2_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if unresolved:
            REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
            lines = [f"# {args.document} 图谱层偏移待人工核对", "",
                     f"> 生成时间：{report['generated_at']}　模型：{args.model}　零 API", ""]
            lines += [f"- {item}" for item in unresolved]
            (REVIEW_ROOT / f"{args.document}_图谱层偏移待核_{datetime.now():%Y%m%d}.md").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )
        if reclassified:
            REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
            out = [
                f"# {args.document} 环境成分人工复核清单（E3 后置）", "",
                f"> 生成时间：{report['generated_at']}　模型：{args.model}　零 API",
                "> 研究者 2026-11-08 裁决：`circumstance_kind` 严格沿用人工 5 类，",
                "> 模型超纲的 `DIRECTION`／`OTHER` 按确定性规则就近归入 5 类之一，降 `confidence=LOW`；",
                "> TIME／LOCATION 中零 API 补不出规范值的，留空并同列于此。",
                "> **语料与 `value_text` 一条未删**，请按 E3 安排人工逐条改判／补值。", "",
                "| 编号 | 事件 | 原值 | 归入 | 原文 | 证据片段 | 待办 |",
                "|---|---|---|---|---|---|---|",
            ]
            for item in reclassified:
                out.append(
                    f"| {item['circumstance_id']} | {item['event_id']} | "
                    f"`{item['original_kind']}` | `{item['folded_kind']}` | "
                    f"{item['value_text'].replace('|', '/')} | {item['evidence_segment_id']} | "
                    f"{item['reason']} |"
                )
            (REVIEW_ROOT / f"{args.document}_环境成分归类待复核_{datetime.now():%Y%m%d}.md").write_text(
                "\n".join(out) + "\n", encoding="utf-8"
            )
        print(f"  已写入：{display_path(folder)}")

    return 0 if report["complete"] and coverage == "1.0000" else 1


if __name__ == "__main__":
    raise SystemExit(main())
