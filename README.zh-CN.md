# NEXUS —— 给你自己的 AI Agent 装一套编排操作系统

[![CI](https://img.shields.io/badge/CI-GitHub_Actions-lightgrey)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](#)

> **带上你自己的 AI Agent**（Claude Code、Codex、Kimi（App/CLI）、ZCode、Cursor……）**和你自己的 Obsidian 仓库，就能获得一套生产级多 Agent 编排系统**：带单一真相源的任务派发、双路检索的共享知识库、声明式质量门禁、跨 Agent 在场感知，以及自我验证的记忆闭环。

NEXUS 不替换你的 AI 工具，而是给它们装上操作系统。

---

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

## 快速上手（约 15 分钟）

以下冒烟路径已做黑盒实证：从干净检出到骨架边界约 15 分钟。

**前置条件**：macOS（Apple Silicon / Intel）；Python 3.11+；带 pgvector 的 PostgreSQL；一个 Obsidian 仓库；至少一个受支持的 AI Agent（自带，不随包出厂）。

```bash
# 1. 克隆
git clone <repo-url> nexus-oss && cd nexus-oss

# 2. 安装——依赖探测 → 配置生成 → 服务注册
./install.sh

# 3. 核对生成的配置（NEXUS_HOME/config.toml）：指向你的 Obsidian 仓库 → 确认服务端口（默认适配标准本地环境——PostgreSQL 在别处时改 config.toml）

# 4. 冒烟到骨架边界：服务起来，健康端点全通，总线就绪待首次派发
```

这就是今天的骨架边界。Agent 接入（安装向导 + 你自己 Agent 的 MCP/skill 连接）是当前产品化重点，见下方路线图。

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
        │   派发 · 回调 · task_state · 在场感知      │
        └───┬──────────────┬───────────────┬──────────┬────┘
    ┌───────▼─────┐ ┌──────▼──────┐ ┌──────▼─────┐ ┌─▼────────┐
    │ MEM 知识库  │ │ EMBED 嵌入  │ │ OCRX 视觉  │ │CONSTRAINT│
    │  (:11537)   │ │  (:11436)   │ │  (:11438)  │ │ 约束路由 │
    └─────────────┘ └─────────────┘ └────────────┘ └──────────┘
                底层：PostgreSQL + pgvector
```

- **XDR 调度总线**：派发/回调/状态查询统一通道，`task_state` 表是唯一真相源，多 Agent 状态不漂移；巡逻看护执行端健康，卡住自动救援。
- **MEM 知识库**：BGE-M3 向量嵌入存 pgvector，FTS + 向量双路召回，文件监听增量索引。读写一体：一个 Agent 学到的，所有 Agent 能查到。
- **EMBED**：MEM 底层的向量嵌入服务。
- **OCRX 视觉**：截图/OCR/模板匹配/UI 自动化，给调度层一双眼睛。
- **CONSTRAINT 约束层**：常驻小路由层 + 按需专题文档，纪律只花最少上下文。

**联邦而非中心**：多主控并存。改文件前必须先向 op-log 声明意图；30 秒窗口内同目标出现第二份声明即拦截（conflict=true）；内容指纹（hash+mtime+size）识别「声明后文件被偷改」。用户永远是最高仲裁者。

## 三个别处找不到的特性

**① 声明式质量门禁**：规则即数据。每个场景（init/dispatch/persist/code/状态迁移）一份 YAML，46 个检查插件池，REJECT 硬拦/WARN 软警告分级。done 回调自动触发硬校验，产出缺失直接打回——纪律由机器执行，不靠模型自觉。

**② 认知诚实闭环**：Agent 检索并套用经验时强制留痕（annotate）；任务结束时回填结果（success/failed）；后台服务据此重算每条经验的校准权重（calibration_weight）。持续失败的经验自动累积债务分，被巡检、固化或淘汰。记忆不只会增长，还会**自我验证**。

**③ 五层落盘资产**：token 买来的推理过程不可再生。每个派发任务沉淀五层：input（任务书）、process（全过程日志）、output/report（结论）、output/files（数据产出）、output/negative-results（被否决的方案**附否决原因**），外加一份可复现脚本。下一个 Agent——或者下一个你——永远不必为同一个发现重复付费。

## 实战成色，诚实标注

不是演示项目。日常生产运行中：标准化接入 **12 家异构 AI Agent**（CLI/桌面/IDE 三种模式）；调度总线全程追踪 **1600+ 任务**；知识库实时索引 **66,000+ 条目**。

经 **16 单硬化工程链** 打磨（447 个 pytest 全过、干净 venv 三包 import 验证 10/10）。

## 路线图

- **产品化（当前重点）**：安装向导 + Agent 一键接入（MCP/skill 连接）、starter vault 模板、文档打磨——进行中；你正在读的这个仓库就是该工作的一部分。
- **跨平台**：Linux/Windows 支持（服务守护与文件监听目前是 macOS 原生实现）。

### 诚实边界

- **macOS-first**（launchd/FSEvents 依赖）；
- **Agent 驱动不随包出厂**（自带你自己的工具）；
- **Obsidian 是当前的仓库底座**：Markdown 原生的约束层住在 vault 里，starter vault 模板在路线图上；
- **首个发行版本号待定**。

## License

**Issues 与 PR 欢迎**——在本仓库提 issue 或 pull request。

MIT —— 见 [LICENSE](LICENSE)。

---

*English version: [README.md](README.md)*
