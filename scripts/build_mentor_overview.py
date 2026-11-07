#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读整理：把文档级归并结果导出成「给导师看的一览表」（CSV + 单页 HTML）。

数据来源（只读，绝不修改）：
  - 04_54份正式语料批处理/document_consolidation/validated_json/<模型目录>/*.json
  - 04_54份正式语料批处理/document_consolidation/inputs/<模型目录>/*.json  （逐字原文片段）
  - 01_实验配置/双线批改台账.csv                                          （文档标题／人工状态）

重要口径：
  - 每行 = 一条「一级事件」（文档级归并后的 document_events）。
  - 大模型正式结果目前没有二级过程阶段（ProcessStage）字段；二级阶段只存在于
    /现行标注/01_*～06_*/process_stages.csv 的 6 份人工标注 Demo 中，本表如实标注为「本轮未产出」。
  - 全部事件仍是 MODEL_CANDIDATE；AUTO_VALIDATED 只是自动流程状态，不等于人工确认。
    本脚本不含任何人工标注结论，不参与放行。

用法：
  python3 scripts/build_mentor_overview.py
  python3 scripts/build_mentor_overview.py --out-dir <目录>
"""

import argparse
import csv
import html
import json
import pathlib
import collections
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONS = ROOT / "04_54份正式语料批处理" / "document_consolidation"
VALIDATED = CONS / "validated_json"
INPUTS = CONS / "inputs"
LEDGER = ROOT / "01_实验配置" / "双线批改台账.csv"

CSV_NAME = "导师查看_事件一览.csv"
HTML_NAME = "导师查看_事件一览.html"

STAGE_NOTE = "本轮未产出（仅 6 份人工标注 Demo 有）"

HEADERS = [
    "序号", "模型", "批次", "文档编号", "文档标题", "受访者", "层级",
    "一级事件ID", "事件名称", "事件类型(中文)", "事件类型(英文)", "核心过程",
    "参与者", "环境成分", "经历范围", "参与依据",
    "经历范围判定引文", "事件逐字证据引文", "证据片段ID", "原文片段(逐字)",
    "二级过程阶段", "完整性", "自动复核状态", "人工复核状态", "放行状态", "备注",
]

SCOPE_ZH = {
    "PERSONAL_EXPERIENCE": "个人经历",
    "NARRATED_CONTEXT": "讲述背景",
    "UNCERTAIN": "待定",
}
STATUS_ZH = {
    "AUTO_VALIDATED": "自动通过（未人工确认）",
    "NEEDS_REVIEW": "待人工复核",
    "MODEL_CANDIDATE": "模型候选",
    "HUMAN_CONFIRMED": "人工确认",
}
COMPLETENESS_ZH = {"COMPLETE": "完整", "INCOMPLETE": "不完整", "UNCERTAIN": "待定"}


def load_ledger():
    out = {}
    if not LEDGER.exists():
        return out
    with LEDGER.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = (row.get("model_id", "").strip(), row.get("technical_document_id", "").strip())
            out[key] = row
    return out


def load_segments(model_dir, doc_id):
    """返回 (元信息, {segment_id: 逐字原文})。按模型隔离，缺专属输入包时才退回公共目录。"""
    candidates = [INPUTS / model_dir / f"{doc_id}.json", INPUTS / f"{doc_id}.json"]
    for p in candidates:
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            segs = {
                s["segment_id"]: (s.get("verbatim_text") or "").strip()
                for s in d.get("dialogue_segments", [])
            }
            meta = {
                "document_id": d.get("document_id", ""),
                "interviewee": d.get("interviewee", ""),
            }
            return meta, segs, str(p.relative_to(ROOT))
    return {"document_id": "", "interviewee": ""}, {}, ""


def fmt_participants(items):
    if not items:
        return ""
    parts = []
    for p in items:
        norm = p.get("normalized_entity") or ""
        parts.append(f"{p.get('role','')}:{p.get('mention','')}" + (f"（{norm}）" if norm else ""))
    return "；".join(parts)


def fmt_circumstances(items):
    if not items:
        return ""
    return "；".join(
        f"{c.get('kind','')}:{c.get('value','')}" + (f"（{c['normalized_value']}）" if c.get("normalized_value") else "")
        for c in items
    )


def collect():
    rows, sources = [], []
    for model_dir in sorted(p for p in VALIDATED.iterdir() if p.is_dir()):
        ledger = load_ledger()
        for f in sorted(model_dir.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            doc_id = d.get("technical_document_id") or f.stem
            model_id = d.get("model_id") or model_dir.name
            meta, segs, input_rel = load_segments(model_dir.name, doc_id)
            led = ledger.get((model_id, doc_id), {})
            evs = d.get("consolidated_output", {}).get("document_events", [])
            sources.append({
                "model": model_id, "doc": doc_id, "events": len(evs),
                "result": str(f.relative_to(ROOT)), "input": input_rel,
            })
            for e in evs:
                ce = e.get("canonical_event") or {}
                seg_ids = e.get("source_segment_ids") or []
                verbatim = "\n".join(
                    f"[{sid}] {segs.get(sid, '（输入包中未找到该片段）')}" for sid in seg_ids
                )
                scope_ids = e.get("scope_evidence_segment_ids") or []
                rows.append({
                    "序号": 0,  # 稍后统一编号
                    "模型": model_id,
                    "批次": doc_id.split("-")[0] if "-" in doc_id else "",
                    "文档编号": doc_id,
                    "文档标题": led.get("document_title") or meta["document_id"],
                    "受访者": meta["interviewee"],
                    "层级": "一级事件（文档级归并结果）",
                    "一级事件ID": e.get("document_event_id", ""),
                    "事件名称": ce.get("event_name", ""),
                    "事件类型(中文)": ce.get("event_type_zh", ""),
                    "事件类型(英文)": ce.get("event_type", ""),
                    "核心过程": ce.get("core_process", ""),
                    "参与者": fmt_participants(ce.get("participants")),
                    "环境成分": fmt_circumstances(ce.get("circumstances")),
                    "经历范围": SCOPE_ZH.get(e.get("experience_scope"), e.get("experience_scope", "")),
                    "参与依据": "、".join(e.get("participation_bases") or []),
                    "经历范围判定引文": e.get("scope_evidence_quote") or "",
                    "事件逐字证据引文": ce.get("evidence_quote") or "",
                    "证据片段ID": "、".join(seg_ids) + ("；范围证据：" + "、".join(scope_ids) if scope_ids else ""),
                    "原文片段(逐字)": verbatim,
                    "二级过程阶段": STAGE_NOTE,
                    "完整性": COMPLETENESS_ZH.get(e.get("completeness"), e.get("completeness", "")),
                    "自动复核状态": STATUS_ZH.get(e.get("review_status"), e.get("review_status", "")),
                    "人工复核状态": led.get("human_review_status") or "待研究者填写",
                    "放行状态": led.get("release_status") or "未放行",
                    "备注": e.get("review_reason") or "",
                })
    for i, r in enumerate(rows, 1):
        r["序号"] = i
    return rows, sources


def write_csv(rows, path):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS)
        w.writeheader()
        w.writerows(rows)


PALETTE = ["#2563eb", "#7c3aed", "#0f766e", "#c2410c", "#b45309", "#475569", "#be185d", "#4d7c0f"]


def write_html(rows, sources, path):
    types = sorted({r["事件类型(中文)"] for r in rows if r["事件类型(中文)"]})
    colors = {t: PALETTE[i % len(PALETTE)] for i, t in enumerate(types)}
    docs = sorted({r["文档编号"] for r in rows})
    models = sorted({r["模型"] for r in rows})
    scopes = sorted({r["经历范围"] for r in rows if r["经历范围"]})
    type_counts = collections.Counter(r["事件类型(中文)"] for r in rows)
    scope_counts = collections.Counter(r["经历范围"] for r in rows)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    payload = json.dumps(rows, ensure_ascii=False).replace("<", "\\u003c")
    type_color = json.dumps(colors, ensure_ascii=False)

    def option(vals):
        return "".join(f'<option value="{html.escape(v)}">{html.escape(v)}</option>' for v in vals)

    stat_cards = "".join(
        f'<div class="card"><div class="num">{v}</div><div class="lab">{html.escape(k)}</div></div>'
        for k, v in [("模型", len(models)), ("文档", len(docs)), ("一级事件", len(rows))]
    )
    type_chips = " ".join(
        f'<span class="chip"><i style="background:{colors[t]}"></i>{html.escape(t)} {type_counts[t]}</span>'
        for t in types
    )
    scope_chips = " ".join(
        f'<span class="chip gray">{html.escape(k)} {v}</span>' for k, v in scope_counts.most_common()
    )

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>大模型事件标注结果一览（给导师查看）</title>
<style>
  :root {{ --ink:#1a2230; --muted:#5b6676; --line:#e2e7ee; --bg:#f5f7fa; --panel:#fff; --accent:#1d4ed8; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
         font-size:14px; line-height:1.6; }}
  .wrap {{ max-width:1600px; margin:0 auto; padding:28px 24px 60px; }}
  h1 {{ font-size:24px; margin:0 0 6px; }}
  .sub {{ color:var(--muted); font-size:13px; margin-bottom:18px; }}
  .warn {{ background:#fff7ed; border:1px solid #fed7aa; border-left:4px solid #ea580c;
           border-radius:8px; padding:12px 16px; margin-bottom:18px; font-size:13px; }}
  .warn b {{ color:#9a3412; }}
  .cards {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:14px; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
           padding:12px 20px; min-width:110px; }}
  .card .num {{ font-size:24px; font-weight:700; color:var(--accent); }}
  .card .lab {{ font-size:12px; color:var(--muted); }}
  .chips {{ margin-bottom:18px; font-size:12px; color:var(--muted); }}
  .chip {{ display:inline-flex; align-items:center; gap:5px; background:var(--panel);
           border:1px solid var(--line); border-radius:20px; padding:3px 10px; margin:2px 4px 2px 0; }}
  .chip i {{ width:8px; height:8px; border-radius:50%; display:inline-block; }}
  .chip.gray {{ color:var(--muted); }}
  .filters {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
              padding:12px 16px; margin-bottom:14px; display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
  select, input[type=search] {{ font:inherit; font-size:13px; padding:6px 10px; border:1px solid #cbd5e1;
                                border-radius:6px; background:#fff; color:var(--ink); }}
  input[type=search] {{ min-width:260px; }}
  .count {{ margin-left:auto; color:var(--muted); font-size:13px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--panel);
           border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  th {{ background:#eef2f7; text-align:left; font-size:12px; color:#334155; font-weight:600;
        padding:10px 10px; border-bottom:1px solid var(--line); position:sticky; top:0; z-index:2; }}
  td {{ padding:10px 10px; border-bottom:1px solid #eef1f5; vertical-align:top; font-size:13px; }}
  tr:hover td {{ background:#fafbfe; }}
  .nowrap {{ white-space:nowrap; }}
  .ename {{ font-weight:600; min-width:190px; }}
  .badge {{ display:inline-block; padding:1px 8px; border-radius:12px; font-size:12px; color:#fff; white-space:nowrap; }}
  .model {{ background:#eef2ff; color:#3730a3; border:1px solid #c7d2fe; border-radius:5px;
            padding:1px 6px; font-size:12px; white-space:nowrap; }}
  .scope {{ font-size:12px; color:#334155; white-space:nowrap; }}
  .quote {{ color:#334155; font-size:12.5px; max-width:420px; }}
  .quote::before {{ content:"“"; color:#94a3b8; }}
  .quote::after {{ content:"”"; color:#94a3b8; }}
  details {{ margin-top:5px; }}
  summary {{ cursor:pointer; color:var(--accent); font-size:12px; }}
  .verbatim {{ margin-top:6px; background:#f8fafc; border-left:3px solid #cbd5e1; padding:8px 12px;
               font-size:12.5px; color:#334155; white-space:pre-wrap; max-width:520px; max-height:320px; overflow:auto; }}
  .id {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:11.5px; color:#64748b; }}
  .st {{ font-size:12px; white-space:nowrap; }}
  .st.review {{ color:#b45309; }} .st.ok {{ color:#0f766e; }}
  .foot {{ margin-top:22px; color:var(--muted); font-size:12.5px; line-height:1.9; }}
  .foot code {{ background:#eef2f7; padding:1px 5px; border-radius:4px; font-size:12px; }}
  @media print {{
    body {{ background:#fff; }} .filters, summary {{ display:none; }}
    .verbatim {{ display:block !important; max-height:none; }}
    th {{ position:static; }} .wrap {{ padding:0; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <h1>大模型事件标注结果一览</h1>
  <div style="background:#ecfdf5;border:1px solid #99f6e4;border-radius:8px;padding:10px 14px;margin-bottom:14px;font-size:13px;">
    <b>新增看板</b>：<a href="导师查看_事件总看板.html" style="color:#0f766e;font-weight:600;">人工已标注 6 份（含二级阶段与逐字原文）＋大模型正式结果双视图 ↗</a>
    　｜　可按文档、类型、有无二级阶段筛选，逐条查看文档来源、一级事件属性、原文，以及二级阶段有几个／是什么／原文。
  </div>
  <div class="sub">生成时间：{now}　｜　来源：文档级归并技术通过结果（只读整理，未改动任何模型输出）　｜　共 {len(sources)} 份文档</div>

  <div class="warn">
    <b>状态说明（请先看）：</b>下列全部事件目前均为 <b>MODEL_CANDIDATE（模型候选）</b>，尚未入库、尚未放行。
    「自动通过」只是程序校验状态，<b>不等于研究者人工确认</b>；「待人工复核」的事件需要先裁决。
    表中「人工复核状态／放行状态」直接引自 <code>01_实验配置/双线批改台账.csv</code>，仍待填写。
    本表不含任何人工标注结论。
  </div>

  <div class="cards">{stat_cards}</div>
  <div class="chips">事件类型分布：{type_chips}</div>
  <div class="chips">经历范围分布：{scope_chips}</div>

  <div class="filters">
    <select id="fModel"><option value="">全部模型</option>{option(models)}</select>
    <select id="fDoc"><option value="">全部文档</option>{option(docs)}</select>
    <select id="fType"><option value="">全部类型</option>{option(types)}</select>
    <select id="fScope"><option value="">全部范围</option>{option(scopes)}</select>
    <input type="search" id="fKey" placeholder="搜索事件名 / 引文 / 原文 / 事件ID">
    <span class="count" id="cnt"></span>
  </div>

  <table>
    <thead><tr>
      <th>#</th><th>模型</th><th>文档</th><th>事件ID</th><th>一级事件名称</th><th>类型</th>
      <th>核心过程</th><th>经历范围</th><th>逐字证据引文</th><th>原文片段</th><th>自动状态</th><th>人工结论</th>
    </tr></thead>
    <tbody id="tb"></tbody>
  </table>

  <div class="foot">
    <b>字段口径</b>：每行 = 一条「一级事件」（<code>consolidated_output.document_events</code>，已跨窗口归并）。
    「类型」为韩礼德六类过程中的主导过程；「逐字证据引文」为模型给出的 <code>evidence_quote</code>；
    「原文片段」按 <code>source_segment_ids</code> 从该模型专属输入包逐字回取，点开可看全文及片段ID。<br>
    <b>关于二级事件</b>：本轮大模型正式结果<b>没有</b>产出二级过程阶段（ProcessStage）字段，
    因此列中标注「本轮未产出」。二级阶段目前只存在于 6 份人工标注 Demo 的
    <code>/现行标注/01_*～06_*/process_stages.csv</code>（配套 <code>event_nodes.csv</code> 为一级事件）。<br>
    <b>原始数据位置</b>：<code>04_54份正式语料批处理/document_consolidation/validated_json/&lt;模型目录&gt;/&lt;文档编号&gt;.json</code>；
    窗口层（归并前）候选在 <code>04_54份正式语料批处理/validated_json/&lt;模型目录&gt;/</code>；
    逐份抽检／复核意见在 <code>document_consolidation/review/</code>。<br>
    <b>按模型隔离</b>：<code>cuc_deepseek</code> 与 <code>cuc_qwen</code> 的结果分开登记，同一文档两模型结果请勿混读为一份标注。
  </div>
</div>

<script>
const DATA = {payload};
const COLORS = {type_color};
const tb = document.getElementById('tb');
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]);

function render() {{
  const m = document.getElementById('fModel').value;
  const d = document.getElementById('fDoc').value;
  const t = document.getElementById('fType').value;
  const s = document.getElementById('fScope').value;
  const k = document.getElementById('fKey').value.trim().toLowerCase();
  const list = DATA.filter(r =>
    (!m || r['模型'] === m) && (!d || r['文档编号'] === d) &&
    (!t || r['事件类型(中文)'] === t) && (!s || r['经历范围'] === s) &&
    (!k || [r['事件名称'],r['事件逐字证据引文'],r['原文片段(逐字)'],r['一级事件ID'],r['经历范围判定引文']]
              .join(' ').toLowerCase().includes(k))
  );
  document.getElementById('cnt').textContent = '显示 ' + list.length + ' / ' + DATA.length + ' 条';
  tb.innerHTML = list.map(r => {{
    const st = r['自动复核状态'];
    const stCls = st.includes('待') ? 'review' : 'ok';
    const col = COLORS[r['事件类型(中文)']] || '#475569';
    return `<tr>
      <td class="nowrap">${{r['序号']}}</td>
      <td class="nowrap"><span class="model">${{esc(r['模型'])}}</span></td>
      <td class="nowrap"><div>${{esc(r['文档编号'])}}</div><div class="id">${{esc(r['受访者'])}}</div></td>
      <td class="id nowrap">${{esc(r['一级事件ID'])}}</td>
      <td class="ename">${{esc(r['事件名称'])}}</td>
      <td class="nowrap"><span class="badge" style="background:${{col}}">${{esc(r['事件类型(中文)'])}}</span>
          <div class="id">${{esc(r['事件类型(英文)'])}}</div></td>
      <td>${{esc(r['核心过程'])}}</td>
      <td class="scope">${{esc(r['经历范围'])}}<div class="id">${{esc(r['完整性'])}}</div></td>
      <td class="quote">${{esc(r['事件逐字证据引文'])}}</td>
      <td><details><summary>展开逐字原文（${{esc((r['证据片段ID']||'').split('；')[0])}}）</summary>
          <div class="verbatim">${{esc(r['原文片段(逐字)'])}}</div></details></td>
      <td class="st ${{stCls}}">${{esc(st)}}</td>
      <td class="st">${{esc(r['人工复核状态'])}}<div class="id">${{esc(r['放行状态'])}}</div></td>
    </tr>`;
  }}).join('');
}}
['fModel','fDoc','fType','fScope','fKey'].forEach(id =>
  document.getElementById(id).addEventListener('input', render));
render();
</script>
</body>
</html>
"""
    path.write_text(doc, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(CONS), help="输出目录（默认 document_consolidation/）")
    args = ap.parse_args()
    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows, sources = collect()
    write_csv(rows, out / CSV_NAME)
    write_html(rows, sources, out / HTML_NAME)
    print(f"只读整理完成：{len(rows)} 条一级事件，来自 {len(sources)} 份文档")
    for s in sources:
        print(f"  {s['model']:<14} {s['doc']:<16} {s['events']:>3} 条")
    print("输出：")
    print(f"  {out / HTML_NAME}")
    print(f"  {out / CSV_NAME}")


if __name__ == "__main__":
    main()
