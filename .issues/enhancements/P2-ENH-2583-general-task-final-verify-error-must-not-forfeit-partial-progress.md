---
id: ENH-2583
title: general-task — final_verify error/timeout must not forfeit partial progress
type: ENH
priority: P2
status: done
completed_at: 2026-07-10T05:29:21Z
discovered_date: "2026-07-10"
discovered_by: audit-loop-run
labels: [loops, fsm, general-task, partial-credit, audit]
relates_to:
- ENH-2584
---

# ENH-2583: general-task — final_verify error/timeout must not forfeit partial progress

## Summary

Audit `general-task-audit-2026-07-09T232714.md` (run `2026-07-09T232714`,
verdict `partial`): after ~5h and 206 iterations with **26/38 hard DoD criteria
verified**, 61 `src/` files rewritten, and build + unit suite green, a single
`final_verify` timeout (`exit_code: 124` at the state's 1800s budget) routed
`on_error → diagnose → failed`, discarding all partial credit. The `failed`
path also wrote no `summary.json`, so downstream tooling saw nothing but the
terminal name.

## Changes (implemented)

`scripts/little_loops/loops/general-task.yaml`:

- `final_verify.on_error: diagnose` → `summarize_partial`.
- `summarize_partial` prompt generalized — it previously asserted "reached its
  iteration limit", which is wrong for arrivals from a verify failure; it now
  covers both arrival paths (`on_max_steps` cap and `final_verify.on_error`)
  and chains `next: write_partial_summary`.
- New `write_partial_summary` shell state: mechanically counts checked /
  unchecked hard / soft criteria from `dod.md` (same awk section-scoping as
  `count_done`) and writes `summary.json` with
  `{"verdict":"partial","checked":N,"total":M,"hard_unchecked":H,"soft_unchecked":S}`.
- New distinct `partial` terminal. Deliberately NOT `done` — sub-loop routing
  treats a child ending at `done` as success (`on_yes`), so reusing `done`
  would launder a verify timeout into success for any parent loop — and NOT
  `failed`, which discards verified progress.

Note: on the `on_max_steps` path the executor terminates immediately after the
summary handler state runs (`terminated_by: max_steps`), so only
`summarize_partial` executes there — unchanged from prior behavior. The full
chain (`summarize_partial → write_partial_summary → partial`) runs on the
`final_verify.on_error` path.

## Acceptance Criteria

- [x] `final_verify.on_error` routes to `summarize_partial`.
- [x] `summarize_partial` no longer claims the iteration limit was reached and
      chains to `write_partial_summary`.
- [x] `write_partial_summary` writes `summary.json` with `verdict:"partial"`
      and correct counts (shell-execution tests, including missing-dod.md case).
- [x] Distinct `partial` terminal exists (`terminal: true`), reached via the
      chain; the chain never ends at `done`.
- [x] `scripts/tests/test_general_task_loop.py` updated
      (`test_final_verify_routes_error_to_summarize_partial`,
      `test_summarize_partial_routes_to_write_partial_summary`, new
      `TestENH2575PartialCredit` class — 153 tests pass, incl. FSM validation).

## Notes

Genuine unrecoverable action failures elsewhere in the loop still route
`diagnose → failed`. The root cause of the audited run — a verification
surface too large for one 1800s prompt — is tracked separately as ENH-2584;
this change only stops the resulting timeout from destroying partial credit.
Rec 4 from the same audit (cap `do_work` timeout self-retries) was found to be
already implemented (`max_retries: 2`, `retryable_exit_codes: [124]`,
`on_retry_exhausted → capture_work_exit`); no issue filed.
