# protocols.md — the three wire protocols (generic)

> NEXUS coordination runs on three small protocols. Each is described here
> with its message shapes and a worked example. Everything rides plain HTTP. The same bus also exposes an MCP endpoint
> (`/mcp`) for agents that speak MCP.

## 1. Dispatch — task assignment over the bus

The bus (`:19998`) is the single channel for task assignment. An orchestrator
posts a task spec; the bus registers it in the ledger (`task_state` — the one
source of truth), issues a task-bound credential, and delivers the spec to the
executor's session.

**Send:**

```bash
curl -X POST http://127.0.0.1:19998/dispatch \
  -H "Content-Type: application/json" \
  -d '{"to": "<executor>", "task_path": "/abs/path/task.md", "timeout": 3600}'
```

**Callback states** (executor → bus, same channel):

| State | When | Required fields |
|---|---|---|
| `started` | immediately after reading the spec | task_id, source |
| `progress` | at milestones | + summary |
| `need_decision` | blocked, needs a human/orchestrator choice | + the question with numbered options |
| `done` | artifacts persisted, gate green | + files[], tests, summary |
| `failed` | unrecoverable | + error |

```bash
curl -X POST http://127.0.0.1:19998/callback \
  -H "Content-Type: application/json" \
  -d '{"task_id": "<id from the dispatched copy>", "source": "<your name>",
       "status": "done", "files": ["output/report.md"], "summary": "..."}'
```

**Waiting:** the orchestrator waits asynchronously for callbacks — it does not
poll screenshots or sleep-loop. The bus records every callback in the ledger;
a patrol loop re-delivers specs whose executor goes silent, and flags tasks
that exceed their timeout.

## 2. Persist — the five-layer artifact contract

Token-bought reasoning cannot be regenerated, so every task ends with five
layers on disk:

```
task/<id>-<name>/
├── input/            # the task spec (and its dispatched copy)
├── process/          # the full execution log
├── output/
│   ├── report.md            # conclusions, with a machine-readable tail
│   ├── files/               # every data artifact the task produced
│   └── negative-results.md  # rejected approaches, each with its reason
└── reproduce.sh      # one command to re-verify the claims
```

Quality bars: the report carries evidence (commands + outputs, or file paths
that exist), `files[]` claims are verified on disk before `done`, and the
negative-results layer names what was *not* done and why. A task without
artifacts is not done — the persist gate bounces it.

## 3. Presence — seeing the fleet

Agents register, heartbeat, declare, and broadcast:

```bash
# register (once, at session start)
curl -X POST http://127.0.0.1:19998/session/register \
  -d '{"agent": "<name>", "role": "executor", "session_id": "<id>", "status": "init"}'

# declare intent before editing a shared file
curl -X POST http://127.0.0.1:19998/session/op-log \
  -d '{"agent": "<name>", "op": "edit", "target": "<file>", "detail": "<what>"}'
# → {"conflict": true} means another agent declared the same target inside
#    the 30-second window — stop and coordinate, don't force it.

# broadcast a completion the fleet should know about
curl -X POST http://127.0.0.1:19998/session/broadcast \
  -d '{"sender": "<name>", "message": "<what changed>", "msg_type": "alert"}'
```

Presence answers the questions a fleet constantly asks: who is online, who is
working on what, and did anyone just touch my file. Content fingerprints
(hash + mtime + size) catch the "declared, but the file changed underneath"
case. The human remains the highest arbiter of any conflict.

## How the three interlock

Dispatch moves work; presence makes parallel work visible; persist makes
finished work permanent. The gates (init / dispatch / persist) sit at the
three seams and enforce the contracts mechanically — see `gates/`.
