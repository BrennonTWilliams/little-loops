---
id: ENH-776
type: ENH
priority: P3
status: active
title: Add `default_timeout` to FSMLoop schema
discovered_date: 2026-03-16
discovered_by: plan
labels:
  - enhancement
  - loops
  - schema
confidence_score: 80
outcome_confidence: 93
---

## Summary

Add a `default_timeout: int | None` field at the loop level in `FSMLoop`. This provides a per-state action timeout fallback without requiring every prompt state to annotate `timeout:` individually. Per-state `timeout:` overrides `default_timeout`; the hardcoded executor fallback (3600s for prompt/LLM, 30s for MCP) applies when neither is set.

## Motivation

This enhancement would:
- Prevent silent SIGKILL bugs: without a loop-level default, any prompt state missing an explicit `timeout:` annotation silently reverts to a 120s hardcoded fallback — causing SIGKILL for slow operations
- Simplify loop authoring: a single `default_timeout` at the loop level eliminates per-state annotation boilerplate and the "missed annotation" class of bugs
- Technical clarity: distinguishes per-state action timeout (new `default_timeout`) from total wall-clock cap (existing `timeout` field); `max_iterations` already bounds overall duration

## Success Metrics

- `loops/issue-refinement.yaml` uses `default_timeout: 3600` with zero per-state `timeout:` overrides
- No SIGKILL caused by missed timeout annotation in any prompt state
- Executor timeout fallback chain: `state.timeout → fsm.default_timeout → hardcoded (3600 prompt / 30 MCP)`

## Scope Boundaries

- **In scope**: `FSMLoop` schema field + serialization, executor fallback chain update, `issue-refinement.yaml` migration, `generalized-fsm-loop.md` documentation
- **Out of scope**: MCP server-level timeout controls; changing per-state `timeout:` semantics (per-state still overrides); any non-FSM timeout configuration

## Proposed Solution

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

## Implementation Steps

1. Add `default_timeout: int | None = None` field to `FSMLoop` dataclass in `schema.py` with `to_dict()`/`from_dict()` serialization
2. Update `executor.py` timeout fallback: `state.timeout or self.fsm.default_timeout or 3600` (prompt/LLM states) and `... or 30` (MCP tool states)
3. Migrate `loops/issue-refinement.yaml` to use `default_timeout: 3600`, remove per-state timeout annotations
4. Document `default_timeout` in `docs/generalized-fsm-loop.md` loop-level settings and Timeouts section
5. Add tests verifying: state with no `timeout` uses `default_timeout`; state with `timeout` overrides it; fallback is 3600 (prompt) / 30 (MCP)

## Acceptance Criteria

