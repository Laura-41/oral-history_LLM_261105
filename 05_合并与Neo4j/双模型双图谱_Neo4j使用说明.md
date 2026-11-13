# 双模型双图谱：Neo4j 分开管理与使用说明

> 版本 v1.1　日期：2026-11-10 18:0x（补 T3／T4 落地说明）　初版：2026-11-07 20:36
> 研究者裁决：**D1=1**「两套都留着，两个模型看两个图谱」；**P0 选 A：两个独立数据库**。
> 本文件只记录**使用与落地方式**。撰写时未改任何代码、提示词、Schema、冻结资产、既有标注结果与运行数据。
> 约定不变：所有需要启动服务、导入数据的命令，由研究者在**本地终端**执行，助手不代跑。

---

## 一、为什么必须分开（一句话 + 证据）

两条模型线的**事件 ID 是同名的**：

| 模型线 | `BATCH02-DOC01` 的 `event_id` |
|---|---|
| `cuc/qwen` | `BATCH02-DOC01-DE001` … `DE005`（5 条） |
| `cuc/deepseek` | `BATCH02-DOC01-DE001` … `DE009`（9 条） |

前 5 个 ID 完全同名，**内容却不是同一条事件**。而 `import.cypher` 用
`MERGE (e:EventNode {event_id:row.event_id})` 且对 `event_id` 建了唯一约束 ——
两套 CSV 若导进**同一个** Neo4j，后导入的会覆盖／合并前一份，两套图谱互相污染。
文档、片段、实体、生平表同理。

因此口径固定为：

> **一个模型 = 一个独立 Neo4j 实例 = 一个独立数据库 = 一套 24 张 CSV。**

选 A 的好处：**ID 保持原样**，不加模型前缀，跟已跑出的结果文件、`GraphBuild.build_id`、
登记表里的 `model_id` 全部一致，不需要任何映射。

---

## 二、目录与文件地图

| 内容 | 位置 |
|---|---|
| Qwen 线导出（24 CSV + `import.cypher` + `prepare_summary.json`） | `05_合并与Neo4j/import_cuc_qwen/` |
| DeepSeek 线导出（跑完后生成） | `05_合并与Neo4j/import_cuc_deepseek/` |
| 两条线的 L0–L3 中间产物 | `04_54份正式语料批处理/document_consolidation/graph_layers/<模型目录>/<文档>/` |
| 验收报告 | 同上目录下的 `VALIDATION_report.json` |
| 6 份人工 Demo 的独立实例 | `/Users/yuqi/Desktop/硕士毕业论文/2609/0920_01/现行标注/neo4j_demo/` |

**2026-11-08 13:40 更新的实际状态**（取代 11-07 20:36 的旧记录）：

- `cuc/qwen`：✅ 单文档端到端验证**已完成**，`VALIDATION_report.json` 为 `valid=true`、覆盖率 1.0000。
  `import_cuc_qwen/` 的 24 张 CSV 已于 **11-08 13:40 按 E1／E2／T1／T2 新口径零 API 重新导出**
  （`segment_type` 时间码独立、`normalized_text` 全空、`circumstance_kind` 严格 5 值、三个字段补真值）。
  **现在就可以按第三节导入 Qwen 实例做可视化检验。**
- `cuc/deepseek`：⚠️ 9 次 stage 全部成功，但 `entity_time` 那次调用**等满 1800 秒超时熔断**
  （`raw/entity_time_CHF-V1-03_20261107_202621_FAILED.json`），因此**尚无后处理／验收／导出**。
  研究者需在终端重跑一次（会跳过 9 个已完成 stage，只补这 1 次调用）：
  ```bash
  cd '/Users/yuqi/Desktop/硕士毕业论文/2609/0920_01/大模型标注1104'
  TIMEOUT=3600 MODEL=cuc/deepseek bash scripts/graph_verify_one_document.sh BATCH02-DOC01
  ```
  跑完才会生成 `import_cuc_deepseek/`，再按第 3.2 节建第二套实例。
- 6 份人工 Demo 库是**第三个**独立实例，保持原样，不要混进来。
- 结构核实：正式批次 24 张表与 `现行标注/neo4j_demo/import/` 的**表名、列名逐列一致**，
  `process_stages` 单文档已有 33 行真实二级阶段。

