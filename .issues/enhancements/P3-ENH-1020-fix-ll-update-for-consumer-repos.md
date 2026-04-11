---
id: ENH-1020
type: ENH
priority: P3
status: backlog
discovered_date: 2026-04-10
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 64
---

# ENH-1020: Fix /ll:update to properly update little-loops in consumer projects

## Summary

`/ll:update` is designed for the little-loops source repo (version bumping `plugin.json`, updating `marketplace.json`), so when run in consumer projects it skips marketplace and plugin steps entirely and only attempts a package update — poorly. The skill needs to be split: consumer-facing update logic (upgrade pip package, refresh Claude Code plugin) should become the primary behavior, and source-repo-only steps (marketplace/plugin version bumping) should move to a separate internal command.

## Current Behavior

When `/ll:update` runs in a consumer repo:
- Prints "This is a consumer repo — skipping marketplace and plugin steps"
- `MARKETPLACE_RESULT="SKIP"`
- `PLUGIN_RESULT="SKIP"`
- Attempts package update but has a logic bug: detects `./scripts/` directory and assumes it's a dev install, then falls back to `pip install --upgrade little-loops` only after realizing the scripts dir isn't the package source
- Produces a confusing output with two SKIP results and no actionable guidance

## Expected Behavior

When `/ll:update` runs in any repo (consumer or source):
- Upgrades the installed `little-loops` pip package via `pip install --upgrade little-loops`
- Updates the `ll@little-loops` Claude Code plugin via `claude plugin update ll@little-loops`
- Reports current → new version for both
- Source-repo-only steps (bump `plugin.json` version, sync `marketplace.json`) live in a separate command (e.g., `commands/ll-publish.md` or similar) that is only relevant to maintainers

## Motivation

Every end-user of little-loops runs `/ll:update` in their own project, not in the source repo. The current skill is backwards: it optimizes for the maintainer workflow and degrades for the common case. Users see two SKIP lines and no clear path to actually getting updated. Moving source-repo steps out also simplifies the skill considerably and removes the confusing is-source-repo branching logic.

## Proposed Solution

1. **Rewrite `skills/update/SKILL.md`** to target consumer repos as the primary path:
   - Remove the is-source-repo detection guard entirely from the main update flow
   - Step A: `pip install --upgrade little-loops` (always)
   - Step B: `claude plugin update ll@little-loops` (always, same as existing Step 4 logic)
   - Remove Step 3 (marketplace update) and Step 4's plugin.json version check from this skill

2. **Create `commands/ll-publish.md`** (or similar internal command) with the source-repo-only operations:
   - Bump `plugin.json` version
   - Sync `marketplace.json` version
   - This command can guard with `if [ ! -f ".claude-plugin/plugin.json" ]; then echo "Not in little-loops source repo"; exit 1; fi`

3. **Fix the `./scripts/` dev-install detection bug** in the package update step:
   - Presence of `./scripts/` should not be used to infer a dev install — check for `pip show -e` or `pip list --format=json` for editable installs instead

## Scope Boundaries

- **In scope**: Rewriting `skills/update/SKILL.md` to consumer-first flow; creating `commands/ll-publish.md` for source-repo operations; fixing `./scripts/` dev-install detection logic
- **Out of scope**: Changes to other skills or commands beyond `update` and new `ll-publish`; adding new update capabilities (e.g., version pinning, offline mode); modifying the `little_loops` package itself
- **Not addressed**: Multi-version rollback, version history tracking, or selective component update flags

## Integration Map

### Files to Modify
- `skills/update/SKILL.md` — rewrite to consumer-first logic, remove source-repo guards
- `skills/configure/SKILL.md:73-74` — has the **same** `./scripts/` dev-install detection bug (`[ -d "./scripts" ] && INSTALL_CMD="pip install -e './scripts'"`) — fix both in the same PR

### New Files
- `commands/ll-publish.md` (or `commands/ll-release-publish.md`) — extract marketplace + plugin.json version bump logic here

