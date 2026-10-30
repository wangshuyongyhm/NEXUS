# <task id> — Report

## TL;DR

<Three lines: what changed, the evidence, the verdict.>

## Analysis

<Numbered steps actually taken, each with the command or observation that drove it.>

## Key findings

- **F1** — <finding> (evidence: <file:line / command output>)
- **F2** — <finding> (evidence: <...>)

## Pitfalls hit

1. <what went wrong> — <root cause> — <the fix that actually worked>

## Reproduce

`bash reproduce.sh`

```yaml
status: done | failed | partial
evidence:
  - <command + what it printed, or file path + checksum>
next_steps:
  - <what the next task should do>
```
