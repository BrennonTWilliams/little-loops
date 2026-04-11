---
discovered_date: 2026-04-11
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
---

# ENH-1034: Move publish command to project-level only

## Summary

The `/ll:publish` command handles version bumping and syncing across `plugin.json`, `marketplace.json`, `pyproject.toml`, and `__init__.py` — files that only exist in the little-loops source repo. It ships as part of the plugin itself (`commands/publish.md`), making it visible to all consumer projects where it is meaningless (and where the guard in Step 1 would immediately error). The command should be removed from the distributed plugin and maintained only as a project-level command within this repo.

## Context

**Direct mode**: User description: "Move publish to a project-level command not included in our ll@little-loops plugin"

Surfaced after `/ll:run-tests` revealed `marketplace.json` was out of sync with `plugin.json` — a reminder that `/ll:publish` is a maintenance tool for this repo's maintainers and not a general-purpose command for ll consumers.

## Motivation

- Shipping a source-repo-only command in the plugin clutters the command palette for every consumer project.
- The command's guard (`if [ ! -f ".claude-plugin/plugin.json" ]`) prevents it from doing harm, but the command still appears in `/ll:help` output and completion lists for all users.
- Keeping it in `commands/` implies it's a supported user-facing command, which it is not.

## Proposed Solution

1. Remove `commands/publish.md` from the distributed plugin.
2. Create a project-level command (e.g., `.claude/commands/publish.md` or a local `.ll/commands/publish.md`) that lives only in this repo and is not packaged/shipped.
3. Update `commands/` references in documentation and `CLAUDE.md` to reflect its removal.
4. Ensure the version-sync tests (`test_update_skill.py::TestMarketplaceVersionSync`) still pass and continue to guard against version drift.

## Implementation Steps

1. Move `commands/publish.md` → `.claude/commands/publish.md` (project-local, not shipped).
2. Audit `plugin.json` `commands` list to confirm `publish` is excluded from the packaged manifest.
3. Update `CLAUDE.md` "Commands & Skills" section to remove `publish` from the listed commands or note it as source-repo-only.
4. Update any doc references (e.g., `docs/`, `CONTRIBUTING.md`) that mention `/ll:publish` as a general command.
5. Verify `ll:manage-release` still cross-references the publish step correctly.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 (Move file):**
- Use `git mv commands/publish.md .claude/commands/publish.md` to preserve history.
- `.claude/commands/` already exists and contains `analyze_log.md` — the established pattern for project-local commands. No frontmatter changes are needed; the file format is identical to plugin commands.
- `manage-release` has no runtime dependency on `publish` — the two commands operate independently. The only link is a success-message hint in `commands/publish.md:146` suggesting `/ll:manage-release release $NEW_VERSION --push` as a next step; that hint stays correct after the move.

**Step 2 (No plugin.json edit needed):**
- `.claude-plugin/plugin.json:19` declares `"commands": ["./commands"]` — a directory glob, not an explicit allowlist. Moving `publish.md` out of `commands/` automatically excludes it from the plugin distribution. **No change to `plugin.json` is required.**

**Step 3 (CLAUDE.md is already clean):**
- `publish` does not appear in `.claude/CLAUDE.md`. The "Commands & Skills" section's "Git & Release" group (`commit`, `open-pr`, `describe-pr`, `manage-release`, `sync-issues`, `cleanup-worktrees`) already omits `publish`. **No CLAUDE.md change is needed.**

**Step 4 — Actual doc targets (narrower than stated):**
- `CONTRIBUTING.md` — no publish references; no change needed.
- `docs/ARCHITECTURE.md` — no publish references; no change needed.
- `docs/reference/COMMANDS.md:65-66` — full `### /ll:publish *(maintainers only)*` section. Update to note the command is now project-local (`.claude/commands/publish.md`), not shipped in the plugin.
- `docs/reference/COMMANDS.md:636` — row in the "Git & Release" command table. Update similarly.
- `README.md` — references `/ll:publish` in the command table; update to note maintainer-only / project-local.
- `commands/help.md` — lists `publish` in the help output; remove or annotate.

