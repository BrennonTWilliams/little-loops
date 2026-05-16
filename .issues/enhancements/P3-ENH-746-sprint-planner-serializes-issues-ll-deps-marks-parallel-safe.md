---
id: ENH-746
type: ENH
priority: P3
status: active
discovered_date: 2026-03-14
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 79
---

# ENH-746: Sprint Planner Serializes Issues That `ll-deps` Marks Parallel-Safe

## Motivation

`ll-deps analyze` and `ll-sprint show` use different overlap detection algorithms with mismatched thresholds. This causes `ll-sprint` to serialize issues into N sequential steps even when `ll-deps` reports them as parallel-safe — eliminating the throughput benefit of running a sprint.

In the `fsm-loop-and-refactors` sprint (11 issues), `ll-deps` found 7 parallel-safe pairs (0–20% conflict score), but `ll-sprint` serialized all 11 into 11 sequential steps. Expected: multiple issues run concurrently per wave.

## Current Behavior

- `ll-deps analyze` uses a **semantic conflict score** (file overlap ratio + content analysis). Pairs are "parallel-safe" when score < 0.4.
- `refine_waves_for_contention` uses `file_hints.overlaps_with()` with hard-coded thresholds:
  - `MIN_OVERLAP_FILES = 2` — any 2 shared files triggers contention (no ratio weighting)
  - Shared directory paths (depth ≥ 2)
  - **Shared scope/component names** (`self.scopes & other.scopes`) — coarse-grained signal that fires on any FSM/loop-related issues in the same sprint
- With 11 issues all touching FSM/loop code, scope matching serializes every pair → greedy graph coloring assigns each its own color → 11 sub-waves.

## Desired Behavior

Issues that `ll-deps` identifies as parallel-safe (conflict score < 0.4) should be schedulable in the same wave by `ll-sprint`. The two systems should agree on what constitutes a real contention.

## Implementation Steps

1. Identify the correct threshold to use in `file_hints.overlaps_with()` — options:
   - **Option A**: Replace binary `overlaps_with()` with conflict-score-based check (align with `ll-deps` ≥ 0.4 threshold)
   - **Option B**: Raise `MIN_OVERLAP_FILES` from 2 → 3 or 4
   - **Option C**: Disable scope matching as a contention signal in the sprint planner (scopes are too coarse for focused sprints)
   - **Option D**: Hybrid — keep file thresholds but remove scope matching from `overlaps_with()` in contention context
2. Update `refine_waves_for_contention` in `scripts/little_loops/dependency_graph.py` to use the chosen threshold
3. Update `file_hints.overlaps_with()` in `scripts/little_loops/parallel/file_hints.py` if needed, or add a separate `contends_with()` method with sprint-appropriate thresholds
4. Add a test: sprint with `ll-deps`-parallel-safe issues should produce multi-issue waves
5. Verify `fsm-loop-and-refactors` sprint shows parallelization after fix

### Implementation Risk Factors

_Added by `/ll:confidence-check`:_

1. **Option selection**: Option D (remove scope matching from `overlaps_with()`, retain it in a new `contends_with()` for the worktree isolation path) is the recommended approach. Before removing scope matching from `overlaps_with()`, confirm whether `overlap_detector.py:125` actually relies on scope matching for correctness — a grep of how `OverlapDetector` is used in the worktree isolation path will settle this. If scope matching is load-bearing there, the `contends_with()` split is required; if not, a direct removal is simpler.

2. **`overlap_detector.py` caller impact**: `overlap_detector.py:125` is the second caller of `overlaps_with()` (worktree isolation path). Modifying `overlaps_with()` without auditing this caller risks breaking concurrent worktree safety. Verify before changing the shared method signature or behavior.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Root cause precision**: Serialization is driven by Check 4 (scope matching) in `file_hints.py:142–144`:

```python
if self.scopes & other.scopes:
    return True
```

`SCOPE_PATTERN` (`file_hints.py:33–36`) is applied to the **entire** issue markdown. Any shared keyword like `component: cli`, `module: scripts`, or `scope: fsm` immediately causes `overlaps_with()` to return `True` with no count or ratio guard — unlike Check 1 which has `MIN_OVERLAP_FILES=2` and `OVERLAP_RATIO_THRESHOLD=0.25` guards. In a sprint where all issues touch FSM/loop code, every pair matches on scope → greedy coloring assigns each its own color.

**Option D (recommended, confirmed-required)**: Remove the scope-match block at `file_hints.py:142–144` and introduce a separate `contends_with()` that retains scope checking for the worktree isolation path. **Scope matching IS load-bearing in `overlap_detector.py`**: `check_overlap()` at `overlap_detector.py:106` calls `overlaps_with()` at `:125` to guard concurrent worktree dispatch in `ll-parallel`. If scope matching is removed from `overlaps_with()` without a `contends_with()` replacement, issues sharing only a scope name could be dispatched concurrently to worktrees — risking runtime merge conflicts not caught by static file analysis. The `contends_with()` split is **required**, not optional. `overlap_detector.py:129–131` further confirms the reliance: when scope matching triggers, `result.overlapping_files` is empty (logged as "scope/directory overlap"), meaning scope matching is the sole safety net for that case.

**Option A (full `ll-deps` alignment)**: Insert a `compute_conflict_score()` call (`analysis.py:188`) as a second gate in `refine_waves_for_contention()` (`dependency_graph.py:382`). Only separate issues into sub-waves when `overlaps_with()` AND `conflict_score >= config.conflict_threshold` (default `0.4`). Requires importing `compute_conflict_score` from `little_loops.dependency_mapper.analysis`.

