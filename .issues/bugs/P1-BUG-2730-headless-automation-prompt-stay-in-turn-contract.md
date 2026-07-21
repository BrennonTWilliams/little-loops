---
id: BUG-2730
title: headless automation prompt path carries no "stay in turn" contract, and
  parallel-agent skills invite the end-turn-and-wait pattern that triggers exit 143
type: BUG
status: open
priority: P1
captured_at: '2026-07-21T22:40:00Z'
discovered_date: '2026-07-21'
discovered_by: issue-size-review
parent: BUG-2729
labels:
- subprocess
- automation
- headless
- prompt-contract
relates_to:
- BUG-2729
- ENH-2714
---

# BUG-2730: headless automation prompt path carries no "stay in turn" contract, and parallel-agent skills invite the end-turn-and-wait pattern

## Summary

FSM `slash_command` actions run skills via headless `claude -p` (stream-json). In
interactive Claude Code, a model may spawn subagents, end its turn, and be
re-invoked by a `<task-notification>` when they finish. In headless mode that
contract does not exist: ending the turn ends the *session*, and `claude -p`
tears down and reaps still-running subagent children (SIGTERM to the process
group, exit 143) — silently discarding in-flight subagent work.

This is the **Primary fix** half of [[BUG-2729]] (decomposed 2026-07-21): prevent
the model from choosing the end-turn-and-wait pattern in headless runs at all,
by (a) injecting a "stay in turn" instruction into the automation prompt path
and (b) removing the wait-for-notification phrasing that currently invites the
unsafe pattern from the parallel-agent skills.

## Parent Issue

Decomposed from [[BUG-2729]]: headless session end-turn-while-awaiting-subagents
self-terminates with exit 143, discarding in-flight work. The parent's Secondary
fix (FSM-side retry classification of exit-143-after-result) is tracked
separately as a sibling BUG created in the same decomposition — see
`## Session Log` cross-reference in BUG-2729 for the sibling ID.

## Codebase Research Findings

_Carried over from [[BUG-2729]]'s `/ll:refine-issue` pass:_

- No automation prompt-prefix builder exists to inject a "stay in turn"
  instruction into. `scripts/little_loops/skill_expander.py` has no
  automation-prefix-building logic at all (only `$ARGUMENTS`/config
  substitution in `expand_skill()`, line ~99) — this is net-new code, not an
  edit to an existing builder.
- `scripts/little_loops/hooks/session_start.py:91-112` is the only existing
  consumer of `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` ([[ENH-2714]]'s carrier).
  It currently only **suppresses** the config-JSON/`project_context` digest
  under automation (`return LLHookResult(exit_code=0, ...)` at line ~112) — a
  subtraction mechanism, not an injection one. This is the nearest existing
  hook point to branch a new "stay in turn" instruction from, but there is no
  precedent in this codebase for *adding* prompt text via this path.
- Treat the `automation_profile` / `LL_AUTOMATION_PROFILE` env-var signal
  (already reaching the child process via `host_runner.py`) as the input
  signal to branch injection on.

### Wait-for-Notification Phrasing to Audit

All four parallel-agent skills contain the same recurring phrase immediately
after their spawn instruction — this is the exact wording that invites the
unsafe end-turn-and-wait pattern:

- `commands/refine-issue.md:123-190` — "Spawn all 3 agents in a SINGLE
  message..." / "**Wait for ALL agents to complete before proceeding.**"
- `skills/wire-issue/SKILL.md:136-241` — same "Spawn all 3 agents..." /
  "**Wait for ALL 3 agents to complete before proceeding.**"
- `skills/decide-issue/SKILL.md:315-322` — "Spawn one
  `ll:codebase-pattern-finder` Agent per option... Use `run_in_background:
  false` and wait for all to complete before proceeding." / "**Wait for ALL
  agents to complete before proceeding to Phase 5.**"
- `skills/manage-issue/SKILL.md:110` — "**CRITICAL**: Wait for ALL sub-agent
  tasks to complete before proceeding to planning."

## Proposed Fix

Inject an instruction into the automation prompt path (the natural carrier is
[[ENH-2714]]'s `automation_profile`, branched via
`hooks/session_start.py`'s existing `LL_AUTOMATION` gate — the injection side
of that gate is new code) stating: *"You are running headlessly. Ending your
turn ends the session. Never end your turn while spawned agents/tasks are
still running — wait for them synchronously within the turn."*

Reword the four wait-for-notification phrasings above so they read as an
in-turn synchronous wait (e.g. "Spawn all N agents and wait for their results
in this same turn before proceeding") rather than language that reads as
"end your turn and resume on notification."

## Acceptance Criteria

- [ ] Headless automation prompt prefix carries the stay-in-turn contract
- [ ] Parallel-agent skills (`refine-issue`, `wire-issue`, `decide-issue`,
      `manage-issue`) contain no end-turn-and-wait phrasing for automation mode

## Session Log
- `/ll:verify-issues` - 2026-07-21T23:08:29 - `9fc8185c-278a-4573-8071-af3d44765f41.jsonl`
- `/ll:issue-size-review` - 2026-07-21T23:15:00Z - `5d306492-7288-421c-83db-83a5420b5516.jsonl`
