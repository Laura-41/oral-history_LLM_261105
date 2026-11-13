// ============================================================
// 图谱视图 04 · 人物 → 一级事件 → 二级阶段 → 原文证据
// 适用：7474 六份人工 Demo 库；7485 / 7486 换人名后通用
// 用法：一次只复制「一个编号块」到 Browser 执行，结果切到 Graph 视图
//      本文件全部只读，不含任何写操作
//
// 【术语】工程里「二级事件」的节点标签是 ProcessStage（二级阶段）
//
// 【层级真相，重要】原文片段不是直连二级阶段的，中间隔一层挂接节点：
//   (EventNode)-[:HAS_STAGE]->(ProcessStage)
//   (ProcessStage)<-[:ATTACHES_TO]-(SourceAttachment)<-[:HAS_ATTACHMENT]-(SourceSegment)
// 所以图上实际是 5 层：人物 → 一级事件 → 二级阶段 → 挂接 → 原文片段。
// SourceAttachment 带 function 属性（EVIDENCE / BACKGROUND 等），保留它能看出证据性质。
//
// 【规模】每个二级阶段最多挂 6 个原文片段（且全部是 EVIDENCE），链式展开很安全；
//        但事件级直接挂原文最多 75 个片段，所以本文件一律走「阶段→原文」，不直连事件。
//
// 【出图设置】左侧标签面板设 caption：
//   EventNode→event_name / ProcessStage→stage_summary / Entity→canonical_name
//   SourceSegment 建议用 segment_id（verbatim_text 太长会挤成一团），
//   点节点在右侧属性面板看逐字原文；SourceAttachment 用 function
// ============================================================


// ------------------------------------------------------------
// 【4-0】先确认这个库里有哪些传记主体（正式库必跑）
// ------------------------------------------------------------
MATCH (p:BiographicalSubject)
RETURN p.canonical_name AS `人物`, p.entity_id AS `ID`;


// ------------------------------------------------------------
// 【4-1】★ 主推：人物 → 生平 → 一级事件 → 二级阶段 → 原文证据
// 走 HAS_LIFE_EPISODE / SUPPORTED_BY_EVENT，箭头方向是「人物指向事件」，
// 符合分层放射的直觉；代价是多一层 LifeEpisode（但这层本身有论文意义）
// ------------------------------------------------------------
MATCH (person:BiographicalSubject {canonical_name:'陈海峰'})
OPTIONAL MATCH p1=(person)-[:HAS_LIFE_EPISODE]->(ep:LifeEpisode)-[:SUPPORTED_BY_EVENT]->(e:EventNode)
OPTIONAL MATCH p2=(e)-[:HAS_STAGE]->(st:ProcessStage)
OPTIONAL MATCH p3=(st)<-[:ATTACHES_TO]-(:SourceAttachment)<-[:HAS_ATTACHMENT]-(s:SourceSegment)
RETURN person, p1, p2, p3 LIMIT 300;


// ------------------------------------------------------------
// 【4-2】紧凑版：少一层生平，直接用「人物参与事件」反查
// 注意 HAS_PARTICIPANT 的方向是 (事件)->(人物)，图上箭头指向人物，
// 视觉上不是从人物放射出去；若只要语义正确、不在意箭头方向，用这条
// ------------------------------------------------------------
MATCH (person:BiographicalSubject {canonical_name:'陈海峰'})
OPTIONAL MATCH p1=(e:EventNode)-[:HAS_PARTICIPANT]->(person)
OPTIONAL MATCH p2=(e)-[:HAS_STAGE]->(st:ProcessStage)
OPTIONAL MATCH p3=(st)<-[:ATTACHES_TO]-(:SourceAttachment)<-[:HAS_ATTACHMENT]-(s:SourceSegment)
RETURN person, p1, p2, p3 LIMIT 300;


// ------------------------------------------------------------
// 【4-3】人物 + 访谈文档一起入图：人物 → 各次访谈 → 事件 → 阶段 → 原文
// 层级更全，但节点更多；卡的话把 LIMIT 降到 200
// ------------------------------------------------------------
MATCH (person:BiographicalSubject {canonical_name:'陈海峰'})
OPTIONAL MATCH p0=(d:InterviewDocument)-[:INTERVIEW_OF]->(person)
OPTIONAL MATCH p1=(d)-[:HAS_EVENT]->(e:EventNode)
OPTIONAL MATCH p2=(e)-[:HAS_STAGE]->(st:ProcessStage)
OPTIONAL MATCH p3=(st)<-[:ATTACHES_TO]-(:SourceAttachment)<-[:HAS_ATTACHMENT]-(s:SourceSegment)
RETURN person, p0, p1, p2, p3 LIMIT 400;


// ------------------------------------------------------------
// 【4-4】只保留 EVIDENCE 挂接（去掉 BACKGROUND / 提问 / 编者注）
// 想让图更干净时用；阶段级挂接本来就全是 EVIDENCE，差别主要在事件层
// ------------------------------------------------------------
MATCH (person:BiographicalSubject {canonical_name:'陈海峰'})
OPTIONAL MATCH p1=(person)-[:HAS_LIFE_EPISODE]->(:LifeEpisode)-[:SUPPORTED_BY_EVENT]->(e:EventNode)
OPTIONAL MATCH p2=(e)-[:HAS_STAGE]->(st:ProcessStage)
OPTIONAL MATCH p3=(st)<-[:ATTACHES_TO]-(a:SourceAttachment {function:'EVIDENCE'})<-[:HAS_ATTACHMENT]-(s:SourceSegment)
RETURN person, p1, p2, p3 LIMIT 300;
