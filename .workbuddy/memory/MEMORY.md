# 工程长期记忆：大模型标注1104

> 硬规则速查。完整事件、参数、复核数据见同目录 `YYYY-MM-DD.md` 与两份 SOP（`04_54份正式语料批处理/DeepSeek_51份分批运行SOP.md` §4.2、对等 Qwen SOP）。工程根 `/Users/yuqi/Desktop/硕士毕业论文/2609/0920_01/大模型标注1104`，路径均相对工程根。11-13 19:10 第四次精简。

## 一、运行方式（最高优先）

大批量跑语料**只给可复制终端命令**，助手不在对话里长跑、不贴长日志；可做零 API 演练、前置核对、单次最小连通验证、读汇总、文档与登记表整理。验证链路只用一份文档端到端跑通。命令含 `cd` 工程根、实时进度、日志落盘、失败即停、断点续跑。放行仍需人工抽检 `experience_scope` 与逐字证据。

## 二、批量入口与图谱层编排

```bash
cd '/Users/yuqi/Desktop/硕士毕业论文/2609/0920_01/大模型标注1104'
bash scripts/run_batches_in_terminal.sh BATCH02                  # DeepSeek
MODEL=cuc/qwen bash scripts/run_batches_in_terminal.sh BATCH02  # Qwen
caffeinate -i env TIMEOUT=1800 MODEL=cuc/deepseek SKIP_AFTER=2 bash scripts/graph_run_all_in_terminal.sh
```
- `python3 -u` + `tee`（日志含模型/时间/PID）、`caffeinate -i`、`pipefail`、`FAILED_CODE` 传出非零码；`DRY_RUN=1 AUTO_CONTINUE=1` 零 API 演练。无人值守连跑＝抽检后置，结果 `MODEL_CANDIDATE`、不入库不放行。
- 图谱层 `graph_run_all_in_terminal.sh`（`MODEL/TIMEOUT/DOCS/SKIP_AFTER/STAGE_ONLY`）：跳过已验收、重跑续跑；仍失败写 `review_queue/graph_pending_<模型>.md`；有跳过文档**不导出 24 表、禁止入库**；`STAGE_ONLY=1` 后仍须补 `entity_time`；同模型两条命令不可并行。
- **重试参数由研究者裁决、助手不得擅改或反复劝阻**：DeepSeek `TIMEOUT=1800`（11-13 01:40 裁）、Qwen `TIMEOUT=3600 SKIP_AFTER=2`。09:52 结论：1800 首轮成功率 57%（1200 基线 33%），但提升来自后半夜 API 不拥堵，非多等 10 分钟；脚本第 54 行旧文案不影响生效值。当场第 2 次重试捞回大部分，第 3 次以上无收益；外层有限轮次 + 轮间 `sleep 180`，禁无限 `while`。
- **分段兜底旁路（15:40 造好、未启用）**：`scripts/graph_entity_time_split_fallback.py` + `scripts/graph_split_fallback_in_terminal.sh`，按片段切 N 段、同提示词同模型分别调用、确定性合并成同构 raw；下游原样生效，冻结资产与既有结果一字未改，零 API 预演 + `--selftest` 8 项通过。归因：瓶颈是输出侧 `completion_tokens` 中位数 55,048、首 token 7.6 min，非文档长度。**是否启用由研究者裁决**，启用前停同模型主链；口径不同须方法章注明、仍 `MODEL_CANDIDATE`。

## 三、数据生产、双线与总账（现行状态）

