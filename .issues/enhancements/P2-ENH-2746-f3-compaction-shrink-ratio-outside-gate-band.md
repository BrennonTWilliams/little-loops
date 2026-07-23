---
id: ENH-2746
type: ENH
title: F3 compaction shrink ratio measured outside 50-70% gate band
priority: P3
status: done
captured_at: '2026-07-23T01:37:52Z'
completed_at: '2026-07-23T04:31:47Z'
discovered_date: '2026-07-23'
discovered_by: capture-issue
parent: EPIC-2456
labels:
- token-cost
- observability
- compaction
relates_to:
- EPIC-2456
- ENH-2719
- FEAT-2598
confidence_score: 94
outcome_confidence: 80
score_complexity: 22
score_test_coverage: 12
score_ambiguity: 22
score_change_surface: 24
---

# ENH-2746: F3 compaction shrink ratio measured outside 50-70% gate band

## Summary

ENH-2719's realized-savings verification pass measured
`evict_sink_and_window()` (FEAT-2598's always-on structural eviction pass,
`sink_n=4`/`window_n=20` defaults) against 3 real on-disk session
transcripts. Shrink ratios were 89.6%, 73.8%, and 61.3% (mean 74.9%) —
2 of 3 exceed EPIC-2456's F3 gate band of 50-70%.

## Current Behavior

- `evict_sink_and_window` alone was measured (structural eviction only); the
  soft-threshold-gated `summarize_6_section` LLM pass was not exercised
  since it requires a live model call and was out of scope for a read-only
  measurement pass.
- The measured range (61.3-89.6%) oversh­oots the 50-70% gate on the two
  longer sessions, suggesting either the gate band was set against the
  combined eviction+summarization behavior (not eviction alone), or the
  default `sink_n`/`window_n` produce more aggressive shrinkage than
  intended on long sessions.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `evict_sink_and_window()` — `scripts/little_loops/compaction/instant.py:34-57`.
  `sink_n`/`window_n` defaults (4/20) are hardcoded call-site defaults;
  `system`-role messages are preserved unconditionally, outside the
  sink/window accounting. If the prunable message count is
  `<= sink_n + window_n`, eviction is a no-op — short sessions pass through
  unchanged.
- `summarize_6_section()` — `compaction/instant.py:113-144`, gated by
  `SOFT_THRESHOLD_TOKENS = 7500` (hardcoded constant,
  `compaction/instant.py:18`) via `_maybe_soft_threshold_summary()`
  (`session_store.py:3576-3648`). This is a **separate** threshold from
  `history.compaction.budget_tokens` (4096, LCM cross-session condensation)
  and `compression.trigger_pct` (0.4, F4 heuristic compressor) — neither
  config value drives F3's own gate.
- Structural eviction always runs first and bounds the summarizer's input
  once the soft threshold is crossed (`session_store.py:3613`) — in
  production the two passes are not independent; summarization only ever
  sees the post-eviction subset.
- `CompactResult` (`compaction/result.py:15-31`) has no
  `original_tokens`/ratio field — there is no production shrink-ratio
  measurement anywhere in the codebase. ENH-2719's numbers came from a
  one-off, uncommitted script (`docs/observability/realized-savings-verification.md:60-65`),
  not a checked-in tool or test assertion.

## Expected Behavior

Either:
1. Measure the combined structural-eviction + 6-section-summarization
   pipeline end-to-end (requires a live model call for the summarization
   step) and compare that ratio to the 50-70% gate, or
2. Reconcile the gate band itself if it was only ever meant to describe
   the always-on structural pass, and the observed 61-90% range is
   actually expected/acceptable.

## Proposed Solution

