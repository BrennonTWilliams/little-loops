---
discovered_date: 2026-04-12T17:20:00Z
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 79
---

# ENH-1060: Change sprint file-overlap detection from OR to AND logic

## Summary

`FileHints.overlaps_with()` in `file_hints.py:126` uses an OR condition to trigger serialization: if two issues share `>= min_files` files **or** share `>= ratio_threshold` of the smaller set, they are serialized into separate steps. This means a single shared hub file (e.g., `App.jsx`) out of 4 total files hits the 25% ratio threshold alone (`1/4 = 0.25`) and forces serialization — even when the changes to that file are to completely different sections. In focused single-component sprints, this creates large cliques where every issue conflicts with every other, collapsing the wave into fully sequential steps.

## Location

- **File**: `scripts/little_loops/parallel/file_hints.py`
- **Line(s)**: 120–127 (`overlaps_with()` file count + ratio check)
- **Anchor**: `in method overlaps_with`
- **Code**:
```python
shared_files = self_files & other_files
if shared_files:
    smaller_set = min(len(self_files), len(other_files))
    if smaller_set > 0:
        ratio = len(shared_files) / smaller_set
        if len(shared_files) >= min_files or ratio >= ratio_threshold:  # ← OR
            return True
```

## Current Behavior

One shared file out of four is enough to trigger serialization (25% ratio). In a sprint where all issues touch a common hub file like `App.jsx` or `index.ts`, this creates a complete conflict graph (K-N), forcing all N issues into N sequential steps regardless of actual code-section overlap.

## Expected Behavior

Both conditions must be satisfied simultaneously:

```python
if len(shared_files) >= min_files and ratio >= ratio_threshold:  # AND
    return True
```

A single shared hub file no longer triggers serialization unless it represents ≥25% of the smaller set **and** there are at least 2 shared files total. Issues with only trivial file overlap remain in parallel.

## Motivation

The OR condition was conservative — it preferred false positives (unnecessary serialization) over false negatives (merge conflicts). But in focused sprints this over-fires aggressively: 10/11 issues serialized for a single-component viewer sprint, eliminating all meaningful parallelism. The AND condition still catches real conflicts (≥2 files, ≥25%) while allowing single-hub-file pairs to run in parallel where the actual changes won't overlap.

## Proposed Solution

Change line 126 in `file_hints.py` from `or` to `and`:

```python
if len(shared_files) >= min_files and ratio >= ratio_threshold:
```

Update `get_overlapping_paths()` (line 201, same file) identically — it duplicates the same condition for returning the overlapping path set.

## Scope Boundaries

- Only change the boolean operator; do not change default threshold values or other detection paths (directory overlap, file-in-directory)
- `contends_with()` (used for worktree isolation, not sprint scheduling) is unaffected

## Success Metrics

- Two issues sharing only 1 file (below `min_files=2`) no longer trigger serialization
- Two issues sharing 3+ files still serialize
- Existing tests pass or are updated to reflect the new logic

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/file_hints.py` — `overlaps_with()` line 126, `get_overlapping_paths()` line 216
- `scripts/little_loops/dependency_mapper/analysis.py` — line 316, `and` → `or` to align with AND-pass

### Dependent Files (Callers/Importers)
- `scripts/little_loops/dependency_graph.py` — `refine_waves_for_contention()` calls `get_overlapping_paths()` at line 383 with `dep_config`
- `scripts/little_loops/cli/sprint/manage.py:122,124` — sprint show/manage entry point; calls `overlaps_with()` at line 122 and `get_overlapping_paths()` at line 124 with `dep_config`; no logic change needed, behavior will automatically follow

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/overlap_detector.py:125` — calls `contends_with()` which delegates to `overlaps_with()` at `file_hints.py:169`; 1-file-per-issue pairs will no longer trigger `has_overlap=True` via this path [Agent 1 finding]

### Consistency Note

_Added by `/ll:refine-issue` — codebase research:_

- `scripts/little_loops/dependency_mapper/analysis.py:316` has an inline guard `if len(overlap) < min_files and ratio < min_ratio: continue`. This is AND-skip logic, logically equivalent to OR-pass. The comment at line 313 reads "matching FileHints.overlaps_with" — after ENH-1060 this comment would become inaccurate if `analysis.py` retained OR-pass. **Decision**: align `analysis.py:316` to AND-pass (`if len(overlap) < min_files or ratio < min_ratio: continue`) to honor the alignment contract. A single shared hub file should not generate a dependency proposal any more than it should force serialization; real conflicts also pass the `conflict_score` gate below. [Agent 2 finding; decision made during confidence check]

