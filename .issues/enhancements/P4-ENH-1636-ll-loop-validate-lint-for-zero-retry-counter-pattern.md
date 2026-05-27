---
id: ENH-1636
type: ENH
priority: P4
status: open
captured_at: 2026-05-23T12:00:00Z
discovered_date: 2026-05-23
discovered_by: capture-issue
parent: EPIC-1663
---

# ENH-1636: `ll-loop validate` lint for zero-retry counter pattern

## Summary

A common loop-authoring footgun: a state that increments a `printf > file` counter and then evaluates `output_numeric` with `operator: lt, target: 1` against itself. After the first increment the counter is `1`, `1 < 1 == false`, so `on_no` fires — i.e. the "retry" budget is 0 by construction. Author almost always intended `target: 2` or `target: 3`. The little-loops static validator does not catch this.

## Motivation

- Observed in `harness-exploratory-user-eval` YAML (lines 787–804 of that loop), where `check_semantic_retry_count` had `target: 1` and never actually allowed a retry.
- This exact pattern is going to show up again in user-written loops — it's a single off-by-one between intent ("up to N retries") and the literal arithmetic.
- A focused lint is cheap and pays for itself the first time a loop author saves debugging time.

## Current Behavior

`ll-loop validate` accepts any `output_numeric` evaluator that parses, regardless of whether the threshold against an obvious-counter pattern yields zero usable iterations.

## Expected Behavior

`ll-loop validate` (or a new `ll-loop lint` subcommand) emits a warning when:

1. A state's action writes to a file via `printf NNN > path` where `NNN` is `${VAR}+1` or similar increment, AND
2. The same state evaluates `output_numeric` reading that file, AND
3. The threshold `target:` value, combined with `operator:`, yields zero successful retries given the counter increments from 0 by 1.

Warning message should suggest the likely intended `target:` value.

## Proposed Solution

Add a lint pass in `scripts/little_loops/cli/loop/_helpers.py` (or a dedicated `lints/` module) that walks loaded loop YAML, identifies counter-pattern states, and raises a `LintWarning` on the pattern above. Wire into the existing `ll-loop validate` output (or expose via `ll-loop lint`).

## Implementation Steps

1. Define a `CounterStateLint` heuristic that matches the action+evaluator pair.
2. Compute the effective retry budget given `operator`/`target`.
3. Emit a warning with the suggested fix when budget == 0.
4. Add unit tests covering: `lt target=1` (warn), `lt target=2` (no warn), `lte target=0` (warn), non-counter actions (no warn).

## Scope Boundaries

In scope:
- Static lint of the specific "counter file + `output_numeric` evaluator" pattern within a single state's action/evaluator pair.
- Suggested-fix message recommending the likely intended `target:` value.

Out of scope:
- General data-flow analysis across multiple states or files.
- Counter patterns expressed in non-`printf`/non-bash actions (e.g. Python helper scripts the loop shells out to).
- Auto-fix / rewriting the YAML in place — warning-only.
- Detecting other off-by-one bugs unrelated to the zero-retry shape.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — wire the lint into the existing `ll-loop validate` path (or a new `ll-loop lint` subcommand).
- New: `scripts/little_loops/fsm/lints/counter_state.py` (or equivalent module) — `CounterStateLint` heuristic.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — registers `validate` subcommand; may need a `lint` registration if exposed separately.

### Similar Patterns
- Existing FSM schema validators in `scripts/little_loops/fsm/schema.py` — match warning emission style so output is consistent with current `ll-loop validate` messages.

### Tests
- `scripts/tests/fsm/` — new test module covering `lt target=1` (warn), `lt target=2` (no warn), `lte target=0` (warn), and non-counter actions (no warn).

### Documentation
- `docs/reference/` lint/validate documentation — add a brief note describing the new warning and its suggested-fix output.

### Configuration
- N/A

## Impact

- **Priority**: P4 — Real footgun observed in the wild, but workaround is trivial once you know the pattern; no production breakage.
- **Effort**: Small — One narrow heuristic plus unit tests; no schema changes required.
- **Risk**: Low — Warning-only output; no behavior change to existing loops, no auto-rewrites.
- **Breaking Change**: No

## Source

Findings from `~/.claude/plans/we-are-running-little-loops-glistening-kitten.md` (Finding 2).

## Labels

`enhancement`, `loops`, `lint`, `validation`, `captured`

## Status

**Open** | Created: 2026-05-23 | Priority: P4

## Session Log
- `/ll:format-issue` - 2026-05-23T19:19:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/900e25aa-792d-43a3-87b5-3b2b3c76ada1.jsonl`

- `/ll:capture-issue` — 2026-05-23T12:00:00Z
