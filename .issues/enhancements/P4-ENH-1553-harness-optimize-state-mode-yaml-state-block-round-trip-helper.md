---
id: ENH-1553
type: ENH
priority: P4
status: open
parent: ENH-1535
---

# ENH-1553: harness-optimize State-Mode — YAML State-Block Round-Trip Helper

## Summary

Implement `scripts/little_loops/loops/yaml_state_editor.py` — a utility module that uses `ruamel.yaml` (round-trip mode) to extract and replace a named state's `action:` block within a loop YAML, preserving block scalar formatting. Add `ruamel.yaml` as an explicit package dependency. This helper is the foundation for state-mode mutation in ENH-1554.

## Parent Issue

Decomposed from ENH-1535: Meta-APO — Per-FSM-State Targeting for harness-optimize

## Covers (from ENH-1535 Implementation Steps)

- Step 1: Add `ruamel.yaml` to `scripts/pyproject.toml`
- Step 4: Write YAML state-block round-trip helper
- Step 8 (unit-test portion): extraction, `replace_action()` modifies only the target state, siblings/other states unchanged; in-place rewrite preserves `action: |` block scalar formatting

## Background

All current YAML reads in the codebase use `yaml.safe_load` (PyYAML). `yaml.safe_load` + `yaml.dump` round-tripping loses `action: |` literal block scalar formatting — multi-line action strings become flow-style or quoted. `ruamel.yaml` must be used for write-back to preserve formatting. Using plain PyYAML will silently corrupt the loop YAML. See `scripts/little_loops/frontmatter.py`:`update_frontmatter()` for the canonical in-place YAML block replacement pattern (uses regex-boundary + `yaml.safe_load`; the new helper should use `ruamel.yaml` instead to preserve block scalars).

## Implementation Steps

1. **`scripts/pyproject.toml`**:
   - Add `ruamel.yaml` to the package dependencies (currently absent from codebase)

2. **`scripts/little_loops/loops/yaml_state_editor.py`** (new module):
   - `extract_action(loop_yaml_path: Path, state_name: str) -> str` — use `ruamel.yaml` `YAML(typ="rt")` to load the file, return the `states[state_name]["action"]` string
   - `replace_action(loop_yaml_path: Path, state_name: str, new_action: str) -> None` — load with `ruamel.yaml`, set `states[state_name]["action"]`, write back in-place preserving block scalars and surrounding keys
   - Do NOT use `yaml.safe_load` for write-back (loses `|` block scalar formatting)
   - Do NOT use regex on `action: |` blocks (brittle under indentation changes)
   - The helper operates on any loop YAML — it has no knowledge of `harness-optimize.yaml` specifically

3. **`scripts/tests/test_harness_optimize.py`** (unit test addition):
   - Write a fixture loop YAML to `tmp_path` with at least 2 states (each with a multi-line `action: |` block)
   - Test `extract_action()` returns the correct action text for each named state
   - Test `replace_action()` modifies only the targeted state's action text
   - Test `replace_action()` preserves sibling keys in the modified state (`prompt`, `type`, etc.)
   - Test `replace_action()` leaves other states entirely unchanged
   - Test that the written YAML preserves `action: |` block scalar style (not `action: "..."` quoted)

## Files to Modify

- `scripts/pyproject.toml` — add `ruamel.yaml` dependency
- `scripts/little_loops/loops/yaml_state_editor.py` — new module (create)
- `scripts/tests/test_harness_optimize.py` — add unit tests for `yaml_state_editor`

## Acceptance Criteria

- [ ] `ruamel.yaml` listed in `scripts/pyproject.toml` dependencies
- [ ] `extract_action()` returns correct action text for a named state
- [ ] `replace_action()` writes only the target state's action; sibling keys and other states are unchanged
- [ ] Written YAML preserves `action: |` block scalar formatting (verified by round-trip assertion in test)
- [ ] All new unit tests pass

## Ordering

Can be worked in parallel with ENH-1552 (schema + validation foundation). ENH-1554 depends on this child.

## Session Log
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e5cf22fe-a508-4b58-ace6-dd0a2c4187a3.jsonl`