**Note**: `dependency_mapper` is a package, not a single file. The conflict score logic lives in `scripts/little_loops/dependency_mapper/analysis.py:188` (`compute_conflict_score`) and `:243` (`find_file_overlaps`). The `0.4` threshold is at `analysis.py:330`.

**New test pattern** — model after `test_dependency_graph.py:664` (`TestRefineWavesForContention`):
- Use `_make_issue_with_content()` helper at `test_dependency_graph.py:637`
- Two issues with identical `scope: fsm` but non-overlapping file sets → should produce one wave after fix
- Integration validation: `ll-sprint show fsm-loop-and-refactors` should show multi-issue waves

## Affected Files

- `scripts/little_loops/parallel/file_hints.py:39–41` — `MIN_OVERLAP_FILES`, `OVERLAP_RATIO_THRESHOLD`, `MIN_DIRECTORY_DEPTH` constants
- `scripts/little_loops/parallel/file_hints.py:84–146` — `FileHints.overlaps_with()` (Check 4 scope match at `:142–144`)
- `scripts/little_loops/dependency_graph.py:340–429` — `refine_waves_for_contention()`, greedy coloring at `:403–409`
- `scripts/little_loops/dependency_graph.py:382` — sole call site for `overlaps_with()` in contention path
- `scripts/little_loops/cli/sprint/show.py:185` — calls `refine_waves_for_contention(waves, config=dep_config)`
- `scripts/little_loops/dependency_mapper/analysis.py:188` — `compute_conflict_score()` (reference for alignment)
- `scripts/little_loops/dependency_mapper/analysis.py:243` — `find_file_overlaps()`, `conflict_threshold=0.4` at `:330`
- `scripts/little_loops/config.py:432–493` — `DependencyMappingConfig` (all thresholds; add `use_scope_matching: bool` if configurable)
- `scripts/little_loops/parallel/overlap_detector.py` — second caller of `overlaps_with()`; check before removing scope matching

## Integration Map

### Callers of `refine_waves_for_contention()`
- `scripts/little_loops/cli/sprint/show.py:185` — `refine_waves_for_contention(waves, config=dep_config)`
- `scripts/little_loops/cli/sprint/run.py:211` — `refine_waves_for_contention(waves, config=config.dependency_mapping)`
- `scripts/little_loops/cli/sprint/manage.py:111` — `refine_waves_for_contention(waves, config=dep_config)`

### Callers of `overlaps_with()`
- `scripts/little_loops/dependency_graph.py:382` — contention path (this issue)
- `scripts/little_loops/parallel/overlap_detector.py:125` — worktree isolation (may need scope matching; check before modifying)
- `scripts/little_loops/cli/sprint/manage.py:122` — conflict detection in sprint manage output (pairwise audit loop)

### Conflict Score (Reference — `ll-deps` side)
- `scripts/little_loops/dependency_mapper/analysis.py:188` — `compute_conflict_score(content_a, content_b)`
- `scripts/little_loops/dependency_mapper/analysis.py:330` — `conflict_threshold = config.conflict_threshold if config else 0.4`
- `scripts/little_loops/dependency_mapper/analysis.py:243` — `find_file_overlaps()` — produces `ParallelSafePair` objects

### Tests
- `scripts/tests/test_file_hints.py:262` — `TestFileHintsOverlap` (threshold boundary tests)
- `scripts/tests/test_file_hints.py:603` — `TestConfigurableThresholds` (config override pattern)
- `scripts/tests/test_dependency_graph.py:637` — `_make_issue_with_content()` helper (use for new test)
- `scripts/tests/test_dependency_graph.py:664` — `TestRefineWavesForContention` (model new test here)
- `scripts/tests/test_dependency_mapper.py:122` — `TestComputeConflictScore` (conflict score boundary)
- `scripts/tests/test_dependency_mapper.py:201` — parallel-safe classification reference test
- `scripts/tests/test_sprint_integration.py` — integration-level sprint wave tests

---

## Session Log
- `/ll:capture-issue` - 2026-03-14T17:20:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bbba52dd-723c-4153-b516-f72f796098d4.jsonl`
- `/ll:refine-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d4f8ab9f-1efb-428f-b354-1f4d317af06f.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c0cfcb50-cb6d-4bdb-bcf5-8e42ca20dd02.jsonl`
- `/ll:refine-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d24d5545-ed0e-442c-bda6-db81c236d356.jsonl`
- `/ll:ready-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/33fcb067-47f1-425b-a171-05818ef871c0.jsonl`

---

## Resolution

**Implemented Option D** — removed scope matching from `overlaps_with()` and introduced `contends_with()` that retains scope checking for worktree isolation.

### Changes

- `file_hints.py`: Removed scope-match block from `overlaps_with()` (lines 142–144). Added `contends_with()` method that delegates to `overlaps_with()` then adds scope matching.
- `overlap_detector.py`: Updated `check_overlap()` to call `contends_with()` instead of `overlaps_with()` — preserves worktree safety.
- `test_file_hints.py`: Updated `test_scope_match` → `test_scope_only_no_file_overlap_not_split` (now asserts `False` for `overlaps_with()`). Added `TestFileHintsContendsWithScope` class testing `contends_with()`.
- `test_dependency_graph.py`: Added `test_shared_scope_no_file_overlap_not_split` regression test in `TestRefineWavesForContention`.

### Verification

All 144 tests pass. Sprint planner no longer serializes scope-only overlaps.

---
## Session Log
- `/ll:manage-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---
## Status

Completed.
