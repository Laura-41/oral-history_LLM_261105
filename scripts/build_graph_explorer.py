#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""口述史 60 份图谱 · 交叉关系查询器（自包含 HTML 生成器）

只读 05_合并与Neo4j/import_all60/*.csv，产出 06_可视化原型/图谱交叉关系查询.html。
口径要点（与现行图谱 all60-v1 一致，勿改）：
  * documents.doc_id 是语料 ID（如 YYS-04）；BATCH0X-DOC0Y 只出现在 event_id / segment_id。
  * 一级节点 = EventNode（479），二级节点 = ProcessStage（1834），HAS_STAGE 直连。
  * 6 份 WORKFLOW_DEMO/CONFIRMED 与 54 份 BATCH_APPLICATION/MODEL_CANDIDATE 分开，
    两类统计不可相加；生平按 DEMO- 前缀；只有 SourceAttachment.function=EVIDENCE 可作史实依据。
  * 原库边忠实于 import.cypher；展示层另加一条派生边 MENTIONED_IN_DOC（虚线、明确标注）。
  * 不改动任何 CSV / 提示词 / Schema / 既有图谱资产。
"""
from pathlib import Path
import csv, json, collections

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / '05_合并与Neo4j' / 'import_all60'
OUT = ROOT / '06_可视化原型' / '图谱交叉关系查询.html'


def rd(name):
    with open(SRC / name, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def jd(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')


# ---------------------------------------------------------------- 节点与边
nodes = {}          # id -> [id, label, kind, role, extra]
edges = []          # [source, target, type, label, extra]


def add(nid, label, kind, role='', extra=None):
    if nid in nodes:
        if extra:
            nodes[nid][4].update({k: v for k, v in extra.items() if v and not nodes[nid][4].get(k)})
        return
    nodes[nid] = [nid, (label or nid)[:40], kind, role, extra or {}]


def link(s, t, typ, label='', ex=None):
    # 边标签不落盘：由前端按关系类型 + ex 现算，避免每条边重复一段中文。
    ex = {k: v for k, v in (ex or {}).items() if v and k != 'hide'}
    edges.append([s, t, typ, ex])


def short(s, n=18):
    return s if len(s) <= n else s[:n - 1] + '…'


ENTITY_KIND = {
    'PERSON': 'person', 'PLACE': 'place', 'MILITARY_UNIT': 'unit',
    'ORGANIZATION': 'org', 'HISTORICAL_EVENT': 'hist',
    'PUBLICATION': 'pub', 'OTHER': 'other',
}

docs = rd('documents.csv')
role_of_doc = {r['doc_id']: ('demo' if r['data_role'] == 'WORKFLOW_DEMO' else 'official') for r in docs}
person_of_doc = {r['doc_id']: r['interviewee'] for r in docs}

for r in docs:
    add('d:' + r['doc_id'], r['title'], 'doc', role_of_doc[r['doc_id']],
        {'受访者': r['interviewee'], '批次': r['visit_no'], '数据角色': r['data_role'],
         '复核': r['review_status'], '字符数': r['total_characters']})

entities = rd('entities.csv')
ent_by_id = {r['entity_id']: r for r in entities}
for r in entities:
    kind = ENTITY_KIND.get(r['entity_type'], 'other')
    extra = {'实体类型': r['entity_type'], '子类': r['entity_subtype'],
             '权威状态': r['authority_status'], '置信度': r['confidence']}
    if r['description']:
        extra['说明'] = r['description']
    add('en:' + r['entity_id'], r['canonical_name'], kind, 'unknown', extra)

subjects = rd('person_subjects.csv')
for r in subjects:
    nid = 'en:' + r['person_entity_id']
    if nid in nodes:
        nodes[nid][2] = 'subject'
        nodes[nid][4]['主体'] = '传记主体（BiographicalSubject）'
        nodes[nid][4]['生平状态'] = r['biography_status']

events = rd('event_nodes.csv')
ev2doc = {r['event_id']: r['doc_id'] for r in events}
for r in events:
    d = r['doc_id']
    add('ev:' + r['event_id'], r['event_name'], 'event', role_of_doc.get(d, 'unknown'),
        {'事件名': r['event_name'][:120], '所属文档': d, '受访者': person_of_doc.get(d, ''),
         '叙述序': r['narrative_order'], '历史序': r['historical_order'],
         '事实性': r['factuality'], '置信度': r['confidence'], '复核': r['review_status']})
    link('d:' + d, 'ev:' + r['event_id'], 'HAS_EVENT', '文档 → 一级事件')

stages = rd('process_stages.csv')
st2ev = {r['stage_id']: r['event_id'] for r in stages}
for r in stages:
    e = r['event_id']
    d = ev2doc.get(e, '')
    add('st:' + r['stage_id'], r['stage_summary'] or r['process_text'], 'stage',
        role_of_doc.get(d, 'unknown'),
        {'阶段': r['stage_order'], '摘要': (r['stage_summary'] or '')[:120],
         '过程原文': (r['process_text'] or '')[:160],
         '所属事件': e, '置信度': r['confidence'], '复核': r['review_status']})
    link('ev:' + e, 'st:' + r['stage_id'], 'HAS_STAGE', '一级 → 二级阶段')

episodes = rd('life_episodes.csv')
ep2src = collections.defaultdict(list)
for r in rd('life_episode_sources.csv'):
    ep2src[r['episode_id']].append(r['event_id'])
for r in episodes:
    eid = r['episode_id']
    base = 'demo' if eid.startswith('DEMO-') else 'official'
    src_roles = {role_of_doc.get(ev2doc.get(e, ''), '') for e in ep2src.get(eid, [])}
    src_roles.discard('')
    role = base if not src_roles else ('mixed' if len(src_roles) > 1 or base not in src_roles else base)
    add('ep:' + eid, r['episode_name'], 'episode', role,
        {'生平片段': r['episode_name'][:120], '主体': r['person_entity_id'], '生平序': r['life_order'],
         '起始': r['normalized_start'], '终止': r['normalized_end'],
         '范围': r['episode_scope'], '精度': r['precision'], '复核': r['review_status']})
    link('en:' + r['person_entity_id'], 'ep:' + eid, 'HAS_LIFE_EPISODE', '人物 → 生平片段')

segments = rd('source_segments.csv')
seg_by_id = {r['segment_id']: r for r in segments}
SEG = {r['segment_id']: [r['doc_id'], r['segment_order'], r['verbatim_text']] for r in segments}
for r in segments:
    sid = r['segment_id']
    d = r['doc_id']
    add('sg:' + sid, r['verbatim_text'] or sid, 'segment', role_of_doc.get(d, 'unknown'),
        {'片段': sid, '所属文档': d, '类型': r['segment_type'],
         '说话人': r['speaker_id'], '复核': r['review_status']})
    link('d:' + d, 'sg:' + sid, 'HAS_SEGMENT', '文档 → 原文片段', {'hide': 1})
    if r['speaker_id'] and 'en:' + r['speaker_id'] in nodes:
        link('sg:' + sid, 'en:' + r['speaker_id'], 'SPOKEN_BY', '说话人', {'hide': 1})

for r in rd('event_processes.csv'):
    pid = r['process_id']
    add('pr:' + pid, short(r['process_normalized'] or r['process_text']), 'process',
        role_of_doc.get(ev2doc.get(r['event_id'], ''), 'unknown'),
        {'过程': r['process_normalized'], '类型': r['event_type_id']})
    link('ev:' + r['event_id'], 'pr:' + pid, 'HAS_PROCESS', '事件 → 过程', {'hide': 1})
    if r['evidence_segment_id']:
        link('pr:' + pid, 'sg:' + r['evidence_segment_id'], 'SUPPORTED_BY', '过程依据',
             {'e': r['evidence_segment_id'], 'hide': 1})

for r in rd('event_times.csv'):
    tid = r['event_time_id']
    e = r['event_id']
    add('tm:' + tid, r['raw_text'] or '时间', 'time', role_of_doc.get(ev2doc.get(e, ''), 'unknown'),
        {'原词': r['raw_text'], '起始': r['normalized_start'], '终止': r['normalized_end'],
         '精度': r['precision'], '确定性': r['certainty'], '来源': r['source_status']})
    link('ev:' + e, 'tm:' + tid, 'HAS_TIME', '事件 → 时间')
    if r['evidence_segment_id']:
        link('tm:' + tid, 'sg:' + r['evidence_segment_id'], 'SUPPORTED_BY', '时间依据',
             {'e': r['evidence_segment_id'], 'hide': 1})

for r in rd('time_expressions.csv'):
    tid = r['time_expression_id']
    add('tx:' + tid, r['raw_text'] or '时间表达', 'time',
        role_of_doc.get(seg_by_id.get(r['segment_id'], {}).get('doc_id', ''), 'unknown'),
        {'原词': r['raw_text'], '类型': r['expression_type'], '精度': r['precision']})
    link('sg:' + r['segment_id'], 'tx:' + tid, 'HAS_TIME_EXPRESSION', '片段 → 时间表达',
         {'hide': 1})

for r in rd('event_circumstances.csv'):
    cid = r['circumstance_id']
    e = r['event_id']
    add('ci:' + cid, short(r['value_text'] or r['kind']), 'circum',
        role_of_doc.get(ev2doc.get(e, ''), 'unknown'),
        {'情境类型': r['kind'], '原值': r['value_text'], '归一值': r['normalized_value'],
         '置信度': r['confidence']})
    link('ev:' + e, 'ci:' + cid, 'HAS_CIRCUMSTANCE', '事件 → 情境·' + r['kind'],
         {'kind': r['kind'], 'e': r['evidence_segment_id']})
    if r['entity_id'] and 'en:' + r['entity_id'] in nodes:
        link('ci:' + cid, 'en:' + r['entity_id'], 'REFERS_TO', '情境指向实体',
             {'e': r['evidence_segment_id']} if r['evidence_segment_id'] else {})

for r in rd('entity_mentions.csv'):
    mid = r['mention_id']
    eid = r['entity_id']
    add('mn:' + mid, r['mention_text'] or mid, 'mention',
        role_of_doc.get(seg_by_id.get(r['segment_id'], {}).get('doc_id', ''), 'unknown'),
        {'提及': r['mention_text'], '功能': r['mention_function'], '来源': r['source_status']})
    link('sg:' + r['segment_id'], 'mn:' + mid, 'HAS_MENTION', '片段 → 提及', {'hide': 1})
    if 'en:' + eid in nodes:
        link('mn:' + mid, 'en:' + eid, 'MENTIONS', '提及 → 实体', {'hide': 1})

for r in rd('entity_aliases.csv'):
    aid = r['alias_id']
    add('al:' + aid, r['alias_text'], 'alias', nodes.get('en:' + r['entity_id'], ['', '', '', 'unknown'])[3],
        {'别名类型': r['alias_type'], '置信度': r['confidence']})
    link('al:' + aid, 'en:' + r['entity_id'], 'ALIAS_OF', '别名 → 实体',
         {'e': r['evidence_segment_id']} if r['evidence_segment_id'] else {})

for r in rd('entity_relations.csv'):
    if 'en:' + r['source_entity_id'] not in nodes or 'en:' + r['target_entity_id'] not in nodes:
        continue
    link('en:' + r['source_entity_id'], 'en:' + r['target_entity_id'], 'RELATED_TO',
         r['relation_type'], {'rt': r['relation_type'], 'role': r['role_label'],
                              'e': r['evidence_segment_id'], 'status': r['source_status']})

# 事件参与者（677 条 UNRESOLVED 不在 entities.csv，建为独立的「未解析参与者」节点）
participants = rd('event_participants.csv')
for r in participants:
    eid = r['entity_id']
    if eid.startswith('UNRESOLVED'):
        nid = 'ur:' + eid
        add(nid, r['entity_name'] or eid, 'unresolved',
            role_of_doc.get(ev2doc.get(r['event_id'], ''), 'unknown'),
            {'名称': r['entity_name'], '类型': r['entity_type'], '状态': '未解析（不在实体表）'})
    else:
        nid = 'en:' + eid
        if nid not in nodes:
            continue
    link('ev:' + r['event_id'], nid, 'HAS_PARTICIPANT',
         '参与·' + (r['role'] or ''), {'role': r['role'], 'e': r['evidence_segment_id']})

for r in rd('stage_next.csv'):
    link('st:' + r['source_stage_id'], 'st:' + r['target_stage_id'], 'NEXT_STAGE',
         '阶段顺序·' + (r['logic'] or ''), {'logic': r['logic'], 'e': r['evidence_segment_id']})
for r in rd('event_next.csv'):
    link('ev:' + r['source_event_id'], 'ev:' + r['target_event_id'], 'NEXT',
         '事件链·' + (r['basis'] or ''), {'basis': r['basis'], 'status': r['review_status']})
for r in rd('life_episode_sources.csv'):
    link('ep:' + r['episode_id'], 'ev:' + r['event_id'], 'SUPPORTED_BY_EVENT',
         '生平依据事件', {'role': r['source_role']})
for r in rd('life_episode_next.csv'):
    link('ep:' + r['source_episode_id'], 'ep:' + r['target_episode_id'], 'BIOGRAPHICAL_NEXT',
         '生平顺序', {'overlap': r['overlap_possible'], 'basis': r['basis']})
for r in rd('narrated_contexts.csv'):
    link('en:' + r['person_entity_id'], 'ev:' + r['event_id'], 'NARRATED_CONTEXT',
         '叙述语境', {'order': r['context_order']})
for r in rd('document_persons.csv'):
    link('d:' + r['doc_id'], 'en:' + r['person_entity_id'], 'INTERVIEW_OF',
         '访谈对象', {'status': r['review_status']})

# 逐字证据索引（仅 function=EVIDENCE 可作史实依据）
EV = collections.defaultdict(list)
PREFIX = {'DOCUMENT': 'd:', 'EVENT': 'ev:', 'STAGE': 'st:'}
for r in rd('source_attachments.csv'):
    if r['function'] != 'EVIDENCE':
        continue
    nid = PREFIX.get(r['target_type'], '') + r['target_id']
    if nid in nodes:
        EV[nid].append(r['segment_id'])

MENT = collections.defaultdict(list)
for r in rd('entity_mentions.csv'):
    MENT['en:' + r['entity_id']].append(r['segment_id'])

# ---------------------------------------------------------------- 交叉索引
cross_people = collections.defaultdict(set)
cross_docs = collections.defaultdict(set)
cross_events = collections.defaultdict(set)
for r in rd('entity_mentions.csv'):
    s = seg_by_id.get(r['segment_id'])
    eid = r['entity_id']
    if s and 'en:' + eid in nodes:
        cross_docs[eid].add(s['doc_id'])
        cross_people[eid].add(person_of_doc.get(s['doc_id'], ''))
for r in participants:
    eid = r['entity_id']
    d = ev2doc.get(r['event_id'])
    if d and 'en:' + eid in nodes:
        cross_docs[eid].add(d)
        cross_people[eid].add(person_of_doc.get(d, ''))
        cross_events[eid].add(r['event_id'])
# 交叉索引只用 entity_mentions 与 event_participants 两条路径。
# 已知数据坑（2026-11-16 21:40 查询层发现）：同一地点存在多个实体 ID，且部分
# LOCATION 成分的 REFERS_TO / entity_id 错指（如 P003「上海」被临沂文本错指），
# 故不把 event_circumstances.entity_id 计入交叉；地点交叉以 Circumstance 文本为锚。

# 实体数据角色：由它出现的文档集合推断（跨两类 = mixed）
for eid, n in ent_by_id.items():
    nid = 'en:' + eid
    ds = cross_docs.get(eid, set())
    rs = {role_of_doc.get(d, '') for d in ds} - {''}
    nodes[nid][3] = ('mixed' if len(rs) > 1 else rs.pop()) if rs else 'unknown'

# 展示层派生边：实体 ↔ 文档（聚合自 entity_mentions），虚线，非 Neo4j 原库关系
derived_pairs = set()
for r in rd('entity_mentions.csv'):
    s = seg_by_id.get(r['segment_id'])
    eid = r['entity_id']
    if s and 'en:' + eid in nodes:
        pair = ('en:' + eid, 'd:' + s['doc_id'])
        if pair not in derived_pairs:
            derived_pairs.add(pair)
            link(pair[0], pair[1], 'MENTIONED_IN_DOC', '提及于文档', {'derived': 1})

CROSS = {}
for eid in ent_by_id:
    p = sorted(x for x in cross_people.get(eid, set()) if x)
    d = sorted(cross_docs.get(eid, set()))
    v = sorted(cross_events.get(eid, set()))
    if len(d) >= 2 or len(p) >= 2:
        CROSS['en:' + eid] = [len(p), len(d), len(v), p, d, v]

# 只保留两端存在的边；落盘时把长 ID 换成节点下标，载入 HTML 后再还原
valid = set(nodes)
edges = [e for e in edges if e[0] in valid and e[1] in valid]
idx = {nid: i for i, nid in enumerate(nodes)}
edges_packed = [[idx[e[0]], idx[e[1]], e[2], e[3]] for e in edges]

META = {
    'docs': len(docs), 'events': len(events), 'stages': len(stages),
    'entities': len(entities), 'episodes': len(episodes), 'segments': len(segments),
    'nodes': len(nodes), 'edges': len(edges),
    'crossPeople': sum(1 for v in CROSS.values() if v[0] >= 2),
    'crossDocs': len(CROSS),
    'edgeTypes': collections.Counter(e[2] for e in edges),
    'kindCounts': collections.Counter(n[2] for n in nodes.values()),
}
META['edgeTypes'] = dict(META['edgeTypes'])
META['kindCounts'] = dict(META['kindCounts'])

print('节点', len(nodes), '边', len(edges), '边类型', len(META['edgeTypes']))
print('跨≥2位受访者', META['crossPeople'], '跨≥2份文档', META['crossDocs'])
print('边类型分布', META['edgeTypes'])

HTML = r'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>口述史图谱 · 交叉关系查询</title>
<style>
:root{--paper:#F5F1E7;--paper2:#EDE6D6;--ink:#2B2A28;--ink2:#5E5A52;--line:#CFC5B2;--zhu:#A8322A;--zhu2:#8C2F27}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:"Songti SC","Noto Serif CJK SC","Source Han Serif SC",SimSun,serif;
 background-image:radial-gradient(rgba(120,105,80,.045) 1px,transparent 1px);background-size:7px 7px}
header{padding:18px 26px 12px;border-bottom:2px double var(--line);position:relative}
h1{margin:0;font-size:23px;letter-spacing:3px;font-weight:600}
.sub{color:var(--ink2);font-size:12px;margin-top:6px;line-height:1.7}
.stamp{position:absolute;right:30px;top:20px;width:52px;height:52px;border:2px solid var(--zhu);color:var(--zhu);
 display:flex;align-items:center;justify-content:center;font-size:17px;letter-spacing:2px;border-radius:5px;opacity:.8;transform:rotate(-7deg)}
.stats{display:flex;gap:9px;flex-wrap:wrap;margin-top:10px}
.stat{background:rgba(255,255,255,.55);border:1px solid var(--line);padding:3px 9px;font-size:11px;color:var(--ink2)}
.stat b{color:var(--zhu2);font-size:13px;font-family:Georgia,serif}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:10px 26px;border-bottom:1px solid var(--line);background:rgba(255,255,255,.4)}
.tab{border:1px solid var(--line);background:transparent;padding:6px 13px;font-size:13px;cursor:pointer;color:var(--ink2);font-family:inherit}
.tab.on{background:var(--zhu2);color:#F7F1E4;border-color:var(--zhu2)}
.bar input,.bar select{border:1px solid var(--line);background:#FCFAF3;padding:6px 8px;font-size:12px;color:var(--ink);font-family:inherit}
.bar label{font-size:12px;color:var(--ink2)}
.sep{width:1px;height:22px;background:var(--line);margin:0 3px}
#searchWrap{position:relative}
#suggest{position:absolute;top:34px;left:0;z-index:30;background:#FCFAF3;border:1px solid var(--line);box-shadow:0 6px 18px rgba(60,50,35,.15);max-height:290px;overflow:auto;min-width:310px;display:none}
#suggest div{padding:5px 9px;font-size:12px;cursor:pointer;border-bottom:1px solid #F0EADC}
#suggest div:hover{background:#F0E7D5}
#suggest em{font-style:normal;color:var(--ink2);font-size:10px;margin-left:6px}
main{display:flex;height:calc(100vh - 190px);min-height:520px}
#stage{flex:1;position:relative;overflow:hidden;background:rgba(255,255,255,.22)}
#stage:after{content:"口述史 · 60 份语料图谱";position:absolute;right:22px;bottom:14px;color:rgba(90,80,65,.16);font-size:20px;letter-spacing:4px;pointer-events:none}
svg{width:100%;height:100%;display:block;cursor:grab}
svg.drag{cursor:grabbing}
aside{width:330px;border-left:1px solid var(--line);overflow:auto;background:rgba(255,255,255,.45);padding:0 0 24px}
.sec{border-bottom:1px solid var(--line);padding:11px 14px}
.sec h3{margin:0 0 8px;font-size:13px;letter-spacing:1px;color:var(--zhu2);border-left:3px solid var(--zhu);padding-left:8px}
.chip{display:inline-flex;align-items:center;gap:5px;font-size:11px;border:1px solid var(--line);padding:3px 7px;margin:2px 3px 2px 0;cursor:pointer;background:#FCFAF3;user-select:none}
.chip.off{opacity:.38;text-decoration:line-through}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.note{font-size:11px;color:var(--ink2);line-height:1.65}
.kv{font-size:12px;line-height:1.75;margin:2px 0}
.kv b{color:var(--ink2);font-weight:400;display:inline-block;min-width:64px}
.quote{background:#FBF7EC;border-left:2px solid var(--zhu);padding:6px 9px;font-size:11.5px;line-height:1.7;margin:5px 0;color:#403B33}
.quote small{color:var(--ink2);display:block;margin-top:3px;font-size:10px}
.edgeItem{font-size:11.5px;padding:4px 6px;border-bottom:1px dashed var(--line);cursor:pointer;line-height:1.5}
.edgeItem:hover{background:#F1E9D8}
.edgeItem span{color:var(--zhu2);font-family:Georgia,serif;font-size:10.5px}
.hot{font-size:11.5px;padding:4px 6px;border-bottom:1px dashed var(--line);cursor:pointer;display:flex;justify-content:space-between;gap:6px}
.hot:hover{background:#F1E9D8}
.hot b{font-weight:400;color:var(--ink)}
.hot i{font-style:normal;color:var(--zhu2);font-family:Georgia,serif;white-space:nowrap}
.listRow{font-size:11.5px;padding:4px 6px;border-bottom:1px dashed var(--line);cursor:pointer;display:flex;justify-content:space-between;gap:6px}
.listRow:hover{background:#F1E9D8}
.listRow b{font-weight:400;color:var(--ink)}
.listRow i{font-style:normal;color:var(--zhu2);font-family:Georgia,serif;white-space:nowrap}
#status{position:absolute;left:14px;bottom:12px;font-size:11px;color:var(--ink2);background:rgba(250,246,236,.9);border:1px solid var(--line);padding:5px 9px}
#empty{position:absolute;inset:0;display:none;align-items:center;justify-content:center;font-size:14px;color:var(--ink2)}
.nlabel{font-size:11px;fill:#2B2A28;paint-order:stroke;stroke:#F5F1E7;stroke-width:3px;stroke-linejoin:round}
.nlabel.minor{display:none}
g[data-id]:hover .nlabel.minor{display:block}
body.show-all .nlabel.minor{display:block}
aside select,aside input{border:1px solid var(--line);background:#FCFAF3;padding:4px 6px;font-size:11px;color:var(--ink);font-family:inherit;min-width:0}
#listPager .tab{padding:2px 8px;font-size:11px}
.nlabel.major{font-weight:600;font-size:12px}
.elabel{font-size:9px;fill:#6B655A;paint-order:stroke;stroke:#F5F1E7;stroke-width:3px}
.dim{opacity:.13}
.sel{stroke:var(--zhu2);stroke-width:3px}
</style></head><body>
<header>
 <div class="stamp">图谱</div>
 <h1>口述史图谱 · 交叉关系查询</h1>
 <div class="sub">一级节点 = EventNode（事件）｜二级节点 = ProcessStage（阶段）｜实体含人物·地点·部队·组织·历史事件等<br>
 实线 = Neo4j 原库关系，虚线 = 展示层派生聚合边（非原库关系）；交叉为自动检出，<b>非受访者原话</b>。<br>
 本页内嵌全量事件／阶段／实体／生平／文档及片段级证据节点，<b>不含 SourceAttachment、DocumentAnnotation 节点</b>；与 Neo4j 全库 27573 节点／49872 关系不是同一口径。<br>
 已知同一地点存在多个实体 ID、部分 LOCATION 成分错指：<b>地点交叉请以「情境 Circumstance」文本为锚</b>，共享实体仅为自动检出线索，须人工核对。</div>
 <div class="stats" id="stats"></div>
</header>
<div class="bar">
 <button class="tab on" data-v="overview">交叉总览</button><button class="tab" data-v="pair">两点交叉</button><button class="tab" data-v="ego">单点邻域 / 查询</button>
 <div class="sep"></div>
 <div id="searchWrap"><input id="search" placeholder="搜索人物 / 事件 / 地点 / 实体 / ID" size="30" autocomplete="off"><div id="suggest"></div></div>
 <span id="pairBox" style="display:none;font-size:12px;color:var(--ink2)">A <input id="pickA" size="10" readonly> ↔ B <input id="pickB" size="10" readonly> <button class="tab" id="swap">互换</button></span>
 <div class="sep"></div>
 <label>范围 <select id="scope"><option value="all">全部 60 份</option><option value="demo">仅 6 份人工 Demo</option><option value="official">仅 54 份正式</option></select></label>
 <label>跳数 <select id="depth"><option value="1">1 跳</option><option value="2">2 跳</option></select></label>
 <label>上限 <select id="limit"><option>80</option><option selected>140</option><option>240</option><option>380</option></select></label>
 <label><input type="checkbox" id="allLabels"> 全部边标签</label>
 <label><input type="checkbox" id="allNodeLabels"> 全部节点标签</label>
 <button class="tab" id="reset">重置视图</button>
</div>
<main>
 <div id="stage">
  <svg id="svg"><defs>
   <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#8A8172"/></marker>
   <marker id="arrowHi" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#A8322A"/></marker>
  </defs><g id="vp"><g id="ge"></g><g id="gl"></g><g id="gn"></g></g></svg>
  <div id="status"></div><div id="empty">当前条件下没有可绘制的节点，请放宽筛选或切换视图</div>
 </div>
 <aside>
  <div class="sec"><h3>节点类型（点击显隐）</h3><div id="legend"></div>
   <div class="note" style="margin-top:7px">节点外环：<b style="color:#A8322A">朱砂实线</b>＝人工 Demo；墨灰＝正式候选；虚线＝跨两类共享。<b style="color:#A8322A">朱砂虚线环</b>＝跨受访者／跨文档的交叉实体。<br>默认只标注受访者与交叉实体，悬停节点可显示其余名称；共享节点在任一范围筛选下都保留，<b>两类统计不可相加</b>。</div></div>
  <div class="sec"><h3>关系边（点击显隐）</h3><div id="etypes"></div>
   <div class="note" style="margin-top:7px">边名沿用 import.cypher 的关系类型；悬停／选中节点或边时显示完整边名与逐字证据。</div></div>
  <div class="sec"><h3>选中详情</h3><div id="detail" class="note">点击画布中的节点或边查看属性、关联边与逐字原文。</div></div>
  <div class="sec"><h3>交叉热点榜（跨受访者 / 跨文档实体）</h3>
   <div class="note" style="margin-bottom:6px">仅按实体提及／事件参与计共现（不含情境 REFERS_TO），按共现人数、文档数排序；点击任一行以该实体为中心展开交叉子图。</div>
   <div id="hotlist"></div></div>
  <div class="sec"><h3>全部节点清单（可翻页）</h3>
   <div style="display:flex;gap:6px;margin-bottom:6px"><select id="listKind" style="flex:1"></select><input id="listQuery" placeholder="名称过滤" size="9"></div>
   <div id="nodeList"></div><div id="listPager" style="margin-top:7px;font-size:11px;color:var(--ink2)"></div></div>
 </aside>
</main>
<script>
const N=__N__,SEG=__SEG__,EV=__EV__,MENT=__MENT__,CROSS=__CROSS__,META=__META__;
let E=__E__;
E=E.map(e=>[N[e[0]][0],N[e[1]][0],e[2],e[3]]);  // 落盘用节点下标省体积，载入后还原成 ID
function eLabel(e){const x=e[3]||{};return x.rt||(x.kind?'情境·'+x.kind:'')||(x.role?'参与·'+x.role:'')
 ||(x.logic?'阶段顺序·'+x.logic:'')||(x.basis?'事件链·'+x.basis:'')
 ||(x.derived?'提及于文档（派生）':'')||e[2];}
const KIND={
 subject:['受访者（人物主体）','#8C2F27',18],event:['一级事件 EventNode','#C0563F',12],
 stage:['二级阶段 ProcessStage','#E0A183',7],person:['人物 PERSON','#2E5B84',10],
 place:['地点 PLACE','#A5652E',10],unit:['部队 MILITARY_UNIT','#6B5A86',9],
 org:['组织 ORGANIZATION','#4B7A52',9],hist:['历史事件 HISTORICAL_EVENT','#B4883B',9],
 pub:['出版物 PUBLICATION','#7A8B96',8],other:['其他实体 OTHER','#8A877F',8],
 doc:['访谈文档','#5A5A55',9],episode:['生平片段 LifeEpisode','#C9A227',8],
 unresolved:['未解析参与者','#B9B4A8',7],alias:['别名','#A8A094',6],
 segment:['原文片段','#9C968A',6],time:['时间','#B0A48D',6],circum:['情境','#B98E6A',7],
 mention:['提及','#B3AC9E',5],process:['过程 Process','#C7A98A',7]};
const DEF_KINDS=new Set(['subject','event','stage','person','place','unit','org','hist','pub','other','doc','episode','unresolved']);
const DEF_EDGES=new Set(['INTERVIEW_OF','HAS_EVENT','HAS_STAGE','NEXT_STAGE','NEXT','HAS_PARTICIPANT','RELATED_TO','HAS_LIFE_EPISODE','SUPPORTED_BY_EVENT','BIOGRAPHICAL_NEXT','NARRATED_CONTEXT','MENTIONED_IN_DOC']);
const ANCHOR={subject:.10,doc:.27,episode:.28,event:.46,stage:.62,person:.78,place:.80,unit:.80,org:.80,hist:.80,pub:.80,other:.80,unresolved:.80,circum:.68,time:.70,segment:.91,mention:.88,alias:.84,process:.58};
const nodeById=new Map(N.map(n=>[n[0],n]));
const KINDCOUNT={};N.forEach(n=>KINDCOUNT[n[2]]=(KINDCOUNT[n[2]]||0)+1);
const adj=new Map();
E.forEach((e,i)=>{if(!adj.has(e[0]))adj.set(e[0],[]);if(!adj.has(e[1]))adj.set(e[1],[]);adj.get(e[0]).push(i);adj.get(e[1]).push(i);});
const nName=id=>{const n=nodeById.get(id);return n?n[1]:id;};
const kindName=k=>(KIND[k]||[k])[0];
const color=k=>(KIND[k]||[k,'#8A877F'])[1];
const radius=k=>(KIND[k]||[k,'',8])[2];

let state={view:'overview',scope:'all',depth:1,limit:140,allLabels:false,
 kinds:new Set(DEF_KINDS),etypes:new Set(DEF_EDGES),center:null,A:null,B:null,sel:null};
const svg=document.getElementById('svg'),vp=document.getElementById('vp');
const ge=document.getElementById('ge'),gl=document.getElementById('gl'),gn=document.getElementById('gn');
let shown=[],shownEdges=[],pos=new Map(),zoom=1,panX=0,panY=0,hoverId=null;

// ---------------------------------------------------------------- 统计与图例
document.getElementById('stats').innerHTML=[
 ['访谈文档',META.docs],['一级事件',META.events],['二级阶段',META.stages],['实体',META.entities],
 ['生平片段',META.episodes],['原文片段',META.segments],['内嵌节点',META.nodes],['内嵌边',META.edges],
 ['跨受访者共享实体',META.crossPeople],['跨文档共享实体',META.crossDocs]
].map(x=>`<span class="stat">${x[0]} <b>${x[1]}</b></span>`).join('');
function drawLegend(){
 const counts={};N.forEach(n=>counts[n[2]]=(counts[n[2]]||0)+1);
 document.getElementById('legend').innerHTML=Object.keys(KIND).filter(k=>counts[k]).map(k=>
  `<span class="chip ${state.kinds.has(k)?'':'off'}" data-k="${k}"><i class="dot" style="background:${color(k)}"></i>${kindName(k)} <em style="font-style:normal;color:#8A877F">${counts[k]}</em></span>`).join('');
 document.querySelectorAll('#legend .chip').forEach(c=>c.onclick=()=>{
  const k=c.dataset.k;state.kinds.has(k)?state.kinds.delete(k):state.kinds.add(k);drawLegend();render();});
 const ec={};E.forEach(e=>ec[e[2]]=(ec[e[2]]||0)+1);
 document.getElementById('etypes').innerHTML=Object.keys(ec).sort((a,b)=>ec[b]-ec[a]).map(t=>
  `<span class="chip ${state.etypes.has(t)?'':'off'}" data-t="${t}">${t} <em style="font-style:normal;color:#8A877F">${ec[t]}</em></span>`).join('');
 document.querySelectorAll('#etypes .chip').forEach(c=>c.onclick=()=>{
  const t=c.dataset.t;state.etypes.has(t)?state.etypes.delete(t):state.etypes.add(t);drawLegend();render();});
}
function drawHot(){
 const rows=Object.entries(CROSS).filter(([id,v])=>nodeById.has(id)).sort((a,b)=>b[1][0]-a[1][0]||b[1][1]-a[1][1]||b[1][2]-a[1][2]).slice(0,30);
 document.getElementById('hotlist').innerHTML=rows.map(([id,v])=>
  `<div class="hot" data-id="${id}"><b>${nName(id)}</b><i>${v[0]} 人 · ${v[1]} 文档 · ${v[2]} 事件</i></div>`).join('')||'<div class="note">无</div>';
 document.querySelectorAll('.hot').forEach(h=>h.onclick=()=>{
  state.center=h.dataset.id;state.view='ego';syncTabs();document.getElementById('search').value=nName(h.dataset.id);render();showNode(h.dataset.id);});
}
let listPage=0;
function drawList(){
 const kind=document.getElementById('listKind').value,q=document.getElementById('listQuery').value.trim().toLowerCase();
 const arr=N.filter(n=>(kind==='all'||n[2]===kind)&&(!q||n[1].toLowerCase().includes(q)||n[0].toLowerCase().includes(q)))
  .sort((a,b)=>crossScore(b[0])-crossScore(a[0])||(a[1]>b[1]?1:-1));
 const pages=Math.max(1,Math.ceil(arr.length/40));listPage=Math.max(0,Math.min(listPage,pages-1));
 document.getElementById('nodeList').innerHTML=arr.slice(listPage*40,listPage*40+40).map(n=>
  `<div class="listRow" data-id="${esc(n[0])}"><b>${esc(n[1].length>22?n[1].slice(0,21)+'…':n[1])}</b><i>${esc(kindName(n[2]).split(' ')[0])}</i></div>`).join('')||'<div class="note">无匹配节点</div>';
 document.getElementById('listPager').innerHTML=`共 ${arr.length} 个 · 第 ${listPage+1}/${pages} 页　<button class="tab" id="prevP">上一页</button> <button class="tab" id="nextP">下一页</button>`;
 document.querySelectorAll('.listRow').forEach(r=>r.onclick=()=>choose(r.dataset.id));
 document.getElementById('prevP').onclick=()=>{listPage--;drawList();};
 document.getElementById('nextP').onclick=()=>{listPage++;drawList();};
}
function syncTabs(){document.querySelectorAll('.bar .tab[data-v]').forEach(t=>t.classList.toggle('on',t.dataset.v===state.view));
 document.getElementById('pairBox').style.display=state.view==='pair'?'inline':'none';}

// ---------------------------------------------------------------- 子图选择
function okNode(id){
 const n=nodeById.get(id);if(!n)return false;
 if(!state.kinds.has(n[2]))return false;
 if(state.scope==='all')return true;
 if(n[3]==='mixed'||n[3]==='unknown')return true;
 return n[3]===state.scope;
}
function okEdge(i){
 const e=E[i];if(!state.etypes.has(e[2]))return false;
 return okNode(e[0])&&okNode(e[1]);
}
function neighbors(id,depth){
 const seen=new Set([id]);let frontier=[id];
 for(let d=0;d<depth;d++){
  const next=[];
  frontier.forEach(x=>(adj.get(x)||[]).forEach(i=>{if(!okEdge(i))return;
   const y=E[i][0]===x?E[i][1]:E[i][0];if(!seen.has(y)&&okNode(y)){seen.add(y);next.push(y);}}));
  frontier=next;
 }
 seen.delete(id);return [...seen];
}
function pathsFrom(id,depth){
 const res=new Map([[id,[]]]);let frontier=[id];
 for(let d=0;d<depth;d++){
  const next=[];
  frontier.forEach(x=>(adj.get(x)||[]).forEach(i=>{if(!okEdge(i))return;
   const y=E[i][0]===x?E[i][1]:E[i][0];
   if(!res.has(y)&&okNode(y)){res.set(y,[...res.get(x),i]);next.push(y);}}));
  frontier=next;
 }
 return res;
}
function pickSet(){
 let ids=new Set(),allow=null;const priority=new Map();
 if(state.view==='overview'){
  const hot=Object.entries(CROSS).filter(([id,v])=>v[0]>=2&&nodeById.has(id)&&okNode(id))
   .sort((a,b)=>b[1][0]-a[1][0]||b[1][1]-a[1][1]||b[1][2]-a[1][2]);
  N.filter(n=>n[2]==='subject').forEach(n=>{ids.add(n[0]);priority.set(n[0],4);});
  const take=Math.max(6,Math.floor(state.limit*.22));
  hot.slice(0,take).forEach(([id,v])=>{
   ids.add(id);priority.set(id,3);
   v[5].slice(0,2).forEach(ev=>{ids.add('ev:'+ev);priority.set('ev:'+ev,2);});
   v[4].slice(0,2).forEach(d=>{ids.add('d:'+d);priority.set('d:'+d,1);});
  });
  N.filter(n=>n[2]==='doc'&&n[3]!=='unknown').slice(0,10).forEach(n=>{if(!ids.has(n[0]))ids.add(n[0]);});
 } else if(state.view==='pair'){
  const A=state.A||'en:PER-CHF',B=state.B||'en:PER-CRT';
  let depth=state.depth,pa=pathsFrom(A,depth),pb=pathsFrom(B,depth);
  const sharedOf=(x,y)=>[...x.keys()].filter(k=>y.has(k)&&k!==A&&k!==B&&okNode(k))
   .sort((m,n)=>crossScore(n)-crossScore(m));
  let shared=sharedOf(pa,pb);
  if(!shared.length&&depth<2){depth=2;pa=pathsFrom(A,2);pb=pathsFrom(B,2);shared=sharedOf(pa,pb);}
  shared=shared.slice(0,Math.max(10,Math.floor(state.limit*.5)));
  ids.add(A);ids.add(B);priority.set(A,4);priority.set(B,4);
  shared.forEach(k=>{ids.add(k);priority.set(k,3);
   pa.get(k).forEach(i=>{ids.add(E[i][0]);ids.add(E[i][1]);});
   pb.get(k).forEach(i=>{ids.add(E[i][0]);ids.add(E[i][1]);});});
  allow=new Set();
  shared.forEach(k=>{pa.get(k).forEach(i=>allow.add(i));pb.get(k).forEach(i=>allow.add(i));});
 } else {
  const c=state.center||'en:PER-CHF';ids.add(c);priority.set(c,4);
  neighbors(c,state.depth).slice(0,state.limit-1).forEach(x=>ids.add(x));
 }
 ids=new Set([...ids].filter(okNode));
 if(ids.size>state.limit){
  const arr=[...ids].sort((a,b)=>(priority.get(b)||0)-(priority.get(a)||0)
   ||crossScore(b)-crossScore(a)||(adj.get(b)||[]).length-(adj.get(a)||[]).length);
  const keep=new Set(arr.slice(0,state.limit));
  if(state.center)keep.add(state.center);if(state.A)keep.add(state.A);if(state.B)keep.add(state.B);
  ids=keep;
 }
 const es=[];const seen=new Set();
 E.forEach((e,i)=>{if(!okEdge(i))return;if(!ids.has(e[0])||!ids.has(e[1]))return;
  if(allow&&!allow.has(i))return;const k=i;if(seen.has(k))return;seen.add(k);es.push(i);});
 return {ids:[...ids],es};
}
function crossScore(id){const c=CROSS[id];return c?c[0]*100+c[1]*10+c[2]:0;}

// ---------------------------------------------------------------- 布局
function layout(ids,es,w,h){
 pos=new Map();
 ids.forEach((id,i)=>{
  const n=nodeById.get(id),ax=(ANCHOR[n[2]]||.5)*w,ay=h*(.08+.84*((i*.6180339887)%1));
  pos.set(id,{x:ax+(Math.random()-.5)*36,y:ay,vx:0,vy:0,ax:ax,ay:ay});
 });
 const IT=190,K=1900,L=60;
 for(let it=0;it<IT;it++){
  const cool=1-it/IT;
  for(let i=0;i<ids.length;i++)for(let j=i+1;j<ids.length;j++){
   const p=pos.get(ids[i]),q=pos.get(ids[j]);
   let dx=p.x-q.x,dy=p.y-q.y,d2=dx*dx+dy*dy+16,d=Math.sqrt(d2);
   const f=K/d2;dx/=d;dy/=d;p.vx+=dx*f;p.vy+=dy*f;q.vx-=dx*f;q.vy-=dy*f;
  }
  es.forEach(i=>{const e=E[i],p=pos.get(e[0]),q=pos.get(e[1]);if(!p||!q)return;
   let dx=q.x-p.x,dy=q.y-p.y,d=Math.sqrt(dx*dx+dy*dy)+.01;
   const f=(d-L)*.014;dx/=d;dy/=d;p.vx+=dx*f;p.vy+=dy*f;q.vx-=dx*f;q.vy-=dy*f;});
  ids.forEach(id=>{const p=pos.get(id);
   p.vx+=(p.ax-p.x)*.026*(.45+.55*cool);p.vy+=(p.ay-p.y)*.010*(.45+.55*cool);
   if(p.x<28)p.vx+=(28-p.x)*.06;if(p.x>w-28)p.vx+=(w-28-p.x)*.06;
   if(p.y<28)p.vy+=(28-p.y)*.06;if(p.y>h-28)p.vy+=(h-28-p.y)*.06;
   p.vx*=.80;p.vy*=.80;
   p.x=Math.max(10,Math.min(w-10,p.x+p.vx));p.y=Math.max(10,Math.min(h-10,p.y+p.vy));});
 }
}
// ---------------------------------------------------------------- 绘制
function render(){
 const box=document.getElementById('stage'),w=box.clientWidth,h=box.clientHeight;
 const {ids,es}=pickSet();shown=ids;shownEdges=es;
 document.getElementById('empty').style.display=ids.length?'none':'flex';
 layout(ids,es,w,h);
 let eh='',lh='',nh='';
 es.forEach(i=>{
  const e=E[i],p=pos.get(e[0]),q=pos.get(e[1]);if(!p||!q)return;
  const r1=radius(nodeById.get(e[0])[2])+3,r2=radius(nodeById.get(e[1])[2])+7;
  let dx=q.x-p.x,dy=q.y-p.y,d=Math.sqrt(dx*dx+dy*dy)||1;
  const x1=p.x+dx/d*r1,y1=p.y+dy/d*r1,x2=q.x-dx/d*r2,y2=q.y-dy/d*r2;
  const derived=e[3]&&e[3].derived;
  eh+=`<line data-ei="${i}" x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="#8A8172" stroke-width="1.3" ${derived?'stroke-dasharray="4 3"':''} marker-end="url(#arrow)" style="cursor:pointer"/>`;
  if(state.allLabels){
   const mx=(x1+x2)/2,my=(y1+y2)/2;
   lh+=`<text class="elabel" x="${mx.toFixed(1)}" y="${(my-3).toFixed(1)}" text-anchor="middle">${esc(e[2])}</text>`;
  }
 });
 ids.forEach(id=>{
  const n=nodeById.get(id),p=pos.get(id),r=radius(n[2]),c=color(n[2]);
  const ring=n[3]==='demo'?'#A8322A':(n[3]==='official'?'#6E685E':'#B9B4A8');
  const dash=n[3]==='mixed'?'stroke-dasharray="2 2"':'';
  const cross=CROSS[id],major=n[2]==='subject'||!!cross;
  nh+=`<g data-id="${esc(id)}" style="cursor:pointer" transform="translate(${p.x.toFixed(1)},${p.y.toFixed(1)})">
   ${cross?`<circle r="${r+4}" fill="none" stroke="#A8322A" stroke-width="1.1" stroke-dasharray="2 2" opacity=".85"/>`:''}
   ${n[2]==='subject'?`<circle r="${r+8}" fill="none" stroke="${c}" stroke-width="1" opacity=".4"/>`:''}
   <circle r="${r}" fill="${c}" stroke="${ring}" stroke-width="1.6" ${dash}/>
   <text class="nlabel${major?' major':' minor'}" x="${r+4}" y="4">${esc(n[1].length>13?n[1].slice(0,12)+'…':n[1])}</text></g>`;
 });
 ge.innerHTML=eh;gl.innerHTML=lh;gn.innerHTML=nh;
 document.getElementById('status').textContent=`当前 ${ids.length} 节点 / ${es.length} 条边　｜　实线＝原库关系　虚线＝派生聚合边　｜　滚轮缩放 · 拖动平移 · 拖动节点`;
 applyTransform();highlight();
}
function esc(s){return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function applyTransform(){vp.setAttribute('transform',`translate(${panX},${panY}) scale(${zoom})`);}
function highlight(){
 const focus=hoverId||(state.sel&&state.sel.type==='node'?state.sel.id:null)
  ||(state.sel&&state.sel.type==='edge'?'__edge__':null);
 if(!focus){gn.querySelectorAll('g').forEach(g=>g.classList.remove('dim'));ge.querySelectorAll('line').forEach(l=>{l.classList.remove('dim');l.setAttribute('stroke','#A9A093');l.setAttribute('stroke-width','1.1');l.setAttribute('marker-end','url(#arrow)');});
  const old=document.getElementById('hoverLabel');if(old)old.remove();return;}
 const isEdge=state.sel&&state.sel.type==='edge'&&!hoverId;
 const related=new Set(),relE=new Set();
 if(isEdge){const i=state.sel.i;relE.add(i);related.add(E[i][0]);related.add(E[i][1]);}
 else{(adj.get(focus)||[]).forEach(i=>{const e=E[i];if(!shown.includes(e[0])||!shown.includes(e[1]))return;relE.add(i);related.add(e[0]);related.add(e[1]);});related.add(focus);}
 gn.querySelectorAll('g').forEach(g=>g.classList.toggle('dim',!related.has(g.dataset.id)));
 ge.querySelectorAll('line').forEach(l=>{const on=relE.has(+l.dataset.ei);l.classList.toggle('dim',!on);
  l.setAttribute('stroke',on?'#A8322A':'#8A8172');l.setAttribute('stroke-width',on?'2':'1.3');l.setAttribute('marker-end',on?'url(#arrowHi)':'url(#arrow)');});
 const old=document.getElementById('hoverLabel');if(old)old.remove();
 if(!state.allLabels&&relE.size){
  let s='';relE.forEach(i=>{const e=E[i],p=pos.get(e[0]),q=pos.get(e[1]);if(!p||!q)return;
   s+=`<text class="elabel" x="${((p.x+q.x)/2).toFixed(1)}" y="${((p.y+q.y)/2-4).toFixed(1)}" text-anchor="middle" fill="#A8322A">${esc(eLabel(e))}</text>`;});
  gl.insertAdjacentHTML('beforeend',`<g id="hoverLabel">${s}</g>`);
 }
}
// ---------------------------------------------------------------- 详情
function quote(sid,tag){
 const s=SEG[sid];if(!s)return '';
 return `<div class="quote">${esc(s[2].length>220?s[2].slice(0,220)+'…':s[2])}<small>${tag||'原文'} · ${esc(s[0])} · 片段 ${esc(s[1])} · ${esc(sid)}</small></div>`;
}
function showNode(id){
 const n=nodeById.get(id);if(!n)return;state.sel={type:'node',id};
 let h=`<div class="kv"><b>名称</b>${esc(n[1])}</div><div class="kv"><b>节点类型</b>${esc(kindName(n[2]))}</div>
 <div class="kv"><b>ID</b>${esc(id)}</div><div class="kv"><b>数据范围</b>${({demo:'人工 6 份 Demo',official:'正式 54 份候选',mixed:'跨两类共享',unknown:'未定'})[n[3]]||n[3]}</div>`;
 Object.entries(n[4]).forEach(([k,v])=>{if(v)h+=`<div class="kv"><b>${esc(k)}</b>${esc(String(v))}</div>`;});
 const c=CROSS[id];if(c)h+=`<div class="kv"><b>交叉度</b>${c[0]} 位受访者 · ${c[1]} 份文档 · ${c[2]} 个事件</div>`;
 const es=(adj.get(id)||[]);
 h+=`<div style="margin-top:9px;border-top:1px solid var(--line);padding-top:7px"><b style="font-size:12px;color:var(--zhu2)">关联边 ${es.length} 条（点按查看）</b></div>`;
 es.slice(0,40).forEach(i=>{const e=E[i],other=e[0]===id?e[1]:e[0];
  h+=`<div class="edgeItem" data-ei="${i}"><span>${esc(e[2])}</span> ${e[0]===id?'→':'←'} ${esc(nName(other))} <span style="color:#8A877F">${esc(eLabel(e))}</span></div>`;});
 if(es.length>40)h+=`<div class="note">仅列前 40 条，共 ${es.length} 条。</div>`;
 const ev=(EV[id]||[]).slice(0,4),mt=(MENT[id]||[]).slice(0,3);
 if(n[2]==='segment'&&SEG[id.slice(3)])h+=`<div style="margin-top:9px;border-top:1px solid var(--line);padding-top:7px"><b style="font-size:12px;color:var(--zhu2)">逐字原文</b></div>`+quote(id.slice(3),'原文片段');
 if(ev.length){h+=`<div style="margin-top:9px;border-top:1px solid var(--line);padding-top:7px"><b style="font-size:12px;color:var(--zhu2)">EVIDENCE 逐字依据</b></div>`;ev.forEach(s=>h+=quote(s,'EVIDENCE'));}
 if(mt.length){h+=`<div style="margin-top:7px"><b style="font-size:12px;color:var(--ink2)">实体提及原话</b></div>`;mt.forEach(s=>h+=quote(s,'提及'));}
 const d=document.getElementById('detail');d.innerHTML=h;d.className='';
 d.querySelectorAll('.edgeItem').forEach(x=>x.onclick=()=>showEdge(+x.dataset.ei));highlight();
}
function showEdge(i){
 const e=E[i];state.sel={type:'edge',i};
 let h=`<div class="kv"><b>关系类型</b><span style="color:var(--zhu2)">${esc(e[2])}</span></div>
 <div class="kv"><b>边说明</b>${esc(eLabel(e))}</div><div class="kv"><b>方向</b>${esc(nName(e[0]))} → ${esc(nName(e[1]))}</div>
 <div class="kv"><b>来源</b>${e[3]&&e[3].derived?'展示层派生聚合边（非 Neo4j 原库关系）':'import.cypher 原库关系'}</div>`;
 Object.entries(e[3]||{}).forEach(([k,v])=>{if(v&&k!=='derived')h+=`<div class="kv"><b>${esc(k)}</b>${esc(String(v))}</div>`;});
 if(e[3]&&e[3].e)h+=`<div style="margin-top:8px"><b style="font-size:12px;color:var(--zhu2)">证据原文</b></div>`+quote(e[3].e,'边证据');
 h+=`<div class="edgeItem" data-id="${esc(e[0])}" style="margin-top:8px">查看头节点：${esc(nName(e[0]))}</div>
 <div class="edgeItem" data-id="${esc(e[1])}">查看尾节点：${esc(nName(e[1]))}</div>`;
 const d=document.getElementById('detail');d.innerHTML=h;d.className='';
 d.querySelectorAll('.edgeItem').forEach(x=>x.onclick=()=>showNode(x.dataset.id));highlight();
}
// ---------------------------------------------------------------- 交互
svg.addEventListener('click',ev=>{
 const g=ev.target.closest('g[data-id]'),l=ev.target.closest('line[data-ei]');
 if(g)showNode(g.dataset.id);else if(l)showEdge(+l.dataset.ei);
});
svg.addEventListener('mousemove',ev=>{
 const g=ev.target.closest('g[data-id]');const id=g?g.dataset.id:null;
 if(id!==hoverId){hoverId=id;highlight();}
});
svg.addEventListener('mouseleave',()=>{hoverId=null;highlight();});
let drag=null;
svg.addEventListener('mousedown',ev=>{
 const g=ev.target.closest('g[data-id]');
 drag={x:ev.clientX,y:ev.clientY,px:panX,py:panY,id:g?g.dataset.id:null,ox:0,oy:0};
 if(g&&pos.get(g.dataset.id)){drag.ox=pos.get(g.dataset.id).x;drag.oy=pos.get(g.dataset.id).y;}
 svg.classList.add('drag');
});
window.addEventListener('mousemove',ev=>{
 if(!drag)return;const dx=ev.clientX-drag.x,dy=ev.clientY-drag.y;
 if(drag.id&&pos.get(drag.id)){
  const p=pos.get(drag.id);p.x=drag.ox+dx/zoom;p.y=drag.oy+dy/zoom;
  redrawPositions();
 }else{panX=drag.px+dx;panY=drag.py+dy;applyTransform();}
});
window.addEventListener('mouseup',()=>{drag=null;svg.classList.remove('drag');});
svg.addEventListener('wheel',ev=>{ev.preventDefault();const f=ev.deltaY<0?1.12:1/1.12;
 zoom=Math.max(.35,Math.min(3,zoom*f));applyTransform();},{passive:false});
function redrawPositions(){
 gn.querySelectorAll('g[data-id]').forEach(g=>{const p=pos.get(g.dataset.id);if(p)g.setAttribute('transform',`translate(${p.x.toFixed(1)},${p.y.toFixed(1)})`);});
 shownEdges.forEach((i,k)=>{const e=E[i],p=pos.get(e[0]),q=pos.get(e[1]),l=ge.children[k];if(!p||!q||!l)return;
  const r1=radius(nodeById.get(e[0])[2])+3,r2=radius(nodeById.get(e[1])[2])+7;
  let dx=q.x-p.x,dy=q.y-p.y,d=Math.sqrt(dx*dx+dy*dy)||1;
  l.setAttribute('x1',(p.x+dx/d*r1).toFixed(1));l.setAttribute('y1',(p.y+dy/d*r1).toFixed(1));
  l.setAttribute('x2',(q.x-dx/d*r2).toFixed(1));l.setAttribute('y2',(q.y-dy/d*r2).toFixed(1));});
}
const search=document.getElementById('search'),sug=document.getElementById('suggest');
let pickMode=null;
function suggest(q){
 if(!q){sug.style.display='none';return;}
 const ql=q.toLowerCase();
 const hits=N.filter(n=>n[1].toLowerCase().includes(ql)||n[0].toLowerCase().includes(ql))
  .sort((a,b)=>(crossScore(b[0])-crossScore(a[0]))||(b[2]==='subject')-(a[2]==='subject')).slice(0,25);
 sug.innerHTML=hits.map(n=>`<div data-id="${esc(n[0])}">${esc(n[1].length>26?n[1].slice(0,25)+'…':n[1])}<em>${esc(kindName(n[2]))} · ${esc(n[0].slice(0,26))}</em></div>`).join('')||'<div>无匹配</div>';
 sug.style.display='block';
 sug.querySelectorAll('div[data-id]').forEach(d=>d.onclick=()=>choose(d.dataset.id));
}
function choose(id){
 sug.style.display='none';
 if(pickMode){state[pickMode]=id;document.getElementById(pickMode==='A'?'pickA':'pickB').value=nName(id);pickMode=null;render();return;}
 const nn=nodeById.get(id);
 if(nn&&!state.kinds.has(nn[2])){
  state.kinds.add(nn[2]);
  (adj.get(id)||[]).forEach(i=>state.etypes.add(E[i][2]));  // 同时打开它相关的边类型，避免孤立节点
  drawLegend();
 }
 state.center=id;state.view='ego';syncTabs();search.value=nName(id);render();showNode(id);
}
search.addEventListener('input',()=>suggest(search.value.trim()));
search.addEventListener('keydown',ev=>{if(ev.key==='Escape')sug.style.display='none';
 if(ev.key==='Enter'){const d=sug.querySelector('div[data-id]');if(d)choose(d.dataset.id);}});
document.addEventListener('click',ev=>{if(!ev.target.closest('#searchWrap'))sug.style.display='none';});
document.querySelectorAll('.bar .tab[data-v]').forEach(t=>t.onclick=()=>{state.view=t.dataset.v;syncTabs();render();});
document.getElementById('scope').onchange=e=>{state.scope=e.target.value;render();};
document.getElementById('depth').onchange=e=>{state.depth=+e.target.value;render();};
document.getElementById('limit').onchange=e=>{state.limit=+e.target.value;render();};
document.getElementById('allLabels').onchange=e=>{state.allLabels=e.target.checked;render();};
document.getElementById('allNodeLabels').onchange=e=>{document.body.classList.toggle('show-all',e.target.checked);};
document.getElementById('reset').onclick=()=>{state={...state,view:'overview',scope:'all',depth:1,limit:140,
 kinds:new Set(DEF_KINDS),etypes:new Set(DEF_EDGES),center:null,A:'en:PER-CHF',B:'en:PER-CRT',sel:null};
 zoom=1;panX=0;panY=0;search.value='';document.getElementById('scope').value='all';
 document.getElementById('depth').value='1';document.getElementById('limit').value='140';
 document.getElementById('allLabels').checked=false;document.getElementById('allNodeLabels').checked=false;
 document.body.classList.remove('show-all');drawLegend();syncTabs();render();};
document.getElementById('pickA').onclick=()=>{pickMode='A';search.focus();search.value='';suggest('');};
document.getElementById('pickB').onclick=()=>{pickMode='B';search.focus();search.value='';suggest('');};
document.getElementById('swap').onclick=()=>{const t=state.A;state.A=state.B;state.B=t;
 document.getElementById('pickA').value=nName(state.A||'');document.getElementById('pickB').value=nName(state.B||'');render();};
state.A='en:PER-CHF';state.B='en:PER-CRT';
document.getElementById('pickA').value=nName(state.A);document.getElementById('pickB').value=nName(state.B);
window.addEventListener('resize',()=>render());
document.getElementById('listKind').innerHTML='<option value="all">全部类型</option>'+
 Object.keys(KIND).filter(k=>KINDCOUNT[k]).map(k=>`<option value="${k}">${esc(kindName(k))}（${KINDCOUNT[k]}）</option>`).join('');
document.getElementById('listKind').onchange=()=>{listPage=0;drawList();};
document.getElementById('listQuery').oninput=()=>{listPage=0;drawList();};
drawLegend();drawHot();drawList();syncTabs();render();
</script></body></html>'''

HTML = (HTML.replace('__N__', jd(list(nodes.values())))
            .replace('__E__', jd(edges_packed))
            .replace('__SEG__', jd(SEG))
            .replace('__EV__', jd({k: v for k, v in EV.items()}))
            .replace('__MENT__', jd({k: v for k, v in MENT.items()}))
            .replace('__CROSS__', jd(CROSS))
            .replace('__META__', jd(META)))
OUT.write_text(HTML, encoding='utf-8')
print('已写出', OUT, f'{OUT.stat().st_size / 1024:.0f} KB')