- **【11-13 19:10 现行图谱状态，优先于下方 18:50 的 54 份描述】已把 6 份人工 Demo 合进同一 DeepSeek 实例，60 份完整库**：`build_id=oral-history-all60-v1`，60 文档／479 事件／6327 片段／1834 阶段／1565 实体／377 生平／27573 节点／49872 关系。`data_role`＝`WORKFLOW_DEMO`+`CONFIRMED` 6 / `BATCH_APPLICATION`+`MODEL_CANDIDATE` 54。构建脚本 `scripts/build_all60_import.py`（`--deploy` 部署）、新包 `05_合并与Neo4j/import_all60/`（24 CSV + `file:///all60_*` 的 Cypher，**不覆盖** `import_cuc_deepseek/` 原 24 张），HTTP API 56/56 成功。合库顺带补齐此前为 0 的 `BiographicalSubject`(3)／`INTERVIEW_OF`(60)／`HAS_LIFE_EPISODE`(377)——正式 `entities.csv` 缺 `PER-CHF/CRT/YYS`，人工 Demo 提供了这三个共享人物实体。**红线**：两类数据统计不可相加，查询按 `d.data_role` 过滤、生平按 `DEMO-` 前缀区分；门户仍只接 6 份人工 Demo，看板 `HUMAN`/`OFFICIAL` 仍分开。**`documents.doc_id` 是语料 ID（`YYS-04`），技术编号 `BATCH0X-DOC0Y` 只在 `event_id`／`segment_id` 里**，写 `d.doc_id='BATCH02-DOC09'` 返回空。回退纯 54 份＝重跑 `import_cuc_deepseek/import.cypher`。详见报告 §六、手册 §九。**可复制查询口令**：`05_合并与Neo4j/图谱查询口令_60份完整图谱.md`（23 条出图 Cypher 已逐条实跑 23/23 通过；按人物/文档/一级二级事件/实体分类 + B1+ 人生链路→支撑事件→文档实际链路 + 白底截图风格 GRASS）；出图关键是 `RETURN` 节点/关系/路径变量而非属性列，否则 Browser 只有 Table/RAW。一级=EventNode、二级=ProcessStage，`HAS_STAGE` 直连非父子事件；`ALIAS_OF` 方向 EntityAlias→Entity；全库 377 生平→377 事件→60 文档无断链。
- **60 份总账**：权威 `现行标注/00_模板/corpus_inventory.csv`（60 行），派生 `04_54份正式语料批处理/corpus_inventory_with_batches.csv`（60 行／19 列）。**60 = 6 人工 Demo + 54 正式（BATCH01 3 + BATCH02–07 51）**。**任何 CSV 不加新列**。BATCH01 `CHF-V1-02`／`CRT-03`／`YYS-02` 是正式语料，禁止再问「要不要纳入」、禁止默认跳过 `BATCH01-*`。`documents.title` = docx 文件名去扩展名，结果文件名 `BATCH0X-DOC0Y` 靠总账反查。
- **最终结果位置**：`04_54份正式语料批处理/document_consolidation/validated_json/<模型>/` 的 `consolidated_output.document_events`；人工 6 份 Demo 在**上级目录** `现行标注/01_*`～`06_*`，原始语料在同级 `语料/`。
- **【17:51 最高优先裁决】Qwen 只是备份，正式只用 DeepSeek 单线**：不等 Qwen、不要求跑完 54 份、不补跑其 BATCH04-DOC02/03/04、不把 Qwen 全量／导出／双模型对比写成任何前置条件；Qwen 终端由研究者决定停不停，助手不主动杀进程。数据不删不改：`model_id` 隔离、双线台账、双 Neo4j 实例原地保留。旧「双线完整全量／不得缩小双跑规模」仅作历史。双线并行本是进度冗余、非学术实验设计，单文档内不混用模型。
- **【16:20 唯一例外 → 18:31 修正 → 18:50 入库】** 测试语料前提下，仅 `BATCH02-DOC09`(YYS-04)／`BATCH04-DOC09`(YYS-07) 两份借 Qwen `entity_time`：只搬 `raw/entity_time_*_FROM_QWEN.json`，用 DS 原有 `graph_apply_enrichment.py`／`graph_validate_bundle.py` 重生成 18 表，实体 ID 统一 `E001…`，`parse`→验收→`graph_export_import.py --model cuc/deepseek --write` 导 24 表。
  - 18:00 抽检发现时间按事件编号错贴（Qwen 切 9 事件 / DS 切 12 事件）：「12月底」挂到肖华报告、「解放以后」挂到 1938 年事件。**18:31 研究者授权「按正确结果修改后进入图谱」**，已按原文重映射（`12月底`→DE007、`过了年以后`→DE009、`大概2月几号，五六号`→DE010，删 3 条无据占位与「解放以后」）、清空两处非 ISO 归一、删 BATCH04 无逐字依据别名 A003「师直属政治处」；存疑的封闭枚举／D5 口径项不改。备份 `_抽检修正备份_20261113_1831/`，报告 `review_queue/抽检与脚注核对报告_20261113.md` §四 + `时间重映射对照表_抽检修正_20261113.csv`。**全量 54/54 valid=true、24 表齐全、`documents.csv` 54 行**。
  - 18:50 已导入 DeepSeek 独立 Neo4j：研究者终端启动服务（`Started.`），助手用 **HTTP API `POST /db/neo4j/tx/commit` 逐条提交 `import.cypher` 的 56 条语句（56/56 成功）**——因 `cypher-shell` 带 `com.apple.quarantine` 被 macOS 拒执行（126 `Operation not permitted`）。未改 CSV／脚本／校验规则，清库只作用本实例。图谱 **54 文档／439 事件／5638 片段／1715 阶段／1260 实体／337 生平／38088 关系**，`build_id=oral-history-batch-cuc_deepseek-v1`，浏览器 <http://localhost:7486>。日后启动服务仍由研究者在终端完成；cypher-shell 仍被挡就沿用 HTTP API（报告 §五）。
  - **口径红线**：两份 `entity_time` 借自 Qwen 且经人工重映射，**非纯模型产出**；语料转正式须重跑 DS 覆盖或方法章注明，不得计入模型对比统计。24 表 `review_status` 仍 `MODEL_CANDIDATE`（字段取值，与放行裁决两件事）。16:20 备份 `_qwen_import_backup_20261113_1620/` 含零删除回退脚本（未执行）。助手不得把此例外当常规、不得擅自移其它文档。