- [ ] `FSMLoop` has `default_timeout: int | None = None` field
- [ ] `to_dict()` serializes `default_timeout` when non-None
- [ ] `from_dict()` deserializes `default_timeout` from YAML
- [ ] Executor uses `state.timeout or self.fsm.default_timeout or 3600` for prompt states
- [ ] Executor uses `state.timeout or self.fsm.default_timeout or 30` for MCP tool states
- [ ] `loops/issue-refinement.yaml` uses `default_timeout: 3600` with no per-state timeout overrides
- [ ] Tests verify: state with no `timeout` uses `default_timeout`; state with `timeout` overrides it; fallback is 3600 (prompt) / 30 (MCP)
- [ ] `docs/generalized-fsm-loop.md` documents the new field

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add `default_timeout` field + serialization
- `scripts/little_loops/fsm/executor.py` — update timeout fallback chain (lines ~640, ~644)
- `loops/issue-refinement.yaml` — use `default_timeout: 3600`, remove per-state overrides
- `docs/generalized-fsm-loop.md` — document new field and updated Timeouts section

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:640,644` — only two `state.timeout` callsites; both updated
- `scripts/little_loops/cli/loop/info.py:713-714` — display path reads `state.timeout` for UI only (no timeout logic change needed)
- YAML loop files with per-state `timeout:` that could migrate to `default_timeout` (16 of 19 loops):
  - `loops/fix-quality-and-tests.yaml:25,31,49,66,84`
  - `loops/dead-code-cleanup.yaml:12,46,63,81`
  - `loops/backlog-flow-optimizer.yaml:34,87,99,114`
  - `loops/sprint-build-and-validate.yaml:14,24,46,72,86`
  - `loops/apo-opro.yaml:19,37,59`, `loops/apo-textgrad.yaml:14,26,48`, `loops/apo-contrastive.yaml:16,35`
  - `loops/apo-beam.yaml:15,25,36`, `loops/apo-feedback-refinement.yaml:15,27,56,67`
  - `loops/issue-staleness-review.yaml:23,51,58`, `loops/issue-size-split.yaml:12,34`
  - `loops/issue-discovery-triage.yaml:26`, `loops/docs-sync.yaml:40`, `loops/worktree-health.yaml:26`

### Similar Patterns
- `scripts/little_loops/fsm/schema.py:379-434` — existing `timeout` field on `FSMLoop` uses identical `to_dict()`/`from_dict()` pattern
- `scripts/little_loops/fsm/__init__.py:113,144` — `FSMLoop` is exported; no change needed
- `scripts/little_loops/fsm/validation.py:274,389,419,426,464` — FSMLoop validation; no timeout-specific validation currently
- `scripts/little_loops/fsm/persistence.py:290` — persists FSMLoop; serialization via `to_dict()` covers this

### Tests
- `scripts/tests/test_fsm_executor.py:3171` — `class` for `default_timeout` fallback chain tests (already added)
  - Line 3204 — `test_state_timeout_used_when_set`
  - Line 3211 — `test_default_timeout_used_when_state_has_none`
  - Line 3219 — hardcoded 3600s fallback when neither is set
- `scripts/tests/test_fsm_schema.py:511` — `TestFSMLoop` class; schema serialization tests live here

### Documentation
- `docs/generalized-fsm-loop.md` — primary doc to update

### Configuration
- `loops/issue-refinement.yaml` — migrate to use `default_timeout`

## API/Interface

```python
@dataclass
class FSMLoop:
    # ... existing fields ...
    timeout: int | None = None          # total wall-clock cap (unchanged)
    default_timeout: int | None = None  # per-state action timeout fallback (new)
```

Executor fallback chain (per state execution):
```
state.timeout → fsm.default_timeout → hardcoded (3600 for prompt/LLM, 30 for MCP)
```


## Verification Notes

- **Verdict**: RESOLVED — all acceptance criteria implemented as of 2026-03-16
- `scripts/little_loops/fsm/schema.py:407`: `default_timeout: int | None = None` field added to `FSMLoop` ✅
- `scripts/little_loops/fsm/schema.py:433-434`: `to_dict()` serializes `default_timeout` when non-None ✅
- `scripts/little_loops/fsm/schema.py:470`: `from_dict()` deserializes `default_timeout` ✅
- `scripts/little_loops/fsm/executor.py:640`: MCP path uses `state.timeout or self.fsm.default_timeout or 30` ✅
- `scripts/little_loops/fsm/executor.py:644`: prompt path uses `state.timeout or self.fsm.default_timeout or 3600` ✅
- `loops/issue-refinement.yaml:112`: `default_timeout: 3600` set; no per-state timeout overrides ✅
- `docs/generalized-fsm-loop.md:356,1231,1236,1240`: field documented with three-level description ✅
- Tests: `scripts/tests/test_fsm_executor.py:3171` — full test class for `default_timeout` fallback chain ✅
- **Action needed**: Move to `completed/` directory (requires explicit user approval — skipped in auto mode)

## Session Log
- `/ll:confidence-check` - 2026-03-16T19:21:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:refine-issue` - 2026-03-16T19:20:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:verify-issues` - 2026-03-16T19:09:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:format-issue` - 2026-03-16T19:06:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
