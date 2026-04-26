---
discovered_commit: 45e21a12570e7811ab10073f24cdaee1695c2e9c
discovered_branch: main
discovered_date: 2026-04-22T00:00:00Z
discovered_by: audit-docs
doc_file: docs/development/TROUBLESHOOTING.md
testable: false
---

# ENH-1261: Review and finalize TROUBLESHOOTING stubs for worktree SIGKILL fixes

## Summary

Documentation issue found by `/ll:audit-docs`.

Two sections in `docs/development/TROUBLESHOOTING.md` were auto-drafted by `/ll:update-docs` and contain `<!-- TODO: update-docs stub -->` markers indicating they need human review before shipping. The content is structurally sound but the TODO markers should be removed after confirming accuracy.

## Location

- **File**: `docs/development/TROUBLESHOOTING.md`
- **Section**: Git Worktree Problems
- **Stubs added**: 2026-04-22 (unstaged, tied to ENH-1246 and ENH-1247/1251/1252/1253)

## Current Content

Both stub sections follow the same structure:

```markdown
<!-- TODO: update-docs stub — ENH-XXXX — drafted 2026-04-22 -->

> **Stub**: This section was auto-drafted by `/ll:update-docs`. Fill in details.

[content]

<!-- END TODO stub -->
```

### Stub 1: "Ghost git worktree refs after SIGKILL"

Covers the scenario where a SIGKILL mid-teardown leaves a ghost metadata entry at `.git/worktrees/<name>/`, causing `fatal: '<path>' already exists` on next `ll-parallel` start. Documents the automatic fix in ENH-1246 (startup scan in orchestrator) and the manual `git worktree prune` fallback.

### Stub 2: "Worktree cleanup fails on locked worktree"

Covers the scenario where `git worktree remove --force` errors on locked worktrees after a SIGKILL. Documents the automatic fix (ENH-1251/1252/1253 — `git worktree unlock` before `git worktree remove --force`) and the manual fallback sequence.

## Current Behavior

The `<!-- TODO: update-docs stub -->` markers are visible in the rendered documentation and signal that content is unreviewed. They should be removed once a human confirms:

1. The symptom/cause descriptions accurately reflect the actual behavior
2. The "How it's handled" sections match the implemented code (ENH-1246, ENH-1247–1253)
3. The manual fix steps are correct and complete

## Expected Behavior

Same content with TODO markers removed after verification.

## Scope Boundaries

- **In scope**: Reviewing the two stub sections in `docs/development/TROUBLESHOOTING.md`, verifying accuracy against implemented code (ENH-1246, ENH-1247–1253), and removing the `<!-- TODO: update-docs stub -->` markers
- **Out of scope**: Rewriting or expanding the stub content; adding new troubleshooting sections; changes to implementation code in ENH-1246–1253

## Impact

- **Severity**: Low (docs are readable; TODO markers are just internal signals)
- **Effort**: Small (read two short sections, verify against code, remove markers)
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `auto-generated`

## Session Log
- `/ll:verify-issues` - 2026-04-26T19:34:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:format-issue` - 2026-04-26T19:23:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2bb55166-f6aa-4bd2-a6a2-b48cd5de603c.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`

---

## Status

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- `docs/development/TROUBLESHOOTING.md:95` — `<!-- TODO: update-docs stub — ENH-1246 -->` marker confirmed ✓
- `docs/development/TROUBLESHOOTING.md:115` — `<!-- TODO: update-docs stub — ENH-1247/1251/1252/1253 -->` marker confirmed ✓
- Both stubs still present; review not yet completed ✓

**Open** | Created: 2026-04-22 | Priority: P4
