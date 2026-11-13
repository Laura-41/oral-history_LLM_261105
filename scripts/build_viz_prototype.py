#!/usr/bin/env python3
"""从 6 份人工标注 Demo 生成「科研工作台」资产与研究侧指标。

用法：
    python3 scripts/build_viz_prototype.py

输入：../现行标注/01_* ~ 06_* 的 18 张 CSV（只读，绝不改动）
输出：06_可视化原型/叙事跳跃度指标_6份Demo.csv （研究侧指标，不进入用户端界面）

2026-11-13 起：科研工作台**不再生成独立 HTML**，而是由
`build_user_portal.py` 调用本模块的 `bench_assets()` 把 CSS / 结构 /
脚本 / 数据整体内嵌进 `06_可视化原型/归途·口述史记忆馆.html` 的 Shadow DOM。
本脚本单独运行时只刷新研究侧指标 CSV；请勿再手工产出
「口述史图谱_科研版.html」，该文件已按研究者要求废弃。

设计口径（2026-11-12 研究者拍板）：
  - 原型只接 6 份人工 Demo，词表 v1.0，不接大模型线、不展示双模型对照
  - 单人主轴默认历史序，叙述序做可切换对照
  - 交叉入口与自然语言问句共用同一查询层
  - 用户端不出现任何叙事跳跃度分数；指标只落研究侧 CSV 与独立的「研究视图」
"""

from __future__ import annotations

import csv
import glob
import itertools
import json
import os
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT.parent / "现行标注"
OUT_DIR = ROOT / "06_可视化原型"
TEMPLATE = Path(__file__).with_name("viz_prototype_template.html")
OUT_METRICS = OUT_DIR / "叙事跳跃度指标_6份Demo.csv"

# 输出 JSON 键 -> 源 CSV 文件名
TABLES = {
    "docs": "documents.csv",
    "events": "event_nodes.csv",
    "times": "event_times.csv",
    "processes": "event_processes.csv",
    "stages": "process_stages.csv",
    "stageNext": "stage_next.csv",
    "eventNext": "event_next.csv",
    "circumstances": "event_circumstances.csv",
    "participants": "event_participants.csv",
    "entities": "entities.csv",
    "aliases": "entity_aliases.csv",
    "mentions": "entity_mentions.csv",
    "relations": "entity_relations.csv",
    "segments": "source_segments.csv",
    "attachments": "source_attachments.csv",
    "timeExpressions": "time_expressions.csv",
    "annotations": "document_annotations.csv",
    "coverage": "coverage_audit.csv",
}


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def load_demos() -> tuple[list[str], dict[str, list[dict]]]:
    demos = [
        d for d in sorted(glob.glob(str(DEMO_DIR / "[0-9][0-9]_*")))
        if os.path.isdir(d) and not os.path.basename(d).startswith("00_")
    ]
    if len(demos) != 6:
        raise SystemExit(f"预期 6 份人工 Demo，实际找到 {len(demos)} 份：{demos}")
    data: dict[str, list[dict]] = {key: [] for key in TABLES}
    for demo in demos:
        for key, filename in TABLES.items():
            path = Path(demo) / filename
            if not path.exists():
                raise SystemExit(f"缺表：{path}")
            data[key].extend(read_csv(path))
    return [os.path.basename(d) for d in demos], data


def jump_metrics(sequence: list[int]) -> dict:
    """按叙述序排列的历史序序列 -> 研究侧指标。"""
    n = len(sequence)
    inversions = sum(1 for a, b in itertools.combinations(sequence, 2) if a > b)
    maximum = n * (n - 1) // 2
    tau = 1 - 4 * inversions / (n * (n - 1)) if n > 1 else 1.0
    backjumps = [
        {"at_narrative": i + 1, "span": sequence[i - 1] - sequence[i]}
        for i in range(1, n) if sequence[i] < sequence[i - 1]
    ]
    return {
        "n": n,
        "inversions": inversions,
        "max_inversions": maximum,
        "normalized": round(inversions / maximum, 4) if maximum else 0.0,
        "kendall_tau": round(tau, 4),
        "max_backjump": max((b["span"] for b in backjumps), default=0),
        "backjump_count": len(backjumps),
    }


