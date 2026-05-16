---
id: BUG-1071
type: bug
priority: P2
discovered_date: 2026-04-12
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
---

# BUG-1071: update skill uses relative ./scripts path when run outside little-loops repo

## Summary

When `/ll:update` is run from any project other than the little-loops repo itself, the package-update step fails with a hard error. The editable-install branch hardcodes `pip install -e './scripts'` using a relative path — since the CWD is the target project, `./scripts` doesn't point to a valid Python project. The fix is to extract the absolute path already returned by `pip show little-loops`.

## Current Behavior

Running `/ll:update` from a project other than `~/AIProjects/brenentech/little-loops` produces:

```
ERROR: file:///path/to/target-project/scripts does not appear to be a Python project
```

because `pip install -e './scripts'` resolves `./scripts` relative to the caller's working directory, not the little-loops source tree.

## Expected Behavior

`/ll:update` detects the absolute path of the editable install from `pip show little-loops` and runs `pip install -e '/absolute/path/to/little-loops/scripts'`, succeeding regardless of the caller's working directory.

## Motivation

`/ll:update` is intended to be run from any project. A relative-path assumption breaks the primary use case (running update from a client project) and causes a confusing, hard-to-diagnose failure. Users who installed little-loops in editable mode (the developer workflow) are entirely blocked from updating via the skill.

## Root Cause

- **File**: `skills/update/SKILL.md`
- **Line(s)**: 124–126
- **Anchor**: editable-install detection block
- **Cause**: The two-liner sets `INSTALL_CMD="pip install -e './scripts'"` unconditionally when an editable install is detected, ignoring the absolute path already present in the `pip show` output.

## Location

- **File**: `skills/update/SKILL.md`
- **Line(s)**: 124–126
- **Code**:
```bash
EDITABLE_INSTALL=$(pip show little-loops 2>/dev/null | grep -E "^Editable project location:")
[ -n "$EDITABLE_INSTALL" ] && INSTALL_CMD="pip install -e './scripts'" || INSTALL_CMD="pip install --upgrade little-loops"
```

## Steps to Reproduce

1. Install little-loops in editable mode from `~/AIProjects/brenentech/little-loops`
2. Open a different project (e.g. `~/AIProjects/ai-workspaces/ll-labs/loop-viz`)
3. Run `/ll:update`
4. Observe: `ERROR: file:///path/to/loop-viz/scripts does not appear to be a Python project`

## Proposed Solution

Replace the two-line block with a block that extracts the absolute path from `pip show` output:

```bash
EDITABLE_INSTALL=$(pip show little-loops 2>/dev/null | grep -E "^Editable project location:")
if [ -n "$EDITABLE_INSTALL" ]; then
    EDITABLE_PATH=$(echo "$EDITABLE_INSTALL" | sed 's/^Editable project location: //')
    INSTALL_CMD="pip install -e '$EDITABLE_PATH'"
else
    INSTALL_CMD="pip install --upgrade little-loops"
fi
```

`pip show little-loops` already outputs the absolute path (e.g. `/Users/brennon/AIProjects/brenentech/little-loops/scripts`). Strip the label prefix and use it directly.

## Integration Map

### Files to Modify
- `skills/update/SKILL.md:124–125` — editable-install detection block (primary bug location)
- `skills/configure/SKILL.md:74–75` — identical two-line pattern with the same bug (confirmed by codebase research)
- `skills/init/SKILL.md:381` — same `[ -d "./scripts" ] && INSTALL_CMD="pip install -e './scripts'"` pattern; lower urgency since `/ll:init` is typically run from the ll repo, but shares the vulnerability _(wiring pass added by `/ll:wire-issue`:)_

### Dependent Files (Callers/Importers)
- No Python callers; this is shell script embedded in the skill markdown

### Similar Patterns
- `skills/init/SKILL.md:381` — older variant using `[ -d "./scripts" ]` for detection (different context: init is typically run from the ll repo, lower urgency)
- `hooks/scripts/*.sh:13-14` — established pattern for CWD-independent path resolution: `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`
- `skills/update/SKILL.md:192-199` — same file already uses absolute path from plugin registry (`installPath`) correctly

