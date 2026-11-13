// ============================================================
// 口述史图谱 · 应用场景查询速查
// 建立：2026-11-09
// 适用：7474 = 6份人工Demo库 / 7485 = Qwen / 7486 = DeepSeek
//      （三库 schema 相同，示例人名与事件ID需按所连的库替换）
//
// 【用法，务必先看】
// 1. 本文件全部为只读查询，不含任何写操作，不会改动图谱。
// 2. 一次只复制「一个编号块」到 Neo4j Browser 输入框执行。
//    整段粘贴会让多条 MATCH...RETURN 连在一起，报
//    "RETURN can only be used at the end of a query or subquery"。
// 3. 注释必须单独成行；`//` 写在语句前面会把整行注释掉。
// 4. 中文别名一律用反引号包裹；示例中的 '陈海峰'、'CHF-V1-E03'、
//    'CHF-V1-01' 只在 7474 Demo 库里存在。
// 5. 全库约 4708 节点 / 8187 关系，概览类查询一律带 LIMIT。
// ============================================================


// ------------------------------------------------------------
// 【场景 1】方法章：交代数据规模、验收导入是否完整
// 用途：论文里写「本图谱共 N 个节点、M 条关系」，并核对三个库的规模差异
// ------------------------------------------------------------
MATCH (n)
WITH count(n) AS nodes
MATCH ()-[r]->()
RETURN nodes AS `节点总数`, count(r) AS `关系总数`;


// ------------------------------------------------------------
// 【场景 2】方法章：一次拿到四层结构的计数（文档/事件/阶段/时间表达）
// ------------------------------------------------------------
MATCH (d:InterviewDocument)
OPTIONAL MATCH (d)-[:HAS_EVENT]->(e:EventNode)
OPTIONAL MATCH (e)-[:HAS_STAGE]->(st:ProcessStage)
OPTIONAL MATCH (d)-[:HAS_SEGMENT]->(:SourceSegment)-[:HAS_TIME_EXPRESSION]->(t:TimeExpression)
RETURN count(DISTINCT d) AS `访谈数`,
       count(DISTINCT e) AS `一级事件`,
       count(DISTINCT st) AS `二级阶段`,
       count(DISTINCT t) AS `时间表达`;


// ------------------------------------------------------------
// 【场景 3】叙事学分析：叙述顺序 vs 历史顺序的错位（倒叙/插叙）
// 用途：口述史里最典型的现象；结果可直接做「叙事时间错位」用例表
// ------------------------------------------------------------
MATCH (d:InterviewDocument)-[:HAS_EVENT]->(e:EventNode)
WHERE e.narrative_order <> e.historical_order
RETURN d.interviewee AS `人物`,
       e.event_id AS `事件ID`,
       e.narrative_order AS `叙述序`,
       e.historical_order AS `历史序`,
       e.event_name AS `事件`
ORDER BY `人物`, `叙述序`;


// ------------------------------------------------------------
// 【场景 4】时间语言学：挑出相对时间与非口述来源的时间表达
// 用途：讨论口述记忆的时间不确定性、编者介入（人物小传/脚注推断）
// ------------------------------------------------------------
MATCH (e:EventNode)-[:HAS_TIME]->(t:EventTime)
WHERE t.precision = 'RELATIVE' OR t.source_status <> 'ORAL_TESTIMONY'
MATCH (d:InterviewDocument)-[:HAS_EVENT]->(e)
RETURN d.interviewee AS `人物`,
       e.event_name AS `事件`,
       t.raw_text AS `原文时间`,
       t.normalized_start AS `规范起`,
       t.precision AS `精度`,
       t.certainty AS `确定性`,
       t.source_status AS `来源性质`
ORDER BY `规范起`;


// ------------------------------------------------------------
// 【场景 5】及物性分析：六类过程的分布 + 参与者角色样例
// 用途：韩礼德及物性系统在口述语料中的分布表（方法章/分析章）
// ------------------------------------------------------------
MATCH (e:EventNode)-[:HAS_TYPE]->(ty:EventType)
OPTIONAL MATCH (e)-[pr:HAS_PARTICIPANT]->(:Entity)
RETURN ty.event_type_id AS `类型ID`,
       ty.name AS `过程类型`,
       count(DISTINCT e) AS `事件数`,
       collect(DISTINCT e.event_name)[0..3] AS `示例事件`,
       collect(DISTINCT pr.role)[0..8] AS `出现的参与者角色`
ORDER BY `事件数` DESC;


