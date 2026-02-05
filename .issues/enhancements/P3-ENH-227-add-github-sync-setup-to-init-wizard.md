---
discovered_date: 2026-02-05
discovered_by: capture_issue
---

# ENH-227: Add GitHub sync setup to init wizard

## Summary

Update `/ll:init` to include a question asking whether the user wants to enable GitHub Issue syncing via `/ll:sync_issues`. When enabled, this should configure the `sync` section in `ll-config.json`, defer to GitHub for correct Issue IDs, and make the setting editable via `/ll:configure`. All related issue commands and skills should respect this setting.

## Context

User description: "Update `/ll:init` to add a question to enable syncing to github via the `/ll:sync_issues` command. This should include deferring to Github for the correct Issue IDs, editing this setting via the `/ll:configure` command, and all related Issue commands and Skills."

## Current Behavior

The `/ll:init` wizard does not ask about GitHub Issue syncing during project setup. Users must manually add `sync` configuration to `ll-config.json` or discover the feature independently.

## Expected Behavior

1. `/ll:init` includes a step asking if the user wants to enable GitHub Issue syncing
2. If enabled, the `sync` section is populated in `ll-config.json` with sensible defaults (label mapping, priority labels, sync_completed preference)
3. GitHub is treated as the source of truth for Issue IDs when sync is enabled
4. `/ll:configure` supports editing the sync settings interactively
5. All issue-related commands and skills respect the sync.enabled flag

## Proposed Solution

1. Add a new question to the `/ll:init` wizard skill asking about GitHub sync
2. When "yes", populate `sync.enabled: true` and `sync.github` defaults in `ll-config.json`
3. Verify `/ll:configure` already handles the sync section (or add support)
4. Audit issue commands/skills to ensure they check `sync.enabled` where relevant

## Impact

- **Priority**: P3
- **Effort**: Medium
- **Risk**: Low

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | System design for commands and config |
| guidelines | .claude/CLAUDE.md | Plugin configuration and command references |

## Labels

`enhancement`, `captured`

---

## Status

**Open** | Created: 2026-02-05 | Priority: P3
