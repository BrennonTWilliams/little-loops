# ENH-905: `/ll:update` skip plugin and package if already current

**Date**: 2026-04-01  
**Issue**: P4-ENH-905  
**File to Modify**: `skills/update/SKILL.md`

## Summary

Add "already current" skip logic to Step 4 (plugin) and Step 5 (package) of `/ll:update`, matching the pattern already used in Step 3 (marketplace). Also fix Step 2 to read `PLUGIN_VERSION` when `$DO_PLUGIN == true` (not only when `$DO_MARKETPLACE == true`).

## Changes

### 1. Step 2 — Extend PLUGIN_VERSION read condition (line ~81)

**Before**: `if [[ "$DO_MARKETPLACE" == true ]]; then`  
**After**: `if [[ "$DO_MARKETPLACE" == true ]] || [[ "$DO_PLUGIN" == true ]]; then`

Rationale: Skip logic in Step 4 needs `$PLUGIN_VERSION` to compare against the installed version. When only `--plugin` is passed, `DO_MARKETPLACE` is false and `PLUGIN_VERSION` stays `"N/A"`.

### 2. Step 4 — Plugin skip logic (after section header, before dry-run check)

After the `echo "PLUGIN UPDATE"` block, add:

```bash
INSTALLED_PLUGIN_VERSION=$(claude plugin list 2>/dev/null | grep -A1 "ll@little-loops" | grep "Version:" | awk '{print $2}')
```

If `$INSTALLED_PLUGIN_VERSION == $PLUGIN_VERSION` (and non-empty):
- Print `[SKIP] Plugin already at $PLUGIN_VERSION`
- Set `PLUGIN_RESULT="SKIP (already at $PLUGIN_VERSION)"`
- Proceed to Step 5 (skip dry-run/update blocks)

If `claude plugin list` fails or returns empty → fall through to update (safe fallback).

### 3. Step 5 — Package skip logic (after PKG_BEFORE read, for dev installs only)

After `PKG_BEFORE` and `INSTALL_CMD` are set, add (only when `[ -d "./scripts" ]` and `DRY_RUN == false`):

```bash
SRC_VERSION=$(python3 -c "import tomllib; d=tomllib.load(open('scripts/pyproject.toml','rb')); print(d['project']['version'])" 2>/dev/null || python3 -c "import re; m=re.search(r'version\s*=\s*\"([^\"]+)\"', open('scripts/pyproject.toml').read()); print(m.group(1) if m else '')" 2>/dev/null || echo "")
```

If `$PKG_BEFORE == $SRC_VERSION` (and `SRC_VERSION` non-empty):
- Print `[SKIP] Package already at $PKG_BEFORE`
- Set `PACKAGE_RESULT="SKIP (already at $PKG_BEFORE)"`
- Proceed to Step 6

For non-dev installs (`pip install --upgrade little-loops`) → always run (no local source to compare).

## Tests (TDD Red → Green)

New test class `TestUpdateSkillSkipLogic` in `scripts/tests/test_update_skill.py`:

1. `test_step2_condition_includes_do_plugin` — checks condition string
2. `test_plugin_step_reads_installed_version` — checks `INSTALLED_PLUGIN_VERSION` + `claude plugin list`
3. `test_plugin_step_has_skip_result` — checks `PLUGIN_RESULT="SKIP (already at $PLUGIN_VERSION)"`
4. `test_package_step_reads_src_version` — checks `SRC_VERSION` + `pyproject.toml`
5. `test_package_step_has_skip_result` — checks `PACKAGE_RESULT="SKIP (already at $PKG_BEFORE)"`

## Success Criteria

- [ ] Step 2 condition reads `PLUGIN_VERSION` when `DO_PLUGIN == true`
- [ ] Step 4 reads installed plugin version and skips if already current
- [ ] Step 5 compares installed vs source version (dev install) and skips if matching
- [ ] Non-dev package installs are unaffected (always run)
- [ ] All new tests pass
- [ ] All existing tests pass
