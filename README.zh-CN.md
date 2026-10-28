# NEXUS —— 给你自己的 AI Agent 装一套编排操作系统

[![CI](https://img.shields.io/badge/CI-GitHub_Actions-lightgrey)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](#)

> **带上你自己的 AI Agent**（Claude Code、Codex、Kimi（App/CLI）、ZCode、Cursor……）**和你自己的 Obsidian 仓库，就能获得一套生产级多 Agent 编排系统**：带单一真相源的任务派发、双路检索的共享知识库、声明式质量门禁、跨 Agent 在场感知，以及自我验证的记忆闭环。

NEXUS 不替换你的 AI 工具，而是给它们装上操作系统。

---

## 目录

- [为什么是 NEXUS](#为什么是-nexus)
- [和市场方案的对照](#和市场方案的对照)
- [能力巡览](#能力巡览)
- [快速上手](#快速上手约-15-分钟)
- [架构](#架构)
- [Agent 生态](#agent-生态)
- [一个任务的完整旅程](#一个任务的完整旅程)
- [实战成色，诚实标注](#实战成色诚实标注)
- [常见问题](#常见问题)
- [路线图](#路线图)
- [参与贡献](#参与贡献)
- [作者](#作者)
- [许可证](#许可证)

## 为什么是 NEXUS

每天用 AI 编码 Agent 的人，多半撞过这几堵墙：

- **上下文稀缺**：单次会话压缩后一切归零，辛苦调试出的洞察随会话蒸发。
- **经验不复利**：Agent A 上周刚解决过同样的问题，Agent B 无从得知，同一笔 token 再交一遍。
- **规则靠自觉**：写在 markdown 里的纪律没有任何**硬性拦截**，漏不漏全看模型心情。
- **多 Agent 互踩**：并行 Agent 改同一个文件，连碰撞发生了都察觉不到。

NEXUS 的回答是基础设施，不是提示词技巧：

| 痛点 | NEXUS 的答法 |
|---|---|
| 上下文稀缺 | 约束注入协议：每轮只注入约 1KB 路由层，专题文档按需加载 |
| 经验蒸发 | MEM 知识库：FTS + 向量双路检索，所有 Agent 读写同一条管道 |
| 规则漂移 | 声明式门禁：场景 YAML 化，46 个检查插件，REJECT/WARN 分级，机器硬拦 |
| Agent 互踩 | PRESENCE 在场感知：注册/心跳/op-log 声明，30 秒窗口内同文件并发声明即拦截 |
| 记忆腐化 | 认知诚实闭环：经验套用强制留痕，结果回填，权重再校准 |

## 和市场方案的对照

| 维度 | LangGraph Supervisor | OpenAI Swarm | AutoGen GroupChat | **NEXUS** |
|---|---|---|---|---|
| 中心数 | 1（单点瓶颈） | 0（无真相源） | N（manager 实为隐式单中心） | **N 主控并存（联邦制）** |
| 协调机制 | 中央 LLM 分派 | agent 间 handoff | manager 轮转 | **op-log 声明 + 定向广播** |
| 共享真相源 | shared state | 无 | 共享对话历史 | **MEM 知识库 + task_state 表** |
| 冲突检测 | 无 | 无 | 无 | **声明式拦截（conflict=true）** |
| 记忆验证 | 无 | 无 | 无 | **outcome 回填 + 校准权重** |

现有框架编排的是**单进程内的角色**；NEXUS 编排的是**真实的异构 CLI/桌面/IDE Agent**——你已经在用、已经在付费的那些工具。

## 能力巡览

### 1. 多 Agent 编排（XDR 总线）

一条派发通道承载一切：任务分派、进度回调、状态查询，以及作为单一真相源的任务台账。多个主控 Agent 并行工作时读写同一本台账，状态永不漂移。巡逻循环盯执行端存活，执行端静默超时自动重投任务书。

```bash
# 通过总线把任务书派给执行 Agent
curl -X POST http://127.0.0.1:19998/dispatch \
  -H "Content-Type: application/json" \
  -d '{"to": "kimi", "task_path": "/abs/path/task.md", "timeout": 3600}'

# 执行端经同一通道回报
curl -X POST http://127.0.0.1:19998/callback \
  -d '{"task_id": "...", "source": "kimi", "status": "done",
       "files": ["output/report.md"], "summary": "改了什么、为什么"}'
```

### 2. 共享知识库（MEM）

读写一体：一个 Agent 学到的，所有 Agent 能查到。检索是混合双路——全文检索与 BGE-M3 向量相似度融合，精确关键词和模糊概念都能命中。文件监听让索引保持增量，不等夜间重建。

```bash
# 检索共享知识库（Agent 用任务绑定凭据认证）
curl "http://127.0.0.1:11537/search?q=dispatch+timeout&top_k=5"

# 把学到的东西写回——其他 Agent 立即可见
curl -X POST http://127.0.0.1:11537/knowledge \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "kimi", "title": "...", "content": "...",
       "knowledge_type": "pitfall", "tags": ["pypi", "rename"]}'
```

### 3. 声明式质量门禁

规则即数据，不是口号。每个场景（init/dispatch/persist/code/状态迁移）一份 YAML，背后是 46 个检查插件池。判定分 **REJECT**（硬拦）与 **WARN**（软警告）两级。`done` 回调自动触发校验——产出缺失直接把任务打回执行端。

```yaml
# 门禁检查是一行声明式配置，不是一段嘱咐
- id: C5
  name: staged 改动测试通过
  severity: REJECT          # 硬拦；WARN 只报告
  check:
    type: command
    cmd: python3 -m pytest -q <staged 测试文件>
```

### 4. 在场感知（PRESENCE）

Agent 上线注册、工作中持续心跳、动文件前先声明意图。30 秒窗口内同目标出现第二份声明即被拦截（`conflict=true`）；内容指纹（hash+mtime+size）识别「声明之后文件被偷改」。并行 Agent 不再互踩——而且互相**看得见**。

```bash
# 改文件前先声明——总线回答 conflict=false / true
curl -X POST http://127.0.0.1:19998/session/op-log \
  -H "Content-Type: application/json" \
  -d '{"agent": "kimi", "op": "edit",
       "target": "src/gate_engine.py", "detail": "加 C17 检查"}'
```

### 5. 认知诚实闭环

Agent 每次检索并套用经验都强制留痕；任务结束时回填结果（`success`/`failed`）；后台服务据此重算每条经验的校准权重。持续失败的经验累积可见的债务分，被复检、固化或淘汰。记忆不只会增长，还会**自我验证**。

```bash
# 闭环：回报套用的经验是否真的帮了忙
curl -X POST http://127.0.0.1:11537/apply_outcome \
  -H "Content-Type: application/json" \
  -d '{"exp_id": 107460, "agent_id": "kimi",
       "result": "success", "evidence": "我实际跑了什么、看到什么"}'
```

## 快速上手（约 15 分钟）

以下冒烟路径已做黑盒实证：从干净检出到骨架边界约 15 分钟。

**前置条件**

- macOS（Apple Silicon / Intel）——见下方「诚实边界」
- Python 3.11+
- 带 pgvector 的 PostgreSQL（安装器可代为置备——见常见问题）
- 一个 Obsidian 仓库（任何现成的都行——纯 Markdown 目录也够，见常见问题）
- 至少一个受支持的 AI Agent（自带，不随包出厂）

**步骤**

```bash
# 1. 克隆
git clone <repo-url> nexus-oss && cd nexus-oss

# 2. 安装——依赖探测 → 配置生成 → 服务注册
./install.sh

# 3. 引导式接入（随 v1.0.0 发布）：安装向导扫描你的环境，
#    缺什么用固定选项协商（从不出开放题），探测你已装的 Agent，
#    并为每家打印复制即用的 MCP 配置片段
nexus init

# 4. 冒烟到骨架边界：服务起来，健康端点全通，总线就绪待首次派发
```

重复跑 `nexus init` 是安全的：doctor 模式会对账所有配置项，只报告漂移——从不覆盖你的自定义。

## 架构

五个协作服务 + 一层 Markdown 原生的约束层：

```
        ┌──────────────────────────────────────────────────┐
        │            你的 AI Agent —— 任意组合              │
        │   Claude Code · Codex · Kimi · Cursor · ZCode    │
        └──────────┬───────────────┬──────────────┬────────┘
                   │  MCP / HTTP   │              │
        ┌──────────▼───────────────▼──────────────▼────────┐
        │   XDR —— 调度总线                     (:19998)   │
        │   派发 · 回调 · task_state · 在场感知            │
        └───┬──────────────┬───────────────┬──────────┬────┘
    ┌───────▼─────┐ ┌──────▼──────┐ ┌──────▼─────┐ ┌─▼─────────┐
    │ MEM 知识库  │ │ EMBED 嵌入  │ │ OCRX 视觉  │ │ CONSOLE   │
    │  (:11537)   │ │  (:11436)   │ │  (:11438)  │ │  (:19900) │
    └─────────────┘ └─────────────┘ └────────────┘ └───────────┘
       ▲                                                ▲
       └────────── PostgreSQL + pgvector ───────────────┘
        CONSTRAINT 约束层：vault 里的纯 Markdown（无端口）
```

| 服务 | 端口 | 职责 |
|---|---|---|
| XDR | 19998 | 调度总线：任务分派、回调、task_state 台账、在场感知、巡逻 |
| MEM | 11537 | 知识库：FTS+向量混合检索，所有 Agent 读写同一条管道 |
| EMBED | 11436 | MEM 底层的 BGE-M3 向量嵌入服务 |
| OCRX | 11438 | 截图 / OCR / 模板匹配 / UI 自动化 |
| CONSOLE | 19900 | 观测台：服务健康与监控聚合 |
| CONSTRAINT | —（vault） | Markdown 分层路由协议：约 1KB 常驻路由层 + 按需专题文档 |

- **XDR 调度总线**：派发/回调/状态查询统一通道，`task_state` 表是唯一真相源，多 Agent 状态不漂移；巡逻看护执行端健康，卡住自动救援。
- **MEM 知识库**：BGE-M3 向量嵌入存 pgvector，FTS + 向量双路召回，文件监听增量索引。
- **EMBED**：MEM 底层的向量嵌入服务。
- **OCRX 视觉**：给调度层一双眼睛，任务需要看画面时上场。
- **CONSOLE 观测台**：一个端点看全舰队健康，代替六条日志尾巴。
- **CONSTRAINT 约束层**：住在 vault 里的分层路由协议，纪律只花最少上下文。

### 数据流：派发 → 回调 → 五层落盘

1. **派发**——主控 Agent 写好任务书发到总线；总线签发凭据（HMAC-SHA256 签名、限时、绑定任务）并把任务书投递到目标 Agent 的会话。
2. **执行**——执行端读任务书、带凭据检索 MEM、开工。心跳与巡逻循环让主控对存活性保持诚实。
3. **回调**——`done`/`progress`/`need_decision` 落入 `task_state`；done 门禁硬校验产出齐全才允许关单。
4. **落盘**——五层资产沉入 vault：input（任务书）、process（全过程日志）、output/report（结论）、output/files（数据产出）、output/negative-results（被否决的方案**附否决原因**），外加可复现脚本。token 买来的推理过程不可再生；下一个 Agent——或者下一个你——永远不必为同一个发现重复付费。

### 联邦而非中心

多主控并存。改文件前必须先向 op-log 声明意图；冲突声明被声明式拦截；用户永远是最高仲裁者。

## Agent 生态

NEXUS 就你的 Agent 所在地接入：调度总线上的 MCP 端点 + 一套共享的指令注入约定（你的 Agent 本来就在读的 AGENTS.md 类文件）。下表的探测特征、注入点、MCP 片段全部来自对各工具的实机探测：

| Agent | 探测特征 | 指令注入点 | MCP 传输 | 配置格式 |
|---|---|---|---|---|
| Claude Code | `~/.claude.json` / `~/.claude/` | `~/.claude/AGENTS.md` + settings hooks | HTTP | JSON |
| Codex | `~/.codex/config.toml` | `~/.codex/AGENTS.md` | HTTP（按 URL 自动识别） | TOML |
| ZCode | `~/.zcode/` | `~/.agents/AGENTS.md` + 工作区 AGENTS.md | HTTP | JSON |
| Kimi（CLI/桌面） | `~/.kimi-code/` 或桌面应用目录 | `~/.config/kimi/AGENTS.md` / 工作区 AGENTS.md | HTTP | JSON |
| Cursor | `~/.cursor/` | `.cursor/rules/` + AGENTS.md + hooks.json | streamable-http | JSON |

- **Claude Code**——已支持：MCP server 条目 + settings hooks 接生命周期事件。
- **Codex**——已支持：TOML 配置 + 内联鉴权头。*
- **ZCode**——已支持：JSON 配置，legacy header 键自动迁移。*
- **Kimi（CLI/桌面）**——已支持：项目级 MCP 配置；桌面端要写托管源文件而非派生文件。
- **Cursor**——已支持：MCP 配置 + 三个生命周期 hook（会话开始/停止/提交前）接广播。

\* Codex 与 ZCode 的 HTTP 传输片段依据其官方或社区文档；表中每行的探测特征与注入点均在真实安装上验证过。凡属「仅文档、未实机核验」的细节，安装向导会明说而不是猜。

## 一个任务的完整旅程

派发 → 执行 → 回调 → 落盘：见上方[数据流叙述](#数据流派发--回调--五层落盘)。关键性质是每一环都机器可验：派发有登记、执行有心跳、回调过门禁、落盘过 lint——四关全过任务才能关闭。

## 实战成色，诚实标注

不是演示项目。日常生产运行中：标准化接入 **12 家异构 AI Agent**（CLI/桌面/IDE 三种模式）；调度总线全程追踪 **1600+ 任务**；知识库实时索引 **66,000+ 条目**。

经 **16 单硬化工程链** 打磨（447 个 pytest 全过、干净 venv 三包 import 验证 10/10）。

## 常见问题

**必须有 Obsidian 吗？**
不必须。vault 本质是一个纯 Markdown 目录——Obsidian 只是它最好用的查看器。安装时你有三个固定选项：指向一个已有的 Markdown 目录；让向导生成带约束模板的 starter vault（推荐默认）；或跳过约束层降级运行。核心服务哪种都转。

**必须有 PostgreSQL 吗？**
知识库和任务台账存在 PostgreSQL 里（向量部分用 pgvector）。安装向导负责置备：可以替你装好 PostgreSQL（macOS 走 Homebrew、Linux 走 apt、或 Docker Compose）；如果你已有 PostgreSQL，向导会建一个专属库并配最小权限角色——绝不碰你的其他库。也保留无数据库的降级模式（仅调度总线），损失清单会明示。

**内存要多大？**
核心 Python 服务日常生产实测约 1.2GB RSS（嵌入服务约 765MB、调度总线约 290MB、rerank 约 124MB、API 约 33MB、视觉约 10MB），外加 PostgreSQL 约 1GB。4GB 机器可跑，8GB 舒适。

**怎么更新？**
`nexus update`——查版本、跑增量迁移（schema 变更有版本轴）、打印 CHANGELOG。之后 `nexus doctor` 复检安装，只报差异。

**支持 Windows 吗？**
当前版本的服务守护（launchd）与文件事件（FSEvents）是 macOS 原生实现；Linux 与 Windows 支持在路线图上。

## 路线图

- **产品化（当前重点）**：安装向导 + Agent 一键接入（MCP/skill 连接）、starter vault 模板、文档打磨——进行中；你正在读的这个仓库就是该工作的一部分。
- **跨平台**：Linux/Windows 支持（服务守护与文件监听目前是 macOS 原生实现）。

### 诚实边界

- **macOS-first**（launchd/FSEvents 依赖）；
- **Agent 驱动不随包出厂**（自带你自己的工具）；
- **Obsidian 是当前的仓库底座**：Markdown 原生的约束层住在 vault 里，starter vault 模板在路线图上；
- **首个发行版本号待定**。

## 参与贡献

欢迎在本仓库提 issue 和 pull request。报 bug 请附上 `nexus doctor` 的输出和故障服务的日志节选——带证据的报告都会得到回应。

## 作者

**wangyong** —— 多 Agent 编排系统作者。[GitHub](https://github.com/wangshuyongyhm)

## 许可证

MIT —— 见 [LICENSE](LICENSE)。Copyright (c) 2026 wangyong。

---

*English version: [README.md](README.md)*
