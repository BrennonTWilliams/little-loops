---
discovered_commit: 0688f71
discovered_branch: main
discovered_date: 2026-01-20T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-096: README.md missing 6 commands in command tables

## Summary

Documentation issue found by `/ll:audit-docs`. The README.md Commands section tables are missing entries for 6 commands that exist in the `commands/` directory.

## Location

- **File**: `README.md`
- **Line(s)**: 249-303 (Commands section)
- **Anchor**: `## Commands`

## Problem

The following commands exist in `commands/*.md` but are not documented in the README Commands section:

| Missing Command | Description | Should Be In Section |
|-----------------|-------------|---------------------|
| `/ll:capture-issue` | Capture issues from conversation or natural language | Issue Management |
| `/ll:align-issues` | Validate issues against key documents | Issue Management |
| `/ll:audit-claude-config` | Audit Claude Code plugin configuration | Documentation & Analysis |
| `/ll:cleanup-worktrees` | Clean orphaned git worktrees from interrupted ll-parallel runs | Git & Workflow |
| `/ll:create-loop` | Create FSM loop configurations interactively | New section or Automation |
| `/ll:toggle-autoprompt` | Toggle automatic prompt optimization settings | Session Management |

## Current State

README shows 24 commands in the overview (line 13: "24 slash commands"), but the detailed command tables only list 18 commands.

## Expected Content

Add to **Issue Management** section:

```markdown
| `/ll:capture-issue [input]` | Capture issues from conversation |
| `/ll:align-issues [category]` | Validate issues against key documents |
```

Add to **Documentation & Analysis** section:

```markdown
| `/ll:audit-claude-config` | Audit Claude Code plugin configuration |
```

Add to **Git & Workflow** section:

```markdown
| `/ll:cleanup-worktrees` | Clean orphaned git worktrees |
```

Add to **Session Management** section:

```markdown
| `/ll:toggle-autoprompt` | Toggle automatic prompt optimization |
```

Add new **Automation** section:

```markdown
### Automation

| Command | Description |
|---------|-------------|
| `/ll:create-loop` | Interactive FSM loop creation |
```

## Impact

- **Severity**: Medium (users may not discover these features)
- **Effort**: Small
- **Risk**: Low

## Verification

```bash
# Count commands in README tables vs actual
grep -E '^\| `/ll:' README.md | wc -l  # Currently 18, should be 24
ls commands/*.md | wc -l               # Should be 24
```

## Labels

`bug`, `documentation`, `auto-generated`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-20
- **Status**: Completed

### Changes Made
- `README.md`: Added 6 missing commands to command tables:
  - Issue Management: `/ll:capture-issue`, `/ll:align-issues`
  - Documentation & Analysis: `/ll:audit-claude-config`
  - Git & Workflow: `/ll:cleanup-worktrees`, `/ll:create-loop`
  - Session Management: `/ll:toggle-autoprompt`

### Verification Results
- Commands documented: 24/24
- Command files: 24/24
- All counts match

### Notes
- `/ll:create-loop` placed in Git & Workflow (not a new Automation section) since it creates workflow configurations
- `/ll:align-issues` uses `<category>` (required argument) not `[category]` (optional) per command definition

---

## Status

**Completed** | Created: 2026-01-20 | Resolved: 2026-01-20 | Priority: P3
