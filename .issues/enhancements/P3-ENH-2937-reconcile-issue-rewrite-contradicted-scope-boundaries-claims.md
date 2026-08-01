---
confidence_score: 95
outcome_confidence: 76
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 20
---
# ENH-2937: reconcile-issue: rewrite Scope Boundaries claims contradicted by its own findings

---
id: ENH-2937
type: ENH
priority: P3
status: open
captured_at: "2026-07-31T21:54:57Z"
discovered_date: 2026-07-31
discovered_by: capture-issue
relates_to: [ENH-2866, ENH-2936, ENH-2689]
program_design_not_applicable: true
---

## Summary

`/ll:reconcile-issue` (rewrite directive sections from own findings) can leave a
factually refuted `## Scope Boundaries` claim intact while updating other directive
sections in the same pass. In ENH-2866, Scope Boundaries claimed "no separate ll-sprint
stamp is needed" because `ll-sprint` delegates to `ParallelOrchestrator` — but the wiring
pass had already found that `_run_issue_with_wall_clock_timeout()` in `cli/sprint/run.py`
calls `process_issue_inplace()` directly and sequentially, a distinct unstamped code path
contradicting the claim verbatim. A reconcile pass (2026-07-31T03:03:58) touched
`## Proposed Change` (added ll-auto as a stamp site) yet never rewrote or flagged the
contradicted Scope Boundaries sentence. The contradiction then survived three
confidence-check passes, holding the Ambiguity subscore down.

## Motivation

A contradiction between a directive section's claim and the issue's own research findings
is exactly the staleness class reconcile exists to fix — and it is not a decision, so
`/ll:decide-issue` correctly won't touch it (see ENH-2936 for the decision-shaped
sibling gap). If reconcile skips it, no automation remedy remains: the contradiction
recurs in every confidence-check as capped Ambiguity, contributing to dishonest
`readiness_stagnated` deferrals. This was one of the two concrete blockers behind
ENH-2866's 56/100 outcome confidence.

## Current Behavior

Reconcile's rewrite scope is not an emergent habit — it is a **binding contract** in
`commands/reconcile-issue.md` ("Contract (read this first — it is binding)"): rewrite
ONLY `## Implementation Steps`, `## Acceptance Criteria`, and `### Files to Modify`;
everything else — explicitly including `## Scope Boundaries` — is "Preserve untouched —
never edit, reorder, or delete." So a `## Scope Boundaries` sentence whose justification
is directly refuted by content elsewhere in the same issue (wiring findings, Codebase
Research Findings) is left standing by design. This enhancement is therefore a
**contract amendment**, in tension with the skill's core promise ("without bulldozing
human prose") — it must be scoped tightly, not as general rewrite-eligibility.

## Expected Behavior

