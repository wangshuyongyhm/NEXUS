-- 002_provenance_rel_type.sql — Task1534 M2b：血缘边 rel_type 扩枚举
--
-- 设计（与 1533 协调，progress 已声明）：血缘边 rel_type='provenance'，
-- **双端都在 knowledge_identity 身份空间**：
--   src_id = identity(kind='mem', mem_id=经验).id
--   dst_id = identity(kind='vault_doc', vault_path=task.md/report.md/会话日志).id
-- 与既有 citation/supersede 边（knowledge↔knowledge id 空间）分域，
-- 消费端（riding/M3 读模型）按 rel_type 分流解析，无双空间歧义。
-- 血缘=事实语义（结构化线索零 LLM 判断），错一条毁信任 → 模糊线索只记录不建边。

BEGIN;

ALTER TABLE knowledge_relation
    DROP CONSTRAINT knowledge_relation_rel_type_check;

ALTER TABLE knowledge_relation
    ADD CONSTRAINT knowledge_relation_rel_type_check
    CHECK (rel_type::text = ANY (ARRAY[
        'supersedes'::varchar, 'conflicts'::varchar,
        'relates'::varchar, 'provenance'::varchar]::text[]));

COMMIT;
