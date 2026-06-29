---
id: ENH-2384
priority: P3
type: ENH
status: done
captured_at: '2026-06-28T19:07:41Z'
completed_at: '2026-06-29T15:10:27Z'
discovered_date: 2026-06-28
discovered_by: capture-issue
relates_to:
- BUG-2383
confidence_score: 100
outcome_confidence: 88
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 23
---

# ENH-2384: `ll-loop validate` rule — flag silent JSONDecodeError swallow in parse states

## Summary

Add an `ll-loop validate` check (new MR-* rule) that flags any loop `shell`
state whose inline Python catches `json.JSONDecodeError`/`ValueError` and exits
0 (`sys.exit(0)`, `exit(0)`, or falls through to a 0 exit) **without** an
`on_error:` route on the state. This shifts the BUG-2383 failure class left
into the validator — the same lint-gate strategy the project already uses for
MR-1 through MR-9 — so a future loop can't silently reintroduce a
swallow-and-exit-0 tagged-JSON parser.

## Current Behavior

`ll-loop validate` does not detect shell states whose inline Python catches
`json.JSONDecodeError` or `ValueError` and exits 0 without an `on_error:`
route. When such a loop runs, parse failures are silently discarded; the FSM
receives exit 0 and treats the state as successful, producing zero results with
no log, no stderr, and no non-zero exit code (as observed in BUG-2383 across
three loops).

## Expected Behavior

`ll-loop validate` emits a MR-10 WARNING when it detects a shell state that:
- contains a `json.loads`/`json.load` call, AND
- has an `except` clause catching `JSONDecodeError`/`ValueError`/bare
  `Exception` whose body exits 0 or falls through to a 0 exit, AND
- defines no `on_error:` route.

The warning is suppressed by `parse_swallow_ok: true` at the loop top-level.
The three loops fixed in BUG-2383 pass the rule clean after their fixes.

## Motivation

BUG-2383 showed that a malformed `*_JSON:` line is silently swallowed with exit
0 across three loops, producing zero results with no log, no stderr, and no
non-zero exit. The diagnosis explicitly noted: *"There is no test, no
assertion, no log line that would catch this in CI."* The existing MR-* rules
(`.claude/CLAUDE.md` § Loop Authoring) demonstrate the project's preferred fix
for exactly this situation: encode the anti-pattern as a `ll-loop validate`
rule rather than relying on post-hoc `loop-specialist` diagnosis. The
loop-specialist agent already classifies this as a `self-evaluation bias` /
silent-failure mode after the fact — this rule moves the catch upstream.

## Proposed Solution

Flag a state when **all** hold:
- `action_type: shell` (or a `fragment` resolving to shell) whose action
  contains a `json.loads`/`json.load` call, AND
- an `except` clause catching `JSONDecodeError`/`ValueError`/bare `Exception`
  whose body reaches a zero exit (`sys.exit(0)`, `exit(0)`, `print(...)` then
  fallthrough), AND
- the state defines **no** `on_error:` route.

Severity: WARNING. Suppress with a top-level `parse_swallow_ok: true` for the
rare case where treating a parse failure as an empty result is intentional and
the absence of an error route is deliberate.

## API/Interface

- New validator rule registered alongside existing MR-* checks in the
  `ll-loop validate` rule set.
- New suppression flag `parse_swallow_ok: true` (loop top-level), mirroring
  `meta_self_eval_ok`, `shared_state_ok`, etc.
- `.claude/CLAUDE.md` § Loop Authoring gets an MR-10 entry documenting the rule
  and its suppression flag.

## Implementation Steps

1. Locate the MR-* rule implementations behind `ll-loop validate` (search for
   `MR-9` / `shell_pid_ok` to find the rule module).
2. Add the MR-10 detector: parse each shell state's action for the
   `json.loads` + swallowing-`except` + zero-exit + no-`on_error` conjunction.
   A conservative regex/AST scan over the heredoc body is sufficient; prefer
   AST if the existing rules already parse Python bodies.
3. Wire the `parse_swallow_ok` suppression flag.
4. Add the MR-10 section to `.claude/CLAUDE.md` § Loop Authoring.
5. Tests: a fixture loop that swallows-and-exits-0 with no `on_error` → WARNING;
   the same with `on_error:` present → clean; the same with `parse_swallow_ok:
   true` → suppressed.

## Scope Boundaries

- Targets only `action_type: shell` states with inline Python that catches `JSONDecodeError`/`ValueError` and exits 0 without `on_error:`
- Does not flag other silent exit-0 patterns unrelated to JSON/value parsing
- Does not modify MR-1 through MR-9 rule behavior or the FSM execution engine
- Does not enforce `on_error:` routes on shell states generally — only when a parse-swallow is detected
- Does not require `on_error:` when `parse_swallow_ok: true` is set

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — add MR-10 rule function alongside `validate_mr9_shell_pid` (~line 1677); register `parse_swallow_ok` in the suppression flag list (~line 200)
- `scripts/little_loops/fsm/schema.py` — add `parse_swallow_ok: bool` field to `FSMLoop` model
- `.claude/CLAUDE.md` — add MR-10 entry to § Loop Authoring

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation.py` `validate()` — already calls all MR-* rules in chain; new rule wires in same place

### Similar Patterns
- `validate_mr9_shell_pid` in `scripts/little_loops/fsm/validation.py` — direct structural template for MR-10
- `shell_pid_ok` suppression flag in `scripts/little_loops/fsm/schema.py` — template for `parse_swallow_ok`

### Tests
- `scripts/tests/test_fsm_validation.py` — add MR-10 fixture tests (WARNING / clean with `on_error:` / suppressed with `parse_swallow_ok: true`)

### Documentation
- `.claude/CLAUDE.md` § Loop Authoring — add MR-10 rule entry with suppression flag docs

### Configuration
- N/A

## Impact

- **Priority**: P3 — Guards against BUG-2383 class recurrence; not urgent since BUG-2383 fixes are already applied
- **Effort**: Small — Follows established MR-* pattern; one detector function, one suppression flag, one CLAUDE.md entry, three test fixtures
- **Risk**: Low — Additive lint check only; no changes to FSM runtime or loop execution logic
- **Breaking Change**: No

## Related Key Documentation

- `BUG-2383` — the concrete failure this rule guards against.
- `.claude/CLAUDE.md` § Loop Authoring (MR-1 … MR-9) — existing rule family
  and suppression-flag convention this follows.
- `agents/loop-specialist.md` — diagnoses this mode post-hoc; this rule shifts
  it left.

## Labels

`enhancement`, `ll-loop-validate`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-06-29T14:59:38 - `70992822-e90f-44d6-951e-3bfa747edf4d.jsonl`
- `/ll:ready-issue` - 2026-06-29T04:20:31 - `2b8f9ec3-e4d1-42ab-9885-9ad2a83807d8.jsonl`
- `/ll:confidence-check` - 2026-06-28T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5578ac8b-2759-46cd-abba-e4e3d9e82e59.jsonl`
- `/ll:format-issue` - 2026-06-29T04:13:37 - `35b22c51-4d5e-4083-af06-a0daf08e0ece.jsonl`
- `/ll:capture-issue` - 2026-06-28T19:07:41Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b88673d-6bf0-48cb-a5d7-7d07fc889091.jsonl`

---

## Status

- **Created**: 2026-06-28
- **Status**: open
