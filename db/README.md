# db/ — NEXUS 数据库结构

- `schema.sql` — pg_dump 结构基线（PostgreSQL 15 + pgvector；已去属主，属主=执行者）。
  含一张 `*_archive_20260728` 历史归档表（结构参考，可忽略）。
- `migrations/00N_*.sql` — 增量迁移（幂等可重跑，按序执行）。

初始化（install.sh 步骤 4 的展开）：

```bash
createdb nexus_mem
psql -d nexus_mem -c 'CREATE EXTENSION IF NOT EXISTS vector'
psql -d nexus_mem -f db/schema.sql
for f in db/migrations/00*.sql; do psql -d nexus_mem -f "$f"; done
```
