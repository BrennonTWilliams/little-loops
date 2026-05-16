---
discovered_date: 2026-04-02
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
---

# ENH-920: Wire EventBus Emission into StateManager

## Summary

Add EventBus event emission to `StateManager.mark_completed()` and `StateManager.mark_failed()` in `state.py` so extensions can observe processing state transitions during automated runs (ll-auto, ll-parallel, ll-sprint).

## Context

Identified from FEAT-911 session continuation prompt. The StateManager tracks which issues have been processed during automated runs. Emitting events from these methods gives extensions visibility into the progress of batch processing — complementing the FSM-level events already wired in FEAT-911.

## Current Behavior

`StateManager.mark_completed()` and `StateManager.mark_failed()` update internal state and persist to JSON, but emit no events. Extensions cannot observe automation progress.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `StateManager.__init__(self, state_file: Path, logger: Logger)` at `state.py:85` — no EventBus parameter
- `mark_completed(self, issue_id: str, timing: dict[str, float] | None = None)` at `state.py:175` — appends to `completed_issues`, stores timing, resets phase to `"idle"`, calls `save()`
- `mark_failed(self, issue_id: str, reason: str)` at `state.py:189` — writes to `failed_issues[issue_id] = reason`, calls `save()`
- Note: `mark_failed` uses parameter name `reason`, not `error`

## Expected Behavior

- `mark_completed()` → emits `state.issue_completed` with issue ID and processing metadata
- `mark_failed()` → emits `state.issue_failed` with issue ID, error info, and processing metadata

## Motivation

For ll-auto and ll-parallel runs, StateManager transitions are the primary signal of per-issue progress. Extensions like progress dashboards or Slack notifiers need these events to report real-time status.

## Proposed Solution

Add an optional `event_bus` parameter to `StateManager.__init__()` in `scripts/little_loops/state.py`:

- Store `self._event_bus = event_bus` in the constructor
- In `mark_completed()`, emit `state.issue_completed` with flat dict payload `{"event": "state.issue_completed", "ts": "<iso8601>", "issue_id": issue_id, "status": "completed"}`
- In `mark_failed()`, emit `state.issue_failed` with flat dict payload `{"event": "state.issue_failed", "ts": "<iso8601>", "issue_id": issue_id, "reason": reason, "status": "failed"}`
- Guard emissions with `if self._event_bus:` to maintain backward compatibility when no bus is provided (alternatively, use no-op default pattern from `fsm/executor.py:370`)
- Wire `EventBus` instance from `AutoManager.__init__()` (`issue_manager.py:734`) — the only call site that creates `StateManager`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Payloads corrected to match `mark_failed`'s actual parameter name (`reason`, not `error`) and codebase flat-dict convention (`LLEvent.to_dict()` at `events.py:41`)
- Wiring scope narrowed: only `AutoManager` needs changes (ll-parallel and ll-sprint don't use StateManager)

## API/Interface

```python
class StateManager:
    def __init__(self, state_file: Path, logger: Logger, event_bus: EventBus | None = None) -> None: ...
    def mark_completed(self, issue_id: str, timing: dict[str, float] | None = None) -> None: ...  # emits state.issue_completed
    def mark_failed(self, issue_id: str, reason: str) -> None: ...  # emits state.issue_failed
```

Events emitted (flat dict format matching codebase convention — see `LLEvent.to_dict()` at `events.py:41`):
- `state.issue_completed`: `{"event": "state.issue_completed", "ts": "<iso8601>", "issue_id": str, "status": "completed"}`
- `state.issue_failed`: `{"event": "state.issue_failed", "ts": "<iso8601>", "issue_id": str, "reason": str, "status": "failed"}`

## Implementation Steps

1. **Modify `StateManager.__init__`** (`state.py:85`): Add optional `event_bus: EventBus | None = None` parameter after `logger`, store as `self._event_bus`
2. **Add `_emit` helper to `StateManager`**: Create a private method following the pattern in `fsm/executor.py:1006` — builds flat dict with `{"event": type, "ts": _iso_now(), **payload}` and calls `self._event_bus.emit()`. Guard with `if self._event_bus:` (or use no-op default like `FSMExecutor` at `executor.py:370`)
3. **Emit in `mark_completed()`** (`state.py:175`): After `self.save()` at line 187, call `self._emit("state.issue_completed", {"issue_id": issue_id, "status": "completed"})`
4. **Emit in `mark_failed()`** (`state.py:189`): After `self.save()` at line 197, call `self._emit("state.issue_failed", {"issue_id": issue_id, "reason": reason, "status": "failed"})`
5. **Wire EventBus in `AutoManager.__init__`** (`issue_manager.py:734`): Create `EventBus()` and pass to `StateManager(config.get_state_file(), self.logger, event_bus=event_bus)`. Optionally expose the bus as `self.event_bus` for CLI consumers to register observers
6. **Add tests** (`tests/test_state.py`): Follow list collector spy pattern from `test_events.py:101` — create `EventBus`, register `lambda e: received.append(e)`, construct `StateManager` with it, call `mark_completed`/`mark_failed`, assert on collected events

## Acceptance Criteria

- [x] `mark_completed()` emits `state.issue_completed` event
- [x] `mark_failed()` emits `state.issue_failed` event
- [x] Events include issue ID and relevant metadata
- [x] EventBus is wired from `AutoManager.__init__` (the only `StateManager` instantiation site)
- [x] Tests verify emission for both methods

## Scope Boundaries

- **In scope**: `mark_completed()` and `mark_failed()` event emission; optional EventBus wiring from `AutoManager.__init__` (`issue_manager.py:734`)
- **Out of scope**: Adding events to other StateManager methods (e.g., `mark_skipped`, `reset`); EventBus configuration UI; persistent event storage; ll-parallel/ll-sprint wiring (covered by ENH-921 and separate sprint state)

## Success Metrics

- Extensions registered on `state.issue_completed` / `state.issue_failed` receive callbacks during ll-auto/ll-parallel runs
- No behavioral change when EventBus is not provided (backward compatible)
- Test coverage for both emission paths

## Impact

- **Priority**: P3 - Useful for extension ecosystem but not blocking core functionality
- **Effort**: Small - Adding optional parameter and 2 emit calls to existing methods
- **Risk**: Low - Optional parameter preserves backward compatibility; well-tested path
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `scripts/little_loops/state.py` — Add `event_bus` parameter to `__init__` (line 85), add `_emit` helper, emit in `mark_completed` (line 175) and `mark_failed` (line 189)
- `scripts/little_loops/issue_manager.py:734` — Wire `EventBus()` into `StateManager` construction inside `AutoManager.__init__`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` — The only module that instantiates `StateManager` (line 734) and calls `mark_completed` (lines 970, 975) and `mark_failed` (line 984)
- `scripts/little_loops/cli/auto.py` — Creates `AutoManager` (lines 90–101); no direct change needed unless exposing bus for observer registration

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **ll-parallel does NOT use StateManager** — it uses `IssuePriorityQueue` with its own `mark_completed`/`mark_failed` (covered by sibling ENH-921)
- **ll-sprint does NOT use StateManager** — it uses `SprintState` directly (`cli/sprint/run.py:272-282`)
- **Only `AutoManager` (ll-auto path) instantiates StateManager** — scope is narrower than originally described

### Similar Patterns
- `fsm/persistence.py:344` — `PersistentExecutor` creates `self.event_bus = EventBus()` in `__init__`, emits via `self.event_bus.emit(event)` at line 394
- `fsm/executor.py:1006` — `_emit` helper builds flat `{"event": type, "ts": _iso_now(), **data}` dict
- `fsm/executor.py:370` — No-op guard pattern: `self.event_callback = event_callback or (lambda _: None)` eliminates per-call guards

### Tests
- `scripts/tests/test_state.py` — Existing `StateManager` tests at lines 308–337; add emission tests alongside
- `scripts/tests/test_events.py:101` — Reference test spy pattern: `received = []; bus.register(lambda e: received.append(e))`

### Documentation
- `docs/reference/API.md` — Update StateManager API docs with new parameter and events

### Configuration
- N/A

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | StateManager role in automation |
| architecture | docs/reference/API.md | EventBus and StateManager API |

## Labels

`enhancement`, `captured`, `extension-system`

---

## Status

**Completed** | Created: 2026-04-02 | Completed: 2026-04-02 | Priority: P3

## Resolution

Implemented EventBus emission in StateManager with 5 new tests. Changes:
- `state.py`: Added optional `event_bus` parameter to `__init__`, `_emit` helper, and emission calls in `mark_completed()` and `mark_failed()`
- `issue_manager.py`: Created `EventBus()` in `AutoManager.__init__` and passed to `StateManager`
- `test_state.py`: 5 new tests covering both emission paths, backward compatibility, and flat dict format

## Session Log
- `/ll:confidence-check` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8394421c-530d-4c82-897e-1edcec40a825.jsonl`
- `/ll:refine-issue` - 2026-04-02T19:10:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87eedb33-487e-4156-9a11-3b9a54f1b62b.jsonl`
- `/ll:format-issue` - 2026-04-02T18:47:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d44d738d-0717-4906-af00-9fc93600eff9.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ec33f5e-0af1-4604-bdc4-0c4331282e3e.jsonl`
- `/ll:ready-issue` - 2026-04-02T20:37:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4bda8160-2032-44ba-98ff-2c78bc74395e.jsonl`
