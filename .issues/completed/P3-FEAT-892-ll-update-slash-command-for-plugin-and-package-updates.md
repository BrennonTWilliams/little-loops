---
id: FEAT-892
type: FEAT
priority: P3
status: open
discovered_date: 2026-03-26
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 78
---

# FEAT-892: /ll:update Slash Command for Plugin and Package Updates

## Summary

Add a new `/ll:update` slash command that provides a single entry point to update all three components of the little-loops ecosystem: the plugin marketplace listing, the little-loops Claude Code plugin itself, and the little-loops pip package. Consolidates update operations currently requiring separate, manual steps.

## Current Behavior

There is no `/ll:update` command. Updating little-loops components requires:
- Manually pulling the latest repo or bumping versions in `plugin.json` / marketplace config
- Reinstalling the pip package with `pip install -e "./scripts[dev]"` or `pip install --upgrade little-loops`
- No single command to check or apply updates across all three surfaces

## Expected Behavior

Running `/ll:update` triggers an interactive or automated update flow that:
- **A) Updates the plugin marketplace listing** — refreshes the marketplace entry (e.g., plugin manifest, version metadata, description) for the little-loops plugin
- **B) Updates the little-loops plugin itself** — pulls the latest version of the plugin (git pull or equivalent) and re-registers it with Claude Code
- **C) Updates the little-loops pip package** — reinstalls/upgrades the `little_loops` Python package from the scripts directory

## Motivation

Developers and plugin authors need a friction-free way to keep all three surfaces in sync when cutting a release or onboarding to a new machine. Currently this requires knowing three separate procedures across git, pip, and the marketplace. A single `/ll:update` command reduces cognitive overhead and reduces the risk of partial updates (e.g., marketplace listing out of sync with installed package version).

## Use Case

A developer has just run `/ll:manage-release` to publish v1.67.0. They now need to ensure the marketplace listing reflects the new version, the plugin in their Claude Code instance is on v1.67.0, and the pip package is upgraded. Instead of running three separate commands in the correct order, they run `/ll:update` and the command handles all three steps — reporting success or failure for each component.

## Acceptance Criteria

- [ ] `/ll:update` is available as a slash command (skill or command) in the little-loops plugin
- [ ] Running `/ll:update` with no arguments updates all three components (A + B + C) in order
- [ ] Running `/ll:update --marketplace` updates only the marketplace listing (A)
- [ ] Running `/ll:update --plugin` updates only the plugin itself (B)
- [ ] Running `/ll:update --package` updates only the pip package (C)
- [ ] Each step reports success/failure independently; partial failures do not abort remaining steps
- [ ] Output shows current version → new version for each updated component
- [ ] Dry-run mode (`--dry-run`) shows what would be updated without applying changes
- [ ] Command is documented in `/ll:help` output

## API/Interface

```
/ll:update [--marketplace] [--plugin] [--package] [--dry-run] [--all]

Flags:
  --marketplace   Update only the plugin marketplace listing
  --plugin        Update only the little-loops Claude Code plugin
  --package       Update only the little-loops pip package
  --all           Update all components (default if no flag given)
  --dry-run       Show what would be updated without making changes
```

## Proposed Solution

Implement as a **Skill** (per CLAUDE.md preference) at `skills/update/SKILL.md`.

The skill should:
1. Detect which components need updating by reading current versions from `plugin.json` (plugin version), `scripts/pyproject.toml` or `setup.cfg` (package version), and marketplace config
2. For each target component, execute the appropriate update mechanism:
   - **Marketplace**: Call `ll-sync` or equivalent to push updated metadata; may involve updating `plugin.json` fields and pushing to the marketplace registry
   - **Plugin**: Run `git pull` or re-register plugin via Claude Code plugin installation mechanism; may call `claude mcp install` or equivalent
   - **Package**: Run `pip install -e "./scripts[dev]"` (dev mode) or `pip install --upgrade little-loops` (release mode)
3. Print a summary table of before/after versions

