---
id: ENH-2936
type: ENH
priority: P2
status: done
captured_at: '2026-07-31T21:54:57Z'
completed_at: '2026-07-31T23:52:59Z'
discovered_date: 2026-07-31
discovered_by: capture-issue
relates_to:
- ENH-2715
- ENH-2443
- ENH-2866
- ENH-2666
confidence_score: 95
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---
# ENH-2936: decide-issue: score un-preferenced decision directives instead of NO_ACTIONABLE_DECISIONS


## Summary

`/ll:decide-issue --auto` declines to act on the one decision shape where its scoring
pipeline would add the most value: an issue that names 2+ concrete alternatives plus an
explicit imperative to decide ("stamp it or move it to Out of scope with a stated reason
— do not leave it unaddressed") but states **no preference**. Phase 3b's Pattern D
(ENH-2715) requires a stated preference to materialize inline alternatives, so this shape
falls through every extraction pattern, the skill exits `NO_ACTIONABLE_DECISIONS`, and
`decision_needed: true` survives indefinitely. Three coupled changes fix it:

1. **Skill**: add an "un-preferenced decision directive" shape to Phase 3b — materialize
   the named alternatives as `**Option A**`/`**Option B**` blocks (reusing ENH-2715
   step 1's machinery) and route to Phase 4–7 evidence-based scoring, which exists
   precisely to pick a winner when no preference is stated.
2. **Companion CLI**: teach `ll-issues check-decidable` the same pattern so the FSM
   pre-gate agrees with the skill. (Note: exit 1 does not permanently divert to refine —
   both `autodev.yaml` and `rn-remediate.yaml` bound the `deposit_options` detour to one
   retry and fall through to decide anyway. The parity fix buys gate agreement and skips
   a wasted refine call per issue; it is not load-bearing for the skill fix.)
3. **Orchestrator visibility**: close the one remaining gap on the score-failing path.
   Autodev already routes "decide ran, flag still armed" to `record_decision_unresolved`
   on the score-passing path (`assert_decision_cleared`, BUG-2595) and the error path
   (`check_decision_after_decide_error`, ENH-2717). The gap is `recheck_after_decide` →
   `on_no: snap_and_size_review` → `recheck_after_size_review`, whose deferral cascade
   checks design-gate/stagnation/low-readiness but never consults `decision_needed` —
   the exact path ENH-2866 took (outcome 56 < threshold).

## Motivation

ENH-2866 postmortem: the issue was deferred `readiness_stagnated` (2026-07-31) with
outcome confidence capped at 56/100, despite being unusually well-researched. Root cause
was not missing research — a `/ll:decide-issue --auto` run (2026-07-31T02:57:31, session
`ffa285f4-3818-4fef-a251-cc2e4a030e29.jsonl`) correctly identified the real open item
(ll-queue run: stamp it or exempt it) but classified it as not a decidable option pair
because no preference was stated, logged `NO_ACTIONABLE_DECISIONS`, and wrote no
`.ll/decisions.d/` fragment. Every subsequent pass (refine, wire, reconcile,
confidence-check ×3) re-flagged the item as still-open. The remedy chain has a genuine
hole: nothing converts "decide before implementation" into `decided: X because Y` unless
a human edits the issue directly. The Ambiguity subscore (Criterion C, capped 8/25) can
never recover through automation.

Secondary failure: the deferral reason lied. `readiness_stagnated` means "every remedy
was attempted and readiness didn't move"; the truthful reason was `decision_unresolved`
("a human needs to make a scope call"). `ll-issues deferred-triage` therefore surfaces
the wrong ask.

## Current Behavior

- Phase 3b Pattern D (skills/decide-issue/SKILL.md) only accepts inline alternatives
  accompanied by a stated preference (declarative recommendation marker, or an
  Open-Questions item with "could do X or Y" + stated leaning). Alternatives + imperative
  decide-marker + no preference → zero candidates → `NO_ACTIONABLE_DECISIONS`, exit 0,
  `decision_needed` unchanged.
- The scan scope for the ENH-2715 inline shape is `## Open Questions`; ENH-2866's
  directive lived in `## Scope Boundaries` prose.
- `ll-issues check-decidable` (`scripts/little_loops/cli/issues/check_decidable.py`, a
  thin wrapper over `issue_parser.locate_enumerable_options()`) counts enumerable option
  blocks only; it exits 1 on this shape, sending `rn-remediate`/`autodev` on a bounded
  one-retry `deposit_options` detour through `/ll:refine-issue --auto` (which cannot
  resolve it either) before falling through to decide.
- autodev's edges to `record_decision_unresolved` cover the score-passing path
  (`assert_decision_cleared`) and the decide-error path
  (`check_decision_after_decide_error`), but NOT the score-failing path: the
  `recheck_after_size_review` deferral cascade (design-gate → stagnation →
  low-readiness) never checks `decision_needed`, so the issue defers as
  `readiness_stagnated` (or `low_readiness`).

## Expected Behavior

- In `--auto` mode with `decision_needed: true`, a passage naming 2+ concrete
  alternatives alongside an imperative decide-marker ("decide before implementation",
  "do not leave unaddressed", "stamp it or exempt it", "X or Y — pick one") with no
  stated preference is treated as decidable: alternatives are materialized as
  `**Option A**`/`**Option B**` blocks under `## Proposed Solution` (verbatim from the
  existing text, never invented), then routed through Phase 4–7 full scoring. Phase 7
  annotates the winner, sets `decision_needed: false`, and writes the decisions-log
  entry as usual.
- Scan scope covers unresolved `## Open Questions` items AND directive sections where
  such imperatives live (`## Scope Boundaries`, `## Proposed Change` /
  `## Proposed Solution`).
- `ll-issues check-decidable` exits 0 on the same shape (same regex/heuristic family,
  pure Python, no LLM).
- When decide still ends `NO_ACTIONABLE_DECISIONS` with `decision_needed: true`, the
  orchestrating loop defers the issue as `decision_unresolved`, not
  `readiness_stagnated`/`low_readiness`.

## Impact

- **Priority**: P2 - closes a real remedy-chain gap (ENH-2866) where automation
  silently fails to clear a `decision_needed` flag it is capable of resolving.
- **Effort**: Medium - three coupled changes (skill pattern, parser heuristic,
  orchestrator branch) each with dedicated tests, plus a guaranteed SKILL.md
  companion-file split (ENH-494 pattern) at the current 491/500 line count.
- **Risk**: Low - additive pattern behind a tight co-occurrence guardrail
  (imperative marker + 2+ alternatives within ~3 lines); bare "X or Y" prose
  without the marker is explicitly excluded to avoid re-litigating settled lists.
- **Breaking Change**: No - existing Pattern D behavior and `decision_needed`
  semantics are unchanged; this only adds a new recognized shape.

## Proposed Solution

**Guardrail rationale**: the imperative marker is what distinguishes this from the
settled-informal-list case that Pattern 4's auto-mode conservatism protects against
(automation must not re-litigate a list the author already settled). Here the issue text
explicitly *asks* for a decision, so scoring it re-litigates nothing. Fire only when
`AUTO_MODE = true` AND `decision_needed: true` AND the imperative marker co-occurs
(within ~3 lines) with the named alternatives.

1. **skills/decide-issue/SKILL.md** — add Provisional Pattern E (un-preferenced decision
   directive) to Phase 3b: match 2+ concrete alternatives ("X or Y", enumerated
   alternatives in one passage) co-located with an imperative decide-marker and no
   preference marker. Resolution: reuse ENH-2715 step 1 materialization → re-scan →
   route to Phase 4 scoring (the step-2 path). Update the Pattern D "Requirement" note
   to point at Pattern E for the no-preference case.
2. **`ll-issues check-decidable`** — add the Pattern E heuristic in
   `scripts/little_loops/issue_parser.py` (alongside `locate_enumerable_options()`) so
   the FSM pre-gate agrees with the skill; `check_decidable.py` calls it. Keep the
   heuristic tight (2+ named alternatives co-located within ~3 lines of an imperative
   decide-marker, no preference marker) — bare "X or Y" prose must keep exiting 1.
3. **Orchestrator wiring** — in `scripts/little_loops/loops/autodev.yaml`, add a
   `decision_needed` re-check to `recheck_after_size_review`'s deferral cascade
   (after the design-gate branch, before the `readiness_stagnated` branch): when the
   flag is still armed, defer as `decision_unresolved` via the same set-status idiom
   `record_decision_unresolved` uses. Re-checking the flag is the established idiom
   (`assert_decision_cleared`, `check_decision_after_decide_error`) — do NOT invent
   `NO_ACTIONABLE_DECISIONS` outcome-token parsing.

**Alternative considered (softer variant)**: have Pattern E score the options but write
the result only as a recommendation, leaving `decision_needed: true` for manual
clearing. Rejected as the default because it reintroduces the human-in-the-loop stall
for every such issue; the full-scoring path already leaves an audited rationale
(annotation + decisions-log fragment) reviewable at go/no-go.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Pattern D location**: `skills/decide-issue/SKILL.md:249-261` (Provisional Pattern D —
  Declarative recommendation). The "Requirement" gate Pattern E must bypass is the "with a
  stated preference" clause at lines 254-260.
- **Materialization machinery** ("ENH-2715 step 1/2") lives in Resolution Logic,
  `skills/decide-issue/SKILL.md:273-296`: step 1 (273-289) rewrites named alternatives into
  `**Option A**`/`**Option B**` blocks (reusing the bold-label template from
  `commands/refine-issue.md:284-297`); step 2 (290-296) re-runs Phase 3 extraction and routes
  to Phase 4 once `OPTIONS >= 2`. Pattern E should trigger this same step-1/step-2 path
  without going through the "clear winner" preference check first — Phase 4's evidence-based
  scoring picks the winner instead of textual-preference detection.
- **Current fallthrough for un-preferenced directives**: `skills/decide-issue/SKILL.md:314-318`
  — logs `✗ Phase 3b: no resolvable provisional decision found`, leaves `decision_needed:
  true` unchanged, exits straight to Phase 8 (skipping Phases 4-9 scoring/annotation).
- **`issue_parser.py` building blocks**: `_OPTION_PATTERNS` (410-417, four regex tiers),
  `_OPTION_FALLBACK_SECTIONS = ("Codebase Research Findings", "Implementation Status")`
  (419), `_count_options_in_text()` (422-428), `locate_enumerable_options()` (449-482,
  3-tier precedence ending in a whole-document H2 fallback via `_iter_h2_sections()`,
  431-446), `count_enumerable_options()` (485-494). None of these scan `## Open Questions`
  for inline "X or Y" prose today — that's purely a SKILL.md Phase 3b concept. Adjacent
  precedent to build the Pattern E heuristic on: `_RESOLVED_QUESTION_MARKER_RE` (591-599)
  and `_OPEN_QUESTION_SIGNAL_RE` (604-615, already matches `\bdecision needed\b`/`\bdecision
  point\b`/`\bopen decision\b`) plus `count_open_questions_in_sections()` (643-656) scanning
  `_OPEN_QUESTION_SECTIONS = ("Edge Cases", "Confidence Check Notes", "Open Questions")`
  (618) — none currently detect "2+ named alternatives," but this is the established
  precedent for scoping to unresolved Open-Questions items.
- **`check_decidable.py` exact call site**: `cmd_check_decidable()`
  (`scripts/little_loops/cli/issues/check_decidable.py:19-49`) calls
  `locate_enumerable_options(path.read_text())` at line 34; exit-0 branch at line 37, exit-1
  `OPTIONS_MISSING` branch at line 49. Extend `locate_enumerable_options()` itself so this
  CLI inherits Pattern E parity for free, rather than adding a second call site inside
  `cmd_check_decidable()`.
- **autodev.yaml decision state graph**: four entry points funnel into
  `check_decision_decidable` (518-537, the sole `ll-issues check-decidable` call site):
  `check_decision_after_refine` (474-482), `decide_current` (502-516, re-entered from
  `recheck_after_size_review.on_yes` at line 1876), `check_decision_before_size_review`
  (1120-1132), `triage_outcome_failure` (1134-1149, bypasses the gate entirely when
  `decision_needed == 'true'`). Deferral chain: `run_decide` (599-614) → `mark_decide_ran` →
  `recheck_after_decide` (658-674) → `assert_decision_cleared` (676-688, re-verifies the
  flag, BUG-2595) → `record_decision_unresolved` (690-713, the exact `set-status ...
  deferred --by automation --reason decision_unresolved` idiom to copy).
  `check_decision_after_decide_error` (616-626) is the sibling short-circuit on
  `run_decide.on_error`. `recheck_after_size_review`'s own design-gate → stagnation →
  low-readiness cascade is at lines 1722-1878; its only intersection with the decision path
  is `on_yes: decide_current` at line 1876 — it does not consult `decision_needed` today,
  confirming the gap point 3 describes.
- **YAML shape to copy for the new orchestrator branch** (from
  `check_decision_after_decide_error`, lines 616-626):
  ```yaml
  check_decision_after_decide_error:
    action: "ll-issues check-flag ${captured.input.output} decision_needed"
    fragment: shell_exit
    on_yes: record_decision_unresolved
    on_no: recheck_after_decide
    on_error: recheck_after_decide
  ```
- **Test scaffolding to reuse**: `TestPhase3bMaterializeInformalDecisions`
  (`scripts/tests/test_decide_issue_skill.py:584-635`, using the shared `_phase_text()`
  helper at 553-558) is the direct ENH-2715 precedent for a Pattern-E structural test class.
  `TestCheckDecidableWidenedOptions.test_options_under_open_questions_exit_zero` /
  `test_no_options_at_all_exit_one` (`scripts/tests/test_ll_issues_check_decidable.py:107-137`
  / `139-157`) are the fixture scaffolds for the new positive/negative check-decidable
  fixtures. `TestCheckDecisionAfterDecideErrorStructural`
  (`scripts/tests/test_autodev_decision_gate.py:923-1007`) and
  `TestAssertDecisionClearedRouting` (1009-1088) are the closest precedent test classes
  (structural-assertion and FSMExecutor-driven-routing styles respectively) for the new
  `decision_unresolved`-on-score-failing-path branch.

## Program Design

### Types

No new data types. The heuristic returns the same `tuple[int, str | None]` shape
`locate_enumerable_options()` already returns (`(count, containing_heading)`); no
new dataclass or schema is introduced.

### Signatures

- `_locate_directive_alternatives(content: str) -> tuple[int, str | None]`
  (new, `scripts/little_loops/issue_parser.py`, placed alongside
  `_OPTION_PATTERNS`/`_count_options_in_text`) — Pattern E heuristic. Scans
  `## Scope Boundaries`, `## Proposed Change`, `## Proposed Solution`, and
  `## Open Questions` section bodies (reusing `_section_body()`, the same
  primitive `locate_enumerable_options()` already calls) for an imperative
  decide-marker (new `_DECIDE_IMPERATIVE_RE`, sibling to
  `_OPEN_QUESTION_SIGNAL_RE`, matching phrases like `\bdecide before
  implementation\b`, `\bdo not leave (?:it |this )?unaddressed\b`, `\bstamp it
  or\b`, `\bpick one\b`) co-occurring within 3 lines of 2+ named alternatives
  (`\bX or Y\b`-shaped enumeration, reusing the loosest existing
  `_OPTION_PATTERNS` tier plus a new inline "A or B" regex) **and no**
  preference marker (reuses Pattern D's stated-preference vocabulary as a
  negative check — presence of a preference marker disqualifies the passage
  from Pattern E, since Pattern D already handles that case). Returns `(2,
  heading)` on a match, `(0, None)` otherwise — never counts higher than the
  co-occurring block requires, since Pattern E only ever proves "a decision
  exists here," not how many alternatives.
- `locate_enumerable_options(content: str) -> tuple[int, str | None]`
  (existing, `issue_parser.py:449`) — gains one more precedence tier: after
  the existing scoped-scan → fallback-sections → whole-document-H2 chain all
  return 0, try `_locate_directive_alternatives(content)` before returning
  `(0, None)`. `count_enumerable_options()` and `cmd_check_decidable()` both
  call through this function, so both inherit Pattern E parity with no new
  call site (per the Codebase Research Findings note on
  `check_decidable.py:34`).
- `skills/decide-issue/SKILL.md` Phase 3b gains a new prose pattern block
  ("Provisional Pattern E — Un-preferenced decision directive") — no code
  signature; matched by the LLM directly against the same imperative-marker +
  alternatives co-occurrence rule `_locate_directive_alternatives()`
  encodes, so the skill and the deterministic probe stay in lockstep by
  construction (same rule, independently applied by LLM and regex).
- `recheck_after_size_review`'s inline Python block
  (`scripts/little_loops/loops/autodev.yaml:1722`) gains one more field read
  off the existing `ll-issues show "$ID" --json` payload already fetched for
  `GATE` — `decision_needed` (string `"true"`/`"false"`) — piped into a new
  `DECISION_UNRESOLVED` shell variable. No new subprocess call: the JSON is
  already in hand.

### Call Path

Skill path (Phase 3b → scoring):
`skills/decide-issue/SKILL.md` Phase 3b pattern match (Pattern E) →
Resolution Logic step 1 (materialize `**Option A**`/`**Option B**` blocks
under `## Proposed Solution`, verbatim from matched text) → step 2 (re-run
Phase 3 extraction, now finds `OPTIONS >= 2`) → **Phase 4** (Gather Codebase
Evidence) → Phase 5–7 (score, annotate `> **Selected:**` +
`### Decision Rationale`, `decision_needed: false`) → Phase 8/9 (session log,
report). Pattern D's existing "Requirement" note gets a cross-reference to
Pattern E for the no-preference case; no other Phase 3b pattern changes.

Deterministic pre-gate path:
`cmd_check_decidable()` (`check_decidable.py:19`) →
`locate_enumerable_options()` (`issue_parser.py:449`, extended with the new
Pattern E tier) → `_locate_directive_alternatives()` (new) → exit 0/1. Four
call sites inherit this for free without their own changes:
`check_decision_after_refine`, `decide_current`'s
`check_decision_before_size_review`, `check_decision_decidable`, and
`triage_outcome_failure` (all in `autodev.yaml`, per the Codebase Research
Findings state-graph note) — none call `locate_enumerable_options()` directly,
they all route through `ll-issues check-decidable`.

Orchestrator deferral path (the score-failing gap):
`recheck_after_size_review` action (`autodev.yaml:1722`) → existing
`DESIGN_FAIL` check (unchanged, still first) → new `DECISION_UNRESOLVED`
check (inserted after the design-gate branch at line ~1799, before the
`CYCLE_COUNT`/`readiness_stagnated` branch at line ~1837) → when
`decision_needed == "true"`: `echo "$ID  decision_unresolved" >>
autodev-skipped.txt` then `ll-issues set-status "$ID" deferred --by
automation --reason decision_unresolved` (the exact idiom
`record_decision_unresolved`, lines 690-713, already uses on the
score-passing/decide-error paths) → `exit 1` → routes through the state's
existing `on_no: check_pre_deferral_remedy` edge unchanged (no new FSM edge
required — this is a shell-level branch inside one existing action, not a new
state).

## Scope Boundaries

- **In scope**: Phase 3b pattern addition; check-decidable parity; autodev/rn-remediate
  deferral-reason wiring; tests for all three.
- **Out of scope**: resolving factual contradictions between issue sections (that is
  `/ll:reconcile-issue`'s charter — see ENH-2937); interactive-mode behavior changes;
  authoring alternatives not named in the issue text.

## Integration Map

### Files to Modify
- `skills/decide-issue/SKILL.md` (Phase 3b patterns + resolution logic). **The file is
  at 491/500 lines** (ll-verify-skills cap), so overflow extraction to
  `skills/decide-issue/reference.md` (currently 107 lines) is guaranteed, not
  contingent — plan the split up front per the ENH-494 companion pattern.
- `scripts/little_loops/issue_parser.py` (Pattern E heuristic, shared home so
  `check_decidable.py` and any future probe reuse it)
- `scripts/little_loops/cli/issues/check_decidable.py` (call the new heuristic as a
  fallback when `locate_enumerable_options()` finds 0)
- `scripts/little_loops/loops/autodev.yaml` (`recheck_after_size_review` deferral
  cascade only; `rn-remediate.yaml` needs no change — its decide path already
  escalates via `check_convergence`)

_Wiring pass added by `/ll:wire-issue`:_
- `.gemini/skills/decide-issue/SKILL.md`, `.kimi-code/skills/decide-issue/SKILL.md` —
  `ll-adapt`-generated mirrors of `skills/decide-issue/SKILL.md`; both currently carry
  the same Pattern-D-only text and will drift stale once the canonical skill gets
  Pattern E + the ENH-494 `reference.md` split. Regenerate via
  `ll-adapt --host gemini --apply` / `ll-adapt --host kimi-code --apply` as the last
  implementation step. No drift-detection test currently catches a missed
  regeneration. [Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/recursive-refine.yaml` (`check_decision_needed`, line
  554) and `scripts/little_loops/loops/refine-to-ready-issue.yaml`
  (`check_decision_mid_refine`/`check_decision_mid_wire`, lines 153/193) both re-read
  the `decision_needed` frontmatter flag via `ll-issues check-flag`, independent of
  `check-decidable`'s heuristic — verify Pattern E's new decidability does not change
  what these states observe (they should be unaffected, since they gate on the flag,
  not on option-counting) [Agent 1 finding]
- `skills/manage-issue/SKILL.md` (Phase 2.3 Decision Gate, line 173) directs to
  `/ll:decide-issue` when `decision_needed` is set — no change expected, listed for
  awareness only [Agent 1 finding]

### Tests
- Existing issue_parser/check-decidable tests from ENH-2443 (extend with
  un-preferenced fixtures, both with and without the imperative marker)
- Loop-validation tests for the autodev routing change (`scripts/tests/test_builtin_loops.py`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser_unresolved.py` — extend with new Pattern E
  heuristic tests (Scope Boundaries co-occurrence scan); model on
  `TestCountOpenQuestionsInSections` (lines 173-241), the closest existing
  section-iteration precedent — no current test scans `## Scope Boundaries` prose at
  all [Agent 3 finding]
- `scripts/tests/test_autodev_loop.py` — add a
  `TestRecheckAfterSizeReviewDecisionUnresolvedBranch`-style class using the
  `action.index(...)` ordering idiom from `TestRecheckAfterSizeReviewDesignGateBranch`
  (lines 422-478) to assert the new `decision_unresolved` branch sits after the
  design-gate branch and before `readiness_stagnated` [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — the following existing `TestAutodevLoop`
  assertions on `recheck_after_size_review`'s single action string must be re-verified
  (not necessarily changed) once the new branch is spliced in, since they key off
  substring presence/ordering within that one action: `line 5061`
  (`--reason low_readiness`), `line 5072` (`outcome_gate_waived`), `line 5567`
  (`autodev-pre-deferral-remedy-fired` index < `--reason low_readiness` index — the new
  branch must not land between these two markers), `line 5606` (`autodev-inflight`)
  [Agent 3 finding]

### Documentation
- `docs/reference/API.md` if check-decidable's documented pattern set is enumerated there

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `count_enumerable_options()`'s precedence-tier description
  (~lines 898-917) needs the new Pattern E tier appended; the `deferred-triage`
  reason-code section (~line 3905) needs a clause noting `recheck_after_size_review`
  is now also a `decision_unresolved` source (the rank table itself is unchanged —
  `decision_unresolved` is already ranked) [Agent 2 finding]
- `docs/reference/CLI.md` (~lines 1616-1630) — `ll-issues check-decidable`'s
  description needs a note that Pattern E (un-preferenced directive + imperative
  marker) is now covered, not just formal option blocks [Agent 2 finding]
- `docs/reference/COMMANDS.md` (~lines 252, 254) — the `/ll:decide-issue` entry states
  "Only if Phase 3b also finds no clear winner does `decision_needed` stay `true`",
  which goes stale once Pattern E routes un-preferenced directives to full scoring
  without requiring a textually-identifiable winner up front [Agent 2 finding]
- `docs/guides/DECISIONS_LOG_GUIDE.md` (~line 198) — same stale "clear winner" framing
  as COMMANDS.md, needs the matching update [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — the "Diagram omissions" paragraph (~line 1045)
  currently lists three known `decision_unresolved`-writing routes and is already
  incomplete; add the new fourth route (`recheck_after_size_review`'s own
  decision-check branch). The adjacent "Ready-but-atomic earn-the-pass remediation"
  paragraph (~line 1051), which narrates this same cascade's branch order, also needs
  the new branch mentioned [Agent 2 finding]

## Acceptance Criteria

- [x] A fixture issue with `decision_needed: true` and a Scope-Boundaries passage of the
      shape "stamp it or move it to Out of scope — do not leave it unaddressed" is
      materialized into Option A/B blocks and scored to a winner by
      `/ll:decide-issue --auto`; `decision_needed` flips to `false` and a decisions-log
      entry is written. Verified two ways: (1) `skills/decide-issue/SKILL.md`'s Phase 3b
      Pattern E prose was added and structurally verified against 7 dedicated tests
      (`TestPattern3bDirectiveAlternatives`, `test_decide_issue_skill.py`) mirroring the
      ENH-2715 precedent; (2) a live `ll-issues check-decidable` run against a throwaway
      fixture confirmed the deterministic Pattern E heuristic — which encodes the exact
      same match rule the skill's Resolution Logic routes through steps 1-2 — correctly
      materializes-decidable on this shape. The full LLM `/ll:decide-issue --auto` skill
      run itself could not be re-exercised live in this session: Claude Code snapshots
      skill content at session start, so a mid-session `Skill` invocation served the
      pre-edit SKILL.md (no Pattern E) rather than the file on disk — invoking it would
      have validated stale instructions, not this change. A fresh session's live run is
      the remaining manual-verification step.
- [x] The same fixture without the imperative marker (bare "X or Y" prose) is NOT
      treated as decidable (guardrail holds). Verified by
      `test_bare_or_prose_without_imperative_marker_exit_one`
      (`test_ll_issues_check_decidable.py`) and the mirroring unit test in
      `test_issue_parser_unresolved.py`.
- [x] `ll-issues check-decidable` exits 0 on the first fixture and 1 on the second.
      Verified live via subprocess CLI invocation against both fixture shapes, plus a
      regression test for a real markdown line-wrap edge case discovered during that
      live check (`test_line_wrapped_marker_still_matches`) — the initial per-line-only
      marker search missed a decide-marker split across two lines by normal ~80-char
      wrapping; fixed by normalizing each 7-line window's whitespace before matching.
- [x] On the score-failing path (decide ran, `decision_needed` still `true`, scores
      below threshold), `recheck_after_size_review`'s deferral cascade defers the issue
      with reason `decision_unresolved` (not `readiness_stagnated`/`low_readiness`) —
      structural assertion in `test_autodev_loop.py`
      (`TestRecheckAfterSizeReviewDecisionUnresolvedBranch`, 4 tests covering branch
      presence, ordering relative to the design-gate/stagnation/low-readiness branches,
      and reuse of the existing `ll-issues show --json` payload).
- [x] `python -m pytest scripts/tests/` passes (17393 passed, 42 skipped; the one
      pre-existing failure, `test_no_prose_dependency_drift_in_repo` on unrelated
      `ENH-2923`/`ENH-2925`, predates this change and touches no file this issue
      modified).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-31_

**Readiness Score**: 95/100 → STOP — ADDRESS GAPS (Program Design hard override)
**Outcome Confidence**: 79/100 → MODERATE

### Gaps to Address
- `## Program Design` section is missing (Phase 1.6 hard override, ENH-2852). The
  project's Program Design gate is armed (`.ll/program-design-cutover.json`, sha
  19364ea9, dated 2026-07-30) and this issue was captured 2026-07-31 with no
  `program_design_not_applicable` flag, so the gate applies. Remedy: run
  `/ll:refine-issue` or `/ll:reconcile-issue` to populate `## Program Design` with
  concrete types/signatures/call path — the existing "Codebase Research Findings"
  section already contains most of the raw material (file:line anchors for
  `_OPTION_PATTERNS`, `locate_enumerable_options()`, `cmd_check_decidable()`, the
  autodev state graph) and mostly needs restructuring into the Program Design
  format, not new research. Alternatively, if this is judged genuinely trivial,
  set `program_design_not_applicable: true` in frontmatter — but given the
  three-file, cross-module scope here that exemption looks like a poor fit.

## Resolution

Implemented all three coupled changes:

1. `skills/decide-issue/SKILL.md` gained Provisional Pattern E under Phase 3b (with
   `reference.md` gaining the full rationale/worked example to stay within the
   ENH-494 500-line budget), materializing un-preferenced decision directives and
   routing them through steps 1-2 to full Phase 4-7 scoring.
2. `issue_parser.py` gained `_locate_directive_alternatives()` (Pattern E heuristic:
   imperative decide-marker + 2+ named alternatives within a whitespace-normalized
   ~7-line window, no stated preference, scoped to Scope Boundaries / Proposed
   Change / Proposed Solution / Open Questions), wired as a final precedence tier
   in `locate_enumerable_options()` — so `ll-issues check-decidable` inherits it
   with no new call site.
3. `autodev.yaml`'s `recheck_after_size_review` gained a `decision_needed` re-check
   between the design-gate branch and the `readiness_stagnated` backstop, deferring
   `decision_unresolved` (mirroring `record_decision_unresolved`'s idiom) instead of
   masking the gap as `readiness_stagnated`/`low_readiness`.

A live `ll-issues check-decidable` run against a throwaway fixture surfaced a real
bug during implementation: the initial per-line-only marker search missed an
imperative decide-marker split across two lines by ordinary markdown line-wrapping
(`"do not leave\n  it unaddressed"`). Fixed by normalizing each sliding window's
whitespace before matching, with a regression test added.

`.gemini/skills/decide-issue/SKILL.md` and `.kimi-code/skills/decide-issue/SKILL.md`
mirrors regenerated via `ll-adapt --host {gemini,kimi-code} --apply`. Docs updated:
`docs/reference/API.md`, `docs/reference/CLI.md`, `docs/reference/COMMANDS.md`,
`docs/guides/DECISIONS_LOG_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md`.

## Status

Done - implemented, tested, documented.

## Session Log
- `/ll:manage-issue` - 2026-07-31T23:53:32 - `6e8f5dbe-f90d-4902-8d9e-8d7187099c2b.jsonl`
- `/ll:ready-issue` - 2026-07-31T23:24:02 - `05ca38fc-0cca-4d56-b484-dfbaa0f469a6.jsonl`
- `/ll:confidence-check` - 2026-07-31T23:45:00Z - `ef66fe4f-db30-4923-b043-15925e4df28f.jsonl`
- `/ll:wire-issue` - 2026-07-31T23:19:03 - `30486698-58c2-4f28-bd8c-7264553c5a25.jsonl`
- `/ll:refine-issue` - 2026-07-31T23:08:01 - `2e47366d-72fe-4c0d-8776-184029693589.jsonl`
- `/ll:capture-issue` - 2026-07-31T21:54:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0da828f8-33c5-4a86-bdb0-74648c03bab5.jsonl`
