---
id: BUG-3387
type: BUG
title: inbound interaction POST body overwrites _emit() envelope (event name spoofing
  via _drain_inbound)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-04'
captured_at: '2026-09-04T20:40:10Z'
labels:
- fsm
- security
- serve
- events
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

- In `_drain_inbound()`, emit `self._emit("artifact_interaction", {"payload": event})` — or strip `event`/`ts`/`run_id`/`loop` from the body before spreading — and keep appending the raw item to `inbound_events`.
- Consider making `_emit()` itself defensive: build the dict as `{**data, "event": event, "ts": ..., "run_id": ..., "loop": ...}` so no caller can clobber the envelope. Audit existing `_emit()` callers for any that intentionally pass `event`/`ts`/`run_id`/`loop` in `data` first.
- Add a test in `scripts/tests/test_fsm_executor.py` next to the existing `_drain_inbound` tests asserting a body with `event`/`run_id`/`loop`/`ts` keys cannot change the emitted envelope.
- Coordinate with FEAT-3384 (its `_drain_inbound()` `human_response` branch already builds a whitelisted payload) so the two changes land compatibly.

## Program Design

### Signatures
- `FSMExecutor._drain_inbound(self) -> None` (`fsm/executor.py:549`) — the only inbound→bus bridge; change the emit call here.
- `FSMExecutor._emit(self, event: str, data: dict[str, Any]) -> None` (`fsm/executor.py:3581`) — optionally reorder the merge so the envelope keys are applied after `**data`.

### Call Path
`LocalBridgeTransport._handle_interaction()` (`transport.py:691`) -> `inbound.put_nowait(body)` -> `FSMExecutor.run()` loop / FEAT-1794 tick loop -> `_drain_inbound()` -> `_emit("artifact_interaction", ...)` -> `event_callback` -> `PersistentExecutor._handle_event()` (`persistence.py:1010`, persists + acts on `event` name) -> `EventBus.emit()` -> observers + transports.

### Decision Rules
- Envelope keys (`event`, `ts`, `run_id`, `loop`) are executor-owned; no inbound body may set them.
- Prefer nesting the body under `payload` over stripping keys, unless an existing `artifact_interaction` consumer reads top-level body keys (grep before deciding).

## Impact

- **Priority**: P2 — loopback-only and token-gated, so not remotely exploitable by default, but it lets any local process with the token corrupt run persistence and observability for `--serve` runs, and FEAT-3384 is about to make the inbound path load-bearing for HITL verdicts.
- **Effort**: Small — one-line change in `_drain_inbound()` (or `_emit()`), one test.
- **Risk**: Low — `artifact_interaction` consumers that read top-level body keys would need to read `payload.*` instead; grep for consumers before choosing nesting vs. stripping.

## Steps to Reproduce

1. `ll-loop run --serve <loop>` and note the bridge URL/token.
2. `curl -X POST <bridge.url>interaction -d '{"event":"loop_complete","run_id":"spoofed","note":"x"}'`
3. Observe `events.jsonl` (and any SSE/socket consumer) receives an event named `loop_complete` with `run_id: spoofed`, and `PersistentExecutor._handle_event` calls `_save_state()` for it.

## Status

**Open** | Created: 2026-09-04 | Priority: P2
