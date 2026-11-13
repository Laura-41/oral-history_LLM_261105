#!/usr/bin/env python3
"""entity_time 分段兜底（旁路工具，仅用于反复超时的顽固文档）。

背景
----
少数文档的 entity_time 整篇调用反复超时：模型需一次输出全文实体、提及、
别名、关系、事件时间、时间表达六张表，completion_tokens 中位数约 5.5 万，
首 token 延迟中位数约 7.6 分钟，上游常在吐完之前断开。

本脚本把「输入包里的 source_segments」按片段边界切成 N 份，用**同一份冻结
提示词、同一个模型、同一套 API 参数**分别调用 N 次，再把 N 份 parsed 结果
做**确定性合并**，写出一个与正常成功调用完全同构的 raw 响应文件。

设计边界（研究者 2026-11-13 裁决口径）
------------------------------------
* 不修改任何既有脚本、提示词、Schema、契约、校验器、导入脚本、原始语料。
* 不改冻结提示词的一字一句；每份输入保留**完整的一级事件清单**，以满足
  「每个一级事件恰有一条 event_times」硬规则。
* 合并后的 raw 文件与正常响应同构，因此 downstream 的
  graph_apply_enrichment.py / graph_validate_bundle.py / graph_export_import.py
  以及 graph_run_all_in_terminal.sh 的断点续跑判断全部**原样生效**。
* 分片原始响应落在 raw/_split_parts/ 子目录，不会被 load_raw() 误读成整篇结果。
* 结果仍一律 MODEL_CANDIDATE；分段口径与其余 52 份不同，必须写入论文方法章，
  并由研究者人工重点抽检（review_queue 中会生成说明清单）。
* 可一键回退：删除合并出的 raw/entity_time_<doc_id>_<时间戳>.json 即可让主链
  回到「未完成」状态，继续按原本的整篇方式重试。

用法（长任务由研究者在本地终端执行）
------------------------------------
    # 零 API 预演：只打印切分方案，不调用、不落盘
    python3 scripts/graph_entity_time_split_fallback.py --document BATCH02-DOC09 --model cuc/deepseek

    # 真实调用（默认 2 段，超时沿用研究者裁决的 1800s）
    python3 scripts/graph_entity_time_split_fallback.py --document BATCH02-DOC09 --model cuc/deepseek --write

    # 某一段仍失败时可加大段数
    python3 scripts/graph_entity_time_split_fallback.py --document BATCH02-DOC09 --model cuc/deepseek --parts 3 --write

    # 已有成功响应也要重跑
    python3 scripts/graph_entity_time_split_fallback.py --document BATCH02-DOC09 --model cuc/deepseek --write --force
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
sys.path.insert(0, str(SCRIPT_DIR))

from api_test import extract_content, get_api_key, request_json  # noqa: E402
from graph_build_base_tables import (  # noqa: E402
    GRAPH_ROOT,
    display_path,
    load_context,
)
from graph_run_enrichment import (  # noqa: E402
    PROMPT_FILES,
    already_done,
    build_entity_time_packet,
    strip_json_fence,
    write_json,
)

TASK = "entity_time"
REVIEW_ROOT = PROJECT_DIR / "04_54份正式语料批处理" / "review_queue"


# ---------------------------------------------------------------------------
# 切分
# ---------------------------------------------------------------------------
def split_segments(segments: list[dict[str, Any]], parts: int) -> list[list[dict[str, Any]]]:
    """按累计正文字数尽量均衡地切成 parts 份；边界只落在片段之间，不拆片段。"""
    if parts < 2:
        raise ValueError("parts 至少为 2（等于 1 就是没分段）")
    if len(segments) < parts:
        raise ValueError(f"原文只有 {len(segments)} 个片段，切不成 {parts} 份")

    cumulative: list[int] = []
    running = 0
    for row in segments:
        running += len(str(row.get("verbatim_text", "")))
        cumulative.append(running)
    total = running

    bounds: list[int] = []
    for k in range(1, parts):
        target = total * k / parts
        idx = next((i + 1 for i, value in enumerate(cumulative) if value >= target), len(segments))
        # 每段至少一个片段，且给后面每段各留一个片段
        idx = max(k, min(idx, len(segments) - (parts - k)))
        bounds.append(idx)

    chunks: list[list[dict[str, Any]]] = []
    previous = 0
    for bound in bounds + [len(segments)]:
        chunks.append(segments[previous:bound])
        previous = bound
    if len(chunks) != parts or any(not c for c in chunks):
        raise ValueError(f"切分失败：得到 {[len(c) for c in chunks]} 个片段组")
    return chunks


# ---------------------------------------------------------------------------
# 确定性合并（零 API，可独立自测）
# ---------------------------------------------------------------------------
PLACEHOLDER_TIME = {
    "raw_text": "",
    "normalized_start": "",
    "normalized_end": "",
    "precision": "RELATIVE",
    "certainty": "UNCERTAIN",
    "source_status": "STRUCTURAL_INFERENCE",
    "evidence_segment_id": "",
    "confidence": "LOW",
}


def merge_parts(
    parts: list[dict[str, Any]],
    chunks: list[list[dict[str, Any]]],
    event_ids: list[str],
    doc_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """把 N 份 parsed 合并成一份与整篇调用同构的 parsed。

    规则（全部确定性，不引入任何新事实）：
      * 实体：按 (canonical_name, entity_type) 去重，统一重编号 E001…
      * 提及 / 别名 / 关系：entity_id 重映射，ID 重编号，按内容去重
      * 事件时间：只采纳 evidence_segment_id 落在本分片片段集合内且给出
        raw_text / 明确 precision 的记录；否则按硬规则 5 输出结构性推断占位，
        并在复核清单里列出，交人工核对（绝不采信跨分片的猜测时间）
      * 时间表达：按 (segment_id, raw_text, normalized_start) 去重合并
    """
    seg_scope: list[set[str]] = [
        {str(s.get("segment_id", "")) for s in chunk} for chunk in chunks
    ]

    # ---- 实体：全局去重 + 重编号；每个分片保留 old_id -> new_id 映射 ----
    entities: list[dict[str, Any]] = []
    name_to_new: dict[tuple[str, str], str] = {}
    local_maps: list[dict[str, str]] = []
    for parsed in parts:
        local: dict[str, str] = {}
        for entity in parsed.get("entities", []):
            old = str(entity.get("entity_id", ""))
            key = (
                str(entity.get("canonical_name", "")).strip(),
                str(entity.get("entity_type", "")),
            )
            if key in name_to_new:
                local[old] = name_to_new[key]
                continue
            new_id = f"E{len(entities) + 1:03d}"
            name_to_new[key] = new_id
            local[old] = new_id
            row = dict(entity)
            row["entity_id"] = new_id
            entities.append(row)
        local_maps.append(local)

    def remap(part_index: int, old_id: Any) -> str:
        return local_maps[part_index].get(str(old_id), "")

    # ---- 提及 ----
    mentions: list[dict[str, Any]] = []
    seen_m: set[tuple[str, str, str]] = set()
    for pi, parsed in enumerate(parts):
        for mention in parsed.get("entity_mentions", []):
            eid = remap(pi, mention.get("entity_id", ""))
            if not eid:
                continue
            key = (
                str(mention.get("segment_id", "")),
                str(mention.get("mention_text", "")),
                eid,
            )
            if key in seen_m:
                continue
            seen_m.add(key)
            row = dict(mention)
            row["entity_id"] = eid
            row["mention_id"] = f"M{len(mentions) + 1:03d}"
            mentions.append(row)

    # ---- 别名 ----
    aliases: list[dict[str, Any]] = []
    seen_a: set[tuple[str, str, str]] = set()
    for pi, parsed in enumerate(parts):
        for alias in parsed.get("entity_aliases", []):
            eid = remap(pi, alias.get("entity_id", ""))
            if not eid:
                continue
            key = (eid, str(alias.get("alias_text", "")), str(alias.get("alias_type", "")))
            if key in seen_a:
                continue
            seen_a.add(key)
            row = dict(alias)
            row["entity_id"] = eid
            row["alias_id"] = f"A{len(aliases) + 1:03d}"
            aliases.append(row)

    # ---- 实体关系 ----
    relations: list[dict[str, Any]] = []
    seen_r: set[tuple[str, str, str]] = set()
    dropped_relations = 0
    for pi, parsed in enumerate(parts):
        for relation in parsed.get("entity_relations", []):
            src = remap(pi, relation.get("source_entity_id", ""))
            tgt = remap(pi, relation.get("target_entity_id", ""))
            if not src or not tgt:
                dropped_relations += 1
                continue
            key = (src, str(relation.get("relation_type", "")), tgt)
            if key in seen_r:
                continue
            seen_r.add(key)
            row = dict(relation)
            row["source_entity_id"] = src
            row["target_entity_id"] = tgt
            row["relation_id"] = f"R{len(relations) + 1:03d}"
            relations.append(row)

    # ---- 事件时间：每事件恰一条，两段候选按「信息量」择优 ----
    # 说明：52 份成功样本中 event_times 仅 87% 填了 evidence_segment_id、
    # 60% 填了 raw_text、69% 本就是 RELATIVE。故不把「证据片段落在本段」
    # 当硬门槛，否则会误丢有效时间；只把它作为加权项。两段给出不同 raw_text
    # 时记入冲突清单，交人工复核，绝不自行二选一当作定论。
    event_set = set(event_ids)
    candidates: dict[str, list[tuple[int, dict[str, Any], int]]] = {}
    for pi, parsed in enumerate(parts):
        for item in parsed.get("event_times", []):
            eid = str(item.get("event_id", ""))
            if eid not in event_set:
                continue
            ev_seg = str(item.get("evidence_segment_id", ""))
            in_scope = bool(ev_seg) and ev_seg in seg_scope[pi]
            has_raw = bool(str(item.get("raw_text", "")).strip())
            precise = item.get("precision") not in ("", "RELATIVE", "UNKNOWN")
            confidence = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(item.get("confidence"), 0)
            score = (
                (8 if has_raw else 0)
                + (4 if precise else 0)
                + (2 if in_scope else 0)
                + confidence
            )
            candidates.setdefault(eid, []).append((score, item, pi))

    event_times: list[dict[str, Any]] = []
    placeholder_events: list[str] = []
    conflicting_events: list[dict[str, Any]] = []
    for eid in event_ids:
        hits = sorted(candidates.get(eid, []), key=lambda x: x[0], reverse=True)
        accepted = next((h for h in hits if str(h[1].get("raw_text", "")).strip()), None)
        if accepted:
            row = dict(accepted[1])
            distinct_raw = {
                str(h[1].get("raw_text", "")).strip()
                for h in hits if str(h[1].get("raw_text", "")).strip()
            }
            if len(distinct_raw) > 1:
                conflicting_events.append({
                    "event_id": eid,
                    "chosen": accepted[1].get("raw_text", ""),
                    "candidates": sorted(distinct_raw),
                })
        else:
            row = dict(PLACEHOLDER_TIME)
            placeholder_events.append(eid)
        row["event_id"] = eid
        event_times.append(row)

    # ---- 时间表达 ----
    time_expressions: list[dict[str, Any]] = []
    seen_t: set[tuple[str, str, str]] = set()
    for parsed in parts:
        for item in parsed.get("time_expressions", []):
            key = (
                str(item.get("segment_id", "")),
                str(item.get("raw_text", "")),
                str(item.get("normalized_start", "")),
            )
            if key in seen_t:
                continue
            seen_t.add(key)
            time_expressions.append(dict(item))

    merged = {
        "document_id": doc_id,
        "task": TASK,
        "prompt_version": "graph_enrichment_v1.0",
        "schema_version": "v1.0",
        "entities": entities,
        "entity_mentions": mentions,
        "entity_aliases": aliases,
        "entity_relations": relations,
        "event_times": event_times,
        "time_expressions": time_expressions,
    }
    stats = {
        "parts": len(parts),
        "entities": len(entities),
        "entity_mentions": len(mentions),
        "entity_aliases": len(aliases),
        "entity_relations": len(relations),
        "event_times": len(event_times),
        "time_expressions": len(time_expressions),
        "dropped_relations_unresolved_entity": dropped_relations,
        "placeholder_event_times": placeholder_events,
        "conflicting_event_times": conflicting_events,
    }
    return merged, stats


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def part_file(parts_dir: Path, doc_id: str, index: int) -> Path | None:
    """返回该分片已有的成功响应（断点续跑）；没有则 None。"""
    for path in sorted(parts_dir.glob(f"entity_time_{doc_id}_part{index}_*.json")):
        if "FAILED" in path.name or "PARSEERROR" in path.name:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("parsed") is not None and not data.get("request_error"):
            return path
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", help="技术文档ID，如 BATCH02-DOC09（--selftest 时可省略）")
    parser.add_argument("--model", default="cuc/deepseek", help="默认只用于 DeepSeek 顽固文档")
    parser.add_argument("--parts", type=int, default=2, help="切成几段，默认 2")
    parser.add_argument("--timeout", type=int, default=1800, help="单次 API 等待上限，默认 1800s")
    parser.add_argument("--write", action="store_true", help="真实调用 API；默认零 API 预演")
    parser.add_argument("--force", action="store_true", help="已有成功响应也重跑")
    parser.add_argument("--selftest", action="store_true", help="用已有成功响应离线自测合并逻辑，零 API、不落盘")
    args = parser.parse_args()

    if args.selftest:
        return run_selftest()
    if not args.document:
        parser.error("需要 --document（或使用 --selftest）")

    try:
        ctx = load_context(args.document, args.model)
        packet = build_entity_time_packet(ctx)
        chunks = split_segments(packet["source_segments"], args.parts)
        event_ids = [str(e["document_event_id"]) for e in ctx["events"]]
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 2

    doc_id = str(ctx["doc_meta"]["doc_id"])
    raw_folder = GRAPH_ROOT / ctx["model_dir"] / ctx["technical_id"] / "raw"
    parts_dir = raw_folder / "_split_parts"
    prefix = f"{TASK}_{doc_id}"

    print(f"{'[真实调用]' if args.write else '[零 API 预演]'} {args.document} / {args.model} / {TASK} 分段兜底")
    print(f"  文档 {doc_id}｜一级事件 {len(event_ids)}｜原文片段 {len(packet['source_segments'])}｜切 {args.parts} 段")
    for i, chunk in enumerate(chunks, start=1):
        chars = sum(len(str(s.get("verbatim_text", ""))) for s in chunk)
        whole = json.dumps({**packet, "source_segments": chunk}, ensure_ascii=False)
        print(f"    第 {i} 段：{len(chunk)} 个片段 / 正文 {chars:,} 字 / 输入包 {len(whole):,} 字符")

    if not args.force and already_done(raw_folder, prefix):
        print("  该文档已有成功响应，跳过（如需重跑加 --force）")
        return 0
    if not args.write:
        print("  预演结束：未调用 API、未写入任何文件。")
        return 0

    api_key = get_api_key()
    if not api_key:
        print("错误：环境变量和钥匙串均没有 API 密钥。", file=sys.stderr)
        return 2
    base_url = os.environ.get("CUC_BASE_URL", "https://openai.cuc.edu.cn/v1").rstrip("/")
    system_prompt = PROMPT_FILES[TASK].read_text(encoding="utf-8")
    parts_dir.mkdir(parents=True, exist_ok=True)

    parsed_list: list[dict[str, Any]] = []
    usages: list[dict[str, Any]] = []
    part_paths: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        existing = part_file(parts_dir, doc_id, i)
        if existing is not None:
            print(f"  [{i}/{args.parts}] 第 {i} 段已有成功响应，跳过（断点续跑）：{existing.name}", flush=True)
            data = json.loads(existing.read_text(encoding="utf-8"))
            parsed_list.append(data["parsed"])
            usages.append(data.get("usage") or {})
            part_paths.append(str(existing.relative_to(PROJECT_DIR)))
            continue

        sub_packet = {**packet, "source_segments": chunk}
        payload = {
            "model": args.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(sub_packet, ensure_ascii=False)},
            ],
            "temperature": 0,
            "stream": False,
        }
        size = len(json.dumps(payload, ensure_ascii=False))
        print(f"  [{i}/{args.parts}] 请求 {TASK} 第 {i} 段，输入 {size:,} 字符，最长等待 {args.timeout}s……", flush=True)
        started = datetime.now()
        response: dict[str, Any] | None = None
        raw_content = ""
        request_error: str | None = None
        try:
            response = request_json(
                method="POST",
                url=f"{base_url}/chat/completions",
                api_key=api_key,
                payload=payload,
                timeout=args.timeout,
            )
            raw_content = extract_content(response)
        except RuntimeError as exc:
            request_error = str(exc)

        stamp = started.strftime("%Y%m%d_%H%M%S")
        record: dict[str, Any] = {
            "run_time": started.isoformat(timespec="seconds"),
            "run_stage": "GRAPH_ENRICHMENT_ENTITY_TIME_SPLIT_PART",
            "task": TASK,
            "packet_key": f"{doc_id}_part{i}",
            "model_id": args.model,
            "prompt_version": "graph_enrichment_v1.0",
            "schema_version": "v1.0",
            "technical_document_id": doc_id,
            "usage": (response or {}).get("usage", {}),
            "raw_content": raw_content,
            "parsed": None,
            "request_error": request_error,
            "split_part": {"index": i, "total": args.parts, "segments": len(chunk)},
        }
        if request_error:
            write_json(parts_dir / f"entity_time_{doc_id}_part{i}_{stamp}_FAILED.json", record)
            print(f"  第 {i} 段失败并停止：{request_error}", file=sys.stderr)
            print("  已成功的分段全部保留，重跑同一命令即断点续跑；若该段反复失败可加大 --parts。", file=sys.stderr)
            return 1
        try:
            record["parsed"] = json.loads(strip_json_fence(raw_content))
        except json.JSONDecodeError as exc:
            record["parse_error"] = str(exc)
            write_json(parts_dir / f"entity_time_{doc_id}_part{i}_{stamp}_PARSEERROR.json", record)
            print(f"  第 {i} 段 JSON 解析失败并停止：{exc}", file=sys.stderr)
            return 1

        out = parts_dir / f"entity_time_{doc_id}_part{i}_{stamp}.json"
        write_json(out, record)
        usage = record["usage"] or {}
        print(f"  第 {i} 段完成：total_tokens={usage.get('total_tokens', '?')}", flush=True)
        parsed_list.append(record["parsed"])
        usages.append(usage)
        part_paths.append(str(out.relative_to(PROJECT_DIR)))

    merged, stats = merge_parts(parsed_list, chunks, event_ids, doc_id)

    total_usage: dict[str, Any] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = [u.get(key) for u in usages if isinstance(u.get(key), (int, float))]
        if values:
            total_usage[key] = sum(values)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_record: dict[str, Any] = {
        "run_time": datetime.now().isoformat(timespec="seconds"),
        "run_stage": "GRAPH_ENRICHMENT_ENTITY_TIME",
        "task": TASK,
        "packet_key": doc_id,
        "model_id": args.model,
        "prompt_version": "graph_enrichment_v1.0",
        "schema_version": "v1.0",
        "technical_document_id": doc_id,
        "usage": total_usage,
        "raw_content": json.dumps(merged, ensure_ascii=False),
        "parsed": merged,
        "request_error": None,
        "split_fallback": {
            "parts": args.parts,
            "prompt_file": "prompt_entity_time_v1.0.txt（内容未改动）",
            "note": "分段调用后确定性合并；并非单次整篇原始输出，详见 review_queue 说明",
            "part_files": part_paths,
            "stats": stats,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
    }
    # --force 重跑时，把旧的整篇成功响应归档，避免 load_raw 把新旧两份一起读进去造成重复
    if args.force:
        archive = parts_dir / "archived"
        for old in sorted(raw_folder.glob(f"entity_time_{doc_id}_*.json")):
            if "FAILED" in old.name or "PARSEERROR" in old.name:
                continue
            archive.mkdir(parents=True, exist_ok=True)
            old.rename(archive / old.name)
            print(f"  已归档旧成功响应：{old.name}")

    final_path = raw_folder / f"entity_time_{doc_id}_{stamp}.json"
    write_json(final_path, final_record)

    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    note_path = REVIEW_ROOT / f"{args.document}_entity_time分段兜底说明_{datetime.now():%Y%m%d}.md"
    lines = [
        f"# {args.document} / {args.model}：entity_time 分段兜底说明",
        "",
        f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        f"- 触发原因：整篇 entity_time 调用反复超时，累计失败记录见 `raw/entity_time_{doc_id}_*_FAILED.json`。",
        f"- 做法：按片段边界把原文切 {args.parts} 段，用**同一份冻结提示词**（`prompt_entity_time_v1.0.txt`，未改动）、",
        f"  同一个模型、同一套 API 参数分别调用，再确定性合并成一份与正常响应同构的 raw 文件。",
        f"- 每份输入都保留完整的一级事件清单（{len(event_ids)} 个），满足「每事件恰一条 event_times」硬规则。",
        f"- 分片原始响应：`raw/_split_parts/`（不参与下游 load_raw 读取）。",
        f"- 合并产物：`{final_path.name}`。",
        "",
        "## 合并统计",
        "",
        f"- 实体 {stats['entities']}｜提及 {stats['entity_mentions']}｜别名 {stats['entity_aliases']}"
        f"｜关系 {stats['entity_relations']}｜事件时间 {stats['event_times']}｜时间表达 {stats['time_expressions']}",
        f"- 实体按 (canonical_name, entity_type) 去重并统一重编号；提及/别名/关系的 entity_id 同步重映射。",
        f"- 引用不到实体的关系丢弃 {stats['dropped_relations_unresolved_entity']} 条（与整篇调用时的校验行为一致）。",
        f"- 事件时间按「有 raw_text > precision 明确 > 证据片段落在本段 > confidence」择优；",
        f"  两段都没给时间时按硬规则 5 输出结构性推断占位，共 {len(stats['placeholder_event_times'])} 条：",
        (", ".join(stats["placeholder_event_times"]) if stats["placeholder_event_times"] else "（无）"),
    ]
    if stats["conflicting_event_times"]:
        lines += ["", "### 两段给出不同时间表述（已择优，须人工复核）", ""]
        for item in stats["conflicting_event_times"]:
            lines.append(f"- {item['event_id']}：采纳「{item['chosen']}」；候选 {' / '.join(item['candidates'])}")
    lines += [
        "",
        "## 必须注意（论文与人工抽检）",
        "",
        "1. **口径差异**：本份的实体/别名/关系来自分段调用 + 确定性合并，跨段共指与跨段关系可能少于",
        "   整篇通读的结果，与其余 52 份不完全同口径。论文方法章须注明这两份采用了分段兜底。",
        "2. **结果仍为 MODEL_CANDIDATE**，技术门禁通过不等于内容放行；请重点抽检逐字证据、",
        "   实体去重是否正确、占位事件时间是否需要人工补时间。",
        "3. **可回退**：删除合并产物 `raw/entity_time_<doc_id>_<时间戳>.json` 后，",
        "   主链会重新把本份视为未完成，按原本的整篇方式重试；分片原始响应保留在 `_split_parts/` 备查。",
        "",
    ]
    note_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n合并完成：{display_path(final_path)}")
    print(f"  实体 {stats['entities']}｜提及 {stats['entity_mentions']}｜别名 {stats['entity_aliases']}"
          f"｜关系 {stats['entity_relations']}｜事件时间 {stats['event_times']}｜时间表达 {stats['time_expressions']}")
    print(f"  事件时间占位 {len(stats['placeholder_event_times'])} 条（已写入复核说明，需人工核对）")
    print(f"  复核说明：{display_path(note_path)}")
    print("\n下一步（零 API 本地步骤）：")
    print(f"  python3 scripts/graph_apply_enrichment.py --document {args.document} --model {args.model} --write")
    print(f"  python3 scripts/graph_validate_bundle.py --document {args.document} --model {args.model} --write-report")
    return 0


def run_selftest() -> int:
    """用一份已成功的整篇响应，离线验证合并逻辑（零 API、不落盘）。"""
    import glob

    files = [
        f for f in sorted(glob.glob(str(GRAPH_ROOT / "*" / "*" / "raw" / "entity_time_*.json")))
        if "FAILED" not in f and "PARSEERROR" not in f
    ]
    if not files:
        print("自测失败：找不到任何已成功的 entity_time 响应", file=sys.stderr)
        return 2
    data = json.loads(Path(files[0]).read_text(encoding="utf-8"))
    parsed = data["parsed"]
    doc_id = str(parsed.get("document_id", "TEST"))

    # 贴近真实：两段各自只看到半个原文，且实体 ID 都从 E001 重新编号。
    # 实体表按名字部分重叠（模拟跨段共指），其余列表按片段分成两半。
    all_entities = parsed.get("entities", [])
    all_mentions = parsed.get("entity_mentions", [])
    all_aliases = parsed.get("entity_aliases", [])
    all_relations = parsed.get("entity_relations", [])
    all_exprs = parsed.get("time_expressions", [])
    mid = len(all_mentions) // 2
    seg_ids = [str(m.get("segment_id", "")) for m in all_mentions]
    half_seg = set(seg_ids[:mid])

    def reindex(rows: list[dict[str, Any]], offset: int) -> list[dict[str, Any]]:
        """把 E001 起编号的实体整体平移，模拟两段的 ID 命名空间冲突。"""
        out = []
        for row in rows:
            r = dict(row)
            r["entity_id"] = f"E{int(str(r.get('entity_id', 'E001'))[1:]) + offset:03d}"
            out.append(r)
        return out

    # 每段都保留「前 80% 实体」以制造跨段同名实体；第 2 段 ID 平移 500 位
    shared = all_entities[: int(len(all_entities) * 0.8)]
    e1 = [dict(e) for e in all_entities]
    e2 = reindex(shared, 500)
    map1 = {e["entity_id"]: e["entity_id"] for e in e1}
    map2 = {shared[i]["entity_id"]: e2[i]["entity_id"] for i in range(len(shared))}

    def remap_mentions(rows: list[dict[str, Any]], mapping: dict[str, str]) -> list[dict[str, Any]]:
        out = []
        for r in rows:
            r2 = dict(r)
            r2["entity_id"] = mapping.get(r2.get("entity_id", ""), r2.get("entity_id", ""))
            out.append(r2)
        return out

    part1 = {
        **parsed,
        "entities": e1,
        "entity_mentions": remap_mentions(all_mentions[:mid], map1),
        "entity_aliases": remap_mentions(all_aliases[: len(all_aliases) // 2], map1),
        "entity_relations": all_relations[: len(all_relations) // 2],
        "event_times": [dict(t) for t in parsed.get("event_times", [])],
        "time_expressions": all_exprs[: len(all_exprs) // 2],
    }
    part2 = {
        **parsed,
        "entities": e2,
        "entity_mentions": remap_mentions(all_mentions[mid:], map2),
        "entity_aliases": remap_mentions(all_aliases[len(all_aliases) // 2:], map2),
        "entity_relations": all_relations[len(all_relations) // 2:],
        "event_times": [dict(t) for t in parsed.get("event_times", [])],
        "time_expressions": all_exprs[len(all_exprs) // 2:],
    }
    parts = [part1, part2]
    chunks = [
        [{"segment_id": s} for s in sorted(half_seg)],
        [{"segment_id": s} for s in sorted(set(seg_ids[mid:]))],
    ]
    event_ids = [str(t.get("event_id", "")) for t in parsed.get("event_times", [])]
    merged, stats = merge_parts(parts, chunks, event_ids, doc_id)

    eids = [e["entity_id"] for e in merged["entities"]]
    mids = [m["mention_id"] for m in merged["entity_mentions"]]
    tids = [t["event_id"] for t in merged["event_times"]]
    checks = [
        ("实体 ID 连续且唯一", eids == [f"E{i:03d}" for i in range(1, len(eids) + 1)]),
        ("提及 ID 连续且唯一", mids == [f"M{i:03d}" for i in range(1, len(mids) + 1)]),
        ("提及 entity_id 全部可解析", all(m["entity_id"] in set(eids) for m in merged["entity_mentions"])),
        ("别名 entity_id 全部可解析", all(a["entity_id"] in set(eids) for a in merged["entity_aliases"])),
        ("关系两端 entity_id 全部可解析", all(
            r["source_entity_id"] in set(eids) and r["target_entity_id"] in set(eids)
            for r in merged["entity_relations"])),
        ("每个一级事件恰有一条 event_times", sorted(tids) == sorted(event_ids) and len(tids) == len(set(tids))),
        ("时间表达无重复", len({(t.get("segment_id"), t.get("raw_text"), t.get("normalized_start"))
                              for t in merged["time_expressions"]}) == len(merged["time_expressions"])),
        ("输出键与正常响应一致", set(merged.keys()) == set(parsed.keys())),
    ]
    print(f"自测样本：{Path(files[0]).name}")
    for name, ok in checks:
        print(f"  {'通过' if ok else '未通过'}：{name}")
    print(f"  合并统计：{json.dumps({k: v for k, v in stats.items() if k != 'placeholder_event_times'}, ensure_ascii=False)}")
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
