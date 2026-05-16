---
discovered_date: 2026-04-01T00:00:00Z
discovered_by: user-report
confidence_score: 100
outcome_confidence: 100
---

# BUG-906: `/ll:update` crashes in user project repos with FileNotFoundError

## Summary

Running `/ll:update` in a project repo that has little-loops installed as a plugin raised `FileNotFoundError: [Errno 2] No such file or directory: '.claude-plugin/plugin.json'`. The skill unconditionally read `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` in Step 2, but those files only exist in the little-loops development repo itself.

## Location

- **File**: `skills/update/SKILL.md` — Step 2 ("Read Current Versions")

## Current Behavior

Step 2 always ran:
```bash
PLUGIN_VERSION=$(python3 -c "import json; d=json.load(open('.claude-plugin/plugin.json')); print(d['version'])")
MARKETPLACE_VERSION=$(python3 -c "import json; d=json.load(open('.claude-plugin/marketplace.json')); print(d['version'])")
```

These paths don't exist in user project repos, causing a crash before any update step ran — even when the user only wanted `--plugin` or `--package`.

## Expected Behavior

`/ll:update --plugin` and `/ll:update --package` should work in any project repo. The `.claude-plugin/` reads are only needed when `--marketplace` is selected.

## Steps to Reproduce

1. Have little-loops installed as a Claude Code plugin in any project
2. Run `/ll:update` (or `/ll:update --plugin`, `/ll:update --package`) in that project
3. Observe `FileNotFoundError` for `.claude-plugin/plugin.json`

## Resolution

In Step 2, gated the `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` reads behind `if [[ "$DO_MARKETPLACE" == true ]]`. The pip package version read remains unconditional. Both variables default to `"N/A"` when the marketplace step is skipped.

## Impact

- **Priority**: P4 - Breaks the skill entirely for all non-little-loops repos
- **Effort**: Trivial — single conditional guard in one file
- **Risk**: None
- **Breaking Change**: No

## Labels

`bug`, `update`, `plugin`

## Status

**Resolved** | Created: 2026-04-01 | Resolved: 2026-04-01 | Priority: P4
