---
id: ENH-668
type: ENH
priority: P3
status: active
discovered_date: 2026-03-11
discovered_by: capture-issue
---

# ENH-668: Add `--check` flag to issue prep skills for FSM loop evaluators

## Summary

Add `--check` (check-only, non-interactive) flag to issue prep skills so they can serve as FSM loop evaluators that exit non-zero when work remains.

## Current Behavior

Skills like `/ll:ready-issue`, `/ll:verify-issues`, `/ll:map-dependencies`, `/ll:issue-size-review`, and `/ll:format-issue` have no dry-run or check-only mode. They always perform their full interactive workflow, which makes them unsuitable for use as FSM loop evaluators (the `check:` field in `goal` and `invariants` paradigm states).

## Expected Behavior

Each skill supports a `--check` flag that:
1. Runs all analysis/validation logic
2. Prints a summary of what work remains
3. Exits non-zero if any work remains (issues not ready, unverified claims, unmapped dependencies, oversized issues)
4. Exits zero if all issues pass the gate

This enables use as a shell-based FSM evaluator with `exit_code` routing — the standard pattern for `invariants` paradigm loops.

## Motivation

The `prep-sprint` FSM loop concept (and `invariants` paradigm in general) requires evaluator commands that report pass/fail without side effects. The `/ll:format-issue --auto` precedent already exists — `--check` extends this pattern to the remaining pipeline skills. Without it, the only way to check sprint readiness is to run the full interactive skill, which is incompatible with automated loop execution.

## Proposed Solution

Add a `--check` flag to each affected skill using the existing `--auto` flag as a model:

1. Parse `--check` from skill arguments alongside existing flags (consistent with `--auto` parsing in `format-issue`)
2. In `--check` mode: run analysis only (no writes), print one line per failing issue (`[ID] [gate]: [reason]`), then a summary count (`N issues not ready`)
3. Exit with `exit 1` if count > 0, `exit 0` if all pass — this integrates directly with FSM `exit_code` evaluator routing
4. Skills affected: `ready-issue`, `verify-issues`, `map-dependencies`, `issue-size-review`, `normalize-issues`, `prioritize-issues`; `format-issue --check` acts as dry-run of `--auto`

## Scope Boundaries

- **In scope**: Adding `--check` flag to `ready-issue`, `verify-issues`, `map-dependencies`, `issue-size-review`, `normalize-issues`, `prioritize-issues`, `format-issue`; defining consistent output format and exit codes; updating SKILL.md docs; adding tests for zero/non-zero exit cases
- **Out of scope**: Changes to FSM execution logic or loop YAML format; adding `--check` to non-prep skills (e.g., `commit`, `manage-issue`); building a unified check runner across all skills

## Implementation Steps

1. For each affected skill, add `--check` flag to argument parsing (mirror `--auto` pattern in `format-issue`)
2. Implement check-only execution path: scan active issues, evaluate gate condition, collect failures
3. Print consistent output: one line per failing issue + summary count
4. Exit `1` if failures > 0, `0` if all pass
5. Update each skill's SKILL.md with `--check` flag docs and examples
6. Add tests covering zero and non-zero exit cases for each skill

## Integration Map

### Files to Modify
- `skills/ready-issue/SKILL.md` — add `--check` flag docs
- `skills/verify-issues/SKILL.md` — add `--check` flag docs
- `skills/map-dependencies/SKILL.md` — add `--check` flag docs
- `skills/issue-size-review/SKILL.md` — add `--check` flag docs
- `skills/format-issue/SKILL.md` — `--auto` already exists; add `--check` for dry-run of auto mode
- `skills/normalize-issues/SKILL.md` — add `--check` flag docs
- `skills/prioritize-issues/SKILL.md` — add `--check` flag docs
- `docs/guides/LOOPS_GUIDE.md` — reference `--check` flags in prep-sprint example

### Dependent Files (Callers/Importers)
- FSM loop YAML configs that use `check:` evaluator fields — these will call `--check` skills directly

### Similar Patterns
- `skills/format-issue/SKILL.md` — `--auto` flag is the reference implementation for non-interactive mode
- `skills/format-issue/SKILL.md` — `--dry-run` flag is the existing dry-run pattern to follow

### Tests
- New test cases in each skill's test suite covering `--check` zero and non-zero exit scenarios

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — reference `--check` flags in prep-sprint example

### Configuration
- N/A

## Impact

- **Priority**: P3 — Quality-of-life; unlocks FSM loop automation over sprint prep pipeline
- **Effort**: Medium — 7 skills to update; each follows the same pattern; mostly SKILL.md + flag parsing changes
- **Risk**: Low — check-only mode has no side effects; existing behavior unchanged when `--check` is not passed
- **Breaking Change**: No

## Related Key Documentation

- `docs/guides/LOOPS_GUIDE.md` — FSM loop evaluator patterns

## Labels

`enhancement`, `skills`, `fsm`, `automation`, `ll-loops`

## Related Issues

- ENH-669: Add `--auto`/`--batch` flags to issue prep skills for non-interactive loop actions

## Status

**Active** | P3 | ENH

## Session Log
- `/ll:capture-issue` - 2026-03-11T01:40:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/534f29dc-9078-4565-b6a5-14cb33271b6f.jsonl`
- `/ll:format-issue` - 2026-03-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/644cb258-98f9-4276-9d10-660523431e43.jsonl`

## Blocked By
- FEAT-638
- ENH-671
- FEAT-565
- BUG-656
- ENH-669

## Blocks
- FEAT-543
- ENH-494
- ENH-541
- ENH-542
- ENH-493
