---
id: ENH-2208
title: Enforce `stale_after_days` threshold in discoverability gate
type: enhancement
priority: P2
status: done
parent: EPIC-2207
captured_at: '2026-06-18T15:38:06Z'
completed_at: '2026-06-18T23:36:45Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
confidence_score: 90
outcome_confidence: 80
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 22
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

- **In scope**: Stale-age check in `learning_tests_gate.py`, `_SESSION_CACHE` update for stale packages, `(stale: N days old)` hint message, test coverage for stale/fresh paths in `test_learning_tests_discoverability.py`, `is_record_stale()` helper at module level in `scripts/little_loops/learning_tests/gate.py`, `--stale-aware` flag on `ll-learning-tests check` CLI (exits 1 if record is absent or date-stale, 0 if proven and within threshold)
- **Out of scope**: Mutating `record.status` on disk (that is `ll-learning-tests mark-stale`'s job), changes to `mark-stale` CLI behavior, schema changes to `config-schema.json` or `LearningTestsConfig`

## Implementation Steps

1. In `learning_tests_gate.py`, after `check_learning_test(pkg)` returns a record, parse `record.date` and compare against `lt_config.stale_after_days`.
2. If `(today - record.date).days > stale_after_days`, treat the record as if it were missing (add to `missing` list). Do not mutate `status` in-place — that is `mark-stale`'s job.
3. Update `_SESSION_CACHE` to cache `(proven=False)` for packages that exceed the threshold so subsequent Write/Edit calls in the same session don't re-compute the date arithmetic.
4. Optionally include `(stale: N days old)` in the `hint` message so the user knows why it triggered.
5. Add/extend tests in `test_learning_tests_discoverability.py` for the stale-age path.
6. Add `--stale-aware` flag to `ll-learning-tests check` CLI: when passed, the command applies `is_record_stale()` logic and exits 1 if the record is absent or date-stale (even if `record.status == "proven"`). This gives ENH-2221 a shell-verifiable eval criterion without requiring a Python wrapper.

## Acceptance Signals

- A record with `date` older than `stale_after_days` triggers the gate at `warn` or `block` mode
- A record within the threshold passes silently
- Session cache correctly short-circuits repeated checks for the same package
- `stale_after_days: 0` is not a footgun (treat as "always stale" or clamp to 1 per schema minimum)

## Integration Map

### Files to Modify
- `scripts/little_loops/hooks/learning_tests_gate.py` — add stale-age check after `check_learning_test()` returns; update `_SESSION_CACHE` for stale packages; import `is_record_stale` from `scripts/little_loops/learning_tests/gate.py`
- `scripts/tests/test_learning_tests_discoverability.py` — extend with stale-age and fresh-record test cases

### Files to Create
- `scripts/little_loops/learning_tests/gate.py` — canonical module for `is_record_stale(record, stale_after_days) -> bool` helper; consumed by ENH-2209, ENH-2210, ENH-2214, ENH-2217

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/pre_tool_use.py` — imports `gate` from `little_loops.hooks.learning_tests_gate`
- `scripts/little_loops/fsm/executor.py` — calls `check_learning_test` directly (not the gate); uses `stale_after_days` from `LearningTestsConfig` context

### Similar Patterns
- `scripts/little_loops/config/features.py:396` — `LearningTestsConfig.stale_after_days` defaulting to 30
- `scripts/little_loops/config/core.py:609` — `stale_after_days` serialized in config to_dict

### Tests
- `scripts/tests/test_learning_tests_discoverability.py` — add/extend stale path coverage

### Documentation
- N/A — internal gate logic, no public API changes

### Configuration
- `config-schema.json` — `stale_after_days` field already defined; no schema changes needed

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue must expose a standalone `is_record_stale(record: LearnTestRecord, stale_after_days: int) -> bool` helper at module level in `learning_tests_gate.py` (or `scripts/little_loops/learning_tests/gate.py`). Without an importable helper, consumers — ENH-2209, ENH-2210, ENH-2212, ENH-2214, ENH-2217, ENH-2218, ENH-2221 — cannot apply stale-age logic without coupling to the hook-event-coupled `gate()` function or duplicating date arithmetic inline. This helper must be exported as part of this issue's implementation, not deferred to downstream consumers. See [[ENH-2210]] for the shared gate utility that wraps it.

**Note** (added by `/ll:audit-issue-conflicts`): The canonical module path for `is_record_stale()` is **`scripts/little_loops/learning_tests/gate.py`** — the "or" hedge in the note above is resolved here. ENH-2208 must create (or move) the helper to `scripts/little_loops/learning_tests/gate.py`. If `hooks/learning_tests_gate.py` already contains the gate logic, it should import `is_record_stale` from the new location rather than defining it twice. ENH-2210 and ENH-2219 both commit unconditionally to this path; if ENH-2208 ships to the wrong location, their imports break. See [[ENH-2210]] and [[ENH-2219]].

## Session Log
- `/ll:ready-issue` - 2026-06-18T23:21:01 - `e4f9f732-f67f-4a9e-95a0-0532c566fd9c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T21:17:06 - `23eb26e5-163c-41e9-bc83-173b75524706.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:50:17 - `2a1b4900-886d-46f7-9096-478aa4b8e4b3.jsonl`
- `/ll:confidence-check` - 2026-06-18T21:50:00 - `815571e6-48ba-47cc-b0be-7e908258e567.jsonl`
- `/ll:format-issue` - 2026-06-18T18:16:43 - `2d07eba4-823a-4df3-b497-a1051dabda4c.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`
- `/ll:confidence-check` - 2026-06-18T00:00:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