**2026-11-10 18:0x 更新（T3=不改／T4=改 已落地）**：

- `import_cuc_qwen/` 与 `instances/qwen/import/` 已再次零 API 重导。**24 张 CSV 与 11-08 版逐字节一致**——
  「没有人工 MERGE 决策」时生平层保持 1 事件 1 生平，零副作用；变化只在
  `import.cypher` 末尾的声明注释、`prepare_summary.json` 的 `vocabulary_version`／`biography_*` 元信息。
- **词表 v1.1**（人工 7 值 + `RECORDING_TIMESTAMP`，环境成分严格人工 5 值）按 T3 裁决
  只在契约 §五·补三、导入脚本注释、导出报告里**全局声明**，没有任何 CSV 加版本列，
  因此 24 表仍与 6 份 Demo 逐列一致。方法章可直接引用的文字也在契约里。
- **导入后看生平层**：`LifeEpisode` 是叠加视图，语料层（`SourceSegment`／`EventNode`）绝不合并；
  跨访谈疑似同一经历只把 `life_episodes.review_status` 标 `NEEDS_REVIEW` 并出清单
  （`04_54份正式语料批处理/review_queue/<模型>_生平层疑似同一经历_待人工确认_*.md`）。
  研究者确认后，在 `04_54份正式语料批处理/human_adjudicated/<模型>/life_episode_merges.csv`
  填 `MERGE` 再重跑导出，才会出现「1 条人生经历 ← 多个来源事件」的形状。
  目前只有 1 份文档入库，故疑似组为 0，属正常。

---

## 三、A 方案在这台机器上怎么落地

### 3.0 一个前提（很重要）

你现在用的是 **Neo4j Community**（`/Users/yuqi/Downloads/neo4j-community-1-2026.06.24`）。
社区版一个实例只有 `neo4j` 一个数据库（在 Browser 里跑 `SHOW DATABASES;` 可确认），
`CREATE DATABASE` / `:USE 库名` 属企业版能力。所以「两个独立数据库」在这台机器上要落成
**两个独立实例**：各自的 `conf / data / logs / run / import`，各自端口。

> 程序分发目录可以共用，但 `data`、`logs`、`run`、`import` **绝不能共用**。
> 两个实例同时开会各占约 1GB 内存（`heap.max_size=768m` + `pagecache=256m`），机器吃紧时也可以只开一个、换文件重导（见 3.3）。

### 3.1 端口与目录规划

| 实例 | 用途 | Browser | Bolt | conf | 实例根目录 | 英文软链 |
|---|---|---|---|---|---|---|
| demo（已有，别动） | 6 份人工 Demo | 7474 | 7687 | `现行标注/neo4j_demo/conf` | `现行标注/neo4j_demo` | `/tmp/oral_history_neo4j_demo` |
| **qwen（新）** | 正式语料 Qwen 线 | **7485** | **7688** | `05_合并与Neo4j/instances/qwen/conf` | `05_合并与Neo4j/instances/qwen` | `/tmp/graph_qwen` |
| **deepseek（新）** | 正式语料 DeepSeek 线 | **7486** | **7689** | `05_合并与Neo4j/instances/deepseek/conf` | `05_合并与Neo4j/instances/deepseek` | `/tmp/graph_deepseek` |

端口与目录名是建议值，可以改，但**两个实例之间必须不同**。
`conf/neo4j.conf` 里 `data / logs / run / import` 四项都要指向本实例自己的目录。

> **2026-11-08 13:47 端口调整**：原计划 Qwen 用 **7475**，实测该端口被 `baidunetd`（百度网盘）占用
> （`lsof -iTCP:7475` 实测），故 Qwen 改 **7485**、DeepSeek 改 **7486**；
> Bolt 端口 7688／7689 实测空闲，保持不变。下文命令与 conf 示例已全部同步。
>
> **Qwen 实例的第 1–3 步助手已备好**：`instances/qwen/conf/neo4j.conf`（端口与目录已配好）、
> `instances/qwen/import/` 里 24 张 CSV + `import.cypher`、软链 `/tmp/graph_qwen` 均已就绪并核对通过。
> 研究者**只需执行第 4 步启动 + 第 5 步粘 Cypher**。DeepSeek 实例仍需按第 6 步照做一遍。