### Dependent Files (Callers/Importers)
- `scripts/tests/test_update_skill.py` — has 3 test classes with structural content assertions that will break when marketplace/plugin.json steps are removed from the skill:
  - `TestUpdateSkillExists` — checks for `--marketplace`, `--plugin`, `plugin.json`, `marketplace.json` strings (will fail after rewrite)
  - `TestUpdateSkillSkipLogic` — checks for `SRC_VERSION`, `PLUGIN_RESULT="SKIP"` (partially affected)
  - `TestMarketplaceVersionSync` — verifies repo-state (plugin.json == marketplace.json version); survives but needs review
- `commands/manage-release.md` — does NOT cross-reference the update skill; its `bump` action (lines 258–270) independently updates `plugin.json`, `marketplace.json`, and `pyproject.toml` via Edit tool — this is the pattern to follow for `ll-publish.md`
- **`commands/ll-update.md` does NOT exist** — no separate command wrapper; skill is invoked directly

### Similar Patterns
- `commands/manage-release.md:258-270` — Edit-tool version bump pattern for `plugin.json`/`marketplace.json`/`pyproject.toml`; model `ll-publish.md`'s version bump logic after this
- `skills/confidence-check/SKILL.md:142-146` — file-existence guard pattern: `if [ ! -f "$FILE" ]; then echo "Error: ..."; exit 1; fi` — use this for the source-repo guard in `ll-publish.md`
- `skills/configure/SKILL.md:73-74` — same `./scripts/` dev-install bug to fix alongside update skill
- `skills/update/SKILL.md:156-158` — `claude plugin list` to detect installed plugin version (keep this in the rewritten skill)

### Tests
- `scripts/tests/test_update_skill.py` — EXISTS with structural content tests (not runtime tests); see Dependent Files above for which test classes will break and need updating after the rewrite

_Wiring pass added by `/ll:wire-issue`:_
**Assertions that will break in `TestUpdateSkillExists`:**
- `test_update_skill.py:34` — `assert "--marketplace" in content` (flag removed from rewritten skill)
- `test_update_skill.py:72` — `assert "plugin.json" in content` (reference moves to `ll-publish.md`)
- `test_update_skill.py:78` — `assert "marketplace.json" in content` (reference moves to `ll-publish.md`)

**Assertions that will break in `TestUpdateSkillSkipLogic`:**
- `test_update_skill.py:103-110` — `"$DO_MARKETPLACE" == true` assertion (`DO_MARKETPLACE` variable removed entirely)
- `test_update_skill.py:126` — `'PLUGIN_RESULT="SKIP (already at $PLUGIN_VERSION)"'` (`PLUGIN_VERSION` variable removed)
- `test_update_skill.py:131-136` — `SRC_VERSION` assertion will break (`SRC_VERSION` is only populated via `./scripts/pyproject.toml` when `./scripts/` exists — removing the dev-install detection removes this variable entirely)
- `test_update_skill.py:148-153` — `PLUGIN_VERSION=$(python3 ...)` with `2>/dev/null` guard (entire variable removed)

**Note on `test_package_step_has_skip_result` (lines 138-144):** This asserts `PACKAGE_RESULT="SKIP (already at $PKG_BEFORE)"`. Whether it survives depends on the implementation approach: if `pip install --upgrade` output is parsed to detect "Requirement already satisfied", a SKIP result can be preserved; if skip logic is removed entirely (always run, report before/after), this test breaks. The implementer should decide and update accordingly.

**`TestMarketplaceVersionSync`** — no changes needed (repo-state check survives)

**New tests to write:**
- Test class for `commands/ll-publish.md` content (follow pattern in `test_update_skill.py:1-17`): assert source-repo guard string (`if [ ! -f ".claude-plugin/plugin.json" ]`), assert `plugin.json` and `marketplace.json` references are present, assert version bump logic exists
- Test assertions for configure skill fix: assert `[ -d "./scripts" ]` is NOT present in `skills/configure/SKILL.md`, assert `pip show little-loops` editable check IS present

