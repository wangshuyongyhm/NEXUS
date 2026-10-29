# Codex 接入 NEXUS

> 目标：10 分钟让 Codex 连上 NEXUS 调度总线与共享知识库。
> 形态：MCP（HTTP，按 URL 自动识别）+ AGENTS.md 指令注入（`~/.codex/AGENTS.md`）。

## 前置要求

- Codex CLI/桌面可用（`~/.codex/config.toml` 存在）
- NEXUS 已安装（`:19998` 健康）

## 五步接入

### 1. 安装 NEXUS

```bash
git clone <repo-url> nexus-oss && cd nexus-oss
./install.sh && nexus init
```

### 2. 写入 MCP 配置

编辑 `~/.codex/config.toml`（TOML 格式）：

```toml
[mcp_servers.nexus-xdr]
url = "http://127.0.0.1:19998/mcp"
http_headers = { "Authorization" = "Bearer <YOUR_TOKEN>" }
```

> 本机实证：`~/.codex/config.toml` 的 `[mcp_servers.nexus-xdr]` 仅需 `url` 一行即可连通
> （本机实例为无鉴权直连）。`http_headers` 写法依据社区文档——官方文档页暂未直核，
> 若你的部署开启了凭据校验而此键不生效，请提 issue（我们会补齐实证）。

### 3. 鉴权初始化

同各家共通：L0 只读工具（`search_knowledge` 等）匿名可用；写入/调度凭据由编排层签发。
先用匿名连通，再按需要配 token。

### 4. 握手验证

新开 Codex 会话（MCP 仅会话创建时加载），让它调用 `search_knowledge` 检索任意关键词；
返回条目即握手成功。

### 5. hello-task 演练

让 Codex 检索一条 NEXUS 经验并按其指引完成一个小改动，结束会话前把心得写回知识库
（写需凭据）——完成最小闭环。

## 已知坑（实机记录）

| 坑 | 现象与对策 |
|---|---|
| reinstall 覆盖配置 | Codex 重装会覆盖 `[mcp_servers]` 段——升级前先备份 `~/.codex/config.toml` |
| OAuth 锁目录 | `~/.codex/mcp-oauth-locks` 残留可致登录态异常，异常时清该目录 |
| `http_headers` 未实证 | 社区文档佐证；本机实例无鉴权直连可用（见步骤2 注记） |

## 故障排查

| 症状 | 先查 |
|---|---|
| 工具列表无 nexus-xdr | 新会话开了吗；TOML 段头是否拼写为 `[mcp_servers.nexus-xdr]` |
| 报配置解析错误 | TOML 内联表语法 `{ "Authorization" = "Bearer ..." }` 用 `=` 不用 `:` |
| 重装后配置消失 | 从备份恢复 `config.toml` 的 `[mcp_servers]` 段 |
| 401 | token 错配；或你的部署没开鉴权却带了错 header |
