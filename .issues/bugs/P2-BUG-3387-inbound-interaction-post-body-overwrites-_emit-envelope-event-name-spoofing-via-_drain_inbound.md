---
id: BUG-3387
type: BUG
title: inbound interaction POST body overwrites _emit() envelope (event name spoofing
  via _drain_inbound)
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-04'
captured_at: '2026-09-04T20:40:10Z'
completed_at: '2026-09-05T04:58:09Z'
labels:
- fsm
- security
- serve
- events
decision_needed: false
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 81
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
relates_to:
- FEAT-3384
---

# BUG-3387: inbound interaction POST body overwrites _emit() envelope (event name spoofing via _drain_inbound)

## Summary

`FSMExecutor._drain_inbound()` re-emits every `POST /{token}/interaction` body via `self._emit("artifact_interaction", event)`. `_emit()` builds the envelope as `{"event": name, "ts": ..., "run_id": ..., "loop": ..., **data}` with the payload spread last, so any key in the POST body overwrites the envelope. A body containing `"event": "loop_complete"` (or any other name) is delivered to every observer and transport under that name, with attacker-chosen `ts`/`run_id`/`loop`. Found during the FEAT-3384 second review (2026-09-04).

## Current Behavior

- `scripts/little_loops/fsm/executor.py:549-565` — `_drain_inbound()` calls `self._emit("artifact_interaction", event)` with the raw parsed body.
- `scripts/little_loops/fsm/executor.py:3581-3591` — `_emit()` merges `**data` after the fixed envelope keys, so `data["event"]`, `data["ts"]`, `data["run_id"]`, `data["loop"]` all win.
- `scripts/little_loops/transport.py:691-715` — `LocalBridgeTransport._handle_interaction()` accepts any dict JSON body and `put_nowait()`s it unchanged.
- Consequence: under `ll-loop run --serve`, anyone who can reach the loopback bridge with the token can inject arbitrary event names into the run's `events.jsonl` (via `PersistentExecutor._handle_event` → `persistence.append_event`), into every transport (JSONL, Unix socket, webhooks, SSE), and into every extension observer. `_handle_event` also acts on some names (`state_enter`/`loop_complete`/`baseline_complete` trigger `_save_state()`; `evaluate` overwrites `_last_result`; `handoff_detected` sets the continuation prompt), so a spoofed body can mutate executor persistence state, not just the log.

## Expected Behavior

Inbound bodies never overwrite the envelope. `_drain_inbound()` should emit `artifact_interaction` with the body nested (e.g. under a `payload` key) or with the four envelope keys stripped/renamed before the spread. FEAT-3384 adds a separate whitelisted `human_response` branch (`alert_id`, `verdict`, `edited_text`, `reason`); this bug covers the default `artifact_interaction` path and any future inbound source.

## Proposed Solution

- In `_drain_inbound()`, strip `event`/`ts`/`run_id`/`loop`/`depth` from the body before spreading it into `self._emit("artifact_interaction", ...)` (per Decision Rationale below: Option B) — and keep appending the raw item to `inbound_events`.
- `depth` is executor-owned too: sub-loop event forwarding (`scripts/little_loops/fsm/executor.py:~1170`, `_sub_event_callback`) only injects `depth` when the event lacks it (`if "depth" not in event`), so a body carrying `"depth": 0` posted while a sub-loop is running masquerades as a parent-level event. Strip it alongside the four `_emit()` envelope keys.
- Log one warning line naming the stripped keys when any are removed (mirrors `LocalBridgeTransport._record_inbound_drop` at the transport layer) so spoof attempts are visible in the run log rather than silently normalised.
- Consider making `_emit()` itself defensive: build the dict as `{**data, "event": event, "ts": ..., "run_id": ..., "loop": ...}` so no caller can clobber the envelope. Audit existing `_emit()` callers for any that intentionally pass `event`/`ts`/`run_id`/`loop` in `data` first.
- Add a test in `scripts/tests/test_fsm_executor.py` next to the existing `_drain_inbound` tests asserting a body with `event`/`run_id`/`loop`/`ts` keys cannot change the emitted envelope.
- Coordinate with FEAT-3384 (its `_drain_inbound()` `human_response` branch already builds a whitelisted payload) so the two changes land compatibly.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

