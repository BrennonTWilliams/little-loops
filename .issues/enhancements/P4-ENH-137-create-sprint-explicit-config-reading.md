---
discovered_date: 2026-01-24
discovered_by: audit
---

# ENH-137: Make config reading explicit in create_sprint command

## Summary

The `/ll:create-sprint` command uses `{{config.sprints.*}}` template syntax that doesn't auto-interpolate. The command should explicitly instruct Claude to read the config file first.

## Context

The command's Configuration section (lines 23-33) shows template placeholders like `{{config.sprints.sprints_dir}}`, but Claude Code commands don't support automatic Jinja-style interpolation. Claude must read `.claude/ll-config.json` to get actual values.

Some commands like `handoff.md` and `configure.md` handle this more explicitly by including config reading instructions in their process steps.

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
| commands | commands/handoff.md | Example of explicit config reading |
| commands | commands/configure.md | Example of explicit config reading |

## Labels

`enhancement`, `create_sprint`, `documentation`

---

## Status

**Completed** | Created: 2026-01-24 | Priority: P4

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-24
- **Status**: Completed

### Changes Made
- `commands/create_sprint.md`: Updated Configuration section to use explicit "Read settings from" language instead of template syntax
- `commands/create_sprint.md`: Added Step 0: Load Configuration with explicit instructions to read `.claude/ll-config.json`
- `commands/create_sprint.md`: Updated all hardcoded paths and values to reference configured values (issues.base_dir, sprints.sprints_dir, etc.)
- `commands/create_sprint.md`: Updated YAML example to reference configured defaults
- `commands/create_sprint.md`: Updated Integration section to reference "configured sprints directory"

### Verification Results
- Tests: N/A (command documentation change)
- Lint: PASS
- Types: PASS
