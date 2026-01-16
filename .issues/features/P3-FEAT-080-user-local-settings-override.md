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

- Load `ll.local.md` after `ll-config.json` in the SessionStart hook
- Parse YAML frontmatter using existing patterns
- Log when local overrides are applied (for debugging)
- Document the feature in CLAUDE.md

## Acceptance Criteria

- [ ] `.claude/ll.local.md` is loaded when present
- [ ] Settings merge correctly with `ll-config.json`
- [ ] `.gitignore` template includes `.claude/ll.local.md`
- [ ] Documentation updated with usage examples
- [ ] SessionStart hook shows when local overrides are active

## Related

- `.claude/settings.local.json` - Similar pattern for Claude Code plugin settings
- `hooks/session-start/` - Where config loading occurs
