---
captured_at: "2026-04-21T19:06:11Z"
completed_at: "2026-04-23T15:51:54Z"
discovered_date: "2026-04-21"
discovered_by: capture-issue
decision_needed: false
confidence_score: 95
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
status: done
---

# ENH-1231: Make loop queue wait timeout configurable

## Summary

The `--queue` flag on `ll-loop run` blocks until a conflicting scope lock is released, but the wait timeout is hardcoded at 3600 seconds. Users with long-running loops or unusual scheduling patterns have no way to adjust this — too short causes spurious timeouts, too long means silent hangs. The timeout should be a field in the `loops` section of `ll-config`.

## Current Behavior

`ll-loop run --queue` calls `lock_manager.wait_for_scope(scope, timeout=3600)` with a hardcoded 1-hour ceiling (`scripts/little_loops/cli/loop/run.py`, `wait_for_scope` call). When the blocking loop holds its lock beyond that window, the queued run emits `"Timeout waiting for scope to become available"` and exits with code 1.

## Expected Behavior

A `queue_wait_timeout_seconds` field (or similar) in the `loops` config section lets users override the 1-hour default. The CLI should read this value at startup and pass it to `wait_for_scope`. The existing hardcoded value becomes the schema default, preserving current behaviour for users who don't set it.

## Motivation

A user encountered this timeout when a queued loop waited more than an hour for a scope to become free. There is no workaround short of patching the source. Making it configurable:
- Lets users extend the window for legitimately long-running loops (e.g. overnight automation).
- Lets users shorten it for fail-fast CI environments where an hour of silent waiting is unacceptable.
- Follows the existing pattern: `automation.timeout_seconds`, `parallel.timeout_per_issue`, and `sprints.default_timeout` are all configurable — the loop queue timeout is the only hard boundary that isn't.

## Proposed Solution

1. Add `queue_wait_timeout_seconds` to the `loops` object in `config-schema.json`:

```json
"queue_wait_timeout_seconds": {
  "type": "integer",
  "description": "Seconds to wait for a conflicting scope lock to be released when --queue is used.",
  "default": 3600,
  "minimum": 1
}
```

2. In `scripts/little_loops/cli/loop/run.py`, read the value from config and pass it through:

```python
queue_timeout = _config.loops.queue_wait_timeout_seconds
if not lock_manager.wait_for_scope(scope, timeout=queue_timeout):
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Correction — `config.loops` is a dataclass, not a dict.** `config.loops.get(...)` will raise `AttributeError`. Use attribute access instead:
```python
queue_timeout = _config.loops.queue_wait_timeout_seconds
if not lock_manager.wait_for_scope(scope, timeout=queue_timeout):
```

**Decision — `wait_for_scope` does not support `None`/`0` for indefinite wait.** The implementation (`concurrency.py:225`) uses `while time.time() - start < timeout`; passing `None` raises `TypeError` and passing `0` exits immediately. **Option A chosen:** set `minimum: 1` in schema and pass the int directly — no patch to `wait_for_scope` required.

## Integration Map

### Files to Modify
- `config-schema.json` — add `queue_wait_timeout_seconds` to `loops` properties
- `scripts/little_loops/cli/loop/run.py` — read config value, replace hardcoded `3600`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/lock_manager.py` (or equivalent) — verify `wait_for_scope` accepts `None`/`0` for indefinite wait

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/__init__.py:39,59` — re-exports `LoopsConfig`; no change needed, confirms public API surface
- `scripts/little_loops/cli/loop/__init__.py:30,34` — instantiates `BRConfig`, reads `config.loops.loops_dir`; no change needed, new field will be available automatically

### Similar Patterns
- `config-schema.json` `automation.timeout_seconds` — same shape: integer, minimum 0, default 3600
- `config-schema.json` `sprints.default_timeout` — same shape

### Tests
- `scripts/tests/` — add/update tests for queue timeout resolution from config; mock `wait_for_scope` to verify correct value is passed

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` — add `TestLoopsConfig` class (none exists; only `TestLoopsGlyphsConfig` at line 1507); follow `TestSprintsConfig` at lines 511-533 with `test_from_dict_with_all_fields` and `test_from_dict_with_defaults`
- `scripts/tests/test_config.py` — add `TestBRConfigLoops` integration class: assert default for `config.loops.queue_wait_timeout_seconds`, config-file override, and `to_dict()["loops"]["queue_wait_timeout_seconds"]` presence
- `scripts/tests/test_config.py:678` — `test_to_dict` does not assert on `result["loops"]`; add assertion for `"queue_wait_timeout_seconds"` key
- `scripts/tests/test_concurrency.py` — if Option B (`0=indefinite`): add test verifying `wait_for_scope(scope, timeout=0)` waits and succeeds when lock is released

