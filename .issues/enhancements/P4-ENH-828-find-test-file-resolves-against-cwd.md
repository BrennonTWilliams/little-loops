---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 86
---

# ENH-828: `_find_test_file` resolves paths against process CWD

## Summary

`_find_test_file` in `parsing.py` checks file existence using `Path(candidate).exists()`, which resolves relative to the process working directory. When invoked from different directories (e.g., from within a worktree or subprocess), results are inconsistent.

## Location

- **File**: `scripts/little_loops/issue_history/parsing.py`
- **Line(s)**: 317-320 (at scan commit: 8c6cf90)
- **Anchor**: `in function _find_test_file`
- **Code**:
```python
for candidate in candidates:
    if Path(candidate).exists():   # relative to CWD, not project root
        return candidate
```

## Current Behavior

File existence checks are resolved against the Python process's CWD, not the project root. Results depend on where the process was started.

## Expected Behavior

Existence checks should be anchored to the project root path for consistent results regardless of invocation context.

## Motivation

`_find_test_file` is called from `analyze_test_gaps` which runs as part of `ll-history analyze`. When invoked from worktrees or automation contexts, the CWD may differ from the project root.

## Proposed Solution

Add an optional `project_root: Path | None = None` parameter to `_find_test_file`. When provided, resolve candidates via `(project_root / candidate).exists()`. Update call sites in `quality.py` to pass the project root from config.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The pattern already exists in `detect_config_gaps` (`quality.py:418-432`):
```python
def detect_config_gaps(
    manual_pattern_analysis: ManualPatternAnalysis,
    project_root: Path | None = None,
) -> ConfigGapsAnalysis:
    if project_root is None:
        project_root = Path.cwd()
    hooks_file = project_root / "hooks" / "hooks.json"
```
Follow this exact same pattern for `_find_test_file` and `analyze_test_gaps`.

`project_root` is already plumbed through the call chain — it's just not forwarded at two points:
1. `calculate_analysis` (`analysis.py:68`) already has `project_root: Path | None = None` but doesn't pass it to `analyze_test_gaps` at line 126
2. `main_history` (`cli/history.py:173`) resolves `project_root = args.config or Path.cwd()` but doesn't pass it to `calculate_analysis` at lines 193-198

## Scope Boundaries

- Out of scope: Changing how candidate paths are generated
- Out of scope: Making project_root required (preserve backward compatibility)

## Impact

- **Priority**: P4 - Correctness issue in specific invocation contexts
- **Effort**: Small - Add parameter, update two call sites
- **Risk**: Low - Backward compatible with optional parameter
- **Breaking Change**: No

## Labels

`enhancement`, `issue-history`, `correctness`

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/parsing.py:281` — add `project_root: Path | None = None` to `_find_test_file`; change line 322 `Path(candidate).exists()` → `(project_root / candidate).exists() if project_root else Path(candidate).exists()`
- `scripts/little_loops/issue_history/quality.py:26` — add `project_root: Path | None = None` to `analyze_test_gaps`; thread to both `_find_test_file` calls
- `scripts/little_loops/issue_history/analysis.py:126` — pass `project_root=project_root` to `analyze_test_gaps(...)` (parameter already on `calculate_analysis` at line 68)
- `scripts/little_loops/cli/history.py:193` — pass `project_root=project_root` to `calculate_analysis(...)` (variable already in scope at line 173)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/quality.py:23` — imports `_find_test_file` from `parsing`
- `scripts/little_loops/issue_history/__init__.py` — re-exports `analyze_test_gaps`

### Similar Patterns
- `scripts/little_loops/issue_history/quality.py:418-432` — `detect_config_gaps` already uses identical `project_root: Path | None = None` pattern with `Path.cwd()` fallback and `project_root / path` anchoring

### Tests
- `scripts/tests/test_issue_history_advanced_analytics.py:1045` — `TestAnalyzeTestGaps` class; all 8 existing tests use mocked hotspot paths (no CWD testing); needs a new test verifying path anchoring
- `scripts/tests/test_subprocess_utils.py:136-183` — **closest existing analogue** for `read_continuation_prompt(repo_path=None)`: uses `tmp_path` fixture, explicit root arg, and `monkeypatch.chdir()` to test the `None`/cwd fallback — model the new test directly after this class (`TestReadContinuationPrompt`)
- `scripts/tests/test_ll_loop_integration.py:82-106` — secondary reference for `monkeypatch.chdir(tmp_path)` pattern

### Documentation
- `docs/reference/API.md:1401` — documents `analyze_test_gaps` signature; update if the signature changes (new `project_root` param)

## Implementation Steps

1. **`parsing.py:281`** — Add `project_root: Path | None = None` to `_find_test_file` signature; update the existence check loop (line 321-322): `if (project_root / candidate).exists() if project_root else Path(candidate).exists()`
2. **`quality.py:26`** — Add `project_root: Path | None = None` to `analyze_test_gaps`; pass `project_root=project_root` to `_find_test_file` at both call sites (lines 64 and 108)
3. **`analysis.py:126`** — Add `project_root=project_root` to the `analyze_test_gaps(completed_issues, hotspot_analysis)` call; `project_root` is already a parameter of `calculate_analysis` (line 68)
4. **`cli/history.py:193`** — Add `project_root=project_root` to the `calculate_analysis(...)` call; `project_root` is already in scope from line 173
5. **Tests** — Add a test to `TestAnalyzeTestGaps` (`test_issue_history_advanced_analytics.py:1045`) using `tmp_path` + `monkeypatch.chdir()` to verify correct path anchoring; also test the `None`/cwd fallback via `monkeypatch.chdir`; model after `TestReadContinuationPrompt` in `test_subprocess_utils.py:136-183`
6. **Verify** — Run `python -m pytest scripts/tests/test_issue_history_advanced_analytics.py::TestAnalyzeTestGaps -v`

## Status

**Open** | Created: 2026-03-19 | Priority: P4


## Verification Notes

**Verdict**: VALID — Issue accurately describes the current state of the codebase.

**Verified**: 2026-03-19

- `scripts/little_loops/issue_history/parsing.py` exists ✓
- `_find_test_file` at line 278 has no `project_root` parameter ✓
- Loop at lines 318-320 uses `Path(candidate).exists()` without anchoring to project root ✓ (issue states 317-320; shifted by 1 line since scan commit `8c6cf90`, but code is identical)
- Call sites in `quality.py` at lines 64 and 108 still pass no project root argument ✓
- Enhancement remains unimplemented

## Session Log
- `/ll:confidence-check` - 2026-03-21T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:refine-issue` - 2026-03-21T05:54:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5b33b4-4f43-4816-926d-91f9358c3ab6.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:40:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
