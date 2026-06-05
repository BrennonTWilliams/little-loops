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

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-01_

**Verdict: OUTDATED** — Implementation not started:
- No `--pi` flag in `skills/init/SKILL.md`
- No Step 8.5 Pi variant in the init skill
- `hooks/adapters/pi/index.ts` does not exist (depends on FEAT-1478, also unstarted)
- Issue is structurally valid; all scope boundaries are accurate

## Status

**Open** | Created: 2026-05-15 | Priority: P5

## Session Log
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
