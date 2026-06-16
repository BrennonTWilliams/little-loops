---
id: ENH-2175
title: Record the feature branch (and PR URL) back to the issue for PR linkage
type: ENH
status: done
priority: P4
parent: EPIC-2171
captured_at: '2026-06-15T16:51:50Z'
completed_at: '2026-06-16T18:41:48Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels:
- parallel
- feature-branches
- issues
- traceability
- open-pr
blocked_by:
- BUG-2172
confidence_score: 98
outcome_confidence: 84
score_complexity: 19
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 25
decision_needed: false
---

# ENH-2175: Record the feature branch (and PR URL) back to the issue for PR linkage

## Summary

When `ll-parallel` runs in feature-branch mode, each completed issue's branch name (and eventual PR URL) is written back to the issue frontmatter as `branch:` and `pr_url:`, enabling `/ll:open-pr` to find the implementing branch without manual lookup or git-ref guessing.

## Motivation

In feature-branch mode the branch name is derived from the issue title slug
(`feature/<id>-<slug>`, `worker_pool.py:248`) and tracked only in the
orchestrator's in-memory `_pr_ready_branches` map, which is printed once at the
end of the run and then discarded. Nothing is written back to the issue file,
so there is no durable link from an issue to the branch (or PR) that implemented
it, and no handoff to `/ll:open-pr`. After the run ends, recovering "which
branch implements ENH-123?" requires guessing the slug or grepping git refs.

## Current Behavior

- `worker_pool.py:248` computes `feature/<id>-<slug>`; the value lives on the
  `WorkerResult` and in `orchestrator._pr_ready_branches`.
- `orchestrator.py:1225` prints the branch list at end-of-run; it is not
  persisted to the issue.
- No frontmatter field records the branch; `/ll:open-pr` has no per-issue branch
  hint to consume.

## Expected Behavior

- After a feature-branch run, each completed issue's frontmatter contains `branch: feature/<id>-<slug>`.
- When BUG-2172 PR creation is enabled, `pr_url: <url>` is also written to the issue frontmatter.
- `/ll:open-pr` reads `branch:` from the issue and skips PR creation if `pr_url:` is already present.
- Issues processed in auto-merge mode (non-feature-branch) have no `branch:` or `pr_url:` field written.

## Proposed Solution

1. On successful completion in feature-branch mode, write the branch name back
   to the issue frontmatter (e.g. `branch: feature/enh-123-...`).
2. Once BUG-2172 adds push/PR, also record the PR URL (e.g. `pr_url:`) when a PR
   is created.
3. Have `/ll:open-pr` read the recorded `branch:` (and short-circuit if `pr_url:`
   already set) so the PR step is one command, not a manual lookup.

## API/Interface

- New optional issue frontmatter fields: `branch: <string>`, `pr_url: <string>`.
  Document in the issue file format / config schema as applicable.

## Acceptance Criteria

1. After a feature-branch run, each completed issue's frontmatter records the
   branch that implemented it.
2. If BUG-2172 PR creation is enabled, the PR URL is recorded too.
3. `/ll:open-pr` consumes the recorded branch for the issue (and skips if a PR
   URL is already present).
4. Issues processed in non-feature-branch (auto-merge) mode are unaffected — no
   `branch:` field is written.
5. **Idempotent on re-run**: re-running an issue updates `branch:` in place
   (no duplicate keys) and does **not** clobber an existing `pr_url:` — if a PR
   URL is already recorded, it is preserved unless a new PR was demonstrably
   created this run.

## Implementation Steps

1. **`orchestrator.py:_on_worker_complete()` — add write-back after push/PR block**: Immediately before `self._pr_ready_branches[issue_id] = branch_state`, read the issue file via `info.path.read_text()`, call `parse_frontmatter(content)` to guard `pr_url:` idempotency, build `updates = {"branch": result.branch_name}` (add `pr_url` only if `branch_state["pr_url"]` is set and not already in frontmatter), call `update_frontmatter(content, updates)`, write back with `info.path.write_text(...)`, and commit via `self._git_lock.run(["add", "-A"], cwd=self.repo_path)` + `["commit", "-m", f"{issue_id}: record feature branch in frontmatter"]`.
2. **`commands/open-pr.md` — read `branch:` and `pr_url:` from issue frontmatter**: In the initial setup steps, after the user specifies an issue ID, check the issue's frontmatter for `pr_url:` (short-circuit: "PR already recorded at <url>, nothing to do") and `branch:` (use as branch hint if the user is not already on a matching branch).
3. **Tests in `scripts/tests/test_orchestrator.py`**: Following the `TestOnWorkerComplete` (line 1506) fixture pattern — write a real issue file to `original_path`, mock `subprocess.run` for push + `gh pr create`, invoke `_on_worker_complete(result)` with `use_feature_branches=True`, assert `parse_frontmatter(original_path.read_text()).get("branch") == expected`. Add negative and idempotency variants (see Integration Map → Tests).
4. **`config-schema.json`** — add optional `branch` (string) and `pr_url` (string) fields to any issue frontmatter schema definition.
5. **Verify**: `python -m pytest scripts/tests/test_orchestrator.py -v -k "feature_branch or branch"` + `python -m mypy scripts/little_loops/parallel/orchestrator.py`.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — insert write-back in `_on_worker_complete()` **after** `_open_pr_for_branch()` completes and `branch_state` has its final values (see Sequencing Detail below). Do **not** add to `_complete_issue_lifecycle_if_needed()` — it is called before `branch_state` is constructed.
- `commands/open-pr.md` — add a step to read `branch:` from issue frontmatter as the branch hint; short-circuit with a "PR already recorded" message if `pr_url:` is present.

