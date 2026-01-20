---
discovered_commit: 0688f71
discovered_branch: main
discovered_date: 2026-01-20T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-096: README.md missing 3 commands in command tables

## Summary

Documentation issue found by `/ll:audit_docs`. The README.md Commands section tables are missing entries for 3 commands that exist in the `commands/` directory.

## Location

- **File**: `README.md`
- **Line(s)**: 249-303
- **Section**: Commands

## Problem

The following commands exist in `commands/*.md` but are not documented in the README Commands section:

| Missing Command | Description | Should Be In Section |
|-----------------|-------------|---------------------|
| `/ll:capture_issue` | Capture issues from conversation or natural language | Issue Management |
| `/ll:create_loop` | Create FSM loop configurations interactively | New section or Automation |
| `/ll:align_issues` | Validate issues against key documents | Issue Management |

## Current State

README shows 24 commands in the overview (correct), but the detailed command tables only list 21 commands.

## Expected Content

Add to Issue Management section:

```markdown
| `/ll:capture_issue [input]` | Capture issues from conversation |
| `/ll:align_issues [category]` | Validate issues against key documents |
```

Add new section or under existing:

```markdown
### Automation Loops

| Command | Description |
|---------|-------------|
| `/ll:create_loop` | Interactive FSM loop creation |
```

## Impact

- **Severity**: Medium (users may not discover these features)
- **Effort**: Small
- **Risk**: Low

## Verification

```bash
# Count commands in README tables vs actual
grep -c '/ll:' README.md  # Check mentions
ls commands/*.md | wc -l   # Should be 24
```

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-20 | Priority: P3
