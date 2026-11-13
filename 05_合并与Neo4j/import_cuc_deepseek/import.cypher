// 正式语料 cuc/deepseek 图谱：可重复执行的 Neo4j 导入脚本。
// 仅用于本目录下的独立 demo 数据库。

MATCH (n) DETACH DELETE n;

CREATE CONSTRAINT document_id IF NOT EXISTS FOR (n:InterviewDocument) REQUIRE n.doc_id IS UNIQUE;
CREATE CONSTRAINT segment_id IF NOT EXISTS FOR (n:SourceSegment) REQUIRE n.segment_id IS UNIQUE;
CREATE CONSTRAINT attachment_id IF NOT EXISTS FOR (n:SourceAttachment) REQUIRE n.attachment_id IS UNIQUE;
CREATE CONSTRAINT event_id IF NOT EXISTS FOR (n:EventNode) REQUIRE n.event_id IS UNIQUE;
CREATE CONSTRAINT process_id IF NOT EXISTS FOR (n:Process) REQUIRE n.process_id IS UNIQUE;
CREATE CONSTRAINT event_type_id IF NOT EXISTS FOR (n:EventType) REQUIRE n.event_type_id IS UNIQUE;
CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE;
CREATE CONSTRAINT circumstance_id IF NOT EXISTS FOR (n:Circumstance) REQUIRE n.circumstance_id IS UNIQUE;
CREATE CONSTRAINT stage_id IF NOT EXISTS FOR (n:ProcessStage) REQUIRE n.stage_id IS UNIQUE;
CREATE CONSTRAINT event_time_id IF NOT EXISTS FOR (n:EventTime) REQUIRE n.event_time_id IS UNIQUE;
CREATE CONSTRAINT time_expression_id IF NOT EXISTS FOR (n:TimeExpression) REQUIRE n.time_expression_id IS UNIQUE;
CREATE CONSTRAINT mention_id IF NOT EXISTS FOR (n:EntityMention) REQUIRE n.mention_id IS UNIQUE;
CREATE CONSTRAINT alias_id IF NOT EXISTS FOR (n:EntityAlias) REQUIRE n.alias_id IS UNIQUE;
CREATE CONSTRAINT annotation_id IF NOT EXISTS FOR (n:DocumentAnnotation) REQUIRE n.annotation_id IS UNIQUE;
CREATE CONSTRAINT life_episode_id IF NOT EXISTS FOR (n:LifeEpisode) REQUIRE n.episode_id IS UNIQUE;

MERGE (g:GraphBuild {build_id: 'oral-history-batch-cuc_deepseek-v1'})
SET g.name = '正式语料cuc/deepseek图谱',
    g.import_date = '2026-11-13',
    g.schema_version = '3.2+batch-application-ext',
    g.description = '正式语料 54 份（cuc/deepseek）：原文—事件—阶段—实体—时间—生平，data_role=BATCH_APPLICATION';

UNWIND [
  {id:'MATERIAL_EVENT', name:'物质事件'},
  {id:'MENTAL_EVENT', name:'心理事件'},
  {id:'RELATIONAL_EVENT', name:'关系事件'},
  {id:'VERBAL_EVENT', name:'言语事件'},
  {id:'BEHAVIOURAL_EVENT', name:'行为事件'},
  {id:'EXISTENTIAL_EVENT', name:'存在事件'}
] AS item
MERGE (t:EventType {event_type_id:item.id})
SET t.name = item.name, t.framework = '韩礼德及物性系统';

LOAD CSV WITH HEADERS FROM 'file:///documents.csv' AS row
MERGE (d:InterviewDocument {doc_id:row.doc_id})
SET d.title=row.title, d.interviewee=row.interviewee, d.interview_date=row.interview_date,
    d.visit_no=row.visit_no, d.version=row.version, d.source_file=row.source_file,
    d.total_characters=toInteger(row.total_characters), d.data_role=row.data_role,
    d.include_in_study=row.include_in_study, d.review_status=row.review_status;

MATCH (g:GraphBuild {build_id:'oral-history-batch-cuc_deepseek-v1'})
MATCH (d:InterviewDocument)
MERGE (g)-[:CONTAINS_DOCUMENT]->(d);

LOAD CSV WITH HEADERS FROM 'file:///entities.csv' AS row
MERGE (e:Entity {entity_id:row.entity_id})
SET e.canonical_name=row.canonical_name, e.entity_type=row.entity_type,
    e.entity_subtype=row.entity_subtype, e.description=row.description,
    e.authority_status=row.authority_status, e.confidence=row.confidence,
    e.review_status=row.review_status;