### Documentation
- `docs/reference/API.md` — if `loops` config section is documented, add the new field
- `docs/` loop usage docs if they mention `--queue` behaviour

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:1174-1184` — describes `--queue` wait behavior without mentioning configurable timeout; add note about `queue_wait_timeout_seconds`
- `docs/guides/LOOPS_GUIDE.md:1237-1259` — `--background --queue` usage sections with no timeout documentation
- `docs/development/TROUBLESHOOTING.md:258-280` — lists `automation.timeout_seconds` and `parallel.timeout_per_issue` as configurable timeout knobs; add symmetrical entry for `loops.queue_wait_timeout_seconds`

### Configuration
- `config-schema.json` — the primary change

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Files to Modify (with exact locations):**
- `scripts/little_loops/cli/loop/run.py:178` — `lock_manager.wait_for_scope(scope, timeout=3600)` — the only call site; `_config = BRConfig(Path.cwd())` is already constructed at `run.py:95-101` so `_config.loops.queue_wait_timeout_seconds` is available without plumbing changes
- `scripts/little_loops/config/features.py:294-307` — `LoopsConfig` dataclass and its `from_dict` classmethod; add `queue_wait_timeout_seconds: int = 3600` field and update `from_dict` to read it
- `config-schema.json:756-781` — `loops` section currently only defines `loops_dir` and `glyphs`; the new field goes here following the shape at lines 740-745 (`sprints.default_timeout`)
- `scripts/little_loops/config/core.py:431-434` — `BRConfig.to_dict` serializes the `loops` section; add `"queue_wait_timeout_seconds": self._loops.queue_wait_timeout_seconds` here (**not mentioned in original issue**)

**`wait_for_scope` signature** (`scripts/little_loops/fsm/concurrency.py:221-238`):
```python
def wait_for_scope(self, scope: list[str], timeout: int = 300) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        ...
    return False
```
`timeout: int` — does not support `None` or `0`. Schema uses `minimum: 1`; the int is passed directly with no conversion needed.

**Similar Patterns (exact refs):**
- `config-schema.json:200-205` — `automation.timeout_seconds`: `type: integer, default: 3600, minimum: 60`
- `config-schema.json:269-274` — `parallel.timeout_per_issue`: same shape
- `config-schema.json:740-745` — `sprints.default_timeout`: same shape
- `scripts/little_loops/config/automation.py:14-36` — `AutomationConfig.from_dict` — exact dataclass pattern to mirror
- `scripts/little_loops/config/features.py:239-253` — `SprintsConfig.from_dict` — closest analog

**Tests (exact refs):**
- `scripts/tests/test_config.py:511-533` — `SprintsConfig.from_dict_with_all_fields` and `from_dict_with_defaults` — model new `LoopsConfig` tests after these
- `scripts/tests/test_concurrency.py:359-408` — existing `wait_for_scope` tests pass `timeout` as explicit kwarg — same shape for any new test

## Implementation Steps

1. Add `queue_wait_timeout_seconds` field to `loops` in `config-schema.json` with default `3600` and minimum `1`
2. Update config loading/dataclass for the `loops` section to expose the new field
3. In `run.py`, replace the hardcoded `timeout=3600` with the config-sourced value
4. Add/update tests asserting config value is forwarded correctly
5. Update relevant docs and schema changelog

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **`config-schema.json:756-781`** — add `queue_wait_timeout_seconds` to `loops` object following the shape at lines `740-745` (`sprints.default_timeout`): `type: integer, description: "...", default: 3600, minimum: 1`
2. **`scripts/little_loops/config/features.py:294-307`** — add `queue_wait_timeout_seconds: int = 3600` to `LoopsConfig` dataclass; update `LoopsConfig.from_dict` to include `queue_wait_timeout_seconds=data.get("queue_wait_timeout_seconds", 3600)` — mirror the `SprintsConfig` pattern at `features.py:239-253`
3. **`scripts/little_loops/cli/loop/run.py:178`** — replace `timeout=3600` with `timeout=_config.loops.queue_wait_timeout_seconds`; `_config` already constructed at `run.py:95-101`, no additional plumbing needed
4. **`scripts/little_loops/config/core.py:431-434`** — add `"queue_wait_timeout_seconds": self._loops.queue_wait_timeout_seconds` to the `loops` dict in `BRConfig.to_dict`
5. **Tests** — add to `scripts/tests/test_config.py` following `test_config.py:511-533` (`SprintsConfig` test class): `test_from_dict_with_all_fields` (pass `{"queue_wait_timeout_seconds": 7200}`, assert `config.queue_wait_timeout_seconds == 7200`) and `test_from_dict_with_defaults` (pass `{}`, assert default is `3600`)
6. **Verify** `python -m pytest scripts/tests/test_config.py scripts/tests/test_concurrency.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `docs/guides/LOOPS_GUIDE.md:1174-1184` — add a note that `queue_wait_timeout_seconds` in the `loops` config section controls how long `--queue` waits before timing out
9. Update `docs/guides/LOOPS_GUIDE.md:1237-1259` — add timeout note in `--background --queue` usage sections
10. Update `docs/development/TROUBLESHOOTING.md:258-280` — add `loops.queue_wait_timeout_seconds` entry alongside `automation.timeout_seconds` and `parallel.timeout_per_issue`
11. Update `scripts/tests/test_config.py:678` (`test_to_dict`) — add assertion that `result["loops"]["queue_wait_timeout_seconds"]` is present after existing assertions

