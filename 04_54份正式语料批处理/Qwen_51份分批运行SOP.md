# Qwen 主线后续51份分批运行 SOP

> 版本：v1.0　日期：2026-11-06
> 接口：`cuc/qwen`（学校 OpenAI 兼容 `/v1/chat/completions`）
> 运行线标记：`QWEN_MAIN_TRACK`；与 `DeepSeek_51份分批运行SOP.md` 的 `DEEPSEEK_PARALLEL_TRACK` 并行。
> **两条线共用同一套冻结提示词、Schema、输出契约 v0.3、校验器和同一份分窗输入**，只有 `--model` 不同；结果严格按 `cuc_qwen` / `cuc_deepseek` 目录隔离，同一份文档内绝不混用两个模型的窗口候选。
> 运行方式：大批量语料一律由**研究者在本地终端自行启动**，助手只给可复制命令，不代为长跑、不回贴长日志（工程约定，见 §3）。

---

## 📍 先看这里：语料与结果位置地图

工程根目录：`/Users/yuqi/Desktop/硕士毕业论文/2609/0920_01/大模型标注1104`

| 想找什么 | 绝对路径 |
|---|---|
| 60份原始语料（只读） | `/Users/yuqi/Desktop/硕士毕业论文/2609/0920_01/语料/` |
| 人工标注6份 Demo（参考基准） | `/Users/yuqi/Desktop/硕士毕业论文/2609/0920_01/现行标注/` |
| **★ Qwen 机器标注最终结果** | `04_54份正式语料批处理/document_consolidation/validated_json/cuc_qwen/`，每份一个 JSON，看 `consolidated_output.document_events` |
| 每批总账、日志、成本 | `04_54份正式语料批处理/batchNN_summary_cuc_qwen.md`/`.json`、`04_54份正式语料批处理/run_logs/`、`01_实验配置/实验登记表.csv` |
| 双模型分开批改 | `01_实验配置/双线批改台账.csv`（一行 = 文档 × 模型） |

人工改判写在 `document_consolidation/human_adjudicated/cuc_qwen/`，**自动结果永久不改**。`inputs/`、`raw_responses/`、`validated_json/`、`review_queue/`、`document_consolidation/inputs/` 都是中间产物，不是结论。

---

## 0. 这条线的定位：进度冗余，不是抽样实验

研究者 2026-11-06 明确：Qwen 效果更好但不稳定、耗时长，DeepSeek 稳但偏保守；因此**一份作业让两个模型各自独立做完整一遍，不怕重复、token 足够、不以成本或样本量缩小双跑规模**，研究者当老师分别批改、分开归档。谁先交、谁崩了都不耽误进度。

本轮具体安排：**先让两个模型各跑一批（BATCH02）做同题对比，再决定后续是继续双跑、针对性调整，还是选一个模型跑完剩下的**。这是分批放行（每批人工抽检后才能进下一批），不是把对照样本缩小。

Qwen 当前进度：

- `BATCH01-DOC03`：4/4 窗口通过、12 候选 → 7 文档事件；`DE004`「他教我们喊话」已由研究者人工裁决改判为 `NARRATED_CONTEXT`，裁决单在 `document_consolidation/review/BATCH01-DOC03_cuc_qwen_DE004_人工裁决.md`。
- `BATCH01-DOC01` / `DOC02`：按研究者 20:41 决定**暂缓**，尚未跑 Qwen。
- `BATCH02`：Qwen 目前 0 个窗口、0 份文档级结果；DeepSeek 已完成 `BATCH02-DOC01`（5 窗口 + 归并），重跑该批时会自动跳过已完成部分，属正常断点续跑，不是漏跑。

DeepSeek SOP §0–§2 描述的「清单 → 分窗 → 文档级归并」通用化改造对两条线同时生效，本文件不重复。

## 1. 两个终端并行跑：可行性与隔离清单

**结论：可行，无写入冲突。** 逐个写入点核查如下（2026-11-06 21:26 核对当前脚本）：

