---
id: BUG-2362
title: recursive-refine parse_input crashes on bare shell variable; breaks all callers
type: BUG
status: done
priority: P0
captured_at: '2026-06-28T00:59:47Z'
completed_at: '2026-06-28T00:59:47Z'
discovered_date: '2026-06-27'
discovered_by: audit-loop-run
relates_to:
- ENH-2005
labels:
- loops
- fsm
- interpolation
- recursive-refine
- regression-guard
confidence_score: 96
outcome_confidence: 92
---

# BUG-2362: recursive-refine parse_input crashes on bare shell variable; breaks all callers

## Summary

`recursive-refine.yaml`'s `parse_input` state echoed two **bare** shell
variables — `${COMMIT_EVERY}` and `${NO_RECURSION}` — in the `order=next-action`
branch. The FSM template engine (`little_loops.fsm.interpolation.interpolate`)
runs a whole-body regex pass over every action string and rejects any `${...}`
that is not a valid `namespace.path` (or escaped as `$${...}`). The bare
references therefore crashed the **entire** `parse_input` state at parse time —
regardless of which shell branch would actually execute — with
`Invalid variable: ${COMMIT_EVERY} (expected namespace.path)`.

Because the validation is a text-level pass over the whole action body, the
crash fired on **every** invocation of recursive-refine (both `order=queue` and
`order=next-action`), silently taking down the loop and all three of its
callers. It went undetected for ~2 weeks because `ll-loop validate` reported the
loop "valid" and the full test suite passed — nothing exercised loop action
bodies against the real interpolation engine.

Surfaced by `/ll:audit-loop-run` on a `sprint-refine-and-implement` run
(`EPIC-364`, 2026-06-27): the run reached `done` after refining/implementing
**zero** issues — all 6 in scope were written to the skipped list because the
delegated recursive-refine sub-loop crashed at `parse_input` on every attempt
(verdict: `phantom`).

## Root Cause

`scripts/little_loops/loops/recursive-refine.yaml` (`parse_input`,
`order=next-action` branch) introduced on 2026-06-13 (commit `176fe300`,
"fold issue-refinement deltas into recursive-refine and alias it"):

```yaml
COMMIT_EVERY="${context.commit_every:default=0}"     # qualified — OK
NO_RECURSION="${context.no_recursion:default=false}" # qualified — OK
echo "Starting next-action mode: commit_every=${COMMIT_EVERY}, no_recursion=${NO_RECURSION}"  # BARE — crashes
```

`interpolate()` (`interpolation.py:202-270`) replaces escaped `$${` first, then
substitutes every remaining `${...}`. A reference with no `.` (and not
`messages`) is rejected at `interpolation.py:246-249` **before** value
resolution, so it is a hard crash independent of runtime context or shell
control flow.

## Blast Radius

recursive-refine is the standalone refinement path *and* a sub-loop of three
callers, all of which were fully broken:

- `auto-refine-and-implement.yaml` (via `refine_issue`)
- `sprint-refine-and-implement.yaml` (via `auto-refine-and-implement`)
- `issue-refinement.yaml` (alias used by `eval-driven-development`, passes
  `order=next-action`)

## Fix

Escaped the two bare references to `$${COMMIT_EVERY}` / `$${NO_RECURSION}`,
matching this file's own established convention (lines 136, 141). `$${...}`
becomes a literal `${...}` after the engine's escape pass, which the shell then
expands normally.

```
scripts/little_loops/loops/recursive-refine.yaml:72
```

## Defense-in-Depth (companion improvements from the same audit)

The audit proposed five layered improvements. Implemented #1–#4; intentionally
dropped #5 (success thresholds on the thin alias) as over-engineering.

1. **[fix] recursive-refine.yaml:72** — the proximate P0 (above).

2. **[guard] `scripts/tests/test_builtin_loop_interpolation.py`** (NEW) — runs
   every builtin loop's action/evaluate strings through the real `interpolate()`
   engine so a bare `${VAR}` now fails CI across all loops. Closes the gap that
   let this live 2 weeks: `ll-loop validate` and the suite both passed because
   nothing interpolated action bodies. This is the durable systemic fix.

3. **[state] auto-refine-and-implement.yaml** — `refine_issue` now routes a
   refinement miss (`on_failure`) → `skip_refinement` and an infrastructure
   crash (`on_error`) → `record_error` (distinct `auto-refine-and-implement-errored.txt`),
   so an automation defect is no longer laundered into the same skip bucket as a
   legitimate confidence-gate miss. Added `record_implemented` tracking.

4. **[auditability] auto-refine-and-implement.yaml `finalize`** (NEW) — writes a
   machine-readable `summary.json` with a `success` / `partial` / `phantom` /
   `no-op` verdict plus an ENH-2005 `subloop_outcome_auto-refine-and-implement.txt`
   token, so callers and post-hoc audits can distinguish genuine success from a
   phantom run.

5. **[structural] sprint-refine-and-implement.yaml** — `delegate` no longer
   collapses `on_success`/`on_failure`/`on_error` into a single terminal `done`.
   `on_error` → distinct `record_crash`; success/failure → `read_outcome`, which
   recovers the child's real verdict from the shared-`run_dir` sidecar. Follows
   the documented ENH-2005 exemption so future audits report *mitigated*, not a
   laundering defect. (The child inherits the parent's `run_dir` via
   `executor.py:673-674` `setdefault`, so the sidecar artifacts are reachable
   without explicit threading.)

## Files Changed

- `scripts/little_loops/loops/recursive-refine.yaml` (the P0 fix)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (skip/error split,
  `record_implemented`, `finalize` + `summary.json` + sidecar token)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` (laundering fix)
- `scripts/tests/test_builtin_loop_interpolation.py` (NEW regression guard)
- `scripts/tests/test_builtin_loops.py` (updated structural tests for the new
  state names and added laundering/summary assertions)

## Verification

- New guard test interpolates the (fixed) `parse_input` action without error and
  was confirmed to *catch* the original bare-var form.
- `ll-loop validate` passes for recursive-refine, auto-refine-and-implement, and
  sprint-refine-and-implement.
- `pytest` over the loop suites + `test_fsm_validation` + the new guard:
  1488 passed; `ruff check` clean.

## Notes / Follow-ups

- Two **pre-existing** test failures surfaced during verification but are
  unrelated to this fix (they fail with these changes stashed) and belong to the
  sibling `sprint-build-and-validate` audit:
  `test_builtin_loops.py::TestBuiltinLoopList::test_list_shows_builtin_tag` and
  `TestValidatorWarningBudget::test_deterministic_warning_categories_do_not_regrow`.
  Not addressed here.
- The interpolation guard (#2) only covers builtin loops. A complementary
  `ll-loop validate` rule flagging bare `${UPPERCASE}` references would extend
  protection to user-authored loops (deferred; candidate enhancement).

## Acceptance Criteria

- [x] `recursive-refine` `parse_input` no longer raises `Invalid variable`.
- [x] A regression test fails on any bare `${VAR}` in a builtin loop action.
- [x] `refine_issue` distinguishes refinement failure from sub-loop crash.
- [x] `auto-refine-and-implement` emits `summary.json` with a verdict.
- [x] `sprint-refine-and-implement` no longer collapses all child outcomes into
      `done` (distinct `on_error` route + verdict recovery).


## Session Log
- `hook:posttooluse-status-done` - 2026-06-28T01:00:55 - `f508966a-781d-4f9a-a413-0a1850737aba.jsonl`