**Option A**: Nest the raw inbound body under a new `payload` key — `self._emit("artifact_interaction", {"payload": event})` (the first bullet above).

**Option B**: Strip/rename the four envelope keys (`event`, `ts`, `run_id`, `loop`) from the body before spreading it, leaving every other body key — including `artifact_id`/`level`/`action` — at top level (the second alternative in the first bullet above).

> **Selected:** Option B — strips the four envelope keys while preserving the documented/schema-registered top-level `artifact_id`/`level`/`action` contract and the dashboard's existing emitter shape.

**Recommended**: Option B — the `artifact_interaction` payload contract is documented (`docs/reference/EVENT-SCHEMA.md:1770`, `docs/reference/ARTIFACT_CONTROL_LEVELS.md:73-89`) and schema-registered (`scripts/little_loops/observability/schema.py:376-388`, `ArtifactInteractionVariant`) as top-level `artifact_id`/`level`/`action` fields composing with the envelope, and the built-in `--serve` dashboard's "Send" control (`scripts/little_loops/templates/dashboard.llat/template.html.j2:379-397`) already POSTs exactly that shape. Option A would move those fields under `event.payload.*`, breaking this documented/registered contract and the dashboard's own emitter; Option B closes the spoofing hole without any consumer/schema change. See Program Design → Codebase Research Findings for the full grep evidence.

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

**Correction — FEAT-3384 coordination claim (remediation pass, 2026-09-04)**
- The "Coordinate with FEAT-3384" bullet above states its `_drain_inbound()` `human_response` branch "already builds a whitelisted payload." As of this remediation pass, that is not accurate: FEAT-3384 (`.issues/features/P3-FEAT-3384-eventbus-hitl-adapter.md`) is `status: open` — unimplemented — and `human_response` appears nowhere in `scripts/little_loops/fsm/executor.py`; it exists only as the unused string constant `HUMAN_RESPONSE_EVENT` at `scripts/little_loops/fsm/communication_adapter.py:19`. The bullet describes FEAT-3384's *planned* branch, not present code.
- Corrected coordination requirement: this bug's Option B fix (stripping `event`/`ts`/`run_id`/`loop` from the body in `_drain_inbound()` before the spread) does not depend on FEAT-3384 landing first and can be implemented independently. The dependency runs the other way — whichever `human_response` branch FEAT-3384 eventually adds to `_drain_inbound()` must be built on top of this bug's stripped-envelope handling (or replicate the same stripping for its own branch), not the reverse. This is a coordination/ordering note, not a blocking prerequisite: `relates_to: FEAT-3384` has been added to this issue's frontmatter (bidirectional with FEAT-3384's existing `relates_to: [BUG-3387]`), not `blocked_by`.
- Ordering check: if FEAT-3384 lands first and adds a `human_response` branch inside `_drain_inbound()` without also stripping the four envelope keys from its own whitelisted fields, the same spoofing hole this bug fixes could reopen on that new branch — the FEAT-3384 implementer should re-check this bug's Decision Rules (`## Program Design → Decision Rules`) before adding that branch.

**Scope clarification — `_emit()` defensive-reorder bullet (remediation pass, 2026-09-04)**
- The second Proposed Solution bullet ("Consider making `_emit()` itself defensive…") is explicitly out of scope for this issue. See `## Program Design → Decision Rules` for the scoping rule: this issue's Acceptance Criteria and test plan cover only the `_drain_inbound()`-local fix (Option B); the `_emit()` merge-order reorder is not required to close the spoofing hole this issue describes and is not asserted by any Acceptance Criterion here. The call-site audit this bullet requested is already complete (see `## Integration Map → Codebase Research Findings → Conventions in Force` and `## Program Design → Codebase Research Findings`): all 61 other `_emit()` call sites pass no `event`/`ts`/`run_id`/`loop` keys in `data`, so the reorder would be safe if done — but "safe if done" is not the same as "required by this issue." Track the `_emit()` hardening separately if wanted.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-04.