// 人物核心与访谈文档的关系。一个人物可以对应多次访谈。
LOAD CSV WITH HEADERS FROM 'file:///person_subjects.csv' AS row
MATCH (person:Entity {entity_id:row.person_entity_id})
SET person:BiographicalSubject,
    person.biography_status=row.biography_status,
    person.biography_review_status=row.review_status;

LOAD CSV WITH HEADERS FROM 'file:///document_persons.csv' AS row
MATCH (d:InterviewDocument {doc_id:row.doc_id})
MATCH (person:Entity:BiographicalSubject {entity_id:row.person_entity_id})
MERGE (d)-[r:INTERVIEW_OF]->(person)
SET r.relation_type=row.relation_type, r.review_status=row.review_status;

LOAD CSV WITH HEADERS FROM 'file:///source_segments.csv' AS row
MERGE (s:SourceSegment {segment_id:row.segment_id})
SET s.doc_id=row.doc_id, s.segment_order=toInteger(row.segment_order),
    s.source_part=row.source_part, s.source_ref_id=row.source_ref_id,
    s.source_block_id=row.source_block_id, s.speaker_id=row.speaker_id,
    s.speaker_type=row.speaker_type, s.start_timecode=row.start_timecode,
    s.end_timecode=row.end_timecode, s.start_offset=toInteger(row.start_offset),
    s.end_offset=toInteger(row.end_offset), s.segment_type=row.segment_type,
    s.verbatim_text=row.verbatim_text, s.normalized_text=row.normalized_text,
    s.transcription_status=row.transcription_status, s.review_status=row.review_status
WITH s, row
MATCH (d:InterviewDocument {doc_id:row.doc_id})
MERGE (d)-[:HAS_SEGMENT]->(s);

LOAD CSV WITH HEADERS FROM 'file:///source_segments.csv' AS row
WITH row WHERE row.speaker_id <> ''
MATCH (s:SourceSegment {segment_id:row.segment_id})
MATCH (e:Entity {entity_id:row.speaker_id})
MERGE (s)-[:SPOKEN_BY]->(e);

LOAD CSV WITH HEADERS FROM 'file:///event_nodes.csv' AS row
MERGE (e:EventNode {event_id:row.event_id})
SET e.doc_id=row.doc_id, e.event_name=row.event_name,
    e.narrative_order=toInteger(row.narrative_order), e.historical_order=toInteger(row.historical_order),
    e.result_state=row.result_state, e.factuality=row.factuality,
    e.confidence=row.confidence, e.boundary_note=row.boundary_note,
    e.boundary_confidence=row.boundary_confidence, e.review_status=row.review_status
WITH e, row
MATCH (d:InterviewDocument {doc_id:row.doc_id})
MERGE (d)-[:HAS_EVENT]->(e);

LOAD CSV WITH HEADERS FROM 'file:///event_processes.csv' AS row
MERGE (p:Process {process_id:row.process_id})
SET p.process_text=row.process_text, p.process_normalized=row.process_normalized,
    p.confidence=row.confidence, p.evidence_segment_id=row.evidence_segment_id
WITH p, row
MATCH (e:EventNode {event_id:row.event_id})
MATCH (t:EventType {event_type_id:row.event_type_id})
MERGE (e)-[:HAS_PROCESS]->(p)
MERGE (e)-[:HAS_TYPE]->(t);

LOAD CSV WITH HEADERS FROM 'file:///event_processes.csv' AS row
WITH row WHERE row.evidence_segment_id <> ''
MATCH (p:Process {process_id:row.process_id})
MATCH (s:SourceSegment {segment_id:row.evidence_segment_id})
MERGE (p)-[:SUPPORTED_BY]->(s);

LOAD CSV WITH HEADERS FROM 'file:///event_participants.csv' AS row
MATCH (e:EventNode {event_id:row.event_id})
MATCH (x:Entity {entity_id:row.entity_id})
MERGE (e)-[r:HAS_PARTICIPANT {entity_id:row.entity_id, role:row.role, evidence_segment_id:row.evidence_segment_id}]->(x)
SET r.entity_name=row.entity_name, r.entity_type=row.entity_type,
    r.participation_status=row.participation_status, r.confidence=row.confidence;

LOAD CSV WITH HEADERS FROM 'file:///event_circumstances.csv' AS row
MERGE (c:Circumstance {circumstance_id:row.circumstance_id})
SET c.kind=row.kind, c.value_text=row.value_text, c.normalized_value=row.normalized_value,
    c.entity_id=row.entity_id, c.evidence_segment_id=row.evidence_segment_id, c.confidence=row.confidence