**Step 5 (manage-release — nothing to fix):**
- `manage-release.md` does not invoke `/ll:publish` at runtime. Its `bump` action at `commands/manage-release.md:258-271` independently edits `pyproject.toml`, `plugin.json`, and `__init__.py` — it does not call `publish`. The only cross-reference is the hint in `publish.md:146` pointing users toward `manage-release` as a next step. That hint is unaffected by the move.

**Critical unlisted step — update test path constant:**
- `scripts/tests/test_update_skill.py:17` declares `PUBLISH_CMD_FILE = PROJECT_ROOT / "commands" / "publish.md"`. After the move this path will not exist, causing `TestPublishCommandExists` (6 structural tests at lines 132–181) to fail immediately.
- **Fix**: Change line 17 to `PUBLISH_CMD_FILE = PROJECT_ROOT / ".claude" / "commands" / "publish.md"`.
- `TestMarketplaceVersionSync` (lines 204–248) does not reference the file path and is unaffected.

## Integration Map

### Files to Modify
- `commands/publish.md` — move to `.claude/commands/publish.md` via `git mv`; no content changes required
- `scripts/tests/test_update_skill.py:17` — update `PUBLISH_CMD_FILE` path from `PROJECT_ROOT / "commands" / "publish.md"` to `PROJECT_ROOT / ".claude" / "commands" / "publish.md"`
- `docs/reference/COMMANDS.md:65-66` — update `### /ll:publish *(maintainers only)*` section to note project-local location
- `docs/reference/COMMANDS.md:636` — update table row in "Git & Release" group
- `README.md` — update `/ll:publish` entry in command table
- `commands/help.md` — remove or annotate publish in help output

### Dependent Files (No Changes Required)
- `.claude-plugin/plugin.json:19` — `"commands": ["./commands"]` directory glob; exclusion is automatic after the move
- `.claude/CLAUDE.md` — publish already absent from the "Git & Release" listing
- `CONTRIBUTING.md` — no publish references
- `docs/ARCHITECTURE.md` — no publish references
- `commands/manage-release.md` — no runtime dependency on publish; the `bump` action at lines 258–271 is independent

### Target Destination (Already Exists)
- `.claude/commands/` — project-local commands directory; contains `analyze_log.md` as the established pattern
- `.claude/commands/publish.md` — destination path (does not yet exist)

### Tests
- `scripts/tests/test_update_skill.py` — `TestPublishCommandExists` (lines 132–181): 6 structural assertions against `PUBLISH_CMD_FILE`; all will fail if path constant is not updated
- `scripts/tests/test_update_skill.py` — `TestMarketplaceVersionSync` (lines 204–248): version drift guards; unaffected by the move (checks file contents, not publish.md path)
- Run: `python -m pytest scripts/tests/test_update_skill.py -v` to verify

### Documentation
- `docs/reference/COMMANDS.md` — primary doc surface with full publish description
- `README.md` — command table reference

## API / Interface Changes

- `/ll:publish` disappears from the plugin's command set for consumer projects.
- Only maintainers working directly in the little-loops source repo will have access via the project-local command.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Lists publish under Commands & Skills |
| architecture | docs/ARCHITECTURE.md | Command packaging and distribution model |

## Labels

`enhancement`, `captured`, `dx`, `plugin-packaging`

---

## Session Log
- `/ll:confidence-check` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fd951d64-2d65-443e-982a-ea4205e199e4.jsonl`
- `/ll:refine-issue` - 2026-04-11T18:08:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/357454b3-7b86-4dcc-8764-fe83bcd065e4.jsonl`
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/91dfec95-ddc4-425f-ab2e-4702ccaf176d.jsonl`

---

## Status

**Open** | Created: 2026-04-11 | Priority: P3