**Selected**: Option B — strip/rename the four envelope keys (`event`, `ts`, `run_id`, `loop`) from the inbound body before spreading it, leaving every other key (including `artifact_id`/`level`/`action`) at top level.

**Reasoning**: The `artifact_interaction` payload contract is documented (`docs/reference/EVENT-SCHEMA.md:1770`, `docs/reference/ARTIFACT_CONTROL_LEVELS.md:73-89`) and schema-registered (`scripts/little_loops/observability/schema.py:376-388`, `ArtifactInteractionVariant`) as top-level `artifact_id`/`level`/`action` fields composing with the envelope, and the built-in `--serve` dashboard's "Send" control (`scripts/little_loops/templates/dashboard.llat/template.html.j2:388-393`) already POSTs exactly `{artifact_id, level, action, payload: {text}}` — all independently confirmed by direct read during this decision pass. Option A (nesting the whole body under a new `payload` key) would move `artifact_id`/`level`/`action` to `event.payload.*`, breaking this documented/registered contract and the dashboard's own emitter; Option B closes the spoofing hole with no consumer/schema change.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (nest under `payload`) | 0/3 | 3/3 | 3/3 | 0/3 | 6/12 |
| Option B (strip envelope keys) | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |

**Key evidence**:
- Nesting under `payload` is a minimal one-line change and easily testable, but breaks the documented/schema-registered `artifact_interaction` contract and the built-in dashboard's own emitter, which POSTs `artifact_id`/`level`/`action` at top level today.
- Stripping the envelope keys matches every existing consumer and the schema exactly (`ArtifactInteractionVariant` in `scripts/little_loops/observability/schema.py:376-388`), requires no downstream change, and still closes the spoofing hole; slightly more code than a bare wrap (build a filtered dict) but remains straightforward.

## Integration Map

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:588` — `FSMExecutor.run()` is the only caller of `_drain_inbound()` (confirmed via `ll-code callers-of` + grep; the graph provider reported `freshness: stale` so this was grep-verified rather than trusted alone).
- `scripts/little_loops/transport.py:691-715` (`_handle_interaction`) → `scripts/little_loops/transport.py:774,779` (`LocalBridgeTransport.__init__`, stores `inbound`) is the only producer that feeds `FSMExecutor.inbound`; no other code path populates the queue `_drain_inbound()` drains.
- `scripts/little_loops/fsm/persistence.py:1010` (`PersistentExecutor._handle_event`) is the sole `event_callback` consumer that acts on event names (`state_enter`/`loop_complete`/`baseline_complete` → `_save_state()` at `:1065-1066`; `evaluate` → `_last_result` at `:1069-1075`; `handoff_detected` → continuation prompt at `:1092-1093`), then delegates to `self.event_bus.emit(event)` at `:1096` for observers/transports.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/fsm/executor.py:564` (`_drain_inbound()`) — the emit call to change: `self._emit("artifact_interaction", event)` currently spreads the raw inbound body last.
- `scripts/little_loops/fsm/executor.py:3581-3591` (`_emit()`) — candidate site if the fix is made defensive at the envelope-builder level instead of (or in addition to) `_drain_inbound()`.

**Conventions in Force**
- Every other `self._emit()` call site in `executor.py` (62 total, grep-confirmed) passes a dict literal built at the call site (e.g. `self._emit("action_start", {"action": action, ...})`); none pass `event`/`ts`/`run_id`/`loop` keys in `data`. `_drain_inbound()` at line 564 is the only caller that forwards an externally-sourced dict wholesale — so the Proposed Solution's requested audit ("Audit existing `_emit()` callers for any that intentionally pass `event`/`ts`/`run_id`/`loop` in `data` first") comes back clean: reordering `_emit()`'s merge (envelope keys applied after `**data`) would not change behavior for any of the other 61 call sites.

