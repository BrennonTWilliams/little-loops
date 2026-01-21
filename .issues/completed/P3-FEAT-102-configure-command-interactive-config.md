---
discovered_date: 2026-01-21
discovered_by: user_request
---

# FEAT-102: Add /ll:configure command for interactive config editing

## Summary

Create a new `/ll:configure` slash command that allows interactive configuration of specific areas in `.claude/ll-config.json` without re-running the full `/ll:init --interactive --force` wizard.

## Context

Currently, modifying configuration requires either:
1. Manually editing `.claude/ll-config.json`
2. Re-running `/ll:init --interactive --force` which walks through the entire setup

Users need a targeted way to modify specific configuration areas interactively.

## Proposed Solution

### Command Interface

```bash
# No args - interactive area selection via AskUserQuestion
/ll:configure

# Configure specific area interactively
/ll:configure <area>

# Show all areas with current status (read-only)
/ll:configure --list

# Show current config for an area (read-only)
/ll:configure <area> --show

# Reset area to defaults
/ll:configure <area> --reset
```

### Configurable Areas (10 total)

| Argument | Config Section | Description |
|----------|----------------|-------------|
| `project` | `project` | Test, lint, format, type-check, build commands |
| `issues` | `issues` | Base dir, categories, templates, capture style |
| `parallel` | `parallel` | ll-parallel: workers, timeouts, worktree files |
| `automation` | `automation` | ll-auto: workers, timeouts, streaming |
| `documents` | `documents` | Key document categories for issue alignment |
| `continuation` | `continuation` | Session handoff: auto-detect, includes, expiry |
| `context` | `context_monitor` | Context monitoring: threshold, limits |
| `prompt` | `prompt_optimization` | Prompt optimization: mode, confirm, bypass |
| `scan` | `scan` | Focus dirs, exclude patterns |
| `workflow` | `workflow` | Phase gates, deep research settings |

### Key Behaviors

1. **No args**: Use `AskUserQuestion` to let user select area (grouped into 4+4+2)
2. **Area selection**: Interactive questions specific to that area (1-2 rounds)
3. **Show current values**: Pre-populate options with current config values
4. **Diff before apply**: Show what will change before writing
5. **Minimal writes**: Only write non-default values to keep config clean
6. **Preserve other sections**: Merge changes without affecting unrelated config

## Implementation Notes

- Create new file: `commands/configure.md`
- Follow patterns from `init.md` (AskUserQuestion grouping) and `toggle_autoprompt.md` (config modification)
- Reference `config-schema.json` for default values and validation
- Use template syntax `{{config.section.key}}` for reading current values

## Acceptance Criteria

- [x] `/ll:configure` prompts for area selection
- [x] `/ll:configure <area>` runs interactive config for that area
- [x] `/ll:configure --list` shows all areas with status
- [x] `/ll:configure <area> --show` displays current settings
- [x] `/ll:configure <area> --reset` removes section (uses defaults)
- [x] Config changes are merged without losing other sections
- [x] Non-default values only are written to config

## Impact

- **Priority**: P3 (useful enhancement)
- **Effort**: Medium (command file + per-area question flows)
- **Risk**: Low (additive feature, no breaking changes)

## Labels

`feature`, `commands`, `configuration`, `developer-experience`

---

## Status

**Completed** | Created: 2026-01-21 | Completed: 2026-01-21 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-21
- **Status**: Completed

### Changes Made
- `commands/configure.md`: Created new command with full interactive configuration for all 10 config areas
- Supports `--list`, `--show`, `--reset` modes
- Interactive area selection using AskUserQuestion with 4+4+2 grouping
- Per-area configuration with 1-2 question rounds each
- Diff display before applying changes
- Minimal writes (only non-default values)

### Verification Results
- Lint: PASS (`ruff check scripts/`)
- Types: PASS (`python -m mypy scripts/little_loops/`)
