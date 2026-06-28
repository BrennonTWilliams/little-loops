---
id: ENH-2384
priority: P3
type: ENH
status: open
captured_at: "2026-06-28T19:07:41Z"
discovered_date: 2026-06-28
discovered_by: capture-issue
relates_to: [BUG-2383]
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

## Proposed Rule (MR-10, WARNING)

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

## API / Interface

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

## Acceptance Criteria

- `ll-loop validate` emits a WARNING for a parse state that swallows
  `JSONDecodeError` and exits 0 with no `on_error` route.
- The warning is suppressed by `parse_swallow_ok: true`.
- The three loops in BUG-2383, once fixed, pass the rule clean.

## Related

- `BUG-2383` — the concrete failure this rule guards against.
- `.claude/CLAUDE.md` § Loop Authoring (MR-1 … MR-9) — existing rule family
  and suppression-flag convention this follows.
- `agents/loop-specialist.md` — diagnoses this mode post-hoc; this rule shifts
  it left.

## Session Log
- `/ll:capture-issue` - 2026-06-28T19:07:41Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b88673d-6bf0-48cb-a5d7-7d07fc889091.jsonl`

---

## Status

- **Created**: 2026-06-28
- **Status**: open
