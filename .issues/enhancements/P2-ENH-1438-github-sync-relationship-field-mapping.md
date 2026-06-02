---
id: ENH-1438
type: ENH
priority: P2
parent: ENH-1432
depends_on:
- ENH-1430
status: done
completed_at: 2026-05-11T02:27:10Z
size: Small
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1438: GitHub sync relationship field mapping

## Summary

Map `blocked_by` to a `blocked-by` GitHub label and `duplicate_of` to a closing comment in `GitHubSyncManager`. Adds unit tests in `test_sync.py` for the new behaviors. Depends on ENH-1430. Can run in parallel with ENH-1436 and ENH-1437.

## Parent Issue

Decomposed from ENH-1432: Standardize Relationship Fields — Dependency Tooling, Sync & Validation

## Scope

Covers implementation steps 9 and 10 from the parent, plus wiring step 16. This is entirely new territory — `ll-sync` currently maps NO relationship fields.

## Current Behavior

`GitHubSyncManager._get_labels_for_issue()` only produces type and priority labels based on filename; `blocked_by` frontmatter is ignored. `_push_single_issue()` has no logic for `duplicate_of` — no closing comment is posted when an issue marks itself as a duplicate.

## Expected Behavior

- When `blocked_by` frontmatter is non-empty, `_get_labels_for_issue()` appends `"blocked-by"` to the GitHub label list.
- When `duplicate_of` frontmatter is set, `_push_single_issue()` posts `"Duplicate of <target>."` as a GitHub comment after creating or updating the issue.

## Proposed Solution

### Step 9 — Map `blocked_by` to GitHub label (`sync.py:298`)

In `GitHubSyncManager._get_labels_for_issue()`: when `issue.blocked_by` is non-empty, append `"blocked-by"` to the returned labels list. Label attachment follows the `args.extend(["--label", label])` pattern in `_create_github_issue()` at line 419.

### Step 10 — Add `duplicate_of` closing comment (`sync.py:374`)

In `GitHubSyncManager._push_single_issue()`: after creating/updating the issue on GitHub, if `issue.duplicate_of` is set, post a closing comment referencing the duplicate target. GitHub has no native relationship API; this is the mapping strategy.

### Step 16 (Wiring) — Unit tests in `test_sync.py`

Following the existing `test_push_single_issue_creates_new` / `test_get_labels_for_issue` patterns:
- `test_get_labels_for_issue_with_blocked_by_adds_label()` — assert `"blocked-by" in labels`
- `test_push_single_issue_adds_duplicate_of_comment()` — assert a second `_run_gh_command` call for the closing comment

Note: `test_cli_sync.py` mocks `GitHubSyncManager` entirely and won't exercise this behavior at the unit level; use `test_sync.py` for these assertions.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Step 9 — `_get_labels_for_issue` has no frontmatter access

`_get_labels_for_issue(self, issue_path: Path) -> list[str]` at `sync.py:298` only reads `issue_path.name` (filename). `blocked_by` lives in frontmatter. The method must read and parse the file to access it:

```python
content = issue_path.read_text(encoding="utf-8")
fm = parse_frontmatter(content, coerce_types=True)
if fm.get("blocked_by"):
    labels.append("blocked-by")
```

`parse_frontmatter` is already imported in `sync.py`. The double file-read (here and in `_push_single_issue`) is acceptable for this small file; no signature change required.

#### Step 10 — `_push_single_issue` needs `effective_number` refactor

Current `_push_single_issue` flow at `sync.py:409–417`: after the if/else create-vs-update branches, no unified github number variable exists. Refactor to track it:

```python
effective_number: int | None = None
if github_number:
    self._update_github_issue(int(github_number), full_title, body, issue_id, result)
    effective_number = int(github_number)
else:
    new_number = self._create_github_issue(full_title, body, labels, issue_id, result)
    if new_number:
        self._update_local_frontmatter(issue_path, content, new_number)
        effective_number = new_number

if effective_number and frontmatter.get("duplicate_of"):
    _run_gh_command(
        ["issue", "comment", str(effective_number), "--body",
         f"Duplicate of {frontmatter['duplicate_of']}."],
        self.logger,
    )
```

The `_run_gh_command(["issue", "comment", str(n), "--body", msg], self.logger)` form (standalone comment without state change) does not currently exist in `sync.py`. The `close_issues()` equivalent at `sync.py:962` uses `--comment` on `gh issue close` — different command.

#### Step 16 — Test patterns from `test_sync.py`

**For `test_get_labels_for_issue_with_blocked_by_adds_label`**:
- Write a temp issue file with `blocked_by: [BUG-001]` in frontmatter (pattern: `test_get_labels_for_issue` at `test_sync.py:412`)
- No `_run_gh_command` mock needed — method is pure computation
- Assert `"blocked-by" in labels`

**For `test_push_single_issue_adds_duplicate_of_comment`**:
- Write temp file with both `github_issue: 42` and `duplicate_of: BUG-001` in frontmatter (update path — simpler than create path for this test)
- Use `side_effect` list (pattern: `test_reopen_all_reopened` at `test_sync.py:1532`):
  ```python
  mock_run.side_effect = [
      subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),  # gh issue edit
      subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),  # gh issue comment
  ]
  ```
- Assert `mock_run.call_count == 2`
- Assert second call args contain `"comment"` and `"--body"` and `"BUG-001"` (Style B from `test_sync.py:1307`)

Patch target: `"little_loops.sync._run_gh_command"` (module where defined).

## Files to Modify

