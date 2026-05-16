---
discovered_date: 2026-03-12
discovered_by: manual
status: done
completed_at: 2026-03-12T00:00:00Z
---

# BUG-1505: map-dependencies creates spurious dependencies from file overlap

## Summary

`/ll:map-dependencies` appears to generate false dependency relationships between issues based on shared file references (e.g., both touching `orchestrator.py` or `issue_lifecycle.py`) rather than actual logical blocking relationships. This produces `## Blocked By` / `## Blocks` entries that are semantically incorrect.

## Current Behavior

When `/ll:map-dependencies` analyzes issues, it proposes dependencies based on file overlap — if two issues reference the same files, it infers a dependency. This led to FEAT-638 (session log hook) being marked as blocked by FEAT-565 (skill-based issue alignment) and ENH-665 (feature branch config), neither of which are actual prerequisites.

## Expected Behavior

Dependencies should only be created when there is a genuine logical blocking relationship — i.e., one issue's implementation literally cannot proceed until another is completed. File overlap alone is insufficient; many issues touch the same core files without blocking each other.

## Steps to Reproduce

1. Have multiple issues that reference the same files (e.g., `orchestrator.py`, `issue_lifecycle.py`)
2. Run `/ll:map-dependencies`
3. Observe that dependencies are proposed between unrelated issues solely because they touch the same files

## Evidence

FEAT-638 was blocked by:
- **FEAT-565** (align issues to skills) — completely unrelated functionality, shares no logical dependency
- **ENH-665** (feature branch config for ll-parallel) — changes branch behavior, not completion tracking

Both were likely linked because all three issues reference `orchestrator.py` or `issue_lifecycle.py` in their Integration Map sections. The dependencies were manually removed on 2026-03-12.

## Root Cause

- **File**: `scripts/little_loops/dependency_mapper/analysis.py`
- **Anchor**: `find_file_overlaps()` at line ~238
- **Cause**: Multiple compounding issues in the overlap-to-dependency pipeline:

1. **No minimum file count guard** — `find_file_overlaps()` triggers on ANY single shared file path (`overlap = issue_paths[id_a] & issue_paths[id_b]`). Config defines `overlap_min_files=2` and `overlap_min_ratio=0.25` in `DependencyMappingConfig` (`config.py:451-452`) but **these fields are never read** by `find_file_overlaps()`.

2. **Semantic score defaults inflate false positives** — When issues have no extractable PascalCase targets or section keywords, `compute_conflict_score()` defaults both signals to `0.5` ("unknown — moderate") at `analysis.py:224,230`. Combined with the type signal, this easily exceeds the `0.4` conflict threshold for issues that share nothing semantically.

3. **Section keywords are UI-oriented, irrelevant to this project** — `_SECTION_KEYWORDS` at `analysis.py:39-47` maps UI concepts (header, sidebar, modal, footer) that never appear in a CLI/Python project, so this signal almost always defaults to `0.5`.

4. **Common file exclusion not applied** — `find_file_overlaps()` doesn't apply the `exclude_common_files` list from `DependencyMappingConfig`. The exclusion only happens in the separate `FileHints.overlaps_with()` path used by the parallel/wave system (`file_hints.py:118`).

5. **File paths extracted from entire issue content** — `extract_file_paths()` (`text_utils.py:54-90`) extracts paths from ALL issue markdown, not just write-target sections. References in `## Evidence`, `## Similar Patterns`, or documentation sections trigger overlap even when the issues don't modify the same files.

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_mapper/analysis.py` — Apply `overlap_min_files` / `overlap_min_ratio` guards; fix default score for missing semantic signals; add common file exclusion
- `scripts/little_loops/text_utils.py` — Optionally scope `extract_file_paths()` to write-target sections (like `file_hints.py` does)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/deps.py:214` — calls `analyze_dependencies()` which calls `find_file_overlaps()`
- `scripts/little_loops/dependency_mapper/__init__.py:93` — backward-compat alias
- `skills/map-dependencies/SKILL.md` — invokes `ll-deps analyze`

