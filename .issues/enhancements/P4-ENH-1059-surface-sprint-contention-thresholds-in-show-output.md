---
discovered_date: 2026-04-12T17:20:00Z
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-1059: Surface dependency_mapping thresholds in ll-sprint show output

## Summary

`dependency_mapping.overlap_min_files` and `dependency_mapping.overlap_min_ratio` are already in `config-schema.json` and wired to sprint contention detection (`run.py:222` passes `config.dependency_mapping` to `refine_waves_for_contention()`), but `ll-sprint show` displays no indication of what effective threshold values are in use. When a sprint over-serializes, users have no visual signal that tuning these values in `ll-config.json` could reduce unnecessary steps.

## Location

- **File**: `scripts/little_loops/cli/sprint/_helpers.py`
- **Anchor**: `_render_execution_plan()` — contention summary rendering
- **Related**: `scripts/little_loops/cli/sprint/show.py` — `ll-sprint show` entry point

## Current Behavior

`ll-sprint show` prints `(N issues, serialized — file overlap)` and a `Contended files: ...` line. It does not show which threshold values triggered the serialization or hint that they are tunable via `dependency_mapping` in `ll-config.json`.

## Expected Behavior

When a wave is serialized due to file overlap, `ll-sprint show` appends the effective thresholds to the serialization note, e.g.:

```
Wave 1 (10 issues, serialized — file overlap [min_files=2, ratio=0.25]):
```

Or adds a footer line beneath the contended-files note pointing to the config key:

```
  Contended files: src/viewer/App.jsx +3 more
  Tune: dependency_mapping.overlap_min_files / overlap_min_ratio in ll-config.json
```

## Motivation

The thresholds already exist and are configurable, but they are effectively invisible. A sprint with 10 serialized steps caused by a single hub file (`App.jsx`) looks identical to one where every pair genuinely conflicts. Surfacing the values nudges users toward the right fix (tuning thresholds or the OR→AND logic) without requiring them to read source code.

## Proposed Solution

In `_render_execution_plan()`, when emitting the `serialized — file overlap` label, read the config values (passed through the `WaveContentionNote` or re-read from config) and append them to the label. Add a one-line tuning hint beneath the `Contended files:` line.

## Scope Boundaries

- Display-only change; no logic changes to overlap detection
- Only shown when at least one contention sub-wave exists

## Success Metrics

