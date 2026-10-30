"""wizard.config — Phase3 配置生成 + starter vault 模板（spec §3）。

幂等铁律（spec §5）：已存在文件永不覆盖——二次 init 走差异报告（doctor 同源）。
master_key 用 secrets.token_hex(18)（=openssl rand -hex 18 同强度同形态，stdlib）。
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from nexusos_common import nexus_home

ENV_TEMPLATE = """\
# NEXUS 环境配置（nexus init 生成；幂等：已存在不覆盖）
NEXUS_PG_DSN={dsn}
NEXUS_XDR_PORT={xdr_port}
NEXUS_MEM_PORT={mem_port}
NEXUS_EMBED_PORT={embed_port}
NEXUS_OCRX_PORT={ocrx_port}
NEXUS_API_PORT={api_port}
NEXUS_GATEWAY_PORT={gateway_port}
NEXUS_MASTER_KEY={master_key}
"""

STARTER_VAULT_DIRS = (
    "00-Inbox", "01-Projects", "03-Daily", "05-System/NEXUS-CONSTRAINT",
    "06-Memory", "task",
)

STARTER_CONSTRAINT_INDEX = """\
# NEXUS-CONSTRAINT / 约束索引（starter vault 模板）

> starter vault=约束模板最小面（spec §2 B 通道推荐默认）。Obsidian 只是查看器——
> vault 本质是 Markdown 目录；把本目录加进 Obsidian 即可获得图谱/双链视图。

## 核心规则（占位）
- 初始化向导：`nexus init`（幂等，二次=对账）
- 环境体检：`nexus init --doctor`
- Agent 接入：见 .nexus/mcp-snippets/

## 目录
- 00-Inbox 临时 / 01-Projects 项目 / 03-Daily 日志 / 06-Memory 记忆 / task 任务五层资产
"""

STARTER_README = """\
# starter vault（nexus init B 通道生成）

