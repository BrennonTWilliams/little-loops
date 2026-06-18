---
id: FEAT-1475
title: Pi Adapter Init Skill — ll:init --pi Support
type: FEAT
priority: P5
status: open
parent: EPIC-1622
size: Small
depends_on: FEAT-1478
---

# FEAT-1475: Pi Adapter Init Skill — ll:init --pi Support

## Summary

Add `--pi` flag support to the `ll:init` skill so that users running Pi Coding Agent can register the little-loops plugin from the init flow. This is a documentation/instructions-only change to `skills/init/SKILL.md`.

## Parent Issue

Decomposed from FEAT-992: Add Pi Coding Agent Plugin Compatibility

## Acceptance Criteria

- `skills/init/SKILL.md` has a `--pi` flag parsed in the Step 1 argument-parsing block
- Pi Coding Agent presence is auto-detected via `command -v pi` or `[ -d ".pi" ]`
- A Step 8.5 variant copies or symlinks `hooks/adapters/pi/index.ts` into `.pi/extensions/ll-hooks.ts`, creating `.pi/extensions/` if absent
- The skill does not require a `{{LL_PLUGIN_ROOT}}`-substituted template — Pi resolves extensions by directory scan

## Proposed Solution

In `skills/init/SKILL.md`:

1. **Step 1 parse block** — add `--pi` flag parsing alongside existing `--opencode`, `--codex` flags
2. **Auto-detection** — detect Pi via `command -v pi` or existence of `.pi/` directory
3. **Step 8.5 Pi variant** — add a new step that:
   ```bash
   mkdir -p .pi/extensions/
   # Copy or symlink the adapter
   cp hooks/adapters/pi/index.ts .pi/extensions/ll-hooks.ts
   # or: ln -sf "$(ll-plugin-root)/hooks/adapters/pi/index.ts" .pi/extensions/ll-hooks.ts
   ```

### Similar Patterns

- The OpenCode `--opencode` flag handling and Step 8.5-equivalent in `skills/init/SKILL.md` is the direct template to follow.

## Files to Modify

- `skills/init/SKILL.md` — `--pi` flag + Step 8.5 Pi registration variant

## Notes

- The `SKILL.md` text may be drafted while FEAT-1478 is in flight, but the step-8.5 registration is only functional (and this issue is only done) after FEAT-1478 ships the `hooks/adapters/pi/index.ts` file it references. The `depends_on: FEAT-1478` frontmatter is correct; do not merge FEAT-1475 before FEAT-1478 is complete.
- No compilation step needed for Pi — it uses jiti for auto-discovery, so no build pipeline required.
- No trust dialog in Pi — the extension is auto-loaded with full permissions.

## Impact

- **Priority**: P5
- **Effort**: Small
- **Risk**: Very low — documentation/instructions only

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-18): This issue adds a `--pi` flag and Step 8.5 block to `skills/init/SKILL.md`. ENH-494 also modifies the same file — it extracts overflow content from lines 130–201, 505–550, and 554–583 into companion files. If both PRs land concurrently, the line-region deletions in ENH-494 will conflict with the new content FEAT-1475 inserts. Sequence FEAT-1475 after ENH-494 has restructured `init/SKILL.md` so insertions target the post-extraction line layout.

**Update (2026-06-12, epic audit)**: the sequencing warning above is **obsolete** — ENH-494 is done. Note also that ENH-1982 (done 2026-06-12) has since collapsed `skills/init/SKILL.md` to a ~56-line redirect stub over the `ll-init` CLI and deleted `interactive.md`; this issue's planned `--pi` flag and Step 8.5 insertion points no longer exist in that form. Re-scope this issue against the `ll-init` CLI surface (its `--hosts` multi-select already exists — see FEAT-1981) before implementation.

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-01_

**Verdict: OUTDATED** — Implementation not started:
- No `--pi` flag in `skills/init/SKILL.md`
- No Step 8.5 Pi variant in the init skill
- `hooks/adapters/pi/index.ts` does not exist (depends on FEAT-1478, also unstarted)
- Issue is structurally valid; all scope boundaries are accurate

## Status

**Open** | Created: 2026-05-15 | Priority: P5

## Verification Notes (2026-06-13)

- `skills/init/SKILL.md` was collapsed to a redirect stub by ENH-1982 — it no longer contains the `--pi` integration point described in the implementation plan. The issue body's "Step 8.5 into SKILL.md" approach is no longer applicable. Re-scope to target the `ll-init` CLI (`--hosts` multi-select already exists via FEAT-1981). The scope boundary note already flags this but the implementation steps have not been updated.
- 2026-06-13 (OUTDATED): `skills/init/SKILL.md` was collapsed to a redirect stub by ENH-1982 (2026-06-12) and is no longer the correct implementation target. Implementation steps referencing this file need re-scoping to the ll-init CLI surface (scripts/little_loops/init/). Recommend updating implementation plan before starting.
- 2026-06-17: Still NEEDS_UPDATE — `skills/init/SKILL.md` remains a redirect stub; `--pi` flag still absent from ll-init CLI; `hooks/adapters/pi/` does not exist. Implementation Steps must be retargeted to `scripts/little_loops/init/` (`--hosts` multi-select already exists via FEAT-1981) before starting.

## Session Log
- `/ll:verify-issues` - 2026-06-17T00:00:00 - `7473c42a-1313-4587-925f-e177ac5fcc85.jsonl`
- `/ll:verify-issues` - 2026-06-14T00:14:10 - `7db6ce0f-4d7c-486d-927d-6804d39ee7b7.jsonl`
- `/ll:verify-issues` - 2026-06-13T21:13:58 - `cfa3cf65-c671-4bf6-a513-92cc448d76e6.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:54 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-06-01T14:29:19 - `f3a091ba-2869-499e-9de4-7f5c8ca96083.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:10 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:13 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-24T06:05:46 - `8cdfeedd-6a9f-4683-a41d-9ff3860ac7e0.jsonl`
- `/ll:verify-issues` - 2026-05-23T00:35:43 - `2955f8fa-d24c-40f9-9d2d-3d46811662f9.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-18T05:05:17 - `16717e5e-bfe4-4e7f-8d36-177b4b791f2d.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-17T18:46:35 - `ebf7abce-1ef1-46c8-8cbc-56d9f857d730.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `59179ce1-13d5-40c7-bdca-8b3c6117c43e.jsonl`
