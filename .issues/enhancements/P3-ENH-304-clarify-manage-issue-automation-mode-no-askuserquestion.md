---
discovered_date: 2026-02-09
discovered_by: capture_issue
---

# ENH-304: Clarify manage_issue automation-mode instructions to forbid AskUserQuestion

## Summary

Update `manage_issue.md` command instructions to explicitly forbid use of `AskUserQuestion` when `--gates` is not passed. Currently, the no-gates instructions say to "auto-adapt minor mismatches" but don't explicitly prohibit interactive tools, leaving room for Claude to call `AskUserQuestion` in non-interactive automation contexts.

## Context

Identified from conversation analyzing how `ll-sprint run` handles user approval. The `manage_issue.md` prompt mentions `AskUserQuestion` for mismatch handling (line ~450) and design decisions (line ~182). When running via `ll-sprint`, `ll-auto`, or `ll-parallel`, there is no terminal attached, so `AskUserQuestion` would hang the subprocess.

## Current Behavior

`manage_issue.md` lines 457-466 (no-gates default behavior) instruct Claude to:
- Auto-adapt minor mismatches
- Mark significant mismatches as INCOMPLETE

But lines 450-456 still describe using `AskUserQuestion` with options ("Adapt", "Update plan", "Stop") without clearly scoping this to `--gates` mode only. Claude may interpret these instructions as applicable even without `--gates`.

## Expected Behavior

The no-gates section should include an explicit instruction like:
> "When running without `--gates`, do NOT use `AskUserQuestion` or any interactive tools. All decisions must be made autonomously."

## Current Pain Point

If Claude calls `AskUserQuestion` during non-interactive execution, the subprocess hangs for up to 1 hour (the default timeout). This is a prompt-level fix that can prevent the hang entirely.

## Proposed Solution

1. Add explicit "Do NOT use AskUserQuestion" instruction to the no-gates behavior section
2. Consider adding a general automation-mode note at the top of `manage_issue.md` reminding Claude that in `-p` mode, interactive tools are unavailable
3. Review design decision section (line ~182) to also scope interactive prompts to `--gates` mode

## Scope Boundaries

- Out of scope: Changes to `subprocess_utils.py` or runtime detection (covered by BUG-302 and ENH-303)
- Out of scope: Changes to other commands (only `manage_issue.md`)
- Out of scope: Adding a formal `--automation` flag (just clarify existing instructions)

## Impact

- **Priority**: P3
- **Effort**: Small
- **Risk**: Very low — prompt instruction change only

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Documents manage_issue lifecycle and automation flow |
| architecture | docs/API.md | Documents manage_issue command templates |

## Labels

`enhancement`, `captured`, `automation`, `prompt-engineering`

---

## Status

**Closed - Already Fixed** | Created: 2026-02-09 | Closed: 2026-02-09 | Priority: P3

---

## Resolution

- **Action**: close
- **Closed**: 2026-02-09
- **Status**: Closed - Already Fixed
- **Reason**: All proposed changes were already implemented as part of BUG-302 (commit `f54b32f`)

### Evidence

All three proposed items were addressed in the BUG-302 fix:
1. `manage_issue.md` line 430: Added explicit "Do NOT use AskUserQuestion or any interactive tools" to Default Behavior section
2. `manage_issue.md` line 458: No-gates mismatch handling explicitly forbids AskUserQuestion
3. `manage_issue.md` line 182: Design decisions section scoped to `--gates` flag only
