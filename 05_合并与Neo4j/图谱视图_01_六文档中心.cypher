// ============================================================
// 图谱视图 01 · 以 6 份访谈文档为中心（Graph 视图专用）
// 适用：7474 六份人工 Demo 库（6 文档 / 40 一级事件 / 3 位受访者）
// 用法：一次只复制「一个编号块」到 Browser 执行，结果切到 Graph 视图
//      本文件全部只读，不含任何写操作
//
// 【出图后必做】节点上的文字默认可能是 ID 或空白：
//   左侧点标签色块 → 底部选 caption 属性，例如
//   InterviewDocument→title / EventNode→event_name / Entity→canonical_name /
//   LifeEpisode→episode_name / ProcessStage→stage_summary / SourceSegment→verbatim_text
//   关系 caption 选 relation_type、function、basis（否则只显示关系类型名）
//   右上角下载图标可导出 PNG / SVG 用于论文插图
// ============================================================


// ------------------------------------------------------------
// 【1-1】最简骨架：构建节点 → 6 份文档 → 3 位受访者
// 规模：约 10 节点 / 12 关系，最干净，适合先确认数据对不对
// ------------------------------------------------------------
MATCH (g:GraphBuild)-[r1:CONTAINS_DOCUMENT]->(d:InterviewDocument)
OPTIONAL MATCH (d)-[r2:INTERVIEW_OF]->(p:BiographicalSubject)
RETURN g, r1, d, r2, p;


// ------------------------------------------------------------
// 【1-2】六文档 + 一级事件放射图
// 规模：46 节点 / 40 关系，六个中心各带一簇事件，推荐做插图
// ------------------------------------------------------------
MATCH (d:InterviewDocument)-[r:HAS_EVENT]->(e:EventNode)
RETURN d, r, e;


// ------------------------------------------------------------
// 【1-3】六文档 + 事件 + 事件链 NEXT + 及物性类型（带箭头的网络图）
// 规模：约 49 节点 / 114 关系，能看出文档内叙事链条
// ------------------------------------------------------------
MATCH (d:InterviewDocument)-[r1:HAS_EVENT]->(e:EventNode)
OPTIONAL MATCH (e)-[r2:NEXT]->(nx:EventNode)
OPTIONAL MATCH (e)-[r3:HAS_TYPE]->(ty:EventType)
RETURN d, r1, e, r2, nx, r3, ty;


// ------------------------------------------------------------
// 【1-4】单份文档全景：事件 + 二级阶段 + 过程/时间/参与者/环境 + 原文挂接
// 规模较大，LIMIT 可按需调大；把 doc_id 换 6 次即可逐份看全库
// ------------------------------------------------------------
MATCH (d:InterviewDocument {doc_id:'CHF-V1-01'})-[:HAS_EVENT]->(e:EventNode)
OPTIONAL MATCH (e)-[:HAS_STAGE]->(st:ProcessStage)
OPTIONAL MATCH p2=(e)-[:HAS_PROCESS|HAS_TIME|HAS_PARTICIPANT|HAS_CIRCUMSTANCE|HAS_TYPE]->()
OPTIONAL MATCH p3=(d)-[:HAS_SEGMENT]->(:SourceSegment)-[:HAS_ATTACHMENT]->(:SourceAttachment)-[:ATTACHES_TO]->(e)
RETURN d, e, st, p2, p3 LIMIT 300;


// ------------------------------------------------------------
// 附：只看文档表格（核对 6 个 doc_id 用，不用于出图）
// MATCH (d:InterviewDocument) RETURN d.doc_id, d.title, d.interviewee ORDER BY d.doc_id;
// ------------------------------------------------------------
