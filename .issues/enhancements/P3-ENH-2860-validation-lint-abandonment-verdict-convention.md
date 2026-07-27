---
id: ENH-2860
status: open
priority: P3
captured_at: "2026-07-27T16:17:56Z"
discovered_date: 2026-07-27
discovered_by: capture-issue
labels: [fsm, validation, loops]
parent: EPIC-2861
relates_to: [ENH-2857]
blocked_by: [ENH-2857]
---

# ENH-2860: validation lint — abandonment must reach summary.json and downgrade the verdict (MR-13)

## Summary

Two builtin loops now independently need the convention "abandonment must reach
summary.json and downgrade the verdict": `auto-refine-and-implement.yaml` implements it
(ENH-2657: `abandoned` field + `incomplete-abandoned` verdict taking precedence over
closed>0) and `general-task.yaml` is getting it via ENH-2857. The general-task
postmortem showed what happens without it: a hardcoded `"verdict":"success"` over 8
abandoned-of-34 steps, invisible to all audit tooling. Shift this check left into
`fsm/validation.py` as a new MR-13-style WARN, same as MR-1..12 did for their failure
taxonomy.

## Current Behavior

Nothing in `ll-loop validate` notices a loop that caps per-step/per-item attempts and
rewrites plan/queue entries as abandoned, but whose summary-emitting state prints a
verdict JSON with no `abandoned` field — the exact shape that let general-task launder
8 abandoned steps into `success`.

## Expected Behavior

New WARN in `scripts/little_loops/fsm/validation.py` (suppress flag e.g.
`abandonment_verdict_ok`): fires when a loop has an abandonment mechanism — heuristics:
a shell action rewriting `- [ ]` checkbox lines while inserting an "abandoned"
annotation **or rewriting them to the `- [!]` abandonment marker** (the heuristic must
match both the old laundering shape — `[x]` + abandoned note — and the post-ENH-2857
`[!]` convention, otherwise the lint won't recognize general-task as having an
abandonment mechanism at all and the "all builtin loops pass" criterion below would be
satisfied vacuously rather than by the carve-out working), or an attempt-cap counter
pattern (`max_step_attempts`-style context var consumed in a shell action) — but no
state whose action emits an `"abandoned"` key in a summary JSON `printf`/write. Additionally flag a shell action containing a literal
hardcoded `"verdict":"success"` (or `verdict=success`) — but **only when the emitting
action has no conditional branch on an abandonment/failure counter and emits no
`"abandoned"` key in the same state**. This carve-out is load-bearing: after ENH-2857,
`general-task.yaml`'s success path will still contain a literal `"verdict":"success"`
printf on its zero-abandoned branch, and `write_partial_summary` will branch between
literal `"partial"` and `"incomplete-abandoned"` strings on its own abandoned-count
check (ENH-2857 gives the partial path the same verdict precedence, so do not assume
that state emits an unconditional `"partial"`). A naive literal-match lint would warn
on the very builtin this epic fixes, contradicting the "all builtin loops pass"
criterion below. A literal verdict string guarded by a counter branch is the *correct*
shape, not the defect.

## Motivation

Same rationale as the MR-1..12 family: two independent recurrences of a defect class in
builtin loops justify a validator gate so third-party/meta loops don't reinvent the bug.

## Implementation Steps

1. Grep `loops/` for literal `"verdict":"success"` to scope the hardcode check and
   establish the allowlist/fix set (general-task is fixed by ENH-2857).
2. Add the lint + suppress flag to `fsm/validation.py`, register in the CLAUDE.md
   Loop Authoring rule table and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`.
3. Tests in the validation test module (positive fixture, suppressed fixture, and
   assert all builtin loops pass).

## Acceptance Criteria

- [ ] `ll-loop validate` warns on abandonment-mechanism-without-abandoned-field and on hardcoded success verdicts
- [ ] Suppress flag documented in CLAUDE.md rule table + HARNESS_OPTIMIZATION_GUIDE.md
- [ ] All builtin loops pass validation after ENH-2857 lands (this issue is blocked_by ENH-2857)

## Session Log
- `/ll:capture-issue` - 2026-07-27T16:17:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3601f984-5d3e-4c48-a9b5-5cb709fc86b3.jsonl`
