---
discovered_date: 2026-02-08
discovered_by: manual_review
---

# ENH-278: Split CLAUDE.md behavioral rules into core docs

## Summary

As CLAUDE.md grows, extract behavioral rules and principles into separate files in a `core/` directory within the plugin, following SuperClaude's pattern. CLAUDE.md stays focused on project setup; behavioral instructions load via the plugin system.

## Current Behavior

`.claude/CLAUDE.md` contains project configuration, key directories, commands reference, development instructions, code style rules, and development preferences — all in a single file (~110 lines currently). This is manageable today but will grow as more conventions, rules, and principles are added.

## Expected Behavior

Create a `core/` directory with separated concerns:

- `core/RULES.md` — Development rules, code style, commit conventions, naming patterns
- `core/PRINCIPLES.md` — Engineering philosophy, design preferences (e.g., "prefer skills over agents"), architectural decisions

Keep `.claude/CLAUDE.md` as a lean project overview:
- Project configuration paths
- Key directories
- Development commands (test, lint, format)
- Pointers to core docs for behavioral rules

Ensure core docs are loaded by the plugin system. Test with `/context` to verify they appear in Claude's context.

### Implementation trigger

Only implement when CLAUDE.md exceeds ~200 lines. Currently at ~80 lines, so this is forward-looking. The issue documents the pattern for when it becomes necessary.

## Files to Modify

- `.claude/CLAUDE.md` — Extract behavioral sections, add pointers to core docs
- New `core/RULES.md` — Development rules and conventions
- New `core/PRINCIPLES.md` — Engineering philosophy and design preferences
- Possibly `plugin.json` — If core docs need explicit registration to load

## Impact

- **Priority**: P4
- **Effort**: Low (when triggered)
- **Risk**: Low — reorganization only, no behavioral changes

## Labels

`enhancement`, `documentation`, `architecture`

---

## Status

**Open** | Created: 2026-02-08 | Priority: P4
