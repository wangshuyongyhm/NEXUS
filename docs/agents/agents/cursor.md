# Cursor 接入 NEXUS

> 目标：10 分钟让 Cursor 连上 NEXUS 调度总线与共享知识库。
> 形态：MCP（streamable-http）+ 指令注入（`.cursor/rules/` + AGENTS.md + hooks.json 三事件）。

## 前置要求

- Cursor 已安装（`~/.cursor/` 存在，含 `mcp.json`/`hooks.json`）
- NEXUS 已安装（`:19998` 健康）

## 五步接入

### 1. 安装 NEXUS

```bash
git clone <repo-url> nexus-oss && cd nexus-oss
./install.sh && nexus init
```

### 2. 写入 MCP 配置

编辑 `~/.cursor/mcp.json` 顶层 `mcpServers`：

```json
"nexus-xdr": { "url": "http://127.0.0.1:19998/mcp", "transport": "streamable-http", "headers": { "Authorization": "Bearer <YOUR_TOKEN>" } }
```

> 本机实证：`~/.cursor/mcp.json` 已存在 nexus-xdr 条目（url + transport streamable-http），加载正常。

### 3. 鉴权初始化

L0 只读工具匿名可用；写入/调度凭据由编排层签发。
⚠️ 已知问题：Cursor 的 `tools/call` 可能丢非默认 header（社区 forum 记录）——若 hello-task
报 401 先查这条（见故障排查）。

### 4. 握手验证

改完 `mcp.json` 必须重启 Cursor 或开新会话（MCP 仅会话创建时加载）。
在 Agent 模式让它调用 `search_knowledge`，返回条目即通。

### 5. hello-task 演练

让 Cursor 检索一条经验并完成一个小改动；hooks.json 的 sessionStart/stop/beforeSubmitPrompt
三事件可把 Cursor 会话接进 NEXUS 广播（本机已实证接广播）——进阶玩法见 `docs/`。

## 已知坑（实机记录）

| 坑 | 现象与对策 |
|---|---|
| 丢非默认 header | `tools/call` 可能丢自定义 header（forum #169015）——401 先查这条 |
| 改 mcp.json 不生效 | 必须重启/新会话；url 型不生效时备选 `mcp-remote` stdio proxy |
| hooks.json | sessionStart/stop/beforeSubmitPrompt 三事件本机实证可接 NEXUS 广播 |

## 故障排查

| 症状 | 先查 |
|---|---|
| 401（带了 token 仍拒） | 疑似丢 header bug——先匿名 L0 验证连通，再排凭据链 |
| 工具列表无 nexus-xdr | 重启 Cursor；`mcp.json` JSON 合法性 |
| url 型完全不工作 | 备选方案：mcp-remote stdio proxy 包一层 |
| 广播不触发 | hooks.json 三事件是否注册；事件脚本路径是否有效 |
