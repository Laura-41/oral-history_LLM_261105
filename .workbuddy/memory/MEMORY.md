# 工程长期记忆：大模型标注1104

> 硬规则速查。完整事件、参数、复核数据见同目录 `YYYY-MM-DD.md` 与两份 SOP（`04_54份正式语料批处理/DeepSeek_51份分批运行SOP.md` §4.2、对等 Qwen SOP）。工程根 `/Users/yuqi/Desktop/硕士毕业论文/2609/0920_01/大模型标注1104`，路径均相对工程根。11-16 第五次精简（细节已移入日志）。

## 一、运行方式（最高优先）
大批量跑语料**只给可复制终端命令**，助手不在对话里长跑、不贴长日志；可做零 API 演练、前置核对、单次最小连通验证、读汇总、文档与登记表整理。命令含 `cd` 工程根、实时进度、日志落盘、失败即停、断点续跑。验证链路只用一份文档端到端跑通。**技术门禁通过 ≠ 内容放行**，放行仍需人工抽检 `experience_scope` 与逐字证据。重试参数由研究者裁决、助手不得擅改或反复劝阻。

## 二、批量入口
```bash
cd '/Users/yuqi/Desktop/硕士毕业论文/2609/0920_01/大模型标注1104'
bash scripts/run_batches_in_terminal.sh BATCH02                 # DeepSeek
MODEL=cuc/qwen bash scripts/run_batches_in_terminal.sh BATCH02 # Qwen
caffeinate -i env TIMEOUT=1800 MODEL=cuc/deepseek SKIP_AFTER=2 bash scripts/graph_run_all_in_terminal.sh
caffeinate -i env MODEL=cuc/qwen TIMEOUT=3600 SKIP_AFTER=2 ROUNDS=3 bash scripts/graph_retry_rounds_in_terminal.sh
```
- 通用：`python3 -u` + `tee`（日志含模型/时间/PID）、`caffeinate -i`、`pipefail`、`FAILED_CODE`；`DRY_RUN=1 AUTO_CONTINUE=1` 零 API 演练。无人值守连跑＝抽检后置，结果 `MODEL_CANDIDATE`、不入库不放行。
- `graph_run_all_in_terminal.sh`（`MODEL/TIMEOUT/DOCS/SKIP_AFTER/STAGE_ONLY`）：跳过已验收、续跑；失败写 `review_queue/graph_pending_<模型>.md`；有跳过文档**不导出 24 表、禁止入库**；`STAGE_ONLY=1` 后仍须补 `entity_time`；同模型不可并行。
- 参数：DeepSeek `TIMEOUT=1800`（11-13 裁）、Qwen `TIMEOUT=3600 SKIP_AFTER=2`。第 2 次重试捞回大部分，第 3 次以上无收益；外层有限轮次 + 轮间 `sleep 180`，禁无限 `while`。`graph_retry_rounds_in_terminal.sh` 默认 `WAIT_FOR_CURRENT=1` 防并行，按 `VALIDATION_report.json valid=true` 达 54 即停；Qwen 全量会自动重导 `import_cuc_qwen/` 24 表（备份产物、不入库）。
- 分段兜底旁路（**造好未启用，是否启用由研究者裁决**）：`scripts/graph_entity_time_split_fallback.py` + `graph_split_fallback_in_terminal.sh`；瓶颈是输出侧 `completion_tokens` 中位数 55,048、首 token 7.6 min，非文档长度。启用前停同模型主链，口径不同须方法章注明。

