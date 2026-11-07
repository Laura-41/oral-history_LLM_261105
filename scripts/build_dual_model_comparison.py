#!/usr/bin/env python3
"""BATCH02 双模型同题对照（只读分析，不调用 API、不改任何结果与冻结资产）。

前提：两条线使用同一批文档、同一套 dialogue_segments（片段 ID 与逐字文本一致），
      但窗口候选由各模型独立抽取，故事件边界可能不同；本脚本按原文片段重叠做
      「近似同题配对」，不是严格事件对齐，配对结果仅供人工复核定位。

用法：python3 scripts/build_dual_model_comparison.py [--batch BATCH02]
输出：04_54份正式语料批处理/document_consolidation/review/
      <batch>_双模型同题对照_20261107.md
"""

from __future__ import annotations

import argparse
import collections
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "04_54份正式语料批处理" / "document_consolidation"
BATCH_ROOT = ROOT / "04_54份正式语料批处理"
MODELS = (("cuc_deepseek", "DeepSeek"), ("cuc_qwen", "Qwen"))
PAIR_THRESHOLD = 0.6


def short(text: str, limit: int = 150) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "…"


def overlap(a: list[str], b: list[str]) -> tuple[float, int]:
    A, B = set(a), set(b)
    if not A or not B:
        return 0.0, 0
    inter = A & B
    return len(inter) / min(len(A), len(B)), len(inter)


def load(mdir: str, doc: str):
    r = json.loads(
        (BASE / "validated_json" / mdir / f"{doc}.json").read_text(encoding="utf-8")
    )
    p = json.loads((BASE / "inputs" / mdir / f"{doc}.json").read_text(encoding="utf-8"))
    return r["consolidated_output"]["document_events"], {
        s["segment_id"]: s.get("verbatim_text", "") for s in p["dialogue_segments"]
    }, len(p["window_candidates"]), p.get("source_model_id")


