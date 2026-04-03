---
id: BUG-938
type: BUG
priority: P2
status: invalid
discovered_date: 2026-04-03
discovered_by: capture-issue
closed_date: 2026-04-03
closed_by: manual
confidence_score: 95
outcome_confidence: 90
---

# BUG-938: Plugin assets missing from pip wheel (skills/, commands/, agents/, hooks/, .claude-plugin/)

## Summary

After `pip install little-loops` (non-editable), the Claude Code plugin assets are not installed. Users get the Python CLI tools but `skills/`, `commands/`, `agents/`, `hooks/`, and `.claude-plugin/plugin.json` are all absent from site-packages. The `ll@little-loops` plugin cannot function after a standard pip install.

Specifically reported missing: `.claude-plugin/plugin.json` (the manifest Claude Code uses to discover skills) and the root-level `skills/` directory (all 21 skills including `confidence-check`).

## Steps to Reproduce

1. `pip install little-loops` (non-editable, e.g. from PyPI or `pip install ./scripts`)
2. Inspect installed package: `ls $(pip show little-loops | grep Location | awk '{print $2}')/little_loops/`
3. Result: no `skills/`, no `commands/`, no `agents/`, no `hooks/`, no `.claude-plugin/`

## Root Cause

Exact repeat of BUG-885 (`loops/` missing after pip install). `scripts/pyproject.toml` packages the wheel with:

```toml
[tool.hatch.build.targets.wheel]
packages = ["little_loops"]
include = ["little_loops/**", "LICENSE"]
```

All plugin assets live at the repo root, **outside** `scripts/little_loops/`:

```
.claude-plugin/   ← not in wheel
skills/           ← not in wheel
commands/         ← not in wheel
agents/           ← not in wheel
hooks/            ← not in wheel
scripts/
  little_loops/   ← packaged ✓
  pyproject.toml
```

Only `scripts/little_loops/**` is bundled. Editable installs (`pip install -e ./scripts`) are unaffected because `__file__` still points to the source tree.

## Current Behavior

- `claude plugin install ll@little-loops` or `claude plugin update ll@little-loops` may succeed, but skill definitions are absent from the installed package
- `ll-loop list` works (BUG-885 fixed `loops/`)
- All `/ll:*` skills silently unavailable to users who pip-install on a fresh machine
- `/ll:update --dry-run` fails with `FileNotFoundError` reading `.claude-plugin/plugin.json`

## Expected Behavior

After `pip install little-loops`, all plugin assets are present inside `site-packages/little_loops/` and the `ll@little-loops` plugin loads correctly.

## Proposed Solution

Move all plugin assets into `scripts/little_loops/` so they are automatically bundled by `packages = ["little_loops"]`. No `pyproject.toml` changes needed. This mirrors the BUG-885 fix exactly.

### Directories to move (via `git mv`)

```
skills/           → scripts/little_loops/skills/
commands/         → scripts/little_loops/commands/
agents/           → scripts/little_loops/agents/
hooks/            → scripts/little_loops/hooks/
.claude-plugin/   → scripts/little_loops/.claude-plugin/
```

### plugin.json path updates

`scripts/little_loops/.claude-plugin/plugin.json` is now one level deeper inside the package. All relative paths must go up one level:

- `"./commands"` → `"../commands"`
- `"./skills"` → `"../skills"`
- `"./agents/foo.md"` → `"../agents/foo.md"` (all 8 agent paths)

### Path references to update

- **`skills/update/SKILL.md`** (lines 82–83, 109–110, 127): `.claude-plugin/plugin.json` → `scripts/little_loops/.claude-plugin/plugin.json`; same for `marketplace.json`; update `git add` path
- **`commands/manage-release.md`**: all `.claude-plugin/plugin.json` references → `scripts/little_loops/.claude-plugin/plugin.json`
- **`CLAUDE.md`** Key Directories section: update paths for `commands/`, `agents/`, `skills/`, `hooks/`

## Integration Map

### Files to Modify
- `scripts/little_loops/.claude-plugin/plugin.json` — update 9 relative paths (`./X` → `../X`)
- `scripts/little_loops/skills/update/SKILL.md` — update 4 path references to `.claude-plugin/`
- `scripts/little_loops/commands/manage-release.md` — update `.claude-plugin/` path references
- `CLAUDE.md` — update Key Directories section

### Directories to Move
- `skills/` → `scripts/little_loops/skills/`
- `commands/` → `scripts/little_loops/commands/`
- `agents/` → `scripts/little_loops/agents/`
- `hooks/` → `scripts/little_loops/hooks/`
- `.claude-plugin/` → `scripts/little_loops/.claude-plugin/`

### No Changes Needed
- `scripts/pyproject.toml` — `packages = ["little_loops"]` already covers `scripts/little_loops/**`

### Similar Patterns
- `scripts/little_loops/cli/loop/_helpers.py:get_builtin_loops_dir()` — BUG-885 fix; same directory-move pattern

## Implementation Steps

1. `git mv` all five directories into `scripts/little_loops/`
2. Update relative paths in `plugin.json`
3. Update `.claude-plugin/` path references in `update` skill and `manage-release` command
4. Update `CLAUDE.md` Key Directories section
5. Run `python -m build ./scripts` and verify `unzip -l dist/*.whl | grep -E "skills/|\.claude-plugin/"` shows the assets
6. Test non-editable install in a venv: confirm `site-packages/little_loops/skills/` exists
7. Run full test suite: `python -m pytest scripts/tests/`

## Impact

- **Priority**: P2 — Affects all non-editable installs; silently breaks the entire Claude Code plugin for fresh installs
- **Effort**: Small — Mechanical directory move + path string updates; no logic changes
- **Risk**: Low — Additive packaging change; editable installs unaffected
- **Breaking Change**: No — Install path changes are internal to the package

## Related

- BUG-885: Built-in loops missing after pip install (completed) — identical fix pattern
- `.claude-plugin/plugin.json` — plugin manifest
- `scripts/pyproject.toml` lines 80–82 — wheel build configuration

## Resolution

**Closed as invalid** — The issue conflates two independent distribution mechanisms.

`pip install little-loops` delivers only the Python CLI tools (`ll-auto`, `ll-loop`, etc.) and is not expected to include plugin assets. Plugin assets (`skills/`, `commands/`, `agents/`, etc.) are distributed via `claude plugin install ll@little-loops`, which pulls from the GitHub repository root per `marketplace.json` (`"source": "./"`) — exactly where these assets live. No packaging change is needed.

The `/ll:update --dry-run` failure noted in Current Behavior is a real but separate bug: the update skill reads `.claude-plugin/plugin.json` via a hardcoded CWD-relative path, which fails when run outside the little-loops repo root. Tracked in BUG-941.

## Labels

`bug`, `packaging`, `install`, `skills`, `plugin`, `invalid`
