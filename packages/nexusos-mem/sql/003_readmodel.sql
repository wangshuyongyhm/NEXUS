-- 003_readmodel.sql — Task1538 M3：统一读模型存储（投影层，非真源）
--
-- 设计（规划 §2 方案四）：读模型 = identity 全空间点 + 全类型边（含 wikilink 文件边）
-- 的合并投影。真源不动：wikilink 真源在文件，边真源在写入链——本表只读消费，
-- 由 refresh_readmodel.py 全量重建（快照链 14:00 挂刷新 + 手动双模式）。
--
-- 双语义吸收（#219）：provenance 边两代实现并存——
--   created_by='backfill:1534' → 端点=identity id（identity 空间，直迁）
--   created_by LIKE 'writechain:%' → 端点=knowledge id（1533 语义，
--     刷新时翻译：src 经 mem 身份行映射；dst=文件代表 chunk → 优先文件 vault_doc 身份）
-- 翻译在 refresh 内做，本表内边端点统一为 identity id——消费端零歧义。

BEGIN;

CREATE TABLE IF NOT EXISTS readmodel_node (
    identity_id  BIGINT PRIMARY KEY,
    kind         TEXT NOT NULL,
    mem_id       BIGINT,
    vault_path   TEXT,
    refresh_id   BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rm_node_kind ON readmodel_node (kind);
CREATE INDEX IF NOT EXISTS idx_rm_node_mem ON readmodel_node (mem_id);

CREATE TABLE IF NOT EXISTS readmodel_edge (
    src_identity BIGINT NOT NULL,
    dst_identity BIGINT NOT NULL,
    edge_kind    TEXT NOT NULL,   -- supersedes/relates/provenance/semantic/wikilink
    evidence     TEXT,
    refresh_id   BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rm_edge_src ON readmodel_edge (src_identity, edge_kind);
CREATE INDEX IF NOT EXISTS idx_rm_edge_dst ON readmodel_edge (dst_identity, edge_kind);

-- 刷新元数据（漂移检测=对比上次刷新的点/边数）
CREATE TABLE IF NOT EXISTS readmodel_meta (
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    refresh_id   BIGINT NOT NULL,
    nodes        BIGINT NOT NULL,
    edges        BIGINT NOT NULL,
    edge_kinds   JSONB NOT NULL
);

COMMIT;

-- 消费固化：监控对照视图（G15/V4 并行视角——M4 观察期接线，本期只读可查）
CREATE OR REPLACE VIEW readmodel_stats AS
SELECT 'node:' || kind AS metric, count(*)::bigint AS value
FROM readmodel_node GROUP BY kind
UNION ALL
SELECT 'edge:' || edge_kind, count(*)::bigint
FROM readmodel_edge GROUP BY edge_kind;
