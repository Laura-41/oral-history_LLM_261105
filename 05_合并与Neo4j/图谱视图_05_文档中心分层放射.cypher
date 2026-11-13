// ============================================================
// 图谱视图 05 · 文档 → 一级事件 → 二级阶段 / 原文证据
// 适用：7474 六份人工 Demo 库（6 文档 / 40 一级事件 / 119 二级阶段）
// 用法：一次只复制「一个编号块」到 Browser 执行，结果切到 Graph 视图
//      本文件全部只读，不含任何写操作
//
// 【术语】「二级事件」= ProcessStage（二级阶段）
//
// 【层级】原文片段经 SourceAttachment 挂接，中间隔一层：
//   (InterviewDocument)-[:HAS_EVENT]->(EventNode)-[:HAS_STAGE]->(ProcessStage)
//   (ProcessStage)<-[:ATTACHES_TO]-(SourceAttachment)<-[:HAS_ATTACHMENT]-(SourceSegment)
// 5-B1 / 5-B2 是链式（阶段再指原文）；5-B3 是并列式（事件同时指阶段和原文）。
//
// 【规模实测】单阶段最多 6 个原文片段，单事件最多 75 个（EVIDENCE 39）。
// 所以走阶段链安全，事件级直连原文必须用 function 过滤 + LIMIT。
//
// 【出图设置】caption：InterviewDocument→title / EventNode→event_name /
//   ProcessStage→stage_summary / SourceSegment→segment_id（点节点看 verbatim_text）/
//   SourceAttachment→function。右上角可导出 PNG / SVG。
// ============================================================


// ------------------------------------------------------------
// 【5-0】先列出 6 个 doc_id（换文档时查这里）
// ------------------------------------------------------------
MATCH (d:InterviewDocument)
RETURN d.doc_id AS `文档ID`, d.title AS `标题`, d.interviewee AS `受访者`
ORDER BY d.doc_id;


// ------------------------------------------------------------
// 【5-1】★ 主推：单份文档 → 一级事件 → 二级阶段 → 原文证据（完整链）
// 换 doc_id 可逐份看全库；这份文档有 7 个一级事件，图最清晰
// ------------------------------------------------------------
MATCH (d:InterviewDocument {doc_id:'CHF-V1-01'})
OPTIONAL MATCH p1=(d)-[:HAS_EVENT]->(e:EventNode)
OPTIONAL MATCH p2=(e)-[:HAS_STAGE]->(st:ProcessStage)
OPTIONAL MATCH p3=(st)<-[:ATTACHES_TO]-(:SourceAttachment)<-[:HAS_ATTACHMENT]-(s:SourceSegment)
RETURN d, p1, p2, p3 LIMIT 300;


// ------------------------------------------------------------
// 【5-2】六份文档一起出图（全库分层图）
// 节点约 6 + 40 + 119 + 挂接/片段若干；卡就把 LIMIT 降到 300
// ------------------------------------------------------------
MATCH p1=(d:InterviewDocument)-[:HAS_EVENT]->(e:EventNode)
OPTIONAL MATCH p2=(e)-[:HAS_STAGE]->(st:ProcessStage)
OPTIONAL MATCH p3=(st)<-[:ATTACHES_TO]-(:SourceAttachment)<-[:HAS_ATTACHMENT]-(s:SourceSegment)
RETURN p1, p2, p3 LIMIT 600;


// ------------------------------------------------------------
// 【5-3】并列式：一级事件同时指向「二级阶段」和「原文证据」
// 事件级挂接只取 EVIDENCE，避免 75 个片段把图挤爆。
// 注意两个 OPTIONAL MATCH 会做笛卡尔积，返回行数偏多但 Browser 会去重节点，
// 图本身是对的；若某个事件原文特别多，改用 5-4 单独看它
// ------------------------------------------------------------
MATCH (d:InterviewDocument {doc_id:'CHF-V1-01'})-[r1:HAS_EVENT]->(e:EventNode)
OPTIONAL MATCH (e)-[r2:HAS_STAGE]->(st:ProcessStage)
OPTIONAL MATCH (e)<-[r3:ATTACHES_TO]-(a:SourceAttachment {function:'EVIDENCE'})<-[r4:HAS_ATTACHMENT]-(s:SourceSegment)
RETURN d, r1, e, r2, st, r3, a, r4, s LIMIT 600;


// ------------------------------------------------------------
// 【5-4】单条一级事件的三层放射（最适合当论文插图）
// 换 event_id 即可：CHF-V1-E01 … CHF-V1-E07 等
// ------------------------------------------------------------
MATCH (e:EventNode {event_id:'CHF-V1-E03'})
OPTIONAL MATCH (e)-[r1:HAS_STAGE]->(st:ProcessStage)
OPTIONAL MATCH p2=(st)<-[:ATTACHES_TO]-(:SourceAttachment)<-[:HAS_ATTACHMENT]-(s:SourceSegment)
RETURN e, r1, st, p2 LIMIT 100;


// ------------------------------------------------------------
// 【5-5】查「某条二级阶段」背后究竟是哪些逐字原文（表格核对用）
// 论文里逐字引用时走这条，比在图上点节点更快
// ------------------------------------------------------------
MATCH (e:EventNode {event_id:'CHF-V1-E03'})-[:HAS_STAGE]->(st:ProcessStage)
OPTIONAL MATCH (st)<-[:ATTACHES_TO]-(a:SourceAttachment)<-[:HAS_ATTACHMENT]-(s:SourceSegment)
RETURN st.stage_order AS `阶段序`, st.stage_summary AS `二级阶段`,
       a.function AS `挂接功能`, s.segment_id AS `片段ID`, s.verbatim_text AS `逐字原文`
ORDER BY `阶段序`, `片段ID`;
