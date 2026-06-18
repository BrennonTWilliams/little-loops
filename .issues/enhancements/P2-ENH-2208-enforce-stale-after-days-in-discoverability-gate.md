---
id: ENH-2208
title: Enforce `stale_after_days` threshold in discoverability gate
type: enhancement
priority: P2
status: open
parent: EPIC-2207
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-2208: Enforce `stale_after_days` threshold in discoverability gate

## Summary

The `stale_after_days` config key exists in `config-schema.json` and `LearningTestsConfig`, but `learning_tests_gate.py` only checks `record.status == "proven"`. Records whose proof is older than `stale_after_days` silently pass the gate as if they were current. This is the most impactful gap in the shipped discoverability infrastructure.

## Motivation

A "proven" record from 6 months ago may be based on an API that has since changed. The `stale_after_days` field was added precisely for this scenario but never plumbed into the runtime gate check. Without enforcement, the gate gives false confidence on stale proofs.

## Success Metrics

- Stale records trigger gate: records older than `stale_after_days` are treated as missing and trigger `warn` or `block` mode → 100% enforcement
- Fresh records pass silently: records within the threshold produce no gate output
- Session cache correctness: repeated checks for the same package in a session return the cached `proven=False` without re-running date arithmetic
- Edge case safety: `stale_after_days: 0` does not silently pass all records (clamped to 1 or treated as always-stale per schema minimum)

## Scope Boundaries

- **In scope**: Stale-age check in `learning_tests_gate.py`, `_SESSION_CACHE` update for stale packages, `(stale: N days old)` hint message, test coverage for stale/fresh paths in `test_learning_tests_discoverability.py`
- **Out of scope**: Mutating `record.status` on disk (that is `ll-learning-tests mark-stale`'s job), changes to `mark-stale` CLI behavior, schema changes to `config-schema.json` or `LearningTestsConfig`

## Implementation Steps

1. In `learning_tests_gate.py`, after `check_learning_test(pkg)` returns a record, parse `record.date` and compare against `lt_config.stale_after_days`.
2. If `(today - record.date).days > stale_after_days`, treat the record as if it were missing (add to `missing` list). Do not mutate `status` in-place — that is `mark-stale`'s job.
3. Update `_SESSION_CACHE` to cache `(proven=False)` for packages that exceed the threshold so subsequent Write/Edit calls in the same session don't re-compute the date arithmetic.
4. Optionally include `(stale: N days old)` in the `hint` message so the user knows why it triggered.
5. Add/extend tests in `test_learning_tests_discoverability.py` for the stale-age path.

## Acceptance Signals

- A record with `date` older than `stale_after_days` triggers the gate at `warn` or `block` mode
- A record within the threshold passes silently
- Session cache correctly short-circuits repeated checks for the same package
- `stale_after_days: 0` is not a footgun (treat as "always stale" or clamp to 1 per schema minimum)

## Integration Map

### Files to Modify
- `scripts/little_loops/learning_tests_gate.py` — add stale-age check after `check_learning_test()` returns; update `_SESSION_CACHE` for stale packages
- `scripts/tests/test_learning_tests_discoverability.py` — extend with stale-age and fresh-record test cases

### Dependent Files (Callers/Importers)
- TBD - `grep -r "check_learning_test\|learning_tests_gate" scripts/`

### Similar Patterns
- TBD - `grep -r "stale_after_days\|LearningTestsConfig" scripts/`

### Tests
- `scripts/tests/test_learning_tests_discoverability.py` — add/extend stale path coverage

### Documentation
- N/A — internal gate logic, no public API changes

### Configuration
- `config-schema.json` — `stale_after_days` field already defined; no schema changes needed

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue must expose a standalone `is_record_stale(record: LearnTestRecord, stale_after_days: int) -> bool` helper at module level in `learning_tests_gate.py` (or `scripts/little_loops/learning_tests/gate.py`). Without an importable helper, consumers — ENH-2209, ENH-2210, ENH-2212, ENH-2214, ENH-2217, ENH-2218, ENH-2221 — cannot apply stale-age logic without coupling to the hook-event-coupled `gate()` function or duplicating date arithmetic inline. This helper must be exported as part of this issue's implementation, not deferred to downstream consumers. See [[ENH-2210]] for the shared gate utility that wraps it.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-18T20:50:17 - `2a1b4900-886d-46f7-9096-478aa4b8e4b3.jsonl`
- `/ll:confidence-check` - 2026-06-18T21:50:00 - `815571e6-48ba-47cc-b0be-7e908258e567.jsonl`
- `/ll:format-issue` - 2026-06-18T18:16:43 - `2d07eba4-823a-4df3-b497-a1051dabda4c.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`