> 为什么要用 `/tmp` 英文软链：`现行标注/neo4j_demo/README.md:13` 已记录，
> Neo4j 启动器会把中文路径转义出错；软链只改访问路径，不复制程序或数据库。

### 3.2 每套实例怎么建（以 qwen 为例，deepseek 照做一遍）

**第 1 步：建目录 + 英文软链**

```bash
cd '/Users/yuqi/Desktop/硕士毕业论文/2609/0920_01/大模型标注1104/05_合并与Neo4j'
mkdir -p instances/qwen/{conf,data,logs,run,import}
ln -sfn "$PWD/instances/qwen" /tmp/graph_qwen
```

**第 2 步：把本模型线的 24 张 CSV 与导入脚本放进该实例的 `import/`**

```bash
cp import_cuc_qwen/*.csv import_cuc_qwen/import.cypher instances/qwen/import/
```

生成的 `import.cypher` 里全是 `LOAD CSV WITH HEADERS FROM 'file:///documents.csv'` 这类**相对文件名**，
所以只要 CSV 在该实例的 `import/` 目录下就能读到，不需要改脚本路径。

**第 3 步：复制一份 conf，改端口与目录**

```bash
cp '/Users/yuqi/Desktop/硕士毕业论文/2609/0920_01/现行标注/neo4j_demo/conf/neo4j.conf' instances/qwen/conf/neo4j.conf
```

打开 `instances/qwen/conf/neo4j.conf`，把这些行改成：

```text
server.directories.data=/tmp/graph_qwen/data
server.directories.logs=/tmp/graph_qwen/logs
server.directories.run=/tmp/graph_qwen/run
server.directories.import=/tmp/graph_qwen/import
server.directories.transaction.logs.root=/tmp/graph_qwen/data/transactions
server.bolt.listen_address=127.0.0.1:7688
server.bolt.advertised_address=127.0.0.1:7688
server.http.listen_address=127.0.0.1:7485
server.http.advertised_address=127.0.0.1:7485
```

其余（`dbms.security.auth_enabled=false`、`initial.dbms.default_database=neo4j`、内存设置）保持原样。

**第 4 步：另开一个终端启动**（不要关掉 demo 实例和另一个模型线的终端）

```bash
env NEO4J_CONF=/tmp/graph_qwen/conf \
  '/Users/yuqi/Downloads/neo4j-community-1-2026.06.24/bin/neo4j' console
```

**第 5 步：导入**

浏览器打开 <http://localhost:7485>，把 `instances/qwen/import/import.cypher` **全文粘贴执行**
（也可用 `cypher-shell -f import.cypher`）。脚本第一行 `MATCH (n) DETACH DELETE n;`
只清**本实例**的数据 —— 因为是独立的 `data/` 目录，不会碰到 demo 库或 DeepSeek 库。

**第 6 步：DeepSeek 实例照做一遍**

目录 `instances/deepseek`、软链 `/tmp/graph_deepseek`、端口 **7486 / 7689**、
`cp import_cuc_deepseek/*`（等它导出后才有）、启动与导入同第 4–5 步。

### 3.3 更省事但功能弱一点的做法（可选）

若不需要两边同时在线对照，可以只起**一个**实例，用同一个 `import/` 目录换文件：
导 Qwen → 查完 → 清空 → 换成 DeepSeek 的 CSV 再导一次。
代价是每次都要重导、两边不能并排看。研究者说的是「两个模型看两个图谱」，
所以**按 3.2 各起一个更贴合**。

---

## 四、日常怎么用

| 想做的事 | 去哪 |
|---|---|
| 看 Qwen 线的图 | <http://localhost:7485> |
| 看 DeepSeek 线的图 | <http://localhost:7486> |
| 看 6 份人工 Demo | <http://localhost:7474>（原有实例，别动） |
| 同题对照 | 两个浏览器标签页并排，跑同一句 Cypher |

**对照示例**（同一份 `BATCH02-DOC01`，两边事件数不同是**正常现象**，不是出错）：

```cypher
MATCH (d:InterviewDocument)-[:HAS_EVENT]->(e:EventNode)
RETURN d.doc_id AS 文档, count(e) AS 事件数;
```

