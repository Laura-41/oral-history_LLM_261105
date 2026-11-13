# 生平层疑似同一经历 · 待人工确认（cuc_deepseek）

> 生成时间：2026-11-13 11:23　零 API　依据：D3 不合并 + T4 叠加视图

**语料层一律不动**：下面每个事件节点、原文片段、文档仍各自独立，绝不合并。
生平层只是套在外面的一层视图；系统**不自动判定**同一经历，只把可能重复的
`life_episodes.review_status` 标成 `NEEDS_REVIEW`，由你逐组确认。

疑似规则（确定性、零 API）：同一人物 + **跨访谈** + 事件名相似 ≥ 0.55 + 时间不冲突；
同一篇访谈里最多保留一个候选，其余相似事件仍留在语料层当独立事件，不并入疑似组。

## 一、疑似组

| 组号 | 人物 | 事件 | 文档 | 事件名 | 时间 | 名称相似度 |
|---|---|---|---|---|---|---|
| CHF-S001 | PER-CHF | BATCH07-DOC04-DE011 | CHF-V3-03 | 担任情报总站站长并组织情报站侦察敌人 | 1937–1945 | 0.553 |
| CHF-S001 | PER-CHF | BATCH01-DOC01-DE005 | CHF-V1-02 | 陈海峰任澄西抗日情报总站副站长并领导情报站开展侦察锄奸工作 | （未知） | 0.553 |
| CHF-S002 | PER-CHF | BATCH03-DOC04-DE001 | CHF-V2-07 | 老一团参加车桥战役 | 1944-03-05–1944-03-06 | 0.889 |
| CHF-S002 | PER-CHF | BATCH05-DOC04-DE007 | CHF-V3-14 | 老1团参加车桥战役 | 1944-03-05–1944-03-05 | 0.889 |
| CHF-S003 | PER-CHF | BATCH05-DOC09-DE005 | CHF-V3-17 | 新登战斗期间接收大批伤员 | （未知） | 0.615 |
| CHF-S003 | PER-CHF | BATCH06-DOC02-DE006 | CHF-V3-18 | 新登战役后医院收治大批重伤员 | （未知） | 0.615 |
| CHF-S004 | PER-CHF | BATCH06-DOC02-DE012 | CHF-V3-18 | 冒雨到吴家道给患疟疾的粟司令打针 | （未知） | 0.56 |
| CHF-S004 | PER-CHF | BATCH06-DOC04-DE001 | CHF-V3-19 | 抢救患疟疾的粟司令 | （未知） | 0.56 |
| CRT-S001 | PER-CRT | BATCH06-DOC06-DE010 | CRT-14 | 警告并炮击英国军舰紫石英号等 | 1949-04-20–1949-04-21 | 0.741 |
| CRT-S001 | PER-CRT | BATCH07-DOC01-DE011 | CRT-15 | 解放军炮击英国军舰紫石英号 | （未知） | 0.741 |

## 二、你可以怎么裁

- **什么都不填**：保持「1 个事件 = 1 条生平」，全部标 `NEEDS_REVIEW`，图谱照常可导。
- **确认是同一段人生经历**：在下面决策文件里对该组填一行 `MERGE`。重跑导出后，
  该组只生成 **1 条 `LifeEpisode`**，下面多个事件都通过 `SUPPORTED_BY_EVENT` 挂上去；
  事件节点与原文片段仍然各归各。
- **确认不是同一段经历**：填 `KEEP_SEPARATE`，该组恢复 `CONFIRMED`、维持多条生平。

决策文件（**不自动创建，需要时手工新建**，这是人工裁决载体，不是新词表或新标签）：

`04_54份正式语料批处理/human_adjudicated/cuc_deepseek/life_episode_merges.csv`

表头与写法：

```csv
group_id,person_entity_id,episode_name,event_ids,decision,reviewer,notes
CHF-S001,PER-CHF,组建救亡会,CHF-V1-DE004|CHF-V3-DE002,MERGE,研究者,一访与三访讲的是同一段经历
```

- `event_ids` 用 `|` 分隔，留空表示该组全部事件；`episode_name` 可留空（取首个事件名）。
- `decision` 只能是 `MERGE` 或 `KEEP_SEPARATE`。
- 改完重跑：`python3 -u scripts/graph_export_import.py --model <模型> --write`。
