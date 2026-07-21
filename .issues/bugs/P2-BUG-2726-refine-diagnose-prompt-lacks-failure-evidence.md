---
id: BUG-2726
title: refine-to-ready-issue diagnose prompt carries no failure evidence, producing
  confabulated wrong-run diagnoses
type: BUG
status: open
priority: P2
captured_at: '2026-07-21T22:10:00Z'
discovered_date: '2026-07-21'
discovered_by: audit-loop-run
labels:
- loops
- fsm
- diagnostics
relates_to:
- ENH-2469
- ENH-2522
---

# BUG-2726: refine-to-ready-issue `diagnose` prompt carries no failure evidence, producing confabulated wrong-run diagnoses

## Summary

The `diagnose` state in `scripts/little_loops/loops/refine-to-ready-issue.yaml` is
reached via `on_error` from states like `refine_issue`, but its prompt interpolates
only the issue ID — not the failing state's exit code, stderr, output tail, or the
current run's `run_dir`/event trail. The diagnosis session must therefore guess
what failed.

## Evidence (run `2026-07-21T214941-autodev`)

- `refine_issue` (`/ll:refine-issue ENH-2722 --auto`) exited **143 (SIGTERM)** after
  155,886 ms — an external kill (the FSM runner's timeout path returns 124, not 143).
- The subsequent `diagnose` output analyzed a *different, earlier* run
  (`.loops/.history/2026-07-21T181435-autodev`), asserted "the wrapping autodev loop
  … never reached a refine/ready-issue state for ENH-2722 at all", and never
  mentioned the SIGTERM — even though in the current run the refine session had been
  actively researching ENH-2722 when killed.
- The diagnose prompt text (from `events.jsonl`): "The refine-to-ready-issue loop
  has terminated with an unrecoverable failure. … Report the issue ID being
  refined: ENH-2722 — Identify which state failed …" — no exit code, no stderr, no
  run ID is passed.

## Proposed Fix

Interpolate concrete failure context into the diagnose prompt:

- failing state name and `${prev_result.exit_code}` / last `action_complete` exit code
- stderr/output tail of the failed action (ENH-2469's `stderr_preview` helps here)
- the current run's `run_dir` and run ID, with an instruction to confine analysis to
  that run's `events.jsonl`

## Acceptance Criteria

- [ ] `diagnose` prompt includes the failing state name, exit code, and stderr/output tail
- [ ] `diagnose` prompt includes the current run ID / `run_dir` and instructs the
      session to analyze only that run
- [ ] A refine kill with exit 143 produces a diagnosis that cites exit 143 (add or
      extend a test/fixture asserting the interpolated prompt content)


## Session Log
- `/ll:verify-issues` - 2026-07-21T23:08:29 - `9fc8185c-278a-4573-8071-af3d44765f41.jsonl`