- **登记表／台账**：`01_实验配置/实验登记表.csv` **18 列不变**、一行＝一次 API 调用；`scripts/backfill_experiment_registry.py` 默认预览、`--write` 追加，按 `(model_id, run_date, total_tokens)` 幂等，只填客观字段。11-13 已补登 477 行 → 648 行。`01_实验配置/双线批改台账.csv`（108 行／25 列）一行＝文档 × 模型，`scripts/build_review_ledger.py` 重建时人工列保留。**不要把文档级抽检／放行状态加进登记表列**。`run_deepseek_batch.py` 按模型生成价格／超时，汇总含 `price_basis`。
- **协调**：11-06 起只用单一对话窗口；改 README／主流程文档／登记表前先读最新版，版本号按时间顺延。原始语料、冻结提示词／Schema、既有结果一律不改。技术门禁通过 ≠ 内容放行。

## 四、图谱层裁决（11-10）

- 全部裁决（R1／D1–D5／P0=A／E1–E4／T1–T4／超纲 115 条）已裁完；`document_consolidation/review/枚举词表与标注路线_裁决单_20261107.md` 为 v3、无待填格子。
- **正式批次词表 v1.1**：`segment_type` 人工 7 值 + `RECORDING_TIMESTAMP`；`circumstance_kind` 严格人工 5 值（超纲就近归类、降 `LOW`、出清单）；`normalized_text` 全留空。版本只在契约／导入脚本注释／导出报告全局声明，**CSV 不加版本列**；24 张表名列名与 6 份 Demo 逐列一致。契约 `02_Schema与提示词/graph_enrichment_v1.0/graph_enrichment_contract_v1.0.md` **v1.0.7 §五·补三**含可写入方法章的文字。区分「契约 v1.0.7」与「数据词表 v1.1」。
- **D3 生平叠加**：语料层永不合并，疑似同一经历只标 `NEEDS_REVIEW`；只有研究者在 `04_54份正式语料批处理/human_adjudicated/<模型>/life_episode_merges.csv`（目录需手工建）填 `MERGE` 才生成叠加视图。不填合法、图谱照常能导；别填进 `document_consolidation/human_adjudicated/`。
- **两个独立 Neo4j 实例**（P0=A）：Qwen 7485／7688、DeepSeek 7486／7689，ID 不加模型前缀；手册 `05_合并与Neo4j/双模型双图谱_Neo4j使用说明.md`。