## Success Metrics

- `queue_wait_timeout_seconds` appears in `config-schema.json` with correct type, default, and minimum
- `ll-loop run --queue` respects a value set in `.ll/ll-config.json`
- Existing tests pass; new test covers config-plumbed timeout

## Scope Boundaries

- Does not change the default behaviour (3600 s default)
- Does not add a `--timeout` CLI flag (config-only change)
- Does not affect non-queued `ll-loop run` behaviour

## API/Interface

New `ll-config` field:

```json
{
  "loops": {
    "queue_wait_timeout_seconds": 3600
  }
}
```

## Impact

- **Priority**: P3 — affects users who rely on `--queue` with long-running loops; not blocking for most workflows
- **Effort**: Small — one schema field, one config read, one variable substitution, one test
- **Risk**: Low — defaults preserve existing behaviour exactly
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `config`, `captured`

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-23T15:52:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa72163f-0946-477f-9a78-b6811b7994a3.jsonl`
- `/ll:ready-issue` - 2026-04-23T15:48:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/adbd4941-0ef6-48a9-b49a-f6150ed66268.jsonl`
- `/ll:confidence-check` - 2026-04-23T16:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e7938665-8e2e-4fea-91b5-179c94810bc3.jsonl`
- `/ll:wire-issue` - 2026-04-23T15:29:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b32bbdcc-d70a-4a99-bb22-88420ffc59bc.jsonl`
- `/ll:refine-issue` - 2026-04-23T15:20:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d31002f4-a308-48f4-9aa5-1991332d2a65.jsonl`

- `/ll:capture-issue` - 2026-04-21T19:06:11Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/292a62ed-c8c7-4b31-bc37-39202571d4c4.jsonl`

---

## Resolution

Implemented `queue_wait_timeout_seconds` as a configurable field in the `loops` config section.

**Changes made:**
- `config-schema.json`: Added `queue_wait_timeout_seconds` (integer, default 3600, minimum 1) to `loops` properties
- `scripts/little_loops/config/features.py`: Added field to `LoopsConfig` dataclass and `from_dict`
- `scripts/little_loops/config/core.py`: Added field to `BRConfig.to_dict` loops serialization
- `scripts/little_loops/cli/loop/run.py`: Replaced hardcoded `timeout=3600` with `timeout=_config.loops.queue_wait_timeout_seconds`
- `scripts/tests/test_config.py`: Added `TestLoopsConfig` class and assertion in `test_to_dict`
- `docs/guides/LOOPS_GUIDE.md`: Added note about configurable timeout in queue and background+queue sections
- `docs/development/TROUBLESHOOTING.md`: Added `loops.queue_wait_timeout_seconds` entry alongside existing timeout knobs

**Completed** | Created: 2026-04-21 | Completed: 2026-04-23 | Priority: P3
