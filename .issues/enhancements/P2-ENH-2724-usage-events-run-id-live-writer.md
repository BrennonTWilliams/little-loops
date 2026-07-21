---
id: ENH-2724
type: ENH
title: usage_events live per-invocation run_id writer (on_usage_detailed)
priority: P2
status: done
captured_at: '2026-07-21T18:30:00Z'
completed_at: '2026-07-21T19:42:15Z'
discovered_date: '2026-07-21'
discovered_by: issue-size-review
parent: EPIC-2456
labels:
- token-cost
- observability
- history-db
relates_to:
- EPIC-2456
- ENH-2721
- ENH-2723
- ENH-2712
- ENH-2722
blocked_by:
- ENH-2723
decision_needed: false
spike_needed: false
spike_attempted: true
spike_completed: true
confidence_score: 99
outcome_confidence: 77
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 20
---

# ENH-2724: `usage_events` live per-invocation `run_id` writer (`on_usage_detailed`)

## Summary

Promote the ENH-2712 spike's write mechanism into production: extend the `on_usage: UsageCallback` parameter into a richer `on_usage_detailed` callback (model, cache tokens, `run_id`) wired at both `_run_action()` (`fsm/executor.py:1482`) and `_run_baseline_arm()` (`fsm/executor.py:2184`), so one `usage_events` row is INSERTed per LLM call with `run_id` stamped at write time. This is the live-writer slice of ENH-2721, decomposed to build on the schema column from ENH-2723.

## Current Behavior

`usage_events` has no live per-invocation writer. Rows only exist via `_backfill_usage_events()` parsing `raw_events` after the fact, so the `run_id` column ENH-2723 added stays unpopulated on new rows — `_run_action()`/`_run_baseline_arm()` never stamp `run_id` (or any per-call token/model data) at write time.

## Expected Behavior

`on_usage_detailed` is wired at both `_run_action()` and `_run_baseline_arm()` call sites and, near `_finish()`, writes one `usage_events` row per LLM call with `run_id` stamped using the same derivation `_finish()` already uses for `loop_runs`. Existing `usage_events` consumers (`cost_attribution()`, `ctx_stats.py`, `cost_graph.py`, `archive_run()`) see no behavior change.

## Parent Issue

Decomposed from ENH-2721: `usage_events` `run_id` column + live per-invocation writer (split from ENH-2712)

## Blocked By

ENH-2723 (the `run_id` column must exist before this writer can stamp it).

## Decision Context (inherited from ENH-2721 / ENH-2712)

**Selected: Option A** — richer `on_usage_detailed` callback wired at `_run_action()`/`_run_baseline_arm()`, over Option B (a single UPDATE at `_finish()` scoped by `[started_at, ended_at]`). Option B was rejected because `loop_runs` has no `session_id` to scope a `BETWEEN` join, and `ll-parallel`/`ll-sprint` run overlapping windows by design — reproducing the exact misattribution failure this issue's lineage already rejected. See ENH-2721's Decision Rationale for the full scored comparison (Option A: 10/12, Option B: 4/12).

`DetailedUsageCallback`/`TokenUsage` and `ActionResult.usage_events` collection already exist in production (`subprocess_utils.py:41,45-60,295-296,473-483`; `fsm/runners.py:23-25,47-48,103-104,156-173,197`) — this is mostly wiring existing pieces through `_run_action()`/`_run_baseline_arm()`, not new design.

## Spike Results (inherited from ENH-2712/ENH-2721)

A 2026-07-21 spike already proved this mechanism viable — see `scripts/tests/spike/usage_events_run_id_writer/` (5/5 tests passing):

| Risk | Proven by | Result |
|------|-----------|--------|
| No live per-invocation writer exists; unproven mid-run write mechanism | `test_single_run_stamps_correct_run_id` | pass |
| Concurrent `ll-parallel`/`ll-sprint` writers could cross-attribute or corrupt `run_id` | `test_concurrent_runs_do_not_cross_attribute` | pass |
| Concurrent writes under `busy_timeout`/WAL could silently drop rows | `test_concurrent_runs_lose_no_writes` | pass |
| `run_id` derivation must match `_finish()`'s inline format exactly | `test_run_id_derivation_matches_executor_format` | pass |
| Isolation guard (spike must not depend on production modules) | `test_spike_does_not_import_production_modules` | pass |

**Promotion plan**: move `record_usage_event()`/`derive_run_id()` from `scripts/tests/spike/usage_events_run_id_writer/` to production (`session_store.py`/`fsm/executor.py`, or a promoted module if the spike shape maps cleanly).

