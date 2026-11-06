# BATCH01-DOC03 / cuc/qwen · DE004 人工裁决单

> 裁决时间：2026-11-06 20:41
> 裁决人：研究者
> 裁决内容：接受 `NEEDS_REVIEW`，由人工把 `DE004` 的 `experience_scope` 改判为讲述背景；`DOC01`、`DOC02` 暂缓。
> 关联抽检：`BATCH01-DOC03_cuc_qwen_抽检.md` §3.1

## 一、裁决对象

`BATCH01-DOC03-DE004`「东北大学生到政治处教喊话」。

| 字段 | 模型原值 | 人工裁决值 |
|---|---|---|
| `experience_scope` | `PERSONAL_EXPERIENCE` | `NARRATED_CONTEXT` |
| `participation_bases` | `["DIRECTLY_AFFECTED"]` | `["THIRD_PARTY_ONLY"]` |
| `review_status` | `NEEDS_REVIEW` | `HUMAN_CONFIRMED` |
| `review_reason` | 模型自述「需人工确认杨永松是否直接在场」 | 记录裁决依据 |

`scope_evidence_segment_ids`、`scope_evidence_quote`、事件片段、`canonical_event` 全部保持不变。

## 二、裁决依据

1. **契约**：`document_consolidation_output_contract_v0.3` §1.1 明确「只有接受者关系，如『他教我们』『给我们讲』」单独出现时不足以证明本人参与。
2. **逐字原文**：`S0082`「才到我们政治处里边作为敌工干事，他教我们喊话。」、`S0084`「教我们拼音……」。受访者处于被教的一方，全文没有给出其在该事件中的职务、任务或在场的具体行动。
3. **同题基线**：`cuc/deepseek` 在 `BATCH01-DOC03` 的 v0.2 定向回归中，把同一内容判为 `NARRATED_CONTEXT + THIRD_PARTY_ONLY`，并已写入 `BATCH01-DOC03_v0.2_抽检.md` 的通过项。
4. **研究者决定**：2026-11-06 20:41 明确选择「接受 NEEDS_REVIEW，由人工改判为讲述背景」，不修订契约、不强制复跑。

## 三、影响范围

- 仅 `DE004` 一个事件的 4 个字段变更，其余 6 个文档事件、12 条候选决策、全部逐字证据均未改动；
- 裁决后指标：个人经历 4→3、讲述背景 3→4、待复核 3→2，文档事件总数仍为 7；
- `DE005`、`DE006` 的 `NEEDS_REVIEW` 保持不变；`DE001`、`DE002`、`DE007` 的边界与复核粒度观察项仍保留，供后续人工抽检；
- **契约 v0.3 未修订**，因此此裁决不触发规则版本升级，也不要求三份重新回归。

## 四、文件与状态

| 用途 | 路径 | 状态 |
|---|---|---|
| 模型原始响应 | `raw_responses/cuc_qwen/20261106_201800_BATCH01-DOC03.json` | 永久保留，未改动 |
| 自动校验结果 | `validated_json/cuc_qwen/BATCH01-DOC03.json` | 永久保留，未改动 |
| 人工复核／图谱导入视图 | `human_adjudicated/cuc_qwen/BATCH01-DOC03.json` | 本轮新建 |

导入视图外层记录 `adjudications`、`metrics_original` / `metrics_after_adjudication`、来源文件与裁决依据；内层 `consolidated_output` 结构与原结果一致，便于现有导入程序读取。`HUMAN_CONFIRMED` 是流程文档 §10.3 定义的人工复核状态，不在自动校验器枚举内，因此该视图不参与 `validate_document_consolidation()` 评分 —— 这是设计使然，不是校验失败。

## 五、本轮未做的操作

- 未修改模型输出、冻结的提示词／契约／Schema／校验器；
- 未使用 `--force` 复跑，未调用 API；
- 未运行 `DOC01`、`DOC02`（研究者决定暂缓）；
- 未读取或覆盖 `cuc_deepseek` 的输入与结果；
- 未停止或改写并行会话的 `BATCH02` 文件。