## 五、可视化系统（11-12～13）

- **定位**：面向公众的产品——接 AI API 后问「陈海峰年轻时都做过什么？」，据图谱有据回答并推荐采访原文（类 RAG），用户不看复杂原文访谈；不把证据链／双时序／裁决状态当首屏主角。
- **四条拍板**：只接 6 份人工 Demo；默认历史序、叙述序可切换；交叉入口共用查询层；跳跃度做量化但**用户端零数字**（11-12 23:38 选 A 冻结：不改 `historical_order` 占位值、不升契约、不重跑，**不要再拿 A/B/C 去问**）。正式只用 DeepSeek 单线（见三），不得删 `model_id` 隔离／双实例／双线台账；原型不展示双模型对照、不接大模型线数据。
- **`historical_order` 在大模型线是占位值（影响论文）**：`scripts/graph_build_base_tables.py:286-287` 两序都赋同一 `index`；`event_times` 中 `precision=RELATIVE` 占 175/257。双时序**只在 6 份人工标注中真实存在**。论文不得把大模型线当独立历史序；助手不得擅自改提示词／契约／Schema／导入脚本或重跑。
- **数据源**：`现行标注/01_*`～`06_*`，每份 18 张非空 CSV + `annotation_bundle.json`，词表 v1.0、40 事件、实为 **3 位受访者**（陈海峰 18／陈锐霆 15／杨永松 7）。字段以 Demo 实际列为准，别套 v1.1。
- **四板块**：A「问一问」AI 对话 + 动态悬浮图谱（引用角标／原文抽屉／推荐追问）；B「人生链路」插画轨迹（逐站／自动漫游／10 个内联 SVG）；C「轨迹交叉」三条人生线，**只画自动检出的 4 处交集** 1931／1937／日军／中国共产党，明标「非受访者原话」；D「口述史图谱」六项指标 + 内嵌科研工作台 + 独立看板入口。导航 `#ask/#life/#cross/#research`，有熄灯夜读。公众三板块**不含 τ／逆序对／归一化跳跃度**。
- **答案合成层**：`build_user_portal.py` 把 CAUSE／PURPOSE／MANNER、其 `evidence_segment_id` 逐字原话与 `event_next` 链带进 `DB.events`；模板有 `buildChain()`／`composeOffline()`／`AnswerEngine.useLLM()`／依据链小卡／动态追问，`CURATED_ANSWERS` 含「陈锐霆为什么去参军」。**回答不是列表**；改完重跑该脚本。默认离线零 API，启动本机代理后自动探测切真 `cuc/deepseek`（`PORTAL_MODEL=cuc/qwen` 可换），模型只把检索好的因果子图 + 逐字原话写成自然语言，`[n]` 由页面转角标，失败回退离线。`cuc/qwen3-embedding` 只做向量检索、不用于对话。此接入只服务原型，与 54 份生产无关。
- **一键启动与密钥隔离（硬规则）**：工程根 `一键启动大模型版.command`（`PORTAL_NO_BROWSER=1`／`--no-browser` 可抑制）。页面同源探测 `http://127.0.0.1:8765`，`file://` 打开只要代理在跑也自动切真模型；代理 CORS 白名单（`Origin: null`／127.0.0.1／localhost，非本机 POST 403）。**密钥只读** `CUC_API_KEY_FILE`、`CUC_API_KEY` 或钥匙串 `edu.cuc.openai.portal-key`；**严禁回退批处理旧条目 `edu.cuc.openai.api-key`**，取不到就明确提示并保持离线；`key_source()` 只报来源不报内容。助手不得加回旧密钥兜底；密钥绝不写进 `归途·口述史记忆馆.html`。`scripts/api_test.py` 等批处理脚本一字未改、仍用旧条目。
- **文件架构与看板**：`06_可视化原型/归途·口述史记忆馆.html`（1.8 MB）由 `build_user_portal.py` + `user_portal_template.html` 生成，科研工作台经 `bench_assets()` → `<template id="benchTpl">` → Shadow DOM + `document` 垫片内嵌，规避 `DB`／`$`／`.view`／`:root` 冲突；独立科研版已废弃。导师看板**分着管理**，不内嵌门户主页，只留 D 板块 iframe 入口；更新链路 `build_mentor_overview.py` → `build_mentor_dashboard.py` → `python3 scripts/build_user_portal.py --sync-boards-only`。看板原件 `document_consolidation/导师查看_事件总看板.html`（959 KB）内嵌 `HUMAN`（人工 6 份 40 事件，`WORKFLOW_DEMO`，**不是正式测试金标准**）与 `OFFICIAL`（`MODEL_CANDIDATE`）两份快照，两视图自写「请勿混读」；只有 `SourceAttachment.function=EVIDENCE` 可作史实依据，两层逐字数量不可相加。`06_可视化原型/事件标注结果总看板.html` 与 `导师查看_事件一览.html` 是只读主题适配副本（原件哈希恒定 `eeebd3b6…`）。`portal_llm_server.py` 把 `/` 与 `/index.html` 重写到中文名。
- **验证累积**：21 + 27 项交互测试、CDP 离线 18 + LLM 8 项、五种打开方式、3 个内联脚本 `node --check`、明暗主题截图、无明文密钥核对通过；细节见日志。
- **移动端适配 v3（11-13 21:58，硬约束）**：`user_portal_template.html` 末尾 `@media(max-width:640px)` 覆盖层是**手机端唯一改法**，桌面基础规则逐字节不动、可整层删除回退；栅格必须 `minmax(0,1fr)`（否则 min-content 撑成 374.891px 裁掉卡片），输入框 ≥16px 防 iOS 缩放，触控目标 ≥44px，`cross-tip` 只在 ≤640px 显示。改完必须同时跑 CDP 390×844／360×800 双视口诊断、桌面 44 项回归、边界验证三套全绿。`presets`／`lifeSvg`／`crossSvg` 横滑容器内的元素越界是设计意图、不是溢出 bug，判据只有页面级 `scrollWidth == innerWidth`。门户资料库 v4 已同步（本地成品 SHA `238a996c…8ea4e`）。
- **资料库同步（11-13 05:07 授权、05:12 修订，长期生效）**：资料库已存在且本地有对应成品的文件，本地改完后助手**自行同步到同一节点**（不新建同名条目、标题链接不变），不必逐次确认；同步后回读验证并告知链接。**不落盘备份、不建 `library_backups` 目录**（研究者怕占空间）；资料库无版本回滚、助手无删除节点 API，本地成品即唯一权威源。更新前只在内存／`/tmp` 工作副本自检，用完即删。`kind=web` 走 Page 事务（create → 基线 → 换工作副本 → 自检 → upload → commit）；平台注入 `data-page-node-id`／`inject.js`（多约 15 KB），线上与本地逐字节不等属正常，用规范化比对。密钥绝不写入上传产物。导师手机要真大模型仍须同一 WiFi 开 `http://<电脑局域网IP>:8765/`。
