---
id: ENH-3125
type: ENH
title: Gate learning-test staleness on installed-version drift, not calendar age
priority: P3
status: open
discovered_date: 2026-08-08
discovered_by: ENH-3073
labels:
- learning-tests
- release
- gates
testable: true
decision_needed: false
relates_to:
- ENH-3073
- FEAT-1813
- ENH-2214
confidence_score: 40
outcome_confidence: 40
score_complexity: 60
score_test_coverage: 40
score_ambiguity: 45
score_change_surface: 55
---

# ENH-3125: Gate learning-test staleness on installed-version drift, not calendar age

## Summary

`is_record_stale()` (`scripts/little_loops/learning_tests/gate.py:45-63`) compares
`record.date` against `stale_after_days` (default 30) — a purely temporal check with no
reference to whether the target's API actually changed. ENH-3073 (Option A) fixed the
*symptom* — the release gate's output now names a remediation command for every row — but
the underlying proxy is still weak: a record proven against a dependency whose installed
version has not changed becomes a warning purely by the passage of time, and the same
seven-ish records will cross the 30-day threshold again ~30 days after ENH-3073 re-proves
them.

This is Option B from ENH-3073's Proposed Solution, filed as its own issue per that
issue's "Follow-up for Option B" section and Acceptance Criteria.

## Motivation

Age is a proxy for "the API may have moved." The proxy is weak when the dependency's
installed version has not changed — which is directly observable and currently not
consulted at all.

## Proposed Solution

Record the resolved package version in the learning-test record at prove time; treat a
record as stale when the installed version differs from the proven one, falling back to
age-based staleness when no version was captured (existing records, or targets without a
resolvable installed version).

**Start from `loops/migrate-sdk-version.yaml`'s existing version resolver**, not from
scratch — ENH-3073's research found this loop (FEAT-1813, `done`) already resolves
installed versions for arbitrary third-party targets and classifies the result as
`still-valid` / `needs-upgrade` / `refuted`. `_warn_adapter_staleness` is a related but
narrower precedent, hardcoded to little-loops' own version — it is not directly reusable
for arbitrary third-party dependencies.

### Known costs (from ENH-3073's decision scoring, Option B: 4/12)

- `is_record_stale(record, stale_after_days)`'s signature likely widens to take an
  installed-version input, which ripples through its production call sites:
  `fsm/executor.py:1113,1161`, `hooks/learning_tests_gate.py:28,129`,
  `hooks/install_learning_gate.py:31,122`, `cli/ctx_stats.py:31`,
  `cli/history_context.py`, plus a dedicated test class in
  `scripts/tests/test_learning_tests_discoverability.py` (`TestIsRecordStale`).
- A new schema field on `LearnTestRecord` (the proven-against version) and a migration
  path for existing `.ll/learning-tests/*.md` frontmatter that predates the field.
- `scripts/little_loops/config-schema.json` additions for any new config knobs, plus
  `docs/reference/CONFIGURATION.md:893-905` and `docs/ARCHITECTURE.md:690` updates
  (both identified as Option-B-only in ENH-3073's wiring pass).
- `test_config.py` (`TestLearningTestsConfig`) and `test_install_learning_gate.py` need
  updates for the new field/behavior.

## Scope Boundaries

**Out of scope**: anything already shipped by ENH-3073 (per-row remediation text,
`cmd_prove` hardening) — this issue is additive on top of that, not a replacement.

## Related Issues

- ENH-3073 — made re-proving reachable (Option A); this issue is its deferred Option B
- FEAT-1813 — `migrate-sdk-version` loop; source of the version resolver this issue
  should build on
- ENH-2214 — introduced the release gate and `stale_after_days`

## Status

Open. Filed per ENH-3073's Acceptance Criteria requiring a follow-up ENH for Option B
before that issue closes. Not yet researched in depth — confidence/outcome scores are
placeholders pending `/ll:refine-issue`.
