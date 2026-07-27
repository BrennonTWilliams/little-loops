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

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — `select_step` (lines 155–199,
  abandonment rewrite at 177–182), `summarize_success` (lines 542–586, hardcoded
  verdict at 578–579), `write_partial_summary` (lines 683–728, hardcoded verdict
  at 718–719), `check_done` prompt (lines 312–367)

### Dependent Files (Callers/Interactions)
- `count_done`'s `UNCHECKED_PLAN` grep (`general-task.yaml:412`,
  `grep -c '^[[:space:]]*-[[:space:]]*\[[[:space:]]\]'`) — matches only literal
  `[ ]`; confirmed a `[!]` marker will NOT match this pattern (so it won't
  re-spin the loop), same as the current `[x]` rewrite doesn't.
- `mark_done`'s exact-match awk (`general-task.yaml:293–310`,
  `$0==target && /^- \[ \]/`) — regex-anchored to `- \[ \]`; confirmed it cannot
  touch an already-`[!]`-marked line.
- `spin_gate` (`general-task.yaml:209–219`) — existing `output_numeric` gate
  (`lt 3` against a spin counter file) is the closest in-file precedent for the
  "count → branch to `summarize_partial`" shape this issue's dependency-halt
  routing needs.
- `partial`/`done` terminals (`general-task.yaml:730–738`) — `partial` is
  deliberately non-`done` (comment at 731–734) so parent sub-loop dispatch
  treats it as `on_failure`; the new `incomplete-abandoned` verdict piggybacks
  on this existing terminal rather than needing a third terminal.

### Similar Patterns
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:799–990` (ENH-2657)
  — the precedent this issue explicitly ports. Ledger diff at lines 799–815
  (`comm -23` against a closed-union file, not a raw grep count), precedence
  check at lines 930–953 (`if [ "$ABANDONED" -gt 0 ]; then VERDICT=incomplete-abandoned`
  — checked *before* the closed/error/skip branches), JSON emission at 955–956,
  and the exit-code gate at 964–982 (`case "$VERDICT" in phantom|incomplete-abandoned)
  exit 1 ;; *) exit 0 ;; esac` combined with the `shell_exit` fragment routing
  `on_yes: done` / `on_no: finalize_incomplete`) — this exit-code-gated
  non-terminal-state shape is exactly what MR terminal-action-ok requires (see
  Validation Constraints below).
- `scripts/little_loops/loops/rn-implement.yaml:1429–1462,1661–1668` (`report`
  → `next: done` → bare `done:` terminal) — the canonical "write summary in a
  penultimate non-terminal state, keep the terminal bare" shape cited by
  `terminal_action_ok`'s own error message.

### Validation Constraints
- `terminal_action_ok` (`scripts/little_loops/fsm/validation.py:1153–1198`) —
  any new/modified terminal must stay bare (`terminal: true`, no `action:`);
  the `ABANDONED_COUNT` capture + `output_numeric` routing must live in a
  penultimate state (`summarize_success` itself, or a new state inserted
  before the `done`/`partial` terminals), not inside the terminal.
- `capture_reachability_ok` (`scripts/little_loops/fsm/validation.py:2957–3014+`)
  — the new `${captured.ABANDONED_COUNT...}` (or equivalent) reference must be
  dominated by the state that captures it on every path that reaches
  `summarize_success`/`write_partial_summary`.

### Tests
- `scripts/tests/test_builtin_loops.py:11637–11786` (`class TestGeneralTaskLoop`)
  — existing per-fix test grouping convention (`# ENH-2246: ...` /
  `# ENH-2293: ...` comment banners inside the same class, one test method per
  assertion, checks against `state.get("next")`/`on_error`/`action_type` and
  substring presence in `action`). A new `# ENH-2857: ...` banner should follow
  this same in-class grouping rather than a new test class. Also check the
  `(loop_file, state_name, field) -> issue_tag` on_error-exemption registry
  near `test_builtin_loops.py:72–73` if `summarize_success`/`write_partial_summary`
  on_error routing changes.

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
- Structural tests in `scripts/tests/test_general_task_loop.py` too — this is the
  dedicated, larger structural test file for this loop (see Integration Map ›
  Files to Modify); it already has `write_partial_summary` assertions on the exact
  `"verdict":"partial"` string this issue changes, so implement the precedence via
  a `$VERDICT` variable rather than a straight substring replacement.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `select_step`'s existing abandonment rewrite is at `general-task.yaml:177–182`:
  `awk -v target="$STEP" ... 'found==0 && $0==target && /^- \[ \]/ { sub(/^- \[ \]/, "- [x]"); $0=$0 "  (abandoned: ...)"; found=1 } 1'`.
  Changing the `sub()` replacement string from `"- [x]"` to `"- [!]"` is the
  entire marker-format change; the surrounding guard (`$0==target && /^- \[ \]/`)
  needs no modification.
- `summarize_success`'s current verdict write is a literal, unconditional
  `printf` at `general-task.yaml:578–579` (`"verdict":"success"` with no
  abandonment field), reached via `next: done` (line 583, `terminal: true` at
  737) with `on_error: done` also routing to success (line 586, deliberately
  per the ENH-2365 comment there — do not remove that on_error routing).
- `write_partial_summary`'s current verdict write is the analogous literal
  `printf` at `general-task.yaml:718–719` (`"verdict":"partial"`), routed via
  `next: partial` / `on_error: partial` (lines 723, 728) to the bare `partial`
  terminal (730–735).