| 写入点 | 路径 | 隔离方式 |
|---|---|---|
| 窗口原始响应 | `raw_responses/<模型>/` | 按 `safe_model_name(model)` |
| 窗口技术通过结果 | `validated_json/<模型>/` | 同上；**断点续跑也按模型判断**，Qwen 不会因 DeepSeek 已完成而跳过 |
| 跨窗口复核队列 | `review_queue/<模型>/<文档>.json` | 按模型 |
| 文档级输入包 | `document_consolidation/inputs/<模型>/` | 按模型，且包内写 `source_model_id` |
| 文档级清单 | `document_consolidation/manifest_<模型>.csv` | 按模型 |
| 文档级原始响应／结果／归档 | `raw_responses/<模型>/`、`validated_json/<模型>/`、`validated_history/<模型>/` | 按模型 |
| 批次技术汇总 | `batchNN_summary_<模型>.json` / `.md` | 按模型 |
| 终端全程日志 | `run_logs/BATCHNN_<模型>_<时间戳>_pid<PID><_dryrun>.log` | 按模型＋时间戳＋进程 PID，两个终端同一秒启动也不撞名 |

`run_document_consolidation.py` 会校验输入包的 `source_model_id` 与运行模型一致，**Qwen 归并程序读不到 DeepSeek 的窗口候选**，反之亦然。

**两个终端共享、但只读的文件**（这正是"同题对照"成立的前提）：

- `inputs/BATCHNN-DOCMM-Wxxx.json`：模型无关的中立分窗输入包，**两个模型读完全相同的窗口和原文片段**；
- `batchNN_manifest.csv` / `batchNN_documents.json` / `batchNN_source_segments.jsonl`；
- `02_Schema与提示词/` 下全部冻结提示词与 Schema。

**批完后只在一个终端各跑一次**（两个终端同时写会冲突）：

```bash
python3 scripts/backfill_experiment_registry.py --write   # 追加调用级登记行
python3 scripts/build_review_ledger.py                    # 刷新文档级台账
```

### 1.1 代码查不到、需要你在终端观察的三个风险

1. **学校 API 同一密钥的并发限制**：两个进程同时请求可能触发 429 或排队变长。Qwen 本就不稳，若超时／429 明显变多，暂停一条线错峰跑，结果不受影响（断点续跑）。
2. **两条线不会同步完成**：同一份 DOC03 实测首 Token 均值 Qwen 385s vs DeepSeek 138s，费用 ¥2.3981 vs ¥0.4255（约 5.6 倍）。Qwen 整批会慢数小时，不必等齐再批改，谁先跑完先抽检。
3. **Qwen 长推理可能看起来"卡住"**：首 Token 实测最大 587s、文档级归并约 552s。先 `tail -f <日志>` 看一眼，别急着 Ctrl+C。超时已按模型放宽到窗口 1800s / 文档 2400s。

## 2. 按模型的运行参数

编排器脚本名虽是 `run_deepseek_batch.py`（历史命名），但已通用化，**按 `--model` 工作，Qwen 也用它**；文件名、docstring 里的 "DeepSeek" 只是遗留字样，不影响输出口径。

| | `cuc/deepseek` | `cuc/qwen` |
|---|---|---|
| 运行线标记 | `DEEPSEEK_PARALLEL_TRACK` | `QWEN_MAIN_TRACK` |
| 估算单价（输入／输出，每百万 Token） | ¥1／¥4 | ¥3／¥18 |
| 窗口级／文档级超时 | 600s／900s | 1800s／2400s |
| 汇总 | `batchNN_summary_cuc_deepseek.*` | `batchNN_summary_cuc_qwen.*` |

汇总里有 `price_basis` 写明所用单价；`run_track` 按模型生成，不会把 Qwen 结果标成 DeepSeek 支线。

## 3. 前置检查（零 API，可反复跑）

