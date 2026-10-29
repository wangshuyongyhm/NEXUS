# Dispatch API — minimal examples

> The dispatch bus (`XDR`, default `http://127.0.0.1:19998`) is the single
> channel for task assignment and callbacks. This page gives the smallest
> working calls. All JSON bodies are `application/json`.

## Dispatch a task

Three required fields: `to` (a registered agent name), `task_path` (an
**existing** spec file), and you should set `timeout` (seconds).

```bash
# 0. prerequisite: a task spec on disk
cat > /tmp/hello-task.md <<'EOF'
---
task_id: hello-1
title: hello task
target_agent: <your-agent>
---

# Objective
Reply with one line proving you received this spec.
EOF

# 1. dispatch it
curl -s -X POST http://127.0.0.1:19998/dispatch \
  -H "Content-Type: application/json" \
  -d '{"to": "<your-agent>", "task_path": "/tmp/hello-task.md", "timeout": 600}'
```

Common failure modes (all seen in the wild):

| Symptom | Cause |
|---|---|
| 400 / validation error | body used `task_id` / `task_dir` / `target_agent` — the field names are **`to` + `task_path`** |
| 404 or immediate rejection | `task_path` does not exist on disk, or the `to` agent is not registered |
| 500 after a legal payload | service-side issue — read the bus log; file an issue with the payload |

## Callback (executor → bus)

```bash
curl -s -X POST http://127.0.0.1:19998/callback \
  -H "Content-Type: application/json" \
  -d '{"task_id": "<id returned by dispatch>", "source": "<your-agent>",
       "status": "done", "files": ["output/report.md"], "summary": "..."}'
```

States: `started` (send immediately — the bus re-delivers to silent executors),
`progress`, `need_decision`, `done`, `failed`.

## Check task state

```bash
curl -s "http://127.0.0.1:19998/task_state?limit=10"
```

## Notes on `/health` self-reported fields

The bus `/health` endpoint is a liveness probe, not a configuration source:
its `port` field reports the compiled-in default (not the port the process is
actually listening on when started with `--port`), and its `version` field
may reflect the underlying MCP framework version rather than the package
version. For reconciliation and monitoring, read the effective configuration
from `$NEXUS_HOME/.env` and the package version from the package metadata —
do not scrape these two `/health` fields.

## Schema/meta naming convention

One naming axis, `nexus_meta`: the onboarding wizard creates and maintains the
`nexus_meta` table (layout/schema version keys) when provisioning a database.
Runtime tooling reads the same table. If you see references to a `_meta`
naming in older tooling, treat `nexus_meta` as the canonical name.
