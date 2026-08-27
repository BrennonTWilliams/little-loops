---
id: ENH-3345
type: ENH
title: Stamp run_id and loop on every emitted FSM event
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T19:56:15Z'
confidence_score: 100
outcome_confidence: 82
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 22
---

# ENH-3345: Stamp run_id and loop on every emitted FSM event

## Summary

`FSMExecutor._emit()` (`scripts/little_loops/fsm/executor.py:3328`) stamps only `event`, `ts`, and the caller-supplied payload. No run-scoped identity is attached: only `loop_start` (`executor.py:484`) carries the `loop` name, and `run_id` is derived *at archive time* in `_finish()` (`executor.py:3686`, `:3711`) from `started_at` + `fsm.name` — never on the wire.

Consequences:

- **Multi-stream consumers cannot correlate.** Concurrent runs each bind their own socket: `_claim_socket_path()` in `scripts/little_loops/transport.py` hands a second producer a `{stem}-{pid}{suffix}` sibling rather than evicting the first (BUG-3324). A consumer that discovers and merges several `.ll/*.sock` streams therefore has no field to key state on. Any realtime multi-run view (dashboard, game-scene visualizer, the "loop-viz" external consumer named in `docs/reference/EVENT-SCHEMA.md`) must infer run identity from socket provenance, which breaks the moment two runs share a sink (`jsonl`, `sqlite`, `webhook`, `otel` are all single-file/single-endpoint).
- **Single-sink transports interleave irrecoverably.** Two concurrent runs writing `.ll/events.jsonl` or `.ll/history.db` via `SQLiteTransport` produce a stream that cannot be de-interleaved after the fact.
- **Downstream tooling re-derives what the executor already knows.** `debug-loop-run`, `audit-loop-run`, and `ll-session`/`history.db` queries reconstruct run scoping by inference instead of reading a field.

Proposed change: compute `run_id` once at executor construction (same derivation as `_finish()` uses today, so archive rows and live events agree) and have `_emit()` stamp `run_id` and `loop` onto every event alongside `event`/`ts`. Purely additive — existing consumers that ignore unknown keys are unaffected, and `LLEvent.from_dict()` folds the new keys into `payload` without change.

Scope note: `parallel.*` and `issue.*` emitters build their dicts inline rather than going through `_emit()`, so they need the same treatment or an explicit decision to leave them run-less. Sibling issue covers the `parallel.*` surface.

Acceptance: every event observed on the bus during a loop run carries a non-empty `run_id` and `loop` — including `loop_resume`, and including both segments of a paused-and-resumed run, which must share one `run_id`; two concurrent runs of *different loops* (or same loop, different second — see the documented same-second collision limitation) writing one `events.jsonl` can be fully separated by `run_id`; `docs/reference/EVENT-SCHEMA.md` documents both fields in the wire-format table; `docs/reference/schemas/` regenerated via `ll-generate-schemas`.


## Current Behavior

`FSMExecutor._emit()` (`scripts/little_loops/fsm/executor.py:3328`) stamps only `event`, `ts`, and the caller-supplied payload — no run identity. `loop` is emitted exactly once, on `loop_start` (`executor.py:494`), by the caller passing it in the payload rather than by `_emit()` itself. `run_id` is never put on the wire at all; it's derived twice, independently, inside `_finish()` (`executor.py:3686` and `:3711`) purely for archive rows (`loop_runs`, `usage_events`), from `self.started_at.replace(":", "").replace(".", "").replace("+", "")[:17]` + `"-" + self.fsm.name`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- Correction: `loop` is currently stamped at **two** `_emit()` call sites in `executor.py`, not one — `loop_start` (`:484`) and the ENH-2486 prompt-size guard's `PROMPT_SIZE_WARN_EVENT` emission (`:2161`, `{"loop": self.fsm.name, "state": ..., "size": ..., "threshold": ..., "est_tokens": ...}`). Confirmed via `grep '"loop": self.fsm.name'` returning exactly these two lines.
- `cli/action.py`'s `_emit()` (module-level function, `:175-176`, `print(json.dumps(event), flush=True)`) and `state.py`'s `StateManager._emit()` (method, `:109-112`, calls `self._event_bus.emit(...)` directly) are **independently-implemented `_emit` functions**, not callers of `FSMExecutor._emit()` — they share only the conventional `event`/`ts` dict shape and, for `StateManager`, the same `EventBus.emit()` sink. A change scoped to `FSMExecutor._emit()` does not reach either of them.
- The `run_id` derivation formula (`.replace(":", "").replace(".", "").replace("+", "")[:17]`) is duplicated at **three** sites total, not two: `executor.py:3686` and `:3711` (as the issue states) plus `persistence.py:611` in `archive_run()` (applied to `state.started_at`) and a fourth near-identical instance at `persistence.py:782-786` inside an artifact-promotion helper (`promote_run_artifact`), which additionally falls back to `datetime.now(UTC).strftime(...)` when `started_at` is falsy.