Consider whether the marketplace update step is a separate CLI operation or an API call to the marketplace registry — this requires clarification on what "marketplace" means in this context.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Marketplace update (A) — clarified:**
- Target file: `.claude-plugin/marketplace.json`
- Mechanism: read `plugin.json:3` for current version, update `marketplace.json:3` (`version`) and `marketplace.json:12` (`plugins[0].version`) to match, then stage and push repo
- No CLI tool exists for this; it is an Edit + git push operation
- `marketplace.json` is currently stale by one patch (`"1.66.0"` vs plugin `"1.66.1"`) — the `--marketplace` step would fix this drift

**Plugin update (B) — mechanism identified:**
- Command: `claude plugin update ll`
- Reference: `docs/claude-code/plugins-reference.md:593-609`
- Alternative reinstall: `claude plugin install ll@little-loops` (`docs/claude-code/plugins-reference.md:500-531`)

**Package update (C) — reusable code identified:**
- Version detection (from `skills/init/SKILL.md:369`): `python3 -c "import importlib.metadata; print(importlib.metadata.version('little-loops'))" 2>/dev/null`
- Dev vs release install (from `skills/init/SKILL.md:375-376`): `[ -d "./scripts" ] && INSTALL_CMD="pip install -e './scripts'" || INSTALL_CMD="pip install --upgrade little-loops"`
- Interactive prompt pattern: `skills/configure/SKILL.md:73-82`
- Auto-mode pattern: `skills/init/SKILL.md:378`

## Integration Map

### Files to Modify
- `skills/update/SKILL.md` — new skill definition (create)
- `.claude-plugin/marketplace.json` — update `version` (line 3) and `plugins[0].version` (line 12) to match `plugin.json` during `--marketplace` step
- `commands/help.md` — hardcoded static content (lines 14–225); must be manually edited to add `/ll:update` entry (not auto-generated)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correction**: `.claude-plugin/plugin.json` does NOT need modification — skills are auto-discovered via `"skills": ["./skills"]` at `.claude-plugin/plugin.json:20`. Creating `skills/update/SKILL.md` is sufficient; no per-skill registration required.
- `.claude-plugin/marketplace.json` is currently stale: version at `"1.66.0"` (lines 3 and 12) while `plugin.json:3` is at `"1.66.1"` — this is a known recurring drift pattern.

### Dependent Files (Callers/Importers)
- `skills/init/SKILL.md:367-389` — implements pip version check and update prompt; directly overlaps with `/ll:update --package` logic; reuse detection and install patterns from here
- `skills/configure/SKILL.md:47-84` — same pip version check pattern; both skills are candidates to eventually delegate to `/ll:update --package` instead of duplicating the logic
- `docs/claude-code/plugins-reference.md:593-609` — documents `claude plugin update <plugin>` — the mechanism for the `--plugin` update step

### Similar Patterns
- `commands/manage-release.md:1-488` — full template: frontmatter pattern, Wave structure, dry-run block format, version file listing, summary report
- `commands/check-code.md:52-195` — per-step pass/fail pattern: each check gated with `[PASS/FIXED/FAIL/SKIP]`, no early exit, summary table at end

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `skills/init/SKILL.md:38-57` — standard multi-flag parse block (`--dry-run`, `--all`, `--auto`, `--dangerously-skip-permissions` auto-enable)
- `skills/init/SKILL.md:369` — pip version detection: `python3 -c "import importlib.metadata; print(importlib.metadata.version('little-loops'))"`
- `skills/init/SKILL.md:375-376` — dev vs release install detection: `[ -d "./scripts" ] && INSTALL_CMD="pip install -e './scripts'" || INSTALL_CMD="pip install --upgrade little-loops"`
- `skills/configure/SKILL.md:73-82` — interactive pip update prompt pattern via `AskUserQuestion`

