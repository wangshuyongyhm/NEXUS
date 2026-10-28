# NEXUS — An Orchestration OS for Your Own AI Agents

[![CI](https://img.shields.io/badge/CI-GitHub_Actions-lightgrey)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](#)

> **Bring your own AI agent** (Claude Code, Codex, Kimi (app / CLI), ZCode, Cursor, …) **and your own Obsidian vault — and get a production-grade multi-agent orchestration system**: task dispatch with a single source of truth, a shared knowledge base with hybrid retrieval, declarative quality gates, cross-agent presence awareness, and a self-verifying memory loop.

NEXUS does not replace your AI coding tools. It gives them an operating system.

---

## Table of contents

- [Why NEXUS](#why-nexus)
- [How it compares](#how-it-compares)
- [Features tour](#features-tour)
- [Quickstart](#quickstart-15-minutes)
- [Architecture](#architecture)
- [Agents ecosystem](#agents-ecosystem)
- [How a task flows](#how-a-task-flows)
- [Battle-tested, honestly labeled](#battle-tested-honestly-labeled)
- [FAQ](#faq)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Author](#author)
- [License](#license)

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

## Features tour

### 1. Multi-agent orchestration (XDR bus)

One dispatch channel carries everything: task assignment, progress callbacks, status queries, and a task ledger that is the single source of truth. When several orchestrator agents work in parallel, they all read and write the same ledger — state cannot drift between them. A patrol loop watches executor liveness and re-delivers a task spec if the executor goes silent.

```bash
# Dispatch a task spec to an executor agent over the bus
curl -X POST http://127.0.0.1:19998/dispatch \
  -H "Content-Type: application/json" \
  -d '{"to": "kimi", "task_path": "/abs/path/task.md", "timeout": 3600}'

# The executor reports back over the same channel
curl -X POST http://127.0.0.1:19998/callback \
  -d '{"task_id": "...", "source": "kimi", "status": "done",
       "files": ["output/report.md"], "summary": "what changed and why"}'
```

### 2. Shared knowledge base (MEM)

Read and write are one path: what one agent learns, every agent can find. Retrieval is hybrid — full-text search and BGE-M3 vector similarity are fused, so both exact keywords and fuzzy concepts hit. File-watch keeps the index incremental; nothing waits for a nightly rebuild.

```bash
# Search the shared base (agents authenticate with a task-bound credential)
curl "http://127.0.0.1:11537/search?q=dispatch+timeout&top_k=5"

# Write back what you learned — instantly visible to every other agent
curl -X POST http://127.0.0.1:11537/knowledge \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "kimi", "title": "...", "content": "...",
       "knowledge_type": "pitfall", "tags": ["pypi", "rename"]}'
```

### 3. Declarative quality gates

Rules are data, not prose. Each scenario (init / dispatch / persist / code / state transition) is a YAML file backed by a 46-plugin check pool. Findings are graded **REJECT** (hard block) or **WARN** (soft warning). A `done` callback automatically triggers validation — missing artifacts bounce the task back to the executor.

```yaml
# A gate check is a declarative row, not a paragraph of instructions
- id: C5
  name: tests pass on staged changes
  severity: REJECT          # hard block; WARN would only report
  check:
    type: command
    cmd: python3 -m pytest -q <staged test files>
```

### 4. Presence awareness (PRESENCE)

Agents register when they come online, heartbeat while they work, and declare intent before touching a file. A second declaration on the same target inside a 30-second window is intercepted with `conflict=true`; content fingerprints (hash + mtime + size) catch the "declared, but the file changed underneath" case. Parallel agents stop stepping on each other — and can *see* each other.

```bash
# Declare before you edit — the bus answers conflict=false / true
curl -X POST http://127.0.0.1:19998/session/op-log \
  -H "Content-Type: application/json" \
  -d '{"agent": "kimi", "op": "edit",
       "target": "src/gate_engine.py", "detail": "add C17 check"}'
```

### 5. The epistemic honesty loop

Every time an agent retrieves an experience and applies it, the application is traced. When the task completes, the outcome (`success` / `failed`) is written back, and a background service recalibrates each experience's calibration weight. Knowledge that keeps failing accumulates visible debt and gets re-inspected, hardened, or retired. The memory doesn't just grow — it **verifies itself**.

```bash
# Close the loop: report whether an applied experience actually helped
curl -X POST http://127.0.0.1:11537/apply_outcome \
  -H "Content-Type: application/json" \
  -d '{"exp_id": 107460, "agent_id": "kimi",
       "result": "success", "evidence": "what I ran and observed"}'
```

## Quickstart (≈15 minutes)

The smoke path below was black-box verified end to end: from a clean checkout to the skeleton's boundaries in about 15 minutes.

**Prerequisites**

- macOS (Apple Silicon or Intel) — see *Honest boundaries* below
- Python 3.11+
- PostgreSQL with the `pgvector` extension (the installer can provision this for you — see the FAQ)
- An Obsidian vault (any existing one works — and a Markdown directory is enough, see the FAQ)
- At least one supported AI agent CLI/desktop app — bring your own

**Steps**

```bash
# 1. Clone
git clone <repo-url> nexus-oss && cd nexus-oss

# 2. Install — dependency detection → config generation → service registration
./install.sh

# 3. Guided onboarding (shipping with v1.0.0): the setup wizard scans your
#    environment, negotiates anything missing with fixed choices (never open
#    questions), detects your installed agents, and prints ready-to-paste
#    MCP config snippets for each of them
nexus init

# 4. Smoke-test to the skeleton's boundaries: services up, health
#    endpoints answering, the bus ready for its first dispatch.
```

Re-running `nexus init` is safe: doctor mode re-checks everything and only reports drift — it never overwrites your customizations.

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
    ┌───────▼─────┐ ┌──────▼──────┐ ┌──────▼─────┐ ┌─▼─────────┐
    │ MEM         │ │ EMBED       │ │ OCRX       │ │ CONSOLE   │
    │ knowledge   │ │ embeddings  │ │ vision/UI  │ │ observing │
    │  (:11537)   │ │  (:11436)   │ │  (:11438)  │ │  (:19900) │
    └─────────────┘ └─────────────┘ └────────────┘ └───────────┘
       ▲                                               ▲
       └────────── PostgreSQL + pgvector ──────────────┘
        CONSTRAINT layer: plain Markdown in your vault (no port)
```

| Service | Port | Role |
|---|---|---|
| XDR | 19998 | Dispatch bus: task assignment, callbacks, the `task_state` ledger, presence, patrol |
| MEM | 11537 | Knowledge base: hybrid FTS + vector retrieval, write-through from every agent |
| EMBED | 11436 | BGE-M3 embedding service underneath MEM |
| OCRX | 11438 | Screenshot / OCR / template matching / UI automation |
| CONSOLE | 19900 | Observability console: service health and monitoring aggregation |
| CONSTRAINT | — (vault) | Layered routing protocol in Markdown: ~1 KB always-on routing + on-demand topic documents |

- **XDR (dispatch bus)** — task dispatch / callback / status query over one channel; `task_state` is the single source of truth so multi-agent state never drifts. A patrol loop watches executor health and rescues stalled tasks.
- **MEM (knowledge base)** — BGE-M3 embeddings in PostgreSQL/pgvector, FTS + vector dual retrieval, file-watch incremental indexing. Read and write are one path.
- **EMBED** — the embedding service underneath MEM.
- **OCRX (vision)** — gives the orchestration layer eyes when a task needs them.
- **CONSOLE (observability)** — one place to see fleet health instead of six log tails.
- **CONSTRAINT (rules layer)** — a layered routing protocol living in the vault, so discipline costs minimal context.

### Data flow: dispatch → callback → five-layer persistence

1. **Dispatch** — an orchestrator agent writes a task spec and posts it to the bus; the bus issues a credential (HMAC-SHA256 signed, TTL-bound, task-bound) and delivers the spec to the target agent's session.
2. **Execute** — the executor reads the spec, searches MEM with its credential, and works. Presence heartbeats and a patrol loop keep the orchestrator honest about liveness.
3. **Callback** — `done` / `progress` / `need_decision` land in `task_state`, and the done gate hard-validates the required artifacts before the task may close.
4. **Persist** — five layers of artifacts hit the vault: `input/` (task spec), `process/` (full execution log), `output/report.md` (conclusions), `output/files/` (data artifacts), `output/negative-results.md` (rejected approaches *with reasons*), plus a `reproduce.sh`. Reasoning bought with tokens cannot be regenerated; the next agent — or the next you — never re-pays for the same discovery.

### Federation, not a center

Multiple orchestrator agents can coexist. Before editing a file, an agent declares its intent to the op-log; conflicting declarations are intercepted declaratively, and the human user remains the highest arbiter.

## Agents ecosystem

NEXUS meets your agent where it lives: an MCP endpoint on the dispatch bus, plus a shared instruction-injection convention (an AGENTS.md-style file your agent already reads). Detection features, injection points, and MCP snippets below come from hands-on probing of each tool:

| Agent | Detection fingerprint | Instruction injection point | MCP transport | Config format |
|---|---|---|---|---|
| Claude Code | `~/.claude.json` / `~/.claude/` | `~/.claude/AGENTS.md` + settings hooks | HTTP | JSON |
| Codex | `~/.codex/config.toml` | `~/.codex/AGENTS.md` | HTTP (URL-inferred) | TOML |
| ZCode | `~/.zcode/` | `~/.agents/AGENTS.md` + workspace AGENTS.md | HTTP | JSON |
| Kimi (CLI / desktop) | `~/.kimi-code/` or desktop app dir | `~/.config/kimi/AGENTS.md` / workspace AGENTS.md | HTTP | JSON |
| Cursor | `~/.cursor/` | `.cursor/rules/` + AGENTS.md + hooks.json | streamable-http | JSON |

- **Claude Code** — supported: MCP server entry plus settings hooks for lifecycle events.
- **Codex** — supported: TOML config with inline auth header.*
- **ZCode** — supported: JSON config with automatic migration from legacy header keys.*
- **Kimi (CLI / desktop)** — supported: project-level MCP config; desktop needs the managed source file, not the derived one.
- **Cursor** — supported: MCP config plus three lifecycle hooks (session start / stop / before submit) for broadcast integration.

\* Snippets for Codex and ZCode HTTP transport follow their official or community documentation; every row's detection fingerprint and injection point was verified on a live installation. Where a detail is docs-only rather than machine-verified, the setup wizard says so explicitly instead of guessing.

## How a task flows

Dispatch → execute → callback → persist: see the [data-flow narrative](#data-flow-dispatch--callback--five-layer-persistence) above. The important property is that each stage is machine-checkable: the dispatch is registered, the execution is heartbeated, the callback is validated by a gate, and the persistence layer is linted before the task can close.

## Battle-tested, honestly labeled

NEXUS is not a demo. In daily production use it has:

- **12 heterogeneous AI agents** onboarded through a standardized registry (CLI, desktop app, and IDE modes)
- **1,600+ tasks** tracked end to end through the dispatch bus
- **66,000+ knowledge entries** indexed and served in real time

Hardened through a **16-task engineering pipeline** (447 pytest tests passing; clean-venv import verified 10/10 across all three packages).

## FAQ

**Do I need Obsidian?**
No, not strictly. A vault is a plain Markdown directory — Obsidian is just the nicest viewer for it. During setup you get three fixed choices: point NEXUS at an existing Markdown directory, let the wizard generate a starter vault with the constraint templates (recommended default), or skip the constraint layer entirely and run degraded. The core services work either way.

**Do I need PostgreSQL?**
The knowledge base and task ledger live in PostgreSQL (with pgvector for embeddings). The setup wizard provisions it: it can install PostgreSQL for you (Homebrew on macOS, apt on Linux, or Docker Compose), or — if you already run PostgreSQL — it creates a dedicated database with a least-privilege role and never touches your other databases. A database-free degraded mode (dispatch bus only) exists with an explicit list of what you lose.

**What are the memory requirements?**
The core Python services use about 1.2 GB RSS in daily production (embedding service ~765 MB, dispatch bus ~290 MB, reranker ~124 MB, API ~33 MB, vision ~10 MB), plus roughly 1 GB for PostgreSQL alongside. A 4 GB machine runs it; 8 GB is comfortable.

**How do I update?**
`nexus update` — it checks versions, applies incremental migrations (schema changes are versioned), and prints the changelog. `nexus doctor` re-audits your installation afterwards and only reports drift.

**Does it support Windows?**
Not today. Service supervision (`launchd`) and file-system events (`FSEvents`) are macOS-native in the current release; Linux and Windows support are on the roadmap.

## Roadmap

- **Productization (current focus):** the setup wizard and one-click agent onboarding (MCP/skill connection), a starter vault template, polished docs — in progress; the repo you are reading is part of that push.
- **Cross-platform:** Linux and Windows support (service supervision and file-watching are currently macOS-native).

### Honest boundaries

- **macOS-first today.** Service supervision (`launchd`) and file-system events (`FSEvents`) are macOS-specific; cross-platform is on the roadmap, not in the box.
- **Bring your own agents.** Agent drivers are *not* bundled — NEXUS orchestrates the AI tools you already have; it ships none itself.
- **Obsidian is the vault substrate today.** The Markdown-native constraint layer lives in the vault; a starter vault template is on the roadmap.
- **First release versioning is TBD.** The public repo starts as a source release; tagged releases will follow.

## Contributing

Issues and pull requests are welcome on this repository. If you are reporting a bug, include the output of `nexus doctor` and the failing service's log excerpt — every bug report with evidence gets answered.

## Author

**wangyong** — multi-agent orchestration systems. [GitHub](https://github.com/wangshuyongyhm)

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 wangyong.

---

*Chinese version: [README.zh-CN.md](README.zh-CN.md)*
