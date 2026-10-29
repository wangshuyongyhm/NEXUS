"""wizard.provision — Phase2 配套置备（spec §2 置备制，261028 15:14 修订）。

PG 三通道：A Docker compose 片段（指引式，不替跑 docker）/ B 已有 PG 建 nexus
专属库（CREATE DATABASE+EXTENSION vector+最小权限角色 nexus_app——绝不触碰
客户其他库）/ C 降级损失清单。端口冲突自动换。schema 版本轴=nexus_meta 表。
"""
from __future__ import annotations

import secrets
import socket

DOCKER_COMPOSE = """\
# nexus 置备片段（spec §2 A 通道：用户自执行，向导不替跑 docker）
services:
  nexus-pg:
    image: pgvector/pgvector:pg16
    container_name: nexus-pg
    environment:
      POSTGRES_USER: nexus
      POSTGRES_PASSWORD: nexus_local
      POSTGRES_DB: nexus_mem
    ports:
      - "127.0.0.1:5433:5432"
    volumes:
      - nexus-pg-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U nexus"]
      interval: 5s
      retries: 10
volumes:
  nexus-pg-data:
"""

DEGRADE_LOSSES = [
    "nexusos-mem 检索/知识库全不可用（PG 无）",
    "gate 部分依赖 PG 的检查降级（plugin warn 类）",
    "xdr 任务台账仍可用（SQLite 家族/文件面）——xdr-only 模式",
]


def docker_snippet() -> str:
    return DOCKER_COMPOSE


def allocate_ports(conflicts: dict[str, int], used: set[int] | None = None) -> dict[str, int]:
    """冲突端口自动换：从冲突口+1 向上找空闲 bind。返回新端口映射（仅冲突项）。"""
    used = used or set()
    out: dict[str, int] = {}
    for name, port in conflicts.items():
        cand = port + 1
        while cand in used or cand in conflicts.values():
            cand += 1
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(("127.0.0.1", cand))
                    break
                except OSError:
                    cand += 1
        out[name] = cand
        used.add(cand)
    return out


def provision_existing_pg(dsn: str, dbname: str = "nexus_mem",
                          app_role: str = "nexus_app", run: bool = True) -> dict:
    """B 通道：已有 PG 上建 nexus 专属库+扩展+最小权限角色（幂等）。

    只操作目标库与该角色——绝不触碰客户其他库。返回 plan（SQL 清单）+
    applied（是否执行）+ 结果。连接库选 postgres/admin 库执行 CREATE DATABASE。
    """
    plan = [
        "-- 建专属库（若不存在）",
        ("SELECT 'CREATE DATABASE {db}' WHERE NOT EXISTS "
         "(SELECT FROM pg_database WHERE datname = '{db}')\\gexec"),
        "-- 建扩展（目标库内）",
        "CREATE EXTENSION IF NOT EXISTS vector;",
        "-- 最小权限角色（若不存在）+ 仅授权该库",
        ("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{role}') THEN "
         "CREATE ROLE {role} LOGIN PASSWORD '<generated>'; END IF; END $$;"),
        "GRANT CONNECT ON DATABASE {db} TO {role};",
        "-- schema 版本轴（doctor 对账依据）",
        "CREATE TABLE IF NOT EXISTS nexus_meta (key text PRIMARY KEY, value text NOT NULL);",
        ("INSERT INTO nexus_meta(key,value) VALUES ('schema_version','1') "
         "ON CONFLICT (key) DO NOTHING"),
    ]
    plan = [s.format(db=dbname, role=app_role) if "{db}" in s or "{role}" in s else s for s in plan]

    result = {"plan": plan, "applied": False, "ok": False, "detail": ""}
    if not run:
        result["detail"] = "dry-run：仅输出 plan"
        return result
    try:
        import psycopg2
    except ImportError:
        result["detail"] = "psycopg2 未装——置备不可执行（装 nexusos-mem 或 psycopg2-binary）"
        return result
    password = secrets.token_urlsafe(18)
    try:
        admin = psycopg2.connect(dsn, connect_timeout=3)
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (dbname,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{dbname}"')
            cur.execute(f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{app_role}') "
                        f"THEN CREATE ROLE {app_role} LOGIN PASSWORD '{password}'; END IF; END $$;")
            cur.execute(f"GRANT CONNECT ON DATABASE \"{dbname}\" TO {app_role}")
        admin.close()
        db = psycopg2.connect(_rebase_dsn(dsn, dbname), connect_timeout=3)
        db.autocommit = True
        with db.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("CREATE TABLE IF NOT EXISTS nexus_meta (key text PRIMARY KEY, value text NOT NULL)")
            cur.execute("INSERT INTO nexus_meta(key,value) VALUES ('schema_version','1') "
                        "ON CONFLICT (key) DO NOTHING")
            cur.execute("GRANT USAGE ON SCHEMA public TO " + app_role)
            cur.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO " + app_role)
        db.close()
        result.update(applied=True, ok=True, detail=f"专属库 {dbname} 就绪（角色 {app_role} 仅该库权限）",
                      app_role_password=password)
        return result
    except Exception as e:  # noqa: BLE001 —— 置备失败=detail 报告非崩溃（fail-open）
        result["detail"] = f"置备失败：{type(e).__name__}: {e}"
        return result


def _rebase_dsn(dsn: str, dbname: str) -> str:
    """DSN 尾库名替换为目标库（postgresql://host[:port][/db]）。"""
    if "://" not in dsn:
        return dsn
    head, _, rest = dsn.partition("://")
    rest = rest.rstrip("/")
    if "/" in rest:
        rest = rest.rsplit("/", 1)[0]
    return f"{head}://{rest}/{dbname}"