### Tests
- `scripts/tests/test_file_hints.py` — overlap detection unit tests; update threshold boundary cases
- `scripts/tests/test_dependency_graph.py` — wave contention tests

_Wiring pass added by `/ll:wire-issue`:_

Additional breaking tests in `test_dependency_graph.py` (not previously listed; all use 1-file-per-issue setups that flip under AND):
- `test_dependency_graph.py:703` — `test_three_issues_two_overlap_one_independent` — `assert len(result) == 2` becomes `len(result) == 1`
- `test_dependency_graph.py:719` — `test_all_three_overlap_pairwise` — `assert len(result) == 3` becomes `len(result) == 1`
- `test_dependency_graph.py:822` — `test_contention_notes_mixed_waves` — wave-notes assertions flip for 1-file pair
- `test_dependency_graph.py:839` — `test_contended_paths_multi_file_overlap` — every pair shares exactly 1 file; `assert len(result) == 3` flips to 1

Tests for `get_overlapping_paths()` in `test_file_hints.py` (the issue only documents `overlaps_with` breaking tests; `get_overlapping_paths` is also changing):
- `test_file_hints.py:424–500` — `TestGetOverlappingPaths` class (11 tests); call `get_overlapping_paths()` directly — verify each against AND semantics [Agent 3 finding]
- `test_file_hints.py:692` — `test_get_overlapping_paths_with_config` inside `TestFileHintsConfig` — calls `get_overlapping_paths()` with custom config [Agent 3 finding]

Tests in `test_overlap_detector.py` (indirect via `contends_with` → `overlaps_with`):
- `test_overlap_detector.py:44` — `test_detect_file_overlap` — 1 shared file; `assert result.has_overlap` flips to False under AND [Agent 2 finding]
- `test_overlap_detector.py:108` — `test_multiple_active_issues` — 1 shared file (count=1 < min_files=2); `assert result.has_overlap` flips to False [Agent 2 finding]

Integration tests in `test_sprint.py` (end-to-end via `manage.py:122` → `overlaps_with`/`get_overlapping_paths`):
- `test_sprint.py:873` — `test_run_shows_dependency_analysis` — fixture uses 1-file-each issues sharing `scripts/config.py`; update assertions [Agent 3 finding]
- `test_sprint.py:946` — `test_show_includes_dependency_analysis` — same fixture [Agent 3 finding]
- `test_sprint.py:1797` — `test_analyze_with_conflicts` — `assert "Conflicts found: 1 pair(s)"` flips; 1-file-each setup [Agent 2 finding]
- `test_sprint.py:1817` — `test_analyze_no_conflicts` — verify still passes (no overlap expected) [Agent 3 finding]
- `test_sprint.py:1847` — `test_analyze_json_format` — `assert data["has_conflicts"] is True` flips to False [Agent 2 finding]
- `test_sprint.py:1872` — `test_analyze_json_no_conflicts` — verify still passes [Agent 3 finding]

