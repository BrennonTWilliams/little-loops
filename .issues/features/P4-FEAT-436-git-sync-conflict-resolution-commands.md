---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# FEAT-436: Git sync conflict resolution commands

## Summary

The sync infrastructure (`SyncedIssue`, `SyncStatus`) tracks basic sync state but doesn't expose detailed conflict information or provide conflict resolution commands. When local and GitHub issues diverge, users have no built-in way to resolve conflicts.

## Current Behavior

`ll-sync` can push and pull issues, but when both local and GitHub versions have changed, there's no conflict detection or resolution mechanism. Users must manually compare and merge changes.

## Expected Behavior

- `ll-sync conflicts` shows issues with diverged local/GitHub state
- `ll-sync resolve <issue-id> --prefer-local|--prefer-github` resolves individual conflicts
- Clear output showing what changed on each side

## Motivation

Bidirectional sync between local files and GitHub Issues naturally leads to conflicts when both sides are edited. Without built-in resolution, users must manually diff and merge, which is error-prone and defeats the purpose of sync automation.

## Use Case

A developer edits an issue locally while a teammate updates the same issue on GitHub. Running `ll-sync conflicts` shows the divergence. The developer reviews both versions and runs `ll-sync resolve ENH-428 --prefer-local` to keep their changes, or `--prefer-github` to accept the remote version.

## Acceptance Criteria

- `ll-sync conflicts` lists issues where local and GitHub versions differ
- Shows summary of changes on each side (sections modified)
- `ll-sync resolve <id> --prefer-local` overwrites GitHub with local version
- `ll-sync resolve <id> --prefer-github` overwrites local with GitHub version
- Resolution updates sync state to mark conflict as resolved

## Proposed Solution

Add subcommands to `ll-sync`:

```python
def cmd_conflicts(args: Namespace) -> int:
    synced = load_sync_state()
    conflicts = [s for s in synced if s.local_changed and s.github_changed]
    for c in conflicts:
        print(f"{c.issue_id}: local modified {c.local_mtime}, github modified {c.github_mtime}")
    return 1 if conflicts else 0

def cmd_resolve(args: Namespace) -> int:
    if args.prefer == "local":
        push_issue(args.issue_id, force=True)
    else:
        pull_issue(args.issue_id, force=True)
    mark_resolved(args.issue_id)
    return 0
```

## Integration Map

### Files to Modify
- `scripts/little_loops/sync.py` — add conflict detection and resolution
- `scripts/little_loops/cli/sync_cli.py` — add subcommands (if CLI exists separately)

### Dependent Files (Callers/Importers)
- N/A

### Similar Patterns
- Existing `push` and `pull` subcommands in sync CLI

### Tests
- Add tests for conflict detection and resolution

### Documentation
- Update CLI help text

### Configuration
- N/A

## Implementation Steps

1. Add conflict detection logic to sync module
2. Add `conflicts` subcommand
3. Add `resolve` subcommand with `--prefer-local`/`--prefer-github`
4. Update sync state tracking
5. Add tests

## Impact

- **Priority**: P4 - Useful for team workflows, not critical for single-user
- **Effort**: Medium - New subcommands with state management
- **Risk**: Low - Explicit user action required for resolution
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `sync`, `cli`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Open** | Created: 2026-02-15 | Priority: P4
