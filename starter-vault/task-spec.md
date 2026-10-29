# task-spec.md — the task spec contract (generic template)

> Every task that crosses the dispatch bus is a Markdown file with these seven
> sections. The spec is the contract: the executor executes it, the gate
> validates against it, the auditor reconstructs from it. Placeholders in
> `<angle brackets>`.

## The seven sections

### 1. Header

```markdown
---
task_id: <unique id>
title: <one line>
target_agent: <executor name>
priority: <P0|P1|P2>
---
```

### 2. Source anchors

Why this task exists — links to the decision, the parent task, the user
directive. Two lines maximum; an auditor must reach the origin in one click.

### 2b. References

A `references.md` sits beside the spec carrying the *actual* knowledge-base
hits this task builds on — search first, paste real content, not titles only.
Without it the executor cannot honor "look before you leap".

### 3. Core objective

What must be true when this is done. Written as outcomes, not activities.
Bad: "look into the cache". Good: "cache hit rate >= 90% on the fixture set,
measured by <command>".

### 4. Completion criteria (verifiable)

A checklist where every item can be verified by a command or a file that must
exist. If a criterion cannot be machine-checked, it does not belong here —
put it in the report's discussion section instead.

### 5. Do-NOT list

Explicit forbidden actions: files not to touch, approaches already rejected,
scope boundaries. The executor reads this before the objective — it defines
the blast radius.

### 6. Rejected alternatives

At least two approaches considered and rejected, each with its reason and the
evidence. This section is what stops the next agent from re-walking the dead
ends. Empty here = the thinking was not done.

### 7. Trap map

At least three known pitfalls for this kind of work, each with its countermeasure.
Drawn from the knowledge base (search before writing) and from the
orchestrator's own scars.

## Output registration

Before `done`, the executor completes the artifact registry inside the spec
copy: which report, which files, which reproduce script — with links. The
registry is the index the persist gate validates.

## Machine-readable tail

Every `output/report.md` ends with a YAML block so machines can consume
results without parsing prose:

```yaml
status: done | failed | partial
evidence:
  - <command run + what it printed, or file path + checksum>
next_steps:
  - <what the next task should do>
```

## Amendments

Mid-task changes go through the spec: the orchestrator appends an amendment
section (what changed, why, what is now void) and re-registers on the bus.
Steering messages in chat are conversation; the spec is the contract.
