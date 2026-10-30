---
task_id: <unique-id>
title: <one line>
target_agent: <executor name>
priority: <P0|P1|P2>
---

# Task spec: <title>

## Source anchors

- <link to the decision / parent task / user directive>

## Core objective

<What must be true when this is done — written as an outcome, not an activity.>

## Completion criteria (verifiable)

- [ ] <criterion verifiable by a command or a required file>
- [ ] <criterion>

## Do NOT

- <forbidden action / off-limits path / rejected approach>
- <boundary>

## Rejected alternatives

1. ❌ <approach> — <reason + evidence>
2. ❌ <approach> — <reason + evidence>

## Trap map

1. <known pitfall> — <countermeasure>
2. <known pitfall> — <countermeasure>
3. <known pitfall> — <countermeasure>

## Output registration (fill before done)

- report: output/report.md
- files: output/files/
- reproduce: reproduce.sh

## Time budget & callbacks

~<estimate>. started → progress → done.
