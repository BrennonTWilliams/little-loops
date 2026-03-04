---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
---

# ENH-554: `test_workflow_integration.py` tests `AutoManager`/`ParallelOrchestrator`, not `workflow_sequence_analyzer`

## Summary

`scripts/tests/test_workflow_integration.py` is named and co-located with workflow analyzer tests, but its entire content tests the issue-processing automation pipeline (`AutoManager`, `ParallelOrchestrator`, `StateManager`, `IssueParser`). It imports nothing from `workflow_sequence_analyzer`. There are no integration-level tests for the `ll-workflows` CLI (`main()` entry point, file I/O round-trip).

## Location

- **File**: `scripts/tests/test_workflow_integration.py`
- **Line(s)**: 1–10 (module docstring and imports) (at scan commit: a574ea0)
- **Anchor**: module docstring
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/tests/test_workflow_integration.py#L1-L10)
- **Code**:
```python
"""Integration tests for the full issue processing workflow.

Tests the end-to-end flow of issue processing with mocked subprocess calls
for Claude CLI and git operations.
"""
```

## Current Behavior

The file name suggests `workflow_sequence_analyzer` integration coverage, but actually covers `AutoManager`/`ParallelOrchestrator`. There are no CLI-level tests for `ll-workflows analyze` (subprocess invocation of `main()`, temp-file round-trips, exit codes).

## Expected Behavior

Either:
- **Option A:** Rename to `test_issue_workflow_integration.py` and update the docstring, making the scope unambiguous. Add a separate `test_workflow_sequence_analyzer_integration.py` if CLI integration tests are wanted.
- **Option B:** Add a `TestWorkflowSequenceAnalyzerIntegration` class to the existing file that exercises `main()` via direct call with real temp files (JSONL input → YAML output round-trip, bad input exit codes).

## Motivation

The naming confusion makes it harder to assess test coverage for `workflow_sequence_analyzer`. Developers searching for integration tests of `ll-workflows` find a file that tests something entirely different. A rename immediately clarifies the gap and prevents future confusion.

## Proposed Solution

**Recommended (Option A — rename):**
```bash
git mv scripts/tests/test_workflow_integration.py \
        scripts/tests/test_issue_workflow_integration.py
```

Update docstring:
```python
"""Integration tests for the issue processing pipeline.

Tests the end-to-end flow of issue processing with mocked subprocess calls
for Claude CLI and git operations (AutoManager, ParallelOrchestrator, StateManager).
"""
```

If CLI integration tests for `ll-workflows` are wanted, create `test_workflow_sequence_analyzer_integration.py` separately.

## Scope Boundaries

- In scope: rename the file (and update any imports that reference it), update docstring
- Out of scope: adding new `ll-workflows` integration tests (tracked separately)

## Integration Map

### Files to Modify
- `scripts/tests/test_workflow_integration.py` → `scripts/tests/test_issue_workflow_integration.py`

### Dependent Files (Callers/Importers)
- Check `pytest.ini` / `pyproject.toml` for test path patterns that may need updating

### Similar Patterns
- N/A

### Tests
- This issue *is* about the test file

### Documentation
- N/A

### Configuration
- `scripts/pyproject.toml` — verify test discovery patterns still match renamed file

## Implementation Steps

1. `git mv` the file to `test_issue_workflow_integration.py`
2. Update the module docstring
3. Verify `python -m pytest scripts/tests/` still discovers and runs all tests

## Impact

- **Priority**: P4 - Naming clarity; no functional impact but causes coverage assessment errors
- **Effort**: Small - Rename + docstring update
- **Risk**: Low - No logic changes; just a rename
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `testing`, `workflow-analyzer`, `captured`

## Session Log

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`

---

**Open** | Created: 2026-03-04 | Priority: P4