- `ll-sprint show` output for a serialized wave includes the effective `overlap_min_files` and `overlap_min_ratio` values
- A tuning hint line references `dependency_mapping` in `ll-config.json`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint/_helpers.py` — `_render_execution_plan()` serialization rendering
- `scripts/little_loops/dependency_graph.py` — `WaveContentionNote` dataclass, possibly add `config_snapshot` field

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint/show.py` — calls `_render_execution_plan()`
- `scripts/little_loops/cli/sprint/manage.py` — calls `_render_execution_plan()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/__init__.py:8,28` — imports and re-exports `_render_execution_plan` in `__all__`; new kwarg is additive so no change required, but awareness needed [Agent 1 finding]
- `scripts/little_loops/cli/__init__.py:34,56` — re-exports `_render_execution_plan` at top-level `cli` package (`__all__` comment: "Re-exported for backward compatibility (used in tests)"); tests import via `from little_loops.cli import _render_execution_plan` through this path [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/cli/sprint/_helpers.py:15–26` — `_score_suffix()` builds `[key: value, key: value]` bracket suffixes appended inline to issue lines; ENH extends this style to the wave header using `=` (`[min_files=N, ratio=X.XX]`)
- `scripts/little_loops/cli/sprint/_helpers.py:178–220` — `_render_dependency_analysis()` accepts `config: DependencyMappingConfig | None = None` as a keyword-only arg and reads thresholds with `config.field if config else default`; this is the established pattern for threading config into render functions in this file
- `scripts/little_loops/sync.py:540–543` — existing pattern for surfacing a tunable `ll-config.json` key path in CLI output: `"Increase sync.github.pull_limit in ll-config.json to fetch more."`

### Tests
- `scripts/tests/test_cli.py:953+` — `TestSprintShowDependencyVisualization` class; all contention render tests live here
- `scripts/tests/test_cli.py:956–975` — `_make_issue()` helper used by all contention tests
- `scripts/tests/test_cli.py:1127–1159` — `test_render_execution_plan_with_contention_notes()` — the base test to extend with threshold assertions
- `scripts/tests/test_cli.py:1244–1285` — 3-way split test; asserts `"3 issues, serialized"` and `"Contended files: CLAUDE.md"`
- Import pattern used in all tests: `from little_loops.cli import _render_execution_plan`

_Wiring pass added by `/ll:wire-issue`:_
- **Existing assertions are safe**: Lines 1157, 1209, 1281, 1285 use substring matching (`"in output"`); none assert the full verbatim header string. The bracket suffix is appended after the existing text, and the tuning hint is a new line — no existing assertions break [Agent 3 finding]
- `scripts/tests/test_sprint.py` — integration-level gap: all 13 `_cmd_sprint_show` invocations (lines 963, 984, 1009, 1033, 1059, 1086, 1114, 1138, 1178, 1203, 1240, 1268, 1309) use `config=None`; no test passes a real `BRConfig` with `dependency_mapping`, so the `config=dep_config` thread at `show.py:241` is not exercised end-to-end — **new integration test needed** [Agent 3 finding]
- Construction pattern to follow: `DependencyMappingConfig(overlap_min_files=3, overlap_min_ratio=0.5)` used directly in `test_dependency_mapper.py:453` and `test_file_hints.py:641–643`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/SPRINT_GUIDE.md:57` — code-block example shows `Wave 2 (2 issues, serialized — file overlap):` without the new bracket suffix; will become incomplete when `config` is present [Agent 2 finding]
- `docs/guides/SPRINT_GUIDE.md:62` — code-block example shows `Contended files: src/middleware.py, src/config.py` without the new tuning hint line below it; example will not reflect real output after the change [Agent 2 finding]

### Configuration
- `config-schema.json` — `dependency_mapping.overlap_min_files`, `dependency_mapping.overlap_min_ratio` (already present)

## Implementation Steps

**Preferred approach: add `config` kwarg to `_render_execution_plan()` — do NOT modify `WaveContentionNote`**

Research confirms `WaveContentionNote` currently stores only `contended_paths`, `sub_wave_index`, `total_sub_waves`, `parent_wave_index` (`dependency_graph.py:21–28`). The established pattern (matching `_render_dependency_analysis()` at `_helpers.py:178`) is to accept `config: DependencyMappingConfig | None = None` as a keyword-only arg.

1. **Extend `_render_execution_plan()` signature** (`_helpers.py:29–33`) — add `config: DependencyMappingConfig | None = None` as a keyword-only parameter; add `from little_loops.config.automation import DependencyMappingConfig` to imports
2. **Update serialization label** (`_helpers.py:88–89`) — when `config` is not None, append bracket suffix to the f-string:
   ```python
   suffix = f" [min_files={config.overlap_min_files}, ratio={config.overlap_min_ratio}]" if config else ""
   f"Wave {logical_num} ({group_count} issues, serialized \u2014 file overlap{suffix}):"
   ```
3. **Add tuning hint** (`_helpers.py:127`, inside the `if first_note:` block) — append a new line immediately after the `Contended files:` line:
   ```python
   lines.append("  Tune: dependency_mapping.overlap_min_files / overlap_min_ratio in ll-config.json")
   ```
   Guard this line on `config is not None` to keep output clean when config is unavailable.
4. **Thread `dep_config` into call sites** (`show.py:241`, `manage.py:206` only):
   - `show.py:241` — `_render_execution_plan(waves, dep_graph, contention_notes, config=dep_config)`
   - `manage.py:206` — same pattern; `dep_config` is already a local variable at line 110
   - `run.py` — **confirmed NOT a caller** (wiring analysis: `run.py` uses its own inline `logger.info` loop at lines 226–236 and does not call `_render_execution_plan` at all; skip)
5. **Update tests** — extend `test_render_execution_plan_with_contention_notes()` (`test_cli.py:1127`) to pass a `DependencyMappingConfig(overlap_min_files=3, overlap_min_ratio=0.3)` and assert `"[min_files=3, ratio=0.3]"` and `"Tune: dependency_mapping"` appear in output; also verify defaults when `config=None`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add integration test in `scripts/tests/test_sprint.py` — create a test that calls `_cmd_sprint_show` with a `BRConfig` containing `dependency_mapping` with custom `overlap_min_files`/`overlap_min_ratio`, and assert the bracket suffix and tuning hint appear in the captured output; follow construction pattern from `test_dependency_mapper.py:453`
7. Update `docs/guides/SPRINT_GUIDE.md:57,62` — update the code-block example to show the new wave header format (`[min_files=N, ratio=X.XX]` bracket suffix) and add the tuning hint line beneath `Contended files:` so the guide reflects real output

## Impact

- **Priority**: P4 — Discoverability improvement; low effort, useful for sprint tuning
- **Effort**: Small — Display change plus one dataclass field
- **Risk**: Low — Display-only
- **Breaking Change**: No

## Labels

`enhancement`, `sprint`, `ux`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1baa99ba-28c7-4c49-aab6-1470dc4d3ea3.jsonl`
- `/ll:wire-issue` - 2026-04-12T16:35:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/20d241ab-dea8-47f5-9639-98fcb5822594.jsonl`
- `/ll:refine-issue` - 2026-04-12T16:30:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6ad93ba1-3799-4f99-80ea-185dca355ffa.jsonl`
- `/ll:format-issue` - 2026-04-12T16:27:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a33ea6e0-b58f-416e-afd7-499202f56a45.jsonl`
- `/ll:capture-issue` - 2026-04-12T17:20:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d397308b-e908-423f-9d30-383270c713d4.jsonl`

## Status

**Open** | Created: 2026-04-12 | Priority: P4