本轮单文档验证的实际数字：Qwen **5** 条、DeepSeek **9** 条。

**自查有没有串线**（每套库的 `GraphBuild` 节点带模型标识）：

```cypher
MATCH (g:GraphBuild) RETURN g.build_id, g.schema_version, g.description;
```

Qwen 库应为 `oral-history-batch-cuc_qwen-v1`，DeepSeek 库应为 `oral-history-batch-cuc_deepseek-v1`；
`schema_version` 均为 `3.2+batch-application-ext`。

---

## 五、严禁事项（踩一条就可能毁数据）

1. **不要**把两套 CSV 放进同一个 `import/` 后一起执行 —— 同名主键会互相覆盖。
2. **不要**把两个模型的候选拼进同一份文档或同一个数据库；单份文档内 `source_model_id` 必须唯一。
3. **不要**把 6 份 Demo 的 CSV 拷进正式库：Demo 的 `data_role=WORKFLOW_DEMO`，正式的是 `BATCH_APPLICATION`。
4. **不要**在正式库里跑 `现行标注/neo4j_demo/import.cypher`，反之亦然。
5. 执行导入前**先确认浏览器连的是对的端口**，因为 `MATCH (n) DETACH DELETE n` 会清空当前连接的库。
6. 不要为了「省一个实例」给 ID 加模型前缀 —— 那是被否掉的 B 方案，会让 24 张表的 ID 与外键全部改动，且与已跑结果不一致。

---

## 六、留痕与已知小问题

- 每套 `import.cypher` 的 `GraphBuild.build_id` 已按模型区分；调用级留痕在
  `01_实验配置/实验登记表.csv`（一行＝一次 API 调用）与 `双线批改台账.csv`（一行＝文档×模型）。
- **已知小问题（不影响数据，待修）**：生成的 `import.cypher` 里 `g.name` 仍写着
  「口述史六份工作流Demo图谱」，是复制 demo 模板时没替换的残留；正式导入以
  `build_id` 与 `description` 为准。它和 T3「`schema_version` 只改了注释字符串」属同一类留痕问题，
  等 E/T 项裁决时一并修。
- 两线 `event_id` 同名是**故意保留**的：选 A 就是为了让 ID 跟已跑结果一致，只要库分开就没有问题。

---

## 七、与其他裁决的对应

| 项 | 裁决 | 本文件涉及 |
|---|---|---|
| D1 | `1` 两套都留、两个图谱 | §一、§三、§四（全文） |
| P0 | **A 两个独立数据库** | §三（全文） |
| D2 | `2` 新增层双跑 | 两套库各自的输入来源 |
| D3 | 不合并，沿用 `LifeEpisode` 叠加视图 | 生平 6 张表在各自库内独立生成 |
| D4 | `1` 沿用 SOP §6 | 抽检在各自模型线进行 |
| D5 | `1` 脚注不专门抽 | 24 表内容口径，不影响分库方式 |

完整裁决、结构依据与落地清单见
`04_54份正式语料批处理/document_consolidation/review/枚举词表与标注路线_裁决单_20261107.md` §七；
契约版本记录见 `02_Schema与提示词/graph_enrichment_v1.0/graph_enrichment_contract_v1.0.md` v1.0.7。

---

## 八、常用查询指令（Neo4j Browser 里逐条粘贴，Ctrl+Enter 执行）

> 2026-11-10 18:3x 核实：`localhost:7485` 的 Qwen 库已成功导入 **570 个节点／877 条关系**，
> 表名列名与 `instances/qwen/import/` 的 24 张 CSV 一一对应。
> 下面所有属性名都取自 `import.cypher` 里真实的 `SET` 语句，可直接运行。
> **一次只粘一条语句**；多条语句粘一起会各自开一个结果框，容易看混。
> 图视图里点节点可展开邻居，右键可固定/隐藏。

### A. 先摸底：这个库里到底装了什么

```cypher
// A1 节点类型与数量
MATCH (n) RETURN head(labels(n)) AS label, count(*) AS cnt ORDER BY cnt DESC;
```

```cypher
// A2 关系类型与数量
MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS cnt ORDER BY cnt DESC;
```

