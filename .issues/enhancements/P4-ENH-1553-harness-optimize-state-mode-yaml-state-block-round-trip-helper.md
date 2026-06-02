---
id: ENH-1553
type: ENH
priority: P4
status: done
completed_at: 2026-05-17T10:28:56Z
parent: ENH-1535
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

## Current Behavior

- All YAML reads use `yaml.safe_load` (PyYAML); `ruamel.yaml` is absent from `scripts/pyproject.toml` dependencies.
- Round-tripping loop YAML via `yaml.safe_load` → `yaml.dump` silently loses `action: |` literal block scalar formatting (multi-line strings become quoted or flow-style).
- `scripts/little_loops/loops/` has no `__init__.py`; it is not an importable Python package.
- No `extract_action` / `replace_action` utility exists anywhere in the codebase.

## Expected Behavior

- `ruamel.yaml>=0.18` is listed in `scripts/pyproject.toml` dependencies.
- `scripts/little_loops/loops/__init__.py` exists, making `loops/` an importable Python package.
- `scripts/little_loops/loops/yaml_state_editor.py` exports `extract_action(loop_yaml_path, state_name) -> str` and `replace_action(loop_yaml_path, state_name, new_action) -> None`.
- Round-tripped YAML preserves `action: |` block scalar style; sibling keys and unmodified states are unchanged.

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. **`scripts/little_loops/loops/__init__.py`** — create as an empty file. The `loops/` directory currently has no `__init__.py` and is not a proper Python package. Every other subpackage (`fsm/`, `issues/`, `dependency_mapper/`) has one. Without it, `from little_loops.loops.yaml_state_editor import extract_action` may fail or rely on namespace package discovery. Create it alongside `yaml_state_editor.py`.

5. **`docs/reference/API.md`** — once `loops/` is a package, add a row for `little_loops.loops` (or `little_loops.loops.yaml_state_editor`) to the module summary table so it matches the documentation pattern for all other subpackages.

6. **`CONTRIBUTING.md`** — update the `loops/` entry (currently "Built-in FSM loop definitions (49 YAML files)") to mention `yaml_state_editor.py`, and add a `loops/` entry to the `little_loops/` package subtree listing (the section is currently missing it entirely).

## Files to Modify

- `scripts/pyproject.toml` — add `ruamel.yaml` dependency
- `scripts/little_loops/loops/__init__.py` — create (empty; makes `loops/` an importable Python package matching convention of every other subpackage)
- `scripts/little_loops/loops/yaml_state_editor.py` — new module (create)
- `scripts/tests/test_harness_optimize.py` — add unit tests for `yaml_state_editor`

## Integration Map

### New Files
- `scripts/little_loops/loops/yaml_state_editor.py` — new module (`extract_action`, `replace_action`)

### Modified Files
- `scripts/pyproject.toml` — add `"ruamel.yaml>=0.18"` to `[project.dependencies]` (follows lower-bound-only convention: `"pyyaml>=6.0"`, `"wcwidth>=0.2"`)
- `scripts/tests/test_harness_optimize.py` — append new test class; existing `BUILTIN_LOOPS_DIR` constant and `loop_data` fixture (`yaml.safe_load`) are reusable

### Utilities to Leverage
- `scripts/little_loops/file_utils.py:atomic_write()` — use in `replace_action()` for safe in-place write-back (tempfile + `os.replace()` avoids partial-write corruption on failure)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- No existing callers yet — `ENH-1554` is the planned downstream consumer; its implementation will `from little_loops.loops.yaml_state_editor import extract_action, replace_action`

