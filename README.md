# NEXUS

**A multi-agent orchestration framework for AI CLIs** — NEXUS's primary job is scheduling and coordinating other agents: dispatching tasks across a fleet of coding agents (Kimi CLI, OpenCode, DeepSeek, …), verifying their work through callbacks, and keeping their shared knowledge honest. Everything else (memory bus, gates, embeddings, console) exists to serve that orchestration loop.

> 中文简介见文末（[中文说明](#中文说明)）。

## Status

🚧 **Pre-release skeleton** (v0.1.0). This repository currently contains the package skeleton, install script draft, and architecture documentation. The full source is being migrated from the author's private monorepo after a security scrub (see `docs/sync-strategy.md`).

## Core capabilities

NEXUS 调度其它 Agent 的协作编排，落在四件核心能力上（**roadmap**——能力定义与运行经验来自作者的多 Agent 生产体系，完整源码正从私有主仓脱敏迁移，当前仓库的可用组件是 setup 向导与 Provider 注册表；以下描述的是目标形态而非已交付实现）：

1. **Dispatch 全链调度** — 把任务派给最合适的 Agent：任务书契约（目标/边界/凭据）、目标路由、回调感知（小弟 done 主控必知）。载体：XDR 消息总线（`nexus-xdr`, :19998）——dispatch / callback / task-state / presence 注册。
2. **回调验收闭环** — 完成不是「Agent 说完成了」：done 回调过 gate（产出存在性/报告质量/经验回流逐项机器验收），验收通过才算交付。载体：GateKit（`nexus-gatekit`）——声明式 YAML 检查（REJECT/WARN）。
3. **认知诚实（经验可验证可纠正）** — Agent 干完活必须回流经验；经验被套用后必须回填真实结果（success/failed），多主验证裁定权重——经验不是越老越值钱，是被验证越多越值钱。载体：MEM 共享知识库（`nexus-mem`, :11537）——FTS+向量混合检索（BGE-M3 中英双语）+ apply-outcome 追踪。
4. **多主控联邦** — N 个主控并存（各自的 supervisor），op-log 声明式冲突检测 + 共享真相源（MEM/task-state）+ 用户最高仲裁；并行是目标，冲突上浮不多数决。

配套（服务于编排循环）：**Embed**（:11436，文件监视→BGE-M3→pgvector）、**Console**（:19900，只读可观测台）。

> macOS-only extras (OCRX screen-control, TCC-gated checks) are intentionally layered outside the core distribution.

## Quickstart (draft)

Requirements: macOS 13+ (Linux roadmap: see below), Python ≥3.10,<3.12, PostgreSQL 15 + pgvector, pgbouncer.

```bash
# 1. Install (creates ~/.nexus/venv — never touches your ambient python)
./install.sh

# 2. heavy ML deps (torch/BGE, ~5GB) only if you need embeddings:
~/.nexus/venv/bin/pip install -e "packages/nexus-mem[full]"

# 3. Connect your providers (see "Provider onboarding" below):
#    local web wizard at http://127.0.0.1:<random-port>/ — add/remove
#    platforms freely, fill keys, get live red/green connectivity tests;
#    keys land in ~/.nexus/.env (chmod 600), NEVER in the repo
~/.nexus/venv/bin/nexus setup

# 4. Check what the scheduler can see (dispatch-ready providers):
~/.nexus/venv/bin/nexus providers

# 5. Initialize the database (schema + migrations are in db/):
#    createdb nexus_mem && psql -d nexus_mem -f db/schema.sql
#    for f in db/migrations/00*.sql; do psql -d nexus_mem -f "$f"; done

# 6. Start services — launchd plist generation is PLANNED (not yet built;
#    templates/launchd/ will ship with the source migration). Linux systemd
#    user units: TODO (see install.sh header)
```

The installer stops with a clear message at the "missing real configuration"
step (vault root, PG DSN, model dir) — that is expected for the skeleton.

## Provider onboarding（接入配置）

Key 配置是**接入层**，不是产品本体——NEXUS 编排调度 Agent，各家 LLM/Bot 平台只是被调度的算力与通知通道。

- **平台可自定义增删**：`~/.nexus/providers.json`（`NEXUS_AGENT_PROVIDERS`）是单一真源——内置智谱/Kimi/DeepSeek/OpenRouter/Telegram/飞书六平台出厂预置，可删、可改、可添加任意自定义平台（四要素：id / env 变量名 / 帮助链接 / 探活方式）
- **向导**：`nexus setup` 页内即可增删平台；自定义平台支持通用 HTTP 探活（`{VAR}` 占位替换 + 预期状态码），填错即时红绿反馈
- **密钥卫生**：真值只写 `~/.nexus/.env`（仓库目录之外，mode 600）；仓库内只有空值模板 `.env.example`
- **调度可见性**：新平台配好 key 后，调度层经同一注册表可见（`nexus providers` / `configured_providers()`，契约见 `docs/agent-providers.md`）

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `NEXUS_HOME` | runtime home (venv, config.toml, .env) | `~/.nexus` |
| `NEXUS_ENV_FILE` | .env target path for `nexus setup` | `$NEXUS_HOME/.env` |
| `NEXUS_AGENT_PROVIDERS` | provider registry JSON path | `$NEXUS_HOME/providers.json` (wizard; `~/.nexus/providers.json` for `nexus providers`) |
| `NEXUS_PYTHON` | interpreter override for install.sh | auto-detect (python3.11 → python3.10 → python3) |
| `NEXUS_PG_DSN` | PostgreSQL DSN (via pgbouncer) | `postgresql://localhost:6432/nexus_mem` |
| `NEXUS_MODEL_DIR` | BGE model cache dir | `~/.cache/huggingface/hub` |

## Linux

Core services (MEM/XDR/GateKit/Embed/Console) are portable in principle; the
launchd → systemd-user translation layer is a designed-but-not-built TODO
(`install.sh` marks the seams). OCRX is macOS-only by design (Vision framework
+ CGEvent) and is not part of the core distribution.

## License

MIT (see `LICENSE`). Third-party obligations in `NOTICE` (psycopg2 LGPL,
opencv/FFmpeg, fswatch GPL-via-subprocess). Model weights are downloaded at
install time and are MIT-licensed (BAAI).

---

## 中文说明

NEXUS 是一套**多 Agent 协作编排调度框架**：主要职责是调度其它 Agent——把任务
派发给一组 AI CLI（Kimi/OpenCode/DeepSeek…）、用回调验收它们的交付、让它们的
共享经验可验证可纠正、并支持多主控联邦并行。四件核心能力（dispatch 全链调度/
回调验收闭环/认知诚实/多主控联邦）之下，记忆库（MEM）、消息总线（XDR）、门禁
引擎（GateKit）、嵌入服务（Embed）与可观测台（Console）都是编排循环的载体。

平台 key 的配置只是接入层：`nexus setup` 向导支持自由增删平台（内置六家 +
任意自定义），真值永不出本机。当前为**开源骨架预览版**（v0.1.0）：包结构、
安装脚本草稿与架构文档已就位，完整源码正在从私有主仓脱敏迁移（策略见
`docs/sync-strategy.md`）。

快速上手见上方 Quickstart——照走到「缺真实配置」提示为止即符合预期。
