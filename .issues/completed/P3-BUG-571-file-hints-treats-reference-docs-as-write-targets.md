---
discovered_date: 2026-03-04T00:00:00Z
discovered_by: capture-issue
---

# BUG-571: `FileHints` Extractor Treats Reference Docs as Write Targets, Causing False Sprint Serialization

## Summary

`file_hints.py` extracts all file paths mentioned in an issue file equally, regardless of whether they appear in "Files to Modify" (write targets) or reference sections like "Related Key Documentation" or "Dependent Files (Callers/Importers)". When `/ll:refine-issue` adds large docs like `docs/generalized-fsm-loop.md` to every issue as context references, every issue in a sprint appears to overlap on that doc, forcing all issues into a single serialized wave instead of running in parallel.

## Steps to Reproduce

1. Create a sprint with 10+ issues where `/ll:refine-issue` has added reference docs (e.g., `docs/generalized-fsm-loop.md`) to each issue under "### Related Key Documentation" or "### Dependent Files (Callers/Importers)"
2. Run `ll-sprint show <sprint-name>`
3. Observe the "overlap serialized" report — issues sharing only reference docs appear in the same serialized wave

**Observed example**: The `ll-loop` sprint shows 14 issues across 2 waves, with Wave 1 containing 10 serialized issues due to `docs/generalized-fsm-loop.md` being listed as a shared reference across all of them.

## Current Behavior

`ll-sprint show` reports `overlap serialized` for 10+ issues in a sprint, even when their actual implementation files are completely distinct. The contended files listed are documentation files (e.g., `docs/generalized-fsm-loop.md`, `docs/guides/LOOPS_GUIDE.md`) that are shared as read-only context references, not write targets.

Observed example: the `ll-loop` sprint has 14 issues across 2 waves, but Wave 1 has 10 issues all serialized due to shared doc references. Only 2 real write-file conflicts exist (`executor.py` shared by BUG-530/ENH-536, `validation.py` shared by ENH-535/ENH-540).

## Expected Behavior

Issues that only share reference/context documentation should not be considered overlapping. The extractor should distinguish:
- **Write targets**: Files listed under "### Files to Modify" or "### Files Changed" → contribute to overlap detection
- **Reference files**: Files listed under "### Related Key Documentation", "### Dependent Files (Callers/Importers)", "### Similar Patterns", audit trail entries, etc. → excluded from overlap detection

## Acceptance Criteria

- [x] Two issues that share a file only in "### Related Key Documentation" or "### Dependent Files (Callers/Importers)" sections do NOT report as overlapping in `ll-sprint show`
- [x] Two issues that share the same file in "### Files to Modify" still correctly report as overlapping
- [x] The `ll-loop` sprint produces more parallel waves (fewer issues serialized in Wave 1) after the fix
- [x] New tests in `scripts/tests/test_file_hints.py` covering section-aware extraction pass

## Root Cause

### File & Function
- `scripts/little_loops/parallel/file_hints.py` — `FILE_PATH_PATTERN` regex + `FileHints` construction

### Explanation
`FILE_PATH_PATTERN` (`file_hints.py:19-22`) matches all file paths in issue content indiscriminately using `re.MULTILINE` across the full content string. `extract_file_hints()` (`file_hints.py:257-286`) receives the raw markdown as one string with no section awareness — every `FILE_PATH_PATTERN` match is added to `hints.files` at `file_hints.py:274` regardless of which section it came from. `COMMON_FILES_EXCLUDE` (`file_hints.py:45-55`) only excludes 8 Python infrastructure filenames (`__init__.py`, `pyproject.toml`, etc.) and is applied at comparison time inside `overlaps_with()` (`file_hints.py:113`), not at extraction time. Project-specific reference docs like `docs/generalized-fsm-loop.md` pass all filters and end up in the `files` set. The `overlaps_with()` threshold (`MIN_OVERLAP_FILES = 2`, `file_hints.py:39`) means even a single shared reference doc can trigger serialization when paired with one other shared path.

## Proposed Solution

**Option A — Section-aware extraction (preferred)**

In `file_hints.py` or a new `issue_sections.py`, add a `_extract_write_target_files(content: str) -> set[str]` function that:
- Searches only within "### Files to Modify" and "### Files Changed" sections (stop at next `###` or `##`)
- Applies `FILE_PATH_PATTERN` only to those sections

Update `FileHints` construction to use `_extract_write_target_files` for the `files` set that feeds `overlaps_with()`. Keep the existing broad extraction for informational purposes (e.g., dependency hints) but don't feed it to overlap detection.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Direct reuse pattern** — `scripts/little_loops/issue_discovery/extraction.py:52-66` already implements `_extract_files_changed()` using the exact same `###`-scoped extraction approach:
```python
section_match = re.search(
    r"###\s*Files Changed\s*\n(.*?)(?=\n###|\n##|\Z)",
    content, re.DOTALL,
)
```
This can be directly adapted for `### Files to Modify` and `### Files Changed` in `file_hints.py`.

