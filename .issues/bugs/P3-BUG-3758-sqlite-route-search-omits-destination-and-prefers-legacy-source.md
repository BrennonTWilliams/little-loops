---
id: BUG-3758
type: BUG
title: SQLite route search omits destination and prefers legacy source
priority: P3
status: done
discovered_by: capture-issue
discovered_date: '2026-10-06'
captured_at: '2026-10-06T09:02:29Z'
completed_at: '2026-10-06T19:43:15Z'
labels:
- telemetry
- transport
- history-db
relates_to:
- BUG-3755
- BUG-3759
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3758: SQLite route search omits destination and prefers legacy source

## Summary

The merged BUG-3755 work already persists both route endpoints in schema v60. The remaining live-producer defect is that route FTS content omits the destination. Also correct defensive compatibility handling: a legacy `state` value currently wins over canonical `from` when an externally supplied payload contains both. In-tree route producers supply `from`/`to` without `state`, so that precedence case is not a production-emitter defect. No further migration is needed.

## Current Behavior

Verified on 2026-10-06 after merge commit `31d2b07fa`:

- `scripts/little_loops/session_store/writers.py`, `SQLiteTransport.send`, stores route `to` in nullable `to_state`. It takes `state` first and falls back to `from` only when `state` is null.
- Route search content joins loop name, source state and event type, excluding `to_state`.
- `scripts/little_loops/session_store/schema.py` is already version 60, with `ALTER TABLE loop_events ADD COLUMN to_state TEXT` in the v60 migration. The manifest and current-version assertions are updated.
- `scripts/tests/test_bug3755_transport_loop_identity.py` already drives a real executor through the event bus and asserts a persisted `work` → `done` route. It does not cover destination search or conflicting source keys.
- `scripts/tests/test_bug3736_usage_replay_holds.py`, `_downgrade_and_remigrate`, already removes the v60 column before replaying v59/v60. No fixture repair remains in this issue.
- `SQLiteTransport.send` is the sole route-row writer. The other loop-row writer, `_backfill_loops`, creates `transition="backfill"` snapshot rows and needs no route fix.

## Expected Behavior

For routes, a non-null canonical `from` takes precedence over legacy `state`; absent/null `from` falls back to `state`. This is an explicit `None` check, not a truthiness check: an empty string is still a supplied source. Missing/null sources and destinations stay SQL NULL; supplied values retain the existing `str(...)` conversion. Both endpoints appear in FTS content for newly received route events. `transition` remains the event type `route`; input events are not mutated.

Append the destination after the existing loop/source/event FTS text: `"<loop> <source> route <destination>"`, omitting only `None` components as today. `search()` matches a literal phrase, so inserting it between the source and `route` would unnecessarily break existing queries such as `work route`. For routes whose selected source is unchanged, that existing phrase must remain searchable.

Non-route rows retain their current state semantics, NULL `to_state`, and search behavior. Loop identity/ref/anchor and `loop_complete` final-status buckets remain intact. Existing structured endpoints and schema v60 remain intact.

## Steps to Reproduce

1. Use a temporary DB and `SQLiteTransport`; send a route with distinct `from`, legacy `state`, and `to` values.
2. Inspect `loop_events`: the destination is stored but the source is the legacy value.
3. Search for a unique destination token: no route result is returned, because destination is absent from route FTS content.
4. Drive a real executor route: its source/target are already stored correctly because the producer has `from`/`to` and no `state`. This isolates the remaining search defect from the synthetic compatibility case.

Use distinct tokens (for example `canonicalsource`, `legacysource`, and `uniquedestination`) so a loop name or another event cannot satisfy the query. With the conflicting payload, the current row has `state=legacysource` and `to_state=uniquedestination`; only the legacy source is searchable.

## Root Cause

`SQLiteTransport.send` applies a legacy-first source fallback and builds FTS text without the destination. The original endpoint-storage defect was repaired by BUG-3755; the issue's prior schema-v59/missing-column claims are outdated.

## Proposed Solution

Change only route source precedence and append the route destination to the FTS content tuple. Within the existing loop-event branch, use:

```python
state = event.get("state")
if event_type == "route":
    source = event.get("from")
    if source is not None:
        state = source
to_state = event.get("to") if event_type == "route" else None
# Retain the existing loop_complete mapping and row-value coercion.
# FTS components: (loop_name, state, event_type, to_state), omitting None.
```

Keep explicit row inserts, event identity handling, the lock, remote/local connection routing, and best-effort sink behavior. Change the content supplied by `SQLiteTransport.send`, not the shared `_index` helper. Reuse the producer-to-sink test module rather than creating a second harness for the same event path.

Both corrections apply only to newly received routes. Existing structured rows and FTS entries are not rewritten: `rebuild()` excludes `loop_events` and the `loop` search kind, and historical repair is outside scope. There is no replay/reindex path that reconstructs route FTS content from stored `loop_events` rows; `_backfill_loops` indexes state snapshots as separate `backfill` events rather than replaying routes. Neither a migration nor a rebuild-derived fingerprint bump is justified; `SQLiteTransport.send` is outside the module-level function graph fingerprinted from `rebuild()`.

## Program Design

### Types

- Existing `loop_events.state: str | None`: route source, canonical non-null `from` then legacy `state`, using the current string conversion.
- Existing `loop_events.to_state: str | None`: route destination, nullable; schema v60 already provides it.
- Existing `transition`: event type, unchanged.

### Signatures

`SQLiteTransport.send(self, event: dict[str, Any]) -> None`

The existing signature stays intact.

### Call Path

`FSMExecutor._emit` → `PersistentExecutor._handle_event` → `EventBus.emit` → `SQLiteTransport.send` → existing structured route row plus `_index` with route FTS text containing both endpoints.

## Implementation Steps

1. Add failing regressions to the existing transport tests: a real `work` → terminal `done` route must be found by destination, and a conflicting synthetic source must use canonical `from` in both storage and search. Keep history and loop paths temporary; close transports in `finally`, including the live `_run_loop` helper if touched.
2. Add a small parameterized writer matrix for absent/null `from` fallback, empty canonical source, absent/null endpoints, and self-transitions. In the empty-source case, supply `from=""` alongside a non-empty unique legacy `state`; assert the stored source is empty and that legacy token is absent from FTS content and search. Without the conflicting value, an incorrect truthiness fallback could pass. Compare the payload before/after `send`. Include a non-route event carrying misleading `from`/`to` keys to prove those keys do not affect its row or FTS text. An extra non-string coercion case is optional if it fits the same matrix; do not add a new harness.
3. Prefer non-null `from` for routes and append `to_state` to the existing FTS components. Keep all changes within `SQLiteTransport.send`.
4. Run the focused tests listed below, then `python -m pytest scripts/tests/`. Update the history guide's full-text search section and API session-store section with the new route contract and the new-writes-only limit. The API section currently labels the schema as 45 in prose and its import example; refresh those two references to the current v60 while touching that section.

### Regression Assertions

