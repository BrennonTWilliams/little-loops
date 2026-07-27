---
id: ENH-2857
status: open
priority: P2
captured_at: "2026-07-27T16:17:56Z"
discovered_date: 2026-07-27
discovered_by: capture-issue
labels: [loops, general-task, verification]
parent: EPIC-2861
relates_to: [ENH-2858, ENH-2859, ENH-2860]
---

# ENH-2857: general-task — make step abandonment visible, counted, and blocking

## Summary

`general-task.yaml`'s per-step attempt cap (`select_step`, Fix #2) launders a failed
hard-blocker step into a completed one: on exhaustion it rewrites the plan line from
`- [ ]` to `- [x]` with an `(abandoned: ...)` note, and `summarize_success` writes a
**hardcoded** `"verdict":"success"` that never mentions abandonment. In the
`little-loops-hermes` June run, 8 of 34 steps were abandoned — including two the plan
itself declared "Hard blocker for Steps 13, 16, 27" — and the run's dependents executed
on guesses, shipping `_hermes_compat.py` still marked `PROVISIONAL` at v1.0.0
(POSTMORTEM-general-task-verification-gaps.md, Finding 1, defect 5).

## Current Behavior

- Abandoned steps become `- [x] ... (abandoned: verify failed after N attempts)` —
  indistinguishable from completed steps to `count_done`, `check_done`, audit tooling,
  and parent loops.
- `summarize_success` emits `{"verdict":"success", "implemented":N, "failed_finals":N}`
  with no abandonment field; 8-of-34 abandoned reads identically to 0-of-34.
- No dependency check: a step whose own text says "Hard blocker for Steps 13, 16, 27"
  is abandoned and the named dependent steps run anyway.

## Expected Behavior

1. **Distinct marker**: abandoned steps are rewritten to `- [!]` (not `- [x]`), so the
   plan file never claims completion the loop did not achieve. Interactions verified:
   `count_done`'s `UNCHECKED_PLAN` greps `- [ ]` only, so `[!]` does not spin the loop;
   `mark_done`'s exact-match awk never touches them. `check_done`'s Step 1
   (plan-vs-DoD reconciliation) must be told a `[!]` step is *abandoned, not done* and
   must either get a covering DoD criterion or be surfaced.
2. **Counted verdict**: `summarize_success` counts `[!]` lines in plan.md — use a
   whitespace-tolerant pattern (`^[[:space:]]*- \[!\]`), matching `count_done`'s
   existing grep style, not a bare `^- \[!\]` — and emits `"abandoned": N` in
   summary.json. When N > 0 the verdict is `incomplete-abandoned` and the run routes
   to the `partial` terminal, not `done`. `write_partial_summary` gets the same
   `abandoned` count **and the same verdict precedence**: when its count > 0 it emits
   `"verdict":"incomplete-abandoned"` instead of `"partial"`, per the ENH-2657
   precedent (abandoned takes precedence over every success/partial bucket). This
   verdict-branching in `write_partial_summary` is coordinated with ENH-2860's lint
   carve-out, which must not assume that state keeps a literal `"partial"`. Port the
   precedent from `auto-refine-and-implement.yaml` (ENH-2657, ~L809–990).
3. **Dependency halt**: before abandoning, `select_step` checks **both directions**
   for blocker relationships, because in the Hermes case the declaration lived in the
   *abandoned step's own text* ("Hard blocker for Steps 13, 16, 27") — the dependent
   steps never mentioned the abandoned step, so a remaining-steps-only grep would miss
   the exact defect this issue cites:
   - (a) the abandoned step's own line matches `[Bb]locker|[Gg]ated|[Pp]rerequisite`
     alongside a step reference — halt;
   - (b) any remaining `- [ ]` line textually references the abandoned step's number —
     halt. The pattern must tolerate comma-separated lists (`Steps? 13, 16, 27`), not
     just `Step N\b`; a naive word-boundary match misses all but the first number.

   On a hit in either direction, do not abandon-and-continue — **still rewrite the
   step to `- [!]` first** (it did exhaust its attempts; the halt only changes what
   happens to the *remaining* steps), then record the reason and route to
   `summarize_partial`. Without the rewrite, `write_partial_summary`'s `abandoned`
   count would read 0 for the exact run that halted because of an abandonment.
   ~20 lines of shell, no LLM call; direction (a) alone would have prevented Hermes
   defect 5 using text the plan already contained.

## Motivation

A failed hard blocker is currently indistinguishable from a completed step — the single
largest gap identified in the postmortem. Downstream audit tooling (`audit-loop-run`)
and parent loops key on summary.json verdicts; a success verdict over 8 abandoned steps
defeats all of them.

## Proposed Solution

- `select_step` abandonment branch: change `sub(/^- \[ \]/, "- [x]")` to `- [!]`; add
  the two-direction blocker check before the rewrite, routing to `summarize_partial` on
  hit (new capture pattern, e.g. `STEP_BLOCKER_HALT`).
- `summarize_success`: count `[!]`, add `abandoned` to the JSON, branch verdict; route
  to `partial` when abandoned > 0 (verdict string `incomplete-abandoned`, matching
  ENH-2657 naming). **Routing mechanism**: the state currently ends the success path
  unconditionally, so branching the verdict *string* is not enough — the terminal must
  change too. Concretely: capture the `[!]` count (e.g. `ABANDONED_COUNT`) and route on
  it via `output_numeric` (or an exit-code split) from a non-terminal summarize state to
  the `done` vs `partial` terminals — the `rn-implement::report` shape. Do not put the
  branch inside a `terminal: true` state's action (terminal-action-ok lint) and keep
  the capture dominating its references (capture-reachability lint).
- `write_partial_summary`: add the same `abandoned` count and branch its verdict to
  `incomplete-abandoned` when the count > 0 (see Expected Behavior 2).
- `check_done` prompt: one paragraph defining `[!]` semantics.
- Structural tests in `scripts/tests/test_builtin_loops.py` (existing `general-task`
  class at ~L11638), matching the per-fix test style used for ENH-2246 etc.

## Acceptance Criteria

- [ ] Abandoned steps are marked `- [!]`, never `- [x]`
- [ ] `summary.json` contains `"abandoned": N` on both success and partial paths; the `[!]` count pattern is whitespace-tolerant (`^[[:space:]]*- \[!\]`)
- [ ] Verdict is `incomplete-abandoned` when N > 0 on **both** paths (`summarize_success` routes to the `partial` terminal; `write_partial_summary` emits it in place of `"partial"`)
- [ ] Abandoning a step that either declares itself a blocker in its own text (the Hermes shape) or is referenced by a remaining unchecked step halts the run via `summarize_partial` — after rewriting the step to `- [!]` so it is counted; blocker patterns match comma-separated `Steps N, M, ...` lists
- [ ] `ll-loop validate general-task` passes; structural tests added and green

## Session Log
- `/ll:capture-issue` - 2026-07-27T16:17:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3601f984-5d3e-4c48-a9b5-5cb709fc86b3.jsonl`
