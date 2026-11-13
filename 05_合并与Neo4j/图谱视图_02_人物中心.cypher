// ============================================================
// 图谱视图 02 · 以一个人物为中心（Graph 视图专用）
// 目标效果：中心一个人物节点，向外放射出访谈 / 生平 / 事件 / 关系，
//           形成截图那种中心放射状网络
// 示例人名 '陈海峰' 只在 7474 Demo 库有效；
// 7485 Qwen / 7486 DeepSeek 请先跑【2-0】拿到名字再全局替换
// 用法：一次只复制「一个编号块」到 Browser 执行，结果切到 Graph 视图
//      本文件全部只读，不含任何写操作
//
// 【出图后必做】左侧点标签色块 → 选 caption 属性：
//   Entity→canonical_name / EventNode→event_name / LifeEpisode→episode_name /
//   InterviewDocument→title / EventTime→raw_text / ProcessStage→stage_summary
//   注意：实体间关系全是 RELATED_TO，具体语义在 r.relation_type 属性里，
//        把关系 caption 设成 relation_type 才看得出 BORN_IN / STUDIED_AT 等
// ============================================================


// ------------------------------------------------------------
// 【2-0】先确认这个库里有哪些传记主体（正式库必跑）
// ------------------------------------------------------------
MATCH (p:BiographicalSubject)
RETURN p.canonical_name AS `人物`, p.entity_id AS `ID`;


// ------------------------------------------------------------
// 【2-1】人物 → 生平经历链（放射 + 链状，最接近截图效果）
// 含 HAS_LIFE_EPISODE / BIOGRAPHICAL_NEXT / 支撑该经历的访谈事件
// ------------------------------------------------------------
MATCH (person:BiographicalSubject {canonical_name:'陈海峰'})
OPTIONAL MATCH p1=(person)-[:HAS_LIFE_EPISODE]->(ep:LifeEpisode)
OPTIONAL MATCH p2=(ep)-[:BIOGRAPHICAL_NEXT]->(:LifeEpisode)
OPTIONAL MATCH p3=(ep)-[:SUPPORTED_BY_EVENT]->(ev:EventNode)<-[:HAS_EVENT]-(d:InterviewDocument)
RETURN person, p1, p2, p3 LIMIT 200;


// ------------------------------------------------------------
// 【2-2】人物 → 参与的事件 → 时间/类型/过程/阶段（三层放射）
// 用 HAS_PARTICIPANT 反查：中心是人物，外圈是事件，再外圈是事件属性
// ------------------------------------------------------------
MATCH (person:BiographicalSubject {canonical_name:'陈海峰'})<-[r1:HAS_PARTICIPANT]-(e:EventNode)
OPTIONAL MATCH p2=(e)-[:HAS_TIME|HAS_TYPE|HAS_PROCESS|HAS_STAGE]->()
RETURN person, r1, e, p2 LIMIT 200;


// ------------------------------------------------------------
// 【2-3】人物 → 各次访谈 → 事件 → 二级阶段（多层放射，规模稍大）
// ------------------------------------------------------------
MATCH (person:BiographicalSubject {canonical_name:'陈海峰'})
OPTIONAL MATCH p1=(d:InterviewDocument)-[:INTERVIEW_OF]->(person)
OPTIONAL MATCH p2=(d)-[:HAS_EVENT]->(e:EventNode)-[:HAS_STAGE]->(st:ProcessStage)
RETURN person, p1, p2 LIMIT 250;


// ------------------------------------------------------------
// 【2-4】人物社会关系网（出生地 / 求学 / 任职 / 隶属 / 指挥等）
// 所有实体关系都是 :RELATED_TO，语义在 r.relation_type
// ------------------------------------------------------------
MATCH (person:BiographicalSubject {canonical_name:'陈海峰'})
OPTIONAL MATCH (person)-[r1:RELATED_TO]->(x:Entity)
OPTIONAL MATCH (x)-[r2:RELATED_TO]->(y:Entity)
RETURN person, r1, x, r2, y LIMIT 150;


// ------------------------------------------------------------
// 【2-5】变长路径版：以人物为圆心，沿指定语义关系走 1–3 跳
// 若 2-1～2-4 想「一网打尽」用这条；无向匹配会自然形成放射网络
// ------------------------------------------------------------
MATCH path=(person:BiographicalSubject {canonical_name:'陈海峰'})
      -[:HAS_LIFE_EPISODE|SUPPORTED_BY_EVENT|BIOGRAPHICAL_NEXT|HAS_EVENT|INTERVIEW_OF|HAS_PARTICIPANT|HAS_TIME*1..3]-()
RETURN path LIMIT 250;