**Tests**
- `scripts/tests/test_fsm_executor.py:13116-13260` (`TestInboundEvents`) — existing `_drain_inbound()` coverage: `test_inbound_item_drained_and_emitted` (13167), `test_inbound_multiple_items_drained_in_one_pass` (13186), `test_inbound_events_bounded_at_100` (13205), `test_inbound_forwarded_into_sub_loop` (13218). None of these queue a body containing `event`/`ts`/`run_id`/`loop` keys, so none currently exercise or guard the spoofing this issue describes — the "Add a test" item in Proposed Solution names a real, currently-unfilled gap.
- `scripts/tests/test_transport.py:1174-1191` (`test_interaction_post_lands_on_inbound_queue_unchanged`) — confirms the POST body reaches `inbound` unchanged at the transport layer (pass-through only); does not overlap with the envelope-safety gap above.

**Documentation**
- `docs/reference/EVENT-SCHEMA.md:1770` and `docs/reference/ARTIFACT_CONTROL_LEVELS.md:73-89` document the `artifact_interaction` payload contract as **top-level** fields `artifact_id` (str, required), `level` (str, required), `action` (str, required), and optional `payload` (object) — explicitly "composing with the standard event/ts envelope, not replace it." `scripts/little_loops/observability/schema.py:376-388` (`ArtifactInteractionVariant`, registered in the `DES_VARIANTS` tuple at `:788`) codifies the identical top-level shape as a dataclass. `scripts/little_loops/templates/dashboard.llat/template.html.j2:379-397` — the built-in `--serve` dashboard's own "Send" control POSTs exactly this shape today: `{artifact_id, level, action, payload: {text}}`. See Program Design → Codebase Research Findings for why this bears directly on the Proposed Solution's nesting-vs-stripping choice.

**Configuration**
- No configuration file gates this path; `LocalBridgeTransport` construction with an `inbound` queue (`scripts/little_loops/transport.py:774,779`) is the only entry point that feeds `FSMExecutor.inbound`.

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

**Blast-radius correction — `_handle_event` and `event_callback` scope (remediation pass, 2026-09-04)**
- The "sole `event_callback` consumer" bullet above (`Dependent Files (Callers/Importers)`) undercounts what `PersistentExecutor._handle_event` itself acts on. Two more event-name-gated branches exist in the same function (`scripts/little_loops/fsm/persistence.py:1010-1096`), both reachable from a spoofed `_drain_inbound()` body before this fix:
  - `event_type == "action_complete" and "input_tokens" in event` (`persistence.py:~1019`) appends attacker-controlled `input_tokens`/`output_tokens`/`model`/`cache_read_tokens`/`cache_creation_tokens` to `usage.jsonl` — requires the spoofed body to set both `event: "action_complete"` and an `input_tokens` key.
  - `event_type == "messages_append"` (`persistence.py:~1051`) appends attacker-controlled `state`/`message` to `messages.jsonl` — no extra key beyond `event` is required.
- "Sole consumer" is also precise only for the `event_callback` parameter, not for blast radius generally: `OTelTransport.send()` (`scripts/little_loops/transport.py:1649-1673`) independently branches on `event_type` (`loop_start`/`loop_resume`/`state_enter`/`action_start`/`action_complete`/`loop_complete`) to drive OpenTelemetry span lifecycle. It is reached via `PersistentExecutor._handle_event`'s trailing `self.event_bus.emit(event)` (`persistence.py:1096`) → `EventBus.emit()` → registered transports, not via the `event_callback` parameter directly — a second, distinct event-name-driven consumer.
- Net effect: a spoofed inbound body can, in addition to the persistence/continuation-prompt effects already listed, corrupt cost/usage telemetry (`usage.jsonl`), the message log (`messages.jsonl`), and OTel trace spans.

## Program Design

### Signatures
- `FSMExecutor._drain_inbound(self) -> None` (`fsm/executor.py:549`) — the only inbound→bus bridge; change the emit call here.
- `FSMExecutor._emit(self, event: str, data: dict[str, Any]) -> None` (`fsm/executor.py:3581`) — optionally reorder the merge so the envelope keys are applied after `**data`.

### Call Path
`LocalBridgeTransport._handle_interaction()` (`transport.py:691`) -> `inbound.put_nowait(body)` -> `FSMExecutor.run()` loop / FEAT-1794 tick loop -> `_drain_inbound()` -> `_emit("artifact_interaction", ...)` -> `event_callback` -> `PersistentExecutor._handle_event()` (`persistence.py:1010`, persists + acts on `event` name) -> `EventBus.emit()` -> observers + transports.

