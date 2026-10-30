# NEXUS 初始化技能 · AGENTS.md 注入片段（1965 交付5）

> 注入位：各家 AGENTS.md 家族（~/.claude/AGENTS.md、~/.codex/AGENTS.md、
> ~/.agents/AGENTS.md、~/.config/kimi/AGENTS.md、工作区 AGENTS.md——见
> .nexus/mcp-snippets/ 各片段头部 inject 行）。Agent 层只做翻译不做逻辑。

---

## 技能：初始化（NEXUS 向导）

当用户输入「初始化 / initialize / setup 环境」时，按以下顺序执行：

1. **环境扫描**（只读，永远先做）：
   ```bash
   nexus init --scan --json
   ```
   向用户汇报：阻断项（必须解决）/可协商项/检测到的 Agent 清单（人读表格可用
   `nexus init --scan` 不带 --json）。

2. **协商缺失项**（三选制，禁开放题）：
   - vault：A 用户指目录 / B starter vault（默认推荐）/ C 降级
   - PG：A Docker 片段（输出 compose 让用户自执行）/ B 已有 PG 建专属库 / C xdr-only（明示损失清单）
   - 端口冲突自动换；macOS 权限按 CLI 指引转述（系统设置路径），用户操作后重扫确认。

3. **执行初始化**（把用户的选择代入 flag；无 TTY/全自动场景用推荐默认 B/B）：
   ```bash
   nexus init --json --vault <a|b|c> [--vault-dir <路径>] --pg <a|b|c> [--pg-dsn <管理串>]
   ```
   B/PG 通道会建 nexus 专属库（绝不碰用户其他库）；A/PG 通道把 Docker compose
   片段原样转给用户自执行。

4. **复检收尾**：
   ```bash
   nexus init --doctor --json
   ```
   all_green=true → 向用户报「初始化完成」并给 MCP 接入片段
   （.nexus/mcp-snippets/<agent>.<json|toml>——复制即接入，改后须重启会话）；
   否则把 diffs 逐条翻译成人话让用户处理。

铁律：二次「初始化」= 对账不重写（幂等）；Agent 不得绕过 CLI 手改 .nexus；
--json 全自动路径无交互。
