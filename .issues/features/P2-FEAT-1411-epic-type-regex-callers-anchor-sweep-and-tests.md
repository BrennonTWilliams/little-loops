---
id: FEAT-1411
type: FEAT
priority: P2

confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-05-10T14:35:03Z
parent: FEAT-1409
status: done
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

## Use Case

A developer using `ll-deps`, `ll-issues anchor-sweep`, or `ll-sprint` creates EPIC-type issues (e.g., `EPIC-001-my-epic.md`) to coordinate a set of related work. Without this change, running `ll-deps` or `ll-issues anchor-sweep` silently ignores EPIC files — cross-issue dependencies involving EPICs don't appear in dependency graphs or anchor reports, making it impossible to track EPIC → child relationships through the automated tooling.

## Implementation Steps

### Step 1 — Extend regex in 5 callers

Extend `(BUG|FEAT|ENH)` to `(BUG|FEAT|ENH|EPIC)`:

1. `scripts/little_loops/cli/deps.py` — `_load_issues()` (line 50):
   `re.search(r"(BUG|FEAT|ENH)-(\d+)", f.name)` → `r"(BUG|FEAT|ENH|EPIC)-(\d+)"`

2. `scripts/little_loops/dependency_mapper/operations.py` — `gather_all_issue_ids()` (line 280):
   `re.search(r"(BUG|FEAT|ENH)-(\d+)", f.name)` → `r"(BUG|FEAT|ENH|EPIC)-(\d+)"`

   **Additional change required (same function, ~line 272):** The `else` branch contains a hardcoded
   fallback directory list `["bugs", "features", "enhancements", "completed", "deferred"]`. Add `"epics"`
   here too, otherwise the function skips the `epics/` subdirectory entirely when no config is passed,
   making the regex change ineffective for EPIC files.
   `["bugs", "features", "enhancements", "completed", "deferred"]` →
   `["bugs", "features", "enhancements", "epics", "completed", "deferred"]`

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
  Note: the shared `issues_dir` fixture in `conftest.py` creates an `epics_dir` but does **not** plant an EPIC file in it — this test must create `(tmp_path / "epics").mkdir()` and the file itself

**`test_workflow_sequence_analyzer.py`**:
- Update `TestExtractEntities.test_issue_ids` (line 61) to include `EPIC-001` in test content string and assert `"EPIC-001" in entities`

**`test_loops_recursive_refine.py`**:
- Extend inline `build_parent_map()` regex at line 780 from `(BUG|FEAT|ENH)` to `(BUG|FEAT|ENH|EPIC)`

