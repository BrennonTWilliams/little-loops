---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
---

# ENH-628: YAML-load + paradigm-detect block duplicated three times across `load_loop`, `load_loop_with_spec`, and `cmd_run`

## Summary

The pattern "open YAML file → `yaml.safe_load` → check `"paradigm" in spec and "initial" not in spec` → branch to `compile_paradigm` or `load_and_validate`" appears three times in the CLI layer: `load_loop()`, `load_loop_with_spec()`, and `cmd_run()` in `run.py`. Any change to paradigm detection logic (e.g., new detection heuristic) must be applied in all three places.

## Location

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Line(s)**: 117–132 and 148–162 (at scan commit: 12a6af0)
- **Anchor**: `in function load_loop()` and `in function load_loop_with_spec()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/cli/loop/_helpers.py#L117-L132)
- **Code**:
```python
# load_loop (lines 122-132):
with open(path) as f:
    spec = yaml.safe_load(f)
if "paradigm" in spec and "initial" not in spec:
    return compile_paradigm(spec)
else:
    return load_and_validate(path)

# Identical in load_loop_with_spec (lines 151-162), plus returns (fsm, spec)
# And again in cmd_run in run.py (lines 36-44)
```

## Current Behavior

Three copies of the same paradigm detection and loading logic exist in the CLI layer. `load_loop_with_spec` already provides the full `(fsm, spec)` return, but `cmd_run` does not use either helper — it re-implements the full pattern itself.

## Expected Behavior

A single internal helper (e.g., `_load_fsm_with_spec(path)`) handles YAML loading and paradigm detection. `load_loop` and `load_loop_with_spec` delegate to it.

## Motivation

Deduplication prevents logic drift. The paradigm detection condition (`"paradigm" in spec and "initial" not in spec`) already has known edge cases (FEAT-634 covers `on_partial` support in paradigm compilers); a future change to detection logic must currently be applied in three places.

## Proposed Solution

```python
def _load_fsm_with_spec(path: Path) -> tuple[FSMLoop, dict]:
    """Load a loop file, auto-compiling paradigm YAML if needed. Returns (fsm, raw_spec)."""
    with open(path) as f:
        spec = yaml.safe_load(f)
    if "paradigm" in spec and "initial" not in spec:
        logger.info(f"Auto-compiling paradigm file: {path}")
        return compile_paradigm(spec), spec
    return load_and_validate(path), spec

def load_loop(name_or_path: str, loops_dir: Path) -> FSMLoop:
    path = resolve_loop_path(name_or_path, loops_dir)
    fsm, _ = _load_fsm_with_spec(path)
    return fsm

def load_loop_with_spec(name_or_path: str, loops_dir: Path) -> tuple[FSMLoop, dict]:
    path = resolve_loop_path(name_or_path, loops_dir)
    return _load_fsm_with_spec(path)
```

`cmd_run` should then call `load_loop` or `load_loop_with_spec` rather than re-implementing the pattern.

## Scope Boundaries

- Refactor only; no behavior changes to detection logic
- `cmd_run` change may require minor integration adjustment

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — extract `_load_fsm_with_spec()`, simplify `load_loop` and `load_loop_with_spec`
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()` should use `load_loop` or `load_loop_with_spec`

### Tests
- `scripts/tests/` — update tests that mock `load_loop`/`load_loop_with_spec` if needed

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Extract `_load_fsm_with_spec(path)` helper in `_helpers.py`
2. Simplify `load_loop` and `load_loop_with_spec` to delegate to it
3. Update `cmd_run` in `run.py` to use `load_loop_with_spec` instead of inline logic

## Impact

- **Priority**: P4 — Maintenance improvement; reduces future maintenance burden
- **Effort**: Small — Simple extraction; no logic changes
- **Risk**: Low — Pure refactor; behavior is unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `loop`, `refactor`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`

---

**Open** | Created: 2026-03-07 | Priority: P4
