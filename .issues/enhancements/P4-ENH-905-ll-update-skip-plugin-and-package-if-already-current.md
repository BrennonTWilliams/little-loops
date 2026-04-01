---
discovered_date: 2026-03-31
discovered_by: capture-issue
---

# ENH-905: `/ll:update` skip plugin and package if already current

## Summary

The `--plugin` and `--package` steps in `/ll:update` always run their update commands regardless of whether the component is already at the latest version. The `--marketplace` step has smart skip logic (compares versions, skips if equal), but the other two steps lack equivalent checks, causing unnecessary command execution on every run.

## Current Behavior

- **Marketplace** (Step 3): Compares `marketplace.json` version against `plugin.json` version — skips with `SKIP (already at $VERSION)` if they match.
- **Plugin** (Step 4): Always runs `claude plugin update ll@little-loops`, even if the installed plugin is already current.
- **Package** (Step 5): Always runs the pip install command, even if the installed package version matches the source.

## Expected Behavior

All three steps should have consistent "already current" skip logic:
- **Plugin**: Check the installed plugin version before running `claude plugin update`; skip with `SKIP (already at $VERSION)` if up to date.
- **Package**: Compare installed pip version against source version (`scripts/pyproject.toml` or `importlib.metadata`); skip if they match.

The summary report should reflect `SKIP (already at $VERSION)` rather than `PASS` for no-op updates.

## Motivation

Running `/ll:update` with no flags is the default "keep everything current" invocation. When all components are already up to date, the command should be a quick no-op with clear confirmation — not silently execute three update commands. This avoids unnecessary pip reinstalls and plugin CLI round-trips during routine checks.

## Proposed Solution

In `skills/update/SKILL.md`:

**Plugin step**: Before running `claude plugin update`, read the currently installed plugin version (e.g., via `claude plugin list` or the installed manifest) and compare against `$PLUGIN_VERSION`. If equal, print `[SKIP] Plugin already at $PLUGIN_VERSION` and set `PLUGIN_RESULT="SKIP (already at $PLUGIN_VERSION)"`.

**Package step**: Before running pip install, compare `$PKG_VERSION` against the version declared in `scripts/pyproject.toml`. If equal, print `[SKIP] Package already at $PKG_VERSION` and set `PACKAGE_RESULT="SKIP (already at $PKG_VERSION)"`.

## Integration Map

### Files to Modify
- `skills/update/SKILL.md` — add version comparison logic to Steps 4 and 5

### Dependent Files (Callers/Importers)
- N/A (skill is invoked directly by user)

### Similar Patterns
- Step 3 (Marketplace) already implements this pattern — use it as the model

### Tests
- N/A (skill is prose instructions, no automated tests)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Extract the installed plugin version before the `claude plugin update` call in Step 4
2. Add version comparison and skip logic matching Step 3's pattern
3. Extract the package version from `scripts/pyproject.toml` (or fallback to `importlib.metadata`) before the pip install in Step 5
4. Add version comparison and skip logic for the package step
5. Verify summary report shows `SKIP (already at $VERSION)` correctly for each skipped step

## Impact

- **Priority**: P4 - Nice-to-have consistency improvement; no functionality is broken today
- **Effort**: Small - Prose changes to one SKILL.md file following an existing pattern
- **Risk**: Low - Additive logic only; worst case is still running the update command
- **Breaking Change**: No

## Scope Boundaries

- Does not change the `--marketplace` step (already correct)
- Does not add new flags or change the CLI interface
- Does not change behavior when a component IS out of date

## Related Key Documentation

| Document | Description | Relevance |
|----------|-------------|-----------|
| `skills/update/SKILL.md` | The update skill being modified | Primary file |

## Labels

`enhancement`, `ll:update`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-04-01T17:45:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/712d1434-5c33-48b6-9de5-782d16771df5.jsonl`
- `/ll:capture-issue` - 2026-03-31T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a08a6ef4-ca07-4031-8993-a8bc29361f74.jsonl`

---

**Open** | Created: 2026-03-31 | Priority: P4
