---
discovered_date: 2026-04-11
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 85
---

# FEAT-1043: LLTestBus Test Harness

## Summary

Implement `LLTestBus` — a standalone class in `scripts/little_loops/testing.py` that loads a recorded `.events.jsonl` file, replays events through registered extensions offline (no live loop execution), and exposes `delivered_events` for assertions. Export it from `scripts/little_loops/__init__.py`.

## Parent Issue

Decomposed from FEAT-916: Extension SDK with Scaffolding Command and Test Harness

## Context

Extension authors need a way to test their `on_event` handlers without running a full loop. `LLTestBus` replays real recorded event files through extensions, making the test loop identical to production behavior — including `event_filter` support.

## Current Behavior

No `LLTestBus` class exists anywhere in `scripts/`. Extension authors must run real loops to test their extensions.

## Expected Behavior

```python
from little_loops.testing import LLTestBus

bus = LLTestBus.from_jsonl("path/to/recorded.events.jsonl")
bus.register(MyExtension())
bus.replay()
assert len(bus.delivered_events) == 15
assert bus.delivered_events[0].type == "loop_start"
```

## Proposed Solution

Implement `LLTestBus` as a standalone class (not an `EventBus` subclass):

1. `from_jsonl(path: str | Path)` classmethod — calls `Path(path)` then `EventBus.read_events(path)` (requires `Path`, not `str`)
2. `register(ext: LLExtension)` — stores extensions in `_extensions: list[LLExtension]`
3. `replay()` — iterates stored events, applies `event_filter` normalization, calls `ext.on_event(event)` directly for each passing `LLEvent`
4. `delivered_events: list[LLEvent]` — exposes events actually delivered

## Integration Map

### Files to Create / Modify
- `scripts/little_loops/testing.py` — new file, `LLTestBus` class
- `scripts/little_loops/__init__.py` — add `from little_loops.testing import LLTestBus` after line 35 (end of import block); add `"LLTestBus"` to `__all__` after line 50 (`"wire_extensions"`, within the `# extensions` block)
- `scripts/tests/test_testing.py` — new test file for `LLTestBus`
- `scripts/tests/test_extension.py` — add `test_smoke_import_ll_test_bus` to `TestNewProtocols` class (lines 465-537)

### Key References
- `scripts/little_loops/extension.py:29-49` — `LLExtension` Protocol
- `scripts/little_loops/events.py:90-93` — `event_filter` normalization pattern: `ef = getattr(ext, "event_filter", None); patterns = ([ef] if isinstance(ef, str) else list(ef)) if ef is not None else None`
- `scripts/little_loops/events.py:132-150` — `EventBus.read_events(path: Path)` returns `list[LLEvent]` (requires `Path`, not `str`)
- `scripts/little_loops/extension.py:52-67` — `NoopLoggerExtension` as reference implementation

### Critical Implementation Notes
- `LLTestBus` must be a **standalone class** — NOT an `EventBus` subclass. `EventBus.register()` takes `EventCallback = Callable[[dict[str, Any]], None]`, not `LLExtension`.
- Do NOT use the `_make_callback` closure pattern from `wire_extensions()` — `LLTestBus` already has typed `LLEvent` objects; call `ext.on_event(event)` directly.
- `event_filter` is `str | list[str] | None` — normalize using `events.py:90-93` pattern; use `fnmatch.fnmatch(event.type, p)` for matching.
- `EventBus.read_events()` requires `Path`, not `str` — call `Path(path)` in `from_jsonl()`.

### Tests
- `test_testing.py` must define its own JSONL fixture in proper `LLEvent` wire format: `{"event": "loop_start", "ts": "2025-01-01T00:00:00", "loop_name": "test-loop"}`. Do NOT reuse `conftest.py:284` `events_file` fixture — it uses history format incompatible with `LLEvent`.
- `test_smoke_import_ll_test_bus` pattern: `from little_loops import LLTestBus; assert LLTestBus is not None`

## Implementation Steps

1. Create `scripts/little_loops/testing.py`:
   - `LLTestBus` standalone class
   - `from_jsonl(path: str | Path) -> LLTestBus` classmethod
   - `register(ext: LLExtension) -> None`
   - `replay() -> None` with `event_filter` normalization from `events.py:90-93`
   - `delivered_events: list[LLEvent]` property or attribute

2. Update `scripts/little_loops/__init__.py`:
   - Add `from little_loops.testing import LLTestBus` after line 35
   - Add `"LLTestBus"` to `__all__` after line 50

3. Create `scripts/tests/test_testing.py` with fixture + tests

4. Add `test_smoke_import_ll_test_bus` to `TestNewProtocols` class in `scripts/tests/test_extension.py` (lines 465-537)

## Acceptance Criteria

- [ ] `LLTestBus.from_jsonl()` loads events from a `.events.jsonl` file
- [ ] `LLTestBus.replay()` calls `ext.on_event()` for events matching `event_filter`
- [ ] `LLTestBus.delivered_events` contains only events that passed the filter
- [ ] `LLTestBus` exported from `little_loops` top-level
- [ ] Smoke import test passes

## Impact

- **Priority**: P4 - Developer experience; valuable once extension ecosystem has traction
- **Effort**: Small-Medium - Focused implementation, well-researched API design
- **Risk**: Low - Purely additive; no changes to existing code paths
- **Breaking Change**: No
- **Depends On**: FEAT-911 (completed)

## Labels

`feat`, `extension-api`, `developer-experience`

---

## Verification Notes

**Verdict**: VALID — Verified 2026-04-11

- `scripts/little_loops/testing.py` does not exist ✓
- `LLTestBus` not in `scripts/little_loops/__init__.py` exports ✓
- Feature not yet implemented

## Status

**Open** | Created: 2026-04-11 | Priority: P4

## Session Log
- `/ll:verify-issues` - 2026-04-11T23:05:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:issue-size-review` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8463ec2-3356-49c3-888b-ccb8aab90cb6.jsonl`
