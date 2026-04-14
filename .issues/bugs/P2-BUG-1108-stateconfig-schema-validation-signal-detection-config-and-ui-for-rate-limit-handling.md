---
parent: BUG-1105
priority: P2
type: BUG
size: Large
---

# BUG-1108: StateConfig Schema, Validation, Signal Detection, Config, and UI for Rate Limit Handling

## Summary

Decomposed from BUG-1105: FSM Loops Silently Skip All Work on 429 Rate Limit Failures.

This child covers the data model layer and all wiring that surrounds the core executor change: new `StateConfig` fields, paired validation, JSON schema update, `RATE_LIMIT_STORM` signal rule, schema registry entry, diagram edge rendering, user-configurable edge colors, `with_rate_limit_handling` fragment in `common.yaml`, and opt-in wiring in the affected loop YAML configs.

## Scope

### StateConfig Schema (schema.py)

Add `max_rate_limit_retries: int`, `on_rate_limit_exhausted: str`, and `rate_limit_backoff_base_seconds: int` fields using the exact 5-part pattern from `max_retries` / `on_retry_exhausted`:
1. Docstring (`schema.py:187-211`)
2. Field declaration (`schema.py:228-229`) — `rate_limit_backoff_base_seconds` defaults to `30`
3. `to_dict` serialization (`schema.py:270-273`)
4. `from_dict` deserialization + register `on_rate_limit_exhausted` in `_known_on_keys` set (`schema.py:305-338`)
5. `get_referenced_states` (`schema.py:362-363`) — `on_rate_limit_exhausted` only; `rate_limit_backoff_base_seconds` is not a state reference

### Paired Validation (validation.py)

Add validation at `validation.py:280-301` (mirror of `max_retries` / `on_retry_exhausted` paired validation): `max_rate_limit_retries` and `on_rate_limit_exhausted` required together; `max_rate_limit_retries >= 1`. Also validate `rate_limit_backoff_base_seconds >= 1` when present (standalone — does not require the paired fields).

### JSON Schema (fsm-loop-schema.json)

Update JSON Schema for the two new `StateConfig` fields.

### Signal Detection (signal_detector.py)

Add `RATE_LIMIT_STORM` pattern/rule. Note: `SignalPattern` instances match text in `action.output`; the correct model is a consecutive-exhaustion counter in the executor that emits the event — see BUG-1107. The signal rule here should detect consecutive `rate_limit_exhausted` events and emit a halt/pause signal.

### Schema Registry (generate_schemas.py)

Add `rate_limit_exhausted` entry to `SCHEMA_DEFINITIONS` at `generate_schemas.py:78-290` (manual registry, not auto-discovered). Update count docstring in `cli/schemas.py:15` (19 → 20).

### Config + UI (config/cli.py, config/core.py, layout.py)

- `config/cli.py:86` — add `rate_limit_exhausted: str` color field to `CliColorsEdgeLabelsConfig` (parallel to `retry_exhausted: str`)
- `config/core.py:475-484` — add `"rate_limit_exhausted"` to the `fsm_edge_labels` dict in `BRConfig.to_dict()`
- `layout.py:27-36` — add `"rate_limit_exhausted"` to `_EDGE_LABEL_COLORS` dict
- `layout.py:62-74` — add `"rate_limit_exhausted"` to `_edge_line_color()` priority tuple
- `layout.py:201-202` — add `on_rate_limit_exhausted` diagram edge (mirrors `on_retry_exhausted`)

### Fragment Library (common.yaml)

Add `with_rate_limit_handling` fragment to `scripts/little_loops/loops/lib/common.yaml`. The fragment wires `max_rate_limit_retries` and `on_rate_limit_exhausted` via context interpolation so loops can opt in with a single `fragment:` line. Must include a non-empty `description` field (or `test_all_common_yaml_fragments_have_description` will fail).

### Loop YAML Configs

Update `auto-refine-and-implement` and `recursive-refine` to import `lib/common.yaml` and apply the fragment where per-state exhaustion routing is needed.

## Files to Modify

- `scripts/little_loops/fsm/schema.py`
- `scripts/little_loops/fsm/validation.py`
- `scripts/little_loops/fsm/fsm-loop-schema.json`
- `scripts/little_loops/fsm/signal_detector.py`
- `scripts/little_loops/generate_schemas.py`
- `scripts/little_loops/cli/schemas.py`
- `scripts/little_loops/config/cli.py`
- `scripts/little_loops/config/core.py`
- `scripts/little_loops/cli/loop/layout.py`
- `scripts/little_loops/loops/lib/common.yaml`
- Affected loop YAML configs (`auto-refine-and-implement.yaml`, `recursive-refine.yaml`)
- `scripts/little_loops/fsm/executor.py` — replace the hardcoded `_DEFAULT_RATE_LIMIT_RETRIES = 3` stub with `route_ctx.state.max_rate_limit_retries`, and replace `_DEFAULT_RATE_LIMIT_BACKOFF_BASE = 30` stub with `route_ctx.state.rate_limit_backoff_base_seconds`, once both fields exist in `StateConfig`

## Key Reference Points

- `schema.py:187-229` — `max_retries` / `on_retry_exhausted` pattern to mirror
- `validation.py:280-301` — paired validation pattern
- `layout.py:201` — `on_retry_exhausted` edge to mirror
- `signal_detector.py:73-76` — `SignalPattern` structure
- `generate_schemas.py:78-290` — `SCHEMA_DEFINITIONS` manual registry

## Acceptance Criteria

- [ ] `StateConfig` accepts `max_rate_limit_retries`, `on_rate_limit_exhausted`, and `rate_limit_backoff_base_seconds` (all 5-part pattern steps)
- [ ] Paired validation rejects either of `max_rate_limit_retries` / `on_rate_limit_exhausted` without the other; `max_rate_limit_retries >= 1`; `rate_limit_backoff_base_seconds >= 1` when present
- [ ] `rate_limit_backoff_base_seconds` defaults to `30`; `executor.py` stub constants replaced with reads from `StateConfig`
- [ ] `fsm-loop-schema.json` updated for new fields
- [ ] `RATE_LIMIT_STORM` signal rule detects consecutive exhaustion events
- [ ] `rate_limit_exhausted` entry added to schema registry; count updated to 20
- [ ] `rate_limit_exhausted` edge color configurable via `CliColorsEdgeLabelsConfig`
- [ ] Diagram edges render `on_rate_limit_exhausted` with color
- [ ] `with_rate_limit_handling` fragment in `common.yaml` (with `description` field)
- [ ] `auto-refine-and-implement` and `recursive-refine` opt in via fragment

## Dependencies

- BUG-1107 implements the executor's 429 detection and retry logic, using a hardcoded `_DEFAULT_RATE_LIMIT_RETRIES = 3` stub. This issue (BUG-1108) is responsible for: (a) adding `max_rate_limit_retries` to `StateConfig`, and (b) updating `executor.py` to replace the stub constant with `route_ctx.state.max_rate_limit_retries`. Implement in parallel or after BUG-1107.

## Session Log
- `/ll:issue-size-review` - 2026-04-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4abdbd46-1b62-4801-9d00-a2569583afde.jsonl`

---

## Status

**Open** | Created: 2026-04-14 | Priority: P2
