# ZCode 接入 NEXUS

> 目标：10 分钟让 ZCode 连上 NEXUS 调度总线与共享知识库。
> 形态：MCP（HTTP）+ AGENTS.md 指令注入（`~/.agents/AGENTS.md` 或工作区 AGENTS.md）。

## 前置要求

- ZCode 已安装（`~/.zcode/` 存在）
- NEXUS 已安装（`:19998` 健康）

## 五步接入

### 1. 安装 NEXUS

```bash
git clone https://github.com/wangshuyongyhm/NEXUS.git nexus-oss && cd nexus-oss
./install.sh && nexus init
```

### 2. 写入 MCP 配置

编辑 `~/.zcode/cli/config.json` 的 `mcp.servers`（或工作区 `<repo>/.zcode/config.json`）：

```json
"mcp": { "servers": { "nexus-xdr": { "type": "http", "url": "http://127.0.0.1:19998/mcp", "headers": { "Authorization": "Bearer <YOUR_TOKEN>" }, "enabled": true } } }
```

> 说明：legacy 的 `http_headers` 键会被自动迁移为 `headers`。HTTP 型片段取自官方 skill
> 文档格式——本机当前 config 未常驻该 server 实例，发布版以向导生成片段为准（向导已实证产出）。

### 3. 鉴权初始化

L0 只读工具匿名可用；写入/调度凭据由编排层签发。首次接入先匿名握手。

### 4. 握手验证

新开 ZCode 会话（MCP 仅会话创建时加载），工具清单应出现 nexus-xdr 系工具；
让它调一次 `search_knowledge` 即验证连通。

### 5. hello-task 演练

让 ZCode 检索一条经验并写回一条心得（写需凭据）——完成最小闭环。

## 已知坑（实机记录）

| 坑 | 现象与对策 |
|---|---|
| schema 严格 | 未知键**静默丢弃**整个 server——片段照抄，别加自创键 |
| command 数组 | 误把 stdio 写法（command/args）放进 http server 会致 Settings 页崩溃 |
| 桌面端绕过 CLI 迁移器 | 桌面与 CLI 配置链路不同，改动走各自入口 |
| 无 system_prompt 入口 | 指令注入只能走 AGENTS.md 家族（`~/.agents/` 或工作区） |

## 故障排查

| 症状 | 先查 |
|---|---|
| server 整个不出现 | schema 静默丢弃——对照片段逐键核对（`type`/`url`/`headers`/`enabled`） |
| Settings 页崩溃 | 是否误用了 `command` 数组写法 |
| 改配置不生效 | 新会话才加载；确认改的是实际生效的那份 config（cli/工作区/fallback） |
| 401 | token 错配或过期 |
