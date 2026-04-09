---
id: FEAT-1009
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-09
discovered_by: capture-issue
---

# FEAT-1009: ll-issues path sub-command to resolve issue ID to file path

## Summary

Add a `path` sub-command to `ll-issues` that accepts an issue ID in any of the three supported formats (`P3-FEAT-1002`, `FEAT-1002`, or `1002`) and prints the relative path from the project root to that issue file in `.issues/`. This enables scripts and skills to resolve issue IDs to concrete file paths without shelling out to `find` or parsing directory listings.

## Current Behavior

There is no dedicated way to look up an issue file path by ID from the CLI. Scripts that need a file path must either use `ll-issues show --json <ID>` and extract the `path` field, or scan `.issues/` manually. The `show` sub-command already resolves IDs via `_resolve_issue_id` in `show.py`, but it outputs a full formatted card — not a bare path.

## Expected Behavior

```bash
ll-issues path 1009
# .issues/features/P3-FEAT-1009-ll-issues-path-subcommand-resolve-issue-id-to-file-path.md

ll-issues path FEAT-1009
# .issues/features/P3-FEAT-1009-ll-issues-path-subcommand-resolve-issue-id-to-file-path.md

ll-issues path P3-FEAT-1009
# .issues/features/P3-FEAT-1009-ll-issues-path-subcommand-resolve-issue-id-to-file-path.md
```

Exits 0 on success, 1 if the issue is not found.

## Acceptance Criteria

- `ll-issues path <ID>` prints the relative path for all three input formats (numeric, TYPE-NNN, P-TYPE-NNN)
- Searches active, completed, and deferred directories (matches `show` behavior)
- Exits 0 on match, 1 on not found with an error message to stderr
- Optional `--json` flag outputs `{"path": "..."}` for programmatic use
- Alias `p` registered (consistent with `show` having alias `s`)

## Motivation

Skills, hooks, and shell scripts frequently need to locate issue files by ID. Currently they must either invoke `ll-issues show --json` and parse JSON, or glob `.issues/**/*.md` and match manually. A dedicated `path` sub-command makes this a one-liner and is consistent with the Unix philosophy of composable tools.

## Use Case

A skill wants to open the file for `FEAT-1009` in an editor or read it with `cat`. With this sub-command:

```bash
ISSUE_PATH=$(ll-issues path FEAT-1009)
cat "$ISSUE_PATH"
```

Without it, the skill must use `ll-issues show --json FEAT-1009 | python3 -c "import sys,json; print(json.load(sys.stdin)['path'])"`.

## Proposed Solution

1. Add `scripts/little_loops/cli/issues/path_cmd.py` with `cmd_path(config, args)` that calls `_resolve_issue_id` (already in `show.py`) and prints the relative path.
2. Extract `_resolve_issue_id` into a shared helper (e.g., `scripts/little_loops/cli/issues/_resolve.py`) so both `show.py` and `path_cmd.py` import it without circular deps, OR import it directly from `show.py`.
3. Register the `path` sub-command in `__init__.py` with alias `p`.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/__init__.py` — register `path` sub-command + alias `p`; add dispatch branch; import `cmd_path`
- `scripts/little_loops/cli/issues/show.py` — extract `_resolve_issue_id` to shared module OR leave in place and import from here

### New Files

- `scripts/little_loops/cli/issues/path_cmd.py` — `cmd_path(config, args) -> int`

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/show.py` — shares `_resolve_issue_id` logic; may become importer if helper is extracted

### Similar Patterns

- `scripts/little_loops/cli/issues/show.py` — same ID resolution, same `--json` flag pattern
- `scripts/little_loops/cli/issues/next_issue.py` — `--path` flag pattern for path-only output

### Tests

- `scripts/tests/test_cli_ll_issues.py` or a new `test_cli_ll_issues_path.py`
- Test all three input formats (numeric, TYPE-NNN, P-TYPE-NNN) resolve correctly
- Test not-found case returns exit code 1
- Test `--json` flag output

## API/Interface

```python
# scripts/little_loops/cli/issues/path_cmd.py
def cmd_path(config: BRConfig, args: argparse.Namespace) -> int:
    """Print relative path to an issue file.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id (str) and optional .json (bool)

    Returns:
        0 if found, 1 if not found
    """
```

```
usage: ll-issues path [-h] [--json] issue_id

positional arguments:
  issue_id    Issue ID (e.g., 1009, FEAT-1009, P3-FEAT-1009)

options:
  --json, -j  Output as JSON object {"path": "..."}
```

## Implementation Steps

1. **Extract or reuse `_resolve_issue_id`** — check if importing from `show.py` is clean; if not, move to `scripts/little_loops/cli/issues/_resolve.py`
2. **Create `path_cmd.py`** — implement `cmd_path`; use `config.project_root` for relative path computation (same as `show.py`)
3. **Register in `__init__.py`** — add `path` parser with alias `p`, `--json` flag, dispatch branch, and update epilog
4. **Write tests** — cover all three ID formats, not-found, and `--json` output
5. **Verify** — run `ll-issues path 1009` against a real issue; check exit codes

## Impact

- **Priority**: P3 - Medium (frequently useful in scripting contexts)
- **Effort**: XS — ~50 lines of new code; ID resolution already implemented
- **Risk**: Low — additive; no changes to existing sub-commands
- **Breaking Change**: No

## Related Key Documentation

| Category | File | Relevance |
|----------|------|-----------|
| Architecture | `docs/reference/API.md` | CLI module conventions |
| Guidelines | `CONTRIBUTING.md` | Code style and test patterns |

## Labels

`feat`, `cli`, `ll-issues`, `scripting`, `captured`

## Status

**Open** | Created: 2026-04-09 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-09T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