### Similar Patterns
- `scripts/little_loops/parallel/file_hints.py:118-124` — `FileHints.overlaps_with()` correctly uses `min_files` and `ratio_threshold` guards + common file exclusion — **this is the pattern to follow**
- `scripts/little_loops/issue_history/coupling.py:63-66` — Jaccard coupling with `co_occurrence >= 2` minimum
- `scripts/little_loops/issue_discovery/matching.py:62-139` — `FindingMatch` uses graduated thresholds with multi-pass search

### Tests
- `scripts/tests/test_dependency_mapper.py` — existing test suite including `TestFindFileOverlapsSemanticAnalysis` at line 329
- `scripts/tests/test_overlap_detector.py` — overlap detector tests (parallel path)

### Configuration
- `scripts/little_loops/config.py:433-493` — `DependencyMappingConfig` already defines all needed fields (`overlap_min_files`, `overlap_min_ratio`, `min_directory_depth`, `exclude_common_files`)
- `config-schema.json:~631-699` — JSON schema for dependency_mapping section

## Implementation Steps

1. **Apply minimum overlap guards in `find_file_overlaps()`** — Read `config.overlap_min_files` and `config.overlap_min_ratio` after computing the file set intersection at `analysis.py:283`. Skip pairs that don't meet either threshold. Follow the pattern from `FileHints.overlaps_with()` at `file_hints.py:118-124`.

2. **Apply common file exclusion** — Filter `issue_paths` through `config.exclude_common_files` before intersection, matching the behavior in `file_hints.py:44-55`.

3. **Fix default scores for missing semantic signals** — Change the default from `0.5` to `0.0` (or a lower value like `0.2`) at `analysis.py:224,230` when no PascalCase targets or section keywords are extractable. Missing data should reduce confidence, not inflate it.

4. **Add tests** — Add test cases to `test_dependency_mapper.py` covering:
   - Single-file overlap below `overlap_min_files` is rejected
   - Common infrastructure files (e.g., `__init__.py`) don't trigger overlap
   - Issues with no semantic targets score low rather than moderate

5. **Run existing tests** — `python -m pytest scripts/tests/test_dependency_mapper.py -v`

## Impact

- **Priority**: P3 — false dependencies don't break anything but create confusion and block sprint planning
- **Effort**: Medium — the config fields and patterns already exist, just need to be wired into `find_file_overlaps()`
- **Risk**: Low — changes are additive filtering; existing tests cover boundary behavior

## Labels

`bug`, `map-dependencies`, `dependency-analysis`

## Verification Notes

**Verdict: VALID** — All five root cause claims verified against current codebase on 2026-03-12. File paths, line numbers, and described behavior are accurate. Config fields `overlap_min_files`/`overlap_min_ratio`/`exclude_common_files` remain unwired in `find_file_overlaps()`. Default scores of `0.5` for missing signals confirmed. `FileHints.overlaps_with()` pattern reference is correct.

## Session Log
- `/ll:refine-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b9abf4ea-ec20-4f60-acc1-924aff82a162.jsonl`
- `/ll:verify-issues` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/24e047d3-fd6c-4840-9034-44f1410f82a8.jsonl`
- `/ll:ready-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

## Resolution

**Fixed** on 2026-03-12.

### Changes Made
- `scripts/little_loops/dependency_mapper/analysis.py`: Added `_basename()` helper; applied `overlap_min_files`/`overlap_min_ratio` guards and `exclude_common_files` filtering in `find_file_overlaps()`; changed default scores from 0.5 to 0.0 in `compute_conflict_score()` for missing semantic/section signals
- `scripts/tests/test_dependency_mapper.py`: Updated 12 existing tests to account for new guards and lower default scores; added 4 new tests in `TestOverlapGuardsAndDefaultScores` class

---

## Status

**Completed** | Created: 2026-03-12 | Resolved: 2026-03-12 | Priority: P3