## Expected Behavior

Every event emitted via `_emit()` during a run — `loop_start` through `loop_complete` — carries non-empty `run_id` and `loop` fields, computed once and reused for the whole run. Two concurrent runs writing to one `events.jsonl` (or any other single-sink transport) can be split back into per-run streams by grouping on `run_id` alone, with no socket-provenance inference required.

## Motivation

Multi-run observability is currently unreliable: `_claim_socket_path()` (`scripts/little_loops/transport.py`) hands a second concurrent producer a `{stem}-{pid}{suffix}` sibling instead of evicting the first (BUG-3324), so a consumer merging several `.ll/*.sock` streams has no field to key state on, and single-file sinks (`jsonl`, `sqlite`, `webhook`, `otel`) interleave two runs irrecoverably. `debug-loop-run`, `audit-loop-run`, and `ll-session`/`history.db` queries all re-derive run scoping by inference today instead of reading a field the executor already computes at `_finish()` time. Stamping the wire format closes that gap for the cost of two dict keys per event.

## Proposed Solution

Compute `run_id` once, right after `self.started_at = _iso_now()` is set at the top of `FSMExecutor.run()` (`executor.py:481`), using the same derivation `_finish()` already uses (`started_at` digits + `-` + `fsm.name`), and store it as `self.run_id`. Change `_emit()` (`executor.py:3327-3334`) to always merge `run_id` and `loop` into the payload:

```python
def _emit(self, event: str, data: dict[str, Any]) -> None:
    self.event_callback(
        {
            "event": event,
            "ts": _iso_now(),
            "run_id": self.run_id,
            "loop": self.fsm.name,
            **data,
        }
    )
```

Then replace both inline derivations in `_finish()` (`:3686`, `:3711`) with reads of `self.run_id` so archive rows and live events agree by construction instead of by duplicated formula. This is purely additive on the wire: `LLEvent.from_dict()` (`scripts/little_loops/events.py:54`) folds unknown top-level keys into `payload`, so existing consumers that don't know about `run_id`/`loop` are unaffected, and the existing `loop_start`-supplied `loop` key becomes a harmless duplicate that can be dropped from that call site.

Out of scope: `parallel.*` and `issue.*` event emitters build their dicts inline rather than going through `_emit()`, so they need the same treatment or an explicit decision to leave them run-less — tracked separately (see Scope Boundaries).

### Pre-Implementation Review Findings

_Added by pre-implementation review — 2026-08-27 — verified against code:_

