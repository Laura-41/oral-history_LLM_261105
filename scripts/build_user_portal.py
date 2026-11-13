#!/usr/bin/env python3
"""生成面向用户的口述史门户（单文件、离线双击可用）。

用法：
    python3 scripts/build_user_portal.py

输入：../现行标注/01_* ~ 06_* 的 18 张 CSV（只读，绝不改动）
输出：06_可视化原型/归途·口述史记忆馆.html

设计口径（2026-11-13 研究者拍板）：
  - 面向公众：AI 自然语言问答是主角，图谱是配角；不复述复杂原文访谈
  - 板块 A「问一问」：AI 对话 + 动态悬浮图谱同屏，按时间/地点/人物展开 + AI 反问
  - 板块 B「人生链路」：单人插画轨迹，逐站点击与小动画
  - 板块 C「轨迹交叉」：多人汇合→岔开，只画 6 份 Demo 中可核实的交集
  - 板块 D「口述史图谱」：科研工作台整体内嵌为本页的一部分（Shadow DOM，无 iframe / 外链）
  - 只接 6 份人工 Demo（词表 v1.0），不接大模型线、不展示双模型对照
  - 用户端不出现任何叙事跳跃度分数（指标只在内嵌工作台的研究视图与 CSV 中）
  - 问答为「本地检索 -> 因果链筛选 -> 逐字证据编排 -> 自然语言回答」演示，
    非真实 LLM；界面显式标注演示模式，并预留可插拔的答案引擎接口
  - 导师看板是持续更新的独立档案（人工 6 份 / 大模型 54 份两视图分开），
    保持独立 HTML + iframe，不内嵌；用 --sync-boards-only 单独刷新副本。

附加参数：
    python3 scripts/build_user_portal.py --sync-boards-only
    只把最新的导师看板原件同步成门户副本，不重建 归途·口述史记忆馆.html。
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_viz_prototype as viz  # noqa: E402  科研工作台资产（同源 6 份 Demo）

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT.parent / "现行标注"
OUT_DIR = ROOT / "06_可视化原型"
TEMPLATE = Path(__file__).with_name("user_portal_template.html")
OUT_HTML = OUT_DIR / "归途·口述史记忆馆.html"

# 导师看板（既有科研成果）：只读原件，生成门户适配副本放到 06_可视化原型/
MENTOR_DIR = ROOT / "04_54份正式语料批处理" / "document_consolidation"
MENTOR_BOARD = MENTOR_DIR / "导师查看_事件总看板.html"
MENTOR_OVERVIEW = MENTOR_DIR / "导师查看_事件一览.html"
MENTOR_OUT = OUT_DIR / "事件标注结果总看板.html"
MENTOR_OVERVIEW_OUT = OUT_DIR / "导师查看_事件一览.html"

# 蓝白数据后台 → 宣纸米白 + 朱红（只作用于 <style> 内，不动内嵌数据与脚本逻辑）
MENTOR_COLORS = {
    "#1a2230": "#2b241d", "#5b6676": "#7a6e5d", "#334155": "#3b3227",
    "#475569": "#6b5c48", "#64748b": "#8a7c66",
    "#f5f7fa": "#f6f1e7", "#e2e7ee": "#e3d9c4", "#e2e8f0": "#e3d9c4",
    "#cbd5e1": "#d8ccb2", "#eef2f7": "#efe7d6", "#eef1f5": "#ece2ce",
    "#fafbfe": "#faf6ea", "#f8fafc": "#f7f1e4", "#f1f5f9": "#efe8d8",
    "#f7fafc": "#f8f3e7", "#edf1f5": "#ece2ce",
    "#1d4ed8": "#973e31", "#0f766e": "#6f7f57", "#b45309": "#a8702a",
    "#f0fdfa": "#f2f5e9", "#99f6e4": "#cfdcb4", "#ecfdf5": "#edf3e4",
    "#a7f3d0": "#c8d8ae", "#065f46": "#4d6b3a", "#115e59": "#4d6b3a",
    "#fff7ed": "#fbf0dc", "#fed7aa": "#e8cda2", "#fffbeb": "#faf2de",
    "#fde68a": "#e6cf9a", "#92400e": "#8a5a1e", "#9a3412": "#8a3a20",
    "#eef2ff": "#f5efe2", "#3730a3": "#7a4a2a", "#c7d2fe": "#e0d2b8",
    "#d5f5ef": "#dce7cc", "#fbfffe": "#fffdf7", "#ecfeff": "#f2f5e9",
}
MENTOR_EXTRA_CSS = """
/* 门户适配：与「口述史图谱」科研成果板块同一套纸感语言 */
h1{font-family:"Songti SC","STSong",serif;color:#5a2a20;letter-spacing:.5px}
.wrap{max-width:1440px}
body{background:#f6f1e7}
.sub{color:#7a6e5d}
.card,.filters,.tablebox,.panel{border-radius:12px;box-shadow:0 2px 14px rgba(90,60,30,.05)}
.tab{border-radius:9px}
th{color:#5c4b36}
"""

TABLES = {
    "docs": "documents.csv",
    "events": "event_nodes.csv",
    "times": "event_times.csv",
    "stages": "process_stages.csv",
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
    "processes": "event_processes.csv",
    "stageNext": "stage_next.csv",
}

# 事件 -> 可爱小插图（依据事件名关键词，纯展示层，不改变标注数据）
ICON_RULES = [
    ("press", ["印书", "排字", "学徒", "罢工", "工厂", "失业"]),
    ("medic", ["伤员", "救护", "卫生", "卫训", "解剖", "医", "病房", "临床"]),
    ("cap", ["参军", "学兵", "军校", "炮兵", "教导", "训练", "补充队", "区队长", "中尉", "整编", "招募"]),
    ("book", ["师范", "教书", "任教", "毕业", "考入", "学习", "小学", "学校"]),
    ("flag", ["救亡会", "宣传", "游行", "示威", "组织", "集会", "誓师", "动员"]),
    ("train", ["逃难", "辗转", "撤离", "铁路", "渡", "行军", "北撤", "离晋", "过江"]),
    ("plow", ["放牛", "家务", "劳动", "农"]),
    ("house", ["家庭", "家人", "返乡", "回江阴", "交往", "哥哥"]),
    ("mountain", ["作战", "防御", "游击", "炮击", "惨案", "事变", "战争", "平型关", "前线", "集结"]),
    ("star", ["改编", "换装", "地下党", "思想", "倾向", "指挥", "主官"]),
]

CROSS_NOTES = {
    "1931": "这一年，陈海峰在上海荣华印书馆当排字学徒、开始接触进步思想；陈锐霆在九一八之后走上街头参加抗日游行示威。两条人生线还没相遇，却已经朝同一个方向转了弯。",
    "1937": "全面抗战爆发的这一年，陈海峰在八一三事变后随家人逃难回江阴，随后组织篁村人民抗日救亡会；杨永松所在的红军第一军团改编为八路军一一五师，誓师开赴平型关前线。一个在江南民间，一个在华北行伍。",
    "日军": "陈锐霆少年时与同伴观看日舰遭炮击、五三惨案期间在济南又险遭炮击；多年后陈海峰所在的第三支队在铜南繁一线执行对日防御与游击作战。同一个对手，出现在两个人的不同年纪。",
    "中国共产党": "陈锐霆在与王兴纲交往中逐渐形成亲共抗日倾向；杨永松所在部队在西安事变后北撤整训、准备全面抗战。两份口述各自提到这条线索，但彼此并不知情。",
}

# 三条人物线拉开色相并降低饱和，色弱可辨；旧金 #B08A4B 只留作装饰与 focus 环，
# 不再当人物线用（UI/UX 建议书 §3.1，2026-11-13）。与模板 LINE_STYLE 第三色保持一致。
PERSON_COLORS = {"陈海峰": "#A8402F", "陈锐霆": "#3E706C", "杨永松": "#5A4B8A"}

# 编辑精编答案：只在命中问句时启用，文字由研究者/模型依据逐字原话离线写定，
# 运行时零 API。{n} 是引用角标，n 对应下方 chain 的第 n 条事件；不改写标注数据。
# 其余「为什么」问题由前端 composeWhy() 依据 CAUSE / PURPOSE 字段与逐字原话现场编排。
CURATED_ANSWERS = [
    {
        "id": "crt-why-join-army",
        "why": True,
        "person": "陈锐霆",
        "words": ["参军", "当兵", "扛枪", "从军", "弃教"],
        "chain": [
            {"id": "CRT-E02", "role": "更早的伏笔", "label": "八岁遭日舰炮击 · 埋下仇日情绪"},
            {"id": "CRT-E04", "role": "直接前因", "label": "1928 济南五三惨案 · 险遭炮击"},
            {"id": "CRT-E05", "role": "关键决定", "label": "放弃教书 · 约同伴决定参军"},
            {"id": "CRT-E06", "role": "随后行动", "label": "辗转沪津保 · 被录取为学兵"},
        ],
        "paragraphs": [
            "先说结论：陈锐霆参军不是为了谋生，也不是被人招募，而是 1928 年在济南亲历五三惨案后，自己把教书的饭碗放下了。他当时从济南师范毕业，在青岛沧口小学当教员，月薪 28 块银洋，离家近、有寒暑假，「我自己本人也满意，家庭也比较满意」；可挨了那一炮之后他说「我这个思想就变了，就觉着教书把孩子什么时候能教大了，打日本了？……我自己去扛枪，我自己去打日本去」，于是约了三个同伴去当兵 {3}。那一炮是他在济南看老乡时落到跟前的，「差一点点就炸死了」，铁路也断了，只能沿小清河和海边绕道回乡 {2}。",
            "再往前还有一层。八岁那年他在即墨村外的高山上看日本兵舰，日军朝山脊打了几十发炮弹，没打中，他跑掉了；后来回忆说「这个时候就对日本人种下一个仇恨的种子吧，仇日」{1}。图谱把这段记作「形成强烈仇日情绪」，把 1928 年那次记作「五三惨案影响」，再用事件链接到「放弃教书并决定参军」——是同一个人在不同年纪被同一件事推着走，不是并列的五段经历。",
            "决定之后的路并不顺：几个人先到上海找同乡没找到，又乘船经天津转往保定；亲戚给安排了会计差事，他没去，看到学兵队后设法加入河北军事政治学校教导大队，才算真正当上兵 {4}。",
            "所以简短回答是：童年遭日军炮击埋下仇日情绪，1928 年五三惨案里再次险些被炸死成了直接触发，他判断教书等不及，于是弃教从军、辗转投考学兵。以上都出自他本人在访谈里的自述，年代、地点与因果词按标注原样保留，没有替他补没说过的动机。",
        ],
        "followups": [
            "五三惨案前后他还经历了什么？",
            "他后来怎么当上学兵的？",
            "陈锐霆为什么会反感不抵抗？",
            "三个人有什么交集？",
        ],
    },
]


def icon_for(name: str) -> str:
    for icon, words in ICON_RULES:
        if any(w in name for w in words):
            return icon
    return "star"


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def load_demos() -> list[dict]:
    demos = [
        d for d in sorted(glob.glob(str(DEMO_DIR / "[0-9][0-9]_*")))
        if os.path.isdir(d) and not os.path.basename(d).startswith("00_")
    ]
    if len(demos) != 6:
        raise SystemExit(f"预期 6 份人工 Demo，实际找到 {len(demos)} 份")
    data: dict[str, list[dict]] = {k: [] for k in TABLES}
    for demo in demos:
        for key, filename in TABLES.items():
            path = Path(demo) / filename
            if not path.exists():
                raise SystemExit(f"缺表：{path}")
            data[key].extend(read_csv(path))
    return data


def build(data: dict[str, list[dict]]) -> dict:
    docs = data["docs"]
    doc2person = {d["doc_id"]: d["interviewee"] for d in docs}
    doc2title = {d["doc_id"]: d["title"] for d in docs}
    people_order: list[str] = []
    for d in docs:
        if d["interviewee"] not in people_order:
            people_order.append(d["interviewee"])

    ent = {e["entity_id"]: e for e in data["entities"]}
    seg = {s["segment_id"]: s for s in data["segments"]}
    ev2doc = {e["event_id"]: e["doc_id"] for e in data["events"]}
    times = {t["event_id"]: t for t in data["times"]}

    circ = defaultdict(list)
    for r in data["circumstances"]:
        circ[r["event_id"]].append(r)
    part = defaultdict(list)
    for r in data["participants"]:
        part[r["event_id"]].append(r)
    stages = defaultdict(list)
    for r in data["stages"]:
        stages[r["event_id"]].append(r)
    att = defaultdict(list)
    for r in data["attachments"]:
        att[r["target_id"]].append(r)

    # 因果类情境（CAUSE / PURPOSE / MANNER）是「为什么」类问题的直接依据，
    # 旧版只取 LOCATION 与实体，把这些文本连同它指向的逐字原话一起丢掉了。
    cause_rows = defaultdict(list)
    for c in data["circumstances"]:
        if c["kind"] in ("CAUSE", "PURPOSE", "MANNER"):
            cause_rows[c["event_id"]].append(c)
    next_map = {r["source_event_id"]: r["target_event_id"] for r in data["eventNext"]}
    prev_map = {r["target_event_id"]: r["source_event_id"] for r in data["eventNext"]}

    stage2ev = {s["stage_id"]: s["event_id"] for s in data["stages"]}
    seg2events: dict[str, set[str]] = defaultdict(set)
    for a in data["attachments"]:
        sid = a["segment_id"]
        if a["target_type"] == "EVENT":
            seg2events[sid].add(a["target_id"])
        elif a["target_type"] == "STAGE" and a["target_id"] in stage2ev:
            seg2events[sid].add(stage2ev[a["target_id"]])

    def label_of(eid: str, fallback: str = "") -> str:
        return ent.get(eid, {}).get("canonical_name") or fallback or eid

    # ---- 事件：人生链路的「站」+ 问答的检索单元 ----
    events = []
    for e in data["events"]:
        eid = e["event_id"]
        t = times.get(eid, {})
        places, orgs, persons = [], [], []
        for c in circ[eid]:
            if c["kind"] == "LOCATION":
                v = c["value_text"] or label_of(c["entity_id"])
                if v and v not in places:
                    places.append(v)
            if c["entity_id"] and c["kind"] != "LOCATION":
                v = label_of(c["entity_id"], c["normalized_value"])
                if v and v not in orgs:
                    orgs.append(v)
        for p in part[eid]:
            v = p["entity_name"] or label_of(p["entity_id"])
            if p["entity_type"] == "PERSON":
                if v and v not in persons:
                    persons.append(v)
            elif v and v not in orgs:
                orgs.append(v)

        # 逐字证据：事件与其阶段挂接的片段，按原文顺序去重
        seen_sid, sids = set(), []
        for a in att[eid]:
            if a["segment_id"] in seg and a["segment_id"] not in seen_sid:
                seen_sid.add(a["segment_id"])
                sids.append(a["segment_id"])
        for s in stages[eid]:
            for a in att.get(s["stage_id"], []):
                if a["segment_id"] in seg and a["segment_id"] not in seen_sid:
                    seen_sid.add(a["segment_id"])
                    sids.append(a["segment_id"])
        sids.sort(key=lambda x: int(seg[x]["segment_order"] or 0))
        quotes = []
        for sid in sids[:3]:
            s = seg[sid]
            text = (s["verbatim_text"] or "").strip().replace("\r", "")
            if not text:
                continue
            if len(text) > 360:
                text = text[:360] + "…"
            quotes.append({
                "sid": sid,
                "text": text,
                "speaker": s["speaker_type"] or "受访者",
                "docTitle": doc2title.get(s["doc_id"], ""),
            })

        # 因果标注文本 + 它指向的逐字原话：回答「为什么」时优先引这几段
        cause_texts: dict[str, list[str]] = {"CAUSE": [], "PURPOSE": [], "MANNER": []}
        cause_sids: list[str] = []
        for c in cause_rows[eid]:
            v = (c["value_text"] or "").strip()
            if v and v not in cause_texts[c["kind"]]:
                cause_texts[c["kind"]].append(v)
            sid = c["evidence_segment_id"]
            if sid in seg and sid not in cause_sids:
                cause_sids.append(sid)
        cause_quotes = []
        for sid in cause_sids[:3]:
            s = seg[sid]
            text = (s["verbatim_text"] or "").strip().replace("\r", "")
            if not text:
                continue
            if len(text) > 360:
                text = text[:360] + "…"
            cause_quotes.append({
                "sid": sid,
                "text": text,
                "kind": next((c["kind"] for c in cause_rows[eid]
                              if c["evidence_segment_id"] == sid), ""),
                "docTitle": doc2title.get(s["doc_id"], ""),
            })

        st = sorted(stages[eid], key=lambda x: int(x["stage_order"] or 0))
        events.append({
            "id": eid,
            "person": doc2person[e["doc_id"]],
            "doc": e["doc_id"],
            "docTitle": doc2title[e["doc_id"]],
            "name": e["event_name"],
            "h": int(e["historical_order"] or 0),
            "n": int(e["narrative_order"] or 0),
            "icon": icon_for(e["event_name"]),
            "timeRaw": t.get("raw_text", ""),
            "timeStart": t.get("normalized_start", ""),
            "precision": t.get("precision", ""),
            "certainty": t.get("certainty", ""),
            "places": places[:3],
            "orgs": orgs[:5],
            "persons": persons[:5],
            "stages": [x["stage_summary"] for x in st if x["stage_summary"]][:6],
            "quotes": quotes,
            "causes": cause_texts["CAUSE"],
            "purposes": cause_texts["PURPOSE"],
            "manners": cause_texts["MANNER"],
            "causeQuotes": cause_quotes,
            "prev": prev_map.get(eid, ""),
            "next": next_map.get(eid, ""),
            "result": e.get("result_state", ""),
            "confidence": e.get("confidence", ""),
            "review": e.get("review_status", ""),
        })
    events.sort(key=lambda x: (people_order.index(x["person"]), x["doc"], x["h"]))

    people = [{
        "name": p,
        "color": PERSON_COLORS.get(p, "#8A6B4A"),
        "docs": [d["doc_id"] for d in docs if d["interviewee"] == p],
        "eventIds": [e["id"] for e in events if e["person"] == p],
    } for p in people_order]

    # ---- 图谱节点：只列「有用」的高频实体 ----
    ent_events: dict[str, set[str]] = defaultdict(set)
    for r in data["circumstances"]:
        if r["entity_id"]:
            ent_events[r["entity_id"]].add(r["event_id"])
    for r in data["participants"]:
        if r["entity_id"]:
            ent_events[r["entity_id"]].add(r["event_id"])
    for m in data["mentions"]:
        if m["entity_id"] and m["segment_id"] in seg2events:
            ent_events[m["entity_id"]].update(seg2events[m["segment_id"]])

    quotas = {"PLACE": 9, "ORGANIZATION": 6, "MILITARY_UNIT": 6,
              "PERSON": 6, "HISTORICAL_EVENT": 5}
    by_type: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for eid, evs in ent_events.items():
        e = ent.get(eid)
        if not e or e["entity_type"] not in quotas:
            continue
        name = (e["canonical_name"] or "").strip()
        if not name or len(name) > 13:
            continue
        by_type[e["entity_type"]].append((len(evs), eid))
    nodes = []
    for typ, quota in quotas.items():
        for weight, eid in sorted(by_type[typ], key=lambda x: (-x[0], x[1]))[:quota]:
            e = ent[eid]
            evs = sorted(ent_events[eid], key=lambda x: (people_order.index(
                next((v["person"] for v in events if v["id"] == x), people_order[0])), x))
            nodes.append({
                "id": eid,
                "name": e["canonical_name"],
                "type": typ,
                "weight": weight,
                "eventIds": evs[:14],
                "people": sorted({doc2person[ev2doc[x]] for x in evs if x in ev2doc}),
            })

    aliases = [{"t": a["alias_text"], "id": a["entity_id"]}
               for a in data["aliases"] if a.get("alias_text")]

    # ---- 交叉：只保留自动检出的真实共现 ----
    cross: list[dict] = []
    year_people: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for e in events:
        m = re.match(r"^(\d{4})", e["timeStart"] or "")
        if m:
            year_people[m.group(1)][e["person"]].append(e["id"])
    for y, pm in sorted(year_people.items()):
        if len(pm) > 1:
            cross.append({
                "id": "Y" + y, "label": y, "kind": "同一个年代", "kindType": "YEAR",
                "note": CROSS_NOTES.get(y, f"{y} 年前后，" + "、".join(pm) + "的经历都留下了记录。"),
                "people": sorted(pm),
                "eventIds": [eid for p in sorted(pm) for eid in pm[p]][:10],
            })
    ent_people: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for eid, doc in ev2doc.items():
        p = doc2person[doc]
        ids = {c["entity_id"] for c in circ[eid] if c["entity_id"]}
        ids |= {x["entity_id"] for x in part[eid] if x["entity_id"]}
        for x in ids:
            x_people = ent_people[x][p]
            x_people.add(eid)
    for eid, pm in ent_people.items():
        if len(pm) <= 1:
            continue
        name = label_of(eid)
        if len(name) > 12:
            continue
        kind = (ent.get(eid, {}).get("entity_type") or "OTHER")
        cross.append({
            "id": "E" + eid, "label": name,
            "kind": {"MILITARY_UNIT": "共同的对手 / 部队", "ORGANIZATION": "共同的组织",
                     "PLACE": "同一个地方", "HISTORICAL_EVENT": "同一桩大事"}.get(kind, "共同的线索"),
            "kindType": kind,
            "note": CROSS_NOTES.get(name, "、".join(sorted(pm)) + "的口述里都提到「" + name + "」。"),
            "people": sorted(pm),
            "eventIds": sorted({x for s in pm.values() for x in s})[:10],
        })
    # 定制文案优先排前，其余按标签排
    priority = {"1931": 0, "1937": 1, "日军": 2, "中国共产党": 3}
    cross.sort(key=lambda c: (priority.get(c["label"], 9), c["label"]))

    stats = {
        "docs": len(docs), "events": len(events), "stages": len(data["stages"]),
        "segments": len(data["segments"]), "attachments": len(data["attachments"]),
        "entities": len(data["entities"]), "mentions": len(data["mentions"]),
        "people": len(people), "nodes": len(nodes), "crosses": len(cross),
    }
    return {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "scope": "6 份人工标注 Demo · 词表 v1.0",
            "mentorFile": "事件标注结果总看板.html",
            "mentorOverviewFile": "导师查看_事件一览.html",
            "note": "面向公众的交互原型；默认离线回答（检索→因果链筛选→逐字证据编排），"
                    "可通过本地代理切换真实大模型，引用回链格式不变",
        },
        "docs": [{"id": d["doc_id"], "title": d["title"], "person": d["interviewee"],
                  "date": d["interview_date"], "visit": d["visit_no"]} for d in docs],
        "people": people, "events": events, "nodes": nodes, "aliases": aliases,
        "crosses": cross, "stats": stats, "answerBook": CURATED_ANSWERS,
    }


def _mentor_theme(html: str) -> str:
    """只改 <style> 里的配色，内嵌数据、表格逻辑、筛选器与云端回退一律不动。"""
    m = re.search(r"(<style[^>]*>)(.*?)(</style>)", html, re.S)
    if not m:
        return html
    css = m.group(2).replace("--panel:#fff;", "--panel:#fffcf5;")
    pattern = re.compile(
        "|".join(re.escape(k) for k in sorted(MENTOR_COLORS, key=len, reverse=True)), re.I
    )
    css = pattern.sub(lambda x: MENTOR_COLORS.get(x.group(0).lower(), x.group(0)), css)
    css += MENTOR_EXTRA_CSS
    return html[: m.start(2)] + css + html[m.end(2) :]


def sync_mentor_boards() -> None:
    """把导师看板迁入门户目录（生成副本，原件保持只读、不改动）。"""
    if not MENTOR_BOARD.exists():
        print("提示：未找到导师看板原件，跳过迁移；D 板块的其他内容不受影响。")
        return
    board = _mentor_theme(MENTOR_BOARD.read_text(encoding="utf-8"))
    board = board.replace(
        "⚠ 云端 SDK 未加载（需要联网加载 CDN）。当前展示页面内嵌快照，未使用云端数据。",
        "☁ 当前离线查看：展示页面内嵌的标注快照（联网时会自动核对云端清单）。",
    )
    MENTOR_OUT.write_text(board, encoding="utf-8")
    print(f"已迁移 {MENTOR_OUT.name}  ({MENTOR_OUT.stat().st_size / 1024:.0f} KB，主题适配副本)")
    if MENTOR_OVERVIEW.exists():
        overview = _mentor_theme(MENTOR_OVERVIEW.read_text(encoding="utf-8"))
        # 门户目录里的总看板叫「事件标注结果总看板.html」，保持早期单表看板的回链不断
        overview = overview.replace(
            'href="导师查看_事件总看板.html"', 'href="事件标注结果总看板.html"'
        )
        MENTOR_OVERVIEW_OUT.write_text(overview, encoding="utf-8")
        print(f"已迁移 {MENTOR_OVERVIEW_OUT.name}  ({MENTOR_OVERVIEW_OUT.stat().st_size / 1024:.0f} KB，回链已改写)")


def main() -> None:
    ap = argparse.ArgumentParser(description="生成面向用户的口述史门户")
    ap.add_argument("--sync-boards-only", action="store_true",
                    help="只刷新导师看板副本，不重建门户主页面")
    args = ap.parse_args()

    if not DEMO_DIR.is_dir():
        raise SystemExit(f"找不到人工标注目录：{DEMO_DIR}")
    if not TEMPLATE.exists():
        raise SystemExit(f"找不到页面模板：{TEMPLATE}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sync_mentor_boards()
    if args.sync_boards_only:
        print("已只刷新导师看板副本；门户主页面未改动。")
        return

    data = load_demos()
    payload = build(data)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    raw = raw.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    assets = viz.bench_assets(data)

    html = TEMPLATE.read_text(encoding="utf-8")
    injections = {
        "/*__DATA__*/": "const DB = " + raw + ";",
        "/*__BENCH_CSS__*/": assets["css"],
        "/*__BENCH_HTML__*/": assets["markup"],
        "/*__BENCH_DATA__*/": assets["db_json"],
        "/*__BENCH_APP__*/": assets["app"],
    }
    for marker, value in injections.items():
        if marker not in html:
            raise SystemExit(f"模板缺少占位符 {marker}")
        html = html.replace(marker, value)
    OUT_HTML.write_text(html, encoding="utf-8")

    s = payload["stats"]
    print(f"已生成 {OUT_HTML}  ({OUT_HTML.stat().st_size / 1024:.0f} KB)")
    print("数据规模：" + " / ".join(f"{k} {v}" for k, v in s.items()))
    print("交叉点：" + "、".join(c["label"] for c in payload["crosses"]))
    print("科研工作台：已内嵌（Shadow DOM），不再产出独立 HTML")


if __name__ == "__main__":
    main()
