#!/usr/bin/env python3
"""把 6 份人工 Demo 与 54 份正式语料合并成一套 60 份的 Neo4j 导入包。

只读既有两套导入包，产出到 05_合并与Neo4j/import_all60/：
  - 18 张基础表：正式 24 表中的 18 张 + 六份 Demo 对应表，按唯一键去重（正式优先）
  - 6 张生成表：正式既有 6 张 + 为 Demo 用同一 build_biography_layer 生成的 6 张
    （Demo 生平 episode_id 加 DEMO- 前缀，避免与正式 CHF-Lxxx 相撞）
  - import.cypher：以 import_cuc_deepseek/import.cypher 为底，文件名加 all60_ 前缀

零 API、零改动既有结果。用法：
    python3 scripts/build_all60_import.py            # 只生成
    python3 scripts/build_all60_import.py --deploy   # 同时拷贝到 /tmp/graph_deepseek/import/
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import graph_export_import as gei  # noqa: E402  复用冻结的合并规则与生平层生成逻辑

PROJECT_DIR = Path(__file__).resolve().parents[1]
NEO4J_DIR = PROJECT_DIR / "05_合并与Neo4j"
FORMAL = NEO4J_DIR / "import_cuc_deepseek"
DEMO_ROOT = PROJECT_DIR.parent / "现行标注"
OUT = NEO4J_DIR / "import_all60"
INSTANCE_IMPORT = Path("/tmp/graph_deepseek/import")
DEMO_DIRS = sorted(d for d in DEMO_ROOT.iterdir()
                   if d.is_dir() and d.name[:2] in ("01", "02", "03", "04", "05", "06"))


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    if len(DEMO_DIRS) != 6:
        raise SystemExit(f"预期 6 份人工 Demo，实际 {len(DEMO_DIRS)} 份：{[d.name for d in DEMO_DIRS]}")
    OUT.mkdir(parents=True, exist_ok=True)

    # ---------- 1. 18 张基础表：正式优先，Demo 追加，按冻结的 UNIQUE_KEYS 去重 ----------
    merged: dict[str, tuple[list[str], list[dict]]] = {}
    stats: dict[str, tuple[int, int]] = {}
    for table in gei.BASE_TABLES:
        fields, formal_rows = read_csv(FORMAL / f"{table}.csv")
        keys = gei.UNIQUE_KEYS[table]
        index: dict[tuple, dict] = {}
        for row in formal_rows:
            index[tuple(row.get(k, "") for k in keys)] = row
        n_formal = len(index)
        if n_formal != len(formal_rows):
            raise SystemExit(f"{table}: 正式表本身有重复主键，停止以免悄悄丢数据")
        added = 0
        for d in DEMO_DIRS:
            demo_fields, demo_rows = read_csv(d / f"{table}.csv")
            if demo_fields != fields:
                raise SystemExit(f"{table}: {d.name} 表头与正式表不一致，停止")
            for row in demo_rows:
                k = tuple(row.get(c, "") for c in keys)
                if k not in index:
                    index[k] = row
                    added += 1
        merged[table] = (fields, list(index.values()))
        stats[table] = (n_formal, added)

    # ---------- 2. 为 6 份 Demo 用同一函数生成生平层 ----------
    doc_person: dict[str, str] = {}
    by_person_episodes: dict[str, list[dict]] = defaultdict(list)
    by_person_context: dict[str, list[str]] = defaultdict(list)
    by_person_docs: dict[str, list[str]] = defaultdict(list)

    for d in DEMO_DIRS:
        _, docs = read_csv(d / "documents.csv")
        for doc in docs:
            pid = gei.PERSON_ENTITY.get(doc["interviewee"], "")
            if not pid:
                raise SystemExit(f"{d.name}: 未识别受访者 {doc['interviewee']}")
            doc_person[doc["doc_id"]] = pid
            by_person_docs[pid].append(doc["doc_id"])

    times: dict[str, dict] = {}
    for d in DEMO_DIRS:
        _, rows = read_csv(d / "event_times.csv")
        for r in rows:
            times[r["event_id"]] = r

    for d in DEMO_DIRS:
        _, events = read_csv(d / "event_nodes.csv")
        for ev in events:
            pid = doc_person.get(ev["doc_id"], "")
            t = times.get(ev["event_id"], {})
            by_person_episodes[pid].append({
                "event_id": ev["event_id"],
                "doc_id": ev["doc_id"],
                "person_entity_id": pid,
                "episode_name": ev["event_name"],
                "normalized_start": t.get("normalized_start", ""),
                "normalized_end": t.get("normalized_end", ""),
                "precision": t.get("precision", "UNKNOWN"),
                "certainty": t.get("certainty", "UNCERTAIN"),
                "confidence": t.get("confidence", "MEDIUM"),
                "review_status": "CONFIRMED",
            })

    name_by_id = {v: k for k, v in gei.PERSON_ENTITY.items()}
    generated, _, bio_stats = gei.build_biography_layer(
        by_person_episodes, by_person_docs, by_person_context,
        name_by_id, "human_demo6", decisions_path=None,
    )

    # Demo 生平 ID 加前缀，避免与正式 CHF-L001… 相撞；人工 Demo 状态标 CONFIRMED / WORKFLOW_DEMO
    demo_generated: dict[str, list[dict]] = {k: [] for k in gei.GENERATED_FIELDS}
    for row in generated["document_persons"]:
        demo_generated["document_persons"].append({**row, "review_status": "CONFIRMED"})
    for row in generated["life_episodes"]:
        demo_generated["life_episodes"].append({
            **row,
            "episode_id": "DEMO-" + row["episode_id"],
            "review_status": "CONFIRMED",
        })
    for row in generated["life_episode_sources"]:
        demo_generated["life_episode_sources"].append({
            **row,
            "episode_id": "DEMO-" + row["episode_id"],
            "review_status": "CONFIRMED",
        })
    for row in generated["life_episode_next"]:
        demo_generated["life_episode_next"].append({
            **row,
            "source_episode_id": "DEMO-" + row["source_episode_id"],
            "target_episode_id": "DEMO-" + row["target_episode_id"],
            "basis": "HUMAN_DEMO_TIME_SORT",
            "review_status": "CONFIRMED",
        })
    # person_subjects 三条与正式完全相同（同一受访者共享节点），不重复写；narrated_contexts Demo 无 scope 信息，留空
    demo_generated["person_subjects"] = []
    demo_generated["narrated_contexts"] = []

    # ---------- 3. 合并 6 张生成表并落盘 24 CSV ----------
    for name, fields in gei.GENERATED_FIELDS.items():
        _, formal_rows = read_csv(FORMAL / f"{name}.csv")
        if name == "person_subjects":
            # 三位受访者是 6 份人工 Demo 与 54 份正式语料共享的节点，标成单一来源会误导。
            formal_rows = [{**r,
                            "biography_status": "MIXED_HUMAN_DEMO_AND_BATCH",
                            "review_status": "MIXED"} for r in formal_rows]
        rows = formal_rows + demo_generated[name]
        write_csv(OUT / f"{name}.csv", fields, rows)
        stats[name] = (len(formal_rows), len(demo_generated[name]))
    for table, (fields, rows) in merged.items():
        write_csv(OUT / f"{table}.csv", fields, rows)

    # ---------- 4. 生成 Cypher（全量重建，只作用本实例） ----------
    cypher = (FORMAL / "import.cypher").read_text(encoding="utf-8")
    cypher = cypher.replace("file:///", "file:///all60_")
    cypher = cypher.replace("oral-history-batch-cuc_deepseek-v1", "oral-history-all60-v1")
    cypher = cypher.replace("g.name = '正式语料cuc/deepseek图谱'",
                            "g.name = '口述史 60 份完整图谱（6 人工 Demo + 54 正式）'")
    cypher = cypher.replace(
        "g.description = '正式语料 54 份（cuc/deepseek）：原文—事件—阶段—实体—时间—生平，data_role=BATCH_APPLICATION'",
        "g.description = '60 份 = 6 人工 Demo（WORKFLOW_DEMO/CONFIRMED，词表 v1.0）+ 54 正式（BATCH_APPLICATION/MODEL_CANDIDATE，词表 v1.1）；以 documents.data_role 区分，统计勿混读'")
    cypher = cypher.replace("// 正式语料 cuc/deepseek 图谱：可重复执行的 Neo4j 导入脚本。",
                            "// 60 份完整图谱：可重复执行的 Neo4j 导入脚本（全量重建本实例）。")
    cypher += (
        "\n// 60 份合库说明：6 份人工 Demo 与 54 份正式语料 18 张表逐列一致、主键无冲突；\n"
        "// Demo 生平 episode_id 以 DEMO- 开头，与正式 CHF-Lxxx 分开；\n"
        "// 三类受访者共用 PER-CHF / PER-CRT / PER-YYS 实体节点（Demo 表提供了该实体，\n"
        "// 因而 person_subjects / document_persons / HAS_LIFE_EPISODE 关系同时补齐）。\n"
        "// 口径：人工 6 份是 WORKFLOW_DEMO 金标准，54 份仍 MODEL_CANDIDATE，两者统计不可相加。\n"
    )
    (OUT / "import.cypher").write_text(cypher, encoding="utf-8")

    # ---------- 5. 可选：部署到实例 import 目录（加前缀，不覆盖原 24 CSV） ----------
    if "--deploy" in sys.argv:
        if not INSTANCE_IMPORT.is_dir():
            raise SystemExit(f"实例 import 目录不存在：{INSTANCE_IMPORT}")
        for p in sorted(OUT.iterdir()):
            if p.suffix == ".csv":
                (INSTANCE_IMPORT / f"all60_{p.name}").write_bytes(p.read_bytes())
        (INSTANCE_IMPORT / "all60_import.cypher").write_text(cypher, encoding="utf-8")
        print(f"已部署 {len(list(OUT.glob('*.csv')))} 张 CSV + Cypher → {INSTANCE_IMPORT}")

    print(f"生成目录：{OUT}")
    print(f"人工 Demo：{[d.name for d in DEMO_DIRS]}")
    print("\n== 24 表规模（正式 / +Demo） ==")
    for name in list(gei.BASE_TABLES) + list(gei.GENERATED_FIELDS):
        a, b = stats[name]
        print(f"  {name:<24} {a:>6} / +{b:<5} = {a + b}")
    print(f"\n生平疑似同一经历（Demo）：{bio_stats['suspect_groups']} 组，人工 Demo 一律 CONFIRMED，不生成待裁决清单")
    print(f"import.cypher 语句数：{sum(1 for s in cypher.split(';') if s.strip())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
