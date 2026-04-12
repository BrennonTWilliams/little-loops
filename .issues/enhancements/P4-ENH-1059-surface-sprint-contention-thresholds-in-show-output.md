---
discovered_date: 2026-04-12T17:20:00Z
discovered_by: capture-issue
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

### Tests
- `scripts/tests/` — any existing sprint show/render tests

### Configuration
- `config-schema.json` — `dependency_mapping.overlap_min_files`, `dependency_mapping.overlap_min_ratio` (already present)

## Implementation Steps

1. Add a `config_snapshot: dict | None` field to `WaveContentionNote` (or pass thresholds separately)
2. Populate it with `{"min_files": config.overlap_min_files, "ratio": config.overlap_min_ratio}` in `refine_waves_for_contention()`
3. In `_render_execution_plan()`, when `is_contention`, append `[min_files=N, ratio=X.XX]` to the header label
4. Add a tuning hint line after the `Contended files:` line
5. Update tests

## Impact

- **Priority**: P4 — Discoverability improvement; low effort, useful for sprint tuning
- **Effort**: Small — Display change plus one dataclass field
- **Risk**: Low — Display-only
- **Breaking Change**: No

## Labels

`enhancement`, `sprint`, `ux`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-12T17:20:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d397308b-e908-423f-9d30-383270c713d4.jsonl`

## Status

**Open** | Created: 2026-04-12 | Priority: P4