## 三、数据生产、双线与总账
- **现行图谱（11-13 19:10，优先于 18:50 的 54 份描述）**：6 份人工 Demo 已合进同一 DeepSeek 实例，`build_id=oral-history-all60-v1`，60 文档／479 事件／6327 片段／1834 阶段／1565 实体／377 生平／27573 节点／49872 关系。构建 `scripts/build_all60_import.py`（`--deploy`）、包 `05_合并与Neo4j/import_all60/`（24 CSV + `file:///all60_*` Cypher，**不覆盖**原 24 张），HTTP API 56/56。`data_role`＝`WORKFLOW_DEMO`+`CONFIRMED` 6 / `BATCH_APPLICATION`+`MODEL_CANDIDATE` 54。**红线**：两类统计不可相加，查询按 `d.data_role` 过滤、生平按 `DEMO-` 前缀；门户仍只接 6 份 Demo，看板 `HUMAN`/`OFFICIAL` 分开。**`documents.doc_id` 是语料 ID（`YYS-04`），`BATCH0X-DOC0Y` 只在 `event_id`／`segment_id`**。回退纯 54 份＝重跑 `import_cuc_deepseek/import.cypher`。查询口令 `05_合并与Neo4j/图谱查询口令_60份完整图谱.md`（23 条 23/23 通过；出图须 `RETURN` 节点/关系/路径变量，否则只有 Table/RAW）。一级=`EventNode`、二级=`ProcessStage`，`HAS_STAGE` 直连；`ALIAS_OF` 方向 EntityAlias→Entity。
- **60 份总账**：权威 `现行标注/00_模板/corpus_inventory.csv`（60 行），派生 `04_54份正式语料批处理/corpus_inventory_with_batches.csv`（60 行／19 列）。**60 = 6 人工 Demo + 54 正式（BATCH01 3 + BATCH02–07 51）**。**任何 CSV 不加新列**；BATCH01 `CHF-V1-02`／`CRT-03`／`YYS-02` 是正式语料，禁止再问是否纳入、禁止默认跳过。`documents.title` = docx 文件名去扩展名。
- **结果位置**：`04_54份正式语料批处理/document_consolidation/validated_json/<模型>/` 的 `consolidated_output.document_events`；人工 6 份在**上级** `现行标注/01_*`～`06_*`，原始语料在同级 `语料/`。
- **Qwen 只是备份，正式只用 DeepSeek 单线**：正式推进不等 Qwen、不把 Qwen 全量／导出／双模型对比写成前置条件；但 11-14 研究者要求 Qwen 终端「跑完一轮再跑一轮直到 54 份成功」，属备份线收尾（产物不入库、不计入模型对比、不动 all60）。终端由研究者决定停不停，助手不主动杀进程。保留 `model_id` 隔离／双线台账／双 Neo4j 实例；双线并行是进度冗余、非实验设计，单文档内不混用模型。
- **唯一例外（两份借 Qwen `entity_time`，非纯模型产出）**：`BATCH02-DOC09`(YYS-04)／`BATCH04-DOC09`(YYS-07)，11-13 18:31 授权按原文重映射后入图谱；备份 `_抽检修正备份_20261113_1831/`，报告 `review_queue/抽检与脚注核对报告_20261113.md` §四。语料转正式须重跑 DS 覆盖或方法章注明，不得计入模型对比。24 表 `review_status` 仍 `MODEL_CANDIDATE`。助手不得把此例外当常规、不得擅自移其它文档。
- **Neo4j 导入**：服务由研究者在终端启动；`cypher-shell` 被 macOS `com.apple.quarantine` 拒执行（126），改用 **HTTP API `POST /db/neo4j/tx/commit` 逐条提交 `import.cypher` 56 条**。两实例 Qwen 7485／7688、DeepSeek 7486／7689，ID 不加模型前缀；手册 `05_合并与Neo4j/双模型双图谱_Neo4j使用说明.md`。
- **登记表／台账**：`01_实验配置/实验登记表.csv` **18 列不变**、一行＝一次 API 调用；`scripts/backfill_experiment_registry.py` 默认预览、`--write` 追加，按 `(model_id, run_date, total_tokens)` 幂等；11-13 补登 477 行 → 648 行。`01_实验配置/双线批改台账.csv`（108 行／25 列）一行＝文档×模型，`scripts/build_review_ledger.py` 重建时人工列保留。**不要把文档级抽检／放行状态加进登记表列**。
- **协调**：11-06 起只用单一对话窗口；改 README／主流程文档／登记表前先读最新版，版本号按时间顺延。原始语料、冻结提示词／Schema、既有结果一律不改。

