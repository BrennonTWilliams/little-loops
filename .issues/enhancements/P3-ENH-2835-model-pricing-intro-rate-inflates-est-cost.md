---
id: ENH-2835
type: ENH
title: MODEL_PRICING doesn't model Sonnet 5 intro pricing, inflating est_cost
priority: P3
status: open
captured_at: '2026-07-26T00:00:00Z'
discovered_date: '2026-07-26'
discovered_by: capture-issue
labels:
- pricing
- observability
relates_to:
- ENH-2745
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
- `/ll:capture-issue` - 2026-07-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dd4fa187-84cc-4f7b-9326-90fd6e0b6b6d.jsonl`