### Tests
- `scripts/tests/test_update_skill.py` — existing test file; extend `TestUpdateSkillConsumerPath` with a new assertion: `assert "pip install -e './scripts'" not in content` (catches the absolute-path regression)
- Also extend `TestConfigureSkillDevInstallFix` with the same assertion for `configure/SKILL.md`
- Existing tests at lines 114–130 (update skill) and 197–211 (configure skill) already verify editable detection is present but do NOT verify the relative path is gone from `INSTALL_CMD`
- Manual smoke-test: run `/ll:update` from a client project with editable install active

### Documentation
- N/A - no documentation updates required; `skills/update/SKILL.md` is self-documenting

### Configuration
- N/A - no configuration file changes required

## Implementation Steps

1. Open `skills/update/SKILL.md`, locate lines 124–125 (the two-line editable-install block), replace with the `if/fi` block from Proposed Solution
2. Open `skills/configure/SKILL.md`, locate lines 74–75 (identical two-line pattern), apply the same `if/fi` replacement
3. In `scripts/tests/test_update_skill.py`, add to `TestUpdateSkillConsumerPath` (after line 130): `assert "pip install -e './scripts'" not in content`
4. In `scripts/tests/test_update_skill.py`, add to `TestConfigureSkillDevInstallFix` (after line 211): same assertion for `CONFIGURE_SKILL_FILE`
5. Run `python -m pytest scripts/tests/test_update_skill.py -v` to confirm all assertions pass
6. Manual smoke-test: run `/ll:update` from a client project with editable install active; verify dry-run shows absolute path

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis:_

7. (Optional) Fix `skills/init/SKILL.md:381` — apply the same `if/fi` absolute-path extraction; same vulnerability, lower urgency. If included, add a corresponding `TestInitSkillDevInstall` class in `scripts/tests/test_update_skill.py` with the same two assertions (no `[ -d "./scripts" ]`, `pip install -e './scripts'` absent).

## Impact

- **Priority**: P2 - Breaks `/ll:update` for all users running from client projects with editable install
- **Effort**: Small - Single 5-line change in one file
- **Risk**: Low - Only changes how the install path is derived; logic is otherwise identical
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `skills`, `update`, `path-resolution`, `captured`

## Resolution

**Fixed** | Resolved: 2026-04-12 | Priority: P2

### Changes Made

- `skills/update/SKILL.md:124–128` — Replaced one-liner with `if/fi` block that extracts the absolute path from `pip show little-loops` output via `sed`, then uses it in `INSTALL_CMD`
- `skills/configure/SKILL.md:74–81` — Same `if/fi` fix applied to the identical editable-install detection block
- `scripts/tests/test_update_skill.py` — Added `test_package_step_does_not_use_relative_scripts_path` to `TestUpdateSkillConsumerPath` and `test_configure_skill_does_not_use_relative_scripts_path` to `TestConfigureSkillDevInstallFix` as regression guards

### Verification

- `python -m pytest scripts/tests/test_update_skill.py -v` — 27 passed (2 pre-existing `TestMarketplaceVersionSync` failures, unrelated)
- Both new regression tests confirm relative path is absent from both skill files

---

## Session Log
- `/ll:ready-issue` - 2026-04-13T01:52:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9505b531-2954-46c0-b8ad-4121d25162a3.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a11f70cd-766c-4f45-b29e-1c8bed62643d.jsonl`
- `/ll:wire-issue` - 2026-04-12T20:41:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c305cac4-c25e-482f-86f7-9adf26df1b0e.jsonl`
- `/ll:refine-issue` - 2026-04-12T20:38:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d44c09c2-55d3-4e29-ae39-b193249296cd.jsonl`
- `/ll:format-issue` - 2026-04-12T20:34:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d54c0e6-ea63-4ad6-9f8e-a2b042846215.jsonl`
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7c42196c-bf0e-4df5-b271-139f23c7c2c3.jsonl`
- `/ll:manage-issue bug fix` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