### Tests
- No existing test file covers skill update flows or pip install calls.
- `scripts/tests/test_subprocess_mocks.py` — use `unittest.mock.MagicMock` pattern here to mock `claude plugin update ll` and `pip install` subprocess calls
- `scripts/tests/test_subprocess_utils.py` — reference for `run_claude_command` wrapper tests (streaming, timeout, output capture patterns)
- `scripts/tests/test_config.py` — `temp_project_dir` fixture pattern for config-loading tests
- Suggested new file: `scripts/tests/test_update_skill.py` — mock subprocess for each of the three update steps; test dry-run produces no side effects; test per-component flags skip the other steps

### Documentation
- `CONTRIBUTING.md` — should reference `/ll:update` for onboarding setup
- `README.md` or marketplace docs — update instructions

### Configuration
- `.claude/ll-config.json` — may add `update.mode` (dev/release) config key

## Implementation Steps

1. ~~Clarify what "marketplace update" means~~ — **Resolved**: target is `.claude-plugin/marketplace.json`; update `version` (line 3) and `plugins[0].version` (line 12) to match `plugin.json:3`
2. Create `skills/update/SKILL.md` using `commands/manage-release.md` frontmatter as template; no `plugin.json` change needed (auto-discovered via `"skills": ["./skills"]` at `.claude-plugin/plugin.json:20`); use multi-flag parse block from `skills/init/SKILL.md:38-57`
3. Implement `--marketplace` step: read `plugin.json:3`, compare with `marketplace.json:3` and `:12`, edit both version fields, stage and push repo
4. Implement `--plugin` step: run `claude plugin update ll` (per `docs/claude-code/plugins-reference.md:593-609`); report success/failure
5. Implement `--package` step: reuse version detection from `skills/init/SKILL.md:369` and install command detection from `skills/init/SKILL.md:375-376`; run `$INSTALL_CMD` and report current → new version
6. Add `--dry-run` and per-component flags using standard parse block from `skills/init/SKILL.md:38-57`; gate each step with `[PASS/SKIP/FAIL]` pattern from `commands/check-code.md:52-195`; print summary table at end
7. Add `/ll:update` entry to `commands/help.md` at line ~187 inside the **SESSION & CONFIG** section (lines 168–188); the section already contains `/ll:init` and `/ll:configure` — insert before the closing line 188
8. Write `scripts/tests/test_update_skill.py`; use `unittest.mock.MagicMock` pattern from `test_subprocess_mocks.py` to mock pip and `claude plugin update ll` subprocess calls; test dry-run, per-component flags, and partial-failure isolation

## Impact

- **Priority**: P3 - Improves developer experience but not blocking any current work
- **Effort**: Medium - Three distinct update mechanisms to implement; marketplace step needs clarification first
- **Risk**: Low - Each step is idempotent and failure-isolated; no destructive operations
- **Breaking Change**: No

## Related Key Documentation

- `docs/claude-code/plugins-reference.md:593-609` — `claude plugin update <plugin>` mechanism used by `--plugin` flag
- `docs/claude-code/plugins-reference.md:500-531` — `claude plugin install` for reinstall fallback
- `docs/claude-code/create-plugin.md` — plugin distribution and marketplace reference
- `CONTRIBUTING.md:29-43` — current pip install instructions; update to reference `/ll:update --package`
- `docs/guides/GETTING_STARTED.md` — onboarding installation steps that `/ll:update` supplements

## Labels

`feature`, `dx`, `cli`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-03-26T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08222264-8c10-483b-8297-c8b24653e187.jsonl`
- `/ll:refine-issue` - 2026-03-26T18:51:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08222264-8c10-483b-8297-c8b24653e187.jsonl`
- `/ll:refine-issue` - 2026-03-26T18:45:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08222264-8c10-483b-8297-c8b24653e187.jsonl`
- `/ll:format-issue` - 2026-03-26T18:36:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08222264-8c10-483b-8297-c8b24653e187.jsonl`

- `/ll:capture-issue` - 2026-03-26T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d4875f47-078b-4e8b-9057-511b4f156510.jsonl`

---

## Status

**Open** | Created: 2026-03-26 | Priority: P3
