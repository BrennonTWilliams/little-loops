---
id: BUG-941
type: BUG
priority: P3
status: open
discovered_date: 2026-04-03
discovered_by: manual
confidence_score: 95
outcome_confidence: 90
---

# BUG-941: `/ll:update` fails outside the little-loops repo root (hardcoded CWD-relative paths)

## Summary

The `update` skill reads `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` using hardcoded CWD-relative paths. When run from any directory other than the little-loops repo root — e.g., a user's own project — it fails with `FileNotFoundError`. `--dry-run` is affected equally since the version-read step runs unconditionally.

## Steps to Reproduce

1. `cd /some/other/project`
2. Run `/ll:update --dry-run` (or `/ll:update`)
3. Result: `FileNotFoundError: [Errno 2] No such file or directory: '.claude-plugin/plugin.json'`

## Root Cause

`skills/update/SKILL.md` lines 82–83 read the plugin manifest with bare relative paths:

```python
python3 -c "import json; d=json.load(open('.claude-plugin/plugin.json')); print(d['version'])"
python3 -c "import json; d=json.load(open('.claude-plugin/marketplace.json')); print(d['version'])"
```

These resolve against `os.getcwd()` at runtime, not against the skill file location or the installed package. They only succeed when the working directory is the little-loops repo root.

## Current Behavior

- `/ll:update --dry-run` fails with `FileNotFoundError` when run outside the repo
- The plugin version check (Step 2 in the skill) is a blocking read — the skill aborts before reaching any conditional logic
- Users in their own projects cannot check for or apply updates

## Expected Behavior

`/ll:update` works from any working directory, resolving plugin manifest paths relative to the installed package location.

## Motivation

Running `/ll:update` from a user's own project — the typical use case — results in an immediate crash with `FileNotFoundError`. Since the update skill is primarily used by non-developer users who do not have the little-loops repo checked out locally, this blocks all users from checking for or applying updates outside the developer environment. The only workaround (`cd` to the repo root) is non-obvious and unavailable to pip-installed users.

## Proposed Solution

Resolve the manifest path using `importlib.resources` (or `importlib.metadata`) against the installed `little_loops` package rather than CWD:

```python
python3 -c "
import importlib.resources, json
base = importlib.resources.files('little_loops')
d = json.loads((base / '.claude-plugin/plugin.json').read_text())
print(d['version'])
"
```

This requires `.claude-plugin/` to be present inside the `little_loops` package directory (`scripts/little_loops/.claude-plugin/`). If that move is undesirable, an alternative is to make the path-read step conditional on `DO_MARKETPLACE or DO_PLUGIN` and guard it with an existence check, degrading gracefully when not in the repo:

```python
python3 -c "
import json, os, sys
p = '.claude-plugin/plugin.json'
if not os.path.exists(p):
    print('N/A')
    sys.exit(0)
d = json.load(open(p))
print(d['version'])
"
```

The graceful-degradation approach is simpler and avoids any directory moves; it means `--marketplace` and `--plugin` steps report `N/A` for the source version when run outside the repo, and the skill can warn rather than crash.

## Integration Map

### Files to Modify
- `skills/update/SKILL.md` — Step 2 version read and Step 3 marketplace version read (CWD-relative `open()` calls)

### Dependent Files (Callers/Importers)
- N/A — SKILL.md files are invoked directly by Claude Code, not imported by other Python modules

### Similar Patterns
- `skills/update/SKILL.md:76` — `PKG_VERSION` already uses `2>/dev/null || echo "not installed"` — exact pattern to apply to line 82
- `skills/update/SKILL.md:83` — `MARKETPLACE_VERSION` already uses `2>/dev/null || echo "N/A"` — confirms line 82 is missing this guard
- `skills/update/SKILL.md:199` — `PKG_BEFORE` uses the same defensive pattern

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Grep of `open('\.` across all `skills/**/*.md` confirms `skills/update/SKILL.md` is the **only** skill with CWD-relative plugin manifest reads — no other skills affected
- `skills/update/SKILL.md:194` and `:206` already use `[ -d "./scripts" ]` directory guards in the same skill (for `pyproject.toml` reads) — `[ -d ".claude-plugin" ]` is the directly analogous guard to add for lines 82/109/110
- `skills/update/SKILL.md:83` already has partial error handling (`2>/dev/null || echo "N/A"`); the **unguarded** lines are 82, 109, and 110
- Line 82 (`PLUGIN_VERSION`) is the blocking read — it lacks `2>/dev/null || echo "N/A"` and is always executed when `DO_MARKETPLACE` or `DO_PLUGIN` is true (the default)
- Lines 109–110 (`MARKETPLACE_CURRENT` and `MARKETPLACE_PLUGIN_ENTRY`) are also unguarded but are only reached if `DO_MARKETPLACE=true`

### Tests
- `scripts/tests/test_update_skill.py` — existing test file (structural content tests); **no test currently covers CWD-relative path failure**
- Add test: verify skill content contains `2>/dev/null || echo "N/A"` guard on the `PLUGIN_VERSION` read (line 82) — follow pattern of `test_step2_condition_includes_do_plugin` at line 101
- Manual smoke test: `cd /tmp && /ll:update --dry-run` should complete without `FileNotFoundError`

### Documentation
- N/A — no documentation changes needed

### Configuration
- N/A — `pyproject.toml` not affected by the graceful-degradation fix

## Implementation Steps

1. Update `skills/update/SKILL.md` Step 2 version reads to guard with `os.path.exists` and print `N/A` on miss
2. Update Step 3 marketplace version reads similarly (lines 109–110)
3. Add a warning line when `PLUGIN_VERSION == "N/A"`: `"[WARN] Not in little-loops repo — marketplace/plugin version unavailable"`
4. Verify `/ll:update --dry-run` runs without error from a non-repo directory

## Impact

- **Priority**: P3 — Breaks the update skill for all non-developer users; developer workaround is simply `cd` to repo root
- **Effort**: Tiny — Two guarded reads + one warning message
- **Risk**: Very low — No logic changes, only defensive path handling

## Related

- BUG-938 (closed/invalid) — Originally misattributed this failure to pip packaging
- `skills/update/SKILL.md` — the only file affected

## Labels

`bug`, `skills`, `update`, `paths`, `ux`

## Status

**Open** | Created: 2026-04-03 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-04-03T22:19:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c218344-c76e-4907-8e91-e34462ce985b.jsonl`
- `/ll:format-issue` - 2026-04-03T22:15:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aa122d32-4468-49e6-9e4b-2982b06af79f.jsonl`
