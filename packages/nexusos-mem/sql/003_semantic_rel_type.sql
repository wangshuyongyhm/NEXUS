-- 003_semantic_rel_type.sql — Task1537 M2.5：语义边 rel_type 扩枚举
--
-- 设计：语义边 rel_type='semantic'，**双端都在 knowledge id 空间**
-- （knowledge↔knowledge 高置信相关对，与 citation/relates 同域）。
-- 语义=增值层（embedding 预筛 + LLM 复审，evidence 带判断理由+confidence），
-- 错边污染检索 → 拿不准不建（零错边红线）；无方向语义，统一小 id 为 src。
-- riding 默认不含 semantic（opt-in include_semantic），见 search.py。
--
-- 幂等：constraint 定义不含 semantic 才重建（与 ensure_schema 判据一致）。

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'knowledge_relation'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) NOT ILIKE '%semantic%'
    ) THEN
        ALTER TABLE knowledge_relation
            DROP CONSTRAINT knowledge_relation_rel_type_check;
        ALTER TABLE knowledge_relation
            ADD CONSTRAINT knowledge_relation_rel_type_check
            CHECK (rel_type::text = ANY (ARRAY[
                'supersedes'::varchar, 'conflicts'::varchar, 'relates'::varchar,
                'provenance'::varchar, 'semantic'::varchar]::text[]));
    END IF;
END $$;

COMMIT;
