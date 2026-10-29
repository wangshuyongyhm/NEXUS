"""wizard.factsheet — 五家 Agent 探测/注册数据单源（1965，源=task/1956 agents-factsheet.md MEM#105529）。

数据文件化（任务书陷阱3）：Agent 工具换代只改本表。探测特征全部为「home 相对
路径/文件名」——配合 HOME 重定向可测。证据分级见 factsheet 原文；未核项
（Codex http_headers/ZCode http 型/Kimi headers 细节）在 snippet 注记保留。
"""
from __future__ import annotations

import os
from pathlib import Path

# (agent_id, 名称, 探测特征[home 相对], 配置格式, MCP 片段模板, 指令注入点, 坑注记)
AGENTS: tuple[dict, ...] = (
    {
        "id": "claude-code",
        "name": "Claude Code",
        "detect": ["~/.claude.json", "~/.claude/"],
        "format": "json",
        "inject_point": "~/.claude/AGENTS.md（或 CLAUDE.md）+ settings hooks",
        "snippet": (
            '"nexus-xdr": { "type": "http", "url": "http://127.0.0.1:19998/mcp", '
            '"headers": { "Authorization": "Bearer <YOUR_TOKEN>" } }'
        ),
        "snippet_target": "~/.claude.json 顶层 mcpServers（CLI: claude mcp add --transport http --header）",
        "notes": "ANTHROPIC_BASE_URL 双重 /v1 坑；settings 非热加载须重启",
    },
    {
        "id": "codex",
        "name": "Codex",
        "detect": ["~/.codex/config.toml"],
        "format": "toml",
        "inject_point": "~/.codex/AGENTS.md",
        "snippet": (
            '[mcp_servers.nexus-xdr]\nurl = "http://127.0.0.1:19998/mcp"\n'
            'http_headers = { "Authorization" = "Bearer <YOUR_TOKEN>" }'
        ),
        "snippet_target": "~/.codex/config.toml",
        "notes": "reinstall 覆盖 [mcp_servers]；OAuth 锁目录 ~/.codex/mcp-oauth-locks；http_headers 为社区佐证（未核项）",
    },
    {
        "id": "zcode",
        "name": "ZCode",
        "detect": ["~/.zcode/"],
        "format": "json",
        "inject_point": "~/.agents/AGENTS.md + 工作区 AGENTS.md",
        "snippet": (
            '"mcp": { "servers": { "nexus-xdr": { "type": "http", '
            '"url": "http://127.0.0.1:19998/mcp", '
            '"headers": { "Authorization": "Bearer <YOUR_TOKEN>" }, "enabled": true } } }'
        ),
        "snippet_target": "~/.zcode/cli/config.json → mcp.servers（工作区 <repo>/.zcode/config.json）",
        "notes": "schema 严格未知键静默丢 server；http 型片段=官方 skill 文档（本机无实例，未核项）",
    },
    {
        "id": "kimi",
        "name": "Kimi CLI/桌面",
        "detect": ["~/.kimi-code/", "~/Library/Application Support/kimi-desktop/"],
        "process_hint": "kimi-co（带尾空格）",
        "format": "json",
        "inject_point": "~/.config/kimi/AGENTS.md（CLI）/ workspace AGENTS.md（桌面）",
        "snippet": (
            '{ "mcpServers": { "nexus-xdr": { "transport": "http", '
            '"url": "http://127.0.0.1:19998/mcp", '
            '"headers": { "Authorization": "Bearer <YOUR_TOKEN>" } } } }'
        ),
        "snippet_target": "CLI $KIMI_CODE_HOME/mcp.json + 项目级 .kimi-code/mcp.json（桌面写托管源 daimon-share/daimon/config.json 的 mcp.servers——home/mcp.json 为派生文件勿手写）",
        "notes": "桌面 home/mcp.json 派生文件三轮踩坑；MCP 仅会话创建时加载；headers 字段细节未核项",
    },
    {
        "id": "cursor",
        "name": "Cursor",
        "detect": ["~/.cursor/mcp.json", "~/.cursor/hooks.json"],
        "format": "json",
        "inject_point": ".cursor/rules/ + AGENTS.md + hooks.json（sessionStart/stop/beforeSubmitPrompt）",
        "snippet": (
            '"nexus-xdr": { "url": "http://127.0.0.1:19998/mcp", '
            '"transport": "streamable-http", '
            '"headers": { "Authorization": "Bearer <YOUR_TOKEN>" } }'
        ),
        "snippet_target": "~/.cursor/mcp.json 顶层 mcpServers",
        "notes": "改 mcp.json 须重启/新会话；url 型不生效备选 mcp-remote stdio proxy；forum #169015 非默认头可能丢",
    },
)

# 六端口（capability matrix 固定面）
DEFAULT_PORTS = {
    "xdr": 19998,
    "mem": 11537,
    "embed": 11436,
    "ocrx": 11438,
    "api": 8642,
    "gateway": 4001,
}


def _expand(marker: str) -> Path:
    home = Path(os.environ.get("HOME", str(Path.home())))
    return Path(marker.replace("~/", str(home) + "/"))


def detect_agents() -> list[dict]:
    """按 factsheet 特征逐家探测（只读）。返回命中清单（含 snippet 等注册料）。"""
    hits = []
    for a in AGENTS:
        found = [m for m in a["detect"] if _expand(m).exists()]
        if found:
            hits.append({**a, "found_via": found})
    return hits


def snippet_all(port: int = DEFAULT_PORTS["xdr"]) -> list[dict]:
    """五家 MCP 片段全量（端口可换后的重渲染）。"""
    out = []
    for a in AGENTS:
        snip = a["snippet"].replace("19998", str(port))
        out.append({
            "agent": a["id"], "name": a["name"], "format": a["format"],
            "target": a["snippet_target"], "snippet": snip,
            "inject_point": a["inject_point"], "notes": a["notes"],
        })
    return out
