# FEAT-489: Add `diff` and `close` Subcommands to ll-sync

**Created**: 2026-03-02
**Issue**: `.issues/features/P3-FEAT-489-add-diff-and-close-subcommands-to-ll-sync.md`
**Status**: Plan

---

## Research Findings

### Current Architecture
- `cli/sync.py` defines `main_sync()` with argparse subparsers for `status`, `push`, `pull`
- Dispatch is inline `if/elif` on `args.action` (not separate handler functions)
- `sync.py` contains `GitHubSyncManager` with all sync logic
- `_run_gh_command()` is a module-level helper used for all `gh` CLI calls
- `--dry-run` is handled at manager level via `self.dry_run` flag
- Issue matching uses `github_issue` frontmatter field (integer GitHub issue number)
- `_get_local_issues()` scans category dirs + optionally completed dir
- `_get_local_github_numbers()` builds `set[int]` from frontmatter
- `parse_frontmatter(content, coerce_types=True)` extracts frontmatter fields
- `_get_issue_body(content)` returns body after frontmatter and title
- Tests use `patch("little_loops.sync._run_gh_command")` and `patch("little_loops.sync._check_gh_auth")` patterns

### Key Methods to Reuse
- `_check_gh_auth()` — auth guard (used by push and pull)
- `_run_gh_command()` — all `gh` CLI calls
- `_get_local_issues()` — scan local issue files
- `_get_local_github_numbers()` — get tracked GitHub numbers
- `_extract_issue_id()` — extract TYPE-NNN from filename
- `parse_frontmatter()` — read frontmatter from issue content
- `_get_issue_body()` — extract body for diff comparison

---

## Implementation Plan

### Phase 1: Add `diff` Subcommand to `GitHubSyncManager`

**File**: `scripts/little_loops/sync.py`

Add two methods to `GitHubSyncManager`:

#### 1a. `diff_issue(issue_id: str) -> SyncResult`
- Auth check via `_check_gh_auth()`
- Find local file matching `issue_id` via `_get_local_issues()` + `_extract_issue_id()`
- Read file content, parse frontmatter to get `github_issue` number
- If no `github_issue`, report error (not synced)
- Fetch GitHub issue body via `gh issue view <number> --json body -q .body`
- Get local body via `_get_issue_body(content)`
- Use `difflib.unified_diff()` to compute diff
- Store diff lines in `result.updated` (repurpose for diff output)
- In dry-run mode: same behavior (diff is read-only anyway)

#### 1b. `diff_all() -> SyncResult`
- Auth check
- For each local issue with `github_issue` in frontmatter:
  - Fetch GitHub body and compare
  - Report summary: "ISSUE-ID: N lines changed" or "ISSUE-ID: in sync"

### Phase 2: Add `close` Subcommand to `GitHubSyncManager`

**File**: `scripts/little_loops/sync.py`

Add `close_issues(issue_ids: list[str] | None = None, all_completed: bool = False) -> SyncResult`:

- Auth check
- **If `all_completed`**: Scan `.issues/completed/` for files with `github_issue` frontmatter
- **If `issue_ids` provided**: Find matching files (check both active and completed dirs)
- For each issue:
  - Read frontmatter to get `github_issue` number
  - If no number, skip (not synced to GitHub)
  - In dry-run: append "(would close)" to result
  - Otherwise: call `gh issue close <number> --comment "Closed via ll-sync. Completed locally."`
  - Append to `result.updated` on success
- Set `result.success = False` if any failures

### Phase 3: Add CLI Subparser Registration

**File**: `scripts/little_loops/cli/sync.py`

#### 3a. Register `diff` subparser
```python
diff_parser = subparsers.add_parser("diff", help="Show differences between local and GitHub issues")
diff_parser.add_argument(
    "issue_id",
    nargs="?",
    help="Specific issue ID to diff (e.g., BUG-123). Omit for all.",
)
```

#### 3b. Register `close` subparser
```python
close_parser = subparsers.add_parser("close", help="Close GitHub issues for completed local issues")
close_parser.add_argument(
    "issue_ids",
    nargs="*",
    help="Specific issue IDs to close (e.g., ENH-123)",
)
close_parser.add_argument(
    "--all-completed",
    action="store_true",
    help="Close all GitHub issues whose local counterparts are in completed/",
)
```

#### 3c. Add dispatch branches
Add `elif args.action == "diff":` and `elif args.action == "close":` blocks following the existing pattern.

#### 3d. Add `_print_diff_result()` helper
A specialized printer for diff output that shows unified diff content instead of the standard summary format.

#### 3e. Update epilog examples
Add `diff` and `close` usage examples to the parser epilog.

### Phase 4: Add Tests

**File**: `scripts/tests/test_sync.py`

Add new test classes:

#### `TestDiffIssue`
- `test_diff_shows_differences` — mock `gh issue view` returning different body, verify diff output
- `test_diff_no_github_issue` — issue without `github_issue` frontmatter, verify error
- `test_diff_in_sync` — same content, verify "in sync" message
- `test_diff_all_summary` — multiple issues, verify summary output
- `test_diff_auth_failure` — auth check fails, verify error

#### `TestCloseIssue`
- `test_close_specific_issue` — close by ID, verify `gh issue close` called
- `test_close_all_completed` — scan completed dir, verify all closed
- `test_close_no_github_issue` — issue not synced, verify skip
- `test_close_dry_run` — verify no `gh` calls made
- `test_close_auth_failure` — auth check fails, verify error
- `test_close_with_comment` — verify comment is passed to `gh issue close`

### Phase 5: Update CLI Import and Epilog

**File**: `scripts/little_loops/cli/sync.py`
- Update parser epilog to include diff and close examples
- No new imports needed (SyncResult already imported)

---

## Success Criteria

- [ ] `ll-sync diff BUG-123` shows unified diff between local and GitHub
- [ ] `ll-sync diff` (no ID) shows summary of all differences
- [ ] `ll-sync close ENH-123` closes the GitHub issue with a comment
- [ ] `ll-sync close --all-completed` closes all completed issues on GitHub
- [ ] `--dry-run` works for both diff and close
- [ ] All existing tests pass
- [ ] New tests cover diff and close operations
- [ ] Lint and type checks pass

---

## Decisions Made

1. **Diff output via `difflib.unified_diff`** — Standard Python library, no new dependencies
2. **`gh issue view` for fetching single issue body** — More efficient than listing all issues for a single diff
3. **`gh issue close --comment`** — Include completion note for traceability
4. **Reuse `SyncResult` for diff output** — Keeps the data contract consistent; diff lines stored in a new `diff_lines` or repurposed field
5. **Close searches both active and completed dirs** — A user might close a specific issue that's still active (edge case) but primarily targets completed ones
