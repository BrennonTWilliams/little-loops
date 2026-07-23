---
id: ENH-2745
type: ENH
title: Tier 0 before/after cost gate blocked on model-pricing drift
priority: P2
status: done
captured_at: '2026-07-23T01:37:52Z'
completed_at: '2026-07-23T04:07:04Z'
discovered_date: '2026-07-23'
discovered_by: capture-issue
parent: EPIC-2456
labels:
- token-cost
- observability
- pricing
relates_to:
- EPIC-2456
- ENH-2719
- FEAT-2470
- ENH-2518
confidence_score: 89
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 18
---

# ENH-2745: Tier 0 before/after cost gate blocked on model-pricing drift

## Summary

ENH-2719's realized-savings verification pass found that FEAT-2470's Tier 0
before/after cost-delta gate cannot currently be computed against the ENH-2518
locked baseline. `MODEL_PRICING` (`scripts/little_loops/pricing.py`) has no
entries for `claude-sonnet-5` or `claude-opus-4-8` — the models every loop run
on disk from 2026-07-20 onward actually uses. `CostReport.from_usage_jsonl`
returns `cost_usd: 0.0` / `has_unknown_model: true` for any of these traces.

## Current Behavior

- The locked Tier 0 trace set (`scripts/tests/fixtures/tier0_traces/manifest.json`,
  owner ENH-2518) is pinned to `single_model_only: claude-sonnet-4-6`.
- The only post-FEAT-2470 `general-task` run on disk
  (`.loops/runs/general-task-20260707T133447/usage.jsonl`, 2026-07-07) uses
  `MiniMax-M3[1m]`, which is also unpriced.
- Every loop run since 2026-07-20 uses `claude-sonnet-5` or
  `claude-opus-4-8[1m]` — neither is in `MODEL_PRICING`.

## Expected Behavior

Either `MODEL_PRICING` carries entries for the fleet's current default
model(s), or a new Tier 0 baseline is locked against whichever model is
actually in production use, so a same-model (or same-regime) before/after
cost delta can be computed for FEAT-2470's success gate.

## Proposed Solution

1. Add `claude-sonnet-5` / `claude-opus-4-8` (and any other actively-used
   models found via `usage_events.model` in `.ll/history.db`) to
   `MODEL_PRICING` with current published pricing.
