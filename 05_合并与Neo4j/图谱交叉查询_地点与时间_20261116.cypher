// 图谱交叉查询：地点 × 时间 × 人物（2026-11-16）
// 实例：DeepSeek 60 份图谱 http://127.0.0.1:7486 （bolt 7689），build_id = oral-history-all60-v1
// 本文件全部指令已在该实例逐条实跑通过；换地点只需把 '上海' 换成 '临沂' / '鲁南' 等。
//
// 【坑 1】地点实体未跨文档消歧：canonical_name='上海' 有 5 个 Entity 节点
//   （P003 / E_PLACE_SHANGHAI / e014 / E12 / PLACE-SHANGHAI），且 P003 被 BATCH05-DOC03
//   两条 value_text='临沂' 的 LOCATION 成分错指。故交叉一律以 Circumstance 的文本字段
//   （value_text / normalized_value）为锚，不要依赖 Entity 节点的 REFERS_TO。见 Q9。
// 【坑 2】EventTime 中 precision=RELATIVE 占 307/479、normalized_start 仅 154/479 非空，
//   按年份区间做数值过滤会漏掉相对时间，须同时看 raw_text。见 Q10。
// 【坑 3】LOCATION 成分口径窄：全库 416 条 LOCATION，含"上海"仅 10 条事件；
//   逐字原话里"上海"出现远多于此。做召回评估请对照 Q8。
// 【红线】WORKFLOW_DEMO(6) 与 BATCH_APPLICATION(54) 两类统计不可相加，需要时按 d.data_role 过滤。

// ---------------------------------------------------------------------------
// Q1 · 地点锚点总表：一个地点带出 受访者 / 文档 / 事件 / 时间 / 证据片段
//     实测 10 行（陈海峰 6、陈锐霆 4、杨永松 0）
// ---------------------------------------------------------------------------
MATCH (d:InterviewDocument)-[:HAS_EVENT]->(e:EventNode)-[hc:HAS_CIRCUMSTANCE]->(c:Circumstance)
WHERE c.kind = 'LOCATION'
  AND (c.normalized_value CONTAINS '上海' OR c.value_text CONTAINS '上海')
OPTIONAL MATCH (e)-[:HAS_TIME]->(t:EventTime)
RETURN d.interviewee    AS 受访者,
       d.doc_id         AS 语料ID,
       e.event_name     AS 事件,
       c.value_text     AS 地点原文,
       c.normalized_value AS 地点归一,
       t.raw_text       AS 时间原文,
       t.normalized_start AS 起始,
       t.precision      AS 精度,
       c.evidence_segment_id AS 证据片段
ORDER BY 起始, 受访者;

// ---------------------------------------------------------------------------
// Q2 · 出图版：上海子图（文档 → 事件 → 地点 / 时间 / 人物 / 实体）
//     RETURN 里带节点与关系变量才会出图，只返回属性则只有 Table/RAW
// ---------------------------------------------------------------------------
MATCH (d:InterviewDocument)-[he:HAS_EVENT]->(e:EventNode)-[hc:HAS_CIRCUMSTANCE]->(c:Circumstance)
WHERE c.kind = 'LOCATION'
  AND (c.normalized_value CONTAINS '上海' OR c.value_text CONTAINS '上海')
OPTIONAL MATCH (e)-[ht:HAS_TIME]->(t:EventTime)
OPTIONAL MATCH (c)-[rt:REFERS_TO]->(x:Entity)
OPTIONAL MATCH (d)-[io:INTERVIEW_OF]->(p:Entity:BiographicalSubject)
RETURN d, he, e, hc, c, ht, t, rt, x, io, p;

// ---------------------------------------------------------------------------
// Q3 · 时间 × 地点双条件：1931–1949 年间在上海的事件（实测 8 行）
//     把两个年份边界换掉即可换时段；RELATIVE 时间若无 normalized_start 会被滤掉
// ---------------------------------------------------------------------------
MATCH (d:InterviewDocument)-[:HAS_EVENT]->(e:EventNode)-[:HAS_CIRCUMSTANCE]->(c:Circumstance)
WHERE c.kind = 'LOCATION'
  AND (c.normalized_value CONTAINS '上海' OR c.value_text CONTAINS '上海')
MATCH (e)-[:HAS_TIME]->(t:EventTime)
WHERE t.normalized_start >= '1931' AND t.normalized_start < '1950'
RETURN t.normalized_start AS 时间,
       t.raw_text         AS 时间原文,
       d.interviewee      AS 受访者,
       e.event_name       AS 事件,
       c.value_text       AS 地点
ORDER BY 时间;

// ---------------------------------------------------------------------------
// Q4 · 轨迹交叉：自动筛出被 >=2 位受访者共同提到的地点（实测 6 处）
//     上海 / 临沂 / 新四军军部 / 鲁南 / …；把 n >= 2 改成 = 3 即三人共同交集
//     对应门户 C 板块「轨迹交叉」，注意 normalized_value 里混有机构名，需人工分辨
// ---------------------------------------------------------------------------
MATCH (d:InterviewDocument)-[:HAS_EVENT]->(:EventNode)-[:HAS_CIRCUMSTANCE]->(c:Circumstance)
WHERE c.kind = 'LOCATION' AND c.normalized_value <> ''
WITH c.normalized_value AS place,
     collect(DISTINCT d.interviewee) AS who,
     count(DISTINCT d.interviewee) AS n,
     count(*) AS ev
