# 连续窗口盲抽取补充规则 v0.1

本规则用于一个最小连续窗口实验。除输出结构外，事件类型、参与者角色、规范化和证据要求继续遵守系统提示词v0.3。

1. 输入是一段按原顺序排列的连续访谈片段，研究者没有提供事件数量或事件边界。
2. 自主判断其中包含0个、1个或多个候选一级事件。不要把每个动词机械拆成事件，也不要把目标和阶段结果不同的经历强行合并。
3. `source_segment_ids` 只列构成该候选事件的直接原文片段，按输入顺序排列。
4. 编辑时间标记、采访者提示或与候选事件无直接关系的片段写入 `unassigned_segment_ids`。
5. 每个输入片段ID必须至少出现在某个事件的 `source_segment_ids` 或 `unassigned_segment_ids` 中；不得虚构输入中不存在的ID。
6. 每个候选事件内部的 `event` 对象必须完整遵守单事件Schema v1.0；`evidence_quote` 必须逐字来自该候选事件的某个 `source_segment_ids`。
7. 只输出以下合法JSON对象，不输出Markdown或解释性前言：

```json
{
  "window_id": "",
  "events": [
    {
      "candidate_id": "",
      "source_segment_ids": [],
      "event": {
        "event_name": "",
        "event_type": "MATERIAL",
        "event_type_zh": "物质",
        "core_process": "",
        "participants": [],
        "circumstances": [],
        "projected_content": null,
        "evidence_quote": "",
        "type_basis": "",
        "alternative_event_type": null,
        "ambiguity_reason": null,
        "review_status": "MODEL_CANDIDATE"
      }
    }
  ],
  "unassigned_segment_ids": []
}
```

`candidate_id` 在本窗口内依次使用 `<window_id>-E01`、`<window_id>-E02`。如果没有事件，`events` 输出空数组，并把全部输入片段ID写入 `unassigned_segment_ids`。
