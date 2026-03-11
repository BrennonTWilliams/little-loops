---
discovered_date: 2026-03-11
discovered_by: capture-issue
---

# ENH-669: Add `--auto`/`--batch` flag to issue prep skills for non-interactive loop actions

## Current Behavior

Skills like `/ll:ready-issue`, `/ll:verify-issues`, `/ll:refine-issue`, `/ll:map-dependencies`, and `/ll:issue-size-review` are interactive: they present findings, ask for user approval on each item, and wait for input before applying changes. This makes them unsuitable as FSM loop actions (`using:`, `fix:`, or `steps:` entries), which must run to completion without user prompting.

The one existing exception is `/ll:format-issue --auto`, which processes all issues non-interactively. This is the pattern to extend.

## Expected Behavior

Each skill supports an `--auto` flag (or `--batch` where more appropriate) that:
1. Runs the full analysis and applies all changes without interactive prompts
2. Uses safe, conservative defaults for any decisions normally requiring user input (e.g., propose but don't apply destructive changes, skip ambiguous cases)
3. Emits structured output suitable for FSM loop logging (issue ID, action taken, result)
4. Exits non-zero only if a hard error occurred; partial success (some issues processed, some skipped) exits zero with a summary

This enables skills to be used directly as `fix:` or `using:` actions in `goal`, `invariants`, and `convergence` FSM loops.

## Summary

Add `--auto`/`--batch` (non-interactive) flag to issue prep skills so they can serve as FSM loop actions that run without user prompting.

## Motivation

The `prep-sprint` FSM loop (and loop-based automation generally) needs skills that can be composed as pipeline steps. Interactive prompting breaks the automation contract — loops must run unattended across iterations. The `/ll:format-issue --auto` pattern proves this is viable; the remaining pipeline skills need the same treatment to unlock `imperative` and `invariants` loops over the sprint prep workflow.

## Implementation Steps

1. Audit each target skill for interactive `AskUserQuestion` calls and decision points that require user input.
2. For each skill, define the `--auto` default behavior:
   - `ready-issue --auto`: process all active issues; auto-correct format/structure issues; skip issues requiring human judgment with a logged warning
   - `verify-issues --auto`: run all checks; flag unverifiable claims but don't block; write findings to issue files
   - `refine-issue --auto`: run codebase research for all unrefined issues; write findings; skip if already refined
   - `map-dependencies --auto`: propose and write new dependency edges with confidence >= threshold; skip ambiguous cases
   - `issue-size-review --auto`: flag oversized issues and auto-decompose where decomposition is unambiguous
3. Add `--auto` flag to each skill's argument parser and implement the non-interactive execution path.
4. Define consistent stdout format: one status line per issue processed (`[ID] [action]: [summary]`).
5. Document `--auto` in each SKILL.md with a note on what decisions are made automatically vs. skipped.
6. Add integration tests for `--auto` mode covering multi-issue batches.

## Related Files

- `skills/ready-issue/SKILL.md` — add `--auto` flag docs
- `skills/verify-issues/SKILL.md` — add `--auto` flag docs
- `skills/refine-issue/SKILL.md` — add `--auto` flag docs
- `skills/map-dependencies/SKILL.md` — add `--auto` flag docs
- `skills/issue-size-review/SKILL.md` — add `--auto` flag docs
- `skills/format-issue/SKILL.md` — reference implementation for `--auto` pattern
- `docs/guides/LOOPS_GUIDE.md` — reference `--auto` flags in prep-sprint example

## Related Issues

- ENH-668: Add `--check` flag to issue prep skills for FSM loop evaluators

---

## Status

**Active** | P3 | ENH

## Session Log
- `/ll:capture-issue` - 2026-03-11T01:40:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/534f29dc-9078-4565-b6a5-14cb33271b6f.jsonl`