WITH c, row
MATCH (e:EventNode {event_id:row.event_id})
MERGE (e)-[:HAS_CIRCUMSTANCE]->(c);

LOAD CSV WITH HEADERS FROM 'file:///event_circumstances.csv' AS row
WITH row WHERE row.entity_id <> ''
MATCH (c:Circumstance {circumstance_id:row.circumstance_id})
MATCH (x:Entity {entity_id:row.entity_id})
MERGE (c)-[:REFERS_TO]->(x);

LOAD CSV WITH HEADERS FROM 'file:///process_stages.csv' AS row
MERGE (s:ProcessStage {stage_id:row.stage_id})
SET s.stage_order=toInteger(row.stage_order), s.stage_summary=row.stage_summary,
    s.process_text=row.process_text, s.confidence=row.confidence, s.review_status=row.review_status
WITH s, row
MATCH (e:EventNode {event_id:row.event_id})
MERGE (e)-[:HAS_STAGE]->(s);

LOAD CSV WITH HEADERS FROM 'file:///stage_next.csv' AS row
MATCH (a:ProcessStage {stage_id:row.source_stage_id})
MATCH (b:ProcessStage {stage_id:row.target_stage_id})
MERGE (a)-[r:NEXT_STAGE]->(b)
SET r.logic=row.logic, r.evidence_segment_id=row.evidence_segment_id,
    r.confidence=row.confidence, r.review_status=row.review_status;

LOAD CSV WITH HEADERS FROM 'file:///event_next.csv' AS row
MATCH (a:EventNode {event_id:row.source_event_id})
MATCH (b:EventNode {event_id:row.target_event_id})
MERGE (a)-[r:NEXT]->(b)
SET r.chain_id=row.chain_id, r.basis=row.basis,
    r.confidence=row.confidence, r.review_status=row.review_status;

LOAD CSV WITH HEADERS FROM 'file:///event_times.csv' AS row
MERGE (t:EventTime {event_time_id:row.event_time_id})
SET t.raw_text=row.raw_text, t.normalized_start=row.normalized_start,
    t.normalized_end=row.normalized_end, t.precision=row.precision,
    t.certainty=row.certainty, t.source_status=row.source_status,
    t.evidence_segment_id=row.evidence_segment_id, t.confidence=row.confidence,
    t.review_status=row.review_status
WITH t, row
MATCH (e:EventNode {event_id:row.event_id})
MERGE (e)-[:HAS_TIME]->(t);

LOAD CSV WITH HEADERS FROM 'file:///event_times.csv' AS row
WITH row WHERE row.evidence_segment_id <> ''
MATCH (t:EventTime {event_time_id:row.event_time_id})
MATCH (s:SourceSegment {segment_id:row.evidence_segment_id})
MERGE (t)-[:SUPPORTED_BY]->(s);

// 人物生平是叠加视图：不改动文档内 EventNode 与 NEXT。
// 同一 LifeEpisode 将来可以由多份访谈中的多个 EventNode 共同支持。
LOAD CSV WITH HEADERS FROM 'file:///life_episodes.csv' AS row
MERGE (episode:LifeEpisode {episode_id:row.episode_id})
SET episode.episode_name=row.episode_name,
    episode.life_order=toInteger(row.life_order),
    episode.normalized_start=row.normalized_start,
    episode.normalized_end=row.normalized_end,
    episode.precision=row.precision,
    episode.certainty=row.certainty,
    episode.episode_scope=row.episode_scope,
    episode.confidence=row.confidence,
    episode.review_status=row.review_status
WITH episode, row
MATCH (person:Entity:BiographicalSubject {entity_id:row.person_entity_id})
MERGE (person)-[r:HAS_LIFE_EPISODE]->(episode)
SET r.life_order=toInteger(row.life_order), r.review_status=row.review_status;

LOAD CSV WITH HEADERS FROM 'file:///life_episode_sources.csv' AS row
MATCH (episode:LifeEpisode {episode_id:row.episode_id})
MATCH (event:EventNode {event_id:row.event_id})
MERGE (episode)-[r:SUPPORTED_BY_EVENT]->(event)
SET r.source_role=row.source_role, r.review_status=row.review_status;

