#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读整理：生成「给导师看」的双视图事件总看板（单页 HTML + 人工6份 CSV）。

两个视图：
  A. 人工已标注 6 份（WORKFLOW_DEMO）：一行 = 一条一级事件；展开可见
     文档来源、一级事件全部属性、事件层逐字原文、二级阶段（几个/是什么/逐字原文）。
  B. 大模型正式结果（MODEL_CANDIDATE）：直接复用 导师查看_事件一览.csv，
     保持原看板的模型/文档/类型/范围/关键词筛选。

数据来源（只读，绝不修改）：
  - ../现行标注/neo4j_demo/import/*.csv   六份人工标注 Demo 的合并导入表
  - 04_54份正式语料批处理/document_consolidation/导师查看_事件一览.csv

口径提醒：
  - 人工 6 份的 CONFIRMED 指「人工核验」，数据角色是 WORKFLOW_DEMO，
    不是正式测试金标准；大模型侧仍是 MODEL_CANDIDATE、未入库未放行。
  - 逐字原文取自 SourceSegment.verbatim_text；SourceAttachment.function
    区分 EVIDENCE / BACKGROUND / INTERVIEWER_PROMPT / DOCUMENT_NOTE / COMMENT。
  - 同一原文片段允许同时挂一级事件与二级阶段（方案 §5.10 双重挂接），
    两层的片段数不可相加当作独立语料量。

用法：
  python3 scripts/build_mentor_dashboard.py
  python3 scripts/build_mentor_dashboard.py --out-dir <目录>
"""

import argparse
import csv
import json
import pathlib
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONS = ROOT / "04_54份正式语料批处理" / "document_consolidation"
IMPORT_DIR = ROOT.parent / "现行标注" / "neo4j_demo" / "import"
OFFICIAL_CSV = CONS / "导师查看_事件一览.csv"

HTML_NAME = "导师查看_事件总看板.html"
CSV_NAME = "导师查看_人工6份标注一览.csv"

TYPE_ZH = {
    "MATERIAL_EVENT": "物质事件",
    "MENTAL_EVENT": "心理事件",
    "RELATIONAL_EVENT": "关系事件",
    "VERBAL_EVENT": "言语事件",
    "BEHAVIOURAL_EVENT": "行为事件",
    "EXISTENTIAL_EVENT": "存在事件",
}
LOGIC_ZH = {
    "SEQUENCE": "顺承", "ENABLES": "使能", "CAUSES": "因果",
    "RESULTS_IN": "导致", "ELABORATES": "详述",
}
FUNC_ZH = {
    "EVIDENCE": "逐字证据", "BACKGROUND": "背景说明",
    "INTERVIEWER_PROMPT": "采访者提问", "DOCUMENT_NOTE": "编者注／文档注",
    "COMMENT": "叙述者评价", "DOCUMENT_ONLY": "文档级兜底",
}
FUNC_ORDER = {"EVIDENCE": 0, "BACKGROUND": 1, "INTERVIEWER_PROMPT": 2,
              "DOCUMENT_NOTE": 3, "COMMENT": 4, "DOCUMENT_ONLY": 5}
PALETTE = ["#2563eb", "#7c3aed", "#0f766e", "#c2410c", "#b45309", "#475569"]

HUMAN_HEADERS = [
    "序号", "数据来源", "文档编号", "文档标题", "受访者", "访谈日期", "访问次序", "标注版本",
    "原始语料文件", "文档复核状态",
    "一级事件ID", "事件名称", "叙述顺序", "历史顺序", "事件类型(中文)", "事件类型(英文)",
    "核心过程", "规范过程", "事件时间原文", "规范起止", "时间精度",
    "参与者", "环境成分", "结果状态", "事实性", "置信度", "边界说明", "边界判断置信度", "事件复核状态",
    "事件原文条数", "事件逐字证据条数", "事件原文(逐字)", "事件证据片段ID",
    "二级阶段数", "二级阶段清单", "阶段链逻辑", "二级阶段原文(逐字)", "阶段证据片段ID",
    "备注",
]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def group(rows, key):
    out = {}
    for r in rows:
        out.setdefault((r.get(key) or "").strip(), []).append(r)
    return out


def esc_text(s):
    """逐字原文：只去首尾空白，正文不改。"""
    return (s or "").strip()


def build_sources(attachments, segments):
    """按 (target_type, target_id) 索引原文片段。"""
    out = {}
    for a in attachments:
        key = ((a.get("target_type") or "").strip(), (a.get("target_id") or "").strip())
        sid = (a.get("segment_id") or "").strip()
        seg = segments.get(sid, {})
        out.setdefault(key, []).append({
            "id": (a.get("attachment_id") or "").strip(),
            "sid": sid,
            "order": int(seg.get("segment_order") or 0),
            "func": (a.get("function") or "").strip(),
            "func_zh": FUNC_ZH.get((a.get("function") or "").strip(), (a.get("function") or "").strip()),
            "part": (seg.get("source_part") or "").strip(),
            "speaker": (seg.get("speaker_id") or "").strip(),
            "text": esc_text(seg.get("verbatim_text")),
        })
    for v in out.values():
        v.sort(key=lambda x: (FUNC_ORDER.get(x["func"], 9), x["order"], x["sid"]))
    return out


def fmt_sources(items):
    return "\n".join(f"[{s['sid']}｜{s['func']}] {s['text']}" for s in items)


def collect_human():
    docs = {r["doc_id"].strip(): r for r in read_csv(IMPORT_DIR / "documents.csv")}
    events = read_csv(IMPORT_DIR / "event_nodes.csv")
    segments = {r["segment_id"].strip(): r for r in read_csv(IMPORT_DIR / "source_segments.csv")}
    sources = build_sources(read_csv(IMPORT_DIR / "source_attachments.csv"), segments)

    processes = group(read_csv(IMPORT_DIR / "event_processes.csv"), "event_id")
    times = group(read_csv(IMPORT_DIR / "event_times.csv"), "event_id")
    participants = group(read_csv(IMPORT_DIR / "event_participants.csv"), "event_id")
    circumstances = group(read_csv(IMPORT_DIR / "event_circumstances.csv"), "event_id")
    stages_by_event = group(read_csv(IMPORT_DIR / "process_stages.csv"), "event_id")
    stage_next = {r["source_stage_id"].strip(): r for r in read_csv(IMPORT_DIR / "stage_next.csv")}

    rows = []
    for e in events:
        eid = (e.get("event_id") or "").strip()
        doc_id = (e.get("doc_id") or "").strip()
        doc = docs.get(doc_id, {})
        proc = (processes.get(eid) or [{}])[0]
        type_en = (proc.get("event_type_id") or "").strip()
        time_rows = times.get(eid) or []
        time0 = time_rows[0] if time_rows else {}

        ev_src = sources.get(("EVENT", eid), [])
        stage_rows = sorted(stages_by_event.get(eid, []),
                            key=lambda x: int(x.get("stage_order") or 0))
        stages = []
        for st in stage_rows:
            sid = (st.get("stage_id") or "").strip()
            nxt = stage_next.get(sid, {})
            st_src = sources.get(("STAGE", sid), [])
            stages.append({
                "id": sid,
                "order": int(st.get("stage_order") or 0),
                "name": (st.get("stage_summary") or "").strip(),
                "process": (st.get("process_text") or "").strip(),
                "confidence": (st.get("confidence") or "").strip(),
                "status": (st.get("review_status") or "").strip(),
                "logic": (nxt.get("logic") or "").strip(),
                "logic_zh": LOGIC_ZH.get((nxt.get("logic") or "").strip(), (nxt.get("logic") or "").strip()),
                "next_id": (nxt.get("target_stage_id") or "").strip(),
                "sources": st_src,
            })

        part_txt = "；".join(
            f"{p.get('role','').strip()}：{p.get('entity_name','').strip()}"
            for p in participants.get(eid, [])
        )
        circ_txt = "；".join(
            f"{c.get('kind','').strip()}：{c.get('value_text','').strip()}"
            for c in circumstances.get(eid, [])
        )
        time_range = (time0.get("normalized_start") or "").strip()
        if (time0.get("normalized_end") or "").strip() and (time0.get("normalized_end") or "").strip() != time_range:
            time_range += "—" + (time0.get("normalized_end") or "").strip()

        ev_ids = "、".join(s["sid"] for s in ev_src)
        ev_evidence_ids = "、".join(s["sid"] for s in ev_src if s["func"] == "EVIDENCE")
        stage_ids = "、".join(s["sid"] for st in stages for s in st["sources"])
        stage_names = "；".join(f"{st['order']}.{st['name']}" for st in stages)
        chain_logic = " → ".join(
            f"{st['logic'] or '终点'}" for st in stages
        )
        stage_text = "\n".join(
            f"[{st['id']}｜阶段{st['order']}：{st['name']}]\n" + fmt_sources(st["sources"])
            for st in stages
        )

        rows.append({
            "序号": len(rows) + 1,
            "数据来源": "人工标注 6 份 Demo（WORKFLOW_DEMO）",
            "文档编号": doc_id,
            "文档标题": (doc.get("title") or "").strip(),
            "受访者": (doc.get("interviewee") or "").strip(),
            "访谈日期": (doc.get("interview_date") or "").strip(),
            "访问次序": (doc.get("visit_no") or "").strip(),
            "标注版本": (doc.get("version") or "").strip(),
            "原始语料文件": (doc.get("source_file") or "").strip(),
            "文档复核状态": (doc.get("review_status") or "").strip(),
            "一级事件ID": eid,
            "事件名称": (e.get("event_name") or "").strip(),
            "叙述顺序": (e.get("narrative_order") or "").strip(),
            "历史顺序": (e.get("historical_order") or "").strip(),
            "事件类型(中文)": TYPE_ZH.get(type_en, type_en),
            "事件类型(英文)": type_en,
            "核心过程": (proc.get("process_text") or "").strip(),
            "规范过程": (proc.get("process_normalized") or "").strip(),
            "事件时间原文": (time0.get("raw_text") or "").strip(),
            "规范起止": time_range,
            "时间精度": (time0.get("precision") or "").strip(),
            "参与者": part_txt,
            "环境成分": circ_txt,
            "结果状态": (e.get("result_state") or "").strip(),
            "事实性": (e.get("factuality") or "").strip(),
            "置信度": (e.get("confidence") or "").strip(),
            "边界说明": (e.get("boundary_note") or "").strip(),
            "边界判断置信度": (e.get("boundary_confidence") or "").strip(),
            "事件复核状态": (e.get("review_status") or "").strip(),
            "事件原文条数": len(ev_src),
            "事件逐字证据条数": sum(1 for s in ev_src if s["func"] == "EVIDENCE"),
            "事件原文(逐字)": fmt_sources(ev_src),
            "事件证据片段ID": ev_ids + ("；逐字证据：" + ev_evidence_ids if ev_evidence_ids else ""),
            "二级阶段数": len(stages),
            "二级阶段清单": stage_names,
            "阶段链逻辑": chain_logic,
            "二级阶段原文(逐字)": stage_text,
            "阶段证据片段ID": stage_ids,
            "备注": "阶段原文与事件层原文允许双重挂接，数量不可相加",
            # 前端专用（不写进 CSV）
            "_doc": {
                "id": doc_id, "title": (doc.get("title") or "").strip(),
                "person": (doc.get("interviewee") or "").strip(),
                "date": (doc.get("interview_date") or "").strip(),
                "version": (doc.get("version") or "").strip(),
                "file": (doc.get("source_file") or "").strip(),
                "status": (doc.get("review_status") or "").strip(),
            },
            "_eventSources": ev_src,
            "_stages": stages,
            "_timeRows": [
                {"raw": (t.get("raw_text") or "").strip(),
                 "start": (t.get("normalized_start") or "").strip(),
                 "end": (t.get("normalized_end") or "").strip(),
                 "precision": (t.get("precision") or "").strip()}
                for t in time_rows
            ],
        })
    return rows


def collect_official():
    if not OFFICIAL_CSV.exists():
        return []
    return read_csv(OFFICIAL_CSV)


def write_human_csv(rows, path):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HUMAN_HEADERS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>事件标注结果总看板（给导师查看）</title>
<style>
  :root { --ink:#1a2230; --muted:#5b6676; --line:#e2e7ee; --bg:#f5f7fa; --panel:#fff;
          --accent:#1d4ed8; --human:#0f766e; --candidate:#b45309; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
         font-size:14px; line-height:1.6; }
  .wrap { max-width:1760px; margin:0 auto; padding:26px 22px 60px; }
  h1 { font-size:24px; margin:0 0 6px; }
  .sub { color:var(--muted); font-size:13px; margin-bottom:16px; }
  .topbar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:16px; }
  .tab { font:inherit; font-size:14px; font-weight:600; cursor:pointer; padding:9px 18px;
         border:1px solid var(--line); border-radius:9px; background:var(--panel); color:var(--muted); }
  .tab.on { background:var(--accent); border-color:var(--accent); color:#fff; }
  .tab.on.human { background:var(--human); border-color:var(--human); }
  .link { margin-left:auto; font-size:13px; color:var(--accent); text-decoration:none; }
  .warn { background:#fff7ed; border:1px solid #fed7aa; border-left:4px solid #ea580c;
          border-radius:8px; padding:12px 16px; margin-bottom:16px; font-size:13px; }
  .warn b { color:#9a3412; }
  .warn.human { background:#f0fdfa; border-color:#99f6e4; border-left-color:var(--human); }
  .warn.human b { color:#115e59; }
  .cards { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:12px; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:10px;
          padding:12px 20px; min-width:120px; }
  .card .num { font-size:24px; font-weight:700; color:var(--accent); }
  .card.human .num { color:var(--human); }
  .card .lab { font-size:12px; color:var(--muted); }
  .chips { margin-bottom:12px; font-size:12px; color:var(--muted); }
  .chip { display:inline-flex; align-items:center; gap:5px; background:var(--panel);
          border:1px solid var(--line); border-radius:20px; padding:3px 10px; margin:2px 4px 2px 0; }
  .chip i { width:8px; height:8px; border-radius:50%; display:inline-block; }
  .filters { background:var(--panel); border:1px solid var(--line); border-radius:10px;
             padding:12px 16px; margin-bottom:14px; display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
  select, input[type=search] { font:inherit; font-size:13px; padding:6px 10px; border:1px solid #cbd5e1;
                               border-radius:6px; background:#fff; color:var(--ink); }
  input[type=search] { min-width:270px; }
  .count { margin-left:auto; color:var(--muted); font-size:13px; }
  .tablebox { overflow-x:auto; border:1px solid var(--line); border-radius:10px; background:var(--panel); }
  table { width:100%; min-width:1500px; border-collapse:collapse; }
  table.human { table-layout:fixed; min-width:1600px; }
  th { background:#eef2f7; text-align:left; font-size:12px; color:#334155; font-weight:600;
       padding:10px; border-bottom:1px solid var(--line); position:sticky; top:0; z-index:2; }
  td { padding:10px; border-bottom:1px solid #eef1f5; vertical-align:top; font-size:13px;
       word-break:break-word; }
  table.human .id { word-break:break-all; }
  tr:hover td { background:#fafbfe; }
  .nowrap { white-space:nowrap; }
  .ename { font-weight:600; min-width:180px; }
  .id { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:11.5px; color:#64748b; }
  .muted { color:var(--muted); font-size:12px; }
  .badge { display:inline-block; padding:1px 8px; border-radius:12px; font-size:12px; color:#fff; white-space:nowrap; }
  .tag { display:inline-block; background:#f1f5f9; border:1px solid #e2e8f0; border-radius:5px;
         padding:1px 6px; font-size:12px; margin:1px 3px 1px 0; }
  .tag.ev { background:#ecfdf5; border-color:#a7f3d0; color:#065f46; }
  .tag.warn { background:#fffbeb; border-color:#fde68a; color:#92400e; }
  .model { background:#eef2ff; color:#3730a3; border:1px solid #c7d2fe; border-radius:5px;
           padding:1px 6px; font-size:12px; white-space:nowrap; }
  .kv { margin-bottom:3px; font-size:12.5px; }
  .kv b { color:#475569; font-weight:600; }
  .stage-line { font-size:12.5px; margin:2px 0; }
  .stage-line .n { display:inline-block; min-width:18px; color:var(--human); font-weight:700; }
  details { margin-top:5px; }
  summary { cursor:pointer; color:var(--accent); font-size:12px; }
  .verbatim { margin-top:6px; background:#f8fafc; border-left:3px solid #cbd5e1; padding:8px 12px;
              font-size:12.5px; color:#334155; white-space:pre-wrap; max-width:640px;
              max-height:360px; overflow:auto; }
  .verbatim .sh { color:#0f766e; font-weight:600; }
  .verbatim .sb { color:#b45309; }
  .stage-card { margin:8px 0 12px; padding:10px 12px; border:1px solid #d5f5ef;
                 border-left:4px solid var(--human); border-radius:8px; background:#fbfffe; }
  .stage-card h4 { margin:0 0 4px; font-size:13px; }
  .stage-card .meta { font-size:12px; color:var(--muted); margin-bottom:6px; }
  .quote { color:#334155; font-size:12.5px; max-width:420px; }
  .quote::before { content:"“"; color:#94a3b8; }
  .quote::after { content:"”"; color:#94a3b8; }
  .st { font-size:12px; white-space:nowrap; }
  .st.ok { color:#0f766e; font-weight:600; }
  .st.review { color:#b45309; }
  .foot { margin-top:22px; color:var(--muted); font-size:12.5px; line-height:1.9; }
  .foot code { background:#eef2f7; padding:1px 5px; border-radius:4px; font-size:12px; }
  .hidden { display:none !important; }
  .expand { font:inherit; font-size:12px; cursor:pointer; margin-top:6px; padding:4px 9px;
            border:1px solid #99f6e4; border-radius:6px; background:#ecfdf5;
            color:#0f766e; font-weight:600; white-space:nowrap; }
  .expand.on { background:#0f766e; color:#fff; }
  .detail-row td { background:#f7fafc; border-bottom:2px solid #cbd5e1; padding:14px; }
  .detail-grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
  .panel { background:#fff; border:1px solid var(--line); border-radius:9px; padding:12px 14px; }
  .panel h3 { margin:0 0 8px; font-size:13px; color:#0f766e;
              border-bottom:1px solid var(--line); padding-bottom:5px; }
  .panel h3:not(:first-child) { margin-top:16px; }
  .detail-row .verbatim { max-width:100%; max-height:260px; }
  @media (max-width:1100px) { .detail-grid { grid-template-columns:1fr; } }
  @media print {
    body { background:#fff; } .filters, .topbar, summary, .expand { display:none; }
    .verbatim { max-height:none; display:block !important; }
    th { position:static; } .wrap { padding:0; }
    .tablebox { overflow:visible; } table, table.human { min-width:0; table-layout:auto; }
    .detail-grid { grid-template-columns:1fr 1fr; }
  }
</style>
</head>
<body>
<div class="wrap">
  <h1>事件标注结果总看板</h1>
  <div class="sub">生成时间：__NOW__　｜　只读整理，未改动任何标注结果　｜　两个视图的数据来源与状态互不相同，请勿混读</div>

  <div class="topbar">
    <button class="tab on human" id="tabHuman" onclick="switchView('human')">① 人工已标注 6 份（Demo）</button>
    <button class="tab" id="tabOfficial" onclick="switchView('official')">② 大模型正式结果（候选）</button>
    <a class="link" href="导师查看_事件一览.html">打开原来的单表看板 ↗</a>
  </div>

  <div class="warn human" id="warnHuman">
    <b>人工 6 份说明：</b>这一视图是<b>研究者人工核验过的 6 份工作流 Demo</b>（<code>WORKFLOW_DEMO</code>），
    文档与事件均为 <code>CONFIRMED</code>，含<b>二级过程阶段</b>及其逐字原文。
    但它是<b>工作流演示样本，不是正式测试金标准</b>；原文按 <code>SourceAttachment.function</code> 标注用途，
    只有 <code>EVIDENCE</code> 是可作史实依据的逐字证据。同一片段允许同时挂一级事件与二级阶段，两层数量不可相加。
  </div>
  <div class="warn hidden" id="warnOfficial">
    <b>状态说明：</b>下列全部事件目前均为 <b>MODEL_CANDIDATE（模型候选）</b>，尚未入库、尚未放行。
    「自动通过」只是程序校验状态，<b>不等于人工确认</b>；本轮大模型结果<b>没有</b>产出二级过程阶段。
    人工复核／放行状态直接引自 <code>01_实验配置/双线批改台账.csv</code>。
  </div>

  <div class="cards" id="cards"></div>
  <div class="chips" id="chips"></div>

  <div class="filters" id="fHuman">
    <select id="hDoc"><option value="">全部文档（6 份）</option></select>
    <select id="hType"><option value="">全部事件类型</option></select>
    <select id="hStage"><option value="">二级阶段：全部</option><option value="yes">有二级阶段</option><option value="no">无二级阶段</option></select>
    <select id="hStatus"><option value="">全部复核状态</option></select>
    <input type="search" id="hKey" placeholder="搜索文档 / 一级事件 / 二级阶段 / 原文 / 事件ID">
    <span class="count" id="hCnt"></span>
  </div>
  <div class="filters hidden" id="fOfficial">
    <select id="oModel"><option value="">全部模型</option></select>
    <select id="oDoc"><option value="">全部文档</option></select>
    <select id="oType"><option value="">全部类型</option></select>
    <select id="oScope"><option value="">全部范围</option></select>
    <input type="search" id="oKey" placeholder="搜索事件名 / 引文 / 原文 / 事件ID">
    <span class="count" id="oCnt"></span>
  </div>

  <div class="tablebox">
    <table id="tbl">
      <thead id="thead"></thead>
      <tbody id="tb"></tbody>
    </table>
  </div>

  <div class="foot" id="foot"></div>
</div>

<script>
const HUMAN = __HUMAN__;
const OFFICIAL = __OFFICIAL__;
const COLORS = __COLORS__;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const uniq = (a) => [...new Set(a.filter(x => x !== '' && x != null))].sort();
const $ = id => document.getElementById(id);
let VIEW = 'human';
const OPEN = new Set();       // 已展开「完整档案」的事件序号
let VISIBLE = [];             // 当前筛选结果，供打印时批量展开

function toggleDetail(n) {
  if (OPEN.has(n)) OPEN.delete(n); else OPEN.add(n);
  renderHuman();
}

function fillSelect(id, vals, label) {
  $(id).innerHTML = '<option value="">' + label + '</option>' +
    vals.map(v => '<option value="' + esc(v) + '">' + esc(v) + '</option>').join('');
}

function srcBlock(items) {
  if (!items.length) return '<div class="muted">（无挂接原文）</div>';
  return items.map(s =>
    '<div class="verbatim"><span class="sh">[' + esc(s.sid) + '｜' + esc(s.func_zh) +
    (s.order ? '｜顺序' + s.order : '') + ']</span>' +
    (s.func === 'EVIDENCE' ? '' : '<span class="sb">（非逐字证据，仅作背景／提示）</span>') +
    '\n' + esc(s.text) + '</div>'
  ).join('');
}

function stageCards(stages) {
  if (!stages.length) return '<div class="muted">该一级事件未划分二级阶段（短事件，按方案 §5.10 可不设阶段）。</div>';
  return stages.map(st =>
    '<div class="stage-card">' +
      '<h4>阶段 ' + st.order + '　' + esc(st.name) + '</h4>' +
      '<div class="meta">' + esc(st.id) + '　｜　关键过程：' + esc(st.process) +
      '　｜　推进逻辑：' + esc(st.logic_zh || '终点（无后继）') +
      (st.next_id ? ' → ' + esc(st.next_id) : '') +
      '　｜　' + esc(st.status) + '　｜　原文 ' + st.sources.length + ' 段</div>' +
      srcBlock(st.sources) +
    '</div>'
  ).join('');
}

function detailRow(r) {
  const doc = r._doc, stages = r._stages;
  const docAttrs = [
    ['文档标题', doc.title], ['文档编号', doc.id], ['受访者', doc.person],
    ['访谈日期', doc.date], ['标注版本', doc.version], ['原始语料文件', doc.file],
    ['文档复核状态', doc.status],
  ];
  const evAttrs = [
    ['事件ID', r['一级事件ID']], ['事件名称', r['事件名称']],
    ['事件类型', r['事件类型(中文)'] + ' / ' + r['事件类型(英文)']],
    ['核心过程', r['核心过程']], ['规范过程', r['规范过程']],
    ['事件时间', r['事件时间原文'] + '　' + r['规范起止'] + '　' + r['时间精度']],
    ['参与者', r['参与者']], ['环境成分', r['环境成分']],
    ['结果状态', r['结果状态']],
    ['事实性 / 置信度', r['事实性'] + ' / ' + r['置信度']],
    ['边界说明', r['边界说明']], ['边界判断置信度', r['边界判断置信度']],
    ['叙述 / 历史顺序', r['叙述顺序'] + ' / ' + r['历史顺序']],
    ['事件复核状态', r['事件复核状态']],
  ];
  const kv = (pairs) => pairs.map(([k, v]) =>
    '<div class="kv"><b>' + esc(k) + '：</b>' + esc(v) + '</div>').join('');
  return '<tr class="detail-row"><td colspan="8"><div class="detail-grid">' +
    '<div class="panel">' +
      '<h3>① 文档来源</h3>' + kv(docAttrs) +
      '<h3>② 一级事件完整属性</h3>' + kv(evAttrs) +
      '<h3>③ 一级事件逐字原文（共 ' + r['事件原文条数'] + ' 段，其中 EVIDENCE ' +
        r['事件逐字证据条数'] + ' 段）</h3>' + srcBlock(r._eventSources) +
    '</div>' +
    '<div class="panel">' +
      '<h3>④ 二级阶段：共 ' + stages.length + ' 个（是什么 / 顺序 / 推进逻辑 / 原文）</h3>' +
      (stages.length
        ? '<div class="muted">阶段链：' + esc(stages.map(st => st.order + '.' + st.name).join(' → ')) + '</div>' + stageCards(stages)
        : '<div class="muted">该一级事件未划分二级阶段（按方案 §5.10，短事件可不设阶段）。</div>') +
      '<div class="muted" style="margin-top:10px">同一原文片段允许同时挂一级事件与二级阶段，两层片段数不可相加。</div>' +
    '</div>' +
  '</div></td></tr>';
}

function humanRow(r) {
  const col = COLORS[r['事件类型(中文)']] || '#475569';
  const doc = r._doc;
  const stages = r._stages;
  const evN = r['事件原文条数'], evE = r['事件逐字证据条数'];
  const stageLabel = stages.length
    ? stages.map(st => '<div class="stage-line"><span class="n">' + st.order + '</span>' + esc(st.name) + '</div>').join('')
    : '<div class="muted">无（短事件未分阶段）</div>';
  const partShort = (r['参与者'] || '').split('；').slice(0, 2).join('；');
  const circShort = (r['环境成分'] || '').split('；').slice(0, 1).join('；');
  const open = OPEN.has(r['序号']);
  return '<tr>' +
    '<td class="nowrap">' + r['序号'] + '</td>' +
    '<td><div class="ename">' + esc(doc.title) + '</div>' +
        '<div class="id">' + esc(doc.id) + '</div>' +
        '<div class="muted">' + esc(doc.person) + '　' + esc(doc.date) + '</div></td>' +
    '<td><div class="ename">' + esc(r['事件名称']) + '</div>' +
        '<div class="id">' + esc(r['一级事件ID']) + '</div>' +
        '<div class="kv"><b>结果：</b>' + esc(r['结果状态']) + '</div></td>' +
    '<td class="nowrap"><span class="badge" style="background:' + col + '">' + esc(r['事件类型(中文)']) + '</span>' +
        '<div class="id">' + esc(r['事件类型(英文)']) + '</div>' +
        '<div class="kv"><b>时间：</b>' + esc(r['事件时间原文']) + '</div>' +
        '<div class="id">' + esc(r['规范起止']) + '　' + esc(r['时间精度']) + '</div></td>' +
    '<td><div class="kv"><b>核心过程：</b>' + esc(r['核心过程']) + '</div>' +
        '<div class="kv"><b>参与者：</b>' + esc(partShort) + '</div>' +
        '<div class="kv"><b>环境：</b>' + esc(circShort) + '</div>' +
        '<div class="kv"><b>事实性：</b>' + esc(r['事实性']) + '／' + esc(r['置信度']) + '</div>' +
        '<div class="muted">全部属性见下方完整档案</div></td>' +
    '<td><span class="tag ev">逐字证据 ' + evE + '</span><span class="tag">共 ' + evN + ' 段</span>' +
        '<div class="muted">逐字原文见下方完整档案</div></td>' +
    '<td><span class="tag" style="background:#ecfdf5;border-color:#a7f3d0;color:#065f46">' + stages.length + ' 个二级阶段</span>' +
        stageLabel +
        '<div class="muted">阶段原文见下方完整档案</div></td>' +
    '<td class="st ok">' + esc(r['事件复核状态']) + '<div class="id">人工标注 Demo</div>' +
        '<button class="expand' + (open ? ' on' : '') + '" onclick="toggleDetail(' + r['序号'] + ')">' +
        (open ? '收起完整档案 ▲' : '展开完整档案 ▼') + '</button></td>' +
  '</tr>';
}

function officialRow(r) {
  const st = r['自动复核状态'] || '';
  const stCls = st.includes('待') ? 'review' : 'ok';
  const col = COLORS[r['事件类型(中文)']] || '#475569';
  return '<tr>' +
    '<td class="nowrap">' + esc(r['序号']) + '</td>' +
    '<td class="nowrap"><span class="model">' + esc(r['模型']) + '</span></td>' +
    '<td class="nowrap"><div>' + esc(r['文档编号']) + '</div><div class="id">' + esc(r['受访者']) + '</div></td>' +
    '<td class="id nowrap">' + esc(r['一级事件ID']) + '</td>' +
    '<td class="ename">' + esc(r['事件名称']) + '</td>' +
    '<td class="nowrap"><span class="badge" style="background:' + col + '">' + esc(r['事件类型(中文)']) + '</span>' +
        '<div class="id">' + esc(r['事件类型(英文)']) + '</div></td>' +
    '<td>' + esc(r['核心过程']) + '</td>' +
    '<td class="nowrap">' + esc(r['经历范围']) + '<div class="id">' + esc(r['完整性']) + '</div></td>' +
    '<td class="quote">' + esc(r['事件逐字证据引文']) + '</td>' +
    '<td><details><summary>展开逐字原文</summary><div class="verbatim">' + esc(r['原文片段(逐字)']) + '</div></details></td>' +
    '<td class="st ' + stCls + '">' + esc(st) + '</td>' +
    '<td class="st">' + esc(r['人工复核状态']) + '<div class="id">' + esc(r['放行状态']) + '</div></td>' +
  '</tr>';
}

const HEAD_HUMAN = [['#','3%'],['文档来源','12%'],['一级事件','15%'],['类型 / 时间','11%'],
                    ['相关属性','19%'],['一级事件原文','12%'],['二级阶段（几个 / 是什么）','20%'],['复核状态','8%']];
const HEAD_OFFICIAL = ['#','模型','文档','事件ID','一级事件名称','类型','核心过程','经历范围','逐字证据引文','原文片段','自动状态','人工结论'];

function humanStats() {
  const docs = uniq(HUMAN.map(r => r['文档编号']));
  const stages = HUMAN.reduce((n, r) => n + (r._stages || []).length, 0);
  const evSegs = HUMAN.reduce((n, r) => n + r['事件原文条数'], 0);
  const stageSegs = HUMAN.reduce((n, r) => n + (r._stages || []).reduce((m, s) => m + s.sources.length, 0), 0);
  return [['人工标注文档', docs.length], ['一级事件', HUMAN.length], ['二级阶段', stages],
          ['事件层原文挂接', evSegs], ['阶段层原文挂接', stageSegs]];
}

function officialStats() {
  return [['模型', uniq(OFFICIAL.map(r => r['模型'])).length],
          ['文档', uniq(OFFICIAL.map(r => r['文档编号'])).length],
          ['一级事件（候选）', OFFICIAL.length]];
}

function cards(list, cls) {
  $('cards').innerHTML = list.map(([k, v]) =>
    '<div class="card ' + cls + '"><div class="num">' + v + '</div><div class="lab">' + esc(k) + '</div></div>'
  ).join('');
}

function chipsHuman() {
  const c = {};
  HUMAN.forEach(r => { const t = r['事件类型(中文)']; c[t] = (c[t] || 0) + 1; });
  const sc = {};
  HUMAN.forEach(r => { const n = r._stages.length; const k = n ? '有二级阶段' : '无二级阶段'; sc[k] = (sc[k] || 0) + 1; });
  $('chips').innerHTML = '事件类型分布：' + Object.keys(c).sort().map(t =>
    '<span class="chip"><i style="background:' + (COLORS[t] || '#475569') + '"></i>' + esc(t) + ' ' + c[t] + '</span>'
  ).join(' ') + '　｜　' + Object.keys(sc).map(k =>
    '<span class="chip">' + esc(k) + ' ' + sc[k] + '</span>').join(' ');
}

function chipsOfficial() {
  const c = {};
  OFFICIAL.forEach(r => { const t = r['事件类型(中文)'] || '未标类型'; c[t] = (c[t] || 0) + 1; });
  $('chips').innerHTML = '事件类型分布：' + Object.keys(c).sort().map(t =>
    '<span class="chip"><i style="background:' + (COLORS[t] || '#475569') + '"></i>' + esc(t) + ' ' + c[t] + '</span>'
  ).join(' ');
}

function renderHuman() {
  const d = $('hDoc').value, t = $('hType').value, s = $('hStage').value,
        st = $('hStatus').value, k = $('hKey').value.trim().toLowerCase();
  const list = HUMAN.filter(r => {
    if (d && r['文档编号'] !== d) return false;
    if (t && r['事件类型(中文)'] !== t) return false;
    if (s === 'yes' && !r._stages.length) return false;
    if (s === 'no' && r._stages.length) return false;
    if (st && r['事件复核状态'] !== st) return false;
    if (k) {
      const hay = [r['文档标题'], r['受访者'], r['文档编号'], r['事件名称'], r['一级事件ID'],
                   r['核心过程'], r['参与者'], r['环境成分'], r['二级阶段清单'], r['边界说明']]
                   .concat(r._eventSources.map(s => s.text))
                   .concat(r._stages.flatMap(st => st.sources.map(s => s.text)))
                   .join(' ').toLowerCase();
      if (!hay.includes(k)) return false;
    }
    return true;
  });
  VISIBLE = list;
  $('hCnt').textContent = '显示 ' + list.length + ' / ' + HUMAN.length + ' 条一级事件';
  $('thead').innerHTML = '<tr>' + HEAD_HUMAN.map(([h, w]) => '<th style="width:' + w + '">' + h + '</th>').join('') + '</tr>';
  $('tb').innerHTML = list.length
    ? list.map(r => humanRow(r) + (OPEN.has(r['序号']) ? detailRow(r) : '')).join('')
    : '<tr><td colspan="8" class="muted">没有符合条件的事件，请放宽筛选。</td></tr>';
}

function renderOfficial() {
  const m = $('oModel').value, d = $('oDoc').value, t = $('oType').value,
        s = $('oScope').value, k = $('oKey').value.trim().toLowerCase();
  const list = OFFICIAL.filter(r =>
    (!m || r['模型'] === m) && (!d || r['文档编号'] === d) &&
    (!t || r['事件类型(中文)'] === t) && (!s || r['经历范围'] === s) &&
    (!k || [r['事件名称'], r['事件逐字证据引文'], r['原文片段(逐字)'], r['一级事件ID'], r['经历范围判定引文']]
              .join(' ').toLowerCase().includes(k))
  );
  $('oCnt').textContent = '显示 ' + list.length + ' / ' + OFFICIAL.length + ' 条';
  $('thead').innerHTML = '<tr>' + HEAD_OFFICIAL.map(h => '<th>' + h + '</th>').join('') + '</tr>';
  $('tb').innerHTML = list.length ? list.map(officialRow).join('')
    : '<tr><td colspan="12" class="muted">没有符合条件的事件，请放宽筛选。</td></tr>';
}

function switchView(v) {
  VIEW = v;
  const human = v === 'human';
  $('tbl').className = human ? 'human' : '';
  $('tabHuman').className = 'tab' + (human ? ' on human' : '');
  $('tabOfficial').className = 'tab' + (human ? '' : ' on');
  $('warnHuman').classList.toggle('hidden', !human);
  $('warnOfficial').classList.toggle('hidden', human);
  $('fHuman').classList.toggle('hidden', !human);
  $('fOfficial').classList.toggle('hidden', human);
  if (human) { cards(humanStats(), 'human'); chipsHuman(); renderHuman(); }
  else { cards(officialStats(), ''); chipsOfficial(); renderOfficial(); }
  $('foot').innerHTML = human
    ? '<b>字段口径</b>：每行 = 一条人工标注的「一级事件」。文档来源含标题／编号／受访者／访谈日期／原始语料文件；' +
      '相关属性含事件类型、时间、核心过程、参与者、环境、结果状态、事实性、置信度与边界说明。' +
      '「一级事件原文」按 <code>SourceAttachment.target_type=EVENT</code> 回取 <code>SourceSegment.verbatim_text</code>，' +
      '并按 <code>function</code> 标注用途；「二级阶段」按 <code>ProcessStage.stage_order</code> 排列，' +
      '点开任一行右侧的<b>「展开完整档案」</b>即可看到各阶段逐字原文与 <code>NEXT_STAGE.logic</code>。<br>' +
      '<b>数据来源</b>：<code>现行标注/neo4j_demo/import/*.csv</code>（由 6 份人工标注 Demo 合并而成，只读）；' +
      '配套可 Excel 打开的明细表：<code>导师查看_人工6份标注一览.csv</code>。<br>' +
      '<b>分享单条</b>：网址后加 <code>?open=3</code> 可直接展开第 3 条事件的完整档案；' +
      '<code>?view=official</code> 可直接打开正式结果视图。<br>' +
      '<b>提醒</b>：6 份为 <code>WORKFLOW_DEMO</code> 工作流演示样本，可作人工标注样例与方法展示，<b>不是正式测试金标准</b>；' +
      '两层原文允许双重挂接，片段数不可相加。'
    : '<b>字段口径</b>：每行 = 一条大模型文档级归并后的「一级事件」（<code>consolidated_output.document_events</code>）。' +
      '全部仍是 <code>MODEL_CANDIDATE</code>，本轮<b>没有</b>二级过程阶段。<br>' +
      '<b>数据来源</b>：<code>导师查看_事件一览.csv</code>（由 <code>scripts/build_mentor_overview.py</code> 从 <code>validated_json/&lt;模型目录&gt;/</code> 只读生成）。' +
      '按模型隔离，<code>cuc_deepseek</code> 与 <code>cuc_qwen</code> 结果请勿混读为一份标注。';
}

// 初始化筛选选项
fillSelect('hDoc', uniq(HUMAN.map(r => r['文档编号'])), '全部文档（6 份）');
fillSelect('hType', uniq(HUMAN.map(r => r['事件类型(中文)'])), '全部事件类型');
fillSelect('hStatus', uniq(HUMAN.map(r => r['事件复核状态'])), '全部复核状态');
fillSelect('oModel', uniq(OFFICIAL.map(r => r['模型'])), '全部模型');
fillSelect('oDoc', uniq(OFFICIAL.map(r => r['文档编号'])), '全部文档');
fillSelect('oType', uniq(OFFICIAL.map(r => r['事件类型(中文)'])), '全部类型');
fillSelect('oScope', uniq(OFFICIAL.map(r => r['经历范围'])), '全部范围');
['hDoc','hType','hStage','hStatus','hKey'].forEach(id => $(id).addEventListener('input', renderHuman));
['oModel','oDoc','oType','oScope','oKey'].forEach(id => $(id).addEventListener('input', renderOfficial));
// 支持 ?open=3,5 直接展开指定序号的完整档案，便于把单条事件直接分享给导师
const openParam = new URLSearchParams(location.search).get('open');
if (openParam) openParam.split(',').forEach(n => { const v = parseInt(n, 10); if (!isNaN(v)) OPEN.add(v); });
window.addEventListener('beforeprint', () => {
  if (VIEW === 'human') { VISIBLE.forEach(r => OPEN.add(r['序号'])); renderHuman(); }
  else document.querySelectorAll('details').forEach(d => d.open = true);
});
const viewParam = new URLSearchParams(location.search).get('view');
switchView(viewParam === 'official' ? 'official' : 'human');
</script>
</body>
</html>
"""


def write_html(human_rows, official_rows, path):
    colors = {}
    types = sorted({r["事件类型(中文)"] for r in human_rows if r["事件类型(中文)"]} |
                   {r.get("事件类型(中文)", "") for r in official_rows if r.get("事件类型(中文)")})
    for i, t in enumerate(types):
        colors[t] = PALETTE[i % len(PALETTE)]

    def js(data):
        return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")

    # 前端只用结构化字段取原文；CSV 专用长文本不重复塞进 HTML，避免页面体积翻倍。
    drop = {"事件原文(逐字)", "二级阶段原文(逐字)", "事件证据片段ID",
            "阶段证据片段ID", "备注", "_timeRows"}
    slim = [{k: v for k, v in r.items() if k not in drop} for r in human_rows]

    doc = (TEMPLATE
           .replace("__NOW__", datetime.now().strftime("%Y-%m-%d %H:%M"))
           .replace("__HUMAN__", js(slim))
           .replace("__OFFICIAL__", js(official_rows))
           .replace("__COLORS__", js(colors)))
    path.write_text(doc, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(CONS), help="输出目录（默认 document_consolidation/）")
    args = ap.parse_args()
    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    human = collect_human()
    official = collect_official()
    write_human_csv(human, out / CSV_NAME)
    write_html(human, official, out / HTML_NAME)

    stages = sum(len(r["_stages"]) for r in human)
    print(f"人工 6 份：{len({r['文档编号'] for r in human})} 份文档 / {len(human)} 条一级事件 / {stages} 个二级阶段")
    print(f"正式结果：{len(official)} 条 MODEL_CANDIDATE 事件（来自现有一览 CSV）")
    print("输出：")
    print(f"  {out / HTML_NAME}")
    print(f"  {out / CSV_NAME}")


if __name__ == "__main__":
    main()