```bash
cd '/Users/yuqi/Desktop/硕士毕业论文/2609/0920_01/大模型标注1104'

# 核对批次文件与命令链（两条线各一次）
DRY_RUN=1 AUTO_CONTINUE=1 bash scripts/run_batches_in_terminal.sh BATCH02
DRY_RUN=1 AUTO_CONTINUE=1 MODEL=cuc/qwen bash scripts/run_batches_in_terminal.sh BATCH02
```

`batch02_manifest.csv`、`batch02_documents.json`、`batch02_source_segments.jsonl` 已存在，不需要重跑 `prepare_batch_from_inventory.py`。密钥程序先读环境变量 `CUC_API_KEY`，再读 macOS 钥匙串；**不要写进任何文件，也不要贴进对话窗口**。

最小连通验证（可选，约 50 Token，把 DeepSeek SOP §3 那段里的 `model` 改成 `cuc/qwen` 即可）。

## 4. 两个终端：可直接复制的命令

**终端 A —— DeepSeek 支线**

```bash
cd '/Users/yuqi/Desktop/硕士毕业论文/2609/0920_01/大模型标注1104'
bash scripts/run_batches_in_terminal.sh BATCH02
```

**终端 B —— Qwen 主线**

```bash
cd '/Users/yuqi/Desktop/硕士毕业论文/2609/0920_01/大模型标注1104'
MODEL=cuc/qwen bash scripts/run_batches_in_terminal.sh BATCH02
```

两个终端可同时启动（日志已带 PID，不必刻意错开）。另开窗口 `tail -f '04_54份正式语料批处理/run_logs/<对应日志名>'` 看进度。脚本会：`python3 -u` 实时输出＋`tee` 落盘、`caffeinate -i` 防休眠、`set -o pipefail` 失败即停、每批结束暂停等人工抽检（按回车才进下一批）。Ctrl+C 随时停，**同一命令重跑即断点续跑**，互不干扰。

若不用终端脚本，等价的单批原命令：

```bash
mkdir -p "04_54份正式语料批处理/run_logs"
python3 -u scripts/run_deepseek_batch.py --model cuc/qwen --batch BATCH02 \
  2>&1 | tee "04_54份正式语料批处理/run_logs/BATCH02_cuc_qwen_$(date +%Y%m%d_%H%M%S).log"
```

只想先做单份端到端验证时（**不改变全量双跑的安排，只是先后顺序**）：

```bash
python3 scripts/run_deepseek_batch.py --model cuc/qwen --batch BATCH02 --only-document BATCH02-DOC01
```

## 5. 熔断与放行（与 DeepSeek SOP §6 完全相同）

技术门槛由汇总自动检查 6 项：窗口 JSON/Schema 全通过、通过率 ≥95%、片段覆盖 100%、边缘候选入队、原始响应与 Token 已保存、文档级归并全通过。**内容门槛必须人工完成**，程序一律标 `MANUAL_REVIEW_REQUIRED`：逐份打开 `document_consolidation/validated_json/cuc_qwen/<技术ID>.json`，抽检 `experience_scope`、`participation_bases` 与 `scope_evidence_quote`，确认没有把集体战斗、部队沿革、历史背景成批写成受访者个人经历。

Qwen 已知倾向（DOC03 实测），抽检时重点盯：

- **多召回但边界偏宽**：`DE002` 一个事件吞 22 个片段、`DE001` 把部队集结动员纳入个人经历；
- **接受者关系误判参与**：`DE004`「他教我们喊话」被判个人经历，而契约 v0.3 §1.1 明确"只有接受者关系不足以证明本人参与"；
- **复核不够保守**：`DE007` 直接 `AUTO_VALIDATED`，DeepSeek 则保留了本人角色的复核。

DeepSeek 的倾向相反（保守易漏，DOC03 有实质内容被判"未分配"）。**两份交叉核对正好能同时抓"漏"和"错"**，这正是双跑的实用价值。

## 6. 一批跑完怎么对比（老师分别批改）

