---
id: FEAT-3077
title: Decide and document the smoke-test/go-no-go carve-out policy for CLAUDE_CODE_DISABLE_BACKGROUND_TASKS
type: FEAT
priority: P3
status: open
testable: true
parent: FEAT-3060
depends_on:
- FEAT-3076
labels:
- automation
- headless
- host-runner
---

# FEAT-3077: Decide and document the smoke-test/go-no-go carve-out policy for CLAUDE_CODE_DISABLE_BACKGROUND_TASKS

## Summary

Two skills currently rely on legitimate backgrounding that a blanket
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` would break:

- `skills/manage-issue/SKILL.md:394-396` explicitly permits backgrounding
  long-running processes (servers) for smoke tests: "start in background,
  wait briefly for startup, then terminate."
- `skills/go-no-go/SKILL.md:174,274,278` launches two agents concurrently with
  `run_in_background: true`, then waits for both before a foreground judge
  step.

Decide whether these carve-outs are retired (accepting the loss of legitimate
backgrounding in automation contexts) or whether the new config flag defaults
off (preserving current behavior until explicitly opted into), and update the
affected skill docs to match the decision.

## Parent Issue

Decomposed from FEAT-3060: Hard-disable background tasks in headless
automation instead of instructing against them. Resolves that issue's
Acceptance Criterion 3.

## Dependency

Depends on FEAT-3076's finding on whether
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` blocks only `Bash run_in_background`
or also subagent-tool backgrounding — that answer determines whether the
`go-no-go` carve-out (which backgrounds subagents, not `Bash`) is even at risk
under a Bash-only reading, which materially changes this decision.

## Proposed Solution

1. Using FEAT-3076's finding, determine for each carve-out whether it would
   actually break under the flag (a Bash-only scope may leave the
   `go-no-go` subagent-launch carve-out unaffected while still breaking
   `manage-issue`'s smoke-test carve-out, or vice versa).
2. For each carve-out that would break, decide: retire the carve-out (accept
   the behavior change), or leave the new config flag defaulting off so
   existing behavior is preserved until a project opts in.
3. Record the decision and rationale in this issue.
4. Update `skills/manage-issue/SKILL.md:394-396` and/or
   `skills/go-no-go/SKILL.md:174,274,278` to reflect the decision — either
   noting the carve-out no longer applies under the new flag, or leaving them
   unchanged with a note that they rely on the flag defaulting off.

## Acceptance Criteria

1. Each of the two known carve-outs (`manage-issue` smoke tests, `go-no-go`
   concurrent agent launch) has an explicit decision: retired, or preserved
   via the flag defaulting off.
2. The decision and its rationale are recorded in this issue, in a form
   FEAT-3078 can consume directly to set the config flag's default value.
3. `skills/manage-issue/SKILL.md` and `skills/go-no-go/SKILL.md` are updated
   to match the decision (or explicitly confirmed to need no change).

## Related Key Documentation

| Document | Relevance |
|---|---|
| `skills/manage-issue/SKILL.md:376-400` | The instruction/carve-out this issue decides on |
| `skills/go-no-go/SKILL.md:174,274,278` | The second carve-out this issue decides on |
| `docs/claude-code/settings.md:772` | The flag's documented scope |


## Session Log
- `/ll:issue-size-review` - 2026-08-06T05:11:26 - `c21cd57e-cb03-41ae-b233-cd39e3e2a29a.jsonl`
