# 文档级归并输出契约 v0.3

本文件是`document_consolidation_prompt_v0.1`的输出结构补充约束。如与先前的输出示例冲突，以本文件为准。

## 1. 内容回归规则

1. 同一战斗、任职、转移或组织行动的过程与伤亡、胜负、突围、脱险等直接结果，通常归并为一个一级事件，不得仅因跨窗口就把「过程」和「伤亡结果」分开。
2. `scope_evidence_quote`必须直接证明所选`participation_bases`。`DIRECT_FIRST_PERSON`的证据必须包含本人的直接行动、任务或受影响表述；一般性的「我们开会」不能代替「把我分配去做什么」的直接证据。
3. 不得因为事件的主要施事者是他人，就忽略受访者在同一事件中的明确行动或直接受影响事实。候选同时包含「我们接头、参加、进入、被编入」和组织改编等紧密相连阶段时，应保留个人阶段；可合并为一个完整事件，必要时拆分，但不得只留下机构沿革并把整体降为背景。

### 1.1 `COLLECTIVE_WITH_ROLE`的窄判定

`COLLECTIVE_WITH_ROLE`必须有该事件中的本人职务、任务、在场或具体行动证据。以下一人称复数表达可构成具体行动证据：

- 「我们参加／接头／进入／撤退／转移／打仗」等以「我们」为行动主体的明确动词；
- 「我们都去……」「我们随后到……」等明确陈述受访者随集体在场或移动的表达；
- 已明确受访者属于该集体，且原文陈述该集体当时执行具体任务，同时没有未参加、转述或不在场证据。

以下表达单独出现时仍不足以证明本人参与：

- 只有所有关系或泛称，如「我们的部队」「我们政治处」「我们团」；
- 只有接受者关系，如「他教我们」「给我们讲」；
- 只叙述集体的长期历史、后续沿革、战果或伤亡；
- 有「我不在现场」「我没参加」「听说」等反证。

不得把所有「我们」自动标为个人经历，也不得把所有「我们」自动降为背景；必须判断「我们」是否是该事件具体动作的主体，并逐字引用该动作。

### 1.2 `DIRECTLY_AFFECTED`的窄判定

受访者不是主要施事者，但原文明确表明事件直接作用于本人或本人当时所在且已确认参与的组织时，可使用`DIRECTLY_AFFECTED`。例如，本人所在部队在其服役期间被收编、改编、解散，或本人在战斗中受伤、落水、被俘。

不得仅因受访者使用「我们部队」就推定直接受影响。部队多年后的发展、改称、战果和历史评价，如无本人当时仍在其中或直接受影响的证据，应标为`NARRATED_CONTEXT`。

## 2. 唯一允许的顶层结构

顶层必须且只能包含以下6个字段。禁止使用`packet_version`、`canonical_events`或其他同义字段。

```json
{
  "schema_version": "document-consolidation-v1.0",
  "technical_document_id": "",
  "document_id": "",
  "interviewee": "",
  "document_events": [],
  "candidate_decisions": []
}
```

## 3. `document_events`结构

每个文档事件必须且只能包含以下12个字段。六类过程事件字段必须放入`canonical_event`内，不得与范围字段平铺。

```json
{
  "document_event_id": "BATCH01-DOC03-DE001",
  "source_candidate_ids": [],
  "source_segment_ids": [],
  "experience_scope": "PERSONAL_EXPERIENCE | NARRATED_CONTEXT | UNCERTAIN",
  "participation_bases": [],
  "scope_evidence_segment_ids": [],
  "scope_evidence_quote": "",
  "completeness": "COMPLETE | INCOMPLETE | UNCERTAIN",
  "canonical_event": {
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
  },
  "review_status": "AUTO_VALIDATED | NEEDS_REVIEW",
  "review_reason": null
}
```

`review_status=AUTO_VALIDATED`时，`review_reason`必须为`null`。`review_status=NEEDS_REVIEW`时，`review_reason`必须是非空字符串。

## 4. `candidate_decisions`结构

每条决策必须且只能包含以下4个字段。禁止使用`canonical_event_ids`或在决策中重复输出`source_segment_ids`。

```json
{
  "candidate_id": "",
  "action": "MERGED | KEPT | SPLIT | CONTEXT_ONLY | REJECTED_AS_NON_EVENT",
  "document_event_ids": [],
  "reason": ""
}
```

- `KEPT`和`CONTEXT_ONLY`必须恰好指向1个文档事件；
- `SPLIT`必须指向至少2个文档事件；
- `REJECTED_AS_NON_EVENT`的`document_event_ids`必须为空数组；
- 其他决策不得使用空数组。

输出前核对：每个输入`candidate_id`恰好出现一次；每个`document_event_id`均由至少一个候选决策指向；决策链接与`source_candidate_ids`完全一致。