这是 NEXUS 约束模板 vault——可被 Obsidian 打开的纯 Markdown 目录。
改名为你的知识库前先跑一次 `nexus init --doctor` 确认配置一致。
"""


def env_file_path(home: Path | None = None) -> Path:
    return (home or nexus_home()) / ".env"


def write_env(ports: dict, pg_dsn: str, home: Path | None = None,
              force: bool = False) -> dict:
    """写 .nexus/.env（幂等：存在且非 force=只报告）。chmod 600。"""
    target = env_file_path(home)
    if target.exists() and not force:
        return {"path": str(target), "created": False, "detail": "已存在——不覆盖（幂等）"}
    target.parent.mkdir(parents=True, exist_ok=True)
    body = ENV_TEMPLATE.format(
        dsn=pg_dsn,
        xdr_port=ports.get("xdr", 19998), mem_port=ports.get("mem", 11537),
        embed_port=ports.get("embed", 11436), ocrx_port=ports.get("ocrx", 11438),
        api_port=ports.get("api", 8642), gateway_port=ports.get("gateway", 4001),
        master_key=secrets.token_hex(18),
    )
    target.write_text(body, encoding="utf-8")
    os.chmod(target, 0o600)
    return {"path": str(target), "created": True, "detail": "已生成（600）"}


def write_starter_vault(vault_dir: Path) -> dict:
    """starter vault 约束模板（默认 .nexus/vault-starter——绝不写用户 Obsidian）。"""
    created_items: list[str] = []
    for d in STARTER_VAULT_DIRS:
        p = vault_dir / d
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created_items.append(d)
    files = {
        "README.md": STARTER_README,
        "05-System/NEXUS-CONSTRAINT/index.md": STARTER_CONSTRAINT_INDEX,
    }
    for rel, content in files.items():
        p = vault_dir / rel
        if not p.exists():
            p.write_text(content, encoding="utf-8")
            created_items.append(rel)
    return {"path": str(vault_dir), "created": created_items,
            "detail": f"模板落盘（新增 {len(created_items)} 项，幂等）"}


def write_agent_registration(agents: list[dict], home: Path | None = None,
                             port: int = 19998) -> dict:
    """检测到的 Agent 注册（.nexus/agents-detected.json）+ MCP 片段输出。"""
    from nexusos_common.wizard.factsheet import snippet_all
    home = home or nexus_home()
    reg = home / "agents-detected.json"
    payload = [{"id": a["id"], "name": a["name"], "found_via": a["found_via"]} for a in agents]
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(json.dumps({"agents": payload}, ensure_ascii=False, indent=2), encoding="utf-8")
    snippets_dir = home / "mcp-snippets"
    snippets_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for s in snippet_all(port=port):
        ext = "toml" if s["format"] == "toml" else "json"
        f = snippets_dir / f"{s['agent']}.{ext}"
        body = s["snippet"]
        if ext == "json":
            body = "{\n  " + body.split("{", 1)[1] if body.startswith("{") else body
        f.write_text(f"# port={port}（本机实际，1981 自洽；重跑 init 刷新）\n# target: {s['target']}\n# inject: {s['inject_point']}\n"
                     f"# notes: {s['notes']}\n{body}\n", encoding="utf-8")
        written.append(f.name)
    return {"registry": str(reg), "snippets": written}


def render_report(env_result: dict, vault_result: dict, agent_reg: dict,
                  provision_result: dict | None, port_realloc: dict,
                  schema_line: str = "状态未知（--doctor 复检）") -> str:
    lines = ["初始化报告（Phase4）", ""]
    lines.append("## 动作清单")
    lines.append(f"- .env：{env_result['detail']}（{env_result['path']}）")
    lines.append(f"- starter vault：{vault_result['detail']}（{vault_result['path']}）")
    lines.append(f"- Agent 注册：{', '.join(agent_reg['snippets']) or '无检测命中'}"
                 f"（片段在 mcp-snippets/，复制即接入——各家会话创建时加载，改后须重启）")
    if provision_result:
        lines.append(f"- PG 置备：{provision_result['detail']}")
    if port_realloc:
        lines.append(f"- 端口自动换：{port_realloc}（已写入 .env）")
    else:
        lines.append("- 端口：默认六口无冲突")
    lines += ["", "## 下一步（Next steps）",
              f"  0. CLI 路径（首次必做）：export PATH=\"$NEXUS_HOME/venv/bin:$PATH\"（nexus 命令在专用 venv 内）",
              "  1. 应用 DB schema：" + schema_line,
              "  2. 启动服务：nohup python3 -m nexusos_xdr.mcp_server > $NEXUS_HOME/xdr-server.log 2>&1 &"
              "（端口自动读 .env 的 NEXUS_XDR_PORT；健康检查 curl 127.0.0.1:$NEXUS_XDR_PORT/health）",
              "  3. 注册 MCP：把 mcp-snippets/<你的Agent> 片段贴进对应配置（端口已按本机实际注入）后重启该 Agent 会话",
              "  4. 复检：nexus init --doctor 全绿后，在 Agent 会话输入「初始化」走 NEXUS 技能演练"]
    return "\n".join(lines)


def schema_status(dsn: str) -> str:
    """DB schema 应用状态（1981 修5：消除"README 手动步骤 vs 向导"歧义）。"""
    try:
        import psycopg2
        conn = psycopg2.connect(dsn, connect_timeout=3)
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name='knowledge' LIMIT 1")
            applied = cur.fetchone() is not None
        conn.close()
        return "applied" if applied else "not-applied"
    except Exception:
        return "unknown"


def apply_schema(dsn: str, oss_home: str | None = None) -> dict:
    """nexus init --apply-schema：从骨架仓 db/ 应用 schema+migrations。"""
    from pathlib import Path as _P
    cands = []
    if oss_home:
        cands.append(_P(oss_home))
    cands += [_P.cwd(), _P.cwd().parent]
    db_dir = next((c / "db" for c in cands if (c / "db" / "schema.sql").is_file()), None)
    if db_dir is None:
        return {"ok": False, "detail": "未定位 db/schema.sql（在骨架仓根运行，或 --oss-home 指向仓根）"}
    import psycopg2, glob
    conn = psycopg2.connect(dsn, connect_timeout=3)
    conn.autocommit = True
    applied = []
    with conn.cursor() as cur:
        cur.execute(open(db_dir / "schema.sql", encoding="utf-8").read())
        applied.append("schema.sql")
        for f in sorted(glob.glob(str(db_dir / "migrations" / "*.sql"))):
            cur.execute(open(f, encoding="utf-8").read())
            applied.append(_P(f).name)
    conn.close()
    return {"ok": True, "detail": f"已应用：{', '.join(applied)}"}
