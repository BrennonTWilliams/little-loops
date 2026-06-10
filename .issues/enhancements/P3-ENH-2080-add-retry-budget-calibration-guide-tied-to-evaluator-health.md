---
id: ENH-2080
title: Add retry-budget calibration guide tied to evaluator health
type: ENH
priority: P3
status: open
captured_at: "2026-06-10T18:12:09Z"
discovered_date: "2026-06-10"
discovered_by: capture-issue
parent: EPIC-2087
depends_on: ENH-2084
---

# ENH-2080: Add retry-budget calibration guide tied to evaluator health

## Summary

Adds a `ll-loop calibrate-budget <loop>` subcommand that reports per-evaluator Bernoulli variance and warns authors when variance falls below 0.05, preventing wasted retry budget against toothless evaluators. Surfaces the variance score in `ll-loop run --baseline` output and documents the threshold in CLAUDE.md with a worked example linking evaluator health to retry budget ROI.

## Motivation

Loop `max_iterations` values are currently set by convention. Additional iterations amplify a sound strategy but produce near-zero returns when the underlying evaluator is unhealthy. Spending retry budget against a toothless evaluator wastes tokens without changing outcomes, which is directly indicated by the existing Bernoulli variance check in CLAUDE.md.

## Current Behavior

`max_iterations` is set by convention with no tooling feedback about evaluator health. Running `ll-loop run --baseline` produces a diff table but does not include per-evaluator variance scores. CLAUDE.md mentions the Bernoulli variance threshold (< 0.05) in the Loop Authoring section but does not link it to retry budget ROI or provide a worked example.

## Expected Behavior

- `ll-loop calibrate-budget <loop>` runs the loop's evaluator in isolation across sampled past run states and reports Bernoulli variance `p*(1-p)` per evaluator state.
- Variance < 0.05 triggers an actionable warning recommending evaluator repair before increasing `max_iterations`.
- `ll-loop run --baseline` diff table includes a variance score column.
- CLAUDE.md Loop Authoring section documents the 0.05 threshold with a concrete worked example.

## Proposed Solution

Add a `ll-loop calibrate-budget <loop>` subcommand that:
1. Runs the loop's evaluator in isolation across a sample of past run states
2. Reports the Bernoulli variance `p*(1-p)`
3. If variance is below 0.05, emits a warning that increasing `max_iterations` is unlikely to help and recommends fixing the evaluator first

Document the threshold in the Loop Authoring section of CLAUDE.md with a concrete example linking evaluator health to retry budget ROI. Surface the variance score in `ll-loop run --baseline` output.

## API/Interface

```bash
# New subcommand
ll-loop calibrate-budget <loop>

# Example output
Loop: rn-refine
Evaluator: check_quality (llm_structured)
  Variance p*(1-p): 0.02   ⚠ WARN: below 0.05 threshold — fix evaluator before increasing max_iterations
Evaluator: check_exit (exit_code)
  Variance p*(1-p): 0.23   ✓ OK
```

## Implementation Steps

1. Add `calibrate-budget` subcommand to `ll-loop` CLI
2. Implement evaluator isolation runner against sampled past run states from history DB
3. Compute and report Bernoulli variance per evaluator state
4. Emit actionable warning when variance < 0.05
5. Surface variance score in `ll-loop run --baseline` diff table
6. Document threshold and ROI linkage in `CLAUDE.md` Loop Authoring section with example

## Scope Boundaries

- Does **not** automate evaluator repair or suggest specific fixes beyond "fix the evaluator"
- Does **not** change the 0.05 variance threshold (fixed per SHOR Table 1 / CLAUDE.md)
- Does **not** modify existing `ll-loop run` behavior beyond adding the variance column to `--baseline` output
- Does **not** introduce per-loop thresholds; the 0.05 threshold is universal

## Acceptance Criteria

- [ ] `ll-loop calibrate-budget <loop>` runs and reports per-evaluator Bernoulli variance
- [ ] Variance < 0.05 triggers a warning recommending evaluator repair before increasing iterations
- [ ] `ll-loop run --baseline` output includes variance score
- [ ] CLAUDE.md Loop Authoring section documents the threshold with a worked example

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop_cli.py` — add `calibrate-budget` subcommand
- `scripts/little_loops/fsm/executor.py` — expose evaluator isolation API used by calibrate-budget
- `.claude/CLAUDE.md` — Loop Authoring section: document threshold + worked example

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store.py` — read past run states from history DB for sampling

### Similar Patterns
- `ll-loop run --baseline` in `scripts/little_loops/cli/loop_cli.py` — variance column should follow existing diff table format
- `ll-loop diagnose-evaluators` — already implements Bernoulli variance check; `calibrate-budget` should reuse or call this logic

### Tests
- `scripts/tests/test_builtin_loops.py` — add tests for `calibrate-budget` subcommand
- New test: verify variance calculation against known evaluator history fixtures
- New test: verify warning emitted when variance < 0.05

### Documentation
- `.claude/CLAUDE.md` (Loop Authoring section) — add threshold documentation with worked example

### Configuration
- N/A

## Impact

- **Priority**: P3 — Improves developer experience for loop authors; not blocking but addresses a real pain point (wasted tokens against toothless evaluators)
- **Effort**: Medium — New CLI subcommand requires evaluator isolation runner and history DB integration; `diagnose-evaluators` pattern can be reused
- **Risk**: Low — Additive feature; no changes to existing evaluator behavior or loop execution paths
- **Breaking Change**: No

## Labels

`cli`, `loops`, `dx`, `documentation`

## Status

**Open** | Created: 2026-06-10 | Priority: P3


## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-10T23:30:28 - `59a16773-20bc-402b-b0cb-97d45d141b4c.jsonl`
- `/ll:format-issue` - 2026-06-10T23:22:11 - `c93434ab-0ed3-45d3-9d83-508ca4bc0147.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers the `calibrate-budget` subcommand and the variance score column in `ll-loop run --baseline`. Related issue ENH-2084 adds Wilson CI bounds to the same baseline diff table and the same `ll-loop diagnose-evaluators` surface. Both issues compute statistics over past evaluator run states from the history DB using the same inputs (p, n). To avoid duplicate sampling/computation code, variance `p*(1-p)` and Wilson CI should be implemented in a shared `scripts/little_loops/stats.py` module rather than independently. This issue should land after ENH-2084 so the variance column can be placed adjacent to ENH-2084's Wilson CI column in a coordinated table format.
