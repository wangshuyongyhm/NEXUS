# starter-vault — the NEXUS constraint layer, ready to drop in

> **Constraints as code for agents.** This package is the declarative rule layer
> of a NEXUS deployment: plain Markdown + YAML, no daemon of its own.

## What this is

A vault starter pack. It gives every agent in your fleet the same small,
enforceable rulebook — so discipline is machine-checked instead of hoped for.
The philosophy in one line: *a rule that no machine enforces is a wish.*

## Contents

| File | Read it when |
|---|---|
| `AGENTS.md` | always loaded by your agent host (each agent's injection point differs — see docs/agents/) |
| `quickref.md` | at every session start — the three gated moments on one page |
| `task-spec.md` | when you write or receive a task spec |
| `protocols.md` | when you dispatch, persist, or coordinate presence |
| `gates/init.yaml` | session-start gate (config present, services reachable) |
| `gates/dispatch.yaml` | pre-dispatch gate (spec exists, target declared) |
| `gates/persist.yaml` | task-close gate (artifacts exist, claims verified) |
| `*.zh-CN.md` | Chinese mirror (section-aligned with the English) |

## How to use it

0. **Install the gate engine** (one of) — prerequisite: Python 3.11+ and, for
   the recommended path, [pipx](https://pipx.pypa.io/) (`brew install pipx`):

   ```bash
   # via pipx (recommended):
   pipx install "git+https://github.com/wangshuyongyhm/nexusos-xdr.git" "git+https://github.com/wangshuyongyhm/nexusos-gate.git"  # or from PyPI once published
   # or a local checkout:
   pip install -e /path/to/pypi/nexusos-gate
   ```

   The `gate_check` tool named in quickref.md comes from the nexus-xdr MCP
   server (`/mcp` on the bus) — configure your agent's MCP client with the
   snippet from docs/agents/, or call the engine CLI directly:
   `python -m nexusos_gate.gate_engine <scenario> '<json-context>'`.

1. **Point the gate engine at these scenarios:**

   ```bash
   export NEXUS_GATES_DIR=/path/to/starter-vault/gates
   ```

2. **Inject `AGENTS.md`** at your agent's instruction point (each agent has its
   own — the wizard prints the right one for every detected agent).

3. **Customize by editing, not forking.** The YAML scenarios are data: add a
   check row, tune a severity, or point `cmd` at your own scripts. User checks
   can also live in `$NEXUS_HOME/gate/checks.d/*.yaml` and are loaded on top.

## What the gates enforce

- **REJECT** — hard block: the action does not happen (missing spec, missing
  artifacts, environment down).
- **WARN** — soft warning: recorded, and you may proceed knowingly.

The done-callback path validates automatically; the other two scenarios run
at session start and before dispatch.

## Layout note (wizard integration)

The setup wizard (`nexus init`) can generate a fresh vault with exactly this
layout (`starter-vault` → your vault root). If you already have a Markdown
directory, drop these files in as-is — the constraint layer is content, not
tooling, and nothing here depends on any specific vault application.
