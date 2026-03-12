---
id: ENH-669
type: ENH
priority: P3
status: active
discovered_date: 2026-03-11
discovered_by: capture-issue
confidence_score: 90
outcome_confidence: 78
---

# ENH-669: Add `--auto`/`--batch` flag to issue prep skills for non-interactive loop actions

## Summary

Add `--auto`/`--batch` (non-interactive) flag to issue prep skills so they can serve as FSM loop actions that run without user prompting.

## Current Behavior

Three issue prep skills are interactive and lack `--auto` support:
- `/ll:verify-issues` — asks "Proceed with these changes?" before writing (`commands/verify-issues.md:106`)
- `/ll:map-dependencies` — uses AskUserQuestion to confirm which dependency proposals to apply (`skills/map-dependencies/SKILL.md:120`)
- `/ll:issue-size-review` — uses AskUserQuestion per-issue for decomposition approval (`skills/issue-size-review/SKILL.md:97`)

This makes them unsuitable as FSM loop actions (`using:`, `fix:`, or `steps:` entries), which must run to completion without user prompting.

**Already non-interactive or implemented:**
- `/ll:ready-issue` — already fully non-interactive (no AskUserQuestion calls; auto-corrects and emits structured `## VERDICT`)
- `/ll:refine-issue` — already has `--auto` implemented (`commands/refine-issue.md:44-65`)
- `/ll:format-issue` — reference implementation for `--auto` pattern (`skills/format-issue/SKILL.md:46-75`)

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

Use `/ll:format-issue --auto` as the reference implementation (`skills/format-issue/SKILL.md:46-75`).

### Flag Parsing Pattern

Two patterns exist in the codebase; use **Pattern A** (named `flags` argument) for commands, **Pattern B** (`$ARGUMENTS` token loop) for skills:

**Pattern A** — for `verify-issues` (command in `commands/`):
```bash
FLAGS="${flags:-}"
AUTO_MODE=false
if [[ "$FLAGS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then
    AUTO_MODE=true
fi
if [[ "$FLAGS" == *"--auto"* ]]; then AUTO_MODE=true; fi
```

**Pattern B** — for `map-dependencies`, `issue-size-review` (skills in `skills/`):
```bash
AUTO_MODE=false
if [[ "$ARGUMENTS" == *"--dangerously-skip-permissions"* ]]; then AUTO_MODE=true; fi
if [[ "$ARGUMENTS" == *"--auto"* ]]; then AUTO_MODE=true; fi
for token in $ARGUMENTS; do
    case "$token" in --*) ;; *) ISSUE_ID="$token" ;; esac
done
```
Reference: `skills/confidence-check/SKILL.md:36-46`

### Per-Skill Auto Defaults

1. **`verify-issues --auto`**: Run all checks; write findings to issue files; skip "Proceed with changes?" confirmation at `commands/verify-issues.md:103`
2. **`map-dependencies --auto`**: Write all proposed dependency edges (conservative: only high-confidence); skip AskUserQuestion approval at `skills/map-dependencies/SKILL.md:120`
3. **`issue-size-review --auto`**: Flag oversized issues; auto-decompose only where decomposition is unambiguous; skip per-issue AskUserQuestion at `skills/issue-size-review/SKILL.md:97`

### Output Contract

Emit one status line per issue: `[ID] [action]: [summary]`
Exit non-zero only on hard errors; partial success exits zero with summary.

## Scope Boundaries

- **In scope**: Adding `--auto` flag to `verify-issues`, `map-dependencies`, `issue-size-review`; defining conservative auto-defaults; structured stdout format; SKILL.md/command docs; integration tests
- **Already done**: `refine-issue` (`commands/refine-issue.md:44-65`) and `format-issue` (`skills/format-issue/SKILL.md:46-75`) already have `--auto`
- **Not needed**: `ready-issue` is already fully non-interactive (no AskUserQuestion calls)
- **Out of scope**: Changes to FSM execution or loop YAML format; fully autonomous destructive actions (decomposition is the limit)

## Implementation Steps