// ------------------------------------------------------------
// 【场景 6】及物性细读：原因/目的/处所等环境成分逐条列出
// 用途：写「环境成分（Circumstance）」一节时的例句来源
// ------------------------------------------------------------
MATCH (e:EventNode)-[:HAS_CIRCUMSTANCE]->(c:Circumstance)
WHERE c.kind IN ['CAUSE', 'PURPOSE', 'LOCATION']
OPTIONAL MATCH (c)-[:REFERS_TO]->(x:Entity)
RETURN e.event_id AS `事件ID`,
       e.event_name AS `事件`,
       c.kind AS `成分类型`,
       c.value_text AS `原文`,
       c.normalized_value AS `规范值`,
       x.canonical_name AS `关联实体`
ORDER BY `事件ID`, `成分类型`;


// ------------------------------------------------------------
// 【场景 7】单条事件的完整框架（论文例句展开）
// 用途：把一条事件拆成 过程—参与者—环境成分 做定性分析
// ------------------------------------------------------------
MATCH (e:EventNode {event_id:'CHF-V1-E03'})
OPTIONAL MATCH (e)-[:HAS_TYPE]->(ty:EventType)
OPTIONAL MATCH (e)-[:HAS_PROCESS]->(p:Process)
OPTIONAL MATCH (e)-[pr:HAS_PARTICIPANT]->(x:Entity)
OPTIONAL MATCH (e)-[:HAS_CIRCUMSTANCE]->(c:Circumstance)
RETURN e.event_name AS `事件`,
       ty.name AS `过程类型`,
       p.process_text AS `过程原文`,
       collect(DISTINCT pr.role + '：' + x.canonical_name) AS `参与者`,
       collect(DISTINCT c.kind + '：' + c.value_text) AS `环境成分`;


// ------------------------------------------------------------
// 【场景 8】生平重构：每段经历由哪几次访谈、哪几条事件支撑
// 用途：说明 LifeEpisode 叠加视图如何跨访谈重组真实时间线
// ------------------------------------------------------------
MATCH (p:BiographicalSubject)-[:HAS_LIFE_EPISODE]->(ep:LifeEpisode)
OPTIONAL MATCH (ep)-[:SUPPORTED_BY_EVENT]->(e:EventNode)<-[:HAS_EVENT]-(d:InterviewDocument)
RETURN p.canonical_name AS `人物`,
       ep.life_order AS `生平序`,
       ep.normalized_start AS `起`,
       ep.episode_name AS `经历`,
       ep.episode_scope AS `经历性质`,
       count(DISTINCT d.title) AS `来源访谈数`,
       collect(DISTINCT d.title) AS `来源访谈`,
       collect(DISTINCT e.event_id) AS `来源事件`
ORDER BY `人物`, `生平序`;


// ------------------------------------------------------------
// 【场景 9】叙述归属：讲述但不认定为本人经历的「集体历史背景」
// 用途：区分个人经历与时代背景，避免把口述中的转述当成亲历
// ------------------------------------------------------------
MATCH (p:BiographicalSubject)-[:NARRATED_CONTEXT]->(e:EventNode)<-[:HAS_EVENT]-(d:InterviewDocument)
RETURN p.canonical_name AS `人物`,
       d.title AS `来源访谈`,
       e.historical_order AS `历史序`,
       e.event_name AS `仅作为背景叙述的事件`
ORDER BY `人物`, `历史序`;


// ------------------------------------------------------------
// 【场景 10】人物社会关系网（图形视图，可用于论文插图）
// 用途：出生地、求学、任职、隶属等实体关系；Graph 视图直接出图
// ------------------------------------------------------------
MATCH p=(:BiographicalSubject {canonical_name:'陈海峰'})-[r:RELATED_TO]->(x:Entity)
RETURN p LIMIT 60;


// ------------------------------------------------------------
// 【场景 10b】同样的数据用表格看（便于复制进论文附录）
// ------------------------------------------------------------
MATCH (p:BiographicalSubject)-[r:RELATED_TO]->(x:Entity)
RETURN p.canonical_name AS `人物`,
       r.relation_type AS `关系`,
       x.entity_type AS `对象类型`,
       x.canonical_name AS `对象`,
       r.start_date AS `起始`
ORDER BY `人物`, `关系`;


