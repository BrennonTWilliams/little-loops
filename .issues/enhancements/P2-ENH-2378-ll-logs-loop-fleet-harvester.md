---
id: ENH-2378
type: ENH
title: '`ll-logs loop-fleet` — aggregate cross-project loop-run outcomes for built-in loop improvement'
priority: P2
status: open
captured_at: '2026-06-28T20:52:00Z'
discovered_date: 2026-06-28
discovered_by: user-report
labels:
- cli
- ll-logs
- ll-loop
- meta-loop
- observability
relates_to:
- BUG-2377
- FEAT-2379
decision_needed: false
confidence_score: 80
---

# ENH-2378: `ll-logs loop-fleet` — aggregate cross-project loop-run outcomes

## Problem

This repo ships 77 built-in loops (`scripts/little_loops/loops/*.yaml`). They are *run* in
other projects on this machine (`forescout-harness-training`, `auto-sdlc-framework`,
`MC-vault`, `sketch-storyboards`, …). Each run leaves two traces:

1. **Session JSONL** in `~/.claude/projects/` — visible cross-project via `ll-logs`.
2. **`.loops/runs/<loop>-<ts>/events.jsonl`** — the authoritative FSM run record (terminal
   state, iteration count, which state failed). **This is project-local and aggregated
   nowhere.**

`ll-logs scan-failures` only mines the *session* layer (failed `ll-loop` invocations), so it
catches "the CLI errored" but not "the loop ran to completion in a degraded way" — oscillation,
premature termination, max-iterations exhaustion, a state that always routes the same way.
There is no cross-fleet view of *how the built-in loops actually behave when used elsewhere*,
which is the richest signal for improving them.

## Proposal

Add a `loop-fleet` subcommand to `ll-logs` that closes the aggregation gap:

```
ll-logs loop-fleet [--window-days D] [--loop NAME] [--existing-only] [-j]
```

Behavior:

1. Enumerate projects via the existing `discover` machinery (depends on BUG-2377's
   `--existing-only` so we skip dead worktrees).
2. For each project, glob `.loops/runs/*/events.jsonl` (and `.loops/.history/*/` archived
   runs) within the window.
3. Parse each run's terminal event: loop name, final FSM state, iteration count, outcome
   (converged / max-steps / error / stalled), and the last evaluator verdict.
4. **Attribute** each run to a loop name and mark whether that name corresponds to a
   *built-in* loop shipped from this repo (intersect with `scripts/little_loops/loops/`),
   since only built-ins are in-scope for fixing here.
5. Emit a per-loop table: runs, success rate, median iterations, most common failure state,
   and the projects where it ran. `-j` for machine consumption (FEAT-2379's runbook).

## Why this is the right layer

- Reuses `discover` for project enumeration and the FSM event schema already written by the
  runner; no new persistence.
- Output is the input to the diagnose step (`ll-loop validate` / `diagnose-evaluators` /
  `loop-specialist`) and the baseline for re-measurement after a fix ships.
- Built-in-only attribution keeps fixes scoped to this repo (per the project decision: other
  projects' own loops are fixed in place, not back-ported here).

## Open questions

- Event schema stability: confirm the terminal-state field names in `events.jsonl` across
  runner versions; older archived runs may need a compat shim.
- Whether to read live `.loops/runs/` only, or also `.loops/.history/` archives (latter gives
  trend depth but may include pre-fix runs that muddy the baseline — likely gate behind a flag).
- Loop-name → built-in attribution when a project has `ll-loop install`-ed and *customized* a
  built-in (the local copy diverges); flag these as "forked" rather than attributing failures
  to the shipped version.

## Acceptance criteria

- `ll-logs loop-fleet -j` returns parseable JSON: one record per (loop, project) with terminal
  outcome, iterations, and failure state.
- Built-in vs. project-local vs. forked loops are distinguished in the output.
- Honors `--window-days`, `--loop`, `--existing-only`.
- Documented in `docs/reference/API.md` and the FEAT-2379 runbook.

## Dependencies

- **BUG-2377** (stdout pollution + `--existing-only`) must land first, or the harvester
  inherits unparseable input.
