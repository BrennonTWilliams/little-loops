---
discovered_date: 2026-04-11
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 93
---

# FEAT-1043: LLTestBus Test Harness

## Summary

Implement `LLTestBus` — a standalone class in `scripts/little_loops/testing.py` that loads a recorded `.events.jsonl` file, replays events through registered extensions offline (no live loop execution), and exposes `delivered_events` for assertions. Export it from `scripts/little_loops/__init__.py`.

## Parent Issue

Decomposed from FEAT-916: Extension SDK with Scaffolding Command and Test Harness

## Context

Extension authors need a way to test their `on_event` handlers without running a full loop. `LLTestBus` replays real recorded event files through extensions, making the test loop identical to production behavior — including `event_filter` support.

## Use Case

An extension author has written an `on_event` handler and wants to verify it receives the correct events offline. They call `LLTestBus.from_jsonl("path/to/recorded.events.jsonl")`, register their extension, and call `replay()`. They then assert on `bus.delivered_events` to confirm the handler logic is correct — without starting a live loop or requiring a running Claude Code session.

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
- `scripts/little_loops/extension.py:35-56` — `LLExtension` Protocol
- `scripts/little_loops/events.py:90-93` — `event_filter` normalization pattern: `ef = getattr(ext, "event_filter", None); patterns = ([ef] if isinstance(ef, str) else list(ef)) if ef is not None else None`
- `scripts/little_loops/events.py:132-150` — `EventBus.read_events(path: Path)` returns `list[LLEvent]` (requires `Path`, not `str`)
- `scripts/little_loops/extension.py:101-116` — `NoopLoggerExtension` as reference implementation

### Critical Implementation Notes
- `LLTestBus` must be a **standalone class** — NOT an `EventBus` subclass. `EventBus.register()` takes `EventCallback = Callable[[dict[str, Any]], None]`, not `LLExtension`.
- Do NOT use the `_make_callback` closure pattern from `wire_extensions()` — `LLTestBus` already has typed `LLEvent` objects; call `ext.on_event(event)` directly.
- `event_filter` is `str | list[str] | None` — normalize using `events.py:90-93` pattern; use `fnmatch.fnmatch(event.type, p)` for matching. Since `LLTestBus` dispatches directly (not through `EventBus.emit()`), use `event.type` (the `LLEvent` attribute) — not `event.get("event","")` — in the fnmatch check. Adapt `events.py:113-118` for this direct-dispatch variant.
- `EventBus.read_events()` requires `Path`, not `str` — call `Path(path)` in `from_jsonl()`.

### Tests
- `test_testing.py` must define its own JSONL fixture in proper `LLEvent` wire format: `{"event": "loop_start", "ts": "2025-01-01T00:00:00", "loop": "test-loop"}` — note `"loop"` (not `"loop_name"`) is the real payload key used in live events (see `test_ll_loop_commands.py:511-515`). Do NOT reuse `conftest.py:284` `events_file` fixture — it uses history format incompatible with `LLEvent`.
- Use `json.dumps` + `open` loop for dict-based JSONL fixture writing (see `test_ll_loop_commands.py:511-520`), or `write_text("\n".join([json.dumps(e) for e in events]))` for inline string lists.
- `test_smoke_import_ll_test_bus` pattern: `from little_loops import LLTestBus; assert LLTestBus is not None`
- Model `delivered_events` assertions after the inline `RecordingExtension` class pattern at `test_extension.py:34-49` — use a local `received: list[LLEvent] = []` list to capture events, then assert against `bus.delivered_events`.
- For filter-scoped tests, use the `FilteredExtension` pattern at `test_extension.py:228-246`: declare `event_filter = "issue.*"` as a class attribute.

### Documentation
- `docs/ARCHITECTURE.md` — already references `LLTestBus`; implementer must read to ensure implementation matches documented interface and update if needed
- `docs/reference/API.md` — already describes `LLTestBus` public API; verify conformance after implementation

_Wiring pass added by `/ll:wire-issue`:_
- **CORRECTION**: `docs/ARCHITECTURE.md` does NOT currently mention `LLTestBus` (confirmed by search). The module tree at lines 174-269 will be missing `testing.py` after implementation. Doc updates are tracked in FEAT-1045; implementer should note the discrepancy rather than expecting the docs to already match.
- **CORRECTION**: `docs/reference/API.md` does NOT currently describe `LLTestBus`. Neither the module table (lines 34-37) nor the extension section (~lines 5147-5325) contains a `LLTestBus` entry. Doc updates are tracked in FEAT-1045.
- `docs/reference/CONFIGURATION.md:631-659` — extension authoring section documents `LLExtension` protocol and usage patterns; will need a cross-reference to `LLTestBus` for offline testing (tracked in FEAT-1045)

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Ensure `test_testing.py` achieves sufficient branch coverage of `testing.py` — `scripts/pyproject.toml:116-132` sets `fail_under = 80` with `source = ["little_loops"]`; `testing.py` is included in the measured set. Cover the main branches: `from_jsonl` with missing file (returns `[]`), `replay` with no extensions, `replay` with unfiltered extension, `replay` with filtered extension (matching and non-matching).

## Acceptance Criteria

- [x] `LLTestBus.from_jsonl()` loads events from a `.events.jsonl` file
- [x] `LLTestBus.replay()` calls `ext.on_event()` for events matching `event_filter`
- [x] `LLTestBus.delivered_events` contains only events that passed the filter
- [x] `LLTestBus` exported from `little_loops` top-level
- [x] Smoke import test passes

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

## Resolution

Implemented `LLTestBus` as a standalone class in `scripts/little_loops/testing.py`. Exported from `little_loops.__init__`. Tests in `scripts/tests/test_testing.py` (14 tests covering all branches: from_jsonl missing file, replay with no extensions, unfiltered, string filter, list filter, multiple extensions). Smoke import added to `TestNewProtocols`. All 24 tests pass; lint clean.

## Status

**Completed** | Created: 2026-04-11 | Completed: 2026-04-11 | Priority: P4

## Session Log
- `/ll:manage-issue` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-04-12T02:40:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9e760b44-f4b0-4713-8c67-eee2ba125404.jsonl`
- `/ll:confidence-check` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9e4f0ded-d1f5-453e-84a5-52a048e214e3.jsonl`
- `/ll:wire-issue` - 2026-04-12T02:32:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/76ef449f-bfef-4e93-a88b-7745bf0d095d.jsonl`
- `/ll:refine-issue` - 2026-04-12T02:23:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5703b25f-485b-4dde-b132-7d7c67442741.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:issue-size-review` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8463ec2-3356-49c3-888b-ccb8aab90cb6.jsonl`
