# NEXUS — An Orchestration OS for Your Own AI Agents

[![CI](https://img.shields.io/badge/CI-GitHub_Actions-lightgrey)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](#)

> **Bring your own AI agent** (Claude Code, Codex, Kimi (app / CLI), ZCode, Cursor, …) **and your own Obsidian vault — and get a production-grade multi-agent orchestration system**: task dispatch with a single source of truth, a shared knowledge base with hybrid retrieval, declarative quality gates, cross-agent presence awareness, and a self-verifying memory loop.

NEXUS does not replace your AI coding tools. It gives them an operating system.

---

## Why NEXUS

If you use AI coding agents daily, you have probably hit these walls:

- **Context is scarce.** A single agent session forgets everything after compaction. Hard-won debugging insights evaporate between sessions.
- **Experience doesn't compound.** Agent A solved this exact problem last week. Agent B has no way to know, so you pay the tokens again.
- **No quality enforcement.** "Rules written in a markdown file" rely on the model's goodwill. Nothing *hard-blocks* a sloppy handoff.
- **Each agent, its own siloed brain.** Parallel agents stepping on each other's files, with no way to even notice the collision.

NEXUS answers each of these with infrastructure, not prompt conventions:

| Pain | NEXUS answer |
|---|---|
| Context scarcity | A constraint-injection protocol: a ~1 KB routing layer every turn, topic documents loaded on demand |
| Experience evaporation | MEM knowledge base: FTS + vector dual retrieval, write-through from every agent |
| Rule drift | Declarative gates: YAML scenarios, REJECT/WARN severity, 46 check plugins, enforced by machines |
| Agent collisions | PRESENCE: registration, heartbeats, and an op-log that intercepts same-file concurrent edits within a 30 s window |
| Experience rot | An epistemic honesty loop: every applied experience is traced, its outcome written back, its weight recalibrated |

## How it compares

| Dimension | LangGraph Supervisor | OpenAI Swarm | AutoGen GroupChat | **NEXUS** |
|---|---|---|---|---|
| Number of centers | 1 (single-point bottleneck) | 0 (no source of truth) | N (manager = hidden single center) | **N orchestrators in a federation** |
| Coordination | Central LLM routes tasks | Agent-to-agent handoff | Rotating manager | **op-log declarations + directed broadcasts** |
| Shared source of truth | Shared state | None | Shared chat history | **MEM knowledge base + task_state table** |
| Conflict detection | None | None | None | **Declarative interception (`conflict=true`)** |
| Memory verification | None | None | None | **Outcome write-back + calibration weights** |

The existing frameworks orchestrate *roles inside one process*. NEXUS orchestrates *real, heterogeneous CLI/desktop/IDE agents* — the tools you already pay for and already know.

## Quickstart (≈15 minutes)

The smoke path below was black-box verified end to end: from a clean checkout to the skeleton's boundaries in about 15 minutes.

**Prerequisites**

- macOS (Apple Silicon or Intel) — see *Honest boundaries* below
- Python 3.11+
- PostgreSQL with the `pgvector` extension
- An Obsidian vault (any existing one works)
- At least one supported AI agent CLI/desktop app — bring your own

**Steps**

```bash
# 1. Clone
git clone <repo-url> nexus-oss && cd nexus-oss

# 2. Install — dependency detection → config generation → service registration
./install.sh

# 3. Review the generated config (NEXUS_HOME/config.toml):
#    - point NEXUS at your Obsidian vault
#    - confirm the service ports (defaults match a standard local setup —
#      edit config.toml if your PostgreSQL listens elsewhere)

# 4. Smoke-test to the skeleton's boundaries: services up, health
#    endpoints answering, the bus ready for its first dispatch.
```

That's the skeleton boundary today. Agent onboarding — the setup wizard and MCP/skill connection for your own agent — is the current productization focus; see *Roadmap* below.

## Architecture

Five cooperating services plus a Markdown-native constraint layer:

```
        ┌──────────────────────────────────────────────────┐
        │            Your AI agents — any mix              │
        │   Claude Code · Codex · Kimi · Cursor · ZCode    │
        └──────────┬───────────────┬──────────────┬────────┘
                   │  MCP / HTTP   │              │
        ┌──────────▼───────────────▼──────────────▼────────┐
        │   XDR — the dispatch bus              (:19998)   │
        │   dispatch · callback · task_state · presence    │
        └───┬──────────────┬───────────────┬──────────┬────┘
    ┌───────▼─────┐ ┌──────▼──────┐ ┌──────▼─────┐ ┌─▼────────┐
    │ MEM         │ │ EMBED       │ │ OCRX       │ │CONSTRAINT│
    │ knowledge   │ │ embeddings  │ │ vision/UI  │ │ rules    │
    │  (:11537)   │ │  (:11436)   │ │  (:11438)  │ │ (vault)  │
    └─────────────┘ └─────────────┘ └────────────┘ └──────────┘
              PostgreSQL + pgvector underneath
```

- **XDR (dispatch bus)** — task dispatch / callback / status query over one channel; `task_state` is the single source of truth so multi-agent state never drifts. A patrol loop watches executor health and rescues stalled tasks.
- **MEM (knowledge base)** — BGE-M3 embeddings in PostgreSQL/pgvector, FTS + vector dual retrieval, file-watch incremental indexing. Read and write are one path: what one agent learns, every agent can find.
- **EMBED** — the embedding service underneath MEM.
- **OCRX (vision)** — screenshot / OCR / template matching / UI automation, giving the orchestration layer eyes when a task needs them.
- **CONSTRAINT (rules layer)** — a layered routing protocol living in the vault: a small always-on routing layer plus on-demand topic documents, so discipline costs minimal context.

### Federation, not a center

Multiple orchestrator agents can coexist. Before editing a file, an agent declares its intent to the op-log; a second declaration on the same target inside the 30-second window is intercepted (`conflict=true`), and content fingerprints (hash + mtime + size) catch "declared, but the file changed underneath" cases. The human user remains the highest arbiter.

## Three features you won't find elsewhere

### 1. Declarative quality gates

Rules are data, not prose. Each scenario (init / dispatch / persist / code / state transitions) is a YAML file with a 46-plugin check pool; findings are graded **REJECT** (hard block) or **WARN** (soft warning). A `done` callback automatically triggers hard validation — missing artifacts bounce the task back. Discipline is enforced by machines, not by model goodwill.

### 2. The epistemic honesty loop

Every time an agent retrieves an experience and applies it, the application is traced (annotate). When the task completes, the outcome (`success` / `failed`) is written back, and a background service recalibrates each experience's `calibration_weight`. Knowledge that keeps failing accumulates visible debt and gets re-inspected, hardened, or retired. The memory doesn't just grow — it **verifies itself**. This loop ships as a first-class feature: applied experiences are traced, outcomes written back, weights recalibrated.

### 3. Five-layer artifact persistence

Reasoning bought with tokens cannot be regenerated. Every dispatched task persists five layers: `input/` (the task spec), `process/` (the full execution log), `output/report.md` (conclusions), `output/files/` (data artifacts), `output/negative-results.md` (rejected approaches *with reasons*), plus a `reproduce.sh`. The next agent — or the next you — never re-pays for the same discovery.

## How a task flows

1. **Dispatch** — an orchestrator agent writes a task spec and posts it to the bus; the bus issues a credential (HMAC-SHA256 signed, TTL-bound, task-bound) and delivers the spec to the target agent's session.
2. **Execute** — the executor reads the spec, searches MEM with its credential, and works. Presence heartbeats and a 30-second patrol keep the orchestrator honest about liveness.
3. **Callback** — `done` / `progress` / `need_decision` land in `task_state`, and the done gate hard-validates the required artifacts before the task may close.
4. **Persist** — five layers of artifacts hit the vault; high-value findings are written back to MEM, where the honesty loop will keep score on whether they actually help next time.

## Battle-tested, honestly labeled

NEXUS is not a demo. In daily production use it has:

- **12 heterogeneous AI agents** onboarded through a standardized registry (CLI, desktop app, and IDE modes)
- **1,600+ tasks** tracked end to end through the dispatch bus
- **66,000+ knowledge entries** indexed and served in real time

Hardened through a **16-task engineering pipeline** (447 pytest tests passing; clean-venv import verified 10/10 across all three packages).

## Roadmap

- **Productization (current focus):** the setup wizard and one-click agent onboarding (MCP/skill connection), a starter vault template, polished docs — in progress; the repo you are reading is part of that push.
- **Cross-platform:** Linux and Windows support (service supervision and file-watching are currently macOS-native).

### Honest boundaries

- **macOS-first today.** Service supervision (`launchd`) and file-system events (`FSEvents`) are macOS-specific; cross-platform is on the roadmap, not in the box.
- **Bring your own agents.** Agent drivers are *not* bundled — NEXUS orchestrates the AI tools you already have; it ships none itself.
- **Obsidian is the vault substrate today.** The Markdown-native constraint layer lives in the vault; a starter vault template is on the roadmap.
- **First release versioning is TBD.** The public repo starts as a source release; tagged releases will follow.

## License

**Issues and PRs welcome** — open an issue or pull request on this repository.

MIT — see [LICENSE](LICENSE).

---

*Chinese version: [README.zh-CN.md](README.zh-CN.md)*