**`test_sprint.py`**:
- Verify `TestSprintEdit` (`_cmd_sprint_edit()`) — the `--prune` regex change is additive and should not break existing tests
- `_setup_edit_project()` at line 1451 creates a real directory tree and **requires two changes**:
  1. Line 1460 — extend the dir-creation loop: `["bugs", "features", "enhancements", "completed"]` → add `"epics"`
  2. The `config_data` dict inside that fixture has a `"categories"` block with no `"epics"` entry — add it
  Once both are updated, add an EPIC-aware prune scenario asserting an `EPIC-NNN` file is recognized by `--prune`.
  Note: the `for category in [...]` loop is at line 1459 (not 1460).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_issues_cli.py` — `TestIssuesCLIAnchorSweep`: add `"epics"` to fixture category loops in `test_dry_run_no_issues` (~line 3618) and `test_alias_asw` (~line 3643), and add a new EPIC anchor-sweep scenario test asserting that an EPIC file in `epics/` is scanned
7. Update `docs/reference/CLI.md` — anchor-sweep section (~line 737): change `"bugs/, features/, enhancements/"` to include `"epics/"` in the description; also update `--category` flag description (~line 110) to include `epics`
8. Update `docs/reference/CONFIGURATION.md` — `issues.categories` section (~line 264): change "three core categories (bugs, features, enhancements)" to "four core categories (bugs, features, enhancements, epics)"

### Step 5 — Verify

```bash
python -m pytest scripts/tests/test_dependency_mapper.py \
  scripts/tests/test_workflow_sequence_analyzer.py \
  scripts/tests/test_loops_recursive_refine.py \
  scripts/tests/test_sprint.py -v
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/deps.py` — regex in `_load_issues()`
- `scripts/little_loops/dependency_mapper/operations.py` — regex in `gather_all_issue_ids()`
- `scripts/little_loops/workflow_sequence/analysis.py` — `ISSUE_PATTERN` constant
- `scripts/little_loops/cli/sprint/edit.py` — regex in `_cmd_sprint_edit()`
- `scripts/little_loops/loops/recursive-refine.yaml` — regex in `build_parent_map()` inside `done` state
- `scripts/little_loops/issues/anchor_sweep.py` — `_ACTIVE_CATEGORIES` in `sweep_issues()`

### Dependent Files (Callers/Importers)
- `ll-deps` CLI command → `scripts/little_loops/cli/deps.py`
- `ll-issues anchor-sweep` → `scripts/little_loops/issues/anchor_sweep.py`
- `ll-workflows` → `scripts/little_loops/workflow_sequence/analysis.py`
- Dependency mapper pipeline → `scripts/little_loops/dependency_mapper/operations.py`

### Similar Patterns
- FEAT-1410 — `conftest.py` shared fixture; coordinate `epics/` dir and epics config category changes
- FEAT-1409 (parent) — same regex extension pattern applied across CLI display paths

### Tests
- `scripts/tests/test_dependency_mapper.py` — `TestGatherAllIssueIds.test_scans_all_categories`
- `scripts/tests/test_workflow_sequence_analyzer.py` — `TestExtractEntities.test_issue_ids`
- `scripts/tests/test_loops_recursive_refine.py` — `build_parent_map()` inline regex
- `scripts/tests/test_sprint.py` — `TestSprintEdit` EPIC prune scenario

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_cli.py` — `TestIssuesCLIAnchorSweep` (test_dry_run_no_issues ~line 3618, test_alias_asw ~line 3643): fixture `for cat in ("bugs", "features", "enhancements"):` loops omit `"epics"` dir creation; no EPIC anchor-sweep scenario test exists — add epics/ fixture dir and an EPIC sweep test [Agent 1 + 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — line 737, anchor-sweep section: `"Scan all active issue files (bugs/, features/, enhancements/)"` — needs `epics/` added [Agent 2 finding]
- `docs/reference/CLI.md` — line 110, `--category` flag description: `"Filter to category: bugs, features, enhancements"` — needs `epics` listed [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — line 264, `issues.categories` section: `"The three core categories (bugs, features, enhancements) are always included automatically."` — will be stale once `epics` is active [Agent 2 finding]

### Configuration
- N/A

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- All 6 regex locations confirmed **not yet updated** — line numbers in Implementation Steps are accurate
- `operations.py` has a **second location** requiring change: hardcoded fallback dir list at ~line 272
  (`["bugs", "features", "enhancements", "completed", "deferred"]`) must also include `"epics"` or
  the regex fix is unreachable for callers that omit config
- FEAT-1410 dependency **already satisfied**: `conftest.py` has `"epics"` in `sample_config` (line 84)
  and `issues_dir` fixture creates `epics_dir` (lines 131, 137) — no blocker
- `conftest.py` `issues_dir` does **not** plant an EPIC `.md` file — `test_scans_all_categories`
  must create `epics/` dir and file explicitly (cannot rely on fixture alone)
- `test_sprint.py` `_setup_edit_project()` requires **two** changes: dir-creation loop (line 1460)
  and the `config_data["categories"]` dict — both confirmed absent

## Dependency Note

`conftest.py` fixture changes (epics/ dir + epics config category in `sample_config`) are owned
by FEAT-1410. If any test here uses `issues_dir` or `sample_config` fixtures, ensure FEAT-1410
has landed first — or coordinate the conftest.py change to land together with this child.

**Confirmed**: FEAT-1410 is completed and its conftest.py changes are already in place.

## Acceptance Criteria

- `deps.py`, `operations.py`, `analysis.py`, `sprint/edit.py`, `recursive-refine.yaml` all match EPIC-NNN IDs
- `ll-issues anchor-sweep` scans files in the `epics/` directory
- `TestGatherAllIssueIds.test_scans_all_categories` includes EPIC-001
- `TestExtractEntities.test_issue_ids` includes EPIC-001
- `test_loops_recursive_refine.py:780` regex covers EPIC
- `TestSprintEdit` passes with EPIC prune scenario (if fixture supports it)
- All new and existing tests pass

## Impact

- **Priority**: P2 - Child of FEAT-1409; required for complete EPIC type support in automated tooling
- **Effort**: Small - Six one-liner regex changes plus four focused test additions; no new modules or infrastructure
- **Risk**: Low - Additive changes only; existing BUG/FEAT/ENH regex alternations remain unchanged
- **Breaking Change**: No

## Status

Completed

## Resolution

Implemented all regex extensions (`BUG|FEAT|ENH` → `BUG|FEAT|ENH|EPIC`) across 5 callers plus the fallback dir list in `operations.py`. Added `"epics"` to `_ACTIVE_CATEGORIES` in `anchor_sweep.py`. Updated tests in all 4 test files and added an EPIC anchor-sweep scenario test. Updated CLI.md and CONFIGURATION.md docs. All 325 targeted tests pass.

## Labels

`regex`, `testing`, `epic-type`, `child-issue`

## Session Log
- `/ll:ready-issue` - 2026-05-10T14:30:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/924aad7a-19a6-4969-a1ac-995eb95f6db8.jsonl`
- `/ll:confidence-check` - 2026-05-10T15:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87aa3665-7b97-4854-8ebd-2e34e4875ba6.jsonl`
- `/ll:wire-issue` - 2026-05-10T14:25:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b252132-81fd-48fa-abf4-43fc7a785312.jsonl`
- `/ll:refine-issue` - 2026-05-10T14:17:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0dc6b66f-7fdc-4662-b3d3-ddd2f4692bcc.jsonl`
- `/ll:format-issue` - 2026-05-10T14:09:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dd3c0207-e3c2-4002-af23-af19329e8f2e.jsonl`

- `/ll:issue-size-review` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62980d84-6316-4d76-811c-87774aefc470.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): `scripts/tests/conftest.py` changes (adding `epics/` dir to `issues_dir` fixture and `epics` to `sample_config`) are owned by FEAT-1410. Verify FEAT-1410 has landed before implementing this issue. Do not re-create or modify conftest.py here — treat those changes as pre-existing when you start. Similarly, all doc-file updates (`docs/reference/CLI.md`, `docs/reference/API.md`, `docs/reference/CONFIGURATION.md`) are owned by FEAT-1407 — defer to that issue for documentation changes.

---

**Open** | Created: 2026-05-09 | Priority: P2
