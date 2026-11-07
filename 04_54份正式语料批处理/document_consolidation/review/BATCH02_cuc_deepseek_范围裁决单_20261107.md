# BATCH02 / cuc/deepseek · 范围判定人工裁决单

> 裁决依据：`review/BATCH02_cuc_deepseek_COLLECTIVE_WITH_ROLE_逐条复核清单_20261107.md` 中研究者填写的数字；落盘时间 2026-11-07T16:54:46。
> 裁决人：研究者；助手只负责按裁决生成文件，**未代填任何结论**。

## 一、裁决编码与汇总

| 数字 | 含义 | 条数 |
|---|---|---:|
| 1 | 维持 PERSONAL_EXPERIENCE | 36 |
| 2 | 改判 NARRATED_CONTEXT | 1 |
| 3 | 改判 UNCERTAIN | 1 |
| 4 | 暂缓（补上下文） | 1 |

共 **39** 条：维持 36 条、改判 2 条、暂缓 1 条。维持项不生成导入视图（原始结果即最终结果）。

**口径结论**：39 条中 36 条维持 `PERSONAL_EXPERIENCE`，说明研究者**维持契约 v0.3 §1.1 口径**；
不升提示词／契约版本、不重跑 BATCH02、不改冻结资产与校验器。

## 二、改判明细

| 文档 | 事件 ID | 清单序号 | 原范围 | 新范围 | 研究者备注 |
|---|---|---:|---|---|---|
| `BATCH02-DOC01` | `BATCH02-DOC01-DE002` | [1] | `PERSONAL_EXPERIENCE` | `NARRATED_CONTEXT` | 不属于个人也不属于集体行为，是假设的内容 |
| `BATCH02-DOC04` | `BATCH02-DOC04-DE002` | [8] | `PERSONAL_EXPERIENCE` | `UNCERTAIN` | — |

每条改判只变更 `experience_scope`、`review_status`（→ `HUMAN_CONFIRMED`）、`review_reason` 三个字段；
`participation_bases`、逐字证据、事件片段、`canonical_event` 全部保持原值。

> ⚠️ **待研究者确认**：`participation_bases` 的新值你还没有指定。
> 目前 2 条改判仍是 `COLLECTIVE_WITH_ROLE`。按 `DE004` 先例，改 `NARRATED_CONTEXT` 通常配 
> `THIRD_PARTY_ONLY`；改 `UNCERTAIN` 通常配 `INSUFFICIENT_EVIDENCE`。
> 你给出取值后我重新生成导入视图即可（原始结果始终不动）。

## 三、暂缓项（本次不落盘）

- `[12]` `BATCH02-DOC04-DE007`：补上下文后再裁

## 四、文档级指标变化

| 文档 | 个人（前→后） | 背景（前→后） | 不确定（前→后） | 待复核（前→后） |
|---|---|---|---|---|
| `BATCH02-DOC01` | 6→5 | 2→3 | 1→1 | 1→1 |
| `BATCH02-DOC04` | 8→7 | 2→2 | 0→1 | 4→3 |

## 五、文件与状态

| 用途 | 路径 |
|---|---|
| 裁决来源清单 | `review/BATCH02_cuc_deepseek_COLLECTIVE_WITH_ROLE_逐条复核清单_20261107.md` |
| 模型原始结果（**未改动**） | `validated_json/cuc_deepseek/` |
| 人工导入视图（本次新建） | `04_54份正式语料批处理/document_consolidation/human_adjudicated/cuc_deepseek/BATCH02-DOC01.json` |
| 人工导入视图（本次新建） | `04_54份正式语料批处理/document_consolidation/human_adjudicated/cuc_deepseek/BATCH02-DOC04.json` |

## 六、本轮未做的操作

- 未修改 `validated_json/` 与 `raw_responses/` 的任何模型输出；
- 未改动冻结的提示词／契约／Schema／校验器，未调用 API、未重跑；
- 未填写 `01_实验配置/双线批改台账.csv` 的人工列（`human_review_status` / `release_status` / `notes`），仍由研究者填写；
- 暂缓项未生成改判；所有结果在人工放行前仍为 `MODEL_CANDIDATE`。

如需撤回：删除本次新建的导入视图即可，原始结果完全不受影响。