### Documentation
- `docs/reference/API.md` — update any mention of `/ll:update` behavior
- `CLAUDE.md` — skill description under "Git & Release" section

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:52-64` — HIGH IMPACT: full `/ll:update` reference block with `--marketplace` flag, three-component framing (`--all` updates all three), and "Default behavior: all three components" description — must be rewritten to reflect consumer-first behavior; `ll-publish` needs a new entry here
- `docs/reference/COMMANDS.md:620-622` — quick-reference table row reads "Update little-loops components (marketplace, plugin, package)" — update to remove "marketplace"
- `commands/help.md:204-206` — user-facing help lists `--marketplace` flag and "marketplace listing" in the description; remove `--marketplace` from flags; add `ll-publish` entry for maintainers
- `README.md:185` — Session & Config command table: flag list includes `--marketplace` and description includes "marketplace" — update both
- `README.md:232` — Skills table description reads "Update little-loops components (marketplace, plugin, package)" — update to reflect consumer-first behavior

### Configuration
- N/A

## Implementation Steps

1. Read full `skills/update/SKILL.md` (285 lines) — trace Steps 1–6 in the file; Steps 3 (marketplace, lines ~100–140) and the `PLUGIN_VERSION="N/A"` guard (lines ~81–87) are the source-repo-only parts to extract
2. Identify consumer path (Steps 4 + 5) vs. source-repo path (Steps 2 version-reading guard + Step 3): consumer path is Steps 4 (`claude plugin update ll@little-loops`) and 5 (`pip install --upgrade little-loops`)
3. Rewrite `skills/update/SKILL.md` — remove Step 3 (marketplace) entirely; remove `PLUGIN_VERSION`/`MARKETPLACE_VERSION` reads from Step 2; remove `DO_MARKETPLACE` flag and related logic; keep Step 4 (plugin) and Step 5 (package)
4. Create `commands/ll-publish.md` — source-repo guard (`if [ ! -f ".claude-plugin/plugin.json" ]; then exit 1; fi`), then bump `pyproject.toml`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (two version fields), `scripts/little_loops/__init__.py` using Edit tool (pattern: `commands/manage-release.md:258-270`)
5. Fix `./scripts/` dev-install detection bug in **both** `skills/update/SKILL.md:197` and `skills/configure/SKILL.md:73-74` — replace `[ -d "./scripts" ]` with `pip show little-loops 2>/dev/null | grep -qE "^Editable project location:"` check
6. Update `scripts/tests/test_update_skill.py` — remove/rewrite `TestUpdateSkillExists` assertions that check for `--marketplace`, `plugin.json`, `marketplace.json` strings; update `TestUpdateSkillSkipLogic` as needed; add test verifying consumer-path strings are present
7. Verify the new update skill works in a consumer test repo (`loop-viz` or similar)
8. Update docs: `docs/reference/COMMANDS.md`, `docs/reference/API.md`, and `CLAUDE.md` skill description under "Git & Release"

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `docs/reference/COMMANDS.md:52-64` — rewrite `/ll:update` section: remove `--marketplace` flag entry, rewrite description from "three components/all" to consumer-first (plugin + package); add new `ll-publish` entry for source-repo publishing operations
10. Update `docs/reference/COMMANDS.md:620-622` — update quick-reference table row for `update`^ to remove "marketplace" from description
11. Update `commands/help.md:204-206` — remove `--marketplace` from flag list and "marketplace listing" from description; add `ll-publish` entry if user-visible
12. Update `README.md:185` — remove `--marketplace` from flag list and update description in Session & Config command table
13. Update `README.md:232` — update Skills table description for `update`^ to reflect consumer-first behavior
14. Update `scripts/tests/test_update_skill.py` — rewrite breaking assertions in `TestUpdateSkillExists` and `TestUpdateSkillSkipLogic`; add new test class for `commands/ll-publish.md` content; add assertions for configure skill dev-install fix

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Actual consumer-repo behavior (corrects issue description):**
- There is **no explicit** "This is a consumer repo — skipping..." message. Consumer detection is implicit: `.claude-plugin/plugin.json` is read with `2>/dev/null || echo "N/A"`, producing `PLUGIN_VERSION="N/A"` and a warn `[WARN] Not in little-loops repo — marketplace/plugin version unavailable` (`skills/update/SKILL.md:85-87`)
- Step 3 (marketplace) silently produces `RESULT="SKIP (already at N/A)"` via a false-positive equality: both `MARKETPLACE_CURRENT` and `PLUGIN_VERSION` are `"N/A"` so the already-synced check passes (`skills/update/SKILL.md:116`)
- Step 4 (plugin update) **actually works in consumer repos**: `claude plugin update ll@little-loops` is a global command, not repo-local. The skip check compares `INSTALLED_PLUGIN_VERSION` (real version string) vs `PLUGIN_VERSION` ("N/A") — they won't match, so the update runs
- The `PLUGIN_RESULT="SKIP"` stated in the issue description is incorrect for the typical case — plugin update runs but reports against an "N/A" target version

**Dev-install detection bug details (`skills/update/SKILL.md:197`):**
```bash
[ -d "./scripts" ] && INSTALL_CMD="pip install -e './scripts'" || INSTALL_CMD="pip install --upgrade little-loops"
```
Any consumer project with a `scripts/` directory at its root triggers `pip install -e './scripts'` — installing whatever is in that directory, not little-loops. **This same bug exists at `skills/configure/SKILL.md:73-74` and must be fixed there too.**

**Recommended dev-install detection replacement:**
```bash
EDITABLE_INSTALL=$(pip show little-loops 2>/dev/null | grep -E "^Editable project location:")
[ -n "$EDITABLE_INSTALL" ] && INSTALL_CMD="pip install -e './scripts'" || INSTALL_CMD="pip install --upgrade little-loops"
```

**`skills/manage-release/SKILL.md` does NOT exist** — manage-release is implemented as `commands/manage-release.md`. It has no cross-reference to the update skill.

**`ll-publish.md` design notes:**
- Guard pattern from `skills/confidence-check/SKILL.md:142-146`: `if [ ! -f ".claude-plugin/plugin.json" ]; then echo "Error: Not in little-loops source repo"; exit 1; fi`
- Version bump via Edit tool (not sed/jq), following `commands/manage-release.md:258-270`; bump `pyproject.toml`, `.claude-plugin/plugin.json`, and `scripts/little_loops/__init__.py` together
- Two fields in marketplace.json to sync: top-level `"version"` and `plugins[0]["version"]`

## Impact

- **Priority**: P3 — Affects all end-users but non-blocking; workaround is running `pip install --upgrade little-loops` manually
- **Effort**: Small — Rewrite one skill file, create one new command file; no shared state to untangle
- **Risk**: Low — Split is clean, no shared state between the two paths; consumer path only improves
- **Breaking Change**: No — Consumer behavior improves; source-repo maintainer steps move to a new explicit command (`ll-publish`), not removed
- **Users affected**: All end-users of little-loops (every consumer project)

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/update/SKILL.md` | Primary file being changed |
| `docs/ARCHITECTURE.md` | Skills vs Commands distinction |
| `.claude/CLAUDE.md` | "Prefer Skills over Agents" guidance |

## Labels

`skill`, `update`, `consumer-ux`, `refactor`

## Status

> backlog

## Session Log
- `/ll:ready-issue` - 2026-04-11T03:19:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b0e24d9-9939-46ca-8a19-b2fd49f87d61.jsonl`
- `/ll:confidence-check` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0673fb54-56ba-4f5c-9ba2-1f9df0dac925.jsonl`
- `/ll:refine-issue` - 2026-04-11T03:11:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b9ac569b-08b5-476c-b76f-c1cdafe537ad.jsonl`
- `/ll:confidence-check` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e220f6b-6c5d-4073-94c2-21ab8f897c3f.jsonl`
- `/ll:wire-issue` - 2026-04-11T03:05:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a587f97e-afd1-46fe-a9ac-dfcf57d1753f.jsonl`
- `/ll:refine-issue` - 2026-04-11T03:00:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee3f2e6b-1489-4333-b99b-09e4300426b6.jsonl`
- `/ll:format-issue` - 2026-04-11T02:55:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8241ead0-8516-4bcd-9c90-27c8f9ac7e7d.jsonl`
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1742fd85-5820-4a26-bdfa-11b23824f386.jsonl`
