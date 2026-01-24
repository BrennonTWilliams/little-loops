---
discovered_date: 2026-01-24
discovered_by: audit
---

# ENH-137: Make config reading explicit in create_sprint command

## Summary

The `/ll:create_sprint` command uses `{{config.sprints.*}}` template syntax that doesn't auto-interpolate. The command should explicitly instruct Claude to read the config file first.

## Context

The command's Configuration section (lines 23-33) shows template placeholders like `{{config.sprints.sprints_dir}}`, but Claude Code commands don't support automatic Jinja-style interpolation. Claude must read `.claude/ll-config.json` to get actual values.

Other commands like `capture_issue.md` handle this more explicitly in their process steps.

## Current Behavior

The Configuration section lists config values with template syntax, but doesn't explicitly instruct to read the config file before using these values.

## Expected Behavior

Add an explicit step at the beginning of the Process section to read and parse the configuration.

## Proposed Solution

Add a new Step 0 before the current Step 1:

```markdown
### Step 0: Load Configuration

Read the project configuration from `.claude/ll-config.json` to get sprint settings:

Use the Read tool to read `.claude/ll-config.json`, then extract:
- `sprints.sprints_dir` - Directory for sprint files (default: `.sprints`)
- `sprints.default_mode` - Default execution mode (default: `auto`)
- `sprints.default_timeout` - Default timeout in seconds (default: `3600`)
- `sprints.default_max_workers` - Default worker count (default: `4`)
- `issues.base_dir` - Issues directory (default: `.issues`)

Store these values for use in subsequent steps.
```

Then update references throughout the document to use "the configured sprints directory" instead of raw template syntax.

## Impact

- **Priority**: P4 (low - clarity improvement)
- **Effort**: Low
- **Risk**: Low

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| config | .claude/ll-config.json | Configuration file to read |
| commands | commands/capture_issue.md | Example of explicit config handling |

## Labels

`enhancement`, `create_sprint`, `documentation`

---

## Status

**Open** | Created: 2026-01-24 | Priority: P4