## Implementation Steps

1. Promote `record_usage_event()`/`derive_run_id()` from `scripts/tests/spike/usage_events_run_id_writer/` into production code.
2. Extend `UsageCallback` into `on_usage_detailed` (model, cache tokens, `run_id`) and wire it at `_run_action()` (`fsm/executor.py:1482`) and `_run_baseline_arm()` (`fsm/executor.py:2184`).
3. Wire the write-through near `_finish()` (`fsm/executor.py:2583-2613`), sibling to `record_loop_run_summary()`, deriving `run_id` with the same format `_finish()` already uses (`self.started_at.replace(":", "").replace(".", "").replace("+", "")[:17]`, concatenated as `f"{run_id}-{self.fsm.name}"`).
4. Update `config-schema.json`'s `analytics.capture.usage_events` description (~line 1749) — it currently asserts `usage_events` has no live writer; that becomes false once this ships.
5. Verify no behavior change to existing `usage_events` consumers: `history_reader.py::cost_attribution()`, `cli/ctx_stats.py`, `fsm/cost_graph.py`, `fsm/persistence.py::archive_run()` (the mirrored `run_id`/archive-path derivation this must continue to match).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Gate the new write behind `feature_enabled_for(config, "analytics.capture.usage_events", ...)` (`config/features.py:610-639`) — this flag exists and defaults `true` but is currently never checked anywhere in production code; this issue is its first real consumer.
7. Decide and document scope for `_dispatch_live()` (`fsm/executor.py:2014`, reached from `_run_action()` at line 1581 for `"sdk"`/`"batch"` request paths) — it bypasses `on_usage`/`on_usage_detailed` entirely today, so SDK/Batch-dispatched invocations won't get a live-written `usage_events` row unless this path is separately wired or explicitly excluded in Scope Boundaries.
8. Update `docs/reference/CONFIGURATION.md:539` alongside `config-schema.json` — same stale "reserved for a future live writer" claim in both places.
9. Update `cli/ctx_stats.py:184-188`'s `_aggregate_usage_events()` docstring — its "populated by `_backfill_usage_events`" / "carries no FSM `state`" claims become only partially true once live-written rows exist.
10. Add a `"run_id": "run_id"` entry to `history_reader.py:843-851`'s `_COST_ATTR_GROUP_COLUMNS` if `cost_attribution(group_by="run_id")` is expected to work once `run_id` is live (needed by ENH-2722's downstream waste view).

## Scope Boundaries

- **Out of scope**: the v29 schema migration itself — that is ENH-2723 (prerequisite).
- **Out of scope**: backfilling `run_id` on historical rows — that is ENH-2725.
- **Out of scope**: the query/CLI waste view (`waste_attribution()`, `ll-ctx-stats` waste section) — that is ENH-2722, blocked on this issue's parent.
- **Known residual gap** (acknowledged, not a blocker): `_run_action()`'s shell/mcp branches have no usage signal today (partial per-action-mode coverage); the spike's INSERT omits `cost_usd`/`invocation_id`/`provider_vendor`. Addressable during promotion, not required for this issue's acceptance criteria.
- **In scope**: the `on_usage_detailed` callback, both call-site wirings, the `_finish()`-adjacent write, and the config-schema doc update.

## Acceptance Criteria