### Decision Rules
- Envelope keys (`event`, `ts`, `run_id`, `loop`) plus the sub-loop tag `depth` are executor-owned; no inbound body may set them.
- Strip the four envelope keys before spreading the body, rather than wrapping the whole body under a new key: an existing `artifact_interaction` consumer (the built-in `--serve` dashboard) reads top-level `artifact_id`/`level`/`action` body keys, so wrapping would break it (resolved — see Decision Rationale below).
- Non-goal: reordering `_emit()`'s own merge (Proposed Solution's second bullet) is out of scope for this issue — the fix, Acceptance Criteria, and test plan below are scoped to `_drain_inbound()` only (see Codebase Research Findings below for the completed call-site audit that makes the reorder safe-if-done but not required-here).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

**Call path and call-site audit (confirmed via `ll-code callers-of`/`callees-of`, grep-verified since the graph provider reported `freshness: stale`)**
- `FSMExecutor.run()` (`executor.py:588`) is the only caller of `_drain_inbound()`.
- `self._emit()` (`executor.py:564`) is the only callee `_drain_inbound()` invokes.
- Of `_emit()`'s 62 call sites in `executor.py`, only the one at `_drain_inbound()` (line 564) spreads an externally-sourced dict; the other 61 pass dict literals with no `event`/`ts`/`run_id`/`loop` keys — this is the full answer to the Proposed Solution's requested caller audit (see Integration Map → Codebase Research Findings for the same finding filed against the file list).