## 四、图谱层裁决（11-10）
- 全部裁决（R1／D1–D5／P0=A／E1–E4／T1–T4／超纲 115 条）已裁完；`document_consolidation/review/枚举词表与标注路线_裁决单_20261107.md` v3 无待填格子。
- **正式批次词表 v1.1**：`segment_type` 人工 7 值 + `RECORDING_TIMESTAMP`；`circumstance_kind` 严格人工 5 值（超纲就近归类、降 `LOW`、出清单）；`normalized_text` 全留空。版本只在契约／导入脚本注释／导出报告声明，**CSV 不加版本列**；24 张表名列名与 6 份 Demo 逐列一致。契约 `02_Schema与提示词/graph_enrichment_v1.0/graph_enrichment_contract_v1.0.md` **v1.0.7 §五·补三**含可写入方法章文字。区分契约 v1.0.7 与数据词表 v1.1。
- **D3 生平叠加**：语料层永不合并，疑似同一经历只标 `NEEDS_REVIEW`；只有研究者在 `04_54份正式语料批处理/human_adjudicated/<模型>/life_episode_merges.csv`（目录需手工建）填 `MERGE` 才生成叠加视图；不填合法。别填进 `document_consolidation/human_adjudicated/`。

## 五、可视化系统（11-12～13）
- **定位／四条拍板**：面向公众，接 AI API 据图谱有据回答并推荐采访原文（类 RAG）。只接 6 份人工 Demo；默认历史序、叙述序可切换；交叉入口共用查询层；跳跃度量化但**用户端零数字**（11-12 23:38 选 A 冻结：不改 `historical_order` 占位值、不升契约、不重跑，**不要再拿 A/B/C 去问**）。原型不展示双模型对照、不接大模型线数据。
- **`historical_order` 在大模型线是占位值（影响论文）**：`scripts/graph_build_base_tables.py:286-287` 两序同一 `index`；`event_times` 中 `precision=RELATIVE` 占 175/257。双时序**只在 6 份人工标注中真实存在**；论文不得把大模型线当独立历史序。助手不得擅自改提示词／契约／Schema／导入脚本或重跑。
- **数据源**：`现行标注/01_*`～`06_*`，每份 18 张非空 CSV + `annotation_bundle.json`，词表 v1.0、40 事件、3 位受访者（陈海峰 18／陈锐霆 15／杨永松 7）；字段以 Demo 实际列为准，别套 v1.1。
- **四板块**：A 问一问（AI 对话 + 动态悬浮图谱、引用角标／原文抽屉／推荐追问）、B 人生链路（逐站／自动漫游／10 个内联 SVG）、C 轨迹交叉（三条人生线，**只画自动检出的 4 处交集** 1931／1937／日军／中国共产党，明标「非受访者原话」）、D 口述史图谱（六项指标 + 内嵌科研工作台 + 独立看板入口）。导航 `#ask/#life/#cross/#research`；公众三板块**不含 τ／逆序对／归一化跳跃度**。
- **答案合成层**：`build_user_portal.py` 把 CAUSE／PURPOSE／MANNER、`evidence_segment_id` 逐字原话与 `event_next` 链带进 `DB.events`；模板 `buildChain()`／`composeOffline()`／`AnswerEngine.useLLM()`，`CURATED_ANSWERS` 含「陈锐霆为什么去参军」。**回答不是列表**；改完重跑该脚本。默认离线零 API，代理起来自动探测切真 `cuc/deepseek`（`PORTAL_MODEL=cuc/qwen` 可换），模型只把检索好的因果子图 + 逐字原话写成自然语言，失败回退离线；`cuc/qwen3-embedding` 只做向量检索。
- **一键启动与密钥隔离（硬规则）**：工程根 `一键启动大模型版.command`（`PORTAL_NO_BROWSER=1`／`--no-browser` 抑制）；页面同源探测 `http://127.0.0.1:8765`，`file://` 打开只要代理在跑也自动切真模型；代理 CORS 白名单（`Origin: null`／127.0.0.1／localhost）。**密钥只读** `CUC_API_KEY_FILE`、`CUC_API_KEY` 或钥匙串 `edu.cuc.openai.portal-key`；**严禁回退批处理旧条目 `edu.cuc.openai.api-key`**；取不到就明确提示并保持离线；`key_source()` 只报来源不报内容；密钥绝不写进 `归途·口述史记忆馆.html`。`scripts/api_test.py` 等批处理脚本一字未改、仍用旧条目。
- **文件架构与看板**：`06_可视化原型/归途·口述史记忆馆.html`（1.8 MB）由 `build_user_portal.py` + `user_portal_template.html` 生成，科研工作台经 `bench_assets()` → `<template id="benchTpl">` → Shadow DOM + `document` 垫片内嵌（规避 `DB`／`$`／`.view`／`:root` 冲突）；独立科研版已废弃。导师看板**分着管理**，只留 D 板块 iframe 入口；更新链路 `build_mentor_overview.py` → `build_mentor_dashboard.py` → `python3 scripts/build_user_portal.py --sync-boards-only`。看板原件 `document_consolidation/导师查看_事件总看板.html` 内嵌 `HUMAN`（人工 6 份 40 事件，**不是金标准**）与 `OFFICIAL` 两快照，「请勿混读」；只有 `SourceAttachment.function=EVIDENCE` 可作史实依据。`06_可视化原型/事件标注结果总看板.html` 与 `导师查看_事件一览.html` 是只读副本（原件哈希恒定 `eeebd3b6…`）。`portal_llm_server.py` 把 `/` 重写到中文名。
- **移动端适配 v3（硬约束）**：`user_portal_template.html` 末尾 `@media(max-width:640px)` 覆盖层是**手机端唯一改法**，桌面规则逐字节不动、可整层删除回退；栅格 `minmax(0,1fr)`、输入框 ≥16px、触控目标 ≥44px、`cross-tip` 仅 ≤640px。改完必须 CDP 390×844／360×800 双视口 + 桌面 44 项回归 + 边界验证三套全绿。横滑容器内元素越界是设计意图，判据只有页面级 `scrollWidth == innerWidth`。
- **资料库同步（长期授权）**：资料库已存在且本地有对应成品的文件，本地改完后助手**自行同步到同一节点**（不新建同名条目、标题链接不变），不必逐次确认；同步后回读验证并告知链接。**不落盘备份、不建 `library_backups`**；资料库无版本回滚、助手无删除节点 API，本地成品即唯一权威源。更新前只在内存／`/tmp` 工作副本自检，用完即删。`kind=web` 走 Page 事务（create→基线→换工作副本→自检→upload→commit），平台注入约 15 KB 属正常，用规范化比对；密钥绝不写入上传产物。导师手机要真大模型须同一 WiFi 开 `http://<局域网IP>:8765/`。

