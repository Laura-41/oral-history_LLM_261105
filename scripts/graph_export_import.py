#!/usr/bin/env python3
"""图谱补齐 L3/L4：合并已验收文档，生成 Neo4j 全套 24 张 import CSV 与 Cypher（零 API）。

只合并 graph_layers/<模型目录>/ 下已通过 graph_validate_bundle.py 的文档目录；
输出到 05_合并与Neo4j/import_<模型目录>/，不覆盖六份 Demo 库。

用法：
    python3 scripts/graph_export_import.py --model cuc/qwen              # 预览
    python3 scripts/graph_export_import.py --model cuc/qwen --write       # 落盘
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from graph_build_base_tables import (  # noqa: E402
    GRAPH_ROOT,
    PERSON_ENTITY,
    STAGE_ROOT,
    display_path,
    safe_model_name,
)

DEMO_ROOT = PROJECT_DIR.parent / "现行标注"
IMPORT_CYPHER = DEMO_ROOT / "neo4j_demo" / "import.cypher"
EXPORT_ROOT = PROJECT_DIR / "05_合并与Neo4j"
BATCH_ROOT = PROJECT_DIR / "04_54份正式语料批处理"
MERGE_DECISION_ROOT = BATCH_ROOT / "human_adjudicated"
SUSPECT_REVIEW_ROOT = BATCH_ROOT / "review_queue"

# T3=不改：词表版本只在契约、导出报告里全局声明，不给任何 CSV 加列，24 表与人工 Demo 逐列一致。
VOCABULARY_VERSION = "v1.1"
VOCABULARY_NOTE = (
    "正式批次 v1.1：segment_type 沿用人工 7 值并新增 RECORDING_TIMESTAMP（共 8 值）；"
    "circumstance_kind 严格沿用人工 5 值，模型超纲值就近归类并标 NEEDS_REVIEW。"
)
# T4：疑似同一经历的判定阈值。只标疑似，绝不自动合并语料层。
SUSPECT_NAME_RATIO = 0.55
SUSPECT_MIN_COMMON_CHARS = 2

BASE_TABLES = (
    "documents", "source_segments", "source_attachments", "event_nodes",
    "event_processes", "event_participants", "event_circumstances",
    "process_stages", "stage_next", "event_next", "entities",
    "entity_mentions", "entity_aliases", "entity_relations",
    "event_times", "time_expressions", "document_annotations", "coverage_audit",
)
UNIQUE_KEYS = {
    "documents": ("doc_id",), "source_segments": ("segment_id",),
    "source_attachments": ("attachment_id",), "event_nodes": ("event_id",),
    "event_processes": ("process_id",),
    "event_participants": ("event_id", "entity_id", "role", "evidence_segment_id"),
    "event_circumstances": ("circumstance_id",),
    "process_stages": ("stage_id",),
    "stage_next": ("source_stage_id", "target_stage_id"),
    "event_next": ("source_event_id", "target_event_id"),
    "entities": ("entity_id",), "entity_mentions": ("mention_id",),
    "entity_aliases": ("alias_id",), "entity_relations": ("relation_id",),
    "event_times": ("event_time_id",), "time_expressions": ("time_expression_id",),
    "document_annotations": ("annotation_id",), "coverage_audit": ("doc_id",),
}
GENERATED_FIELDS = {
    "person_subjects": ["person_entity_id", "person_name", "biography_status", "review_status"],
    "document_persons": ["doc_id", "person_entity_id", "relation_type", "review_status"],
    "life_episodes": ["episode_id", "person_entity_id", "episode_name", "life_order", "normalized_start", "normalized_end", "precision", "certainty", "episode_scope", "confidence", "review_status"],
    "life_episode_sources": ["episode_id", "event_id", "source_role", "review_status"],
    "life_episode_next": ["source_episode_id", "target_episode_id", "person_entity_id", "basis", "overlap_possible", "confidence", "review_status"],
    "narrated_contexts": ["person_entity_id", "event_id", "context_order", "relation_type", "review_status"],
}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def approved_folders(model_dir: str) -> list[Path]:
    root = GRAPH_ROOT / model_dir
    if not root.exists():
        return []
    folders = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        report = folder / "VALIDATION_report.json"
        if not report.exists():
            continue
        try:
            if json.loads(report.read_text(encoding="utf-8")).get("valid"):
                folders.append(folder)
        except (json.JSONDecodeError, OSError):
            continue
    return folders


# ---- L3 人物生平：叠加视图（研究者 2026-11-10 T4=改） ----
#
# 口径（对应 D3 裁决与人工 Demo README:39）：
#   1. 语料层永不合并：Document / SourceSegment / EventNode / ProcessStage 各归各，
#      同一段经历在多次访谈里讲两遍，就是两个事件、两份原文。
#   2. 生平层是套在外面的一层视图：按人物真实历史时间排 LifeEpisode。
#   3. 不自动判定「同一经历」：跨文档、名称相似、时间不冲突 → 只标疑似，
#      life_episodes.review_status = NEEDS_REVIEW，另出人工复核清单。
#   4. 人工确认后才有合并：在 human_adjudicated/<模型>/life_episode_merges.csv
#      填一行 MERGE，重跑导出即生成 1 条 LifeEpisode + 多条 SUPPORTED_BY_EVENT。
#      没有该决策文件时行为与旧版一致（1 事件 = 1 生平），零副作用。


def normalized_name(text: str) -> str:
    return re.sub(r"[\s，。、；：！？（）()【】「」“”‘’—\-·,.;:!?]", "", text or "")


def name_similarity(a: str, b: str) -> float:
    x, y = normalized_name(a), normalized_name(b)
    if not x or not y:
        return 0.0
    return SequenceMatcher(None, x, y).ratio()


def time_conflict(a: dict, b: dict) -> bool:
    """两段时间的区间明确不重叠时返回 True；任一缺时间视为未知，不据此排除。"""
    sa, sb = a.get("normalized_start", ""), b.get("normalized_start", "")
    if not sa or not sb:
        return False
    ea = a.get("normalized_end", "") or sa
    eb = b.get("normalized_end", "") or sb
    return ea < sb or eb < sa


def detect_suspect_groups(items: list[dict]) -> list[dict]:
    """同一人物、跨文档、名称相似、时间不冲突 → 疑似同一经历（并查集连通分组）。"""
    count = len(items)
    parent = list(range(count))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    pairs: list[tuple[int, int, float]] = []
    for i in range(count):
        for j in range(i + 1, count):
            a, b = items[i], items[j]
            if a["doc_id"] == b["doc_id"]:
                continue  # 同一篇访谈内不判重复，避免把连续阶段误判成同一经历
            if time_conflict(a, b):
                continue
            sim = name_similarity(a["episode_name"], b["episode_name"])
            if sim < SUSPECT_NAME_RATIO:
                continue
            common = set(normalized_name(a["episode_name"])) & set(normalized_name(b["episode_name"]))
            if len(common) < SUSPECT_MIN_COMMON_CHARS:
                continue
            union(i, j)
            pairs.append((i, j, sim))

    buckets: dict[int, list[int]] = defaultdict(list)
    for i in range(count):
        buckets[find(i)].append(i)
    person = items[0].get("person_entity_id", "") if items else ""
    suffix = person.split("-")[-1] if person else "UNKNOWN"
    groups = []
    for _, members in sorted(buckets.items()):
        if len(members) < 2:
            continue
        # 同一篇访谈最多保留一个候选：并查集连通会「顺带」把同文档的其它相似事件
        # 连进组（例如 V1 的 DE004、DE005 都像 V3 的 DE002）。这些留在语料层当独立事件。
        first_by_doc: dict[str, int] = {}
        for i in sorted(members):
            first_by_doc.setdefault(items[i]["doc_id"], i)
        kept = sorted(first_by_doc.values())
        if len(kept) < 2:
            continue
        member_set = set(kept)
        best = max((sim for i, j, sim in pairs if i in member_set and j in member_set), default=0.0)
        if best == 0.0:
            continue  # 按文档去重后已无直接相似对，不标疑似
        groups.append({
            "group_id": f"{suffix}-S{len(groups) + 1:03d}",
            "person_entity_id": person,
            "items": [items[i] for i in kept],
            "max_similarity": round(best, 3),
        })
    return groups


def load_merge_decisions(model_dir: str, path: Path | None = None) -> dict[str, dict]:
    """人工合并入口。决策文件不存在时返回空字典，旧行为完全不变。"""
    decision_path = path or (MERGE_DECISION_ROOT / model_dir / "life_episode_merges.csv")
    if not decision_path.exists():
        return {}
    decisions: dict[str, dict] = {}
    with decision_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            gid = (row.get("group_id") or "").strip()
            decision = (row.get("decision") or "").strip().upper()
            if not gid or decision not in ("MERGE", "KEEP_SEPARATE"):
                continue
            decisions[gid] = {
                "decision": decision,
                "episode_name": (row.get("episode_name") or "").strip(),
                "event_ids": [x.strip() for x in (row.get("event_ids") or "").split("|") if x.strip()],
                "reviewer": (row.get("reviewer") or "").strip(),
            }
    return decisions


def build_biography_layer(
    by_person_episodes: dict[str, list[dict]],
    by_person_docs: dict[str, list[str]],
    by_person_context: dict[str, list[str]],
    name_by_id: dict[str, str],
    model_dir: str,
    decisions_path: Path | None = None,
) -> tuple[dict[str, list[dict]], list[dict], dict[str, int]]:
    """生成 6 张生平表 + 疑似清单数据 + 统计；24 表列名与人工 Demo 逐列一致。"""
    decisions = load_merge_decisions(model_dir, decisions_path)
    person_subjects, document_persons, life_episodes = [], [], []
    life_sources, life_next, narrated_contexts = [], [], []
    suspect_groups: list[dict] = []
    stats = {"suspect_groups": 0, "human_merged_episodes": 0, "human_keep_separate": 0}

    for person_id, docs in sorted(by_person_docs.items()):
        person_subjects.append({
            "person_entity_id": person_id, "person_name": name_by_id.get(person_id, ""),
            "biography_status": "BATCH_APPLICATION", "review_status": "MODEL_CANDIDATE",
        })
        for doc_id in sorted(docs):
            document_persons.append({
                "doc_id": doc_id, "person_entity_id": person_id,
                "relation_type": "INTERVIEW_OF", "review_status": "MODEL_CANDIDATE",
            })
        items = sorted(
            by_person_episodes.get(person_id, []),
            key=lambda x: (x["normalized_start"] == "", x["normalized_start"], x["event_id"]),
        )
        groups = detect_suspect_groups(items) if items else []
        suspect_groups.extend(groups)
        stats["suspect_groups"] += len(groups)

        # 一个 unit 最终生成一条 LifeEpisode；默认 1 事件 1 生平，人工 MERGE 后才多来源。
        units: list[dict] = []
        handled: set[str] = set()
        for group in groups:
            dec = decisions.get(group["group_id"], {})
            if dec.get("decision") == "MERGE":
                members = group["items"]
                if dec.get("event_ids"):
                    wanted = set(dec["event_ids"])
                    members = [m for m in members if m["event_id"] in wanted] or group["items"]
                units.append({
                    "members": members,
                    "episode_name": dec.get("episode_name") or members[0]["episode_name"],
                    "review_status": "CONFIRMED",
                    "group_id": group["group_id"], "merged": True,
                })
                handled.update(m["event_id"] for m in members)
                stats["human_merged_episodes"] += 1
            else:
                keep = dec.get("decision") == "KEEP_SEPARATE"
                if keep:
                    stats["human_keep_separate"] += 1
                for member in group["items"]:
                    units.append({
                        "members": [member], "episode_name": member["episode_name"],
                        "review_status": "CONFIRMED" if keep else "NEEDS_REVIEW",
                        "group_id": group["group_id"], "merged": False,
                    })
                    handled.add(member["event_id"])
        for item in items:
            if item["event_id"] not in handled:
                units.append({
                    "members": [item], "episode_name": item["episode_name"],
                    "review_status": "MODEL_CANDIDATE", "group_id": "", "merged": False,
                })

        def unit_start(unit: dict) -> str:
            starts = [m["normalized_start"] for m in unit["members"] if m.get("normalized_start")]
            return min(starts) if starts else ""

        units.sort(key=lambda u: (unit_start(u) == "", unit_start(u), u["members"][0]["event_id"]))
        episode_rows: list[tuple[dict, dict]] = []
        for index, unit in enumerate(units, start=1):
            members = unit["members"]
            first = members[0]
            starts = [m["normalized_start"] for m in members if m.get("normalized_start")]
            ends = [(m["normalized_end"] or m["normalized_start"]) for m in members if m.get("normalized_start")]
            episode_id = f"{person_id.split('-')[-1]}-L{index:03d}"
            episode = {
                "episode_id": episode_id, "person_entity_id": person_id,
                "episode_name": unit["episode_name"], "life_order": index,
                "normalized_start": min(starts) if starts else "",
                "normalized_end": max(ends) if ends else "",
                "precision": "INTERVAL" if len(set(starts)) > 1 else first.get("precision", "UNKNOWN"),
                "certainty": "APPROXIMATE" if len(members) > 1 else first.get("certainty", "UNCERTAIN"),
                "episode_scope": "PERSONAL_EXPERIENCE",
                "confidence": first.get("confidence", "LOW"),
                "review_status": unit["review_status"],
            }
            episode_rows.append((episode, unit))
            life_episodes.append(episode)
            for member in members:
                life_sources.append({
                    "episode_id": episode_id, "event_id": member["event_id"],
                    "source_role": "PRIMARY_EVIDENCE", "review_status": unit["review_status"],
                })
        for (current, cur_unit), (following, next_unit) in zip(episode_rows, episode_rows[1:]):
            overlap = "YES" if (current["normalized_end"] and following["normalized_start"]
                                and current["normalized_end"] >= following["normalized_start"]) else "NO"
            if cur_unit["group_id"] and cur_unit["group_id"] == next_unit["group_id"]:
                overlap = "YES"
            # 生平链是自动按时间排的，一律留 NEEDS_REVIEW 供 SOP §6 抽检；不因 T4 改造放宽。
            life_next.append({
                "source_episode_id": current["episode_id"], "target_episode_id": following["episode_id"],
                "person_entity_id": person_id, "basis": "HISTORICAL_TIME_AUTO_SORT",
                "overlap_possible": overlap, "confidence": "MEDIUM",
                "review_status": "NEEDS_REVIEW",
            })
        for index, event_id in enumerate(sorted(by_person_context.get(person_id, [])), start=1):
            narrated_contexts.append({
                "person_entity_id": person_id, "event_id": event_id,
                "context_order": index, "relation_type": "NARRATED_CONTEXT",
                "review_status": "MODEL_CANDIDATE",
            })

    generated = {
        "person_subjects": person_subjects, "document_persons": document_persons,
        "life_episodes": life_episodes, "life_episode_sources": life_sources,
        "life_episode_next": life_next, "narrated_contexts": narrated_contexts,
    }
    return generated, suspect_groups, stats


def write_suspect_review(model_dir: str, groups: list[dict]) -> Path | None:
    """疑似同一经历的人工复核清单；语料层不动，只请研究者决定生平层怎么挂。"""
    if not groups:
        return None
    SUSPECT_REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    out = SUSPECT_REVIEW_ROOT / f"{model_dir}_生平层疑似同一经历_待人工确认_{datetime.now():%Y%m%d}.md"
    decision_path = MERGE_DECISION_ROOT / model_dir / "life_episode_merges.csv"
    lines = [
        f"# 生平层疑似同一经历 · 待人工确认（{model_dir}）", "",
        f"> 生成时间：{datetime.now():%Y-%m-%d %H:%M}　零 API　依据：D3 不合并 + T4 叠加视图", "",
        "**语料层一律不动**：下面每个事件节点、原文片段、文档仍各自独立，绝不合并。",
        "生平层只是套在外面的一层视图；系统**不自动判定**同一经历，只把可能重复的",
        "`life_episodes.review_status` 标成 `NEEDS_REVIEW`，由你逐组确认。", "",
        "疑似规则（确定性、零 API）：同一人物 + **跨访谈** + 事件名相似 ≥ 0.55 + 时间不冲突；",
        "同一篇访谈里最多保留一个候选，其余相似事件仍留在语料层当独立事件，不并入疑似组。", "",
        "## 一、疑似组", "",
        "| 组号 | 人物 | 事件 | 文档 | 事件名 | 时间 | 名称相似度 |",
        "|---|---|---|---|---|---|---|",
    ]
    for group in groups:
        for item in group["items"]:
            span = item["normalized_start"] or "（未知）"
            if item["normalized_end"]:
                span += f"–{item['normalized_end']}"
            lines.append(
                f"| {group['group_id']} | {group['person_entity_id']} | {item['event_id']} | "
                f"{item['doc_id']} | {item['episode_name'].replace('|', '/')} | {span} | "
                f"{group['max_similarity']} |"
            )
    lines += [
        "", "## 二、你可以怎么裁", "",
        "- **什么都不填**：保持「1 个事件 = 1 条生平」，全部标 `NEEDS_REVIEW`，图谱照常可导。",
        "- **确认是同一段人生经历**：在下面决策文件里对该组填一行 `MERGE`。重跑导出后，",
        "  该组只生成 **1 条 `LifeEpisode`**，下面多个事件都通过 `SUPPORTED_BY_EVENT` 挂上去；",
        "  事件节点与原文片段仍然各归各。",
        "- **确认不是同一段经历**：填 `KEEP_SEPARATE`，该组恢复 `CONFIRMED`、维持多条生平。", "",
        "决策文件（**不自动创建，需要时手工新建**，这是人工裁决载体，不是新词表或新标签）：", "",
        f"`{display_path(decision_path)}`", "",
        "表头与写法：", "",
        "```csv",
        "group_id,person_entity_id,episode_name,event_ids,decision,reviewer,notes",
        "CHF-S001,PER-CHF,组建救亡会,CHF-V1-DE004|CHF-V3-DE002,MERGE,研究者,一访与三访讲的是同一段经历",
        "```", "",
        "- `event_ids` 用 `|` 分隔，留空表示该组全部事件；`episode_name` 可留空（取首个事件名）。",
        "- `decision` 只能是 `MERGE` 或 `KEEP_SEPARATE`。",
        "- 改完重跑：`python3 -u scripts/graph_export_import.py --model <模型> --write`。", "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="cuc/qwen")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    model_dir = safe_model_name(args.model)
    folders = approved_folders(model_dir)
    print(f"{'[落盘]' if args.write else '[预览]'} 模型线 {args.model}｜已验收文档 {len(folders)} 份")
    if not folders:
        print("  没有已通过校验的文档；请先完成单文档端到端验证。")
        return 1

    merged: dict[str, tuple[list[str], dict[tuple[str, ...], dict[str, str]]]] = {}
    warnings: list[str] = []
    for table in BASE_TABLES:
        fields: list[str] | None = None
        rows: dict[tuple[str, ...], dict[str, str]] = {}
        for folder in folders:
            current_fields, current_rows = read_csv(folder / f"{table}.csv")
            if fields is None:
                fields = current_fields
            elif fields != current_fields:
                warnings.append(f"{table}: {folder.name} 表头不一致，已跳过该份")
                continue
            for row in current_rows:
                key = tuple(row.get(col, "") for col in UNIQUE_KEYS[table])
                previous = rows.get(key)
                if previous is not None and previous != row:
                    if table == "entities":
                        stable = ("canonical_name", "entity_type", "entity_subtype")
                        if any(previous.get(c) != row.get(c) for c in stable):
                            warnings.append(f"共享实体冲突 {key}，保留首次")
                        if row.get("review_status") == "NEEDS_REVIEW":
                            previous["review_status"] = "NEEDS_REVIEW"
                        continue
                    warnings.append(f"{table}: 重复主键 {key}，保留首次")
                    continue
                rows[key] = row
        merged[table] = (fields or [], rows)

    # ---- L3 人物生平 ----
    doc_person: dict[str, str] = {}
    for row in merged["documents"][1].values():
        doc_person[row["doc_id"]] = PERSON_ENTITY.get(row.get("interviewee", ""), "")
    times = {row["event_id"]: row for row in merged["event_times"][1].values()}

    scopes: dict[str, str] = {}
    for result_path in sorted((STAGE_ROOT / "validated_json" / model_dir).glob("*.json")):
        data = json.loads(result_path.read_text(encoding="utf-8"))
        for event in data["consolidated_output"]["document_events"]:
            scopes[event["document_event_id"]] = event["experience_scope"]
        view_path = STAGE_ROOT / "human_adjudicated" / model_dir / result_path.name
        if view_path.exists():
            view = json.loads(view_path.read_text(encoding="utf-8"))
            for event in view["consolidated_output"]["document_events"]:
                scopes[event["document_event_id"]] = event["experience_scope"]

    by_person_episodes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_person_context: dict[str, list[str]] = defaultdict(list)
    by_person_docs: dict[str, list[str]] = defaultdict(list)
    doc_of_event = {row["event_id"]: row["doc_id"] for row in merged["event_nodes"][1].values()}

    for doc_id, person_id in doc_person.items():
        if not person_id:
            warnings.append(f"{doc_id} 的受访者未映射到人物实体，跳过生平")
            continue
        by_person_docs[person_id].append(doc_id)

    for event in merged["event_nodes"][1].values():
        doc_id = event["doc_id"]
        person_id = doc_person.get(doc_id, "")
        if not person_id:
            continue
        scope = scopes.get(event["event_id"], "UNCERTAIN")
        if scope == "NARRATED_CONTEXT":
            by_person_context[person_id].append(event["event_id"])
            continue
        if scope != "PERSONAL_EXPERIENCE":
            warnings.append(f"{event['event_id']} scope={scope}，生平链暂不收录（待人工裁决）")
            continue
        time_row = times.get(event["event_id"], {})
        by_person_episodes[person_id].append({
            "event_id": event["event_id"],
            "doc_id": doc_id,
            "person_entity_id": person_id,
            "episode_name": event["event_name"],
            "normalized_start": time_row.get("normalized_start", ""),
            "normalized_end": time_row.get("normalized_end", ""),
            "precision": time_row.get("precision", "UNKNOWN"),
            "certainty": time_row.get("certainty", "UNCERTAIN"),
            "confidence": time_row.get("confidence", "LOW"),
            "review_status": "MODEL_CANDIDATE",
        })

    name_by_id = {v: k for k, v in PERSON_ENTITY.items()}
    generated, suspect_groups, bio_stats = build_biography_layer(
        by_person_episodes, by_person_docs, by_person_context, name_by_id, model_dir,
    )
    print(
        f"  生平叠加视图：疑似同一经历 {bio_stats['suspect_groups']} 组（只标 NEEDS_REVIEW，交人工）；"
        f"人工 MERGE 生效 {bio_stats['human_merged_episodes']} 组，"
        f"KEEP_SEPARATE {bio_stats['human_keep_separate']} 组"
    )

    summary = {table: len(rows) for table, (_, rows) in merged.items()}
    summary.update({name: len(rows) for name, rows in generated.items()})
    print("\n== 24 张 import CSV 规模 ==")
    for name, count in summary.items():
        print(f"  {name:<24} {count:>6} 行")
    if warnings:
        print(f"\n  警告 {len(warnings)} 条（详见报告）")

    if args.write:
        out = EXPORT_ROOT / f"import_{model_dir}"
        out.mkdir(parents=True, exist_ok=True)
        for table, (fields, rows) in merged.items():
            write_csv(out / f"{table}.csv", fields, list(rows.values()))
        for name, rows in generated.items():
            write_csv(out / f"{name}.csv", GENERATED_FIELDS[name], rows)
        cypher = IMPORT_CYPHER.read_text(encoding="utf-8")
        cypher = cypher.replace("oral-history-workflow-demo-v2", f"oral-history-batch-{model_dir}-v1")
        cypher = cypher.replace("'2026-11-04'", f"'{datetime.now():%Y-%m-%d}'")
        cypher = cypher.replace("3.2+biography-view", "3.2+batch-application-ext")
        cypher = cypher.replace("六份访谈：原文—事件—阶段—实体—时间表达，并叠加按人物真实时间排列的生平经历视图",
                                f"正式语料 {len(folders)} 份（{args.model}）：原文—事件—阶段—实体—时间—生平，data_role=BATCH_APPLICATION")
        # 复制 Demo 模板时残留的标题与图谱名；只改文案，不涉及 T3 的「每行版本字段」决策。
        cypher = cypher.replace("// 口述史六份工作流Demo：可重复执行的 Neo4j 导入脚本。",
                                f"// 正式语料 {args.model} 图谱：可重复执行的 Neo4j 导入脚本。")
        cypher = cypher.replace("g.name = '口述史六份工作流Demo图谱'",
                                f"g.name = '正式语料{args.model}图谱'")
        # T3=不改：版本声明写在脚本注释里，不给任何 CSV 加列。
        cypher += (
            f"\n// 词表 {VOCABULARY_VERSION}：{VOCABULARY_NOTE}\n"
            "// 生平层为叠加视图：语料层不合并；疑似同一经历标 NEEDS_REVIEW 交人工；\n"
            "// 人工 MERGE 后，一条 LifeEpisode 可由多个来源 EventNode 共同支持。\n"
        )
        (out / "import.cypher").write_text(cypher, encoding="utf-8")
        review_path = write_suspect_review(model_dir, suspect_groups)
        if review_path:
            print(f"  疑似清单：{display_path(review_path)}")
        report = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "layer": "L3_L4_EXPORT", "model_id": args.model,
            "documents": len(folders),
            "document_ids": [f.name for f in folders],
            "tables": summary, "warnings": warnings, "api_calls": 0,
            "vocabulary_version": VOCABULARY_VERSION,
            "vocabulary_note": VOCABULARY_NOTE + "版本只在契约／导入脚本／本报告中全局声明，不写入任何 CSV 列（T3=不改）。",
            "biography_view": "叠加视图：语料层不合并；疑似同一经历标 NEEDS_REVIEW 交人工；人工 MERGE 后一条 LifeEpisode 挂多个来源事件。",
            "biography_suspect_groups": bio_stats["suspect_groups"],
            "biography_human_merges": bio_stats["human_merged_episodes"],
            "biography_human_keep_separate": bio_stats["human_keep_separate"],
            "note": "不覆盖六份 Demo 库；导入前请核对 import.cypher 指向本目录的 file:/// 路径。",
        }
        (out / "prepare_summary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\n  已写入：{display_path(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
