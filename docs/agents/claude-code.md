# Claude Code 接入 NEXUS

> 目标：10 分钟让你的 Claude Code 连上 NEXUS 调度总线与共享知识库。
> 形态：MCP（streamable HTTP）+ AGENTS.md 指令注入。

## 前置要求

- Claude Code 已安装并可正常对话（`~/.claude.json` 存在即已初始化）
- NEXUS 已安装（`./install.sh` + `nexus init` 完成，`:19998` 健康）
- 一个你的 Markdown vault（或向导生成的 starter vault）

## 五步接入

### 1. 安装 NEXUS

```bash
git clone <repo-url> nexus-oss && cd nexus-oss
./install.sh && nexus init     # 向导扫描环境 → 固定选项协商 → 打印 MCP 片段
```

### 2. 写入 MCP 配置

编辑 `~/.claude.json` 顶层 `mcpServers`（或用 CLI）：

```json
"nexus-xdr": { "type": "http", "url": "http://127.0.0.1:19998/mcp", "headers": { "Authorization": "Bearer <YOUR_TOKEN>" } }
```

CLI 等价命令：

```bash
claude mcp add --transport http --header "Authorization: Bearer <YOUR_TOKEN>" nexus-xdr http://127.0.0.1:19998/mcp
```

> 本机实证：`~/.claude.json` 已存在 nexus-xdr 注册条目（type http + Bearer header），加载正常。

### 3. 鉴权初始化

- 只读握手（`search_knowledge` 等 L0 工具）**不需要 token**——先匿名验证连通。
- 写入/调度凭据由编排层按任务签发（HMAC 签名、限时、任务绑定）；日常用向导生成的
  `.nexus/` 配置即可，需要手动签发时见进阶文档 `docs/`。

### 4. 握手验证

**改配置必须开新会话**（MCP 仅会话创建时加载）。新会话里：

```
/mcp   # 应看到 nexus-xdr 及其工具（search_knowledge 等）
```

或直接让 Claude 调一次 `search_knowledge`（如 "用 nexus 搜一下 dispatch 超时的经验"）。

### 5. hello-task 演练

让 Claude 通过 NEXUS 完成一个最小闭环：检索一条经验 → 写回一条心得
（`write_knowledge` 需凭据——首次可只演练检索），即完成接入。

## 已知坑（实机记录）

| 坑 | 现象与对策 |
|---|---|
| `ANTHROPIC_BASE_URL` 双重 `/v1` | 自建代理时路径重复致 404——base url 不要带尾 `/v1` |
| `settings.json` 非热加载 | 改完必须重启 Claude Code 进程，新会话不够 |
| nvm PATH | launchd/服务场景用 node 全路径，别依赖 nvm shim |
| 首次进入新目录 | 有 2 个一次性授权弹窗，点完即永久记住 |

## 故障排查

| 症状 | 先查 |
|---|---|
| `/mcp` 里看不到 nexus-xdr | 是否开了新会话；`~/.claude.json` JSON 语法是否被逗号破坏 |
| 工具调用 401 | Bearer token 是否过期/错配；L0 工具匿名可通则为凭据问题 |
| 工具列表空 | `curl http://127.0.0.1:19998/health` 先确认总线在 |
| 改配置不生效 | settings.json 改了要整进程重启，不是新会话 |