- The ENH-2657 precedent (`auto-refine-and-implement.yaml:930–953`) checks
  `ABANDONED -gt 0` **before** any success/partial branch, so
  `incomplete-abandoned` always wins — port this precedence ordering, not just
  the field name, into both `summarize_success` and `write_partial_summary`.
- `count_done`'s `UNCHECKED_PLAN` grep (`general-task.yaml:412`) already
  excludes `[x]`-marked (and would exclude `[!]`-marked) lines, so no change is
  needed there; the whitespace-tolerant `[!]` count pattern this issue
  specifies (`^[[:space:]]*- \[!\]`) is a **new** grep to add in
  `summarize_success`/`write_partial_summary`, matching `count_done`'s existing
  `[[:space:]]*` style rather than introducing a stricter pattern.

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/proof-first-task.yaml` — delegates to `general-task` as its `impl_loop` (line 14); the sub-loop's `summary.json` (with the new `abandoned`/`incomplete-abandoned` fields) is what this wrapper reads back for its own outcome handling. [Agent 1 finding]

### Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_general_task_loop.py` — this is the **primary, previously-uncited** structural test file for `general-task.yaml` (1707 lines, `TestGeneralTaskLoopFile` and per-fix classes keyed to ENH numbers), distinct from `scripts/tests/test_builtin_loops.py`'s smaller `general-task` class the issue's Proposed Solution names. It already contains `write_partial_summary` tests that hardcode the exact string this issue changes: `test_write_partial_summary_emits_partial_verdict_json` (~line 1649) asserts `'"verdict":"partial"' in action`, `test_write_partial_summary_on_error_still_reaches_partial` (~line 1654) asserts `on_error == "partial"`, and lines ~1670–1706 assert `data["verdict"] == "partial"` / `"verdict=partial checked=2/4"` in stdout for a no-abandoned-steps fixture. Implement the new precedence as `if [ "$ABANDONED" -gt 0 ]; then VERDICT=incomplete-abandoned; else VERDICT=partial; fi` interpolated into the printf so the literal `"verdict":"partial"` substring survives for the zero-abandoned case — a straight string replacement breaks these tests. [Agent 2 + 3 findings]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` (~lines 101–118, the `general-task` walkthrough) — prose currently documents `select_step`'s abandonment branch, `spin_gate`'s abandonment-driven routing to `summarize_partial`, and `summarize_success`'s hardcoded `{"verdict":"success","implemented":N,"failed_finals":0}` payload (this last line is the exact claim ENH-2857 falsifies) — needs an update describing the `[!]` marker, the `abandoned` count, and the `incomplete-abandoned` verdict precedence on both success and partial paths. [Agent 2 finding]
- `skills/audit-loop-run/SKILL.md` (Step 6a, ~line 290 and its verdict table ~lines 305–313) — documents `general-task`'s claimed-success counter (`implemented`) and enumerates verdict classifications (`phantom`, `honest-failure`, etc.) but has **no entry for `incomplete-abandoned`**, which currently only exists for `auto-refine-and-implement`/`autodev` (ENH-2657). Add guidance so an auditor reading a `general-task` summary.json knows how to classify the new verdict. [Agent 2 finding]

### Implementation Constraints (from `fsm/validation.py`, confirmed)

_Wiring pass added by `/ll:wire-issue`:_
- `terminal-action-ok` (`_validate_terminal_action_ok`) fires if `incomplete-abandoned` routing is special-cased via an `action:` placed directly on the `done`/`partial` terminals. Insert a non-terminal shell/routing state before them instead (mirroring `rn-implement.yaml`'s `report:` state at line 1429, and this file's own existing `count_done`/`count_final` → terminal pattern) — this satisfies the rule and is the shape the issue's Proposed Solution already points at ("the `rn-implement::report` shape").
- `capture-reachability` (`_validate_capture_reachability`) only becomes relevant if the new routing state introduces a `${captured.*}` reference (e.g. reading back an abandoned-count capture in a later state); `summarize_success` currently has no `capture:` key, and the loop's path here is linear (no branches), so dominance holds as long as no state skips the capturing state.
- Neither rule inspects plan-file marker syntax (`[x]`/`[ ]`/`[!]`) — that's shell-internal to `action:` bodies, invisible to the YAML-structural validator. The `[!]` change is a test/shell-pattern concern only, not an `ll-loop validate` concern.

## Acceptance Criteria

- [ ] Abandoned steps are marked `- [!]`, never `- [x]`
- [ ] `summary.json` contains `"abandoned": N` on both success and partial paths; the `[!]` count pattern is whitespace-tolerant (`^[[:space:]]*- \[!\]`)
- [ ] Verdict is `incomplete-abandoned` when N > 0 on **both** paths (`summarize_success` routes to the `partial` terminal; `write_partial_summary` emits it in place of `"partial"`)
- [ ] Abandoning a step that either declares itself a blocker in its own text (the Hermes shape) or is referenced by a remaining unchecked step halts the run via `summarize_partial` — after rewriting the step to `- [!]` so it is counted; blocker patterns match comma-separated `Steps N, M, ...` lists
- [ ] `ll-loop validate general-task` passes; structural tests added and green

## Session Log
- `/ll:wire-issue` - 2026-07-27T17:39:44 - `82e9a15d-7cdb-4b8a-960c-07a9ad645126.jsonl`
- `/ll:refine-issue` - 2026-07-27T17:38:22 - `df687459-c84a-4cb2-988d-1cafdba36512.jsonl`
- `/ll:capture-issue` - 2026-07-27T16:17:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3601f984-5d3e-4c48-a9b5-5cb709fc86b3.jsonl`