During a reconcile pass, claims in `## Scope Boundaries` (and other directive sections,
e.g. exclusion rationales) are checked against the issue's own recorded findings. When a
finding directly contradicts a claim's stated justification, reconcile either rewrites
the claim to match the evidence (e.g. "ll-sprint's `_run_issue_with_wall_clock_timeout()`
path calls `process_issue_inplace()` directly and needs its own stamp") or — if the
resolution requires a scope call rather than a factual correction — rewrites it into an
explicit decision-directive shape ("stamp it or exempt it — decide before
implementation") so the ENH-2936 decide path can pick it up. It must not leave the
refuted sentence standing verbatim.

## Proposed Solution

In `commands/reconcile-issue.md`:

1. Amend the binding contract: `## Scope Boundaries` (and any section asserting "X is
   not needed because Y") becomes **conditionally** rewrite-eligible — ONLY for a claim
   whose stated justification is directly contradicted by a recorded finding in the
   same issue. It is NOT added to the general rewrite list; unrefuted scope prose stays
   under "Preserve untouched."
2. Add an explicit contradiction check step: for each scope claim with a stated
   justification, verify the justification against Integration Map / wiring /
   Codebase Research Findings content in the same issue. On contradiction:
   - factual mismatch → rewrite the claim from the findings;
   - open scope call → rewrite as an imperative decision directive (ENH-2936's
     Pattern E shape) rather than silently keeping the stale claim, AND set
     `decision_needed: true` in frontmatter — without the flag, the decide pipeline
     never picks the directive up.
3. Carve out the contract line "Every rewritten claim must trace to an existing
   finding" for branch 2b: the decision-directive text is new imperative prose, not
   finding-traceable; the contract must explicitly permit it for this branch only.
4. Extend `--check` mode's staleness detection to include the contradicted-scope-claim
   class — autodev's plateau gate reaches reconcile via staleness detection, so if the
   contradiction check only runs in rewrite mode the gate never routes this shape to
   reconcile at all.
5. Log each rewrite in the reconcile output report (existing report template) so the
   change is auditable.
6. _Wiring Phase (added by `/ll:wire-issue`)_: sync the two doc files that
   paraphrase the old "exactly three sections, everything else untouched"
   contract — `docs/reference/COMMANDS.md`'s `### /ll:reconcile-issue` entry
   and `docs/guides/LOOPS_REFERENCE.md`'s "Post-spike reconcile plateau
   (ENH-2689)" paragraph — so the docs don't reintroduce the same
   stale-claim pattern this issue exists to fix.

**Sequencing**: implement after ENH-2936 (or at minimum after Pattern E's
imperative-marker phrasing is finalized), since branch 2b hardcodes examples of that
shape. Soft ordering only — the factual-rewrite branch is independent, so no hard
`blocked_by` edge (which would over-block this issue in autodev).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Sequencing is now clear**: ENH-2936 is `status: done` (completed
  2026-07-31T23:53:39Z, `confidence_score: 95`). The Pattern E imperative-marker
  machinery branch 2b needs to reuse already exists end-to-end:
  - Skill prose: `skills/decide-issue/SKILL.md:263-274` ("Provisional Pattern E —
    Un-preferenced decision directive"), whose scan scope already includes
    `## Scope Boundaries` (line 271-272).
  - Worked example matching this exact issue's shape: `skills/decide-issue/reference.md:6-27`
    (the ENH-2866 "stamp it or move it to Out of scope … do not leave it
    unaddressed" case).
  - Deterministic (non-LLM) mirror: `scripts/little_loops/issue_parser.py:449-524`
    — `_DECIDE_IMPERATIVE_RE`, `_PREFERENCE_MARKER_RE`,
    `_DIRECTIVE_ALTERNATIVES_SECTIONS` (includes `"Scope Boundaries"`), and
    `_locate_directive_alternatives()`.
  - `decision_needed: true` machine-visibility gate: `ll-issues check-decidable
    <ID>` (`scripts/little_loops/cli/issues/check_decidable.py`), the same probe
    `commands/refine-issue.md`'s own Option-Count Detection step already gates on.
  - Bold-label materialization template to reuse for branch 2b (`**Option A**:
    ... **Option B**: ...`) is defined at `skills/decide-issue/SKILL.md:288-304`
    and `commands/refine-issue.md:284-313`.
  - ENH-2936's own Scope Boundaries (lines 315-321 of that issue) explicitly
    disclaims resolving factual contradictions: "that is `/ll:reconcile-issue`'s
    charter — see ENH-2937" — confirming this issue is the intended completion
    of that hand-off, not overlapping work.
- **Important nuance for AC #3 (`--check` mode routing)**: `autodev.yaml`'s
  plateau gate (`check_reconcile_needed`, `scripts/little_loops/loops/autodev.yaml:1393-1447`)
  does **not** invoke `/ll:reconcile-issue --check` at all today — it uses a
  separate, purely numeric predicate (bit-identical Readiness score before/after
  a repair attempt, or a fresh-issue-below-threshold check per BUG-2803). It
  routes into `reconcile_current` (`autodev.yaml:1675-1691`), which always calls
  the full rewrite path, never `--check`. So extending step 4's staleness
  detection to the contradicted-Scope-Boundaries class makes `--check` mode
  correctly report `NEEDED`, but by itself does **not** change what triggers
  autodev to call reconcile in the first place — the plateau-gate predicate and
  reconcile's own `--check` staleness detector are two disconnected mechanisms.
  AC #3 as written ("plateau gate can route this shape to reconcile") should be
  read as "the `--check` mode signal becomes available for such routing," not as
  an automatic behavior change in `autodev.yaml` — wiring the plateau gate itself
  to consume `--check` mode is out of this issue's stated scope (`commands/reconcile-issue.md`
  changes only) unless explicitly added.
- **Closest existing contradiction-detection precedent**: `commands/refine-issue.md:545-559`
  (`### 6.5. Prose Dependency Gate`, FEAT-2849), which drives a
  `ll-issues format-check --format json` signal (`prose_dep_drift`/`stale_prose_dep`
  keys, implemented in `scripts/little_loops/cli/issues/format_check.py`) through
  a text-fix-or-edge-fix branch. No existing code path does within-issue
  section-vs-section contradiction detection outside reconcile's own step 4
  (`commands/reconcile-issue.md:104-112`), which is why this issue must extend
  that step directly rather than reuse an existing prose-drift checker.
- **Existing test file to extend**: `scripts/tests/test_reconcile_issue_command.py`
  is a string-slice/anchor-heading style suite (mirrors `test_refine_issue_command.py`)
  already reading both `commands/reconcile-issue.md` and `skills/ll-reconcile-issue/SKILL.md`
  (`COMMAND_FILE`/`SKILL_FILE` constants). Existing classes: `TestReconcileContract`
  (asserts the three-section rewrite list and preserve/in-place/source-of-truth
  language), `TestReconcileGuardAndOutput` (asserts the `reconcile_attempted`
  guard, `[reconcile]` correction category, `VALIDATED_FILE` requirement, session
  log append), `TestReconcileRegistered`. New assertions for this issue's
  contract amendment would follow the same `content = COMMAND_FILE.read_text()`
  + phrase-presence pattern — this answers the issue's own "Tests: TBD" item:
  the change is testable via this existing fixture-free string-slice suite, no
  new test infrastructure is needed.

## Scope Boundaries

- **In scope**: reconcile's rewrite-eligibility rules and contradiction check; prompt/
  instruction text changes; a fixture-based test if reconcile has one.
- **Out of scope**: making the scope decision itself (ENH-2936); changes to
  confidence-check scoring.

## Integration Map

### Files to Modify
- `commands/reconcile-issue.md` — contract at lines 41-64 (add Scope Boundaries as
  conditionally rewrite-eligible + carve-out from the "must trace to an existing
  finding" rule at lines 62-64 for branch 2b); contradiction-detection step 4 at
  lines 104-112 (extend to Scope Boundaries claims); `--check` mode step 7 at
  lines 139-147 (extend staleness verdict); Output Format at lines 149-184
  (`## SECTIONS_REWRITTEN` checklist at lines 158-161 and `[reconcile]` category
  definition at lines 178-181 both need a Scope Boundaries line/mention)
- `skills/ll-reconcile-issue/SKILL.md:3` — `description` frontmatter line
  currently reads "Rewrite an issue's Implementation Steps, Acceptance Criteria,
  and Files to Modify in place..." and must be updated to mention the
  conditional Scope Boundaries eligibility

### Dependent Files (Callers)
- `scripts/little_loops/loops/autodev.yaml:1675-1691` (`reconcile_current` state)
  — calls `/ll:reconcile-issue ${captured.input.output}` as a `slash_command`
  action, always full-rewrite mode, never `--check`. See the `--check` routing
  nuance under Proposed Solution → Codebase Research Findings.
- `scripts/little_loops/loops/autodev.yaml:1393-1447` (`check_reconcile_needed`
  state) — the plateau-gate predicate that triggers `reconcile_current`; does not
  itself read reconcile's staleness detector.

### Similar Patterns
- `commands/refine-issue.md:545-559` — Prose Dependency Gate, the closest existing
  claim-vs-ground-truth contradiction check (via `ll-issues format-check
  --format json`'s `prose_dep_drift`/`stale_prose_dep` keys).
- `skills/decide-issue/SKILL.md:263-334` — Pattern E detection + resolution logic
  + `decision_needed` frontmatter write, the template for branch 2b.

### Tests
- `scripts/tests/test_reconcile_issue_command.py` — existing string-slice/
  anchor-heading test file (mirrors `test_refine_issue_command.py`), reads both
  `commands/reconcile-issue.md` and `skills/ll-reconcile-issue/SKILL.md` via
  `COMMAND_FILE`/`SKILL_FILE` constants. Existing classes:
  `TestReconcileContract`, `TestReconcileGuardAndOutput`,
  `TestReconcileRegistered`. This is instruction-text-only work
  (`testable` judgment: yes, via this file's existing string-slice pattern —
  no new test infrastructure needed).

  _Wiring pass added by `/ll:wire-issue` — specific gaps found in this file:_
  - The module docstring (lines 1-8, "rewrites ONLY the three directive
    sections") and the `TestReconcileContract` class docstring (line 34,
    "exactly three directive sections") describe the invariant this issue
    breaks conceptually — no existing `assert` fails, but both docstrings need
    rewording to "three unconditional + one conditional" or similar so the
    test file's own self-description doesn't become the next stale claim
    [Agent 3 finding]
  - Model new assertions after `TestPattern3bDirectiveAlternatives`
    (`scripts/tests/test_decide_issue_skill.py:638-693`) — the closest existing
    "narrow, conditionally-eligible carve-out" test shape (ENH-2936's Pattern
    E). It uses a section-scoped helper (`_phase_text()`, bounding
    `content.index(...)`/`content.find(...)` between two headings) rather than
    searching the whole file — a new `TestReconcileScopeBoundariesEligibility`
    class should slice on the `"## Contract (read this first"` heading through
    the next `## Process` heading the same way, to avoid false positives from
    unrelated "Scope Boundaries" mentions elsewhere in the doc [Agent 3
    finding]
  - `--check` mode (step 7, `commands/reconcile-issue.md:139-147`) has **zero**
    existing test coverage in this file (`--check`/`CHECK_MODE`/`NEEDED`/
    `CLEAN` all zero matches) — AC #3's assertion will be the **first**
    `--check`-mode test here, not an extension of an existing one [Agent 3
    finding]
  - Model the `decision_needed: true` assertion after
    `test_decide_issue_skill.py:181`'s string-presence style
    (`assert "decision_needed: false" in phase7_text`) — reconcile-issue.md is
    prompt-only with no Python implementation, so this stays a doc-text
    assertion, not a frontmatter-mutation test [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — the `### /ll:reconcile-issue` entry (~line 280)
  paraphrases the current contract near-verbatim: "reconcile-issue closes that
  loop with a targeted, in-place rewrite of exactly those three sections; every
  other section ... is left untouched" — goes factually stale once Scope
  Boundaries becomes conditionally rewrite-eligible; the terser command-index
  line (~line 1029, "Rewrite stale Implementation Steps/AC/Files to Modify...")
  is lower-urgency but same staleness [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — the "Post-spike reconcile plateau
  (ENH-2689)" paragraph (near `check_reconcile_needed`, ~line 1051) says
  "a targeted in-place rewrite of just those three directive sections" — same
  stale "just those three" phrasing [Agent 2 finding]

Neither doc is machine-checked against `commands/reconcile-issue.md` (no test
asserts them in sync), so nothing fails mechanically, but both should be synced
in the same pass to avoid reintroducing the stale-claim pattern this issue
itself is about fixing.

## Impact

- **Priority**: P3 - Closes a hand-off gap between reconcile and decide (ENH-2936)
  that otherwise caps Ambiguity on every affected issue's confidence-check.
- **Effort**: Medium - Prompt/instruction-text-only change to `commands/reconcile-issue.md`
  and a `SKILL.md` description line, plus fixture-free string-slice test additions.
- **Risk**: Low - No Python implementation touched; the contradiction-check carve-out
  is narrowly scoped to Scope Boundaries claims with a stated, refutable justification.

## Status

**Open** | Created: 2026-07-31 | Priority: P3

## Acceptance Criteria

- [ ] Reconcile's contract marks Scope Boundaries as conditionally rewrite-eligible
      (contradicted-claim-only) and includes the claim-vs-findings contradiction check;
      unrefuted scope prose remains under "Preserve untouched."
- [ ] On the ENH-2866 shape (scope claim justified by delegation, refuted by a direct
      call path recorded in the same issue), a reconcile pass rewrites or
      decision-directive-izes the claim instead of leaving it verbatim; the
      decision-directive branch also sets `decision_needed: true`.
- [ ] `--check` mode reports a contradicted scope claim as a stale section (plateau
      gate can route this shape to reconcile).
- [ ] Rewrites are listed in the reconcile output report.
- [ ] `skills/ll-reconcile-issue/SKILL.md`'s `description` reflects the amended scope.

## Confidence Check Notes

**Gaps to Address** (hard override — STOP):
- `## Program Design` section is absent (`ll-issues format-check --format json` →
  `"missing": ["Impact", "Program Design", "Status"]`). The project's Program
  Design gate is armed (`.ll/program-design-cutover.json`, stamped
  2026-07-30/`19364ea9d...`) and this issue was captured 2026-07-31 — after the
  cutover, so it is not grandfathered. Remedy: populate `## Program Design` with
  concrete types/signatures/call path (run `/ll:refine-issue` or
  `/ll:reconcile-issue`), or set `program_design_not_applicable: true` in
  frontmatter if this prompt-only doc change is judged genuinely trivial for the
  gate's purposes.
- `## Impact` and `## Status` sections are also reported missing by
  `format-check`; lower-severity than the Program Design hard override but worth
  clearing in the same pass (likely `/ll:format-issue`).

## Session Log
- `/ll:ready-issue` - 2026-08-01T00:14:32 - `2777ec5f-44db-458f-9f82-ae3c2b08713b.jsonl`
- `/ll:confidence-check` - 2026-08-01T00:11:58Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/78ee6f4e-05b3-4708-b3b1-d24c8d5bdce0.jsonl`
- `/ll:wire-issue` - 2026-08-01T00:09:51 - `2bd25d1c-eb58-449a-8bbb-3061cb5df938.jsonl`
- `/ll:refine-issue` - 2026-08-01T00:02:07 - `c93dba9a-5c4f-4c21-b5dc-dbd2cf43a008.jsonl`
- `/ll:capture-issue` - 2026-07-31T21:54:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0da828f8-33c5-4a86-bdb0-74648c03bab5.jsonl`
