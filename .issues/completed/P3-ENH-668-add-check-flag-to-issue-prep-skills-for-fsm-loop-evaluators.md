---
id: ENH-668
type: ENH
priority: P3
status: active
discovered_date: 2026-03-11
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 70
---

# ENH-668: Add `--check` flag to issue prep skills for FSM loop evaluators

## Summary

Add `--check` (check-only, non-interactive) flag to issue prep skills so they can serve as FSM loop evaluators that exit non-zero when work remains.

## Current Behavior

Skills like `/ll:ready-issue`, `/ll:verify-issues`, `/ll:map-dependencies`, `/ll:issue-size-review`, `/ll:confidence-check`, and `/ll:format-issue` have no dry-run or check-only mode. They always perform their full interactive workflow, which makes them unsuitable for use as FSM loop evaluators. For exit-code-based routing, loop YAML states must use `evaluate: type: exit_code` (the actual schema field — there is no `check:` field). Additionally, `/ll:` slash commands are auto-detected as prompt actions by the executor (`executor.py:747` `_is_prompt_action()`), so loop states consuming `--check` output must explicitly declare `evaluate: type: exit_code` to bypass LLM-structured evaluation.

### Current Flag Support Per Skill

| Skill | File | Has `--auto`? | Has `--dry-run`? | Flag var |
|---|---|---|---|---|
| `format-issue` | `skills/format-issue/SKILL.md` | Yes | Yes | `$FLAGS` |
| `verify-issues` | `commands/verify-issues.md` | Yes | No | `$FLAGS` |
| `confidence-check` | `skills/confidence-check/SKILL.md` | Yes | No | `$ARGUMENTS` |
| `issue-size-review` | `skills/issue-size-review/SKILL.md` | Yes | No | `$ARGUMENTS` |
| `map-dependencies` | `skills/map-dependencies/SKILL.md` | Yes | No | `$ARGUMENTS` |
| `prioritize-issues` | `commands/prioritize-issues.md` | Yes (partial) | No | `$FLAGS` (undeclared) |
| `normalize-issues` | `commands/normalize-issues.md` | **No** | **No** | none |
| `ready-issue` | `commands/ready-issue.md` | **No** | **No** | none (has `--deep`) |

**Note**: `normalize-issues` and `ready-issue` require flag parsing to be added from scratch.

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
4. Skills affected: `ready-issue`, `verify-issues`, `map-dependencies`, `issue-size-review`, `normalize-issues`, `prioritize-issues`, `confidence-check`; `format-issue --check` acts as dry-run of `--auto`
5. Each skill's `--check` flag parsing must match its existing flag variable pattern: `$FLAGS` for commands (`ready-issue`, `verify-issues`, `normalize-issues`, `prioritize-issues`), `$ARGUMENTS` for skills (`map-dependencies`, `issue-size-review`, `confidence-check`)

## Scope Boundaries

- **In scope**: Adding `--check` flag to `ready-issue`, `verify-issues`, `map-dependencies`, `issue-size-review`, `normalize-issues`, `prioritize-issues`, `confidence-check`, `format-issue`; defining consistent output format and exit codes; updating SKILL.md/command docs; adding tests for zero/non-zero exit cases
- **Out of scope**: Changes to FSM execution logic or loop YAML format; adding `--check` to non-prep skills (e.g., `commit`, `manage-issue`); building a unified check runner across all skills

## Implementation Steps