def main() -> int:
    ap = argparse.ArgumentParser(description="生成双模型同题对照报告")
    ap.add_argument("--batch", default="BATCH02")
    args = ap.parse_args()

    docs = sorted(
        p.stem for p in (BASE / "validated_json" / "cuc_deepseek").glob(
            f"{args.batch}-DOC*.json"
        )
    )
    lines: list[str] = []
    lines.append(f"# {args.batch} 双模型同题对照（只读，2026-11-07）")
    lines.append("")
    lines.append(
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}　"
        "生成脚本：`scripts/build_dual_model_comparison.py`"
    )
    lines.append(
        "> 性质：**助手只读整理，不含任何人工标注结论**；两条线全部结果仍为 `MODEL_CANDIDATE`，未入库、未放行。"
    )
    lines.append("")
    lines.append("## 一、口径与边界")
    lines.append("")
    lines.append("- 数据：`document_consolidation/validated_json/{cuc_deepseek,cuc_qwen}/`，各 9 份文档级归并结果；")
    lines.append("  输入为 `document_consolidation/inputs/<模型目录>/`，已核对同一文档的 `dialogue_segments` 片段 ID 与逐字文本**完全一致**。")
    lines.append("- 但两条线的 `window_candidates` 由各模型**独立抽取**（候选数不同），因此事件边界与归并粒度天然不同；")
    lines.append(f"  本报告的「同题配对」按 `source_segment_ids` 重叠系数 ≥ {PAIR_THRESHOLD} 贪心匹配，**是定位工具，不是严格同题对齐**。")
    lines.append("- 冻结规则未改动；两模型使用同一套提示词／契约／Schema／校验器（单份文档内不混用模型）。")
    lines.append("")
    lines.append("### 本表要你裁决什么（2026-11-07 补充说明）")
    lines.append("")
    lines.append("**只裁 `experience_scope`（个人经历／讲述背景／不确定），不裁事件边界。**")
    lines.append("两条线各自独立抽取窗口候选并归并，事件切分本来就不一样；本表按原文片段重叠把")
    lines.append("「大体指向同一段话」的两个事件配成一对。当它们给出不同 `experience_scope` 时，")
    lines.append("请你判断**这段叙述里受访者到底算不算亲历**：写 **1** 维持 `PERSONAL_EXPERIENCE`、")
    lines.append("**2** 改 `NARRATED_CONTEXT`、**3** 改 `UNCERTAIN`、**4** 暂缓（补上下文）——")
    lines.append("编码与 `BATCH02_cuc_deepseek_COLLECTIVE_WITH_ROLE_逐条复核清单_20261107.md` 一致。")
    lines.append("")
    lines.append("⚠️ 但分歧对里有两类，别混着裁：")
    lines.append("")
    lines.append("- **A 类｜同一证据、范围判定不同**：两边 `scope_evidence_quote` 指向同一句话，这才是本表真正要裁的；")
    lines.append("- **B 类｜两边引的是不同内容**：往往不只范围不同，连「是不是同一个事件」都不同（事件名、参与者、")
    lines.append("  片段边界都变了）。这类**请先判断是不是同一事件**；若不是，不要在这里二选一，另案按事件边界处理。")
    lines.append("")
    lines.append("**「给出的原文」不是全部。** 上一版只放了 `scope_evidence_quote`（范围证据引文，且截到 220 字）；")
    lines.append("本版已为每对补齐**两个事件 `source_segment_ids` 并集的全部逐字片段**（按片段 ID 列出、不截断）。")
    lines.append("这仍不是整篇文档；完整语料在 `document_consolidation/inputs/<模型目录>/BATCH02-DOC0X.json`")
    lines.append("的 `dialogue_segments`，两模型该字段逐字一致。")
    lines.append("")

    per_doc: list[dict] = []
    all_bases: dict[str, collections.Counter] = {m: collections.Counter() for m, _ in MODELS}
    all_scope: dict[str, collections.Counter] = {m: collections.Counter() for m, _ in MODELS}
    cwr_total: dict[str, int] = {m: 0 for m, _ in MODELS}
    evidence_ok: dict[str, int] = {m: 0 for m, _ in MODELS}
    evidence_bad: dict[str, list[str]] = {m: [] for m, _ in MODELS}
    pairs_all: list[dict] = []
    segment_consistent: list[str] = []

    for doc in docs:
        entry = {"doc": doc}
        loaded = {}
        for mdir, label in MODELS:
            events, seg, ncand, smid = load(mdir, doc)
            loaded[mdir] = (events, seg)
            scope = collections.Counter(e["experience_scope"] for e in events)
            bases = collections.Counter(b for e in events for b in e["participation_bases"])
            nr = sum(1 for e in events if e["review_status"] == "NEEDS_REVIEW")
            cwr = sum(
                1 for e in events
                if e["experience_scope"] == "PERSONAL_EXPERIENCE"
                and "COLLECTIVE_WITH_ROLE" in e["participation_bases"]
            )
            for e in events:
                q = e["scope_evidence_quote"]
                if any(q in seg.get(sid, "") for sid in e["scope_evidence_segment_ids"]):
                    evidence_ok[mdir] += 1
                else:
                    evidence_bad[mdir].append(e["document_event_id"])
            entry[mdir] = {
                "events": events, "seg": seg, "ncand": ncand, "scope": scope,
                "bases": bases, "nr": nr, "cwr": cwr, "source_model_id": smid,
            }
            all_bases[mdir].update(bases)
            all_scope[mdir].update(scope)
            cwr_total[mdir] += cwr

        # 输入片段一致性
        sa, sq = loaded["cuc_deepseek"][1], loaded["cuc_qwen"][1]
        segment_consistent.append(f"{doc}:{'一致' if sa == sq else '不一致'}")

        # 贪心配对
        ds = loaded["cuc_deepseek"][0]
        qw = loaded["cuc_qwen"][0]
        cand = []
        for di, d in enumerate(ds):
            for qi, q in enumerate(qw):
                s, inter = overlap(d["source_segment_ids"], q["source_segment_ids"])
                if s >= PAIR_THRESHOLD and inter >= 1:
                    cand.append((s, inter, di, qi))
        cand.sort(key=lambda x: (-x[0], -x[1], x[2], x[3]))
        used_d, used_q, matched = set(), set(), []
        for s, inter, di, qi in cand:
            if di in used_d or qi in used_q:
                continue
            used_d.add(di)
            used_q.add(qi)
            matched.append((s, inter, di, qi))
        entry["pairs"] = matched
        entry["unpaired_ds"] = [i for i in range(len(ds)) if i not in used_d]
        entry["unpaired_qw"] = [i for i in range(len(qw)) if i not in used_q]
        for s, inter, di, qi in matched:
            d, q = ds[di], qw[qi]
            pairs_all.append({
                "doc": doc, "score": s, "inter": inter,
                "ds": d, "qw": q,
                "same_scope": d["experience_scope"] == q["experience_scope"],
            })
        per_doc.append(entry)

    seg_by_doc = {e["doc"]: e["cuc_deepseek"]["seg"] for e in per_doc}

    # 二、技术层面对照
    lines.append("## 二、技术层面对照")
    lines.append("")
    lines.append("| 文档 | DS 候选 | QW 候选 | DS 事件 | QW 事件 | DS 个人/背景/不确定 | QW 个人/背景/不确定 | DS 待复核 | QW 待复核 |")
    lines.append("|---|---:|---:|---:|---:|---|---|---:|---:|")
    tot = collections.Counter()
    for e in per_doc:
        d, q = e["cuc_deepseek"], e["cuc_qwen"]
        dsc = d["scope"]
        qsc = q["scope"]
        lines.append(
            f"| `{e['doc']}` | {d['ncand']} | {q['ncand']} | {len(d['events'])} | {len(q['events'])} "
            f"| {dsc['PERSONAL_EXPERIENCE']}/{dsc['NARRATED_CONTEXT']}/{dsc['UNCERTAIN']} "
            f"| {qsc['PERSONAL_EXPERIENCE']}/{qsc['NARRATED_CONTEXT']}/{qsc['UNCERTAIN']} "
            f"| {d['nr']} | {q['nr']} |"
        )
        for key, val in (
            ("ds_events", len(d["events"])), ("qw_events", len(q["events"])),
            ("ds_nr", d["nr"]), ("qw_nr", q["nr"]),
        ):
            tot[key] += val
        for mdir, label in MODELS:
            for k, v in e[mdir]["scope"].items():
                tot[f"{label}_{k}"] += v
    lines.append("")
    lines.append(
        f"**全批**：DeepSeek {tot['ds_events']} 事件（个人 {tot['DeepSeek_PERSONAL_EXPERIENCE']}／"
        f"背景 {tot['DeepSeek_NARRATED_CONTEXT']}／不确定 {tot['DeepSeek_UNCERTAIN']}），"
        f"`NEEDS_REVIEW` {tot['ds_nr']}；"
        f"Qwen {tot['qw_events']} 事件（个人 {tot['Qwen_PERSONAL_EXPERIENCE']}／"
        f"背景 {tot['Qwen_NARRATED_CONTEXT']}／不确定 {tot['Qwen_UNCERTAIN']}），"
        f"`NEEDS_REVIEW` {tot['qw_nr']}。"
    )
    lines.append("")
    lines.append(
        "成本与时长（取自 `batch02_summary_*.md`）：DeepSeek ¥3.9511、14:17:48 完成；"
        "Qwen ¥20.2906、16:23:44 完成。Qwen 约为 DeepSeek 的 5.1 倍费用、慢约 2 小时，"
        "且 `NEEDS_REVIEW` 明显更多（模型自述分歧更多，不等于质量更差）。"
    )
    lines.append("")
    lines.append("输入片段一致性：" + ", ".join(segment_consistent))
    lines.append("")

    # 三、依据分布
    lines.append("## 三、`participation_bases` 分布对照")
    lines.append("")
    keys = sorted(set(all_bases["cuc_deepseek"]) | set(all_bases["cuc_qwen"]))
    lines.append("| 依据 | DeepSeek | Qwen |")
    lines.append("|---|---:|---:|")
    for k in keys:
        lines.append(f"| `{k}` | {all_bases['cuc_deepseek'][k]} | {all_bases['cuc_qwen'][k]} |")
    lines.append("")

    # 四、上一轮焦点
    lines.append("## 四、上一轮焦点：`COLLECTIVE_WITH_ROLE` 的双线视角")
    lines.append("")
    lines.append(
        f"`PERSONAL_EXPERIENCE + COLLECTIVE_WITH_ROLE`：DeepSeek **{cwr_total['cuc_deepseek']}** 条，"
        f"Qwen **{cwr_total['cuc_qwen']}** 条。"
    )
    both_cwr = [
        p for p in pairs_all
        if "COLLECTIVE_WITH_ROLE" in p["ds"]["participation_bases"]
        and "COLLECTIVE_WITH_ROLE" in p["qw"]["participation_bases"]
        and p["ds"]["experience_scope"] == "PERSONAL_EXPERIENCE"
        and p["qw"]["experience_scope"] == "PERSONAL_EXPERIENCE"
    ]
    lines.append(
        f"在近似同题配对中，**{len(both_cwr)}** 对事件两模型都判为 `PERSONAL_EXPERIENCE + COLLECTIVE_WITH_ROLE`。"
    )
    lines.append("")
    lines.append(
        "> 观察（不代裁决）：若两条线在相同原文上都大量使用这一依据，说明它主要来自**冻结契约 v0.3 §1.1 的允许项**"
        "（「我们参加／打仗」类动作动词），属于口径／规则层面，而非单一模型的系统性误判；"
        "此时按上一轮建议应「维持口径 + 个案改判」，不宜为此升提示词版本并重跑。"
        "若两模型差异显著，则更可能是模型行为差异，需要在方法章说明，或考虑统一的判例化人工复核尺度。"
    )
    lines.append("")

    # 五、配对与分歧
    lines.append("## 五、同题配对与范围分歧")
    lines.append("")
    lines.append(
        f"配对 {len(pairs_all)} 对，其中 `experience_scope` 一致 "
        f"{sum(1 for p in pairs_all if p['same_scope'])} 对、"
        f"**分歧 {sum(1 for p in pairs_all if not p['same_scope'])} 对**；"
        f"未配对：DeepSeek {sum(len(e['unpaired_ds']) for e in per_doc)} 条、"
        f"Qwen {sum(len(e['unpaired_qw']) for e in per_doc)} 条（多为归并粒度差异）。"
    )
    lines.append("")
    diffs = [p for p in pairs_all if not p["same_scope"]]
    if diffs:
        lines.append("### 5.1 范围判定分歧（需人工裁决的重点）")
        lines.append("")
        def norm_quote(s: str) -> str:
            return "".join(
                ch for ch in str(s)
                if "\u4e00" <= ch <= "\u9fff" or ch.isdigit() or ch.isalpha()
            )

        for i, p in enumerate(diffs, 1):
            d, q = p["ds"], p["qw"]
            a, b = norm_quote(d["scope_evidence_quote"]), norm_quote(q["scope_evidence_quote"])
            common = 0
            for x, y in zip(a, b):
                if x != y:
                    break
                common += 1
            same_evidence = bool(a and b and (a in b or b in a or common >= 12))
            kind = (
                "A 类｜同一证据、范围判定不同"
                if same_evidence
                else "B 类｜两边引的是不同内容，可能牵涉事件切分"
            )
            lines.append(f"#### [{i}] {p['doc']}　{kind}")
            lines.append("")
            lines.append(
                f"> 片段重叠 {p['inter']} 个 / 系数 {p['score']:.2f}。"
                + (
                    "**这是本表要裁的范围分歧**：同一段原文，两模型判了不同 `experience_scope`。"
                    if same_evidence
                    else "**先确认两边是不是同一个事件**；事件名、参与者或边界不同的话，不要在这里二选一，另案按事件边界处理。"
                )
            )
            lines.append("")
            lines.append(
                f"- **DeepSeek** `{d['document_event_id']}`：{d['canonical_event']['event_name']}"
            )
            lines.append(
                f"  - 范围：`{d['experience_scope']}` / 依据 `{', '.join(d['participation_bases'])}` / `{d['review_status']}`"
            )
            lines.append(f"  - 范围证据引文：{d['scope_evidence_quote']}")
            lines.append(
                f"- **Qwen** `{q['document_event_id']}`：{q['canonical_event']['event_name']}"
            )
            lines.append(
                f"  - 范围：`{q['experience_scope']}` / 依据 `{', '.join(q['participation_bases'])}` / `{q['review_status']}`"
            )
            lines.append(f"  - 范围证据引文：{q['scope_evidence_quote']}")
            ids = sorted(set(d["source_segment_ids"]) | set(q["source_segment_ids"]))
            lines.append("")
            lines.append(
                f"**完整逐字原文**（两事件 `source_segment_ids` 并集，共 {len(ids)} 片段；"
                "两模型该字段文本一致，取自 DeepSeek 输入；空白已规范化，汉字与标点逐字未改）："
            )
            lines.append("")
            for sid in ids:
                txt = seg_by_doc.get(p["doc"], {}).get(sid, "（该片段未在输入中找到）")
                lines.append(f"- `{sid}`：{' '.join(str(txt).split())}")
            lines.append("")
            lines.append(
                "- 最终裁决（写数字即可）：**1** 维持 `PERSONAL_EXPERIENCE`　**2** 改 `NARRATED_CONTEXT`　"
                "**3** 改 `UNCERTAIN`　**4** 暂缓（补上下文）"
            )
            lines.append("- 采信：□ DS 判定　□ QW 判定　□ 另判　依据／片段 ID：____________")
            lines.append("")
    else:
        lines.append("本批配对事件中无 `experience_scope` 分歧。")
        lines.append("")

    lines.append("### 5.2 逐字证据核对")
    lines.append("")
    for mdir, label in MODELS:
        bad = evidence_bad[mdir]
        total = evidence_ok[mdir] + len(bad)
        lines.append(
            f"- {label}：`scope_evidence_quote` 逐字命中 {evidence_ok[mdir]}/{total}"
            + (f"，**未命中：{', '.join(bad)}**" if bad else "，无错配／编造")
        )
    lines.append("")

    # 六、待办
    lines.append("## 六、待办与放行条件（SOP §6）")
    lines.append("")
    lines.append("1. 口径已由研究者 2026-11-07 裁决：**维持契约 v0.3**（逐条复核清单 39 条中 36 条维持 `PERSONAL_EXPERIENCE`），不升版本、不重跑；")
    lines.append("2. 用 `review/BATCH02_cuc_deepseek_COLLECTIVE_WITH_ROLE_逐条复核清单_20261107.md` 与本报告 §5.1 逐条裁决；")
    lines.append("   改判一律落 `human_adjudicated/<模型目录>/`，不动 `validated_json/`、不动冻结资产、不重跑；")
    lines.append("3. 补登与台账重建已完成（登记表 171 行／18 列、台账 22 行／25 列）；人工列仍待研究者填写；")
    lines.append("4. `human_review_status` / `release_status` / `notes` 由研究者填写；完成前所有结果保持 `MODEL_CANDIDATE`；")
    lines.append("5. 抽检与裁决完成后才放行 BATCH03；`AUTO_CONTINUE=1` 的「跳过人工抽检」只是**抽检后置**，不代表放行。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("本脚本只读，未调用 API、未修改任何模型输出、原始响应与冻结资产。")

    out = BATCH_ROOT / "document_consolidation" / "review" / f"{args.batch}_双模型同题对照_20261107.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"已生成：{out}")
    print(f"文档 {len(docs)} 份；配对 {len(pairs_all)} 对；范围分歧 {len(diffs)} 对")
    print(f"CWR+PERSONAL：DeepSeek {cwr_total['cuc_deepseek']}，Qwen {cwr_total['cuc_qwen']}，双方一致 {len(both_cwr)} 对")
    for mdir, label in MODELS:
        print(f"{label} 证据未命中：{len(evidence_bad[mdir])} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
