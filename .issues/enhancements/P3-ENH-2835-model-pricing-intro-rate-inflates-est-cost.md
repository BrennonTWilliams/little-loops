---
id: ENH-2835
type: ENH
title: MODEL_PRICING doesn't model Sonnet 5 intro pricing, inflating est_cost
priority: P3
status: done
captured_at: '2026-07-26T00:00:00Z'
completed_at: '2026-07-26T22:18:18Z'
discovered_date: '2026-07-26'
discovered_by: capture-issue
labels:
- pricing
- observability
relates_to:
- ENH-2745
confidence_score: 100
outcome_confidence: 93
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 23
score_change_surface: 23
---

# ENH-2835: MODEL_PRICING doesn't model Sonnet 5 intro pricing, inflating est_cost

## Summary

`scripts/little_loops/pricing.py`'s `MODEL_PRICING["claude-sonnet-5"]` entry
uses the standard post-intro rate ($3/M input, $15/M output, $0.30/M
cache-read, $3.75/M cache-creation) even though Sonnet 5 is currently under a
temporary introductory rate ($2/M input, $10/M output) through 2026-08-31. This
was a deliberate scope-cut in ENH-2745 ("Sonnet 5's $2/$10 introductory rate
through 2026-08-31 is not modeled — standard rates used"), but the follow-up to
actually apply the discount was never filed. Every `ll-loop run`/`ll-harness`
`est_cost` figure for Sonnet 5 traffic is currently overstated by roughly 33%
(2/3 of the standard rate) until the intro window ends.

## Current Behavior

`estimate_cost_usd()` (`scripts/little_loops/pricing.py`) looks up a single,
static per-model rate with no time-bounding. A `general-task` run on
2026-07-26 reported `$23.79` total `est_cost`; at the actual $2/$10 intro rate
the same usage would cost closer to `$15.86`.

## Expected Behavior

`MODEL_PRICING` (or `estimate_cost_usd`) should apply the $2/$10 intro rate
(and the correspondingly discounted cache rates) for `claude-sonnet-5` while
`2026-08-31` has not yet passed, and revert to the standard $3/$15 rate
automatically afterward — without requiring a manual code edit on the cutover
date.

## Motivation

Cost estimates drive real decisions (loop budget tuning, `ll-loop
calibrate-budget`, Tier 0 before/after gates in EPIC-2456). A ~33% systematic
overstatement understates the actual savings of any optimization and could
cause budget/cost-gate decisions to be made against inflated numbers for the
five weeks the intro rate is active.

## Integration Map

### Files to Modify
- `scripts/little_loops/pricing.py` — extend `MODEL_PRICING["claude-sonnet-5"]`
  with a time-bounded intro sub-table and add the date-comparison branch to
  `estimate_cost_usd()` (lines 12-31, 87-116); update/remove the stale
  scope-cut note in the module docstring (lines 4-6)
- `scripts/tests/test_pricing.py` — add pre-expiry / post-expiry / boundary
  (`2026-08-31` exactly) test cases to `TestEstimateCostUsd`, following the
  `TestBatchDiscount` (lines 67-84) conditional-multiplier test style

### Dependent Files (Callers — no changes expected, pick up the fix automatically)
- `scripts/little_loops/fsm/cost_graph.py:235` — per-row cost aggregation
- `scripts/little_loops/session_store.py:2572` — usage-event cost recording
- `scripts/little_loops/session_store.py:3697` — historical usage backfill
- `scripts/little_loops/cli/loop/_helpers.py` — cost table rendering (via `CostReport`)
- `scripts/little_loops/cli/ctx_stats.py` — context-window cost stats

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `estimate_cost_usd()`'s signature has a standing append-only, keyword-default
  contract: the batch-discount decision (`.ll/decisions.d/1eee63aa-c942-4ea5-a2a6-09d4a43d25ba.json`)
  requires new parameters (e.g. an "as-of date" override) to be appended at the
  end with a default, not inserted — so existing positional callers
  (`fsm/cost_graph.py`, `session_store.py`) stay unaffected. Prefer a bare
  `date.today()` call inside the function over a required new parameter.

### Similar Patterns
- `scripts/little_loops/learning_tests/gate.py:37-55` (`is_record_stale()`) —
  closest existing "valid until threshold, else fallback" shape
- `scripts/little_loops/issue_history/debt.py:401`,
  `scripts/little_loops/issue_history/summary.py:215` — bare `date.today()`
  comparison-window precedent (no shared injectable clock exists project-wide)

### Tests
- `scripts/tests/test_pricing.py` — existing coverage (`TestModelPricing`,
  `TestEstimateCostUsd`, `TestBatchDiscount`); no date/time coverage yet
- `scripts/tests/test_issue_history_debt.py:69-111` — reference pattern for
  mocking `date.today()` via `patch("<module>.date")`

_Wiring pass added by `/ll:wire-issue`:_
- `pricing.py` has zero `datetime`/`patch` imports today — adding a
  date-comparison branch requires `from datetime import date` in `pricing.py`
  so tests can `patch("little_loops.pricing.date")` per the
  `test_issue_history_debt.py` convention. No existing `TestBatchDiscount`/
  `TestEstimateCostUsd` case hardcodes a `claude-sonnet-5` dollar value (all
  use `claude-sonnet-4-6`) — confirmed no existing test will break when the
  intro rate becomes default.
- `scripts/tests/test_fsm_cost_graph.py`, `scripts/tests/test_cli_cost_table.py`,
  `scripts/tests/test_tier0_traces.py` — exercise `CostReport`/cost aggregation
  downstream of `estimate_cost_usd`; run as a regression check post-change.
- New test cases needed in `TestEstimateCostUsd`: (1) pre-expiry — mocked
  `today` before `2026-08-31` uses $2/$10 intro rates; (2) post-expiry — mocked
  `today` after `2026-08-31` uses $3/$15 standard rates; (3) exact boundary at
  `2026-08-31` itself (direct analog to `test_issue_history_debt.py`'s
  `test_aging_30_boundary_exactly_30_days`) — requires an explicit inclusive/
  exclusive decision, since "has not yet passed" implies the intro rate is
  still active *on* 2026-08-31; (4) an unaffected-model regression case (e.g.
  `claude-sonnet-4-6`) proving the date branch only touches `claude-sonnet-5`;
  (5) a shape assertion that the new `intro` sub-dict populates all four rate
  keys (`input`, `output`, `cache_read`, `cache_creation`), since
  `estimate_cost_usd()` indexes with `pricing["input"]` (bracket, not `.get()`)
  and a missing key would raise `KeyError` instead of degrading gracefully.

### Documentation
- `docs/observability/realized-savings-verification.md` — references the
  Tier 0 gate blocked partly on this pricing gap; may need a status update
  once resolved

_Wiring pass added by `/ll:wire-issue`:_
- `docs/observability/tier0-traces.md` — line ~231 cites a stale line-range
  anchor (`scripts/little_loops/pricing.py:10-55 — MODEL_PRICING constants`)
  that will shift once the intro sub-table is added; lines ~154-167 document
  a `has_unknown_model` assertion sensitive to any new lookup-miss path in
  `estimate_cost_usd()` — review both for staleness after the change.
- `docs/reference/CLI.md` lines 618-641 (`est_cost` column description) —
  mechanism-level prose referencing `MODEL_PRICING` generically; likely no
  edit needed but worth a stale-reference check.
- `.ll/decisions.d/f472613b-7f09-48b7-b86d-7a12c032f091.json` — records the
  original scope-cut decision this issue resolves; close it via `ll-issues
  decisions outcome` once implemented (not a code change).

## Proposed Solution

1. Extend the `MODEL_PRICING` entry shape (or add a parallel time-bounded
   override table) to support an expiring rate: e.g. `{"input": 3.0, ...,
   "intro": {"input": 2.0, "output": 10.0, "cache_read": 0.20, "cache_creation":
   2.5, "expires": "2026-08-31"}}`.
2. In `estimate_cost_usd()`, compare against the current date and select the
   intro sub-table when unexpired, else fall back to standard rates. Needs a
   date source consistent with the rest of the codebase (avoid hardcoding
   "today" at write-time).
3. Update `scripts/tests/test_pricing.py` to cover both the pre- and
   post-expiry code paths (e.g. by injecting/mocking the comparison date
   rather than relying on wall-clock time in tests).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

4. Add `from datetime import date` to `scripts/little_loops/pricing.py` (no
   datetime import exists there today) so tests can
   `patch("little_loops.pricing.date")` per the house convention.
5. Keep `estimate_cost_usd()`'s signature append-only/keyword-default if any
   new parameter is added (standing decision in
   `.ll/decisions.d/1eee63aa-c942-4ea5-a2a6-09d4a43d25ba.json`); prefer a bare
   `date.today()` call inside the function so `fsm/cost_graph.py` and
   `session_store.py` positional callers stay unaffected.
6. Add pre-expiry, post-expiry, exact-boundary (`2026-08-31`), unaffected-model
   regression, and intro-sub-dict-shape test cases to `TestEstimateCostUsd` in
   `scripts/tests/test_pricing.py` (five cases, detailed under Integration
   Map → Tests).
7. Update the stale module docstring in `pricing.py` (lines 1-7) removing the
   "not modeled here" scope-cut sentence.
8. Review `docs/observability/tier0-traces.md` for the stale
   `pricing.py:10-55` line-range anchor and the `has_unknown_model` note once
   line numbers shift.
9. Run `scripts/tests/test_fsm_cost_graph.py`, `test_cli_cost_table.py`, and
   `test_tier0_traces.py` as a regression check after the change.
10. Close `.ll/decisions.d/f472613b-7f09-48b7-b86d-7a12c032f091.json` via
    `ll-issues decisions outcome` once implemented.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Current shape**: `MODEL_PRICING` (`scripts/little_loops/pricing.py:12-76`)
  is a flat `dict[str, dict[str, float]]` — every entry has exactly 4 keys
  (`input`, `output`, `cache_read`, `cache_creation`), no entry has a 5th key
  today. The `claude-sonnet-5` entry (lines 26-31) is byte-for-byte identical
  in shape to `claude-sonnet-4-6` (lines 45-50) and `claude-sonnet-3-7`
  (lines 64-69). The module docstring (lines 4-6) already states the scope-cut
  in prose: *"Sonnet 5's intro pricing ($2/$10 through 2026-08-31) is not
  modeled here — standard rates are used."* — this line should be
  removed/updated once the fix lands.
- **`estimate_cost_usd()`** (`scripts/little_loops/pricing.py:87-116`): does a
  single `pricing = MODEL_PRICING.get(model)` lookup (line 104) with no
  date/time parameter anywhere in its signature or body. Returns `None` for an
  unknown model (lines 105-106); otherwise reads all 4 rate fields via bracket
  indexing (`pricing["input"]`, etc., lines 108-113) — **not** `.get()` — so a
  new `intro` sub-dict must populate all 4 keys or a lookup will raise
  `KeyError` instead of degrading gracefully. `BATCH_DISCOUNT` (line 79) +
  the `is_batch` flag (lines 114-115) is the closest existing precedent in this
  same function for a "compute base cost, then conditionally adjust" branch —
  worth mirroring for the intro-rate branch's shape.
- **No injectable clock exists project-wide.** There is no shared
  `Clock`/`_now()` protocol or config key for overriding "today" for tests.
  The established convention (used identically in 3+ places) is a bare
  `date.today()` call at the comparison site, with tests patching the
  module-level `date` import directly:
  - Closest structural analog — "value valid until threshold, else fallback" —
    is `is_record_stale()` in
    `scripts/little_loops/learning_tests/gate.py:37-55`, which parses an ISO
    date, computes `(datetime.date.today() - record_date).days`, and falls
    back to a safe default on parse failure.
  - Same `today = date.today()` shape (module-level `from datetime import
    date`, one comparison per call) also appears in
    `scripts/little_loops/issue_history/debt.py:401`,
    `scripts/little_loops/issue_history/summary.py:215`, and
    `scripts/little_loops/issue_history/analysis.py:85`.
  - No `freezegun` dependency exists in this project — the house style for
    mocking "today" is `unittest.mock.patch("<module>.date")` +
    `mock_date.today.return_value = date(...)`, demonstrated in
    `scripts/tests/test_issue_history_debt.py:69-111` (including an
    exactly-on-the-boundary test case, `test_aging_30_boundary_exactly_30_days`
    — a direct analog for testing the `2026-08-31` cutover date itself).
- **Call sites of `estimate_cost_usd()`** that will pick up the corrected
  intro rate automatically once fixed (no changes needed at these sites):
  `scripts/little_loops/fsm/cost_graph.py:235`,
  `scripts/little_loops/session_store.py:2572` (usage recording) and `:3697`
  (historical backfill), and indirectly `scripts/little_loops/cli/loop/_helpers.py`
  (cost table rendering) and `scripts/little_loops/cli/ctx_stats.py`.
- **Test file to extend**: `scripts/tests/test_pricing.py` — `TestBatchDiscount`
  (lines 67-84) is the closest existing style precedent for testing a
  conditional-multiplier code path (default vs. flag-triggered), directly
  analogous to how a pre-expiry-vs-post-expiry pair of tests should be
  structured for the intro rate.
- **Docs that reference the deferred scope-cut and may need a follow-up
  update once this lands**: `docs/observability/realized-savings-verification.md`
  (lines 18, 31-51, 120-122) references ENH-2745's Tier 0 gate as blocked
  partly on this pricing gap.

## Impact

- **Priority**: P3 — cost estimates are directional/informational, not a
  correctness-blocking bug, but the 33% skew is large enough to mislead budget
  decisions during the ~5-week intro window.
- **Effort**: Small — one pricing table/function change plus tests.
- **Risk**: Low.

## Labels

`pricing`, `observability`, `captured`

## Status

**Open** | Created: 2026-07-26 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-07-26T22:17:50Z - `2f4a5db5-167f-494a-a4a6-f6b69e644f6c.jsonl`
- `/ll:wire-issue` - 2026-07-26T22:10:02 - `7ffe1944-52a4-4bab-8b89-30b739733d35.jsonl`
- `/ll:refine-issue` - 2026-07-26T22:02:34 - `2ae2009f-291c-495e-977e-2a481b51e8aa.jsonl`
- `/ll:capture-issue` - 2026-07-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dd4fa187-84cc-4f7b-9326-90fd6e0b6b6d.jsonl`