1. **`verify-issues`** (`commands/verify-issues.md`): Add `flags` argument to frontmatter; add Pattern A flag parsing; gate the "Proceed with changes?" prompt at line 106 behind `AUTO_MODE`; in auto mode, apply all non-destructive corrections automatically
2. **`map-dependencies`** (`skills/map-dependencies/SKILL.md`): Add Pattern B `$ARGUMENTS` parsing (following `confidence-check/SKILL.md:36-46`); gate the AskUserQuestion at line 120 behind `AUTO_MODE`; in auto mode, apply all proposed dependency edges
3. **`issue-size-review`** (`skills/issue-size-review/SKILL.md`): Add Pattern B `$ARGUMENTS` parsing; gate per-issue AskUserQuestion at line 97 behind `AUTO_MODE`; in auto mode, auto-decompose only unambiguous candidates, skip ambiguous
4. Emit consistent stdout per issue: `[ID] [action]: [summary]`
5. Update each SKILL.md/command with `--auto` flag docs and auto-decision behavior
6. Verify loop YAML compatibility — `loops/issue-refinement.yaml:48-49` already passes `--auto` to `verify-issues`; confirm it works end-to-end

## Integration Map

### Files to Modify
- `commands/verify-issues.md` — add `flags` argument, Pattern A flag parsing, gate interactive prompt at line 106
- `skills/map-dependencies/SKILL.md` — add Pattern B `$ARGUMENTS` parsing, gate AskUserQuestion at line 120
- `skills/issue-size-review/SKILL.md` — add Pattern B `$ARGUMENTS` parsing, gate AskUserQuestion at line 97
- `docs/guides/LOOPS_GUIDE.md` — reference `--auto` flags in prep-sprint example

### Dependent Files (Callers/Importers)
- `loops/issue-refinement.yaml:48-49` — already passes `--auto` to `verify-issues` and `format-issue`
- `.loops/issue-refinement-git.yaml:44-45,75` — already passes `--auto` to these skills

### Similar Patterns (Reference Implementations)
- `skills/format-issue/SKILL.md:46-75` — Pattern A flag parsing, `--auto`/`--all`/`--dry-run`
- `skills/format-issue/SKILL.md:221-265` — auto-mode gates (skip interactive section)
- `skills/confidence-check/SKILL.md:36-46` — Pattern B `$ARGUMENTS` parsing with `--auto`/`--all`
- `skills/confidence-check/SKILL.md:402-411` — auto-mode behavior specification block
- `commands/refine-issue.md:44-65` — Pattern A flag parsing with `--auto`/`--dry-run`
- `skills/review-loop/SKILL.md:307-315` — `--auto` conservative-apply pattern

### Tests
- New integration tests per skill covering `--auto` mode with multi-issue batches (zero and partial-success scenarios)

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — reference `--auto` flags in prep-sprint example

### Configuration
- N/A

## Impact

- **Priority**: P3 — Quality-of-life; unlocks FSM loop automation as pipeline action steps
- **Effort**: Low-Medium — 3 skills to update (reduced from 5); audit + implement non-interactive path per skill; integration tests
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
- `/ll:refine-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10685d70-4d1f-420f-be75-81a4b4fefe36.jsonl`
- `/ll:ready-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4915946-638f-4f1b-8cd6-6502108d230b.jsonl`
- `/ll:confidence-check` - 2026-03-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4915946-638f-4f1b-8cd6-6502108d230b.jsonl`
- `/ll:manage-issue` - 2026-03-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/45358110-356e-4957-9ed5-e2169fe080ed.jsonl`


---

## Resolution

- **Status**: Completed
- **Completed**: 2026-03-12
- **Action**: implement

### Changes Made
- `commands/verify-issues.md`: Added `flags` argument to frontmatter, Pattern A flag parsing (`### 0. Parse Flags`), gated `### 3. Request User Approval` behind `AUTO_MODE`, added `--auto` to Arguments and Examples
- `skills/map-dependencies/SKILL.md`: Added `## Arguments` section with Pattern B `$ARGUMENTS` parsing, gated AskUserQuestion in `## Applying Proposals` behind `AUTO_MODE` (HIGH-confidence only in auto mode), added `--auto` to Examples
- `skills/issue-size-review/SKILL.md`: Added `## Arguments` section with Pattern B `$ARGUMENTS` parsing and issue ID extraction, gated `### Phase 4: User Approval` behind `AUTO_MODE` (Very Large ≥8 only in auto mode), added `--auto` to Examples

### Auto-Mode Conservative Defaults
- **verify-issues**: Apply non-destructive updates; skip moving resolved issues
- **map-dependencies**: Apply HIGH-confidence proposals (≥0.7); skip MEDIUM
- **issue-size-review**: Auto-decompose Very Large (≥8); skip Large (5-7)

## Blocked By
- ~~BUG-656~~ (resolved)
## Blocks
- FEAT-565
- ENH-494
- ENH-493
- ENH-668
