# quickref.md — the three gated moments (one-page card)

> Read at session start. Each row: what to do + the command. The gate engine
> already enforces the hard parts — this card is your muscle memory.
> Paths assume `$NEXUS_HOME` (default `~/.nexus`) and the default ports.

## Scenario 0 — who am I (10 seconds)

| You are | Read |
|---|---|
| Orchestrator (dispatching) | this card + protocols.md §dispatch |
| Executor (dispatched) | this card + protocols.md §persist |

## Scenario 1 — init (session start / restart / context-loss recovery)

1. Read this card → confirm your role.
2. Register presence: `POST $XDR/session/register` `{agent, role, session_id, current_task}`
3. See who is online: `GET $XDR/session/active`
4. Health-check services: six ports 11436/11438/11537/19998/4001/19900 →
   `/health` (the init gate machine-checks two of them: the bus and MEM;
   check the rest yourself)
5. Run the init gate: `gate_check(scenario="init", context={agent, role, session_id})`
6. Report readiness to the human (or to your orchestrator).

```bash
curl -s -X POST "$NEXUS_XDR_URL/session/register" -H "Content-Type: application/json" \
  -d '{"agent":"<name>","role":"executor","session_id":"<name>-<MMDDHHmm>","status":"init"}'
curl -s "$NEXUS_XDR_URL/session/active"
```

## Scenario 2 — dispatch

**Orchestrator, before sending:**

1. Target executor alive? (presence active list)
2. Parallel-conflict sweep: op-log declarations on the same files in the last 120 s
3. Write the task spec (task-spec.md seven sections) + references with real content
4. Register on the bus: `POST /dispatch {to, task_path, caller, timeout}` —
   `caller` names you so the ledger stays honest — then start waiting for
   callbacks in the same turn (do not poll blindly)
5. Pass the dispatch gate first: `gate_check(scenario="dispatch", ...)`

**Executor, on receiving:**

1. Read the spec copy → verify the credential (missing = refuse, ask back)
2. Callback `started` immediately (the bus re-delivers if you stay silent)
3. Search MEM with your credential before acting
4. Work → `progress` callbacks at milestones → persist → `done`

## Scenario 3 — persist (closing a task)

**Executor, before `done`:**

1. `output/report.md` with evidence + a machine-readable tail block
2. `process/` log + `output/files/` non-empty + `negative-results.md`
3. Every path in your `files[]` actually exists on disk (verify, never claim)
4. Write high-value findings back to MEM
5. Only then callback `done`

**Orchestrator, closing the loop:**

1. Read every done summary; ack with a restatement of key points
2. Spot-check `files[]` on disk
3. Reflux lessons into MEM and your agent's own profile
4. `gate_check(scenario="persist", ...)` before final commit

## Defaults

- XDR bus: `http://127.0.0.1:19998` · MEM: `http://127.0.0.1:11537`
- `$NEXUS_HOME` default `~/.nexus` (config / logs / data / keys live there)
- When in doubt: search MEM first, read the topic doc second, ask the human third.