WHERE n >= 2
RETURN place AS 交叉地点, n AS 受访者数, who AS 受访者, ev AS 关联次数
ORDER BY n DESC, ev DESC;

// ---------------------------------------------------------------------------
// Q5 · 受访者 × 地点统计：某一地点在三条人生线里各占多少
// ---------------------------------------------------------------------------
MATCH (d:InterviewDocument)-[:HAS_EVENT]->(e:EventNode)-[:HAS_CIRCUMSTANCE]->(c:Circumstance)
WHERE c.kind = 'LOCATION'
  AND (c.normalized_value CONTAINS '上海' OR c.value_text CONTAINS '上海')
RETURN d.interviewee AS 受访者,
       count(DISTINCT d) AS 文档数,
       count(DISTINCT e) AS 事件数,
       collect(DISTINCT e.event_name) AS 事件清单
ORDER BY 事件数 DESC;

// ---------------------------------------------------------------------------
// Q6 · 生平轨迹上的地点：三条人生线里带该地名的站点 + 支撑事件的时间（实测 6 行）
//     门户 B 板块「人生链路」的同源数据；DEMO- 前缀为人工 6 份
// ---------------------------------------------------------------------------
MATCH (p:Entity:BiographicalSubject)-[:HAS_LIFE_EPISODE]->(l:LifeEpisode)
        -[:SUPPORTED_BY_EVENT]->(e:EventNode)
WHERE l.episode_name CONTAINS '上海'
OPTIONAL MATCH (e)-[:HAS_TIME]->(t:EventTime)
RETURN p.canonical_name AS 受访者,
       l.life_order     AS 站点序,
       l.episode_name   AS 人生站点,
       l.episode_id     AS 站点ID,
       l.normalized_start AS 起始,
       l.precision      AS 精度,
       t.raw_text       AS 事件时间原文
ORDER BY 受访者, 站点序;

// ---------------------------------------------------------------------------
// Q7 · 地点标注的逐字证据链：c.evidence_segment_id 回查原话（抽检用，实测 10 行）
//     Circumstance 到 SourceSegment 只有属性、没有建边，必须靠 segment_id 连接
// ---------------------------------------------------------------------------
MATCH (d:InterviewDocument)-[:HAS_EVENT]->(e:EventNode)-[:HAS_CIRCUMSTANCE]->(c:Circumstance)
WHERE c.kind = 'LOCATION' AND c.value_text CONTAINS '上海'
MATCH (s:SourceSegment {segment_id: c.evidence_segment_id})
RETURN d.doc_id      AS 语料ID,
       e.event_name  AS 事件,
       c.value_text  AS 地点原文,
       c.confidence  AS 置信度,
       s.segment_id  AS 片段ID,
       s.verbatim_text AS 逐字原话;

// ---------------------------------------------------------------------------
// Q8 · 宽口径文本反查：全库逐字原话里出现"上海"的片段（含编者注，需分辨来源）
//     对照 Q1 可看出 LOCATION 标注的召回缺口
// ---------------------------------------------------------------------------
MATCH (d:InterviewDocument)-[:HAS_SEGMENT]->(s:SourceSegment)
WHERE s.verbatim_text CONTAINS '上海'
RETURN d.doc_id AS 语料ID, d.interviewee AS 受访者,
       s.segment_id AS 片段ID, s.segment_type AS 片段类型,
       s.verbatim_text AS 逐字原话
LIMIT 30;

// ---------------------------------------------------------------------------
// Q9 · 数据体检：同名地点实体未消歧 + REFERS_TO 错配（写方法章可用）
//     实测 '上海' 有 5 个 PLACE 节点；其中 P003 被两条 value_text='临沂' 的成分错指
// ---------------------------------------------------------------------------
MATCH (x:Entity) WHERE x.canonical_name = '上海' AND x.entity_type = 'PLACE'
OPTIONAL MATCH (x)<-[rt:REFERS_TO]-(c:Circumstance)<-[:HAS_CIRCUMSTANCE]-(e:EventNode)
RETURN x.entity_id AS 实体ID, x.canonical_name AS 实体名,
       c.value_text AS 所连地点成分, e.doc_id AS 来源语料
ORDER BY 实体ID;

// ---------------------------------------------------------------------------
// Q10 · 数据体检：时间精度分布（RELATIVE 307 / INTERVAL 69 / MONTH 49 / DAY 37 / YEAR 17）
//      with_iso 一列说明有多少能进数值区间过滤
// ---------------------------------------------------------------------------
MATCH (t:EventTime)
RETURN t.precision AS 精度, count(*) AS 条数,
       count(t.normalized_start) AS 有归一值
ORDER BY 条数 DESC;
