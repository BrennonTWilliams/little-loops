---
id: BUG-3196
type: BUG
title: "ll-harness dsl never compares against a task's expected: values \u2014 a flagless\
  \ run reports a 100% pass rate unconditionally"
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T18:44:20Z'
---

# BUG-3196: ll-harness dsl never compares against a task's expected: values — a flagless run reports a 100% pass rate unconditionally

## Summary

`ll-harness dsl` loads each task YAML into `DslTask`, which parses an `expected:` mapping (`scripts/little_loops/cli/harness.py:167,178`), but `cmd_dsl` never reads it. The runner builds `task.prompt`, appends the `blanks` list, and delegates to `cmd_prompt` (`harness.py:689-703`); pass/fail is then decided entirely by `_evaluate_and_report`, which checks only `--exit-code` and `--semantic` (`harness.py:419-433`).

Two consequences:

1. **A DSL set run without `--semantic` reports a 100% pass rate unconditionally.** `passed` initializes to `True` and no requested check can flip it, so every task returns rc 0 and `cmd_dsl` prints `N/N [1.00, 1.00] (95% CI)` regardless of what the model answered. The Wilson interval makes the null result look rigorous.

2. **Even with `--semantic`, grading is uniform across the set.** One criterion string applies to every task, so per-task `expected` values — the whole point of a fill-in-the-blank/correction task — are never checked. `/ll:create-eval-from-issues --dsl` generates `expected:` blocks for tasks it emits, and `skills/create-eval-from-issues/SKILL.md:135-141` documents `expected` as part of the Option B schema, so the generator and the runner disagree about the contract.

Reproduce: generate any DSL task set with `/ll:create-eval-from-issues --dsl`, then run `ll-harness dsl evals/dsl/<name>/` with no other flags — it reports a perfect pass rate without comparing a single answer.

Fix direction: grade each task by comparing the model's response against its own `expected` mapping (per-blank exact or normalized match), and fall back to `--semantic` only when a task declares no `expected`. Until then, `--semantic` should arguably be required for `ll-harness dsl`, since the flagless invocation cannot produce a meaningful number.

Documented as a gotcha in `docs/guides/EVALUATION_GUIDE.md` § Gotchas.


## Current Behavior

`DslTask.expected` is populated from the task YAML and then never referenced again anywhere
in `scripts/little_loops/cli/harness.py`. Each task is run as a bare prompt and graded only
by the flags passed to the `dsl` subcommand, which apply identically to every task in the
set. With no `--semantic` and no `--exit-code`, `_evaluate_and_report` leaves `passed` at its
`True` initializer and the run reports `N/N  [1.00, 1.00] (95% CI)`.

## Expected Behavior

Each task is graded against its own `expected:` mapping — a per-blank comparison of the
model's response to the declared correct values — so the reported pass rate reflects task
correctness. `--semantic` remains available as a fallback for tasks that declare no
`expected`, and as an additional gate. A run that can produce no meaningful verdict should
say so rather than reporting a perfect score.

## Impact

- **Priority**: P2 - Silently produces a confidently-wrong measurement. Any decision made on a DSL pass rate (model comparison via `--model`, regression tracking) is unfounded, and the Wilson CI lends it false credibility. Not P1 only because the DSL runner is a narrow, opt-in surface.
- **Effort**: Small - Compare `task.expected` against the captured response inside `cmd_dsl`'s per-task loop; the response is already in hand from `cmd_prompt`. Requires refactoring `cmd_prompt` to return the captured output alongside its exit code, or calling the runner directly.
- **Risk**: Low - Additive grading path; existing `--semantic` behavior can be preserved for tasks with no `expected`.
- **Breaking Change**: No - though previously-green DSL runs will start reporting real (lower) pass rates, which is the point.

## Status

**Open** | Created: 2026-08-15 | Priority: P2