1. **Add flag parsing to skills that lack it**: `normalize-issues` (`commands/normalize-issues.md`) and `ready-issue` (`commands/ready-issue.md`) need flag parsing blocks added from scratch, following the `$FLAGS` pattern from `commands/verify-issues.md:33-43`
2. **Add `--check` flag to all 8 affected files**: Parse `--check` alongside existing flags. Use `$FLAGS` for commands, `$ARGUMENTS` for skills (match each file's existing pattern per the table in Current Behavior)
3. **Implement check-only execution path**: Run analysis/validation logic without writes or interactive prompts. Collect failures as a list
4. **Print consistent output**: One line per failing issue (`[ID] [gate]: [reason]`) + summary count (`N issues not ready`). This matches the established auto-mode output format in `issue-size-review` and `map-dependencies`
5. **Exit codes**: `exit 1` if failures > 0, `exit 0` if all pass. This integrates with FSM `evaluate_exit_code()` at `evaluators.py:79-98` (0→success, 1→failure, 2+→error)
6. **Update docs**: Each skill's SKILL.md or command .md with `--check` flag description and examples
7. **Update `docs/guides/LOOPS_GUIDE.md`**: Add prep-sprint example showing `--check` with explicit `evaluate: type: exit_code` block
8. **Add tests**: Cover zero and non-zero exit cases for each skill

## Integration Map

### Files to Modify

**Skills (use `$ARGUMENTS` pattern):**
- `skills/format-issue/SKILL.md` — `--auto`/`--dry-run` already exist; add `--check` as dry-run of auto mode
- `skills/map-dependencies/SKILL.md` — has `--auto`; add `--check` flag parsing and check-only path
- `skills/issue-size-review/SKILL.md` — has `--auto`; add `--check` flag parsing and check-only path
- `skills/confidence-check/SKILL.md` — has `--auto`/`--all`; add `--check` flag parsing and check-only path

**Commands (use `$FLAGS` pattern):**
- `commands/verify-issues.md` — has `--auto`; add `--check` flag parsing and check-only path
- `commands/prioritize-issues.md` — has `--auto` (partial); add `--check` flag and fix flag parsing
- `commands/normalize-issues.md` — **no flag parsing exists**; add full flag block (`--auto`, `--check`) from scratch
- `commands/ready-issue.md` — **no `--auto` flag**; only has `--deep`; add `--check` flag and auto-detection block

**Documentation:**
- `docs/guides/LOOPS_GUIDE.md` — add prep-sprint example using `--check` with `evaluate: type: exit_code`

### Dependent Files (Callers/Importers)
- FSM loop YAML configs that use `evaluate: type: exit_code` — these will consume `--check` skill output
- `scripts/little_loops/fsm/evaluators.py:79-98` — `evaluate_exit_code()` maps exit codes to verdicts (0→success, 1→failure, 2+→error)
- `scripts/little_loops/fsm/executor.py:604` — `_evaluate()` dispatches to exit_code evaluator
- `scripts/little_loops/fsm/executor.py:747` — `_is_prompt_action()` — `/ll:` commands are auto-detected as prompts; loop states must explicitly set `evaluate: type: exit_code`

### Similar Patterns
- `skills/format-issue/SKILL.md:46-75` — `--auto`/`--dry-run` flag parsing reference implementation (`$FLAGS` pattern)
- `skills/confidence-check/SKILL.md:37-67` — `$ARGUMENTS`-style flag parsing with token loop for ID extraction
- `skills/issue-size-review/SKILL.md:128` — auto-mode one-line-per-issue output format: `[ID] decomposed: N child issues`
- `skills/map-dependencies/SKILL.md:142` — auto-mode one-line-per-proposal output: `[ID] → [ID]: dependency added`
- `loops/fix-quality-and-tests.yaml:37-52` — `exit_code` evaluator consuming shell commands (target integration pattern)
- `docs/generalized-fsm-loop.md:257-287` — `compile_invariants()` showing check/fix paradigm structure

### Tests
- New test cases in each skill's test suite covering `--check` zero and non-zero exit scenarios
- Reference patterns: `scripts/tests/test_fsm_evaluators.py:44-66` (exit code mapping tests), `scripts/tests/test_cli_args.py:141-163` (flag argument tests)

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — add prep-sprint example with explicit `evaluate: type: exit_code` blocks

### Configuration
- N/A

## Impact

- **Priority**: P3 — Quality-of-life; unlocks FSM loop automation over sprint prep pipeline
- **Effort**: Medium — 8 skills/commands to update; 6 already have `--auto` flag parsing (add `--check` alongside); 2 (`normalize-issues`, `ready-issue`) need flag parsing blocks added from scratch
- **Risk**: Low — check-only mode has no side effects; existing behavior unchanged when `--check` is not passed
- **Breaking Change**: No

## Related Key Documentation

- `docs/guides/LOOPS_GUIDE.md` — FSM loop evaluator patterns (lines 170-178: evaluator table, lines 234-242: action type table)
- `docs/generalized-fsm-loop.md:257-287` — `compile_invariants()` paradigm compiler showing check/fix state structure
- `docs/generalized-fsm-loop.md:499-512` — `exit_code` evaluator verdicts table

## Labels

`enhancement`, `skills`, `fsm`, `automation`, `ll-loops`

## Related Issues

- ENH-669: Add `--auto`/`--batch` flags to issue prep skills for non-interactive loop actions

## Resolution

- **Action**: implement
- **Date**: 2026-03-12
- **Result**: Added `--check` flag to all 8 issue prep skills/commands
- **Files Changed**:
  - `skills/confidence-check/SKILL.md` — added `CHECK_MODE`, check-mode behavior, examples
  - `skills/issue-size-review/SKILL.md` — added `CHECK_MODE`, check-mode behavior, examples
  - `skills/map-dependencies/SKILL.md` — added `CHECK_MODE`, check-mode behavior, examples
  - `skills/format-issue/SKILL.md` — added `CHECK_MODE` (implies `--auto --dry-run`), check-mode behavior, examples
  - `commands/verify-issues.md` — added `CHECK_MODE`, check-mode behavior, examples
  - `commands/prioritize-issues.md` — added `FLAGS` frontmatter arg, `CHECK_MODE`, check-mode behavior, examples
  - `commands/normalize-issues.md` — added full flag parsing from scratch (`FLAGS`, `AUTO_MODE`, `CHECK_MODE`), check-mode behavior, examples
  - `commands/ready-issue.md` — added full flag parsing (`FLAGS`, `CHECK_MODE`, `DEEP_MODE`), check-mode behavior, examples
  - `docs/guides/LOOPS_GUIDE.md` — added prep-sprint pattern section with complete YAML example

## Status

**Completed** | P3 | ENH

## Session Log
- `/ll:capture-issue` - 2026-03-11T01:40:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/534f29dc-9078-4565-b6a5-14cb33271b6f.jsonl`
- `/ll:format-issue` - 2026-03-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/644cb258-98f9-4276-9d10-660523431e43.jsonl`
- `/ll:refine-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a05aa5fa-4656-46ac-8831-05fd805ad2c0.jsonl`
- `/ll:confidence-check` - 2026-03-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da7809ed-8bca-4fa9-8c31-ca9edfcf4950.jsonl`
- `/ll:ready-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a8f602b-4ea5-429e-8987-fac60f318de7.jsonl`
- `/ll:manage-issue` - 2026-03-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e1936664-5efd-4945-9cf6-1349fc15fb68.jsonl`

## Blocked By

## Blocks
- FEAT-543
- ENH-494
- ENH-541
- ENH-542
- ENH-493