Stale comments to update (no assertion flip, but comments reference old OR behavior):
- `test_file_hints.py:653` — comment reads `"both branches of OR fail"`; update to AND [Agent 2 finding]
- `test_file_hints.py:659` — comment and docstring describe OR path leading to True; first assert at line 662 also flips to False [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — specific tests that flip under OR → AND (assertions must be updated):_

**`test_file_hints.py` — will break (rely on ratio arm alone):**
- `test_single_file_in_small_set_meets_ratio` (line 271) — 1 shared of set-of-1, count=1 < 2; currently `True` via ratio=100%; becomes `False`
- `test_ratio_threshold_edge` (line 409) — 1 shared of set-of-1, count=1 < 2, ratio=100%; same flip
- `test_shared_write_target_still_causes_overlap` (line 245) — 1 shared `executor.py` of 2-file sets, count=1 < 2, ratio=0.5; flip to `False`; test name/intent needs update to reflect new behavior
- `test_overlaps_with_stricter_ratio` first assert (line 657, `TestConfigurableThresholds`) — 1 shared of 4, count=1 < 2, ratio=0.25; flip to `False`

**`test_dependency_graph.py` — will break (wave-split assumptions change):**
- `test_two_issues_same_file_split` (line 690) — each issue has 1 file, 1 shared < min_files=2; `len(result)==2` becomes `len(result)==1`
- `test_contention_notes_for_split_wave` (line 803) — same 1-file-each setup; split/notes assertions change

**Unaffected tests (already expect `False` or have ≥2 shared files):**
- `test_single_file_below_ratio_threshold` (line 278) — already expects `False`
- `test_multiple_file_matches` (line 265) — 2 shared files, both arms satisfied

### Configuration
- `config-schema.json` — `dependency_mapping.overlap_min_files`, `dependency_mapping.overlap_min_ratio` (unchanged; AND makes defaults less aggressive without changing their values)

## Implementation Steps

1. In `file_hints.py:126`, change `or` to `and` in `overlaps_with()`
2. Apply the same change in `get_overlapping_paths()` — OR condition is at ~line 216 (function body starts at ~178; "line 201" in the Proposed Solution refers to a line within the function, not the condition itself)
3. Update the 6 tests that rely on the ratio arm alone (see Integration Map → Tests research findings above): flip `assert ... is True` to `assert ... is False` and rename `test_shared_write_target_still_causes_overlap` to reflect the new expected behavior
4. Run `python -m pytest scripts/tests/test_file_hints.py scripts/tests/test_dependency_graph.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. In `dependency_mapper/analysis.py:316`, change `and` to `or` to align with AND-pass: `if len(overlap) < min_files or ratio < min_ratio: continue` — the comment at line 313 ("matching FileHints.overlaps_with") remains accurate
6. Update `test_overlap_detector.py` — `test_detect_file_overlap` (line 44) and `test_multiple_active_issues` (line 108) exercise 1-shared-file pairs through `contends_with`; both `assert result.has_overlap` assertions flip to False under AND
7. Update `test_sprint.py` — integration tests at lines 873, 946, 1797, 1817, 1847, 1872 exercise `overlaps_with`/`get_overlapping_paths` end-to-end via `manage.py:122`; conflict assertions flip for 1-file-per-issue fixture cases (especially `test_analyze_with_conflicts` and `test_analyze_json_format`)
8. Update additional `test_dependency_graph.py` breaking tests (lines 703–717, 719–731, 822–837, 839–863): all use 1-file-per-issue setups; wave-count and contention-path assertions flip
9. Review `TestGetOverlappingPaths` class in `test_file_hints.py` (lines 424–500, 11 tests) and `test_get_overlapping_paths_with_config` (line 692) — these test `get_overlapping_paths()` directly; verify each against AND semantics since `get_overlapping_paths()` is also changing
10. Run full suite: `python -m pytest scripts/tests/test_file_hints.py scripts/tests/test_dependency_graph.py scripts/tests/test_overlap_detector.py scripts/tests/test_sprint.py -v`

## Impact

- **Priority**: P3 — Directly reduces over-serialization in single-component sprints; restores intended parallelism
- **Effort**: Tiny — Two-character change (`or` → `and`) in two lines; test updates required
- **Risk**: Low — Makes detection less conservative; real conflicts (≥2 shared files) still serialize correctly
- **Breaking Change**: No

## Labels

`enhancement`, `sprint`, `parallelism`, `file-hints`, `captured`

## Resolution

**Status**: Completed — 2026-04-12

### Changes Made

1. **`scripts/little_loops/parallel/file_hints.py:126`** — `overlaps_with()`: `or` → `and`
2. **`scripts/little_loops/parallel/file_hints.py:216`** — `get_overlapping_paths()`: `or` → `and`
3. **`scripts/little_loops/dependency_mapper/analysis.py:316`** — aligned guard to AND-pass: `and` → `or`

### Tests Updated

- `test_file_hints.py`: 4 tests renamed/flipped (single-file no longer triggers overlap)
- `test_dependency_graph.py`: 6 tests updated; 1-file-per-issue fixtures replaced with 2-file fixtures
- `test_overlap_detector.py`: 2 tests updated; fixtures updated to 2-file overlap
- `test_sprint.py`: `_setup_analyze_project` overlapping fixture updated to share 2 files
- `test_dependency_mapper.py`: 4 tests updated to reflect AND-pass semantics

### Verification

4526 tests pass (1 pre-existing failure in `test_builtin_loops.py` unrelated to this change).

## Session Log
- `/ll:ready-issue` - 2026-04-12T17:04:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f45e1dff-afbc-4d86-8204-6bcacbd51ec3.jsonl`
- `/ll:wire-issue` - 2026-04-12T16:38:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/46202feb-d001-41be-a52b-687026007370.jsonl`
- `/ll:refine-issue` - 2026-04-12T16:31:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/99267590-1f6b-48a8-b5a5-7586dfb4d27d.jsonl`
- `/ll:capture-issue` - 2026-04-12T17:20:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d397308b-e908-423f-9d30-383270c713d4.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6fd5b1cf-9282-4020-bbe7-2578be1e816e.jsonl`
- `/ll:manage-issue` - 2026-04-12T00:00:00Z - (current session)

## Status

**Completed** | Created: 2026-04-12 | Priority: P3