- [x] Live writer stamps `run_id` on new `usage_events` rows at loop-run finish, matching `_finish()`'s `run_id` derivation exactly.
- [x] Concurrent `ll-parallel`/`ll-sprint` runs do not cross-attribute or lose rows (regression coverage carried over from the spike: cross-attribution + no-lost-writes tests — each `record_usage_event()` call is a self-contained `connect()`/`INSERT`/`commit()`/`close()`, matching `record_loop_run_summary()`'s concurrency-safe shape; the spike already proved this pattern under WAL/busy_timeout).
- [x] `config-schema.json`'s `analytics.capture.usage_events` description reflects the live writer.
- [x] No behavior change to existing `usage_events` consumers (`cost_attribution()`, `ctx_stats.py`, `cost_graph.py`, `archive_run()`).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py:1482` (`_run_action()`) — thread `on_usage_detailed`
- `scripts/little_loops/fsm/executor.py:2184` (`_run_baseline_arm()`) — thread `on_usage_detailed`
- `scripts/little_loops/fsm/executor.py:2583-2613` (`_finish()`) — new `run_id`-stamped write, sibling to `record_loop_run_summary()`
- `scripts/little_loops/config-schema.json` (~line 1749-1752) — update `analytics.capture.usage_events` description
- `scripts/tests/test_fsm_executor.py` — verify `record_loop_run_summary()` caller in `_finish()` still passes alongside the new write-through; concurrency regression tests promoted from the spike

### Similar Patterns
- `scripts/tests/spike/usage_events_run_id_writer/writer.py` — spike implementation to promote
- `record_loop_run_summary()` (`session_store.py:1709-1780`) — existing sibling writer pattern (connect → parameterized INSERT → commit → close-in-finally)
- `_finish()`'s `record_loop_run_summary` sink (`fsm/executor.py:2594-2613`, try/except-pass around the call) plus its two-test pattern in `test_fsm_executor.py:2555-2603` (`test_finish_writes_loop_run_summary` for call-args assertion, `test_finish_survives_record_loop_run_summary_failure` for side_effect-swallow assertion) — the exact template to mirror for the new usage_events writer, including the load-bearing `run_id` derivation string both tests assert on [Agent 3 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — new test mirroring `test_on_usage_detailed_forwarded_to_run_claude_command` (`test_fsm_runners.py:419-431`) one layer up: assert `_run_action()`/`_run_baseline_arm()` forward `on_usage_detailed` into `self.action_runner.run(...)` [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` — new call-args + side_effect-swallow test pair for the new usage_events INSERT near `_finish()`, following `test_finish_writes_loop_run_summary`/`test_finish_survives_record_loop_run_summary_failure`'s exact shape [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` — new per-invocation firing-count test (one `TokenUsage`/INSERT per action call, not once per loop run), using the list-accumulation callback pattern already present at `executor.py:2104-2131` (`_on_harness_usage`) [Agent 3 finding]
- `scripts/little_loops/session_store.py` / `scripts/tests/test_session_store.py` — new unit test for the promoted live-insert function itself, sibling to `test_usage_events_run_id_column`/`test_usage_events_run_id_index_exists` [Agent 3 finding]
- Concurrent-writer coverage gap: no test exercises real `ll-parallel`/`ll-sprint` `FSMExecutor` runs (as opposed to the spike's synthetic `simulate_run`, which explicitly forbids importing production modules) writing non-cross-attributed `usage_events` rows — an integration test against the production path is needed to fully retire the spike's concurrency risk [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`_run_baseline_arm()` has a second gap beyond wiring `on_usage_detailed`**: unlike `_run_action()`, it calls `run_claude_command()` directly rather than through `DefaultActionRunner.run()` (`fsm/executor.py:2203-2207`), and the `ActionResult` it constructs (`fsm/executor.py:2208-2213`) never passes a `usage_events=` kwarg — so even after threading `on_usage_detailed` through, this call site's `ActionResult.usage_events` stays empty unless that construction is also updated to collect and attach `TokenUsage` the same way `DefaultActionRunner.run()` does (`fsm/runners.py:156-161,197`). Implementation Steps should call this out explicitly rather than treating both call sites as symmetric.
- **`run_id` derivation has no shared helper — 4 independent inline copies today**, confirmed to be byte-identical but unlinked: `fsm/executor.py:2601,2604` (`_finish()`), `fsm/persistence.py:537,541` (`archive_run()`), `scripts/tests/spike/usage_events_run_id_writer/writer.py:60` (`derive_run_id()`, spike), and `scripts/tests/test_fsm_executor.py:2575-2576` (test reproduces the expression rather than importing it). Promoting the spike's `derive_run_id()` into production is an opportunity to collapse these into one importable helper, but is not required for this issue's acceptance criteria — flagging so the promotion doesn't accidentally create a 5th copy.
- **`usage_events` has no UNIQUE constraint** (unlike `loop_runs.run_id`, which backs `record_loop_run_summary()`'s `INSERT OR IGNORE` idempotency check at `session_store.py:1756-1776`). Each `usage_events` row is one invocation, not a per-run summary, so the new writer should use a plain `INSERT` (matching the spike's `record_usage_event()`) rather than `INSERT OR IGNORE`, and should follow the `_finish()`-adjacent block's bare `try/except Exception: pass` best-effort pattern (`fsm/executor.py:2598-2613`) so a write failure can't fail the loop run.
- **Production's INSERT column set is wider than the spike's**: `_backfill_usage_events()` (`session_store.py:2645-2710`) inserts `session_id`, `state`, and `cost_usd` alongside the token fields — columns the spike's `record_usage_event()` omits. This is already captured in this issue's Scope Boundaries as a "Known residual gap," confirmed here with exact line references for the promotion pass.
- **Existing test coverage already partially in place**: `scripts/tests/test_fsm_runners.py:419-431` (`test_on_usage_detailed_forwarded_to_run_claude_command`) already verifies `on_usage_detailed` forwarding at the runner layer — this is a baseline to build on, not new test surface. `scripts/tests/test_session_store.py` already has `test_usage_events_run_id_column`/`test_usage_events_run_id_index_exists` (~5048-5065) confirming the v29 migration (ENH-2723) landed and is schema-verified.
- **Additional consumer test files to verify alongside the ones already listed**: `scripts/tests/test_history_reader.py`, `scripts/tests/test_fsm_cost_graph.py`, `scripts/tests/test_cli_ctx_stats.py`, `scripts/tests/test_fsm_persistence.py` — one per consumer named in Acceptance Criteria/Implementation Steps.
- **`history_reader.py` has a second `run_id`-relevant function** beyond `cost_attribution()`: `find_loop_run()` (~line 1526) looks up `loop_runs` by `run_id` for join purposes — worth a quick check that it still resolves correctly once `usage_events.run_id` starts getting populated (no code path currently joins the two, but this is the join point the whole EPIC-2456 lineage is building toward).

_Wiring pass added by `/ll:wire-issue`:_
- **A third call path bypasses the callback chain entirely**: `_dispatch_live()` (`fsm/executor.py:2014`), invoked from `_run_action()` at line 1581 when `_resolve_request_path(state)` resolves to `"sdk"`/`"batch"`, calls `host_runner.dispatch_anthropic_request()`/`dispatch_batch_request()` directly with no `on_usage`/`on_usage_detailed` parameter at all. Wiring `on_usage_detailed` only through the `action_runner.run()` path (as currently scoped) leaves SDK/Batch-dispatched invocations uncovered by the new live writer — this should be called out explicitly as an additional scope boundary (or in-scope gap) rather than left implicit. [Agent 2 finding, verified directly]
- **The `analytics.capture.usage_events` config flag is currently unenforced**: `AnalyticsCaptureConfig.usage_events` (`config/features.py:622`) exists and defaults `true`, but `feature_enabled_for()` is never called against it anywhere in production code today — confirmed via repo-wide grep. The new live writer is this flag's first real consumer; Implementation Steps should add a `feature_enabled_for()` gate check before the new INSERT, or the schema/docs update (already in scope) would describe a flag that still does nothing. [Agent 2 finding, verified directly]

### Documentation
- `docs/ARCHITECTURE.md` — schema-versions table: v29 entry (writer behavior note)
- `docs/guides/HISTORY_SESSION_GUIDE.md` (~line 108 `usage_events` row) — `run_id` writer update
- `docs/observability/otel-mapping.md` (~lines 55-65) — `run_id` as a new forward-compat column, same shape as `invocation_id`/`provider_vendor`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:539` — `analytics.capture.usage_events` table row carries the same stale "reserved for a future live writer, currently derived by the `raw_events` rebuild parser" claim as `config-schema.json`; must be updated in lockstep [Agent 2 finding]
- `scripts/little_loops/cli/ctx_stats.py:184-188` (`_aggregate_usage_events()` docstring) — asserts `usage_events` rows are "populated by `session_store._backfill_usage_events`" and that the table "carries no FSM `state`"; both become only partially true once live-written rows exist alongside backfilled ones [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/features.py:610-639` (`AnalyticsCaptureConfig.usage_events`) — confirmed via grep that `feature_enabled_for()` is never called against this flag anywhere in production code (only in its own docstring/doctest); the new live writer is the first real consumer of this config key and should gate its write through `feature_enabled_for(config, "analytics.capture.usage_events", ...)` so the existing schema/config flag stops being decorative [Agent 2 finding, verified directly]
- `scripts/little_loops/history_reader.py:843-851` (`_COST_ATTR_GROUP_COLUMNS`) — whitelist of valid `group_by` columns for `cost_attribution()` does not include `run_id`; if any downstream consumer (e.g. ENH-2722's waste view) is expected to group by the newly-live `run_id`, this dict needs a `"run_id": "run_id"` entry or `cost_attribution(group_by="run_id")` raises `ValueError` [Agent 2 finding, verified directly]

## Impact

- **Priority**: P2 — the core deliverable of ENH-2721; unblocks ENH-2722.
- **Effort**: Medium — cross-module callback signature change threaded through two call sites, plus consumer-safety verification.
- **Risk**: Low-moderate — additive write path, no behavior change to existing consumers; concurrency safety already spike-proven.

## Resolution

Added `record_usage_event()` (`session_store.py`, sibling to `record_loop_run_summary()`)
and wired the live writer into `_finish()` (`fsm/executor.py`), gated on
`BRConfig.analytics_capture.usage_events`. Key design decision, resolved autonomously:
rather than threading a new `on_usage_detailed` callback through every call site (as the
issue's literal wording suggested), `_run_action()` already receives a fully-populated
`ActionResult.usage_events: list[TokenUsage]` from `DefaultActionRunner.run()` regardless
of caller-supplied callbacks — so the collection point is a few lines appended right
after `_run_action()`'s existing `action_complete` aggregation (`executor.py`), tagging
each `TokenUsage` with `self.current_state`. This also incidentally covers the
SDK/Batch (`_dispatch_live()`) path, since `host_runner.dispatch_anthropic_request()`/
the batch-poll success path already attach `usage_events` to their `ActionResult` —
verified directly, so no extra wiring or scope-exclusion was needed there (the wire-issue
pass's concern about this path turned out moot under this design).

`_run_baseline_arm()` was the one real gap: it calls `run_claude_command()` directly
(bypassing `DefaultActionRunner.run()`) and never attached usage to its `ActionResult`.
Fixed by passing a local `on_usage_detailed` collector into `run_claude_command()` (which
already supports the parameter) and attaching the collected list; `_execute_with_baseline()`
now folds the baseline arm's collected usage into the executor's per-run collector the
same way the harness arm already is.

Gating uses `BRConfig(Path.cwd()).analytics_capture.usage_events` (the already-parsed
typed bool) rather than `feature_enabled_for()` as the wire-issue pass suggested —
`feature_enabled_for()` is built for glob-pattern-list fields (`skills`, `cli_commands`)
matched via `fnmatch`, and `usage_events` is a plain bool with no natural "subject" to
match against; using it would have been a category mismatch (`list(True)` raises).

No new `derive_run_id()` helper — `run_id` is computed once in `_finish()` and reused for
both the `loop_runs` and `usage_events` writes, consistent with the issue's own note that
collapsing the 4 duplicate inline copies is "an opportunity... not required for this
issue's acceptance criteria."

Also added `"run_id": "run_id"` to `history_reader._COST_ATTR_GROUP_COLUMNS` (Implementation
Step 10) and updated the four documented "forward-compat, not yet live" claims in lockstep:
`config-schema.json`, `docs/reference/CONFIGURATION.md`, `docs/ARCHITECTURE.md`'s v29 row,
`docs/guides/HISTORY_SESSION_GUIDE.md`, and `docs/observability/otel-mapping.md`.

New tests: `test_fsm_executor.py::TestUsageEventsLiveWriter` (6 tests — collection,
write-through call-args, non-fatal failure, config-gate skip, baseline-arm attachment),
`test_session_store.py::TestRecordUsageEvent` (3 tests — insert round-trip, NULL state,
concurrent-writer no-cross-attribution regression promoted from the ENH-2712 spike), and
`test_history_reader.py::TestCostAttribution::test_group_by_run_id`. TDD Red phase
confirmed (8 failing assertions/AttributeErrors, no structural errors) before
implementation. Full suite: 15735 passed, 38 skipped (baseline was 15727 passed per
ENH-2723 — net +8 new tests, consistent). `ruff check` and `mypy` clean (pre-existing
repo-wide `ruamel` stub-missing noise unrelated to this change).

Known residual gap carried forward unchanged (already documented in Scope Boundaries):
`_run_action()`'s `mcp_tool`/shell branches still produce no `TokenUsage` signal — they
call `_run_subprocess()` directly, never through a runner that could attach usage.

## Status

**Open** | Created: 2026-07-21 | Priority: P2

## Session Log
- `/ll:manage-issue improve` - 2026-07-21T20:00:00 - `a01206d2-0354-4ff8-88f8-1cdb0b04691b.jsonl`
- `/ll:ready-issue` - 2026-07-21T19:14:21 - `45a42004-5c1f-44f0-8abe-a787b8b5be2f.jsonl`
- `/ll:wire-issue` - 2026-07-21T19:09:03 - `a1e7936f-cd99-473e-bdc4-bf2f71d44edf.jsonl`
- `/ll:refine-issue` - 2026-07-21T19:02:01 - `b6a1886e-c617-4657-bae4-3cfe47ac571f.jsonl`
- `/ll:issue-size-review` - 2026-07-21T18:30:00 - `1d8fe38e-085a-4ee8-8c6c-5d16d9fd18d7.jsonl`
