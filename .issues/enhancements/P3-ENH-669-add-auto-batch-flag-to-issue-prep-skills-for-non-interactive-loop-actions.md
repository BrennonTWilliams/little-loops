---
id: ENH-669
type: ENH
priority: P3
status: active
discovered_date: 2026-03-11
discovered_by: capture-issue
---

# ENH-669: Add `--auto`/`--batch` flag to issue prep skills for non-interactive loop actions

## Summary

Add `--auto`/`--batch` (non-interactive) flag to issue prep skills so they can serve as FSM loop actions that run without user prompting.

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

## Motivation

The `prep-sprint` FSM loop (and loop-based automation generally) needs skills that can be composed as pipeline steps. Interactive prompting breaks the automation contract — loops must run unattended across iterations. The `/ll:format-issue --auto` pattern proves this is viable; the remaining pipeline skills need the same treatment to unlock `imperative` and `invariants` loops over the sprint prep workflow.

## Proposed Solution

Use `/ll:format-issue --auto` as the reference implementation:

1. For each skill, audit `AskUserQuestion` calls and identify all interactive decision points
2. Add `--auto` flag to argument parsing (same pattern as `format-issue`)
3. Define conservative auto-defaults per skill:
   - `ready-issue --auto`: process all active issues; auto-correct format/structure; skip issues requiring human judgment with a logged warning
   - `verify-issues --auto`: run all checks; flag unverifiable claims but don't block; write findings to issue files
   - `refine-issue --auto`: run codebase research for all unrefined issues; write findings; skip if already refined
   - `map-dependencies --auto`: propose and write new dependency edges with confidence >= threshold; skip ambiguous cases
   - `issue-size-review --auto`: flag oversized issues; auto-decompose only where decomposition is unambiguous
4. Emit one status line per issue: `[ID] [action]: [summary]`
5. Exit non-zero only on hard errors; partial success exits zero with summary

## Scope Boundaries

- **In scope**: Adding `--auto` flag to `ready-issue`, `verify-issues`, `refine-issue`, `map-dependencies`, `issue-size-review`; defining conservative auto-defaults; structured stdout format; SKILL.md docs; integration tests for multi-issue batches
- **Out of scope**: Adding `--auto` to skills that are already non-interactive (e.g., `commit`, `manage-issue`); changes to FSM execution or loop YAML format; fully autonomous destructive actions (decomposition is the limit)

## Implementation Steps

1. Audit each target skill for interactive `AskUserQuestion` calls and decision points
2. Define `--auto` default behavior per skill (see Proposed Solution)
3. Add `--auto` flag to each skill's argument parser; implement non-interactive path
4. Emit consistent stdout: `[ID] [action]: [summary]` per issue
5. Update each SKILL.md with `--auto` flag docs and a note on auto-decisions vs. skipped
6. Add integration tests for `--auto` mode covering multi-issue batches

## Integration Map

### Files to Modify
- `skills/ready-issue/SKILL.md` — add `--auto` flag docs
- `skills/verify-issues/SKILL.md` — add `--auto` flag docs
- `skills/refine-issue/SKILL.md` — add `--auto` flag docs
- `skills/map-dependencies/SKILL.md` — add `--auto` flag docs
- `skills/issue-size-review/SKILL.md` — add `--auto` flag docs
- `skills/format-issue/SKILL.md` — reference implementation for `--auto` pattern
- `docs/guides/LOOPS_GUIDE.md` — reference `--auto` flags in prep-sprint example

### Dependent Files (Callers/Importers)
- FSM loop YAML configs that use `fix:` or `using:` action fields — these will call skills with `--auto`

### Similar Patterns
- `skills/format-issue/SKILL.md` — `--auto` flag is the reference implementation; `--all` is the batch mode pattern

### Tests
- New integration tests per skill covering `--auto` mode with multi-issue batches (zero and partial-success scenarios)

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — reference `--auto` flags in prep-sprint example

### Configuration
- N/A

## Impact

- **Priority**: P3 — Quality-of-life; unlocks FSM loop automation as pipeline action steps
- **Effort**: Medium — 5 skills to update; audit + implement non-interactive path per skill; integration tests
- **Risk**: Low — `--auto` path is additive; conservative defaults prevent destructive auto-actions; existing interactive behavior unchanged
- **Breaking Change**: No

## Related Key Documentation

- `docs/guides/LOOPS_GUIDE.md` — FSM loop action patterns
- `skills/format-issue/SKILL.md` — reference `--auto` implementation

## Labels

`enhancement`, `skills`, `fsm`, `automation`, `ll-loops`

## Related Issues

- ENH-668: Add `--check` flag to issue prep skills for FSM loop evaluators

## Status

**Active** | P3 | ENH

## Session Log
- `/ll:capture-issue` - 2026-03-11T01:40:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/534f29dc-9078-4565-b6a5-14cb33271b6f.jsonl`
- `/ll:format-issue` - 2026-03-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/644cb258-98f9-4276-9d10-660523431e43.jsonl`
