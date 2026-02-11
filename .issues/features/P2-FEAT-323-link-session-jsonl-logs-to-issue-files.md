---
discovered_date: 2026-02-10
discovered_by: capture_issue
---

# FEAT-323: Link Session JSONL Logs to Issue Files

## Summary

Add session log linking to issue files so that each issue tracks which Claude Code JSONL session files were involved in its lifecycle. When an issue is completed via `/ll:manage_issue`, the issue file is updated with a link to the implementation session's JSONL file(s) in `~/.claude/projects/`. When other commands (`/ll:capture_issue`, `/ll:scan_codebase`, `/ll:refine_issue`, etc.) create or update an issue, they append a session log entry with the command name and timestamp.

## Current Behavior

Issue files have no reference to the Claude Code session logs that created, modified, or implemented them. Session data in `~/.claude/projects/` is disconnected from the issues it relates to.

## Expected Behavior

Issue files contain a `## Session Log` section that accumulates entries linking to the JSONL session files involved:

```markdown
## Session Log
- `/ll:capture_issue` - 2026-02-10T14:32:00 - `~/.claude/projects/.../abc123.jsonl`
- `/ll:refine_issue` - 2026-02-10T15:00:00 - `~/.claude/projects/.../def456.jsonl`
- `/ll:manage_issue` - 2026-02-10T16:45:00 - `~/.claude/projects/.../ghi789.jsonl`
```

## Motivation

Session logs contain rich implementation context — decisions made, alternatives considered, errors encountered. Linking them to issues enables post-hoc analysis of how issues were resolved, feeds into the planned SQLite history DB (FEAT-324), and supports learning from past implementations.

## Use Case

A developer completes an issue and later wants to understand why a particular implementation approach was chosen. They open the issue file, find the session log link for the `/ll:manage_issue` run, and use `ll-messages` to review the conversation that led to the implementation decisions.

## Acceptance Criteria

- [ ] A utility function resolves the current session's JSONL file path from within a running Claude Code session
- [ ] `/ll:manage_issue` appends a session log entry on issue completion
- [ ] `/ll:capture_issue` appends a session log entry when creating or updating issues
- [ ] `/ll:scan_codebase` appends a session log entry when creating issues
- [ ] `/ll:refine_issue` appends a session log entry when updating issues
- [ ] Session log entries include command name, ISO timestamp, and absolute JSONL path
- [ ] `## Session Log` section is added to `issue-sections.json` as a common section
- [ ] Existing `ll-messages` code is reused for JSONL path discovery

## API/Interface

```python
# New utility in scripts/little_loops/
def get_current_session_jsonl() -> Optional[Path]:
    """Resolve the active Claude Code session's JSONL file path."""
    ...

def append_session_log_entry(issue_path: Path, command: str) -> None:
    """Append a session log entry to an issue file's Session Log section."""
    ...
```

## Proposed Solution

Leverage the existing `ll-messages` JSONL discovery logic in `scripts/little_loops/` to locate session files. Create a small utility module that:

1. Resolves the current session's JSONL path (likely by finding the most recently modified `.jsonl` in the project's `~/.claude/projects/` directory matching the current project)
2. Provides an `append_session_log_entry()` function that skills/commands call
3. Each command that creates/updates issues calls this function as a final step

The main challenge is reliably identifying the *active* session file. `ll-messages` finds them after the fact — the utility needs to identify the in-progress one, likely by matching the project path and finding the most recent file.

## Integration Map

### Files to Modify
- `commands/manage_issue.md` - Add session log append on completion
- `commands/capture_issue.md` - Add session log append on create/update
- `commands/scan_codebase.md` - Add session log append on create
- `commands/refine_issue.md` - Add session log append on update
- `templates/issue-sections.json` - Add Session Log section definition

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli.py` - Reuse JSONL discovery logic (main_messages function)

### Similar Patterns
- N/A

### Tests
- `scripts/tests/` - Tests for session JSONL resolution and log entry appending

### Documentation
- `docs/ARCHITECTURE.md` - Document session linking design

### Configuration
- N/A

## Implementation Steps

1. Create utility for resolving current session JSONL path (reuse `ll-messages` logic)
2. Create `append_session_log_entry()` function
3. Add `Session Log` section to `issue-sections.json`
4. Integrate into `manage_issue`, `capture_issue`, `scan_codebase`, `refine_issue` skills
5. Add tests for the utility functions
6. Verify end-to-end with a test issue lifecycle

## Impact

- **Priority**: P2 - Foundational for the SQLite history DB (FEAT-324) and historical analysis
- **Effort**: Medium - Core utility is small but touches multiple skills
- **Risk**: Low - Additive change, no breaking modifications
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Session/issue lifecycle design |
| guidelines | CONTRIBUTING.md | Skill modification conventions |

## Labels

`feature`, `captured`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P2

---

## Verification Notes

- **Verified**: 2026-02-11
- **Verdict**: VALID (updated)
- .ll/ directory does not exist — no local state storage implemented
- No session log linking exists in issue files
- JSONL discovery logic lives in `scripts/little_loops/cli.py` (main_messages), not a separate `messages.py`
- Fixed: Files to Modify section corrected from `skills/` to `commands/` paths
- Feature is new work, no existing implementation
