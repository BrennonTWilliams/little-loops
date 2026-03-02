---
type: ENH
id: ENH-521
priority: P5
effort: low
risk: low
---

# INDEX.md completeness gap — unlisted documentation files

## Summary

`docs/INDEX.md` describes itself as "Complete reference for all little-loops documentation" but omits several files, requiring an editorial decision on scope.

## Motivation

Users navigating via the documentation index may miss reference material. Aligning the INDEX with its "complete reference" claim improves discoverability.

## Current Behavior

The following files exist under `docs/` but are not listed in `docs/INDEX.md`:

- `docs/research/LCM-Lossless-Context-Management.md`
- `docs/research/LCM-Integration-Brainstorm.md`
- `docs/claude-code/*.md` (12 files — Claude Code reference documentation)
- `docs/demo/modules.md`, `docs/demo/scenarios.md`

## Expected Behavior

All documentation files under `docs/` should either be listed in `docs/INDEX.md` or the index's scope claim should accurately reflect what it covers. Users should be able to discover all project documentation from a single entry point.

## Proposed Solution

**Add missing entries** to INDEX.md under appropriate sections (e.g., a "Reference Material" or "External Documentation" section for claude-code/ docs)

## Affected Files

- `docs/INDEX.md`

## Scope Boundaries

- Only `docs/INDEX.md` is in scope — no changes to the listed documentation files themselves
- Does not involve writing new documentation content, only updating the index
- Does not require restructuring the `docs/` directory layout

## Implementation Steps

1. Decide which approach to take (editorial decision)
2. Update INDEX.md accordingly

## Impact

- **Priority**: P5 - Documentation completeness, no functional impact
- **Effort**: Low - Single file edit to INDEX.md
- **Risk**: Low - No code changes, only documentation
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `low-effort`

## Source

Discovered by `/ll:audit-docs` on 2026-03-02.

## Resolution

**Resolved** on 2026-03-02.

Added 17 missing entries to `docs/INDEX.md`:
- New "Claude Code Reference" section with all 12 `claude-code/` files
- Added 3 missing `demo/` files (README, modules, scenarios) to Advanced Topics
- Added 2 missing `research/` files (LCM paper and integration brainstorm) to Advanced Topics

All 36 documentation files under `docs/` (excluding INDEX.md itself) are now referenced.

## Status

**Completed** | Created: 2026-03-02 | Resolved: 2026-03-02 | Priority: P5
