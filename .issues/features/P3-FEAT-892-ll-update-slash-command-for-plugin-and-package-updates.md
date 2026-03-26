---
id: FEAT-892
type: FEAT
priority: P3
status: open
discovered_date: 2026-03-26
discovered_by: capture-issue
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

## Integration Map

### Files to Modify
- `skills/update/SKILL.md` — new skill definition (create)
- `.claude-plugin/plugin.json` — may need `update` skill registered

### Dependent Files (Callers/Importers)
- TBD — use grep to find any existing update-related scripts

### Similar Patterns
- `skills/manage-release/SKILL.md` — release workflow skill to follow as structural template
- `skills/check-code/SKILL.md` — multi-step quality check pattern (independent steps with individual pass/fail)

### Tests
- TBD — integration test for update flow (may require mocking pip/git calls)

### Documentation
- `CONTRIBUTING.md` — should reference `/ll:update` for onboarding setup
- `README.md` or marketplace docs — update instructions

### Configuration
- `.claude/ll-config.json` — may add `update.mode` (dev/release) config key

## Implementation Steps

1. Clarify what "marketplace update" means — is it updating the Claude Code plugin marketplace listing, or an internal registry? Define the mechanism.
2. Create `skills/update/` directory and `SKILL.md` based on the `manage-release` skill template
3. Implement marketplace update step (depends on Step 1 clarification)
4. Implement plugin update step (git pull + re-registration)
5. Implement pip package update step (`pip install -e "./scripts[dev]"`)
6. Add `--dry-run` and component flags
7. Register skill in `plugin.json` and add to `/ll:help`
8. Write tests for each update step

## Impact

- **Priority**: P3 - Improves developer experience but not blocking any current work
- **Effort**: Medium - Three distinct update mechanisms to implement; marketplace step needs clarification first
- **Risk**: Low - Each step is idempotent and failure-isolated; no destructive operations
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `dx`, `cli`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-03-26T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d4875f47-078b-4e8b-9057-511b4f156510.jsonl`

---

## Status

**Open** | Created: 2026-03-26 | Priority: P3
