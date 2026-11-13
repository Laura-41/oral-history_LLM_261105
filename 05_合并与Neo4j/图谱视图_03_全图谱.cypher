// ============================================================
// 图谱视图 03 · 相对完整的全图谱（Graph 视图专用）
// 前提：全库约 4708 节点 / 8187 关系，Browser 一次全 RETURN 会卡死，
//      所以「相对完整」分三档，按需要选一条执行
// 用法：一次只复制「一个编号块」到 Browser 执行，结果切到 Graph 视图
//      本文件全部只读，不含任何写操作
// ============================================================


// ------------------------------------------------------------
// 【3-1】结构全图（标签级）：17 类节点 + 全部关系类型
// 最清晰、秒出，适合论文里说明「图谱的 schema 长什么样」
// ------------------------------------------------------------
CALL db.schema.visualization();


// ------------------------------------------------------------
// 【3-2】语义骨架全图：排除原文片段 / 实体提及 / 别名 / 挂接 / 注释 /
//        时间表达 / 覆盖审计等叶子层，只留语义主干：
//        文档—事件—阶段—过程—类型—时间—参与者—环境—实体—生平
// 规模约 700 节点 / 800 关系，是「能看的最完整的一张图」
// 若浏览器卡：把 LIMIT 降到 300；若想更全：调到 2000
// ------------------------------------------------------------
MATCH (n)-[r]->(m)
WHERE NOT (n:SourceSegment OR m:SourceSegment)
  AND NOT (n:EntityMention OR m:EntityMention)
  AND NOT (n:EntityAlias OR m:EntityAlias)
  AND NOT (n:SourceAttachment OR m:SourceAttachment)
  AND NOT (n:TimeExpression OR m:TimeExpression)
  AND NOT (n:DocumentAnnotation OR m:DocumentAnnotation)
  AND NOT (n:CoverageAudit OR m:CoverageAudit)
RETURN n, r, m
LIMIT 1000;


// ------------------------------------------------------------
// 【3-3】尽量完整（含所有节点类型、含孤立节点）
// 注意：LIMIT 限制的是「返回行数」，一个节点有多条出边就占多行，
//      所以 1500 行并不等于 1500 个节点，图会有断点，属正常
// ------------------------------------------------------------
MATCH (n)
OPTIONAL MATCH (n)-[r]->(m)
RETURN n, r, m
LIMIT 1500;


// ------------------------------------------------------------
// 【3-4】按文档分批看「完整」图谱：把 doc_id 换 6 次即可覆盖全库
// 单份文档内连原文片段、提及、时间表达、挂接、二级阶段全都带出来
// ------------------------------------------------------------
MATCH (d:InterviewDocument {doc_id:'CHF-V1-01'})
OPTIONAL MATCH p1=(d)-[:HAS_SEGMENT]->(s:SourceSegment)
OPTIONAL MATCH p2=(s)-[:HAS_MENTION|HAS_TIME_EXPRESSION|HAS_ATTACHMENT]->()
OPTIONAL MATCH p3=(d)-[:HAS_EVENT]->(e:EventNode)-[:HAS_STAGE|HAS_PROCESS|HAS_TIME|HAS_PARTICIPANT|HAS_CIRCUMSTANCE]->()
RETURN d, p1, p2, p3 LIMIT 500;


// ------------------------------------------------------------
// 【3-5】确认全库规模（表格，不用于出图）
// ------------------------------------------------------------
MATCH (n) WITH count(n) AS nodes
MATCH ()-[r]->()
RETURN nodes AS `节点总数`, count(r) AS `关系总数`;


// ------------------------------------------------------------
// 说明：若确实需要「一个文件里的 4708 节点全量图」，Browser 不是合适工具。
// 可在装了 APOC 后导出 GraphML / Gephi 布局，或按 3-4 分 6 次导出 SVG 再拼。
// ------------------------------------------------------------