**Resolves the previously undecided Decision Rule ("prefer nesting under `payload` … unless an existing consumer reads top-level body keys — grep before deciding")**
- An existing consumer *does* read top-level body keys. The `artifact_interaction` payload contract is documented (`docs/reference/EVENT-SCHEMA.md:1770`, `docs/reference/ARTIFACT_CONTROL_LEVELS.md:73-89`) and schema-registered (`scripts/little_loops/observability/schema.py:376-388`, `ArtifactInteractionVariant` in `DES_VARIANTS`) as top-level `artifact_id`/`level`/`action` fields composing with the envelope — not nested under a `payload` wrapper of the whole body. The built-in `--serve` dashboard's "Send" control (`scripts/little_loops/templates/dashboard.llat/template.html.j2:379-397`) already POSTs exactly that shape: `{artifact_id, level, action, payload: {text}}`.
- Consequence: emitting `self._emit("artifact_interaction", {"payload": event})` (the Proposed Solution's first-listed option) would move `artifact_id`/`level`/`action` from top level to `event.payload.artifact_id` etc., breaking this documented/registered contract and the dashboard's own emitter. Stripping/renaming only the four envelope keys (`event`, `ts`, `run_id`, `loop`) from the body before the spread — the Proposed Solution's second-listed option — preserves the existing `artifact_id`/`level`/`action` top-level shape for `artifact_interaction` while still closing the spoofing hole, and needs no consumer/schema update.

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

**Non-goal — `_emit()` merge-order reorder is out of scope (remediation pass, 2026-09-04)**
- Proposed Solution's second bullet ("Consider making `_emit()` itself defensive") is explicitly a non-goal for this issue. This issue's fix, Acceptance Criteria, and test plan are scoped to `_drain_inbound()` only (Option B: strip the four envelope keys from the inbound body before the spread). `_emit()` (`fsm/executor.py:3581`) itself is not modified by this issue.
- The call-site audit that bullet requested is already complete (see Codebase Research Findings above): all 61 non-`_drain_inbound()` call sites pass no `event`/`ts`/`run_id`/`loop` keys in `data`, so reordering `_emit()`'s merge would be behavior-neutral for them — but that only establishes the reorder is *safe*, not that it is *required*. If defense-in-depth at the `_emit()` level is wanted later, it is a separate, follow-up hardening change, not part of this issue.

## Implementation Steps

1. `_drain_inbound()` (`scripts/little_loops/fsm/executor.py:549-565`) strips the executor-owned keys (`event`, `ts`, `run_id`, `loop`, `depth`) from the parsed POST body before it is spread into `self._emit("artifact_interaction", ...)`, per the selected Option B in Decision Rationale above — every other body key (including `artifact_id`/`level`/`action`) stays at top level. When any key is stripped, log one warning naming the stripped keys. The raw item continues to be appended to `inbound_events` unchanged.
2. `_emit()` (`fsm/executor.py:3581-3591`) is left unmodified — reordering its merge (Proposed Solution's second bullet) is a non-goal for this issue; see Program Design → Decision Rules.
3. A unit test in `scripts/tests/test_fsm_executor.py`, alongside `TestInboundEvents` (`:13116-13260`), asserts a queued body containing `event`/`ts`/`run_id`/`loop` keys is emitted as `artifact_interaction` with the executor's own envelope values, not the body's. Extend `test_inbound_forwarded_into_sub_loop` (`:13218`) (or add a sibling) so a body carrying `"depth": 0` posted during a sub-loop still arrives tagged `depth == 1`.
4. An integration-level regression test drives the spoof through the real path, not `_handle_event` in isolation: construct a `PersistentExecutor` (with a `run_dir` in context) whose inner executor has an `inbound` queue, enqueue `{"event": "loop_complete", "run_id": "spoofed", "ts": "x", "loop": "y"}` plus an `action_complete`+`input_tokens` body and a `messages_append` body, run the loop, and assert: every callback-observed event carrying a body key is named `artifact_interaction` with the executor's `run_id`/`loop`; `_save_state()` was called only the expected number of times for the FSM's genuine `state_enter`/`loop_complete` events (spy it); `_last_result` and `_continuation_prompt` are untouched; `usage.jsonl` and `messages.jsonl` are absent or contain no spoofed rows. Calling `_handle_event({"event": "loop_complete", ...})` directly is **not** a valid test — that function is supposed to act on that name; the property under test is that `_drain_inbound()` never lets a body reach it under that name.
5. `python -m pytest scripts/tests/test_fsm_executor.py -v` (and any new persistence-layer test module/class covering step 4) passes.

## Acceptance Criteria

- A POST body to `/{token}/interaction` containing `event`/`ts`/`run_id`/`loop` keys does not change the `event`/`ts`/`run_id`/`loop` values on the emitted `artifact_interaction` envelope — the executor's own values win.
- A body containing a `depth` key, drained while a sub-loop is executing, is still tagged with the sub-loop's real depth by `_sub_event_callback` (`executor.py:~1170`) — the body cannot pose as a parent-level event.
- When any executor-owned key is stripped from a body, one warning is logged naming the stripped keys (no warning for clean bodies).
- `artifact_id`/`level`/`action` (and any other non-envelope body key) remain top-level on the emitted `artifact_interaction` event, unchanged from today's shape — no `payload`-wrapping regression for the built-in `--serve` dashboard's existing emitter or the documented/schema-registered contract (`docs/reference/EVENT-SCHEMA.md:1770`, `scripts/little_loops/observability/schema.py:376-388`).
- `PersistentExecutor._handle_event` (`persistence.py:1010`) does not call `_save_state()`, overwrite `_last_result`, or set the continuation prompt as a result of a spoofed `event` value in an inbound body — i.e. the `state_enter`/`loop_complete`/`baseline_complete`/`evaluate`/`handoff_detected` side effects are not reachable via `_drain_inbound()` spoofing.
- A spoofed inbound body cannot append attacker-controlled entries to `usage.jsonl` (via the `action_complete` branch, `persistence.py:~1019`) or `messages.jsonl` (via the `messages_append` branch, `persistence.py:~1051`) through `_drain_inbound()`.
- `scripts/tests/test_fsm_executor.py::TestInboundEvents` (or a new adjacent test) covers the envelope-stripping property above; a persistence-layer regression test covers the `_handle_event` side-effect property above — a single envelope-shape unit test alone does not satisfy this criterion.
- `_emit()` (`fsm/executor.py:3581`) is unchanged by this issue's implementation — the fix is scoped to `_drain_inbound()` only (Program Design → Decision Rules non-goal).

## Impact

- **Priority**: P2 — loopback-only and token-gated, so not remotely exploitable by default, but it lets any local process with the token corrupt run persistence and observability for `--serve` runs, and FEAT-3384 is about to make the inbound path load-bearing for HITL verdicts.
- **Effort**: Small — a filtered-dict build plus one warning line in `_drain_inbound()`; `_emit()` untouched. Two tests: an envelope-shape unit test in `TestInboundEvents` and a `PersistentExecutor` regression test driving the spoof through the real drain path (Implementation Steps 3–4).
- **Risk**: Low — Option B (strip executor-owned keys) preserves the documented top-level `artifact_id`/`level`/`action` shape, so no consumer, schema, or dashboard change is needed. Only a body that deliberately set `event`/`ts`/`run_id`/`loop`/`depth` sees any difference, and that is the bug.

## Steps to Reproduce

1. `ll-loop run --serve <loop>` and note the bridge URL/token.
2. `curl -X POST <bridge.url>interaction -d '{"event":"loop_complete","run_id":"spoofed","note":"x"}'`
3. Observe `events.jsonl` (and any SSE/socket consumer) receives an event named `loop_complete` with `run_id: spoofed`, and `PersistentExecutor._handle_event` calls `_save_state()` for it.

## Resolution

Implemented Option B per the Decision Rationale: `_drain_inbound()`
(`scripts/little_loops/fsm/executor.py:549`) now strips the five
executor-owned keys (`event`, `ts`, `run_id`, `loop`, `depth`) from the
inbound body before spreading it into `self._emit("artifact_interaction",
...)`. Every other body key (`artifact_id`/`level`/`action`/etc.) stays
top-level, unchanged. A `logging.getLogger(__name__)` warning names any
stripped keys; clean bodies log nothing. The raw item is still appended to
`inbound_events` unchanged. `_emit()` itself was left untouched, as scoped.

Added coverage:
- `scripts/tests/test_fsm_executor.py::TestInboundEvents` — envelope-key
  stripping, sub-loop `depth` spoof stripping, and the stripped-keys
  warning (present/absent).
- `scripts/tests/test_fsm_persistence.py::TestPersistentExecutor::test_drain_inbound_spoof_does_not_trigger_persistence_side_effects`
  — drives spoofed `loop_complete`/`action_complete`/`messages_append`/
  `evaluate`/`handoff_detected` bodies through a real `PersistentExecutor`
  run and asserts no extra `_save_state()` calls, no `_last_result`/
  `_continuation_prompt` corruption, and no `usage.jsonl`/`messages.jsonl`
  leakage.

Full suite: `python -m pytest scripts/tests/` — 23118 passed, 43 skipped, 6
pre-existing failures unrelated to this change (skill-mirror drift for
gemini/kimi-code/qwen hosts, confirmed present on `main` before this fix).
`ruff check` and `mypy` clean on all changed files.

## Status

**Open** | Created: 2026-09-04 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-09-05T04:57:29 - `9a288b01-52c9-4f8f-a5e0-523e41896fc2.jsonl`
- `/ll:ready-issue` - 2026-09-05T04:44:47 - `7ad2c895-8f68-4859-96fb-41e7c667e5b1.jsonl`
- `/ll:confidence-check` - 2026-09-05T04:41:03 - `4edf6d3c-5d54-450d-a8f2-eb96eef0d54b.jsonl`
- `/ll:confidence-check` - 2026-09-04T21:10:35 - `a0e94d5f-76a9-4089-9549-a69de7658b21.jsonl`
- `/ll:verify-issues` - 2026-09-04T21:06:56 - `a0e94d5f-76a9-4089-9549-a69de7658b21.jsonl`
- `/ll:decide-issue` - 2026-09-04T20:59:12 - `15f28469-a6a4-4d6e-a8c3-8e12607ee711.jsonl`
- `/ll:refine-issue` - 2026-09-04T20:51:54 - `fcf441d7-4e2b-44cc-9bfb-5988b3d419cb.jsonl`
