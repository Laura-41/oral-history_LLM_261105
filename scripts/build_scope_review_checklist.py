#!/usr/bin/env python3
"""生成 BATCH02 范围判定逐条复核清单（只读分析，不调用 API、不改模型输出与冻结资产）。

用法：
    python3 scripts/build_scope_review_checklist.py                     # 默认 cuc_deepseek
    python3 scripts/build_scope_review_checklist.py --model cuc/qwen     # Qwen 归并齐后可另出一份

输出：04_54份正式语料批处理/document_consolidation/review/
      BATCH02_<模型目录>_COLLECTIVE_WITH_ROLE_逐条复核清单_20261107.md
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "04_54份正式语料批处理" / "document_consolidation"

# 仅作"提示"用，不构成判定结论
RECIPIENT = re.compile(r"教我们|给我们讲|叫我们|请我们|让我们|给我们(上课|讲|做)")
NEG = re.compile(
    r"我不在现场|我没参加|没有参加|未参加|听说|不在场|我不在|以后我们才知道"
)
ALLOW_VERB = re.compile(
    r"我们(参加|接头|进入|撤退|转移|打仗|打|保卫|去|到|随后到|都去|翻|走|出发|全班|学生)"
    r"|要我们|我们[0-9]"
)


def model_dir(model: str) -> str:
    return model.replace("/", "_")


def quote(text: str, limit: int = 320) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…（原文更长，请回查输入文件）"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成范围判定逐条复核清单")
    parser.add_argument("--model", default="cuc/deepseek")
    parser.add_argument("--batch", default="BATCH02")
    args = parser.parse_args()

    mdir = model_dir(args.model)
    vdir = BASE / "validated_json" / mdir
    idir = BASE / "inputs" / mdir
    files = sorted(vdir.glob(f"{args.batch}-DOC*.json"))
    if not files:
        print(f"未找到结果文件：{vdir}/{args.batch}-DOC*.json")
        return 1

    rows: list[dict] = []
    for f in files:
        doc = f.stem
        result = json.loads(f.read_text(encoding="utf-8"))
        input_path = idir / f"{doc}.json"
        if not input_path.exists():
            print(f"缺少输入文件：{input_path}")
            return 1
        packet = json.loads(input_path.read_text(encoding="utf-8"))
        seg = {
            s["segment_id"]: s.get("verbatim_text", "")
            for s in packet["dialogue_segments"]
        }
        for event in result["consolidated_output"]["document_events"]:
            if (
                event["experience_scope"] == "PERSONAL_EXPERIENCE"
                and "COLLECTIVE_WITH_ROLE" in event["participation_bases"]
            ):
                rows.append({"doc": doc, "event": event, "seg": seg})

    flagged_recipient: list[str] = []
    flagged_neg: list[str] = []
    lines: list[str] = []
    lines.append(
        f"# {args.batch} / {args.model} · `COLLECTIVE_WITH_ROLE` 逐条复核清单"
    )
    lines.append("")
    lines.append(
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}　"
        f"生成脚本：`scripts/build_scope_review_checklist.py --model {args.model}`"
    )
    lines.append(
        "> 性质：**助手只读整理，不含任何人工标注结论**；所有事件仍为 `MODEL_CANDIDATE`，未入库、未放行。"
    )
    lines.append("> 本表只列 `PERSONAL_EXPERIENCE` 且含 `COLLECTIVE_WITH_ROLE` 的事件，供研究者逐条裁决。")
    lines.append("")
    lines.append("## 一、判定基准（冻结文件，不得在复核中临时变更）")
    lines.append("")
    lines.append("`document_consolidation_output_contract_v0.3` §1.1：")
    lines.append("")
    lines.append("**可构成具体行动证据（允许项）**")
    lines.append("")
    lines.append("1. 「我们参加／接头／进入／撤退／转移／打仗」等以「我们」为行动主体的明确动词；")
    lines.append("2. 「我们都去……」「我们随后到……」等明确陈述受访者随集体在场或移动；")
    lines.append("3. 已明确受访者属于该集体，且原文陈述该集体当时执行具体任务，同时无未参加、转述或不在场证据。")
    lines.append("")
    lines.append("**单独出现时仍不足以证明本人参与（禁止项）**")
    lines.append("")
    lines.append("1. 只有所有关系或泛称（「我们的部队」「我们政治处」「我们团」）；")
    lines.append("2. 只有接受者关系（「他教我们」「给我们讲」）；")
    lines.append("3. 只叙述集体的长期历史、后续沿革、战果或伤亡；")
    lines.append("4. 有「我不在现场」「我没参加」「听说」等反证。")
    lines.append("")
    lines.append("另据冻结清单 §二.4，回归已覆盖「本人直接任务、**具体集体行动**和直接受影响证据进入个人经历链」；")
    lines.append("§三.2 明确 `AUTO_VALIDATED` 只是自动流程状态，**不等于研究者最终人工确认**。")
    lines.append("")
    lines.append("**先例**：`review/BATCH01-DOC03_cuc_qwen_DE004_人工裁决.md` —— 「他教我们喊话」因接受者关系，")
    lines.append("由 `PERSONAL_EXPERIENCE + DIRECTLY_AFFECTED` 人工改判为 `NARRATED_CONTEXT + THIRD_PARTY_ONLY`。")
    lines.append("")
    lines.append("## 二、口径提示（重要）")
    lines.append("")
    lines.append("- 初检报告按「事件名含集体／战斗词」粗筛出 21 条；按 `participation_bases` 精确筛，")
    lines.append(f"  本模型本批共 **{len(rows)} 条** `PERSONAL_EXPERIENCE + COLLECTIVE_WITH_ROLE`，本表为全量。")
    lines.append("- 按 v0.3 §1.1 允许项 1，「我们参加车桥战役」「我们保卫繁昌」「要我们343旅迅速南下」")
    lines.append("  这类集体第一人称 + 动作动词的证据**属于现行冻结规则允许的个人经历依据**，不是模型违规。")
    lines.append("  因此这里要先区分两件事：**研究者是否要改标注口径**（改规则）与**个别事件是否违反 §1.1 禁止项**（改个案）。")
    lines.append("- 「契约比对提示」一列由关键词粗判，仅用于定位重点，**不构成判定**；请以逐字原文为准。")
    lines.append("")
    lines.append("## 三、逐条清单")
    lines.append("")
    for i, row in enumerate(rows, 1):
        e = row["event"]
        q = e["scope_evidence_quote"]
        context = " / ".join(
            row["seg"].get(sid, "") for sid in e["scope_evidence_segment_ids"]
        )
        alltext = " ".join(
            row["seg"].get(sid, "") for sid in e["source_segment_ids"]
        )
        hints: list[str] = []
        if RECIPIENT.search(q):
            hints.append("**疑似接受者关系**（§1.1 禁止项 2，对照 DE004 先例），建议优先裁决")
            flagged_recipient.append(f"[{i}] {e['document_event_id']}")
        elif ALLOW_VERB.search(q):
            hints.append("引文含「我们＋动作动词」（§1.1 允许项 1/2），按现行口径可成立")
        else:
            hints.append("引文未见明确动作动词，需按允许项 3 核对「属于该集体＋集体执行具体任务＋无反证」")
        if NEG.search(alltext):
            hints.append("该事件片段内出现疑似反证词，**需回查原文确认是否针对本事件**")
            flagged_neg.append(f"[{i}] {e['document_event_id']}")

        lines.append(f"### [{i}] {e['document_event_id']}")
        lines.append("")
        lines.append(f"- 事件名：{e['canonical_event']['event_name']}")
        lines.append(
            f"- 现状：`{e['experience_scope']}` / `{', '.join(e['participation_bases'])}` / "
            f"`{e['review_status']}` / `{e['completeness']}`"
        )
        lines.append(f"- 范围证据（逐字）：{quote(q, 400)}")
        lines.append(f"- 证据片段 `{'`, `'.join(e['scope_evidence_segment_ids'])}` 原文：{quote(context, 400)}")
        lines.append(f"- 事件片段数：{len(e['source_segment_ids'])}")
        lines.append(f"- 契约比对提示：{'；'.join(hints)}")
        lines.append(
            "- 研究者裁决：□ 维持 `PERSONAL_EXPERIENCE`　□ 改 `NARRATED_CONTEXT`　"
            "□ 改 `UNCERTAIN`　□ 暂缓（补上下文）"
        )
        lines.append("- 裁决依据／备注：________________________")
        lines.append("")

    lines.append("## 四、优先核对")
    lines.append("")
    lines.append("**疑似接受者关系（与 DE004 先例同类）**：" + (", ".join(flagged_recipient) or "无"))
    lines.append("")
    lines.append("**上下文含疑似反证词（需回查原文）**：" + (", ".join(flagged_neg) or "无"))
    lines.append("")
    lines.append("## 五、边界")
    lines.append("")
    lines.append("- 本脚本只读 `validated_json/` 与 `inputs/`，未调用 API、未修改任何模型输出；")
    lines.append("- 未改动冻结的提示词／契约／Schema／校验器；")
    lines.append("- 裁决落地方式：在 `human_adjudicated/<模型目录>/` 新建导入视图 + 裁决单 + 台账登记，")
    lines.append("  **不覆盖 `validated_json/` 里的模型原始结果**；")
    lines.append("- `HUMAN_CONFIRMED` 是人工复核状态，不在自动校验器枚举内，导入视图不参与自动评分。")
    lines.append("")

    out = (
        BASE / "review"
        / f"{args.batch}_{mdir}_COLLECTIVE_WITH_ROLE_逐条复核清单_20261107.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"已生成：{out}")
    print(f"条目数：{len(rows)}；疑似接受者关系 {len(flagged_recipient)} 条；疑似反证词 {len(flagged_neg)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