## 六、新需求（11-16）
桌面 `吴裕泰知识图谱.docx` 是**老字号知识图谱**的独立新需求（非本工程语料线），提出者不熟悉图谱；已定五种分类为一级节点，二级含标签／属性，另有 10 条关系定义表。剖析结论与本体建议见当日日志／对话产物；**不要把它并入口述史图谱工程或改写既有冻结资产**。
- **唯一权威目录**：`~/Desktop/作业/研 2026秋/1116老字号论文/261116第一次讨论/吴裕泰知识图谱/`（桌面旧副本已由研究者移走）。5 项裁决已全部定稿，版本 v2.2；预览图展示层 v2.3（中式宣纸/朱印/宋体，配色唯一入口＝`ontology_gene_type.csv` 的 `color` 列，改后跑 `python3 build_preview.py`）。细节见当日日志。
- **资料库长期自动同步（研究者 11-16 明确要求「之后每次改动你自己记得更新」）**：本地预览图 `吴裕泰知识图谱_样例预览.html` 每次改动后，助手**自行同步到同一资料库节点、不新建、链接不变**，无需逐次确认。节点 `nodeId=R2ApQUQ81H5JdeFsChrowi`（`kind=web`，个人空间 `biCLRufJnbdkZlU4X7sNFp` 根），链接 `https://www.workbuddy.cn/space/d/R2ApQUQ81H5JdeFsChrowi`。走 library 的 Page 事务：`prepare_page_edit.py` 建基线 → 本地成品覆盖工作副本 → `finalize_page_edit.py --check-only` 预检 → 语义审查 → 提交（平台自动重新注入 inject.js 与 pnid，约 2–15 KB 属正常）。**提交后必须再跑 `page/publish_page.py --node-id …` 重新发布**——否则只更新了编辑态，用户打开的 `/space/d/...?preview=1` 走的是**发布快照**，仍是旧版（11-16 踩过：提交后编辑态已是新版、发布态仍黑色）。发布链接 `https://workbuddy.link/p/R2ApQUQ81H5JdeFsChrowi`，重新发布链接不变。同步后用 `download_page_artifacts.py --source publish` 回读发布态验证（不是只验导出/编辑态）。同步范围仅此 HTML 成品；README/CSV/Cypher 等不上传。
