---
id: FEAT-1411
type: FEAT
priority: P2
parent_issue: FEAT-1409
---

# FEAT-1411: EPIC Type — Regex-Based Callers, Anchor Sweep, and Tests

## Summary

Extend `(BUG|FEAT|ENH)` regex patterns to `(BUG|FEAT|ENH|EPIC)` in all regex-based ID scanners
and add `"epics"` to the anchor sweep active categories. Add corresponding test cases.

Depends on FEAT-1410 for the `conftest.py` shared fixture (epics/ dir + epics config category)
used by some tests here. Implement FEAT-1410 first or coordinate the conftest.py change.

## Parent Issue

Decomposed from FEAT-1409: EPIC Type — CLI Source, Regex Extensions, and Tests

## Current Behavior

Regex-based ID scanners in `deps.py`, `operations.py`, `analysis.py`, `sprint/edit.py`, and
`recursive-refine.yaml` do not match `EPIC-NNN` identifiers. `anchor_sweep.py` does not scan
the `epics/` directory.

## Expected Behavior

After this child lands:
- `deps.py`, `operations.py`, `analysis.py`, `sprint/edit.py`, `recursive-refine.yaml` all match EPIC-NNN IDs
- `ll-issues anchor-sweep` scans EPIC issue files
- `ll-deps`, dependency mapper, and workflow sequence extractor recognize EPIC issue IDs
- All new and existing tests pass

## Implementation Steps

### Step 1 — Extend regex in 5 callers

Extend `(BUG|FEAT|ENH)` to `(BUG|FEAT|ENH|EPIC)`:

1. `scripts/little_loops/cli/deps.py` — `_load_issues()` (line 50):
   `re.search(r"(BUG|FEAT|ENH)-(\d+)", f.name)` → `r"(BUG|FEAT|ENH|EPIC)-(\d+)"`

2. `scripts/little_loops/dependency_mapper/operations.py` — `gather_all_issue_ids()` (line 280):
   `re.search(r"(BUG|FEAT|ENH)-(\d+)", f.name)` → `r"(BUG|FEAT|ENH|EPIC)-(\d+)"`

3. `scripts/little_loops/workflow_sequence/analysis.py` — module-level constant (line 28):
   `ISSUE_PATTERN = re.compile(r"(?:BUG|FEAT|ENH)-\d+", re.IGNORECASE)` →
   `ISSUE_PATTERN = re.compile(r"(?:BUG|FEAT|ENH|EPIC)-\d+", re.IGNORECASE)`

4. `scripts/little_loops/cli/sprint/edit.py` — `_cmd_sprint_edit()` `--prune` branch (line 77):
   `re.search(r"(BUG|FEAT|ENH)-(\d+)", path.name)` → `r"(BUG|FEAT|ENH|EPIC)-(\d+)"`

5. `scripts/little_loops/loops/recursive-refine.yaml` — `build_parent_map()` inside `done` state inline Python (line 686):
   `re.search(r'(BUG|FEAT|ENH)-(\d+)', os.path.basename(f))` → `r'(BUG|FEAT|ENH|EPIC)-(\d+)'`

### Step 2 — Check `refine_status.py`

`scripts/little_loops/cli/issues/refine_status.py` — **Confirmed: no `BUG|FEAT|ENH` regex present.**
File delegates type filtering via `type_prefixes` set; no hardcoded regex. No action needed.

### Step 3 — `anchor_sweep.py`

`scripts/little_loops/issues/anchor_sweep.py` — add `"epics"` to `_ACTIVE_CATEGORIES` tuple in `sweep_issues()` (line 29):
```python
_ACTIVE_CATEGORIES = ("bugs", "features", "enhancements")
# → 
_ACTIVE_CATEGORIES = ("bugs", "features", "enhancements", "epics")
```

### Step 4 — Tests

**`test_dependency_mapper.py`**:
- Update `TestGatherAllIssueIds.test_scans_all_categories` (line 635) to include `epics/` subdir with `P2-EPIC-001-foo.md` and assert `"EPIC-001" in ids`

**`test_workflow_sequence_analyzer.py`**:
- Update `TestExtractEntities.test_issue_ids` (line 61) to include `EPIC-001` in test content string and assert `"EPIC-001" in entities`

**`test_loops_recursive_refine.py`**:
- Extend inline `build_parent_map()` regex at line 780 from `(BUG|FEAT|ENH)` to `(BUG|FEAT|ENH|EPIC)`

**`test_sprint.py`**:
- Verify `TestSprintEdit` (`_cmd_sprint_edit()`) — the `--prune` regex change is additive and should not break existing tests
- Investigate `_setup_edit_project()` fixture (line 1451) — if it creates a real directory tree, adding `epics/` is likely a one-liner; add an EPIC-aware prune scenario if the fixture supports it

### Step 5 — Verify

```bash
python -m pytest scripts/tests/test_dependency_mapper.py \
  scripts/tests/test_workflow_sequence_analyzer.py \
  scripts/tests/test_loops_recursive_refine.py \
  scripts/tests/test_sprint.py -v
```

## Files to Modify (Source)

- `scripts/little_loops/cli/deps.py` — regex in `_load_issues()` (line 50)
- `scripts/little_loops/dependency_mapper/operations.py` — regex in `gather_all_issue_ids()` (line 280)
- `scripts/little_loops/workflow_sequence/analysis.py` — `ISSUE_PATTERN` constant (line 28)
- `scripts/little_loops/cli/sprint/edit.py` — regex in `_cmd_sprint_edit()` (line 77)
- `scripts/little_loops/loops/recursive-refine.yaml` — regex in `build_parent_map()` inside `done` state (line 686)
- `scripts/little_loops/issues/anchor_sweep.py` — `_ACTIVE_CATEGORIES` (line 29)

## Files to Modify (Tests)

- `scripts/tests/test_dependency_mapper.py`
- `scripts/tests/test_workflow_sequence_analyzer.py`
- `scripts/tests/test_loops_recursive_refine.py`
- `scripts/tests/test_sprint.py`

## Dependency Note

`conftest.py` fixture changes (epics/ dir + epics config category in `sample_config`) are owned
by FEAT-1410. If any test here uses `issues_dir` or `sample_config` fixtures, ensure FEAT-1410
has landed first — or coordinate the conftest.py change to land together with this child.

## Acceptance Criteria

- `deps.py`, `operations.py`, `analysis.py`, `sprint/edit.py`, `recursive-refine.yaml` all match EPIC-NNN IDs
- `ll-issues anchor-sweep` scans files in the `epics/` directory
- `TestGatherAllIssueIds.test_scans_all_categories` includes EPIC-001
- `TestExtractEntities.test_issue_ids` includes EPIC-001
- `test_loops_recursive_refine.py:780` regex covers EPIC
- `TestSprintEdit` passes with EPIC prune scenario (if fixture supports it)
- All new and existing tests pass

## Session Log

- `/ll:issue-size-review` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62980d84-6316-4d76-811c-87774aefc470.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P2
