# BATCH01-DOC03 文档级归并 v0.1 抽检

> 日期：2026-11-06  
> 模型：`cuc/deepseek`  
> 输入：10个窗口候选、3组相邻候选对、62个对话片段  
> Token：输入14,089，输出33,748，合计47,837，其中推理Token 27,783。

## 一、结构恢复

模型输出为合法JSON，但使用了`canonical_events`、`canonical_event_ids`等与正式Schema语义等价的自定义字段。兼容层执行以下无损映射：

- `packet_version` → `schema_version`；
- `canonical_events` → `document_events`；
- `event_id` → `document_event_id`；
- 平铺的六类过程字段 → `canonical_event`；
- `canonical_event_ids` → `document_event_ids`；
- 删除决策中重复的`source_segment_ids`。

未修改事件名称、事件类型、归并决策、范围类别、证据或候选去向。规范化后严格校验通过，恢复过程未调用API。

## 二、有效改进

- 10/10个输入候选全部有去向；
- `W001-E01`被拆成本人政治组／民运任务与前线战斗背景；
- `W001-E01 + W002-E01`的部队开进与进攻被归并并标为`NARRATED_CONTEXT`；
- `W003-E04 + W004-E01`的夜攻东西跑池已合并并标为`NARRATED_CONTEXT`；
- 平型关前线进攻、减员、夜攻和未俘获活俘均没有进入个人经历链；
- 动员新兵和往前查看后被劝返得到保留；
- 保留缴获武器的一般政策说明被判为非独立事件。

## 三、待修问题

1. `W002-E01`和`W003-E01`仍被分为「进攻过程」与「同一战斗减员」，与中等粒度规则不符；
2. 政治组／民运任务被标为`DIRECT_FIRST_PERSON`，但范围证据只引用`S0017`中一般性会议表述，应直接使用`S0021`的本人任务证据；
3. 东北大学生教日语喊话被标为`PERSONAL_EXPERIENCE + COLLECTIVE_WITH_ROLE`，但「他教我们」只是集体指称，缺少杨永松具体角色证据；应使用`UNCERTAIN`或`NARRATED_CONTEXT`，或给出更直接的本人证据。

## 四、结论

v0.1完成了关键的个人／背景分流，但尚未完成中等粒度事件归并和参与依据严格性回归，因此不继续运行`DOC01`和`DOC02`。使用v0.2输出契约对`DOC03`执行一次保留原响应的强制复跑。
