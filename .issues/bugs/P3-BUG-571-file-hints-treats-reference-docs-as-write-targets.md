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

- [ ] Two issues that share a file only in "### Related Key Documentation" or "### Dependent Files (Callers/Importers)" sections do NOT report as overlapping in `ll-sprint show`
- [ ] Two issues that share the same file in "### Files to Modify" still correctly report as overlapping
- [ ] The `ll-loop` sprint produces more parallel waves (fewer issues serialized in Wave 1) after the fix
- [ ] New tests in `scripts/tests/test_file_hints.py` covering section-aware extraction pass

## Root Cause

### File & Function
- `scripts/little_loops/parallel/file_hints.py` — `FILE_PATH_PATTERN` regex + `FileHints` construction

### Explanation
`FILE_PATH_PATTERN` (line 19) matches all file paths in issue content indiscriminately. The constructor in `parallel/file_hints.py` (called from `cli/sprint/manage.py`) passes the entire issue content to the extractor without sectioning. The `COMMON_FILES_EXCLUDE` list (line 45) only excludes known Python infrastructure files (`__init__.py`, `pyproject.toml`, etc.) but not project-specific large reference documents.

## Proposed Solution

**Option A — Section-aware extraction (preferred)**

In `file_hints.py` or a new `issue_sections.py`, add a `_extract_write_target_files(content: str) -> set[str]` function that:
- Searches only within "### Files to Modify" and "### Files Changed" sections (stop at next `###` or `##`)
- Applies `FILE_PATH_PATTERN` only to those sections

Update `FileHints` construction to use `_extract_write_target_files` for the `files` set that feeds `overlaps_with()`. Keep the existing broad extraction for informational purposes (e.g., dependency hints) but don't feed it to overlap detection.

**Option B — Extend COMMON_FILES_EXCLUDE** (not recommended)

Add well-known reference docs to the exclude list. Simpler but fragile — doesn't generalize to other projects or newly added docs.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/file_hints.py` — add `_extract_write_target_files()`, update `FileHints` population

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint/manage.py` — calls `FileHints` for contention detection; no interface change needed
- `scripts/little_loops/parallel/orchestrator.py` — also uses `FileHints`; benefits automatically

### Tests
- `scripts/tests/test_file_hints.py` (if exists) — add test: issue with doc in "Related Key Documentation" should not overlap with another issue that also references same doc
- Add test: two issues both with same path in "### Files to Modify" should still overlap

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `_extract_write_target_files(content: str) -> set[str]` in `file_hints.py` that scopes `FILE_PATH_PATTERN` to "### Files to Modify" / "### Files Changed" sections only
2. Update `FileHints` constructor to use the new function for the `files` set fed to `overlaps_with()`
3. Add unit tests in `test_file_hints.py`: reference-only shared file → no overlap; write-target shared file → overlap
4. Run `ll-sprint show` on the `ll-loop` sprint to verify improved parallelism

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/parallel/file_hints.py` | Core file to modify |
| `docs/generalized-fsm-loop.md` | Example of a widely-referenced doc that triggers false contention |

## Session Log
- `/ll:capture-issue` — 2026-03-04T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffa88660-2b5b-4a83-a475-9f7a9def1102.jsonl`
- `/ll:format-issue` — 2026-03-04T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fac97403-79d6-481f-b8da-20f7f34b52d4.jsonl`
