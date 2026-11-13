# Qwen 结果移入 DeepSeek 线 · 来源说明

- 时间：2026-11-13 16:20–16:28
- 裁决：研究者本人。原话「我的语料只是测试，现在还不是正式语料呢。你就先把 qwen 输出的结果拿进 deepseek，id 都改成 deepseek 的，你就相当于重新写入文件就行。晚上我再看看能否继续跑结果」
- 涉及文档：`BATCH02-DOC09`（YYS-04）、`BATCH04-DOC09`（YYS-07）
- 结果：DeepSeek 线 **54/54 `valid=true`**，24 张表已统一导出

## 为什么做

这两份的整篇 `entity_time` 调用累计失败 9 / 6 次（上游超时，非数据问题），而 Qwen 线这两份早已完整验收通过。此前卡住的是同一份提示词要一口气吐约 5.5 万 token 的输出通道。

## 具体做了什么（只搬卡住的那一步）

1. 把 Qwen 线这两份的 `raw/entity_time_*.json` 复制成 DeepSeek 线的 `raw/entity_time_*_FROM_QWEN.json`。
2. 用 DeepSeek 线**原有**脚本 `graph_apply_enrichment.py --model cuc/deepseek --write` 重新生成 18 张表：
   - 事件／阶段／环境成分／参与者／片段／附件沿用 DeepSeek 线自己的 L0 底座与 stage 响应（BATCH02-DOC09 是 12 事件、BATCH04-DOC09 是 1 事件，都保持 DeepSeek 线原有数量）；
   - 只有实体四表、事件时间、时间表达来自搬入的响应；
   - 原有脚本自动为 DeepSeek 线独有的 DE010–012 补了 3 条「结构性推断」事件时间占位（代码里既有逻辑，非新增规则，预览里显示的 3 条校验问题就是它）。
3. 实体 ID 在**搬入副本**里统一重编号为 `E001…`，并同步重映射提及／别名／关系的引用，复核 0 行孤立引用。
4. `graph_validate_bundle.py --write-report`：两份均 `valid=true`、覆盖率 1.0。
5. `graph_export_import.py --model cuc/deepseek --write`：统一导出 **24 张表**到 `05_合并与Neo4j/import_cuc_deepseek/`，`documents.csv` 54 行数据。

## ID 口径（研究者要求「都改成 DeepSeek 的」）

| 类别 | 结果 |
|---|---|
| 文档／事件／时间表达／事件时间／阶段／附件 ID | 全部由 DeepSeek 线原有脚本生成：`YYS-04-TX0001`、`BATCH02-DOC09-DE001-T01`、`…-DE001-P01`、`YYS-04-AT0001` |
| 实体 ID | 统一 `E001…`（含脚本自动生成的 `UNRESOLVED-*` 占位，与其它 52 份格式一致） |
| 唯一保留的 Qwen 标记 | 搬入的 raw 响应里 `model_id=cuc/qwen`。18 张 CSV **没有** `model_id` / `run_id` 列，不影响任何结果；保留它只为溯源，避免晚上分不清这两份哪来的 |

## 没有动的东西

Qwen 线任何文件、`validated_json/` 一级层结果、`01_实验配置/实验登记表.csv`（**不编造 API 调用记录**）、冻结提示词／Schema／契约／校验器／导入脚本／原始语料。所有既有脚本一字未改，全程零 API 调用。

## 状态与红线

- 结果一律 `MODEL_CANDIDATE`，技术门禁通过 ≠ 内容放行；人工抽检、台账人工列、BATCH07 脚注核对仍由研究者完成。
- **禁止导入 Neo4j**：Qwen 线还差 25 份，且本线这两份属于测试性移入。
- 导出报告里 12850 条「共享实体冲突 E001，保留首次」是既有的跨文档 ID 命名空间提示，不是新错误。
- `review_queue/graph_pending_cuc_deepseek.md` 是 12:23 的历史清单，已过时；**以 54/54 验收为准**。
- 偏移待核 47 / 38 条、环境成分待复核 9 / 1 条照常留复核清单（E3 后置，不阻断）。

## 若日后这批语料转为正式

这两份的 `entity_time` 内容来自 Qwen，与其余 52 份**不完全同口径**。正式使用时二选一：

- (a) 重跑 DeepSeek 整篇 `entity_time`（或上一轮做好的分段兜底 `scripts/graph_split_fallback_in_terminal.sh`）覆盖；
- (b) 在论文方法章注明这两份的处理方式并保留本说明。

**不要把它们当作 DeepSeek 模型产出写进模型对比统计。**

## 一键回退

```
python3 '04_54份正式语料批处理/_qwen_import_backup_20261113_1620/回退到移入前.py'
```

零删除：把搬入的响应与衍生表移到备份区 `after_import/`，再从 `BATCH0*-DOC09/` 恢复原来的 10 张底座 CSV。回退后重跑主链即可按原本整篇方式继续；备份目录 160 KB。