先在一个终端跑一次 §1 末尾的两条命令。台账 `paired_model_submitted` 会自动标出哪些文档两个模型都交了卷，直接筛即可。然后逐文档按这张清单核对：

| 层次 | 看什么 |
|---|---|
| 技术 | 窗口数、候选数、片段覆盖、JSON/Schema、原始响应是否齐全 |
| 文档级 | 事件总数、个人／背景／不确定／待复核分布 |
| **范围判定** | 逐事件比 `experience_scope` + `participation_bases` + `scope_evidence_quote`；尤其「他教我们」「我们部队」「我不在现场」这类接受者／集体／转述表述 |
| 归并粒度 | 单事件覆盖片段数、是否把本人任务与转述战斗揉成复合事件 |
| 召回 | 某模型独有片段是否为实质内容遗漏，还是背景议论膨胀 |
| 工程 | Token、费用、耗时、失败与重试 |

结论落在两处：`01_实验配置/双线批改台账.csv` 的人工列（`human_review_status`／`release_status`／`notes`），以及 `document_consolidation/review/` 下的抽检 md。若需改判，写 `document_consolidation/human_adjudicated/cuc_qwen/` 的独立视图，**原始模型输出一个字节都不改**（DE004 已示范这套做法）。

## 7. 一批之后「针对性修改」或「只选一个模型」的口径要求

- **只选模型、不改规则**：可以直接继续。此后数据集中部分文档有两份、部分只有一份，入库必须带 `model_id` / `run_id`，论文方法章如实写明即可。
- **改提示词／契约／Schema／校验器**：属于规则升级，必须升版本号并写明生效批次。更要紧的是——**已跑的 BATCH02 与新规则口径不一致**：要么两条线都按新规则重跑 BATCH02 才能继续做同题对照，要么把 BATCH02 单列为旧版本样本、不纳入对比。不能悄悄改，否则"两个模型对比"会变成"两套规则对比"，结论失效。
- 任何情况下：**同一份文档不得拼接两个模型的窗口候选**。Qwen 中途崩了，就用 DeepSeek 整份重跑，不拿几个窗口补进去。
- 若最终确定 Qwen 为主线，`BATCH01-DOC01` / `DOC02` 的 Qwen 回归仍待补跑以完成首批 3 份闭环（由研究者决定时机）。

## 8. 常见问题

| 现象 | 处理 |
|---|---|
| 429 / 请求超时 | 同一命令断点续跑；必要时暂停一条线错峰。Qwen 超时已是 1800/2400，仍不够可直接给编排器加 `--window-timeout` |
| Qwen 长时间无输出 | 先 `tail -f` 看日志，首 Token 最长约 587s 属已知范围 |
| 想确认没串数据 | 看 `document_consolidation/inputs/cuc_qwen/` 包内 `source_model_id`，以及汇总里的 `run_track` |
| DeepSeek 批汇总显示跳过 DOC01 | 正常断点续跑，该文档已完成；不是漏跑 |
| 别用 `--force` | 旧结果会归档到 `validated_history/<模型>/`，双线并行时没必要 |
| 脚本名叫 `run_deepseek_batch.py` | 命名历史，按 `--model` 通用；Qwen 也用它 |

## 9. 冻结边界

本 SOP 不改动任何冻结提示词、Schema、输出契约、校验器、原始语料与既有标注结果；不取消 DeepSeek 支线；所有输出仍是 `MODEL_CANDIDATE`，未经人工核验不得称为人工标注或历史事实。

## 10. 变更记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-11-06 | 按研究者要求新建 Qwen 主线 SOP，与 DeepSeek SOP 对等。核准双终端并行的写入隔离清单；`run_batches_in_terminal.sh` 日志名加 PID 防同秒撞名；写明按模型参数、两终端可复制命令、一批跑完的双模型批改清单，以及「改规则／只选模型」时的口径留痕要求。零 API 演练验证，未启动任何长任务。 |