2. Decide whether to relock a new Tier 0 baseline against the current
   default model (superseding ENH-2518's `claude-sonnet-4-6` set) or keep
   the existing set as a historical reference and diff same-model traces
   only when they recur.
3. Re-run the Tier 0 before/after measurement once pricing/baseline is
   resolved; update `docs/observability/realized-savings-verification.md`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Actual model strings on disk** (`.ll/history.db`, `usage_events.model`,
  queried directly): `claude-sonnet-4-6` (65,547 rows, through 2026-06-30),
  `claude-sonnet-5` (43,123 rows, 2026-06-30 onward), `MiniMax-M3` (41,053
  rows, unpriced, unrelated to this issue), `claude-opus-4-8` (31,671 rows,
  2026-06-13 onward), `claude-fable-5` (987 rows, 2026-07-11 onward),
  `deepseek-v4-flash`/`deepseek-v4-pro` (unpriced, unrelated),
  `claude-haiku-4-5-20251001` (118 rows, already priced). `SUM(cost_usd)`
  for both `claude-sonnet-5` and `claude-opus-4-8` rows is `NULL`,
  confirming they price to nothing today.
- **Correction to the issue's `[1m]`-suffix claim**: `usage_events.model`
  stores the bare string `claude-opus-4-8` — no `[1m]` rows exist in
  `.ll/history.db` (`SELECT DISTINCT model FROM usage_events WHERE model
  LIKE '%1m%'` returns empty). The `[1m]` suffix does appear as an example
  in `context_window.py:43`'s docstring and in `docs/observability/
  realized-savings-verification.md:42`, but is not present in the live
  data this gate will actually diff against. `claude-fable-5` is also a
  live, actively-used model with no `MODEL_PRICING` entry — not mentioned
  in the issue body but affected by the same fix if fable-run traces ever
  enter a Tier 0 comparison set.
- **`MODEL_PRICING` lookup is exact-string, no normalization**
  (`scripts/little_loops/pricing.py:83`, `estimate_cost_usd`): a single
  `MODEL_PRICING.get(model)` call, no prefix/suffix stripping, no fuzzy
  match. Contrast with the sibling table `context_window.py:19-33`
  (`MODEL_CONTEXT_WINDOW`), which already has a `claude-opus-4-8: 200_000`
  entry and explicitly strips a `[1m]` suffix before lookup
  (`context_window_for()`, `context_window.py:67-69`) — `pricing.py` has
  no equivalent suffix-handling, so if a `[1m]`-suffixed model string is
  ever seen, adding `claude-opus-4-8` alone would not cover it.
- **Bucket-level (not row-level) poisoning**: `CostReport.from_usage_jsonl`
  (`scripts/little_loops/fsm/cost_graph.py:184-256`) sets a per-state
  bucket's `has_unknown_model = True` the moment any row in that state is
  unpriced (lines 236-237), which stops `cost_usd` accumulation for that
  whole bucket; `_compute_totals()` (`cost_graph.py:259-273`) then ORs all
  bucket flags into the report total and skips summing `cost_usd`
  entirely if any bucket is poisoned (`totals["cost_usd"]` stays `0.0`).
  One unpriced state anywhere in a run zeroes the whole report, not just
  its own contribution.
- **Tier 0 lock mechanics to follow for a relock** (ENH-2518 precedent):
  `scripts/tests/fixtures/tier0_traces/manifest.json` `_meta` carries
  `owner`, `lock_date`, and `command_options: {min_count, single_model_only,
  model}`. ENH-2518's issue file
  (`.issues/enhancements/P2-ENH-2518-lock-tier-0-verification-trace-set.md:276-297`)
  embeds the exact one-off Python snippet used to compute baseline costs
  per trace via `estimate_cost_usd` — no separate generator script exists;
  a relock would reuse this snippet against new `claude-sonnet-5`/
  `claude-opus-4-8` traces once priced, then stamp `_meta.owner` to
  `ENH-2745` and update `command_options.model`.
  `scripts/tests/test_tier0_traces.py:37-40`'s `LOCKED_TRACE_IDS` tuple
  mirrors the manifest and must be updated in lockstep if traces are
  swapped.
- **Test coverage to extend**: `scripts/tests/test_pricing.py`'s
  `TestModelPricing.test_known_models_present` needs new `assert "..." in
  MODEL_PRICING` lines per added model; `test_pricing_fields_present` and
  `test_output_more_expensive_than_input` iterate `MODEL_PRICING.items()`
  generically and cover new entries automatically as long as they carry
  the same 4-field shape (`input`/`output`/`cache_read`/`cache_creation`).
- **Fleet-wide unpriced-model query for future re-runs**: the reusable
  pattern is `history_reader.py:1057-1109`'s `aggregate_usage(
  group_by="model")` (rolls up `usage_events` by model, `cost_usd` sums to
  `NULL`/0 for unpriced rows), or the raw SQL used above directly against
  `.ll/history.db`.
- **Live status confirmation**: `docs/observability/
  realized-savings-verification.md:18,31-49` already documents this gate
  as `BLOCKED` — this issue is the tracked follow-up referenced at line
  120-121 of that doc.

## Integration Map

_Wiring pass added by `/ll:wire-issue`:_

### Files to Modify

- `scripts/little_loops/pricing.py` — add `MODEL_PRICING` entries for
  `claude-sonnet-5`, `claude-opus-4-8`, `claude-fable-5` (core fix).
- `scripts/little_loops/context_window.py` — sibling `MODEL_CONTEXT_WINDOW`
  table already has `claude-opus-4-8` (200_000) but is missing
  `claude-sonnet-5` and `claude-fable-5`. Same root cause (model-string
  drift), adjacent table, not currently in this issue's scope — flagged
  here so a relock/fix pass doesn't miss it. Also has a bash mirror
  (`hooks/scripts/context-monitor.sh:get_context_limit()`) referenced in
  its own module docstring, out of Python scope.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/session_store.py` — `record_usage_event()` (~line
  2084) and the historical usage backfill loop (~line 3013) both call
  `estimate_cost_usd()`. No code change needed, but `cost_usd` output for
  `claude-sonnet-5`/`claude-opus-4-8`/`claude-fable-5` rows flips from
  `NULL` to a real value once priced — a behavior change worth spot-checking.
- `scripts/little_loops/cli/loop/_helpers.py` — `_print_usage_summary()`
  renders the per-state cost table via `CostReport.from_usage_jsonl()`;
  `~$X.XXX (model unknown)` rows for these models become real dollar
  amounts once priced.
- `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_usage_events()`
  (`ll-ctx-stats`) is a downstream consumer of the same cost aggregation;
  output values change once these models price successfully.

### Documentation

- `docs/observability/tier0-traces.md` — **not previously flagged in the
  issue.** Directly coupled to the relock decision in Proposed Solution
  step 2: pins `single_model_only: claude-sonnet-4-6` (~line 40-41),
  describes the `model` envelope field as `"Locked single-model
  (\"claude-sonnet-4-6\")"` (~line 106), explains the bucket-poisoning
  nuance that a non-Claude-model trace "must either ensure that trace's
  `model` resolves in `MODEL_PRICING` or relax this assertion" (~line 166),
  and documents `has_unknown_model` flipping `true` "until pricing entries
  are added" (~line 189) — this is the exact mechanism the relock decision
  interacts with and must be updated if a new baseline supersedes ENH-2518's.
- `docs/observability/realized-savings-verification.md` — already named in
  Proposed Solution step 3; exact spans confirmed: line 18 (Gate Catalog
  `BLOCKED` verdict), lines 31-51 (`## Tier 0 (FEAT-2470) — BLOCKED`
  narrative section, including the `grep -n "claude-sonnet-5\|claude-opus-4-8"
  scripts/little_loops/pricing.py` — no match` line), lines 120-122
  (`## Follow-ups Filed` entry citing this issue) — all need rewriting once
  the gate becomes computable.

### Tests

- `scripts/tests/test_pricing.py::TestModelPricing::test_known_models_present`
  — add `assert "claude-sonnet-5" in MODEL_PRICING` /
  `assert "claude-opus-4-8" in MODEL_PRICING` /
  `assert "claude-fable-5" in MODEL_PRICING` lines (mechanical, follows the
  existing one-line-per-model pattern). `test_pricing_fields_present` and
  `test_output_more_expensive_than_input` iterate `MODEL_PRICING.items()`
  generically and need no edit.
- `scripts/tests/test_context_window.py` — new test needed only if
  `context_window.py`'s `MODEL_CONTEXT_WINDOW` gap (see Files to Modify) is
  also closed in this pass.
- Confirmed **no existing test breaks**: searched
  `test_fsm_cost_graph.py`, `test_fsm_executor.py`, `test_tier0_traces.py`,
  `test_cli_cost_table.py` — none assert `has_unknown_model`/`cost_usd==0.0`
  tied to these three specific model strings, and `test_fsm_executor.py`'s
  six `model="claude-sonnet-5"` usages are opaque mock kwargs, never passed
  through `estimate_cost_usd`.
- **Gap, no existing pattern**: fleet-wide pricing-drift detection (a query
  that surfaces models present in `usage_events` but absent from
  `MODEL_PRICING`) has no automated test — closest precedent is
  `history_reader.py::aggregate_usage(group_by="model")`, used ad hoc via
  raw SQL in this issue's own refinement research rather than through a
  tested code path. Worth a regression test if this drift class recurs.

## Impact

- **Priority**: P2 — blocks the only unmeasured piece of EPIC-2456's Tier 0
  gate; no user-facing behavior change.
- **Effort**: Small — pricing table entries are data, not logic changes;
  relocking a baseline follows the ENH-2518 precedent.
- **Risk**: Low.

## Labels

`token-cost`, `observability`, `pricing`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-22_

**Readiness Score**: 89/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- Actual `$/Mtok` pricing values for `claude-sonnet-5`, `claude-opus-4-8`, and
  `claude-fable-5` are not specified anywhere in the issue — "current
  published pricing" must be sourced (e.g. via `/ll:claude-api` or a web
  lookup) before the `MODEL_PRICING` entries can be written; a wrong figure
  would silently poison the Tier 0 cost gate the same way a missing one does.
- Proposed Solution step 2 leaves an open, unresolved decision (relock a new
  Tier 0 baseline against the current default model vs. keep the ENH-2518
  `claude-sonnet-4-6` set as historical reference) — this should be decided
  before implementation starts to avoid rework on the manifest/test-fixture
  side.

## Resolution

- Added `claude-sonnet-5` ($3/$15/$0.30/$3.75 per Mtok), `claude-opus-4-8`
  ($5/$25/$0.50/$6.25), and `claude-fable-5` ($10/$50/$1.00/$12.50) to
  `MODEL_PRICING` (`scripts/little_loops/pricing.py`), sourced from current
  published Anthropic pricing (Sonnet 5's $2/$10 introductory rate through
  2026-08-31 is not modeled — standard rates used).
- **Relock decision (Proposed Solution step 2)**: kept the ENH-2518
  `claude-sonnet-4-6` Tier 0 trace set as the historical reference rather than
  relocking against the current default model. Relocking requires capturing a
  new trace set and updating the manifest/`LOCKED_TRACE_IDS` fixture — a
  separate, larger effort than this issue's pricing-table scope. Filed as a
  follow-up in `docs/observability/realized-savings-verification.md`.
- Extended `test_pricing.py::TestModelPricing::test_known_models_present`
  with the three new model assertions; `test_pricing_fields_present` and
  `test_output_more_expensive_than_input` cover the new entries generically.
- Updated `docs/observability/realized-savings-verification.md` (Gate
  Catalog row, Tier 0 section, Follow-ups) to reflect the pricing fix while
  keeping the gate `BLOCKED` pending the relock follow-up.
- Out of scope per the issue's own Integration Map: `context_window.py`'s
  `MODEL_CONTEXT_WINDOW` gap (adjacent table, same root cause, explicitly
  flagged as not-in-scope) and `docs/observability/tier0-traces.md` (only
  needs updating if/when a relock happens).
- Full suite: `python -m pytest scripts/tests/` — 15911 passed, 38 skipped.

## Status

**Done** | Created: 2026-07-23 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-07-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17511300-04f0-4885-83b3-601084f09cbc.jsonl`
- `/ll:wire-issue` - 2026-07-23T03:57:10 - `b7b7b660-d788-4f5e-8c14-e29c6df80fb5.jsonl`
- `/ll:refine-issue` - 2026-07-23T03:51:35 - `96cbf5a6-0e23-4726-895f-08fab765d190.jsonl`
- `/ll:capture-issue` - 2026-07-23T01:37:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1b068faa-9da8-4bec-af30-feafda6b3309.jsonl`
- `/ll:manage-issue` - 2026-07-23T04:06:24Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2d37ec46-6d79-46ce-b85d-d8d6213568b6.jsonl`
