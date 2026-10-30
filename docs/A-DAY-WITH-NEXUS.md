# A day with NEXUS — what your first day actually looks like

> This is a walkthrough of a real first day after installing NEXUS.
> Every command and capability shown here exists in the current release —
> nothing is promised that isn't shipped. Where a step is still manual today,
> we say so.

## Morning: install and initialize

You clone the repo and run the installer. It detects dependencies, creates an
isolated environment, and generates your configuration:

```bash
git clone https://github.com/wangshuyongyhm/NEXUS.git nexus-oss && cd nexus-oss
./install.sh
```

Then the one-time schema step (today this is a documented manual step — the
wizard provisions your database but does not yet apply the schema for you):

```bash
createdb nexus_mem 2>/dev/null; psql -d nexus_mem -c 'CREATE EXTENSION IF NOT EXISTS vector'
psql -d nexus_mem -f db/schema.sql
```

Now the wizard. Type "initialize" — or run it directly:

```bash
nexus init
```

The wizard scans your environment (read-only), tells you what is missing in
fixed choices rather than open questions, provisions PostgreSQL if you don't
have it (or creates a dedicated least-privilege database in the one you do),
detects the AI agents installed on your machine, and writes your config to
`~/.nexus/`. Re-running it later is safe — doctor mode only reports drift.

## Morning, continued: your vault wakes up

The wizard also lays down the constraint layer in your vault: `AGENTS.md`,
a one-page `quickref.md`, the task-spec contract, the three wire protocols,
and three gate scenarios (init / dispatch / persist). Your agents read these
from now on — the rules are Markdown, not magic.

Your session starts with a ritual your agent now follows from quickref:
register presence, check who else is online, and health-check the services:

```bash
curl -s -X POST http://127.0.0.1:19998/session/register \
  -d '{"agent":"my-agent","role":"executor","session_id":"my-agent-day1","status":"init"}'
curl -s http://127.0.0.1:19998/session/active
```

## Late morning: connect your agent

The wizard printed an MCP snippet for each agent it detected. You paste the
one for your tool (Claude Code, Codex, ZCode, Kimi, or Cursor — each has a
step-by-step guide in `docs/agents/`), restart that agent's session, and ask
it to search the knowledge base:

```
> use nexus to search for "dispatch timeout"
```

It works anonymously for read-only search — your first contact with the shared
memory of the fleet. Every experience written back by any agent is now
searchable by all of yours.

## Midday: your first dispatched task

You (or an orchestrator agent) write a task spec using the template from
`starter-vault` — seven sections: objective, verifiable criteria, a do-not
list, rejected alternatives, and a trap map. Then it goes over the bus:

```bash
curl -s -X POST http://127.0.0.1:19998/dispatch \
  -H "Content-Type: application/json" \
  -d '{"to":"my-agent","task_path":"/path/to/task.md","timeout":3600}'
```

The executor acknowledges with `started` right away, searches MEM with its
credential before acting, and reports `progress` at milestones. You never
watch a blank screen — `task_state` on the bus is the single source of truth:

```bash
curl -s "http://127.0.0.1:19998/task_state?limit=5"
```

## Afternoon: work, guarded

While your agents work, the gates keep them honest. When one tries to close a
task without artifacts, the persist gate bounces it back. When two agents
reach for the same file, the op-log intercepts the second declaration inside
its 30-second window. You stay the highest arbiter — the machines just make
collisions visible.

When the task finishes, five layers of artifacts land in your vault: the
spec, the full log, a report with evidence, the data files, and a
negative-results page naming what was not done and why. The executor writes
the valuable lessons back to MEM, where the honesty loop starts tracking
whether they actually help next time.

## Evening: the log

You close the day with a five-section session log (template included):
overview, process, artifacts, lessons, open items. Open questions go into the
decision log so tomorrow starts from facts, not from memory.

That is the day. Same agents you already had, same Markdown vault — but now
tasks are assigned with a ledger, knowledge compounds instead of evaporating,
rules are enforced by machines, and every finished task leaves behind
everything needed to never repeat it.

## Where to go next

- `quickref.md` — the three gated moments on one page
- `protocols.md` — dispatch / persist / presence in detail
- `docs/agents/` — step-by-step onboarding for your specific agent
- `README.md` — the full feature tour