- Use public `session_store.search(db, query=...)` for destination and canonical-source queries. For the existing terminal-target live fixture, assert a result with `content=f"{LOOP} work route done"`, `kind="loop"`, the expected `ref` and `.loops/<loop>.yaml` anchor. A nonterminal target may be indexed in `state_enter` and again as the source of a later route; even a result containing `route` can therefore be the wrong transition. Keep the terminal fixture and check exact content instead of adding another live harness.
- Send the conflicting-source synthetic event alone to a fresh DB. Its FTS content must equal `"<loop> canonicalsource route uniquedestination"`, with the expected kind/ref/anchor. The rejected `legacysource` query must return no match; the preferred source and destination must each retrieve the route. Assert structured values via `recent(..., kind="loop")` or SQL separately from FTS results.
- For `from=""` with `state="rejectedemptysource"` in an isolated DB, assert `state=""` in storage and exact FTS content `"<loop>  route <destination>"` (the existing join retains the empty component). Retrieve that content by the unique destination; searching for `rejectedemptysource` returns no match. Do not search for an empty string.
- Verify `work route` still returns the route when the source does not change. Do not pin BM25 scores or rank ordering.
- Verify NULL endpoint cases do not introduce the literal `None` into indexed content. A self-transition keeps both structured endpoints; do not require duplicate FTS tokens or a particular rank.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/writers.py` — route mapping and FTS content only.
- `scripts/tests/test_bug3755_transport_loop_identity.py`, `TestSQLiteTransportLiveLoop` and `_run_loop` — real producer destination-search regression and exception-safe transport cleanup.
- `scripts/tests/test_session_store_writers.py`, `TestSQLiteTransport` — synthetic key precedence in storage and FTS, nulls, empty source, self-transitions and non-route behavior.
- `docs/reference/API.md`, session-store section; `docs/guides/HISTORY_SESSION_GUIDE.md`, full-text search section — both searchable route endpoints for new events, legacy fallback, and historical-search limits.

### Dependent Files

- `scripts/little_loops/session_store/schema.py` and `scripts/little_loops/session_store/schema_manifest.json` — v60 is already sufficient; no edit.
- `scripts/little_loops/session_store/queries.py`, `recent` and `export_history` — existing `SELECT *` projections already return all structured columns; retain existing behavior. `search` matches literal phrases and returns FTS content/identity, not structured route rows.
- `scripts/little_loops/session_store/lifecycle.py` — event-level loop storage/search is not rebuilt; document new-row-only search improvement.
- `scripts/little_loops/session_store/remote_schema.py` — existing exact-version write policy remains unchanged. This fix introduces no additional remote upgrade requirement.

### Focused Validation

`scripts/tests/test_bug3755_transport_loop_identity.py`, `scripts/tests/test_session_store_writers.py`, `scripts/tests/test_session_store_queries.py`, `scripts/tests/test_session_store_schema.py`, `scripts/tests/test_bug3736_usage_replay_holds.py`, `scripts/tests/test_enh3678_rebuild_derive_gate.py`, and `scripts/tests/test_remote_schema.py`. These cover the live producer, writer/search contract, existing migration/replay fixture, rebuild fingerprint boundary, and remote schema policy without adding another transport harness.

## Acceptance Criteria

- [ ] Destination search returns the specific real executor `work` → `done` route with exact FTS content `"<loop> work route done"` and the expected loop kind/ref/anchor. Its structured row remains `state=work`, `to_state=done`, `transition=route`. Existing `work route` phrase search still finds it.
- [ ] An isolated conflicting-source route uses non-null `from` in the row and FTS; both selected endpoints retrieve that route and the rejected legacy source is absent from search. Absent/null `from` falls back to `state`. A separate empty-but-non-null `from` case with a conflicting non-empty legacy `state` stores the empty source, retains the existing empty-component join, and excludes the rejected legacy token from FTS content/search.
- [ ] Missing/null endpoint semantics, self-transitions and input payload equality are covered; existing string conversion is preserved. No literal `None` is added to search content.
- [ ] Non-route state/search behavior and NULL destinations remain unchanged even when `from`/`to` keys are supplied; existing completion-status mapping tests pass.
- [ ] Schema remains v60 with no new migration/manifest or rebuild fingerprint churn; existing migration, replay-hold and endpoint-persistence tests pass. The existing rebuild-fingerprint gate passes unchanged; if it fails because of this fix, investigate and revise the plan instead of bumping the fingerprint to silence it. Neither historical structured rows nor historical FTS entries are rewritten or promised repair.
- [ ] Targeted tests and the full local suite pass; `docs/guides/HISTORY_SESSION_GUIDE.md` and `docs/reference/API.md` describe both searchable endpoints for newly ingested route events and explicitly exclude historical repair.

## Impact

- **Priority**: P3 — optional diagnostic search/legacy-payload correctness.
- **Effort**: Small — writer mapping plus focused regression coverage.
- **Risk**: Low — no schema change; search terms expand for new routes.
- **Breaking Change**: No.

## Review Notes

Reviewed on 2026-10-06. A temporary DB probe stored the destination, selected the conflicting legacy source, and returned zero destination FTS matches. The merged BUG-3755 tests cover endpoint persistence and passed in the 338-test baseline. Opus supported narrowing the remaining scope (consult confidence 0.72). No implementation edits were made. BUG-3755 is completed background context, not an outstanding dependency.

Follow-up review on 2026-10-06 inspected `main` at `fec7d6462` in the repository-root worktree (`.`). Fresh temporary-DB probes reproduced both remaining defects. A separate nonterminal-target probe returned a `state_enter` hit and an outgoing route hit for the destination while the incoming route remained unsearchable, validating the need for exact-content assertions. The focused validation set passed **565 tests**; this is a baseline, not evidence that the pending fix is implemented. Format/design checks passed after correcting the query anchors; no outstanding dependency or proof requirement was found.

`/ll:advise --signal user_requested --host claude-code --model opus` supported proceeding with this bounded writer change (confidence **0.85**). Its main risks were misleading impact claims, incomplete destination search across old runs, phrase-search regression if the destination is inserted mid-content, and accidental fingerprint churn. Incorporated its exact-content test plan, explicit empty-source rule, filename correction, and smaller test scope. Its dissent was that canonical precedence could be dropped because no in-tree producer emits conflicting keys; retain the small defensive correction, but describe that limitation explicitly. Filename-reference search found no references requiring updates. Review verdict: **CORRECTED — ready for implementation**. This review changes only the issue file.

Additional review on 2026-10-06 at `46f696c4b` reproduced the legacy-source selection and missing destination search in a temporary DB. Strengthened the empty-source regression with a conflicting legacy value so it actually rejects truthiness fallback; confirmed that snapshot backfill is the only other loop FTS writer and that no route replay/reindex path needs updating. An Opus consult through `/ll:advise` (`user_requested`, confidence **0.80**) supported these bounded refinements. Its dissent favored optional non-string coercion coverage; retain that option without expanding the required matrix. The shared live/writer/OTel/persistence/query baseline passed **272 tests**; format and evidence checks were clean. This is review evidence, not an implemented fix.

## Related

- BUG-3759 — independent OTel span-lifetime fix. Both issues touch `_run_loop` in `scripts/tests/test_bug3755_transport_loop_identity.py` and separate sections of `docs/reference/API.md`. Whichever is implemented second should incorporate the first issue's edits; neither requires a dependency edge. Keep any new harness options keyword-only with defaults, preserve existing fresh-start callers, and use exception-safe teardown. Coordinate ownership of those shared files if implementation runs concurrently.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| architecture | `docs/reference/API.md` | SQLite transport and search contract. |

## Resolution

- **Action**: fix
- **Completed**: 2026-10-06
- **Changes**: `SQLiteTransport.send` (`scripts/little_loops/session_store/writers.py`) now prefers a non-null `from` over legacy `state` for routes and appends the destination to the route FTS content (`"<loop> <source> route <destination>"`). Regressions added in `test_bug3755_transport_loop_identity.py` (real executor route) and `test_session_store_writers.py` (precedence, empty source, endpoint matrix, non-route). `docs/reference/API.md` and `docs/guides/HISTORY_SESSION_GUIDE.md` updated (API schema references refreshed to v60).
- **Verification**: new tests fail without the fix; full suite 28929 passed, 8 errors in `test_libsql_integration.py::TestLive` (expired live JWT; same 8 errors on the pre-change tree); ruff and mypy clean.

## Status

**Done** | Reviewed: 2026-10-06 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-10-06T19:42:58 - `cb6316ff-ddb6-4617-a26c-5abf85ec662f.jsonl`
- `/ll:ready-issue` - 2026-10-06T19:34:12 - `f0964627-c607-4e44-92f3-bb6e15369944.jsonl`
- `/ll:confidence-check` - 2026-10-06T19:26:49 - `afda5a75-36fd-4868-b330-ef24a018b110.jsonl`
- `/ll:ready-issue` - 2026-10-06T18:18:56 - `471d3a7a-54d3-4495-af46-a12400a91738.jsonl`
- `/ll:capture-issue` - 2026-10-06T09:04:30 - `da8cdf64-7ea1-489f-a22f-62d03c35c5b9.jsonl`