1. Determine (from `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md`
   or FEAT-2598's own issue) whether the 50-70% gate was scoped to
   structural eviction alone or the combined pipeline.
2. If combined: run a small opt-in measurement invoking
   `summarize_6_section` on the same 3 sessions and recompute the ratio.
3. If structural-only: update EPIC-2456's Success Metrics F3 line to
   reflect the actual measured range, or tune `sink_n`/`window_n` defaults
   if 61-90% is considered too aggressive.
4. Update `docs/observability/realized-savings-verification.md` with the
   resolved measurement.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 answered — the gate was scoped to the combined pipeline, not
structural eviction alone.** FEAT-2598's own issue text uses
"eviction+summarization together" / "combo" language in three places when
defining the 50-70% gate:
- Expected Behavior (`P2-FEAT-2598-f3-session-memory-compaction-eviction-and-6-section-schema.md:108-112`):
  "Eviction+summarization together land in the 50-70% context-size
  reduction range on a locked trace set..."
- Tests list (`:351-354`): "50-70% reduction range on the locked trace
  set" alongside soft/hard threshold and 6-section schema coverage
- Acceptance Criteria (`:516-518`): "The eviction+summarization combo
  reduces context size to the 50-70% range..."

EPIC-2456's own Success Metrics F3 line
(`.issues/epics/P2-EPIC-2456-token-cost-reduction.md:332`) uses matching
"eviction+heuristic combo" wording. No text anywhere describes the gate as
applying to structural eviction alone. This points to **step 1's option
1** (measure the combined pipeline) as the correct path, not a
structural-only band reconciliation.

- **Existing annotation convention** to follow for steps 3/4 (updating
  EPIC-2456 and the report doc): the F3 gate line already carries a
  bracketed measurement-result annotation —
  `**[<issue-id>, <date>] <VERDICT>**: <one-line evidence>. Follow-up: <id>.`
  (`P2-EPIC-2456-token-cost-reduction.md:332`, added by ENH-2719). Append
  a new dated annotation in the same format once the combined measurement
  resolves the gate, rather than replacing the existing FAIL annotation.
- **No dedicated measurement CLI exists.** `ll-compact-session SESSION_ID
  --json` (`scripts/little_loops/cli/compact_session.py:55-97`) already
  drives the full combined pipeline
  (`session_store.compact_session()` → structural eviction →
  soft-threshold-gated `summarize_6_section()`) and its `--json` output
  surfaces `context_token_estimate` (after-tokens), but no before-token
  count or ratio. A combined-pipeline measurement script would need to
  compute before-tokens itself via the same `len(text)//4` convention
  (`session_store._estimate_tokens`, `session_store.py:3302`) and diff
  against `context_token_estimate` — the same shape ENH-2719's ad-hoc
  structural-only script used. No `--live`-flag or opt-in-marker
  convention exists elsewhere in the CLI/test surface for live-model
  measurement runs (checked `cli/compact_session.py`, `cli/ctx_stats.py`,
  `test_compaction.py`) — the established pattern in this codebase is a
  manual, uncommitted script whose output is pasted into the report doc,
  matching how ENH-2719 measured the structural-only pass.
- **Report doc structure to extend** —
  `docs/observability/realized-savings-verification.md`'s F3 section
  (lines 60-81) already documents method, a before/after table keyed by
  truncated session id, and a mean/range summary with an explicit caveat
  about the untested combined pipeline; there's also a
  `## Decision History` section (lines 150-158) with dated bullets to
  append to on resolution.

## Integration Map

### Files to Modify
- `docs/observability/realized-savings-verification.md` — append
  combined-pipeline measurement results to the F3 section (lines 60-81)
  and a dated bullet to `## Decision History` (lines 150-158)
- `.issues/epics/P2-EPIC-2456-token-cost-reduction.md:332` — update the F3
  Success Metrics line with a new bracketed annotation once resolved
  (existing convention: `**[<issue-id>, <date>] <VERDICT>**: <evidence>.`)

### Similar Patterns
- `.issues/epics/P2-EPIC-2456-token-cost-reduction.md:336` (F8 gate) —
  precedent for reconciling a gate band inline in the Success Metrics
  line itself, with a parenthetical explaining the prior unverified
  estimate
- `.issues/enhancements/P2-ENH-2745-tier-0-blocked-on-model-pricing-drift.md` —
  sibling follow-up filed from the same ENH-2719 pass, resolving a
  different EPIC-2456 gate; useful template for how a follow-up's
  resolution folds back into the EPIC and report doc
- `scripts/tests/test_heuristic_compression.py::TestReductionBand` (F4's
  locked-trace 3-6x reduction-band gate; `REDUCTION_MIN`/`REDUCTION_MAX`
  parametrized over `LOCKED_TRACE_IDS`, backed by `CompressedResult`'s
  `original_tokens`/`compressed_tokens`/`reduction_ratio` shape in
  `compression/heuristic.py:54-80`) — _wiring pass added by
  `/ll:wire-issue`:_ if the combined-pipeline measurement is ever promoted
  from a manual script to a checked-in pytest gate (rather than the
  currently-planned one-off), this is the closest existing template:
  locked trace-id fixtures, a per-trace parametrized band assertion, and
  a separate mean-in-band test. `CompactResult`
  (`compaction/result.py:15-31`) has no equivalent
  `original_tokens`/ratio field today, so adopting this pattern would
  require adding one.

### Tests
- `scripts/tests/test_compaction.py` — existing coverage is
  correctness-only (no shrink-ratio/band assertion); a combined-pipeline
  measurement would remain a manual script per the established
  convention, not a new pytest case

### Configuration
- `SOFT_THRESHOLD_TOKENS = 7500` (`scripts/little_loops/compaction/instant.py:18`) —
  F3's own trigger constant, independent of `history.compaction.budget_tokens`
  (4096) and `compression.trigger_pct` (0.4)

## Impact

- **Priority**: P3 — a measurement/gate-definition reconciliation, not a
  functional regression (more aggressive shrinkage than the gate expected
  is not obviously harmful).
- **Effort**: Small — either a doc/gate update or one measurement run.
- **Risk**: Low.

## Resolution

- **Action**: improve
- **Completed**: 2026-07-23
- **Status**: Completed

### Changes Made
- `docs/observability/realized-savings-verification.md`: ran the combined
  `evict_sink_and_window()` + `summarize_6_section()` pipeline (a live model
  call) on the same 3 on-disk sessions ENH-2719 used for the structural-only
  proxy; recorded 99.3%/98.9%/98.7% (mean 99.0%) — still outside the 50-70%
  gate, and worse than the structural-only reading. Kept the prior
  structural-only numbers as a labeled sub-section for reference, updated
  the Gate Catalog row, Follow-ups, and Decision History.
- `.issues/epics/P2-EPIC-2456-token-cost-reduction.md`: appended a new
  dated `[ENH-2746, 2026-07-23]` annotation to the F3 Success Metrics line
  alongside the existing ENH-2719 annotation, per the established
  bracketed-annotation convention.

### Verification Results
- Tests: PASS (`scripts/tests/ -k compaction`, 36 passed; no source changed)
- Lint: N/A (docs/issue-file only)
- Types: N/A (docs/issue-file only)
- Integration: PASS — no code changed; measurement reused existing
  `compaction.instant` functions unmodified

## Labels

`token-cost`, `observability`, `compaction`, `captured`

## Status

**Open** | Created: 2026-07-23 | Priority: P3

## Session Log
- `/ll:manage-issue improve` - 2026-07-23T04:31:03 - `48a00a20-ae84-4a62-8a45-875cdf446b57.jsonl`
- `/ll:ready-issue` - 2026-07-23T04:21:25 - `6f3ccc64-0431-4415-b0b8-9fd4facba423.jsonl`
- `/ll:confidence-check` - 2026-07-23T04:19:55 - `a3df09e7-aa8d-4fa9-b58d-48ea764ca43b.jsonl`
- `/ll:wire-issue` - 2026-07-23T04:17:21 - `630e795b-8aa5-4cb4-a3fa-4d87767d4f4d.jsonl`
- `/ll:refine-issue` - 2026-07-23T04:12:19 - `17176365-9289-4dc5-8678-db38cea9855d.jsonl`
- `/ll:capture-issue` - 2026-07-23T01:37:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1b068faa-9da8-4bec-af30-feafda6b3309.jsonl`