### Downstream Dependents
- `ENH-1554` — harness-optimize state-mode wiring depends on this module's `extract_action` / `replace_action` public API

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — module table (lines 24–61) lists every importable `little_loops.*` subpackage; add a row for `little_loops.loops` once `loops/` gains `__init__.py`
- `CONTRIBUTING.md` — line 122 describes `loops/` as "Built-in FSM loop definitions (49 YAML files)"; update to note the `yaml_state_editor` Python module and add `loops/` to the `little_loops/` subtree listing (currently absent from that section)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_harness_optimize.py` — existing `TestHarnessOptimizeFile` / `TestHarnessOptimizeStates` classes are read-only and will not break; append new `TestYamlStateEditor` class (already planned in Implementation Steps)
- `scripts/tests/test_ll_loop_commands.py` — contains the canonical `action: |` block scalar YAML fixture pattern (string concatenation + `tmp_path.write_text()`); use this as the model for writing multi-line action fixtures in `TestYamlStateEditor`

### Reference Patterns
- `scripts/little_loops/frontmatter.py:update_frontmatter()` — canonical in-place YAML rewrite pattern (uses PyYAML; new helper uses `ruamel.yaml` instead to preserve block scalars)
- `scripts/tests/test_fsm_fragments.py:TestResolveFragmentsImport._write_lib()` — `textwrap.dedent` + `tmp_path.write_text()` pattern for multi-line YAML fixtures
- `scripts/tests/test_benchmark_fragment.py:TestBenchmarkFragmentResolution._write_lib()` — same pattern with a `lib/` subdirectory fixture

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `ruamel.yaml` is absent from `scripts/pyproject.toml`; only `pyyaml>=6.0` and `wcwidth>=0.2` are listed under `[project.dependencies]`. Add `"ruamel.yaml>=0.18"` following the lower-bound-only convention.
- When `replace_action()` sets a new action string, wrap it with `ruamel.yaml.scalarstring.LiteralScalarString(new_action)` to force `action: |` block scalar style — assigning a plain `str` lets ruamel choose the style, which produces a quoted or flow scalar for short strings.
- `atomic_write()` in `file_utils.py` uses tempfile + `os.replace()`; use it for the write-back step in `replace_action()` to avoid partial-write corruption.
- `harness-optimize.yaml` states mix `action: |` block scalars (`propose`, `apply`, `load_directive`, `commit_and_log`) and inline quoted strings (`capture_prev`, `baseline_score`). The helper must preserve both styles for states it does not modify.
- New tests should use a class `TestYamlStateEditor` with `tmp_path` fixtures (not the built-in `harness-optimize.yaml`) to keep tests hermetic and independent of loop YAML changes.

## Acceptance Criteria

- [ ] `ruamel.yaml` listed in `scripts/pyproject.toml` dependencies
- [ ] `extract_action()` returns correct action text for a named state
- [ ] `replace_action()` writes only the target state's action; sibling keys and other states are unchanged
- [ ] Written YAML preserves `action: |` block scalar formatting (verified by round-trip assertion in test)
- [ ] All new unit tests pass

## Impact

- **Priority**: P4 — Foundation required by ENH-1554 (state-mode FSM wiring); no user-visible value until that child ships
- **Effort**: Small — New isolated module (~80 lines), no changes to existing code paths
- **Risk**: Low — Adds a new dependency (`ruamel.yaml`) and new files only; no callers until ENH-1554
- **Breaking Change**: No

## Scope Boundaries

Out of scope for this issue:
- State-mode FSM orchestration and harness-optimize integration (ENH-1554)
- Modifying `harness-optimize.yaml` directly
- Replacing existing `yaml.safe_load` usage in other modules
- Any CLI surface or user-facing features

## Labels

`yaml`, `round-trip`, `dependency`, `loops`

## Status

**Open** | Priority: P4 | Parent: ENH-1535

## Ordering

Can be worked in parallel with ENH-1552 (schema + validation foundation). ENH-1554 depends on this child.

## Session Log
- `/ll:manage-issue` - 2026-05-17T10:28:56Z - `current.jsonl`
- `/ll:ready-issue` - 2026-05-17T10:23:56 - `a2d82250-3713-411b-9266-ed7f85038ded.jsonl`
- `/ll:refine-issue` - 2026-05-17T10:14:34 - `0783e89a-8ca1-45e3-8088-edbb380f1e90.jsonl`
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `e5cf22fe-a508-4b58-ace6-dd0a2c4187a3.jsonl`
- `/ll:wire-issue` - 2026-05-17T00:00:00Z - `current.jsonl`
- `/ll:confidence-check` - 2026-05-17T00:00:00Z - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
