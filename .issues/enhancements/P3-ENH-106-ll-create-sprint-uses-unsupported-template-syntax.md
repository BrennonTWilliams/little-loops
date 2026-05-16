---
discovered_date: 2026-01-22
discovered_by: capture_issue
---

# ENH-106: create_sprint uses unsupported template syntax

## Summary

The `/ll:create-sprint` command uses Handlebars-style template syntax like `{{config.issues.base_dir}}` throughout the document, but Claude Code does not support this templating. The values are not substituted, causing Claude to attempt literal commands with `{{config...}}` in them.

## Context

Identified during audit of the `/ll:create-sprint` slash command. Multiple lines reference config values using template syntax that doesn't work.

**File**: `.claude/commands/create_sprint.md`
**Anchor**: `## Configuration`

## Current Behavior

Lines 22-23, 62, 74 contain:
```markdown
- **Issues base**: `{{config.issues.base_dir}}`
- **Categories**: `{{config.issues.categories}}`
```

```bash
find {{config.issues.base_dir}} -name "*.md" ...
```

Claude will try to execute `find {{config.issues.base_dir}} -name ...` literally, which fails.

## Expected Behavior

The command should either:
1. Use hardcoded default values (`.issues`)
2. Or explicitly instruct Claude to first read `.claude/ll-config.json` and use the values from there

## Proposed Solution

Replace template syntax with explicit instructions:

```markdown
## Configuration

First read `.claude/ll-config.json` to get project settings:
- Issues are stored in the directory specified by `issues.base_dir` (default: `.issues`)
- Categories include `bugs`, `features`, `enhancements`
- Sprints are stored in `.sprints/`
```

Then update bash examples to use variable assignment after reading config.

## Impact

- **Priority**: P3 - Commands may fail without explicit config reading
- **Effort**: Low - Text updates throughout command
- **Risk**: Low - Documentation change only

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Plugin configuration |

## Labels

`enhancement`, `commands`, `documentation`

---

**Priority**: P3 | **Created**: 2026-01-22

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-22
- **Status**: Completed

### Changes Made
- `.claude/commands/create_sprint.md`: Replaced template syntax with prose instructions
  - Configuration section now instructs Claude to read config file
  - Bash examples use hardcoded `.issues` default path
  - Lines 22-24, 62, 74 updated

### Verification Results
- Template syntax removed: PASS (0 instances of `{{config`)
- Lint: PASS
- Types: PASS