LOAD CSV WITH HEADERS FROM 'file:///life_episode_next.csv' AS row
MATCH (a:LifeEpisode {episode_id:row.source_episode_id})
MATCH (b:LifeEpisode {episode_id:row.target_episode_id})
MERGE (a)-[r:BIOGRAPHICAL_NEXT]->(b)
SET r.person_entity_id=row.person_entity_id,
    r.basis=row.basis,
    r.overlap_possible=row.overlap_possible,
    r.confidence=row.confidence,
    r.review_status=row.review_status;

// 只讲述、但当前证据不足以认定为本人经历的集体历史，单独保留。
LOAD CSV WITH HEADERS FROM 'file:///narrated_contexts.csv' AS row
MATCH (person:Entity:BiographicalSubject {entity_id:row.person_entity_id})
MATCH (event:EventNode {event_id:row.event_id})
MERGE (person)-[r:NARRATED_CONTEXT]->(event)
SET r.context_order=toInteger(row.context_order),
    r.relation_type=row.relation_type,
    r.review_status=row.review_status;

LOAD CSV WITH HEADERS FROM 'file:///time_expressions.csv' AS row
MERGE (t:TimeExpression {time_expression_id:row.time_expression_id})
SET t.raw_text=row.raw_text, t.normalized_start=row.normalized_start,
    t.normalized_end=row.normalized_end, t.precision=row.precision,
    t.expression_type=row.expression_type, t.certainty=row.certainty,
    t.start_offset=toInteger(row.start_offset), t.end_offset=toInteger(row.end_offset),
    t.source_status=row.source_status, t.confidence=row.confidence,
    t.review_status=row.review_status
WITH t, row
MATCH (s:SourceSegment {segment_id:row.segment_id})
MERGE (s)-[:HAS_TIME_EXPRESSION]->(t);

LOAD CSV WITH HEADERS FROM 'file:///entity_mentions.csv' AS row
MERGE (m:EntityMention {mention_id:row.mention_id})
SET m.mention_text=row.mention_text, m.start_offset=toInteger(row.start_offset),
    m.end_offset=toInteger(row.end_offset), m.mention_function=row.mention_function,
    m.source_status=row.source_status, m.confidence=row.confidence,
    m.review_status=row.review_status
WITH m, row
MATCH (s:SourceSegment {segment_id:row.segment_id})
MATCH (e:Entity {entity_id:row.entity_id})
MERGE (s)-[:HAS_MENTION]->(m)
MERGE (m)-[:MENTIONS]->(e);

LOAD CSV WITH HEADERS FROM 'file:///entity_aliases.csv' AS row
MERGE (a:EntityAlias {alias_id:row.alias_id})
SET a.alias_text=row.alias_text, a.alias_type=row.alias_type,
    a.evidence_segment_id=row.evidence_segment_id, a.confidence=row.confidence,
    a.review_status=row.review_status
WITH a, row
MATCH (e:Entity {entity_id:row.entity_id})
MERGE (a)-[:ALIAS_OF]->(e);

LOAD CSV WITH HEADERS FROM 'file:///entity_relations.csv' AS row
MATCH (a:Entity {entity_id:row.source_entity_id})
MATCH (b:Entity {entity_id:row.target_entity_id})
MERGE (a)-[r:RELATED_TO {relation_id:row.relation_id}]->(b)
SET r.relation_type=row.relation_type, r.role_label=row.role_label,
    r.start_date=row.start_date, r.end_date=row.end_date,
    r.evidence_segment_id=row.evidence_segment_id, r.source_status=row.source_status,
    r.confidence=row.confidence, r.review_status=row.review_status;

LOAD CSV WITH HEADERS FROM 'file:///source_attachments.csv' AS row
MERGE (a:SourceAttachment {attachment_id:row.attachment_id})
SET a.target_type=row.target_type, a.target_id=row.target_id, a.function=row.function,
    a.quote_start_offset=toInteger(row.quote_start_offset),
    a.quote_end_offset=toInteger(row.quote_end_offset), a.confidence=row.confidence,
    a.review_status=row.review_status
WITH a, row
MATCH (s:SourceSegment {segment_id:row.segment_id})
MERGE (s)-[:HAS_ATTACHMENT]->(a);

LOAD CSV WITH HEADERS FROM 'file:///source_attachments.csv' AS row
WITH row WHERE row.target_type='DOCUMENT'
MATCH (a:SourceAttachment {attachment_id:row.attachment_id})
MATCH (t:InterviewDocument {doc_id:row.target_id})
MERGE (a)-[:ATTACHES_TO]->(t);

LOAD CSV WITH HEADERS FROM 'file:///source_attachments.csv' AS row
WITH row WHERE row.target_type='EVENT'
MATCH (a:SourceAttachment {attachment_id:row.attachment_id})
MATCH (t:EventNode {event_id:row.target_id})
MERGE (a)-[:ATTACHES_TO]->(t);

