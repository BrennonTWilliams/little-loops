---
discovered_date: 2026-03-16
discovered_by: plan
---

# ENH-776: Add `default_timeout` to FSMLoop schema

## Summary

Add a `default_timeout: int | None` field at the loop level in `FSMLoop`. This provides a per-state action timeout fallback without requiring every prompt state to annotate `timeout:` individually. Per-state `timeout:` overrides `default_timeout`; the hardcoded executor fallback (3600s for prompt/LLM, 30s for MCP) applies when neither is set.

## Motivation

`executor.py` previously hardcoded `state.timeout or 120` — there was no way to set a loop-wide action timeout default. Every loop had to annotate each prompt state individually, making it easy to miss one and silently revert to a 120s timeout that causes SIGKILL for slow operations. A single `default_timeout` at the loop level makes the intent explicit and prevents the "missed annotation" class of bugs.

The existing loop-level `timeout` field (total wall-clock cap) is unrelated — overall duration is already bounded by `max_iterations`. `default_timeout` is purely the per-state action timeout fallback.

## Implementation

**`scripts/little_loops/fsm/schema.py`**:
- Add `default_timeout: int | None = None` to `FSMLoop` dataclass (after `timeout`)
- Include in `to_dict()` when non-None
- Include in `from_dict()` from `data.get("default_timeout")`

**`scripts/little_loops/fsm/executor.py:644`**:
```python
# Before:
timeout=state.timeout or 120,

# After:
timeout=state.timeout or self.fsm.default_timeout or 3600,
```

MCP tool path at line 640:
```python
timeout=state.timeout or self.fsm.default_timeout or 30,
```

**`loops/issue-refinement.yaml`**:
```yaml
default_timeout: 3600  # all prompt states default to 1 hour
```
Remove all explicit per-state `timeout:` values.

**`docs/generalized-fsm-loop.md`**:
- Document `default_timeout` in loop-level settings schema
- Update the Timeouts section to describe three levels

## Files to Modify

- `scripts/little_loops/fsm/schema.py` — add field + serialization
- `scripts/little_loops/fsm/executor.py` — update timeout fallback chain
- `loops/issue-refinement.yaml` — use `default_timeout: 3600`
- `docs/generalized-fsm-loop.md` — document the new field

## Acceptance Criteria

- [ ] `FSMLoop` has `default_timeout: int | None = None` field
- [ ] `to_dict()` serializes `default_timeout` when non-None
- [ ] `from_dict()` deserializes `default_timeout` from YAML
- [ ] Executor uses `state.timeout or self.fsm.default_timeout or 3600` for prompt states
- [ ] Executor uses `state.timeout or self.fsm.default_timeout or 30` for MCP tool states
- [ ] `loops/issue-refinement.yaml` uses `default_timeout: 3600` with no per-state timeout overrides
- [ ] Tests verify: state with no `timeout` uses `default_timeout`; state with `timeout` overrides it; fallback is 3600 (prompt) / 30 (MCP)
- [ ] `docs/generalized-fsm-loop.md` documents the new field

## Labels

`enhancement`, `loops`, `schema`

## Status

**Open** | Created: 2026-03-16 | Priority: P3
