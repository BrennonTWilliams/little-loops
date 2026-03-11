---
discovered_date: 2026-03-11
discovered_by: capture-issue
---

# ENH-668: Add `--check` flag to issue prep skills for FSM loop evaluators

## Current Behavior

Skills like `/ll:ready-issue`, `/ll:verify-issues`, `/ll:map-dependencies`, `/ll:issue-size-review`, and `/ll:format-issue` have no dry-run or check-only mode. They always perform their full interactive workflow, which makes them unsuitable for use as FSM loop evaluators (the `check:` field in `goal` and `invariants` paradigm states).

## Expected Behavior

Each skill supports a `--check` flag that:
1. Runs all analysis/validation logic
2. Prints a summary of what work remains
3. Exits non-zero if any work remains (issues not ready, unverified claims, unmapped dependencies, oversized issues)
4. Exits zero if all issues pass the gate

This enables use as a shell-based FSM evaluator with `exit_code` routing — the standard pattern for `invariants` paradigm loops.

## Summary

Add `--check` (check-only, non-interactive) flag to issue prep skills so they can serve as FSM loop evaluators that exit non-zero when work remains.

## Motivation

The `prep-sprint` FSM loop concept (and `invariants` paradigm in general) requires evaluator commands that report pass/fail without side effects. The `/ll:format-issue --auto` precedent already exists — `--check` extends this pattern to the remaining pipeline skills. Without it, the only way to check sprint readiness is to run the full interactive skill, which is incompatible with automated loop execution.

## Implementation Steps

1. For each affected skill (`ready-issue`, `verify-issues`, `map-dependencies`, `issue-size-review`, `normalize-issues`, `prioritize-issues`), add a `--check` flag to the skill's argument parsing.
2. In `--check` mode: scan active issues, evaluate the gate condition, print a summary (`N issues not ready`, `N issues unprioritized`, etc.), and `exit 1` if count > 0, `exit 0` if all pass.
3. Define a consistent output format: one line per failing issue ID + reason, followed by a summary count line. This makes the output parseable by `output_contains` or `output_numeric` evaluators as an alternative to `exit_code`.
4. Add `--check` examples to each skill's documentation and SKILL.md.
5. Add tests covering the zero and non-zero exit cases.

## Related Files

- `skills/ready-issue/SKILL.md` — add `--check` flag docs
- `skills/verify-issues/SKILL.md` — add `--check` flag docs
- `skills/map-dependencies/SKILL.md` — add `--check` flag docs
- `skills/issue-size-review/SKILL.md` — add `--check` flag docs
- `skills/format-issue/SKILL.md` — `--auto` already exists; add `--check` for dry-run of auto mode
- `skills/normalize-issues/SKILL.md` — add `--check` flag docs
- `skills/prioritize-issues/SKILL.md` — add `--check` flag docs
- `docs/guides/LOOPS_GUIDE.md` — reference `--check` flags in prep-sprint example

## Related Issues

- ENH-669: Add `--auto`/`--batch` flags to issue prep skills for non-interactive loop actions

---

## Status

**Active** | P3 | ENH

## Session Log
- `/ll:capture-issue` - 2026-03-11T01:40:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/534f29dc-9078-4565-b6a5-14cb33271b6f.jsonl`