### Dependent Files (Read-Only Context)
- `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool._process_issue()` computes `branch_name = f"feature/{issue.issue_id.lower()}-{slugify(issue.title)}"` and returns it on `WorkerResult.branch_name`; no changes needed here.
- `scripts/little_loops/parallel/types.py` — `WorkerResult` dataclass (line 52) already has `branch_name: str`; no `pr_url` field needed (PR URL lives only in orchestrator's `branch_state` dict).
- `scripts/little_loops/frontmatter.py` — `update_frontmatter()` and `parse_frontmatter()`: `update_frontmatter` is already imported in `orchestrator.py` (line 23); `parse_frontmatter` must be added to the same import. `update_frontmatter` accepts an arbitrary `dict[str, Any]`; `parse_frontmatter` is needed for the idempotency check on `pr_url:`.

### Sequencing Detail (Critical)

The current call order inside `_on_worker_complete()` for the feature-branch arm:

1. `_complete_issue_lifecycle_if_needed(issue_id)` — writes `status: done` + `completed_at:` **before** `branch_state` exists.
2. `branch_state = {"branch_name": result.branch_name, "pushed": False, "pr_url": None}` is constructed.
3. Push block runs; `_open_pr_for_branch()` may mutate `branch_state["pr_url"]` to a URL string.
4. **← Insert here**: read issue file, call `parse_frontmatter()` for idempotency check, build `updates` dict with `branch:` and conditionally `pr_url:`, call `update_frontmatter()`, write back, commit via `_git_lock`.
5. `self._pr_ready_branches[issue_id] = branch_state`

### Idempotency Guard (Caller-Side Pattern)
```python
content = info.path.read_text()
fm = parse_frontmatter(content)
updates: dict[str, Any] = {"branch": result.branch_name}
if branch_state.get("pr_url") and not fm.get("pr_url"):
    updates["pr_url"] = branch_state["pr_url"]
content = update_frontmatter(content, updates)
info.path.write_text(content)
```
`update_frontmatter` always overwrites keys in the dict, so caller must guard `pr_url:` itself. `branch:` is always written (idempotent overwrite is safe — same value each run for a given issue).

### Similar Patterns
- `orchestrator.py:_complete_issue_lifecycle_if_needed()` (line 1292) — exact read / `update_frontmatter` / write / `_git_lock` commit sequence to replicate.
- `sync.py:_update_local_frontmatter()` (line 519) — precedent for writing a URL-typed field (`github_url:`) back to issue frontmatter after an external call succeeds.
- `cli/issues/set_status.py:cmd_set_status()` (line 13) — minimal read / `update_frontmatter` / write pattern without git commit.

### Tests
- `scripts/tests/test_orchestrator.py` — add cases in/near `TestOnWorkerComplete` (line 1506) and `TestCompleteIssueLifecycle` (line 2174).
  - Fixture pattern: write a real issue file to `original_path`; set `mock_issue.path = original_path`; fake `subprocess.run` for `git push` and `gh pr create` via `patch("little_loops.parallel.orchestrator.subprocess.run", ...)`; invoke `_on_worker_complete(result)` with `use_feature_branches=True`; assert `parse_frontmatter(original_path.read_text()).get("branch") == "feature/enh-2175-..."`. *(Note: `parse_frontmatter` must be added to the `from little_loops.frontmatter import` line in orchestrator.py — only `update_frontmatter` is currently imported.)*
  - Negative test: `use_feature_branches=False` (auto-merge arm) → assert no `branch:` key in frontmatter.
  - Idempotency test: pre-populate `pr_url: https://existing-url` in the file; re-run; assert URL unchanged.

### Documentation
- `docs/reference/API.md` — note new optional `branch:` and `pr_url:` frontmatter fields.
- `.claude/CLAUDE.md` § Issue File Format — reference optional fields (coordinate with EPIC-2171 doc pass).

### Configuration
- `config-schema.json` — extend any issue frontmatter schema section with optional `branch` (string) and `pr_url` (string) fields.

## Scope Boundaries

- `branch:` recording is gated to feature-branch mode only; auto-merge runs are unaffected.
- `pr_url:` recording depends on BUG-2172 being implemented first; this ENH covers `branch:` persistence independently.
- Retroactive backfill of `branch:` for previously completed issues is out of scope.
- Branch naming convention (`feature/<id>-<slug>`) is unchanged by this ENH.
- No changes to how `/ll:open-pr` creates PRs — only how it discovers the branch to use.

## Impact

- **Priority**: P4 — traceability/polish; depends on the workflow existing
  (BUG-2172) to be fully valuable, but `branch:` persistence is useful alone.
- **Effort**: Small–Medium.
- **Risk**: Low — additive frontmatter; gated to feature-branch mode.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-15 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-06-16T18:34:31 - `9ebeb009-82d7-499d-9df4-cce68a1bb95f.jsonl`
- `/ll:confidence-check` - 2026-06-16T00:00:00Z - `652072f2-a11c-4dd7-9a33-67f1e5b1a03c.jsonl`
- `/ll:refine-issue` - 2026-06-16T18:27:11 - `9a7e4935-ffcc-464a-83c8-4893caceeb93.jsonl`
- `/ll:confidence-check` - 2026-06-16T00:00:00Z - `1b991b43-1dc3-4bec-bad5-f0d4047b05d1.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-15T20:33:22 - `708f5540-fdfd-4ca1-92bc-72a7cb548730.jsonl`
- `/ll:format-issue` - 2026-06-15T16:58:05 - `bffefeb0-fbda-400c-89f6-f9e3c1696323.jsonl`
- `/ll:capture-issue` - 2026-06-15T16:51:50Z - `5b1dd63b-714f-41e9-b9c2-f55f8ebd0e98.jsonl`
