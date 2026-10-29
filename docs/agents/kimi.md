# Kimi（CLI / 桌面 App）接入 NEXUS

> 目标：10 分钟让 Kimi CLI 或 Kimi 桌面连上 NEXUS 调度总线与共享知识库。
> 形态：MCP（HTTP transport）+ AGENTS.md 指令注入（CLI：`~/.config/kimi/AGENTS.md`；桌面：工作区 AGENTS.md）。

## 前置要求

- Kimi CLI（`~/.kimi-code/`——注意不是 `~/.kimi/`）或 Kimi 桌面（`~/Library/Application Support/kimi-desktop/`）
- NEXUS 已安装（`:19998` 健康）

## 五步接入

### 1. 安装 NEXUS

```bash
git clone https://github.com/wangshuyongyhm/NEXUS.git nexus-oss && cd nexus-oss
./install.sh && nexus init
```

### 2. 写入 MCP 配置

**Kimi CLI**：`$KIMI_CODE_HOME/mcp.json`（默认 `~/.kimi-code/mcp.json`）或项目级 `.kimi-code/mcp.json`：

```json
{ "mcpServers": { "nexus-xdr": { "transport": "http", "url": "http://127.0.0.1:19998/mcp", "headers": { "Authorization": "Bearer <YOUR_TOKEN>" } } } }
```

**Kimi 桌面**：⚠️ `home/mcp.json` 是**派生文件**，手写会被 daimon 启动时重置——必须写托管源
`daimon-share/daimon/config.json` 的 `mcp.servers`，或项目级 `.kimi-code/mcp.json`。

> 注意：transport 值是 `"http"`——`"streamable-http"` 在 Kimi 是非法值。

### 3. 鉴权初始化

L0 只读工具匿名可用（本机实证无鉴权直连可检索）；写入/调度凭据由编排层签发。
`headers` 字段细节以向导生成片段为准。

### 4. 握手验证

新开 Kimi 会话（MCP 仅会话创建时加载；CLI 可用 `/mcp-config` 查看）。
让它调 `search_knowledge` 检索任意关键词，返回即通。

### 5. hello-task 演练

让 Kimi 检索一条经验、完成一个小任务、把心得写回知识库（写需凭据）——完成最小闭环。

## 已知坑（实机记录，三轮踩坑固化）

| 坑 | 现象与对策 |
|---|---|
| 桌面派生文件 | `home/mcp.json` 手写必被 daimon 重置——写托管源或项目级（三轮实踩） |
| 会话创建时加载 | MCP 只在新会话/重启时加载，改配置不重载当前会话 |
| 双安装 PATH 锚定 | 多安装共存时 PATH 锚 `~/.kimi-code/bin/kimi` |
| 进程匹配 | 进程名 `kimi-co` 带尾空格，脚本 grep 时留意 |

## 故障排查

| 症状 | 先查 |
|---|---|
| 桌面端配置总是丢 | 你写的是派生文件——改写 `daimon-share/daimon/config.json` |
| transport 报错 | 值必须是 `"http"` 不是 `"streamable-http"` |
| 工具不出现 | 新会话开了吗；项目级 `.kimi-code/mcp.json` 的 JSON 合法性 |
| 401 | token 错配；匿名 L0 先验证连通 |
