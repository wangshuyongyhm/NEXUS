-- 001_knowledge_identity.sql — Task1524 M1单B：知识身份统一层（PG 身份注册表）
--
-- 设计（2026-09-24-MEM-Obsidian融合根治规划 §2 方案一"知识本体双地址制"）：
--   同一知识单元在体系里有三套身份（PG mem_id / Vault 路径 / 镜像分片锚点）互不认识——
--   本表成为唯一身份入口：identity_kind 区分身份类别，mem_id↔vault_path 双地址。
--
-- 登记机制（单一真源 = 数据库触发器，非散落调用点钩子）：
--   AFTER INSERT ON knowledge 触发器自动登记 mem 行（覆盖全部写入口：
--   api_server / embed_server / SharedKnowledge / 任何直连脚本）。
--   写入链通过 set_config('app.producer', ...) 标注精确 producer；
--   未标注的写入口落 'pg:knowledge-insert' 兜底值。
--   登记失败（锁/权限/任何错误）只 RAISE WARNING，绝不阻断知识写入主链路
--   （lock_timeout 250ms 有界等待 + 异常吞噬 + 恢复原值）。
--   mem 行消失（DELETE）由 FK ON DELETE CASCADE 同步注销身份。
--
-- 约束（幂等可重跑；禁 DROP 已有对象——B2）：
--   UNIQUE (identity_kind, vault_path) WHERE kind<>'mem' —— 文件型身份防重复（mem 以 mem_id 为身份）
--   UNIQUE (identity_kind, mem_id) WHERE mem_id IS NOT NULL —— PG 侧防重复登记
--
-- 零关系列：本表只管"存在与身份"，血缘/语义关系是 M2 的边表，不混入。

BEGIN;

CREATE TABLE IF NOT EXISTS knowledge_identity (
    id            BIGSERIAL PRIMARY KEY,
    identity_kind TEXT NOT NULL CHECK (identity_kind IN
                    ('mem', 'vault_doc', 'mirror_shard', 'graph_card', 'index')),
    mem_id        BIGINT REFERENCES knowledge(id) ON DELETE CASCADE,
    vault_path    TEXT,
    producer      TEXT NOT NULL DEFAULT 'unknown',
    created       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- vault_path 唯一性只对文件型身份成立（vault_doc/mirror_shard/graph_card/index：
-- 文件即身份，一路径一身份行）。mem 行的身份是 mem_id——多条经验指向同一
-- Vault 文件是事实不是冲突（回填实测 1176 行多_entry共路径），不参与 path 去重。
DROP INDEX IF EXISTS uq_identity_kind_vault_path;
CREATE UNIQUE INDEX IF NOT EXISTS uq_identity_kind_vault_path_filekinds
    ON knowledge_identity (identity_kind, vault_path)
    WHERE identity_kind <> 'mem';

CREATE UNIQUE INDEX IF NOT EXISTS uq_identity_kind_mem_id
    ON knowledge_identity (identity_kind, mem_id)
    WHERE mem_id IS NOT NULL;

-- 登记触发器：knowledge 每插一行 → identity 自动多一行 mem 记录。
-- 内层 BEGIN 块 = 隐式 savepoint：登记任何失败只 WARNING，主写入不受影响。
CREATE OR REPLACE FUNCTION nexus_mem_identity_register() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    _old_lt TEXT;
BEGIN
    BEGIN
        -- 有界等待：identity 表被锁（回填/维护）时最多阻塞 250ms 即放弃登记，
        -- 保证知识写入主链路延迟不受登记侧拖累。用完恢复事务原值。
        _old_lt := coalesce(current_setting('lock_timeout', true), '0');
        PERFORM set_config('lock_timeout', '250ms', true);
        INSERT INTO knowledge_identity (identity_kind, mem_id, vault_path, producer)
        VALUES ('mem', NEW.id, NEW.path,
                coalesce(nullif(current_setting('app.producer', true), ''),
                         'pg:knowledge-insert'))
        ON CONFLICT DO NOTHING;
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'identity register skipped (knowledge %): %', NEW.id, SQLERRM;
    END;
    PERFORM set_config('lock_timeout', _old_lt, true);
    RETURN NEW;
END
$fn$;

DO $do$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 'trg_knowledge_identity_register'
                     AND tgrelid = 'knowledge'::regclass) THEN
        CREATE TRIGGER trg_knowledge_identity_register
            AFTER INSERT ON knowledge
            FOR EACH ROW EXECUTE FUNCTION nexus_mem_identity_register();
    END IF;
END
$do$;

-- identity_stats()：按 kind 计数 + 按顶层目录分布（M1A 域监控 / M3 读模型消费）。
CREATE OR REPLACE FUNCTION identity_stats()
RETURNS TABLE (identity_kind TEXT, top_dir TEXT, entries BIGINT, with_mem_id BIGINT)
LANGUAGE sql STABLE AS $fn$
    SELECT identity_kind,
           coalesce(nullif(split_part(vault_path, '/', 1), ''), '(pg-only)') AS top_dir,
           count(*),
           count(mem_id)
    FROM knowledge_identity
    GROUP BY 1, 2
    ORDER BY 1, 2
$fn$;

-- identity_coverage：mem 身份覆盖对账（活跃口径，验收判据）。
CREATE OR REPLACE VIEW identity_coverage AS
SELECT
    (SELECT count(*) FROM knowledge)                                        AS knowledge_total,
    (SELECT count(*) FROM knowledge_identity WHERE identity_kind = 'mem')   AS mem_identity_total,
    (SELECT count(*) FROM knowledge WHERE NOT deprecated)                   AS knowledge_active,
    (SELECT count(*) FROM knowledge_identity i
       JOIN knowledge k ON k.id = i.mem_id
      WHERE i.identity_kind = 'mem' AND NOT k.deprecated)                   AS mem_identity_active,
    (SELECT count(*) FROM knowledge WHERE NOT deprecated)
      - (SELECT count(*) FROM knowledge_identity i
            JOIN knowledge k ON k.id = i.mem_id
           WHERE i.identity_kind = 'mem' AND NOT k.deprecated)              AS active_gap;

COMMIT;
