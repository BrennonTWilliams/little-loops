---
discovered_date: 2026-04-01
discovered_by: capture-issue
---

# BUG-913: `context_passthrough` passes full JSON capture object instead of issue ID string to sub-loop

## Summary

When `issue-refinement` uses `context_passthrough: true` to pass the parsed issue ID to `refine-to-ready-issue`, the sub-loop receives the full serialized capture object (`{'output':'ENH-8975','stderr':'','exit_code':0,'duration_ms':4}`) in `context.input` rather than the plain issue ID string (`ENH-8975`). Every command in the sub-loop is invoked with this JSON blob as the issue ID argument, e.g. `/ll:format-issue {'output':'ENH-8975',...} --auto`.

## Current Behavior

- `parse_id` state in `issue-refinement.yaml` captures shell output `ENH-8975` under key `"input"`
- `run_refine_to_ready` passes context to sub-loop via `context_passthrough: true`
- Sub-loop `resolve_issue` reads `${context.input}` → outputs `{'output':'ENH-8975','stderr':'','exit_code':0,'duration_ms':4}`
- All subsequent slash commands receive the JSON blob as the issue identifier:
  ```
  /ll:format-issue {'output':'ENH-8975','stderr':'','exit_code':0,'duration_ms':4} --auto
  /ll:refine-issue {'output':'ENH-8975','stderr':'','exit_code':0,'duration_ms':4} --auto
  /ll:confidence-check {'output':'ENH-8975','stderr':'','exit_code':0,'duration_ms':4}
  ```

## Expected Behavior

`context.input` in the sub-loop should be the plain string `ENH-8975`. The `resolve_issue` state should output `ENH-8975`, and commands should be called as `/ll:format-issue ENH-8975 --auto`.

## Motivation

Currently this only works because LLM-based slash commands can infer the real issue ID from the JSON blob. Any future sub-loop state that uses `context.input` in a pure shell command would silently receive the wrong value. It also makes logs harder to read and debug, and could break if the serialization format of captured objects ever changes.

## Root Cause

- **File**: `scripts/little_loops/loops/issue-refinement.yaml`
- **Anchor**: `run_refine_to_ready` state (`context_passthrough: true`)
- **Cause**: `context_passthrough` serializes the parent loop's full captured context map and makes it available as `context.*` in the sub-loop. The `parse_id` capture key is `"input"`, but what gets stored is the full capture result object (including `output`, `stderr`, `exit_code`, `duration_ms`) rather than just the `.output` string. The sub-loop's `resolve_issue` then echoes this whole object verbatim.

The FSM executor's `context_passthrough` implementation needs to either:
- Pass only the `.output` field of each captured value, or
- Document that consumers must dereference `.output` explicitly (e.g. `${context.input.output}`)

## Steps to Reproduce

1. Run `ll-loop run issue-refinement <issue-ids>`
2. Observe `resolve_issue` output: `{'output':'ENH-XXXX','stderr':'','exit_code':0,'duration_ms':N}`
3. Observe subsequent slash commands called with JSON blob as issue ID argument

## Proposed Solution

Two options:

**Option A — Fix at FSM executor level (preferred):** When `context_passthrough: true`, pass only the `.output` string of each capture entry rather than the full capture object. This makes `${context.input}` equal to `ENH-8975` as intended.

**Option B — Fix at YAML level:** Update `resolve_issue` in `refine-to-ready-issue.yaml` to explicitly extract the output field:
```yaml
resolve_issue:
  action: >-
    { [ -n "${context.input}" ] && printf '%s' "${context.input}" ||
    ll-issues next-issue; } | python3 -c "import sys,json,re; s=sys.stdin.read().strip();
    m=re.search(r\"'output':\\s*'([^']+)'\", s); print(m.group(1) if m else s)" | tr -d '\n\r '
```

Option A is cleaner and fixes the issue for all current and future sub-loops.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop` method: `context_passthrough` block (around line 589) spreads full capture dicts into child context instead of `.output` strings

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/issue-refinement.yaml` — uses `context_passthrough: true`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — consumes `${context.input}`
- `scripts/little_loops/loops/examples-miner.yaml` — uses `context_passthrough: true`
- `scripts/little_loops/loops/prompt-regression-test.yaml` — uses `context_passthrough: true`
- `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml` — uses `context_passthrough: true`

### Similar Patterns
- All 5 loops above use `context_passthrough: true` and may be affected by the fix

### Tests
- `scripts/tests/test_fsm_executor.py` — existing test `test_sub_loop_context_passthrough` covers this behavior and will need updating

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Locate the FSM executor code that implements `context_passthrough`
2. Determine whether captures are stored as full objects or just `.output` strings
3. Apply Option A (pass `.output` only) or Option B (fix YAML extraction) based on findings
4. Verify with a test run that `resolve_issue` outputs the plain issue ID

## Impact

- **Priority**: P3 — Currently masked by LLM resilience; no observed failures, but fragile and confusing
- **Effort**: Small — Localized to FSM executor or one YAML state
- **Risk**: Low — Change affects how context is passed to sub-loops; need to check all `context_passthrough` usages
- **Breaking Change**: Potentially — If any sub-loop intentionally reads the full capture object (unlikely)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `fsm`, `context-passthrough`, `captured`

## Resolution

**Status**: Fixed
**Approach**: Option A — FSM executor level fix

In `scripts/little_loops/fsm/executor.py`, the `_execute_sub_loop` method's `context_passthrough` block was spreading `self.captured` directly into `child_fsm.context`. Since captured values are stored as full dicts (`{"output": ..., "stderr": ..., "exit_code": ..., "duration_ms": ...}`), child contexts received those dicts instead of plain strings.

**Fix** (line ~590): Extract `.output` string from capture result dicts before spreading into child context:
```python
captured_as_context = {
    k: v["output"] if isinstance(v, dict) and "exit_code" in v else v
    for k, v in self.captured.items()
}
child_fsm.context = {**self.fsm.context, **captured_as_context, **child_fsm.context}
```

**Test added**: `test_sub_loop_context_passthrough_captured_values` in `test_fsm_executor.py` — verifies a captured shell output is received as a plain string in the child loop's context.

## Session Log
- `/ll:manage-issue` - 2026-04-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:ready-issue` - 2026-04-02T02:58:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dab3a3df-4969-489e-998b-1844664bee57.jsonl`
- `/ll:capture-issue` - 2026-04-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eaf73d5c-81eb-45a4-a5e6-b157f77ba059.jsonl`

---

**Completed** | Created: 2026-04-01 | Resolved: 2026-04-01 | Priority: P3