**Additional existing patterns** for reference:
- `scripts/little_loops/cli/issues/show.py:141-150` — extracts item count under `### Files to Modify` using `start`/`next_header` boundary logic
- `scripts/little_loops/issue_parser.py:435-471` — `_parse_section_items()` with code-fence stripping (consider reusing `_strip_code_fences` to prevent false matches inside code examples in issues)

**Option B — Extend COMMON_FILES_EXCLUDE** (not recommended)

Add well-known reference docs to the exclude list. Simpler but fragile — doesn't generalize to other projects or newly added docs.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/file_hints.py` — add `_extract_write_target_files()`, update `FileHints` population

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint/manage.py:100` — `_cmd_sprint_analyze()` calls `extract_file_hints()` directly in O(n²) pairwise loop; no interface change needed
- `scripts/little_loops/parallel/overlap_detector.py:87,120` — `register_issue()` and `check_overlap()` both call `extract_file_hints()`; benefits automatically from fix
- `scripts/little_loops/dependency_graph.py:376` — `refine_waves_for_contention()` calls `extract_file_hints()` in a loop to build conflict adjacency map for greedy graph coloring; benefits automatically
- `scripts/little_loops/parallel/orchestrator.py` — uses `OverlapDetector` (not `extract_file_hints` directly); benefits automatically through `overlap_detector.py`
- `scripts/little_loops/parallel/__init__.py` — re-exports `FileHints` and `extract_file_hints` as public API

### Tests
- `scripts/tests/test_file_hints.py` — **exists**; `TestFileHintExtraction` class at line 17 tests `extract_file_hints()` directly — add test: issue with doc in "Related Key Documentation" should not overlap with another issue that also references same doc
- Add test: two issues both with same path in "### Files to Modify" should still overlap
- Reference pattern: `scripts/tests/test_issue_discovery.py:749-775` — `test_extract_files_changed` and `test_extract_files_changed_skips_placeholder` show exact pattern for `###`-section-scoped extraction tests

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `scripts/little_loops/parallel/file_hints.py`, add `_extract_write_target_files(content: str) -> set[str]` that scopes `FILE_PATH_PATTERN` to "### Files to Modify" / "### Files Changed" sections only — model after `_extract_files_changed()` at `issue_discovery/extraction.py:52-66`
2. In `extract_file_hints()` (`file_hints.py:257`), replace `FILE_PATH_PATTERN.findall(content)` loop (lines 270-274) with a call to `_extract_write_target_files(content)` for `hints.files`; optionally keep the broad extraction in a separate set for informational use
3. In `scripts/tests/test_file_hints.py`, add two new test methods to `TestFileHintExtraction` (line 17): (a) issue with doc only in "Related Key Documentation" → no overlap with sibling; (b) two issues with same path in "### Files to Modify" → still overlapping. Follow test structure at `test_issue_discovery.py:749-775`
4. Run `ll-sprint show` on the `ll-loop` sprint (or `python -m pytest scripts/tests/test_file_hints.py -v`) to verify improved parallelism and test passage

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/parallel/file_hints.py` | Core file to modify |
| `docs/generalized-fsm-loop.md` | Example of a widely-referenced doc that triggers false contention |

## Resolution

**Status**: Fixed

**Changes**:
- `scripts/little_loops/parallel/file_hints.py` — Added `_extract_write_target_files()` that scopes `FILE_PATH_PATTERN` to "### Files to Modify" and "### Files Changed" sections only; updated `extract_file_hints()` to use it for the `files` set
- `scripts/tests/test_file_hints.py` — Added `TestExtractWriteTargetFiles` and `TestSectionAwareOverlapDetection` test classes; updated existing `TestFileHintExtraction` tests to use proper section structure
- `scripts/tests/test_dependency_graph.py` — Updated `_make_issue_with_content` helper to wrap content in "### Files to Modify" section
- `scripts/tests/test_overlap_detector.py` — Updated `make_issue` helper likewise
- `scripts/tests/test_sprint.py` — Updated test issue content in `_setup_overlapping_issues` and `_setup_analyze_project` to use "### Files to Modify" sections

## Session Log
- `/ll:capture-issue` — 2026-03-04T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffa88660-2b5b-4a83-a475-9f7a9def1102.jsonl`
- `/ll:format-issue` — 2026-03-04T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fac97403-79d6-481f-b8da-20f7f34b52d4.jsonl`
- `/ll:refine-issue` — 2026-03-04T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4f0f739c-fb26-490f-a599-0820d59a6c52.jsonl`
- `/ll:ready-issue` — 2026-03-04T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c26ab41-10f9-41f7-ae1f-8c1d7177acfa.jsonl`
- `/ll:manage-issue` — 2026-03-04T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
