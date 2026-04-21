---
captured_at: "2026-04-21T19:06:11Z"
discovered_date: "2026-04-21"
discovered_by: capture-issue
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
  "description": "Seconds to wait for a conflicting scope lock to be released when --queue is used. 0 = wait indefinitely.",
  "default": 3600,
  "minimum": 0
}
```

2. In `scripts/little_loops/cli/loop/run.py`, read the value from config and pass it through:

```python
# Before the queue wait block
queue_timeout = config.loops.get("queue_wait_timeout_seconds", 3600)
if not lock_manager.wait_for_scope(scope, timeout=queue_timeout or None):
```

(`0` maps to `None` for indefinite wait if `wait_for_scope` supports that; otherwise clamp to a large sentinel.)

## Integration Map

### Files to Modify
- `config-schema.json` — add `queue_wait_timeout_seconds` to `loops` properties
- `scripts/little_loops/cli/loop/run.py` — read config value, replace hardcoded `3600`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/lock_manager.py` (or equivalent) — verify `wait_for_scope` accepts `None`/`0` for indefinite wait

### Similar Patterns
- `config-schema.json` `automation.timeout_seconds` — same shape: integer, minimum 0, default 3600
- `config-schema.json` `sprints.default_timeout` — same shape

### Tests
- `scripts/tests/` — add/update tests for queue timeout resolution from config; mock `wait_for_scope` to verify correct value is passed

### Documentation
- `docs/reference/API.md` — if `loops` config section is documented, add the new field
- `docs/` loop usage docs if they mention `--queue` behaviour

### Configuration
- `config-schema.json` — the primary change

## Implementation Steps

1. Add `queue_wait_timeout_seconds` field to `loops` in `config-schema.json` with default `3600` and minimum `0`
2. Update config loading/dataclass for the `loops` section to expose the new field
3. In `run.py`, replace the hardcoded `timeout=3600` with the config-sourced value
4. Handle `0` → indefinite-wait mapping if `wait_for_scope` supports it
5. Add/update tests asserting config value is forwarded correctly
6. Update relevant docs and schema changelog

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

- `/ll:capture-issue` - 2026-04-21T19:06:11Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/292a62ed-c8c7-4b31-bc37-39202571d4c4.jsonl`

---

**Open** | Created: 2026-04-21 | Priority: P3
