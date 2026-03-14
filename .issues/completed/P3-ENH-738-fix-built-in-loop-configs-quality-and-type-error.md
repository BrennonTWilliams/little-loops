---
id: ENH-738
type: ENH
priority: P3
status: completed
discovered_date: 2026-03-13
discovered_by: manual
confidence_score: 100
outcome_confidence: 100
---

# ENH-738: Fix two built-in loop configs — quality gate and type-error-fix

## Summary

Two built-in loop files had known quality issues: `fix-quality-and-tests.yaml` bundled auto-fixable and manual-investigative work into a single undifferentiated state, and `type-error-fix.yaml` had a hardcoded project-specific mypy path and a dead `capture` key.

## Problems

### `loops/fix-quality-and-tests.yaml`

The `fix-quality` state handled both auto-fixable work (lint/format via `check-code all`) and manual investigative work (type errors) in a single prompt with no structured analysis pass. When type errors were complex, the LLM received no categorization or prioritization guidance — it was told to "investigate each one." This made the loop less effective on codebases with many type errors.

### `loops/type-error-fix.yaml`

Two issues:

1. `run_mypy` hardcoded `python -m mypy scripts/little_loops/` — a path specific to this project. The loop would fail or produce incorrect results on any other project.
2. `run_mypy` had a dead `capture: mypy_output` key. The output was already captured via `tee /tmp/ll-mypy-results.txt`; nothing downstream referenced `${captured.mypy_output.output}`. The dead key added noise and false expectations.

## Solution

### `loops/fix-quality-and-tests.yaml`

Split the single `fix-quality` state into three focused states:

| State | Type | Responsibility |
|---|---|---|
| `fix-lint-format` | prompt | Run `/ll:check-code fix` to auto-fix lint + format only |
| `analyze-type-errors` | prompt | Run `/ll:check-code types`, categorize errors, capture analysis |
| `fix-type-errors` | prompt | Fix errors using captured analysis, up to 5 per iteration |

`check-quality.on_failure` now routes to `fix-lint-format` (was `fix-quality`).

The analyze-first pattern is borrowed from `type-error-fix.yaml`'s `analyze_errors` → `fix_errors` structure. `analyze-type-errors` exits cleanly when mypy is clean ("No type errors found"), making `fix-type-errors` a safe no-op on lint-only failures — no additional routing complexity required.

### `loops/type-error-fix.yaml`

1. Replaced the hardcoded mypy invocation with the established config-read pattern (identical to `check-tests` in `fix-quality-and-tests.yaml` and `dead-code-cleanup.yaml`), reading `project.type_cmd` from `.claude/ll-config.json`. Uses `or 'python -m mypy .'` (not a dict `.get()` default) to correctly handle both missing key and explicit `null`.
2. Removed dead `capture: mypy_output` from `run_mypy`.

## Files Changed

- `loops/fix-quality-and-tests.yaml` — replaced `fix-quality` state with `fix-lint-format`, `analyze-type-errors`, `fix-type-errors`; updated description; updated `check-quality.on_failure` routing
- `loops/type-error-fix.yaml` — replaced hardcoded mypy path with dynamic config read; removed `capture: mypy_output`
