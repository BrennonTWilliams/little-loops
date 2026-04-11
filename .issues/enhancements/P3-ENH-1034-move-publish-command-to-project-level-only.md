---
discovered_date: 2026-04-11
discovered_by: capture-issue
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
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/91dfec95-ddc4-425f-ab2e-4702ccaf176d.jsonl`

---

## Status

**Open** | Created: 2026-04-11 | Priority: P3
