# Implementation Plan: FEAT-892 — /ll:update Slash Command

**Date**: 2026-03-26
**Issue**: FEAT-892
**Action**: implement

## Problem Statement

No single command to update all three little-loops surfaces (marketplace listing, Claude Code plugin, pip package). Requires three separate, manual procedures.

## Solution Design

Implement as a **Skill** at `skills/update/SKILL.md` (per CLAUDE.md preference). The skill instructs Claude to:
1. Parse flags (`--marketplace`, `--plugin`, `--package`, `--all`, `--dry-run`)
2. Default to all three if no component flag is given
3. Execute each target step with `[PASS/SKIP/FAIL/DRY-RUN]` reporting
4. Print a summary table at the end

No Python module needed — skill is pure markdown instructions like `init` and `configure`.

## Files to Create/Modify

| File | Action | Notes |
|------|--------|-------|
| `skills/update/SKILL.md` | Create | Main skill definition |
| `commands/help.md` | Edit | Add `/ll:update` entry in SESSION & CONFIG section + Quick Reference Table |
| `.claude-plugin/marketplace.json` | Edit | Sync version `1.66.0` → `1.66.1` (implement `--marketplace` step as part of this issue) |
| `scripts/tests/test_update_skill.py` | Create | TDD tests: skill existence, required flags, marketplace version sync |

## Implementation Phases

### Phase 0: Write Tests (Red) — TDD

Tests in `scripts/tests/test_update_skill.py`:
- `test_skill_file_exists()` — fails until `skills/update/SKILL.md` is created
- `test_skill_has_required_flags()` — fails until flags are in skill content
- `test_marketplace_version_matches_plugin()` — fails because `marketplace.json` is stale

### Phase 1: Create Skill

Skill structure:
1. Parse flags (pattern from `skills/init/SKILL.md:38-57`)
2. Read current versions (plugin.json, marketplace.json, pip)
3. Update Marketplace: Edit `marketplace.json` top-level + `plugins[0].version`
4. Update Plugin: `claude plugin update ll` (from `docs/claude-code/plugins-reference.md:593-609`)
5. Update Package: detect dev vs release install; run `pip install -e './scripts'` or `pip install --upgrade little-loops`
6. Summary report (`[PASS/SKIP/FAIL/DRY-RUN]` per `commands/check-code.md` pattern)

### Phase 2: Update help.md

Add to SESSION & CONFIG section (after toggle-autoprompt):
```
/ll:update [flags]
    Update little-loops components (marketplace listing, plugin, pip package)
    Flags: --marketplace, --plugin, --package, --all, --dry-run
```
Also add `update` to Quick Reference Table session-config line.

### Phase 3: Sync marketplace.json

Update `.claude-plugin/marketplace.json` version fields from `1.66.0` → `1.66.1` to match `plugin.json`.

## Confidence Gate

- **Readiness Score**: 98 — all mechanisms identified, no open questions
- **Outcome Confidence**: 78 — skill is markdown-only; no complex Python to get wrong

## Success Criteria

- [ ] `skills/update/SKILL.md` exists with all 5 flags
- [ ] `commands/help.md` has `/ll:update` entry in SESSION & CONFIG
- [ ] `commands/help.md` Quick Reference Table includes `update`
- [ ] `marketplace.json` version is `1.66.1` on both fields
- [ ] All tests pass
- [ ] Lint and type check pass