```cypher
// A3 防串线：确认当前库是哪条模型线
MATCH (g:GraphBuild)
RETURN g.build_id, g.name, g.description, g.import_date, g.schema_version;
```

```cypher
// A4 已入库的文档与每份事件数
MATCH (d:InterviewDocument)
OPTIONAL MATCH (d)-[:HAS_EVENT]->(e:EventNode)
RETURN d.doc_id, d.title, d.interviewee, d.review_status, count(e) AS events
ORDER BY d.doc_id;
```

### B. 看内容：原文 → 一级事件 → 二级阶段 → 人物生平

```cypher
// B1 一篇访谈全貌（图视图，可拖拽）
MATCH (d:InterviewDocument)-[:HAS_EVENT]->(e:EventNode)
OPTIONAL MATCH (e)-[:HAS_STAGE]->(s:ProcessStage)
OPTIONAL MATCH (e)-[:HAS_CIRCUMSTANCE]->(c:Circumstance)
RETURN d, e, s, c;
```

```cypher
// B2 事件 + 二级阶段清单（表格）
MATCH (e:EventNode)
OPTIONAL MATCH (e)-[:HAS_STAGE]->(s:ProcessStage)
RETURN e.event_id, e.event_name, e.review_status, s.stage_order, s.stage_summary
ORDER BY e.narrative_order, s.stage_order;
```

```cypher
// B3 事件先后顺序
MATCH (a:EventNode)-[r:NEXT]->(b:EventNode)
RETURN a.event_name, b.event_name, r.basis, r.confidence;
```

```cypher
// B4 二级阶段的先后逻辑
MATCH (a:ProcessStage)-[r:NEXT_STAGE]->(b:ProcessStage)
RETURN a.stage_id, a.stage_summary, r.logic, b.stage_id, b.stage_summary
ORDER BY a.stage_id;
```

```cypher
// B5 人物生平时间线（D3 叠加视图；一套经历可挂多个来源事件）
MATCH (p:Entity:BiographicalSubject)-[:HAS_LIFE_EPISODE]->(l:LifeEpisode)
OPTIONAL MATCH (l)-[:SUPPORTED_BY_EVENT]->(e:EventNode)
RETURN p.canonical_name, l.life_order, l.normalized_start, l.episode_name,
       l.review_status, collect(e.event_id) AS source_events
ORDER BY l.life_order;
```

```cypher
// B6 生平叠加视图（图视图：人物 → 经历 → 来源事件 → 文档）
MATCH (p:Entity:BiographicalSubject)-[:HAS_LIFE_EPISODE]->(l:LifeEpisode)
OPTIONAL MATCH (l)-[:SUPPORTED_BY_EVENT]->(e:EventNode)
OPTIONAL MATCH (d:InterviewDocument)-[:HAS_EVENT]->(e)
RETURN p, l, e, d;
```

```cypher
// B7 事件回跳逐字原文（抽检必用）
MATCH (e:EventNode)<-[:ATTACHES_TO]-(a:SourceAttachment)<-[:HAS_ATTACHMENT]-(s:SourceSegment)
RETURN e.event_id, e.event_name, a.function, s.segment_id, s.verbatim_text
ORDER BY s.segment_order LIMIT 50;
```

```cypher
// B8 实体、别名与原文写法
MATCH (m:EntityMention)-[:MENTIONS]->(en:Entity)
RETURN en.canonical_name, en.entity_type, count(m) AS mentions,
       collect(DISTINCT m.mention_text)[0..5] AS variants
ORDER BY mentions DESC LIMIT 20;
```

```cypher
// B9 时间表达
MATCH (s:SourceSegment)-[:HAS_TIME_EXPRESSION]->(t:TimeExpression)
RETURN t.raw_text, t.normalized_start, t.normalized_end, t.expression_type, s.segment_id
ORDER BY t.normalized_start;
```

```cypher
// B10 环境成分（含规范化值、证据片段、置信度）
MATCH (e:EventNode)-[:HAS_CIRCUMSTANCE]->(c:Circumstance)
RETURN e.event_id, c.kind, c.value_text, c.normalized_value,
       c.evidence_segment_id, c.confidence
ORDER BY e.event_id, c.kind;
```

### C. 查质量：验收与人工复核

