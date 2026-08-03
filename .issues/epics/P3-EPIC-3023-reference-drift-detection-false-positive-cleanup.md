---
id: EPIC-3023
title: Reference-drift detection false-positive cleanup
type: EPIC
priority: P3
status: open
discovered_by: capture-issue
discovered_date: 2026-08-02
testable: true
labels:
- epic
- issues
- text-utils
---

# EPIC-3023: Reference-drift detection false-positive cleanup

## Summary

`stale_file_ref` detection (`build_ref_index`/`classify_file_ref` in
`scripts/little_loops/text_utils.py`) and the `research-triage` coverage
predicate it feeds both over-report drift for structural reasons unrelated to
actual staleness. Three narrow fixes already landed and closed
(**ENH-2971**, **ENH-2983**, **ENH-2999**, all `done`); two related gaps
remain open: **ENH-3000** (315 false positives from references into
intentionally-untracked directories like `thoughts/`, `postmortems/`,
`.loops/`) and **ENH-2990** (the live/production skip rate of ENH-2971's
staleness-check predicate is unmeasured, unknown within a 4x band). Both
trace back to the same `stale`-classification machinery and were already
cross-linked via `relates_to` before either had a home.

## Motivation

A check that's right most of the time but noisy in a predictable, ignorable
way is worse than one with a narrower, trusted scope — every unexplained
`stale_file_ref` false positive trains the reader to skim past real drift.
ENH-3000 is the single largest remaining false-positive class (~9% of all
findings); ENH-2990 exists because the mechanism ENH-2971 shipped to reduce
false positives has never been measured against the case it was built for
(live re-refine), only against a corpus proxy that the issue's own author
flagged as a poor stand-in.

## Children

- **ENH-3000** (P3, `decision_needed`) — untracked-by-design directory refs
  always report `stale`; needs an Option A (filesystem-existence fallback) vs.
  Option B (config-driven prefix allowlist) decision via `/ll:decide-issue`
  before implementation.
- **ENH-2990** (P3) — measure the live/production skip rate of ENH-2971's
  Staleness Check predicate (currently unknown within a 4x band: 8.6%–33.7%
  depending on measurement method), to decide whether the check needs
  narrowing.

No dependency edge between them — ENH-3000 narrows what counts as `stale` in
the first place; ENH-2990 measures how often the existing predicate skips
re-refine work. Resolving ENH-3000 will shift ENH-2990's baseline numbers, so
sequencing ENH-3000 first is preferable but not required.

## Integration Map

### Files to Modify
- `scripts/little_loops/text_utils.py` — `build_ref_index`/`classify_file_ref`
  (ENH-3000)
- `scripts/little_loops/config-schema.json` — if ENH-3000 resolves to the
  config-driven Option B
- `scripts/little_loops/cli/issues/research_triage.py`,
  `scripts/little_loops/issues/research_triage.py` — instrumentation point and
  `AxisCoverage` reason-code field (ENH-2990)
- `.ll/history.db` — candidate sink for ENH-2990's live measurement

### Tests
- `scripts/tests/test_text_utils.py`, `scripts/tests/test_ll_issues_format_check.py`
  (ENH-3000)
- `scripts/tests/test_research_triage.py` (ENH-2990)

## Goal

`stale_file_ref`/research-triage coverage findings are trustworthy — every
reported `stale` reflects genuine drift, not a structural blind spot — and the
Staleness Check's real-world cost/benefit is known rather than estimated
within a 4x range.

## Scope

In scope: the two children above. Out of scope: `ENH-2999`'s
absent-vs-ambiguous distinction (already resolved/done), changing
`COVERAGE_THRESHOLD` or the Staleness Check's granularity (an ENH-2990
follow-up, not this epic), and any embeddings/semantic-similarity approach to
reference resolution.

## Impact

- **Priority**: P3 — data-quality/signal-trust issue in an internal tool, not
  user-facing breakage; both children are Small-Medium.
- **Effort**: Small-Medium — ENH-3000 is small once the design decision is
  made; ENH-2990 is instrumentation plus a wait (or a bounded replay).
- **Risk**: Low — both are additive/measurement-only; ENH-3000's Option A
  (if chosen over the recommended Option B) is the one path with a real
  working-tree-dependence risk, called out in its own issue.

## Status

**Open** | Created: 2026-08-03 | Priority: P3

## Success Criteria

- [ ] The ENH-3000 design decision is recorded and implemented; corpus
      re-measurement shows the 315 untracked-by-design false positives
      leaving `stale`
- [ ] ENH-2990's live/replayed skip-rate measurement is recorded in ENH-2971's
      Threshold Validation section alongside the existing corpus numbers
- [ ] `python -m pytest scripts/tests/` passes

## Related Key Documentation

- `docs/reference/CLI.md` § `ll-issues research-triage` — the predicate's
  documented contract both children touch.
- `.issues/enhancements/P3-ENH-2971-*.md` § Threshold Validation — the corpus
  measurement ENH-2990 exists to supersede for the live case.