1. **Resume path splits one logical run into two `run_id`s — must be guarded.** `PersistentExecutor.resume()` restores `self._executor.started_at = state.started_at` (`persistence.py:1276`), then calls `self.run(clear_previous=False)` → `FSMExecutor.run()`, which unconditionally clobbers it via `self.started_at = _iso_now()` (`executor.py:481`). If `run_id` is computed there naively, a paused-and-resumed run emits its pre-pause segment under one `run_id` and its post-resume segment under another — defeating correlation for exactly the long-running loops most likely to be watched. **Decision: `run()` sets `started_at`/`run_id` only when `self.started_at` is still `""`** (preserving the restored value on resume), so both segments share one `run_id` and archive rows keyed on `started_at` stay consistent. Add a resume test asserting `run_id` stability across the pause/resume boundary.
2. **`loop_resume` bypasses `_emit()` and would violate acceptance.** It's built inline in `persistence.py:1309-1320` and emitted straight onto the bus mid-run — it would carry `loop` but never `run_id`. **Decision: stamp `run_id` on it in `resume()`**, derived from the just-restored `state.started_at` with the same formula (or by reading `self._executor.run_id` if the restore order makes it available). During implementation, grep for any other `event_bus.emit(`/`append_event(` call sites in `persistence.py` that emit run-scoped events outside `_emit()` and give them the same treatment.
3. **Same-second collision is a known, accepted limitation.** The derivation truncates to second precision (`[:17]`), so two concurrent runs of the *same loop* started in the same second get identical `run_id`s, while acceptance promises separability. This collision already exists in archive-folder naming (`.history/<run_id>-<loop>`); changing the formula would desync folder names and the three `persistence.py` derivation copies. **Decision: keep the formula, document the limitation in EVENT-SCHEMA.md**, and make the concurrent-runs integration test use two different loop names deliberately.
4. **Initialize `self.run_id = ""` in `__init__`** alongside `started_at` (`executor.py:258`) — tests like `test_finish_writes_loop_run_summary` call `_finish()` without `run()`, and a `run()`-only attribute would raise `AttributeError`. Mirrors the existing `started_at` init/assign pattern.
5. **Both explicit `loop` call sites get cleaned up, not just one.** Implementation Step 2's "drop the now-redundant `loop` key" applies to `loop_start` (`:484`) *and* the `PROMPT_SIZE_WARN_EVENT` emission (`:2161`) — the two sites the research findings already identified.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- No existing "compute once at construction/run-start" eager pattern exists for a chokepoint-injected field: `_emit()` (`executor.py:3328-3336`) today only injects `event` (param) and `ts` (freshly computed via `_iso_now()` each call) — never a pre-computed `self.*` value. The dominant "compute once, reuse" idiom in this file is lazy memoization (`_get_br_config()` at `:2429`, `self._prepatch_check_memo` in `__init__`), not eager assignment. The closest eager single-assignment analogue is `self.started_at` itself (`""` default in `__init__` at `:258`, single assignment in `run()` at `:481`) — the issue's proposed `self.run_id` shape should model on `started_at`, not the lazy-memo idiom.
- `loop` is currently supplied per-call-site by the caller (`"loop": self.fsm.name` at `:484` and `:2161`), not injected centrally — this is the only existing precedent for how a run-scoped field has been introduced into events so far, and it's the opposite of chokepoint injection.
- A chokepoint-style stamped field does exist, but at the sub-loop forwarding layer, not `_emit()`: `_sub_event_callback` (`:1002-1011`) conditionally injects `depth` (`if "depth" not in event`) when relaying child events to the parent's `event_callback`, and `self._depth` is propagated onto the child executor via direct attribute assignment (`child_executor._depth = depth`). This is the nearest structural precedent for "wrap emission to inject a field on every event," useful context for the sub-loop `run_id`/`loop` emergent-behavior question already flagged in the Integration Map.
- Confirmed a fourth (not just three) inline copy of the run_id derivation formula: `persistence.py:782-786` (`promote_run_artifact()`) duplicates the same `.replace(":", "").replace(".", "").replace("+", "")[:17]` transform, with an added `datetime.now(UTC)` fallback when `started_at` is falsy — no shared helper wraps this formula anywhere in the codebase today.
- Closest test precedent confirmed: `test_event_includes_timestamp` (`test_fsm_executor.py:2355-2372`) collects events via `event_callback=events.append`, then iterates asserting key presence — no dict-equality/exact-key-set test exists anywhere against `FSMExecutor`-emitted events. `test_sub_loop_events_forwarded_to_parent_callback`/`test_sub_loop_depth_propagates_to_nested_sub_loops` (`:6495`, `:6522`) show the "filter events by `.get(field) == value`" idiom for a stamped identity field — the shape the new `run_id`/`loop` presence and stability tests should follow.
- `docs/reference/EVENT-SCHEMA.md`'s Wire Format table (`:11-27`) currently documents only `event`/`ts` as universal envelope keys; `loop` is documented per-event-type today (e.g. `loop_start`'s own table). `generate_schemas.py`'s `_BASE_PROPS`/`_BASE_REQUIRED` (`:25-30`) is the single merge point every event schema goes through (`additionalProperties: True` unconditionally) — confirms `run_id`/`loop` belong in `_BASE_PROPS`, not per-type `extra_props`, matching the Integration Map's existing wiring note.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — init `self.run_id = ""` in `__init__` (`:258` area), guarded `started_at`/`run_id` assignment in `run()` (`:481` area), update `_emit()` (`:3327`), update the two inline derivations in `_finish()` (`:3686`, `:3711`)
- `scripts/little_loops/fsm/persistence.py` — stamp `run_id` on the inline `loop_resume` event in `resume()` (`:1309-1320`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/events.py` (`LLEvent.from_dict()`, `:54`) — already forward-compatible, no change required, but is the consumer contract this issue relies on
- Transports under `scripts/little_loops/transport.py` and any registered sinks (`jsonl`, `sqlite`, `webhook`, `otel`) — pass events through unchanged; no code change expected, but they're the consumers this issue is meant to unblock

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` `_call_sub_loop` (~`:1013`) — constructs a second, independent `FSMExecutor` (`child_executor`) with its own `run()`/`started_at`/`run_id`. Once `_emit()` stamps `run_id`/`loop`, sub-loop events forwarded to the parent via `_sub_event_callback` (`:1005-1011`) will carry the **child's own** `run_id`/`loop`, not the parent's, distinguishable only by the existing `depth` field. Emergent behavior of this change (today nothing diverges since neither field is stamped) — confirm this is intended before shipping; covered by a new test below. [Agent 2 finding]
- `scripts/little_loops/fsm/persistence.py` `PersistentExecutor` — has **no existing `.run_id` property** (only `_on_event` at `:964`); currently reaches the live executor's `run_id`/`started_at` via `self._executor`. No change required by this issue's stated scope, but any future caller wanting `PersistentExecutor.run_id` would need one added. [Agent 1 finding]
- `scripts/little_loops/generate_schemas.py` shared `_schema()` builder (`:57-74`) sets `"additionalProperties": True` (`:73`) for every event schema — confirms the wire-format change is validator-safe even before regeneration. [Agent 2 finding]

### Similar Patterns
- `scripts/little_loops/fsm/persistence.py::archive_run` — the run_id derivation this issue's `self.run_id` must continue to match, so archived rows still JOIN cleanly

### Tests
- `scripts/tests/` FSM executor event-emission tests — add assertions that `run_id` and `loop` are present and non-empty on every emitted event, and that `run_id` is stable across all events within one run

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py::test_event_includes_timestamp` (`~:2355`) — closest template for a new presence test: collects `events` via `event_callback=events.append`, then `for event in events: assert "ts" in event`. Mirror for `run_id`/`loop`. [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py::test_sub_loop_events_forwarded_to_parent_callback` (`~:6495`) and `::test_sub_loop_depth_propagates_to_nested_sub_loops` (`~:6522`) — extend to assert whether forwarded sub-loop events carry the child's own `run_id`/`loop` or the parent's (see the `_call_sub_loop` emergent-behavior note above); no existing test covers this dimension. [Agent 2 + 3 finding]
- New test: run_id-stability across one run (`len({e["run_id"] for e in events}) == 1`) — no existing helper/precedent for this exact shape; model on `test_event_includes_timestamp`. [Agent 3 finding]
- New test: run_id-stability across a pause/resume boundary — pre-pause and post-resume events (including the stamped `loop_resume`) share one `run_id` (Review Findings 1–2); model on existing `PersistentExecutor.resume()` tests in `test_fsm_persistence.py`. [Review finding]
- New integration test: two concurrent runs writing interleaved events into one shared `events.jsonl`, split cleanly by `run_id` (Implementation Step 6's verify requirement) — net-new; nearest but insufficient precedent is `test_multiple_archive_runs_coexist` (`test_fsm_persistence.py:646`), which is sequential, not concurrent. [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py::test_finish_writes_loop_run_summary` (`:3082-3110`) and `::test_finish_writes_usage_events` (`:3167-3200`) — both independently recompute the run_id formula inline and assert it against `kwargs["run_id"]`; won't break (same formula, same value) but should be updated to assert against `executor.run_id` directly to lock in the centralization. [Agent 1 + 3 finding]
- `scripts/tests/test_fsm_executor.py::test_warn_emitted_above_threshold` (`:155-170`) — asserts `warns[0]["loop"] == "psg-test"` value-based, not mechanism-based; confirmed it will NOT break when the explicit `"loop"` key is dropped from the `PROMPT_SIZE_WARN_EVENT` call site per Implementation Step 2. [Agent 3 finding]
- `scripts/tests/test_fsm_persistence.py::test_archive_run_run_id_from_started_at` (`:556-568`) — asserts a *separate* copy of the run_id formula baked into `persistence.py:611`; not touched by this issue's stated file-change list (executor.py only), so it will not break unless a future pass also centralizes the `persistence.py` sites onto `FSMExecutor.run_id`. [Agent 1 + 3 finding]

### Documentation
- `docs/reference/EVENT-SCHEMA.md` — document `run_id` and `loop` in the wire-format table
- `docs/reference/schemas/` — regenerate via `ll-generate-schemas` per the issue's stated acceptance criteria

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md` "Wire Format" section (`:11-27`) — currently documents only `event`/`ts` as universal envelope keys; add `run_id`/`loop` here as universal fields, not payload-specific ones. [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md` per-event-type field tables for `loop_start` (`:128`), `prompt_size_warn` (`:515`), and `loop_resume` (`:912`) — each already lists `loop` as a payload-specific field; reconcile with the new universal-field documentation so it isn't duplicated/contradicted. `:132`'s example `loop_start` payload also needs `run_id` added. [Agent 1 + 2 finding]
- `scripts/little_loops/generate_schemas.py` shared `_BASE_PROPERTIES`/`_BASE_REQUIRED` (`:25-30`) — natural touch point for `run_id`/`loop` since they're universal envelope fields, not a single event type's payload; changes the CONTRIBUTING.md maintenance procedure's step 2 from a per-type `extra_props` edit to a shared-schema edit, and regeneration then touches all ~42 committed schema files under `docs/reference/schemas/`, not just one. [Agent 2 finding]
- `docs/observability/otel-mapping.md:65-66,76` — documents `usage_events.run_id` (archive-time, via `record_usage_event()`) and lists `run_id` as a `cost_attribution()` `group_by` value; distinct from the new live-wire field but worth a note to avoid conflating the two `run_id` concepts. No prose change required since the archive-time value and call site are unchanged. [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- `scripts/little_loops/fsm/persistence.py:611` (`PersistentExecutor.archive_run()`) and `scripts/little_loops/fsm/persistence.py:782-786` (`promote_run_artifact()`) carry independent copies of the same `run_id` derivation formula this issue centralizes in `executor.py`. Out of this issue's stated scope (only `_finish()`'s two sites are named), but worth a maintainer decision: leave them deriving in parallel (they must keep matching `self.run_id`'s formula for archive rows to JOIN, per the existing `persistence.py::archive_run` comment this issue already cites), or have them read the now-canonical `self.run_id` where a live `FSMExecutor` instance is in scope.
- `EventBus.emit()` (`scripts/little_loops/events.py:117-138`) does no key filtering: it reads `event.get("event", "")` only to match observer filter globs, then passes the entire unmodified dict to every observer and transport. `LLEvent.from_dict()` (`events.py:54-62`) pops only `event`/`type` and `ts`/`timestamp`; every other key (including the new `run_id`/`loop`) lands in `payload`. Both claims in the Proposed Solution are confirmed exactly as stated — no special-casing needed.
- `cli/action.py`'s `_emit()` (`:175-176`) and `state.py`'s `StateManager._emit()` (`:109-112`) are independently-implemented `_emit` functions that do not call `FSMExecutor._emit()` — they are unaffected by this change and do not need updating.
- No test in `scripts/tests/` does exact dict-equality or exact key-set comparison against a `FSMExecutor`-emitted event (`event == {...}`, `set(event.keys()) == {...}` all return zero matches) — the closest is `test_fsm_executor.py:7787-7839`'s subset check (`missing = expected_keys - event.keys()`), which tolerates additional keys. Adding `run_id`/`loop` will not break existing assertions.
- Closest existing precedent for testing a stamped identity field across many/nested events: `test_sub_loop_events_forwarded_to_parent_callback` (`test_fsm_executor.py:6495`) and `test_sub_loop_depth_propagates_to_nested_sub_loops` (`:6522`), which assert on a `depth` key forwarded onto sub-loop events — same "field stamped on every event, verify via `[e for e in events if e.get(...) == ...]`" shape this issue's new tests should follow. `test_event_includes_timestamp` (same file) is the closest template for "assert a field is present and stable across all events."
- Event-schema doc-update workflow is documented at `CONTRIBUTING.md` § "Event Schema Maintenance" (lines 784-800): edit `docs/reference/EVENT-SCHEMA.md` first, then `SCHEMA_DEFINITIONS` in `scripts/little_loops/generate_schemas.py`, then run `ll-generate-schemas` (never hand-edit the generated `.json` files).
- `parallel.*` (e.g. `orchestrator.py:1285`, `parallel.worker_completed`) and `issue.*` (e.g. `issue_lifecycle.py:1491`, `issue.started`) emitters build event dicts standalone at each call site — there is no shared chokepoint analogous to `FSMExecutor._emit()` in those modules, confirming the issue's Scope Boundaries note that they need separate treatment (sibling issue ENH-3346).

## Program Design

### Types

- `FSMExecutor.run_id: str` (new instance attribute; initialized to `""` in `__init__` mirroring `started_at`, assigned in `run()` only when `started_at` is still empty — see Pre-Implementation Review Finding 1/4)

### Signatures

- `FSMExecutor._emit(self, event: str, data: dict[str, Any]) -> None` (existing, modified to stamp `run_id` and `loop`)

### Call Path

`FSMExecutor.run()` (sets `self.started_at`, then `self.run_id`) -> `FSMExecutor._emit()` (stamps `run_id`/`loop` on every call site, e.g. `loop_start` at `:494`, `loop_complete` at `:3675`) -> `self.event_callback` -> registered transports (`jsonl`/`sqlite`/`webhook`/`otel`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- No existing "compute once at construction/run-start, store on self, read everywhere" idiom is present in `executor.py` for an eager, run-once value. The closest analogues are both lazy-memoized accessors: `_get_br_config()` (`:2429`, backed by `self._br_config: BRConfig | None = None` set in `__init__`) and the `_prepatch_check_memo` dict (`__init__`, `:263-266`). This issue's proposed shape — assign `self.run_id` eagerly in `run()` rather than lazily on first access — has no exact prior instance in this file; it is closer to how `self.started_at` itself is already set (`run()` line 481, single assignment, no lazy accessor).
- Confirmed: `self.fsm` is assigned exactly once, in `__init__` (`:234`), never reassigned; `FSMLoop.name: str` (`schema.py:1382`, dataclass field on the class at `:1360`) is a required, non-mutated string. `fsm.name` is therefore stable for the executor's whole lifetime and is already read at execution time at `executor.py:826, 3044, 2161, 3299, 3689, 3690, 3717, 3787` — safe to reuse for `self.run_id` and the `loop` stamp.
- Confirmed: `self.started_at` is initialized to `""` in `__init__` (`:258`) and set exactly once, in `run()` at `:481` (`self.started_at = _iso_now()`); no other assignment site exists. Every `self._emit(...)` call site in `executor.py` occurs after line 481 in the call graph — `loop_start` (`:484`) is the first emission and fires immediately after `started_at` is set, so `started_at` is never empty at emission time during a real `run()`.

## Implementation Steps

1. Initialize `self.run_id = ""` in `__init__` (`executor.py:258` area); in `FSMExecutor.run()`, set `started_at` and `run_id` **only when `self.started_at` is still `""`** (resume guard — preserves the value restored by `PersistentExecutor.resume()` at `persistence.py:1276`), reusing `_finish()`'s existing derivation
2. Update `_emit()` to merge `run_id` and `loop` into every event payload; drop the now-redundant `loop` key from both explicit call sites — `loop_start` (`:484`) and `PROMPT_SIZE_WARN_EVENT` (`:2161`)
3. Replace the two inline `run_id` derivations in `_finish()` with reads of `self.run_id`
4. Stamp `run_id` on the inline `loop_resume` event in `PersistentExecutor.resume()` (`persistence.py:1309-1320`); grep `persistence.py` for other run-scoped `event_bus.emit()`/`append_event()` sites bypassing `_emit()` and treat them the same
5. Add/extend executor tests asserting `run_id`/`loop` presence and stability across a run's events, including stability across a pause/resume boundary
6. Update `docs/reference/EVENT-SCHEMA.md` (including the documented same-second same-loop collision limitation) and regenerate `docs/reference/schemas/` via `ll-generate-schemas`
7. Verify: emit two concurrent runs (different loop names — see Review Finding 3) to one `events.jsonl` and confirm they split cleanly by `run_id`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Confirm/decide sub-loop `run_id`/`loop` behavior: `_call_sub_loop`'s child `FSMExecutor` (`executor.py` ~`:1013`) will stamp its own `run_id`/`loop` on events forwarded to the parent via `_sub_event_callback` — decide if this is intended (distinguishable today only by the existing `depth` field) and add a test asserting the chosen behavior.
- Update `test_finish_writes_loop_run_summary` and `test_finish_writes_usage_events` (`test_fsm_executor.py:3082`, `:3167`) to assert against `executor.run_id` instead of re-deriving the formula inline.
- Update `docs/reference/EVENT-SCHEMA.md`'s Wire Format section (`:11-27`) to list `run_id`/`loop` as universal envelope fields, and reconcile the `loop_start`/`prompt_size_warn`/`loop_resume` per-type tables (`:128`, `:515`, `:912`) that currently list `loop` as payload-specific.
- Update `scripts/little_loops/generate_schemas.py`'s shared `_BASE_PROPERTIES`/`_BASE_REQUIRED` (`:25-30`) rather than per-type `extra_props`, then regenerate all `docs/reference/schemas/*.json` via `ll-generate-schemas`.
- Add new tests: run_id/loop presence-on-every-event (model: `test_event_includes_timestamp`), run_id-stability-across-one-run, and a two-concurrent-runs-one-shared-`events.jsonl` integration test.

## Impact

- **Priority**: P2 - Correctness/observability gap affecting any multi-run consumer (dashboards, loop-viz, history.db queries); not user-blocking but actively undermines a stated capability (BUG-3324's multi-stream scenario)
- **Effort**: Small - Confined to `_emit()`, one new instance attribute in `run()`, and two call-site edits in `_finish()`; no new dependencies or schema migrations
- **Risk**: Low - Purely additive wire fields; `LLEvent.from_dict()` already folds unknown keys into `payload`, so no consumer can break from two new keys appearing
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-27 | Priority: P2

## Success Metrics

Every event in a captured `events.jsonl` from a test run has non-empty `run_id` and `loop`. Two concurrent loop runs writing to one `events.jsonl` can be split into exactly two disjoint per-run event sequences by grouping on `run_id`, with zero cross-run leakage.

## Scope Boundaries

Out of scope: retrofitting `parallel.*` and `issue.*` emitters that build event dicts inline rather than through `_emit()` — that's the sibling issue ENH-3346. Out of scope: fixing `_claim_socket_path()`'s socket-eviction behavior for concurrent producers (BUG-3324) — this issue only makes concurrent runs *distinguishable* on shared sinks, not resolves socket contention. Out of scope: backfilling `run_id` onto already-archived historical events. Out of scope: changing the `run_id` derivation formula to disambiguate same-loop same-second concurrent starts — accepted as a documented limitation (Review Finding 3) since changing it would desync `.history/<run_id>-<loop>` folder names and the `persistence.py` derivation copies.

## API/Interface

```python
# New wire fields on every FSMExecutor-emitted event (additive, non-breaking):
{"event": "...", "ts": "...", "run_id": "20260827T195651-my-loop", "loop": "my-loop", ...}
```


## Session Log
- `/ll:confidence-check` - 2026-08-27T21:18:15 - `086de69c-22b2-41be-878d-e9a1dd904924.jsonl`
- `/ll:decide-issue` - 2026-08-27T21:03:09 - `afdc9a20-86de-4e24-ad07-3b472050429a.jsonl`
- `/ll:refine-issue` - 2026-08-27T21:02:35 - `3300bae1-29e4-43aa-be1f-dbf44d0ba9ec.jsonl`
- `/ll:wire-issue` - 2026-08-27T20:56:26 - `90bd9242-a8e8-4a44-9297-fb97e2e007d7.jsonl`
- `/ll:refine-issue` - 2026-08-27T20:08:12 - `6a48b0c1-bff7-4c66-a42d-e3b6acefc1f6.jsonl`
- `/ll:format-issue` - 2026-08-27T19:59:35 - `278ef87b-9267-47eb-b438-15c48011237e.jsonl`
- `/ll:capture-issue` - 2026-08-27T19:56:51 - `f1d9d0f2-280e-4e9e-bb4a-45c14f878f7b.jsonl`