- `scripts/little_loops/sync.py` — `_get_labels_for_issue()`, `_push_single_issue()`
- `scripts/tests/test_sync.py` — new unit tests for label and comment mapping

## Integration Map

### Files to Modify
- `scripts/little_loops/sync.py` — `_get_labels_for_issue()` (line 298): add frontmatter read + `blocked_by` → label; `_push_single_issue()` (line 374): refactor if/else to track `effective_number`, add `duplicate_of` comment call
- `scripts/tests/test_sync.py` — add two new test methods inside `TestGitHubSyncManager`

### Dependent Files (Callers)
- `scripts/little_loops/cli/sync.py` — `main_sync()` calls `GitHubSyncManager.push_issues()`; observable via new label and comment output

### Similar Patterns
- `sync.py:962` — `close_issues()` uses `_run_gh_command(["issue", "close", ..., "--comment", msg])` for comment-with-state; standalone `["issue", "comment", ...]` form is the model for Step 10
- `test_sync.py:412` — `test_get_labels_for_issue` — model for the new label test
- `test_sync.py:777` — `test_push_single_issue_creates_new` — model for the new push+comment test
- `test_sync.py:1532` — `test_reopen_all_reopened` — model for multi-call `side_effect` list

### Tests
- `scripts/tests/test_sync.py` — `TestGitHubSyncManager` class; add `test_get_labels_for_issue_with_blocked_by_adds_label` and `test_push_single_issue_adds_duplicate_of_comment`
- `scripts/tests/test_cli_sync.py` — fully mocks `GitHubSyncManager` at class level; no changes needed (new behavior is not exercised at CLI test level) [Agent 3 finding]

### Configuration
- `config-schema.json:204–227` — `blocked_by` and `duplicate_of` schema already defined (from ENH-1430)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `commands/sync-issues.md` — "Determine labels" bullet and `gh issue create` shell block in "Push (Local → GitHub)" section do not mention the new `blocked-by` label source; update to document `blocked_by` frontmatter → `"blocked-by"` label behavior [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `### sync` table lists only `label_mapping` and `priority_labels` as label sources; add note that `blocked_by` frontmatter also produces a `"blocked-by"` label (lower priority doc update) [Agent 2 finding]

## Dependent Files (Callers — no code change required)

- `scripts/little_loops/cli/sync.py` — direct consumer of `GitHubSyncManager`; label and comment output changes will be observable here

## Implementation Steps

1. **`sync.py:_get_labels_for_issue()` (line 298)** — After the existing priority-label block, read frontmatter with `parse_frontmatter(issue_path.read_text(encoding="utf-8"), coerce_types=True)` and append `"blocked-by"` if `fm.get("blocked_by")` is non-empty.
2. **`sync.py:_push_single_issue()` (line 409)** — Replace the current `if github_number: ... else: ...` block with the `effective_number` pattern (see research findings). Add `duplicate_of` comment call after the block using `_run_gh_command(["issue", "comment", str(effective_number), "--body", ...], self.logger)`.
3. **`test_sync.py`** — Inside `TestGitHubSyncManager`, add `test_get_labels_for_issue_with_blocked_by_adds_label` (no mock needed, write file with `blocked_by:` frontmatter) and `test_push_single_issue_adds_duplicate_of_comment` (file with `github_issue: 42` + `duplicate_of: BUG-001`, two-element `side_effect` list, assert `call_count == 2` and second call contains `"comment"`).
4. **Verify** — Run `python -m pytest scripts/tests/test_sync.py -v` and confirm all existing tests still pass.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `commands/sync-issues.md` — in the "Push (Local → GitHub)" → "Determine labels" bullet block and `gh issue create` shell example, add the third label source: `blocked_by` non-empty → append `"blocked-by"` label.

## Acceptance Criteria

- `GitHubSyncManager._get_labels_for_issue()` appends `"blocked-by"` label when `issue.blocked_by` is non-empty
- `GitHubSyncManager._push_single_issue()` posts a closing comment when `issue.duplicate_of` is set
- `test_get_labels_for_issue_with_blocked_by_adds_label()` passes
- `test_push_single_issue_adds_duplicate_of_comment()` passes
- All existing sync tests still pass

## Scope Boundaries

- **In scope**: `sync.py` and `test_sync.py` only
- **Out of scope**: Dependency graph, validation, dependency mapper display (separate children)
- **Depends on**: ENH-1430 — `IssueInfo.blocked_by`, `.duplicate_of` fields must be accessible

## Impact

- **Priority**: P2 — Part of relationship field standardization epic (ENH-1432); needed for GitHub sync to reflect local issue relationships
- **Effort**: Small — Targeted changes to two methods plus two unit tests; no new abstractions
- **Risk**: Low — Additive only; no existing label or push behavior changes
- **Breaking Change**: No

## Labels

`enhancement`, `github-sync`

## Status

**Open** | Created: 2026-05-10 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-05-11T02:24:30 - `e057bbb2-c08a-407a-b509-825a5527bb66.jsonl`
- `/ll:wire-issue` - 2026-05-11T02:19:58 - `9f49300b-cc50-4516-9631-31f97704f9ef.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00 - `99c8c5a2-312b-4736-9bbd-38f6355b06a6.jsonl`
- `/ll:refine-issue` - 2026-05-11T02:16:36 - `ed02f0e3-d7d1-4ccf-8a41-f8076521a4ab.jsonl`
- `/ll:issue-size-review` - 2026-05-10T23:55:00Z - `49b56280-19ff-42e9-bb93-088d6e560fa2.jsonl`