def build_research_metrics(data: dict) -> list[dict]:
    """研究侧指标：不注入用户端界面，只写 CSV 与独立研究视图。"""
    by_doc: dict[str, list[dict]] = {}
    for e in data["events"]:
        by_doc.setdefault(e["doc_id"], []).append(e)
    doc_title = {d["doc_id"]: d["title"] for d in data["docs"]}
    rows = []
    for doc_id, events in by_doc.items():
        pairs = sorted(
            ((int(e["narrative_order"]), int(e["historical_order"]), e["event_name"]) for e in events),
            key=lambda x: x[0],
        )
        seq = [p[1] for p in pairs]
        m = jump_metrics(seq)
        rows.append({
            "doc_id": doc_id,
            "title": doc_title.get(doc_id, ""),
            "event_count": m["n"],
            "historical_order_sequence": "|".join(str(x) for x in seq),
            "inversions": m["inversions"],
            "max_inversions": m["max_inversions"],
            "normalized_jump": m["normalized"],
            "kendall_tau": m["kendall_tau"],
            "max_backjump_span": m["max_backjump"],
            "backjump_count": m["backjump_count"],
            "backjump_events": "；".join(
                p[2] for p in pairs if p[1] < p[0]
            ) or "（无）",
            "note": "人工标注双序；τ = 1 − 4·逆序对/(n(n−1))；仅研究侧使用",
        })
    return sorted(rows, key=lambda r: r["doc_id"])


def bench_payload(data: dict) -> dict:
    """科研工作台的内嵌数据；与门户共用同一批 6 份 Demo，不另读一次。"""
    demo_names = sorted(
        os.path.basename(d) for d in glob.glob(str(DEMO_DIR / "[0-9][0-9]_*"))
        if os.path.isdir(d) and not os.path.basename(d).startswith("00_")
    )
    return {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "scope": "6 份人工标注 Demo（词表 v1.0）",
            "demo_folders": demo_names,
            "note": "不含大模型线数据；不含双模型对照；结果仅供交互原型演示",
        },
        "researchMetrics": build_research_metrics(data),
        **data,
    }


def bench_assets(data: dict) -> dict:
    """把科研工作台模板拆成可嵌入 Shadow DOM 的四份资产。

    css / markup 会一起克隆进 shadow root；app 与 db_json 进内联脚本。
    门户与工作台各自有 `DB`、`$`、`switchView`、`.view`、`#themeBtn`，
    因此必须用 Shadow DOM + 作用域 document 垫片隔离，不能直接拼 HTML。
    """
    tpl = TEMPLATE.read_text(encoding="utf-8")
    css = re.search(r"<style>(.*?)</style>", tpl, re.S).group(1)
    body = re.search(r"<body>(.*?)</body>", tpl, re.S).group(1)
    markup = body.split("<script>")[0].strip()
    scripts = re.findall(r"<script>(.*?)</script>", tpl, re.S)
    if len(scripts) < 2:
        raise SystemExit("科研工作台模板应含两个 <script> 块")
    app = scripts[-1].replace(
        "try{if(localStorage.getItem('ohg-theme')==='night')$('#themeBtn').click();}catch(e){}",
        "",
    )
    # Shadow DOM 里没有 :root / body，变量与夜读态改挂到宿主元素上
    css = (css.replace("body.night{", ":host(.night){")
              .replace("body.night ", ":host(.night) ")
              .replace("html,body{", ":host{")
              .replace("body{", ":host{")
              .replace(":root{", ":host{"))
    css += """
/* 内嵌适配：固定画框，不撑破门户页面；窄屏时自适应高度 */
:host{display:block;height:780px;overflow:hidden;background:var(--paper);color:var(--ink)}
main{height:calc(100% - 92px)}
@media(max-width:900px){:host{height:auto;overflow:visible}main{height:auto;overflow:visible}}
"""
    raw = json.dumps(bench_payload(data), ensure_ascii=False, separators=(",", ":"))
    raw = raw.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return {
        "css": css,
        "markup": markup.replace("</script", "<\\/script"),
        "app": app.replace("</script", "<\\/script"),
        "db_json": raw,
    }


def main() -> None:
    if not DEMO_DIR.is_dir():
        raise SystemExit(f"找不到人工标注目录：{DEMO_DIR}")
    if not TEMPLATE.exists():
        raise SystemExit(f"找不到页面模板：{TEMPLATE}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    _, data = load_demos()
    metrics = build_research_metrics(data)
    with OUT_METRICS.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(metrics[0].keys()))
        writer.writeheader()
        writer.writerows(metrics)

    counts = " / ".join(f"{k} {len(v)}" for k, v in data.items() if k in
                        ("docs", "events", "stages", "segments", "attachments", "entities", "mentions"))
    print(f"已生成 {OUT_METRICS}  ({len(metrics)} 行，研究侧专用)")
    print(f"数据规模：{counts}")
    print("科研工作台 HTML 已内嵌进 归途·口述史记忆馆.html；刷新请跑 python3 scripts/build_user_portal.py")
    print("说明：用户端界面不含任何跳跃度分数；指标仅在独立「研究视图」与 CSV 中。")


if __name__ == "__main__":
    main()