// ------------------------------------------------------------
// 【场景 11】可核查性 / 人工抽检：从事件回溯逐字原文与挂接功能
// 用途：SOP §6 人工抽检、逐字证据核对；function 区分证据/背景/提问
// ------------------------------------------------------------
MATCH (e:EventNode {event_id:'CHF-V1-E03'})<-[:ATTACHES_TO]-(a:SourceAttachment)<-[:HAS_ATTACHMENT]-(s:SourceSegment)
RETURN s.segment_order AS `原文序`,
       a.function AS `挂接功能`,
       s.source_part AS `来源部分`,
       left(s.verbatim_text, 160) AS `逐字原文`
ORDER BY `原文序` LIMIT 30;


// ------------------------------------------------------------
// 【场景 12】脚注与编者话语：脚注里出现的实体与时间表达
// 用途：讨论编排层（编者注、人物小传）对语料的介入
// ------------------------------------------------------------
MATCH (d:InterviewDocument)-[:HAS_SEGMENT]->(s:SourceSegment)
WHERE s.source_part = 'footnotes'
OPTIONAL MATCH (s)-[:HAS_MENTION]->(:EntityMention)-[:MENTIONS]->(x:Entity)
OPTIONAL MATCH (s)-[:HAS_TIME_EXPRESSION]->(t:TimeExpression)
RETURN d.interviewee AS `人物`,
       left(s.verbatim_text, 120) AS `脚注原文`,
       collect(DISTINCT x.canonical_name) AS `涉及实体`,
       collect(DISTINCT t.raw_text) AS `时间表达`
ORDER BY `人物`;


// ------------------------------------------------------------
// 【场景 13】质量抽检 / 熔断：缺时间、缺阶段、低置信、未复核的事件
// 用途：每批放行前先跑一遍，定位需要人工复核的条目
// ------------------------------------------------------------
MATCH (d:InterviewDocument)-[:HAS_EVENT]->(e:EventNode)
OPTIONAL MATCH (e)-[:HAS_TIME]->(t:EventTime)
OPTIONAL MATCH (e)-[:HAS_STAGE]->(st:ProcessStage)
WITH d, e, count(DISTINCT t) AS nTime, count(DISTINCT st) AS nStage
WHERE nTime = 0 OR nStage = 0 OR e.confidence <> 'HIGH' OR e.review_status <> 'CONFIRMED'
RETURN d.doc_id AS `文档`,
       e.event_id AS `事件ID`,
       e.event_name AS `事件`,
       nTime AS `时间数`,
       nStage AS `阶段数`,
       e.confidence AS `置信度`,
       e.review_status AS `复核状态`
ORDER BY `文档`, `事件ID`;


// ------------------------------------------------------------
// 【场景 13b】覆盖率审计：原文是否全部挂接进图谱
// ------------------------------------------------------------
MATCH (d:InterviewDocument)-[:HAS_COVERAGE_AUDIT]->(a:CoverageAudit)
RETURN d.title AS `访谈`,
       a.total_characters AS `总字数`,
       a.coverage_rate AS `覆盖率`,
       a.uncovered_characters AS `未覆盖字数`,
       a.overlap_characters AS `重叠字数`,
       a.audit_status AS `审计`
ORDER BY `覆盖率`;


// ------------------------------------------------------------
// 【场景 14】双模型对照：两个标签页跑同一句，比事件数与类型分布
// 用途：Qwen / DeepSeek 同题独立跑完后的差异表（记得按 model_id 分开记）
// ------------------------------------------------------------
MATCH (g:GraphBuild)
MATCH (d:InterviewDocument)-[:HAS_EVENT]->(e:EventNode)
OPTIONAL MATCH (e)-[:HAS_TYPE]->(ty:EventType)
RETURN g.build_id AS `图谱`,
       count(DISTINCT d) AS `文档数`,
       count(DISTINCT e) AS `事件数`,
       collect(DISTINCT ty.event_type_id) AS `出现的及物性类型`;


// ------------------------------------------------------------
// 【场景 15】论文插图：单份文档的「事件—二级阶段」局部图
// 用途：Graph 视图截图，比全库图清晰得多
// ------------------------------------------------------------
MATCH p=(d:InterviewDocument {doc_id:'CHF-V1-01'})-[:HAS_EVENT]->(e:EventNode)-[:HAS_STAGE]->(st:ProcessStage)
RETURN p LIMIT 100;


// ============================================================
// 附：常用零门槛命令（排查用）
// CALL db.labels();                      // 所有节点标签
// CALL db.relationshipTypes();          // 所有关系类型
// CALL db.schema.visualization();       // schema 图
// MATCH (n) RETURN n LIMIT 50;          // 只看节点（含孤立节点）
// MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 50;  // 看节点+关系
// ============================================================
