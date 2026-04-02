---
discovered_date: 2026-03-31
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
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

## API/Interface

N/A - No public API changes. This enhancement modifies prose instructions in `skills/update/SKILL.md` only; no function signatures or CLI arguments change.

## Integration Map

### Files to Modify
- `skills/update/SKILL.md` — add version comparison logic to Steps 4 and 5

### Dependent Files (Callers/Importers)
- N/A (skill is invoked directly by user)

### Similar Patterns
- Step 3 (Marketplace) already implements this pattern — use it as the model

### Tests
- `scripts/tests/test_update_skill.py` — structural/content tests (verifies skill file exists with required content); no automated tests for skip behavior

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact model to follow** — `skills/update/SKILL.md:108-137` (Step 3 marketplace skip):
```
If $MARKETPLACE_CURRENT == $PLUGIN_VERSION and $MARKETPLACE_PLUGIN_ENTRY == $PLUGIN_VERSION:
  - Print `[SKIP] Marketplace already at $PLUGIN_VERSION`
  - Set MARKETPLACE_RESULT="SKIP (already at $PLUGIN_VERSION)"
  - Proceed to Step 4
```

**`$PLUGIN_VERSION` conditional read — critical gap**: At `skills/update/SKILL.md:79-84`, `PLUGIN_VERSION` is only read when `$DO_MARKETPLACE == true`. Running `/ll:update --plugin` alone leaves `PLUGIN_VERSION="N/A"`. The skip logic for Step 4 requires `$PLUGIN_VERSION` to be available, so Step 2 must also read `plugin.json` when `$DO_PLUGIN == true`.

**Package version sources** — two values exist at runtime:
- `$PKG_BEFORE` at `skills/update/SKILL.md:186` (installed version via `importlib.metadata`)
- Source version at `scripts/pyproject.toml:7` — `version = "1.67.2"` (matches `scripts/little_loops/__init__.py:26`)

**Package skip scope**: Skip only applies to dev-repo installs (where `./scripts` exists and `INSTALL_CMD="pip install -e './scripts'"`). For end-user installs (`pip install --upgrade little-loops`), no local `pyproject.toml` is available to compare against — always run.

**Plugin version introspection — resolved**: `claude plugin list` outputs the installed version in this format:

```
  ❯ ll@little-loops
    Version: 1.67.2
    Scope: user
    Status: ✔ enabled
```

Extraction command:
```bash
INSTALLED_PLUGIN_VERSION=$(claude plugin list 2>/dev/null | grep -A1 "ll@little-loops" | grep "Version:" | awk '{print $2}')
```

`Bash(claude:*)` is already in the skill's `allowed-tools`, so this command is permitted. Compare `$INSTALLED_PLUGIN_VERSION` against `$PLUGIN_VERSION` (from `plugin.json`) — if equal, skip.

## Implementation Steps

1. **Step 2 fix** (`skills/update/SKILL.md:79-84`): Extend the `$PLUGIN_VERSION` read to also trigger when `$DO_PLUGIN == true` — change the condition from `if [[ "$DO_MARKETPLACE" == true ]]` to `if [[ "$DO_MARKETPLACE" == true ]] || [[ "$DO_PLUGIN" == true ]]`
2. **Step 4 plugin skip** (`skills/update/SKILL.md:141-165`): After the section header print, add: read a variable to represent the installed plugin version (method TBD — see note below), compare against `$PLUGIN_VERSION`; if equal, print `[SKIP] Plugin already at $PLUGIN_VERSION`, set `PLUGIN_RESULT="SKIP (already at $PLUGIN_VERSION)"`, and proceed to Step 5. Otherwise continue to dry-run/update logic.
3. **Step 5 package skip** (`skills/update/SKILL.md:169-204`): After `$PKG_BEFORE` is read (line 186) and the `INSTALL_CMD` is detected (line 181), add: if `[ -d "./scripts" ]` (dev repo), read `SRC_VERSION` from `scripts/pyproject.toml:7` via `python3 -c "import tomllib; ..."` or grep; if `$PKG_BEFORE == $SRC_VERSION`, print `[SKIP] Package already at $PKG_BEFORE`, set `PACKAGE_RESULT="SKIP (already at $PKG_BEFORE)"`, and proceed to Step 6. Skip the comparison for non-dev installs (always run).
4. **Summary report** (`skills/update/SKILL.md:222-226`): No changes needed — the status key already documents `SKIP` as "Already up to date, or step not selected".
5. Verify: a no-op run shows `SKIP (already at $VERSION)` for each up-to-date component; a run where a component needs updating still runs correctly.

**Step 4 plugin version introspection — resolved**: Use `claude plugin list` to get the installed version (see Codebase Research Findings above). The concrete implementation for Step 4:

```bash
INSTALLED_PLUGIN_VERSION=$(claude plugin list 2>/dev/null | grep -A1 "ll@little-loops" | grep "Version:" | awk '{print $2}')
if [[ "$INSTALLED_PLUGIN_VERSION" == "$PLUGIN_VERSION" ]]; then
    echo "[SKIP] Plugin already at $PLUGIN_VERSION"
    PLUGIN_RESULT="SKIP (already at $PLUGIN_VERSION)"
    # proceed to Step 5
fi
```

If `claude plugin list` fails or returns empty, fall through to running `claude plugin update` (safe fallback).

## Impact

- **Priority**: P4 - Nice-to-have consistency improvement; no functionality is broken today
- **Effort**: Small - Prose changes to one SKILL.md file following an existing pattern
- **Risk**: Low - Additive logic only; worst case is still running the update command
- **Breaking Change**: No

## Scope Boundaries

- Does not change the `--marketplace` step (already correct)
- Does not add new flags or change the CLI interface
- Does not change behavior when a component IS out of date

## Success Metrics

- **Plugin step**: A no-op run shows `SKIP (already at $VERSION)` instead of executing `claude plugin update`
- **Package step**: A no-op run shows `SKIP (already at $VERSION)` instead of executing the pip install command
- **Summary report**: Reflects `SKIP (already at $VERSION)` rather than `PASS` for already-current components on a no-op run

## Related Key Documentation

| Document | Description | Relevance |
|----------|-------------|-----------|
| `skills/update/SKILL.md` | The update skill being modified | Primary file |

## Labels

`enhancement`, `ll:update`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-04-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55240902-445e-4d6a-95cf-171fcd330636.jsonl`
- `/ll:refine-issue` - 2026-04-02T03:53:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a4f1b01-67b9-4287-b97b-4c053fd50cb7.jsonl`
- `/ll:refine-issue` - 2026-04-02T03:45:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4e287fb1-9497-4145-8422-6b6a7f5b6bba.jsonl`
- `/ll:format-issue` - 2026-04-02T03:20:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b87ef8cd-b696-4139-81a3-d6129ab0c040.jsonl`
- `/ll:verify-issues` - 2026-04-01T17:45:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/712d1434-5c33-48b6-9de5-782d16771df5.jsonl`
- `/ll:capture-issue` - 2026-03-31T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a08a6ef4-ca07-4031-8993-a8bc29361f74.jsonl`

---

**Open** | Created: 2026-03-31 | Priority: P4
