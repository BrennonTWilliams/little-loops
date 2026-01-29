---
discovered_date: 2026-01-16T00:00:00Z
discovered_by: manual
---

# FEAT-080: User-local settings override via ll.local.md

## Summary

Add support for `.claude/ll.local.md` to allow per-user settings that override values in `ll-config.json`.

## Problem

Currently, `ll-config.json` is committed to the repository and shared across all users. There's no mechanism for individual developers to customize settings for their local environment without modifying the shared config file.

Use cases requiring local overrides:
- Different test commands for local debugging
- Personal preferences (e.g., different lint strictness during development)
- Local paths that differ from CI/team defaults
- Experimental settings not ready for team-wide use

## Proposed Solution

1. Support a new file: `.claude/ll.local.md`
2. Settings in `ll.local.md` override corresponding values in `ll-config.json`
3. File should be gitignored (user-specific, not committed to repo)
4. Follow existing `.local` pattern used by Claude Code settings

### File Format

Use YAML frontmatter in markdown (consistent with other plugin components):

```markdown
---
project:
  test_cmd: "python -m pytest scripts/tests/ -v --tb=short"
  lint_cmd: "ruff check scripts/ --fix"
scan:
  focus_dirs: ["scripts/", "my-experimental-dir/"]
---

# Local Settings Notes

Personal development preferences for this project.
```

### Merge Behavior

- Deep merge: nested objects are merged, not replaced
- Arrays: local values replace (not append to) config values
- Explicit `null` removes a setting from the merged result

## Implementation Notes

- Load `ll.local.md` after `ll-config.json` in `hooks/scripts/session-start.sh`
- Parse YAML frontmatter using existing patterns
- Log when local overrides are applied (for debugging)
- Document the feature in CLAUDE.md

## Acceptance Criteria

- [x] `.claude/ll.local.md` is loaded when present
- [x] Settings merge correctly with `ll-config.json`
- [x] `.gitignore` template includes `.claude/ll.local.md`
- [x] Documentation updated with usage examples
- [x] SessionStart hook shows when local overrides are active

## Related

- `.claude/settings.local.json` - Similar pattern for Claude Code plugin settings
- `hooks/scripts/session-start.sh` - Where config loading occurs

---

## Verification Notes

**Verified: 2026-01-29**

- Corrected path references: `hooks/session-start/` → `hooks/scripts/session-start.sh`
- Confirmed `.claude/ll-config.json` exists as primary config
- Confirmed `.claude/settings.local.json` pattern exists (gitignored)
- Confirmed `.gitignore` needs `.claude/ll.local.md` added (acceptance criterion)
- Ready for implementation

---

## Status

**Completed** | Created: 2026-01-16 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-29
- **Status**: Completed

### Changes Made
- `hooks/scripts/session-start.sh`: Added Python-based YAML frontmatter parsing and deep merge logic to load and apply local overrides from `.claude/ll.local.md`
- `.gitignore`: Added `.claude/ll.local.md` to gitignore (user-specific, not committed)
- `.claude/CLAUDE.md`: Added "Local Settings Override" documentation section with usage examples and merge behavior

### Verification Results
- Bash syntax: PASS
- Lint: PASS
- Types: PASS
- Manual testing: PASS (local overrides applied correctly, arrays replace, deep merge works)