```cypher
// C1 覆盖率（应为 1.0 / PASS）
MATCH (d:InterviewDocument)-[:HAS_COVERAGE_AUDIT]->(a:CoverageAudit)
RETURN d.doc_id, a.total_segments, a.attached_segments, a.coverage_rate, a.audit_status;
```

```cypher
// C2 待人工复核的事件
MATCH (e:EventNode) WHERE e.review_status = 'NEEDS_REVIEW'
RETURN e.event_id, e.event_name, e.boundary_note, e.boundary_confidence;
```

```cypher
// C3 低置信环境成分（E3「后面再标」的复核对象）
MATCH (e:EventNode)-[:HAS_CIRCUMSTANCE]->(c:Circumstance)
WHERE c.confidence = 'LOW'
RETURN e.event_id, c.circumstance_id, c.kind, c.value_text,
       c.normalized_value, c.evidence_segment_id
ORDER BY e.event_id;
```

```cypher
// C4 词表分布：验证 E1（人工 7 值 + RECORDING_TIMESTAMP）
MATCH (s:SourceSegment) RETURN s.segment_type AS seg_type, count(*) AS cnt ORDER BY cnt DESC;
```

```cypher
// C5 词表分布：验证 E2（严格人工 5 类）
MATCH (c:Circumstance) RETURN c.kind AS kind, count(*) AS cnt ORDER BY cnt DESC;
```

```cypher
// C6 环境成分三字段补齐率
MATCH (c:Circumstance)
RETURN count(c) AS total,
  sum(CASE WHEN coalesce(c.evidence_segment_id,'') <> '' THEN 1 ELSE 0 END) AS with_evidence,
  sum(CASE WHEN coalesce(c.normalized_value,'') <> '' THEN 1 ELSE 0 END) AS with_normalized,
  sum(CASE WHEN c.confidence = 'HIGH' THEN 1 ELSE 0 END) AS high_conf;
```

```cypher
// C7 T1 校验：normalized_text 应全空，这一条应返回 0
MATCH (s:SourceSegment) WHERE coalesce(s.normalized_text,'') <> ''
RETURN count(s) AS should_be_zero;
```

```cypher
// C8 T4 校验：人工填 MERGE 后才会出现「1 条经历挂多个来源」
MATCH (l:LifeEpisode)-[:SUPPORTED_BY_EVENT]->(e:EventNode)
WITH l, collect(e.event_id) AS sources
WHERE size(sources) > 1
RETURN l.episode_id, l.episode_name, l.review_status, sources;
```

```cypher
// C9 疑似同一经历（待你填 MERGE / KEEP_SEPARATE）
MATCH (l:LifeEpisode) WHERE l.review_status = 'NEEDS_REVIEW'
RETURN l.episode_id, l.episode_name, l.normalized_start, l.review_status;
```

### D. 双库对照与重导

在两个浏览器标签页（7485 Qwen / 7486 DeepSeek）各跑一次下面这条，
**两边事件数不同是正常的**（同一篇访谈 Qwen 5 条、DeepSeek 9 条），不是出错：

```cypher
MATCH (d:InterviewDocument)-[:HAS_EVENT]->(e:EventNode)
RETURN d.doc_id, d.title, count(e) AS events, collect(e.event_name) AS event_names;
```

`import.cypher` 全部用 `MERGE`，**重复执行不会建重复节点**，只会更新属性。
只有想彻底重导时才先清空（⚠️ 会删掉当前库全部数据，执行前确认端口是 7485 还是 7486）：

```cypher
// MATCH (n) DETACH DELETE n;
```

### E. 当前已知状态（2026-11-10 18:31）

| 项 | 状态 |
|---|---|
| Qwen 库 7485 | ✅ 已导入 1 份文档（`CHF-V1-03`）、5 个一级事件、33 个二级阶段、87 个原文片段 |
| DeepSeek 库 7486 | ⏳ 尚未建立；且 `BATCH02-DOC01` 的 `entity_time` 调用在 11-07／11-08／11-10 **连续三次 HTTP 500（上游错误）**，非命令问题 |
| 覆盖率 | `1.0000 / PASS`（`coverage_audit`） |
| 词表 | `segment_type` 8 值（含 `RECORDING_TIMESTAMP`）；`circumstance_kind` 严格 5 值 |