LOAD CSV WITH HEADERS FROM 'file:///source_attachments.csv' AS row
WITH row WHERE row.target_type='STAGE'
MATCH (a:SourceAttachment {attachment_id:row.attachment_id})
MATCH (t:ProcessStage {stage_id:row.target_id})
MERGE (a)-[:ATTACHES_TO]->(t);

LOAD CSV WITH HEADERS FROM 'file:///document_annotations.csv' AS row
MERGE (a:DocumentAnnotation {annotation_id:row.annotation_id})
SET a.doc_id=row.doc_id, a.annotation_type=row.annotation_type,
    a.annotation_text=row.annotation_text, a.author_or_editor=row.author_or_editor,
    a.source_status=row.source_status, a.target_type=row.target_type,
    a.target_id=row.target_id
WITH a, row
MATCH (d:InterviewDocument {doc_id:row.doc_id})
MERGE (d)-[:HAS_ANNOTATION]->(a);

LOAD CSV WITH HEADERS FROM 'file:///document_annotations.csv' AS row
WITH row WHERE row.source_segment_id <> ''
MATCH (a:DocumentAnnotation {annotation_id:row.annotation_id})
MATCH (s:SourceSegment {segment_id:row.source_segment_id})
MERGE (a)-[:DERIVED_FROM]->(s);

LOAD CSV WITH HEADERS FROM 'file:///document_annotations.csv' AS row
WITH row WHERE row.target_type='DOCUMENT'
MATCH (a:DocumentAnnotation {annotation_id:row.annotation_id})
MATCH (t:InterviewDocument {doc_id:row.target_id})
MERGE (a)-[:ANNOTATES]->(t);

LOAD CSV WITH HEADERS FROM 'file:///document_annotations.csv' AS row
WITH row WHERE row.target_type='EVENT'
MATCH (a:DocumentAnnotation {annotation_id:row.annotation_id})
MATCH (t:EventNode {event_id:row.target_id})
MERGE (a)-[:ANNOTATES]->(t);

LOAD CSV WITH HEADERS FROM 'file:///document_annotations.csv' AS row
WITH row WHERE row.target_type='STAGE'
MATCH (a:DocumentAnnotation {annotation_id:row.annotation_id})
MATCH (t:ProcessStage {stage_id:row.target_id})
MERGE (a)-[:ANNOTATES]->(t);

LOAD CSV WITH HEADERS FROM 'file:///document_annotations.csv' AS row
WITH row WHERE row.target_type='ENTITY'
MATCH (a:DocumentAnnotation {annotation_id:row.annotation_id})
MATCH (t:Entity {entity_id:row.target_id})
MERGE (a)-[:ANNOTATES]->(t);

LOAD CSV WITH HEADERS FROM 'file:///document_annotations.csv' AS row
WITH row WHERE row.target_type='SOURCE_SEGMENT'
MATCH (a:DocumentAnnotation {annotation_id:row.annotation_id})
MATCH (t:SourceSegment {segment_id:row.target_id})
MERGE (a)-[:ANNOTATES]->(t);

LOAD CSV WITH HEADERS FROM 'file:///coverage_audit.csv' AS row
MERGE (a:CoverageAudit {doc_id:row.doc_id})
SET a.total_characters=toInteger(row.total_characters),
    a.segmented_characters=toInteger(row.segmented_characters),
    a.uncovered_characters=toInteger(row.uncovered_characters),
    a.overlap_characters=toInteger(row.overlap_characters),
    a.total_segments=toInteger(row.total_segments),
    a.attached_segments=toInteger(row.attached_segments),
    a.document_only_segments=toInteger(row.document_only_segments),
    a.coverage_rate=toFloat(row.coverage_rate), a.audit_status=row.audit_status
WITH a, row
MATCH (d:InterviewDocument {doc_id:row.doc_id})
MERGE (d)-[:HAS_COVERAGE_AUDIT]->(a);


// 词表 v1.1：正式批次 v1.1：segment_type 沿用人工 7 值并新增 RECORDING_TIMESTAMP（共 8 值）；circumstance_kind 严格沿用人工 5 值，模型超纲值就近归类并标 NEEDS_REVIEW。
// 生平层为叠加视图：语料层不合并；疑似同一经历标 NEEDS_REVIEW 交人工；
// 人工 MERGE 后，一条 LifeEpisode 可由多个来源 EventNode 共同支持。
