---
id: ENH-3280
type: ENH
title: decide-issue should propagate the selected option through the issue body
priority: P2
status: open
parent: EPIC-3290
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T15:46:10Z'
verify_verdict: NON_VALID
labels:
- decide-issue
- skills
- pipeline
- consistency
reconcile_attempted: true
blocked_by:
- BUG-3289
relates_to:
- BUG-3278
- BUG-3279
- BUG-3289
- ENH-3277
size: Large
depends_on:
- BUG-3278
---

# ENH-3280: decide-issue should propagate the selected option through the issue body

## Summary

`/ll:decide-issue` records a decision in three places — a `> **Selected:**` callout, a
`### Decision Rationale` subsection, and `decision_needed: false` — and changes nothing else. Prose
elsewhere in the issue that recommends or is conditioned on a *losing* option survives verbatim,
so the file ships with implementation steps instructing work that was decided against.

## Current Behavior

Phases 6–7 of `skills/decide-issue/SKILL.md` define exactly those three writes. There is no phase
that reconciles the rest of the document against the selection.

Observed on ENH-3277 (2026-08-21), where Option A was selected and the body still contained the
list below. **These have since been repaired by hand** — ENH-3277 is a record of the defect, not a
reproducer. Line numbers are as-observed, pre-repair; use `git show` on the commit that captured
this issue to see the original. A fresh reproducer fixture is needed (see *Tests*).

- `**Recommendation: Option C.**` (line 193) — a direct contradiction of the callout 35 lines above
- `*If Option C is taken*, the following elsewhere in this issue change and must be updated in the
  same pass:` (line 198) followed by an explicit three-item propagation checklist
- Implementation step 3b (line 588): *"Under the recommended **Option C** they become genuine
  drop-ins via `ll-config get --raw project.<key>`, which must land … before either YAML is
  touched"* — an imperative instruction to build the rejected option
- `## Scope Boundaries` (line 695): "No new production code — **conditional on the *DECISION
  REQUIRED* outcome**", still framing the boundary as unsettled
- `## Program Design` § Signatures (lines 718–725): two entries specifying the rejected `--raw`
  surface

Counts and scope statements keyed to the pre-decision option set also go stale ("nine files,
eleven inline reads, ten live" describes work Option A reduces to seven files).

## Expected Behavior

After `/ll:decide-issue` completes, the issue reads as a document that only ever advocated the
selected option. No recommendation names a loser, no implementation step instructs rejected work,
and no scope boundary is still framed as conditional on the decision. Rejected options survive
only as the alternatives they now are — in the option list and the Decision Rationale's
scoring table.

## Motivation

`/ll:decide-issue` sits at `refine → **decide** → wire → ready → manage`. `/ll:manage-issue` reads
the whole file, not just the Decision Rationale. A document whose imperative steps and its
decision callout disagree is a document that can be implemented wrongly by following it
faithfully — and the contradiction is *introduced* by the decision pass, since before it ran the
body was internally consistent.

That the propagation work is expected is not an inference: ENH-3277's own text (line 198) wrote
the checklist of what must change if a given option won. The skill had that list in front of it
and had no phase in which to act on it.

### Half of this already exists — `format-check`'s `unapplied_decision` (found 2026-08-21)

`issue_parser._unapplied_decision` (`:1449`) already **detects** this defect: it enumerates option
blocks, and reports rejected-option identifiers still present in directive sections as
`unapplied_decision` gaps. So the missing capability is narrower than "notice the problem" — it is
**acting on it at decision time**.

Two consequences for this issue:

1. **Reuse the detector rather than writing a second one.** Phase 7c should drive off the same
   rejected-identifier extraction, so detection and remediation cannot drift apart.
2. **The detector must be fixed first, or Phase 7c inherits its noise.** A propagation phase driven
   off a noisy signal rewrites *correct* prose to satisfy a false report — the worst failure mode
   available to a phase that edits arbitrary issue text.

   **Prerequisite re-pointed 2026-08-21 — the blocker is BUG-3289, not BUG-3279.** This bullet
   originally read "**BUG-3279 is a hard prerequisite**", filed when ENH-3277 emitted ~40 findings,
   nearly all false (`pytest`, `lint_cmd`, `ll-config get`), because the rejected option's block
   absorbed the section's trailing analysis prose. That span defect **has since been fixed** —
   BUG-3279's parser work landed as `f39a417e`, and BUG-3279's only remaining scope is two test
   methods that change no behavior. Blocking on it now gates this issue on test coverage while
   leaving the actual noise ungated.

   The surviving noise is **BUG-3289**'s: `_decision_identifiers` treats every backticked span of
   length >= 3 as option-discriminating, so shared subject vocabulary fires whenever the winner's
   own prose happens not to restate it. Measured post-`f39a417e`: **~23 surviving reports on
   ENH-3277** (`pytest`, `ProjectConfig`, `rn-refine`, `.ll/ll-config.json`, `to_dict()`,
   `oracles/code-run-gate.yaml`) plus two *new* ones on ENH-2692 for `final_score`, the issue's own
   shared subject. Every one of those is prose Phase 7c would be instructed to rewrite.

   `blocked_by` is therefore **BUG-3289**; BUG-3279 is demoted to `relates_to` as the issue that
   removed the first layer of this noise and measured the second.

   **A third issue moves this detector's output, and it is not declared anywhere** (added
   2026-08-21, epic review). **BUG-3285** tightens `_OPTION_HEADING_RE`, which feeds
   `_option_block_spans` → `_unapplied_decision`'s block set, and therefore its `sel_ids` /
   `rej_ids` / `spans[-1]`. Unlike BUG-3289's subtraction — which can only *remove* reports —
   a block-set change can move reports in **both** directions, including introducing new ones.
   Consequences for this issue:

   - **Not promoted to `blocked_by`.** Phase 7c's correctness requirement is that the report list
     is not dominated by false positives, which is BUG-3289's fix. BUG-3285 changes *which* blocks
     exist, which shifts the list without making it untrustworthy. Blocking on it would gate a P2
     behind an issue still owing two corpus differentials.
   - **But Implementation Step 4's fixture comparison must be taken against the tree this lands
     on.** If Phase 7c's expected-output oracle is captured before BUG-3285 lands and validated
     after, the diff includes BUG-3285's block-set movement and reads as a Phase 7c defect.

   > **Mechanism identified and measured 2026-08-22 (review pass) — stronger than "shifts which
   > blocks exist".** On a phantom-carrying document `_unapplied_decision` returns **`[]`
   > outright**, not a shifted list. `_option_label("**Option A evidence**")` yields `A`, which
   > collides with the real Option A, so the selected-block resolution
   > `matching = [i for i, (_, _, heading) in enumerate(spans) if _option_label(heading) == label]`
   > fails its `if len(matching) != 1: return []` guard (`issue_parser.py:1568-1571`). The phantom
   > does not add a false report — it **suppresses every true one**, and with it the whole
   > blocking `unapplied_decision` gap class on that issue. Filed as BUG-3285 consequence 4.
   >
   > Consequences for this issue, beyond the baseline caveat above:
   >
   > - **Phase 7c silently no-ops today on exactly the documents BUG-3285 repairs.**
   >   `_unapplied_decision` is named here (`:315`) as "the sole existing entry point Phase 7c
   >   drives"; on a phantom-carrying issue it yields nothing to drive. Measured: `ENH-2967`
   >   `0 → 5` reports and `BUG-1484` `0 → 3` once BUG-3285 lands.
   > - **Implementation Step 4's oracle cannot be captured on a phantom-carrying fixture at all
   >   before BUG-3285 lands** — not "the diff will include movement", but "the detector produces
   >   nothing to diff". Choose fixtures whose option letters are already unique, or capture the
   >   oracle post-BUG-3285.
   > - Still **not** promoted to `blocked_by`, for the reason already given: this changes how much
   >   the detector sees, not whether what it reports is trustworthy, which remains BUG-3289's.
     Name the baseline commit in the fixture's docstring, the way BUG-3278 assertion (c5) does for
     the same function. See BUG-3285 § *Second blast radius*.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

- **Status update (2026-08-23): the entire prerequisite chain discussed above has landed.** `BUG-3289` (subtract shared-subject vocabulary from `_unapplied_decision`, commit `e3ffd49ce`), `BUG-3285` (widen `_option_block_spans`'/`_OPTION_HEADING_RE` matching, probe Pattern E directives), `BUG-3279` (fix `locate_enumerable_options` giving the final option every remaining line), and `BUG-3278` (gate `decision_needed` clear on a decision-group residual probe, adding the `is_group_resolved`/`check-unresolved-decisions` machinery to Phase 7b) are all `status: done` as of this pass — confirmed via `ll-issues show <ID>` and `git log --all --grep`. `blocked_by: BUG-3289` in this issue's frontmatter is therefore resolved per the status-based resolution rule (only `done`/`cancelled` resolve `blocked_by`); this issue is no longer blocked on prerequisite work. See the Program Design findings above for what BUG-3289's and BUG-3278's landed changes actually did to `_unapplied_decision` and Phase 7's structure, since neither landed as a pure no-op relative to what this issue's Proposed Solution assumed.

## Proposed Solution

Add **Phase 7c: Propagate Selection** after Phase 7b, before the session log.

Scan the full file (not just `## Proposed Solution`) for text keyed to the option set and rewrite
it to the decided state:

1. **Recommendation markers naming a loser** — `Recommendation: <X>`, `Recommended: <X>`,
   `we should take <X>` where `<X>` is not the winner. Rewrite to name the selection, or strike and
   fold into the Decision Rationale as a "considered and rejected" line.
2. **Conditional blocks keyed to an option** — `If <X> is taken, …`, `Under <X>, …`,
   `conditional on the DECISION REQUIRED outcome`. For the winner: unwrap the condition and state
   it declaratively. For a loser: delete, or demote to a parenthetical under the rejected option.
3. **Imperative steps referencing a loser** — any `## Implementation Steps` item naming a rejected
   option. These are the highest-risk instances (an implementer executes them) and should be
   rewritten to the winner's shape or marked not-applicable, never left as-is.
4. **Sections the issue itself flags** — when the body contains an explicit propagation checklist
   for the selected option, apply it item by item and report each edit.

Report every propagated edit in Phase 9 with its line reference, so the pass is auditable rather
than silent.

**Bounded scope.** Phase 7c rewrites prose *keyed to the option set only*. It does not restate
counts, re-derive scope, or re-run analysis — a decision pass must not become a refine pass. Where
propagation implies a downstream change it cannot safely make (stale counts, an untouched
`## Scope Boundaries` figure), it flags the location in the report rather than editing.

**Idempotency.** Mirroring Phase 7a: if `### Decision Rationale` already exists and no
loser-keyed prose remains, log `✓ Phase 7c: no unpropagated references — skipping` and write
nothing.

**Non-empty re-check (added 2026-08-21, epic review).** The post-pass `format-check` re-run may
legitimately still report `unapplied_decision` entries — the bounded-scope rule above allows
flag-not-edit dispositions. That outcome is **not a failure and must not retry**: Phase 7c
carries the surviving reports into Phase 9's flagged-but-not-edited block and proceeds to
Phase 8, mirroring Phase 7b's report-rather-than-loop discipline (BUG-3278). Without this branch
the Call Path's "confirm `unapplied_decision` is now empty before proceeding" reads as a gate
with no defined exit.

## Integration Map

### Files to Modify

- `skills/decide-issue/SKILL.md` — new Phase 7c; Phase 9 report gains a propagated-edits block
- `skills/decide-issue/reference.md` — the Phase 9 output template lives here

> ⚠ **Line budget — updated 2026-08-23; BUG-3287 and BUG-3278 have both landed and already
> consumed most of the headroom.** `skills/decide-issue/SKILL.md` is **494 lines** against the hard
> **500-line** cap enforced by `TestSkillLineLimit`
> (`scripts/tests/test_enh494_skill_companions.py:73-86`) — **6 lines left**. Phase 7c as specified —
> four rewrite categories with trigger patterns and per-category disposition, the bounded-scope
> statement, and the idempotency rule — cannot fit.
>
> **Required shape:** `SKILL.md` gets the Phase 7c *heading, the imperative step sequence, the
> idempotency guard, and a `See [reference.md](reference.md) for the rewrite-category catalogue`
> pointer* — target **≤ 15 lines**, tighter still now that only 6 lines remain. The four-category
> catalogue, its trigger patterns, and the worked dispositions move into `reference.md` (**219
> lines** now, already this skill's companion — grown in part from BUG-3278's own additions:
> `## Phase 7a Marker-Placement Matrix, per decision-group tier (BUG-3278)` and `## Phase 3b Step 4
> Exit-Code Disposition (BUG-3278)`). `test_enh494_skill_companions.py::test_skill_links_to_companion`
> enforces that the pointer exists. See EPIC-3290 § *Shared constraint — the decide-issue SKILL.md
> line budget*, which also notes that the extraction pass may land as a standalone preparatory commit
> rather than inside any one child — if it does, this issue inherits the headroom and only needs the
> budget check.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/confidence-check/SKILL.md` — Phase 1.8 reads the `unapplied_decision` format-check gap key into a `DECISION_GAP` variable and reports it as advisory (line ~594); once Phase 7c ships, `unapplied_decision` should typically already be empty by the time confidence-check runs on a decided issue — no code change required, but worth re-verifying Phase 1.8's advisory framing still reads correctly against the new steady state [Agent 1 finding]
- `skills/confidence-check/rubric.md` — references the `> **Selected:**` callout when describing gap-reason advisory detail (line ~323) [Agent 1 finding]
- `skills/wire-issue/SKILL.md` (this skill) — reads `decision_needed`/`### Decision Rationale` as a pipeline gate (line ~489); unaffected by Phase 7c's prose rewrites, no change needed [Agent 1 finding]
- `skills/manage-issue/SKILL.md` — halts to `/ll:decide-issue` on the `decision_needed` frontmatter gate (line ~173); unaffected, no change needed [Agent 1 finding]

### Tests

- A fixture whose body recommends the losing option: assert the marker is rewritten and reported
- A fixture with an `If <loser> is taken` conditional block: assert it is removed or demoted
- A fixture with an implementation step naming the loser: assert the step no longer instructs the
  rejected work
- An already-propagated fixture: assert a second run writes nothing (idempotency)
- `_unapplied_decision` test coverage: `scripts/tests/test_issue_parser.py:5093`, class
  `TestUnappliedDecision`, using an inline `_issue()` builder helper rather than
  on-disk `.md` fixtures — no fixture file for this detector exists under
  `scripts/tests/fixtures/issues/`
- A live-corpus sweep test already exists and documents a known precision limit:
  `scripts/tests/test_issue_parser.py:5604`, `TestUnappliedDecisionLiveCorpusSweep`
  (`test_corpus_sweep_does_not_crash` at `:5626`)
  — asserts `_unapplied_decision` never raises across `.issues/`, and is explicitly
  report-only/non-blocking due to a high false-positive rate on the real corpus. **That residual
  noise is BUG-3289's, not BUG-3279's** — this issue's own `blocked_by`.
  > ⚠ **Two corrections, 2026-08-21.** (i) The anchor `:4968` was stale; actual is `:5063`/`:5085`
  > (the same `f39a417e` drift). (ii) This bullet read *"this is the noise BUG-3279 is fixing"*,
  > which contradicts this issue's own *Motivation* — BUG-3279's span fix **landed** as `f39a417e`
  > and the prerequisite was re-pointed to **BUG-3289**, which is what `blocked_by` now declares.
  > Every remaining reference in this issue to BUG-3279 as the noise fix is stale by the same
  > argument.
- `decide-issue`'s own test file, `scripts/tests/test_decide_issue_skill.py`, tests SKILL.md as
  prose/documentation (the skill has no executable binary) via a `_phase_text()` slice-and-assert
  helper reused across five phase test classes (e.g. lines 233-238, 290-295, 402-406). A Phase 7c
  test class should follow this same slicing convention against the new `### 7c` heading rather
  than attempting to execute the skill.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_decide_issue_skill.py` — the best-fit existing template for a new Phase 7c
  test class is `TestPattern3bDirectiveAlternatives` (`:649-705`: class docstring naming the
  driving issue, a `_phase_text()` helper, narrowly-scoped `test_*` methods each asserting one
  documented element). For the outer slice specifically, since Phase 7c nests under the existing
  `## Phase 7: Apply Changes` heading alongside `### 7a`/`### 7b`, follow
  `TestDecisionNeededFrontmatterUpdate` (`:183-208`), which already slices the whole
  `## Phase 7:` → `## Phase 8:` span and asserts on `### 7b`-scoped content without a dedicated
  inner slice — no test in this file currently narrows below an outer Phase-level slice to a
  lettered sub-heading, so a `### 7c`-scoped inner slice would be new [Agent 3 finding]
- `scripts/tests/fixtures/issues/` — no fixture models the two-option
  (`**Option A**`/`**Option B**` + `> **Selected:**` callout + stale directive-section prose)
  shape Phase 7c's four test fixtures need. Closest precedents: the before/after pairing
  convention in `BUG-3025-pre-review-original.md` / `BUG-3025-reviewed-uncorrected.md` (matches
  the idempotency fixture's run-once-vs-run-twice shape), and `FEAT-398-decide-empty-proposed.md`
  for how a decide-issue-specific fixture is wired into a test class (`FIXTURE = Path(...)`,
  existence check, content assertions — see `TestFEAT398Snapshot`,
  `test_decide_issue_skill.py:496-527`) [Agent 3 finding]
- `scripts/tests/test_issue_parser.py:4912-4929`,
  `test_all_blocks_carry_selected_line_resolves_single_winner` — the one test in
  `TestUnappliedDecision` that pins `_unapplied_decision`'s reason string with `==` rather than
  substring containment (`reasons == ["Implementation Steps still specifies \`check_refine_limit\`
  (rejected option)"]`). This is the test most likely to break if BUG-3279's fix changes the
  `"{section} still specifies \`{identifier}\` (rejected option)"` template — and Phase 7c's own
  string-parsing logic depends on that exact template staying aligned with this test [Agent 3
  finding]

**Flagged, not resolved** — ENH-3277 pre-repair reproducer (Implementation Step 4): verified via
`git log --all --diff-filter=A -- "*ENH-3277*"` plus a search of all three
`refs/ll/abandoned/BUG-001-*` refs that no git revision — committed or abandoned — contains the
"Recommendation: Option C" pre-repair text. The hand-repair described in this issue's Current
Behavior section was never committed in its pre-repair form, so Implementation Step 4's `git show`
instruction has no target to run against. The reproducer fixture must be hand-authored from this
issue's own quoted Observed Behavior text (lines 42-51 above), not reconstructed from history.

### Documentation

- `skills/decide-issue/reference.md` — Phase 9 output report template

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/DECISIONS_LOG_GUIDE.md` — two stale-after-this-change spots: the pipeline diagram
  (lines 168-194) enumerates decide-issue's actions without mentioning propagation, and the
  "Sample output" block ends with an explicit claim (line 262) that `CHANGES APPLIED` "reports only
  these three issue-file edits" — false once Phase 7c adds a fourth reported edit class
  [Agent 2 finding]
- `docs/reference/COMMANDS.md` — the `/ll:decide-issue` section's "Frontmatter write-back"
  paragraph (~line 256) describes only the Phase 7a/7b idempotency rule; needs a sentence covering
  Phase 7c's behavior and its own idempotency rule [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

> ⚠ **Every `issue_parser.py` anchor in this section was the pre-`f39a417e` set and has been
> refreshed in place (2026-08-21).** EPIC-3290 refreshed the shared anchors on 2026-08-21 but this
> issue did not get the pass, so its entire *Program Design* § Signatures and Call Path were running
> on stale numbers. Corrected: `_unapplied_decision` 1392→**1449**, reason template 1513→**1571**,
> `check_format_gaps` 1114→**638**, `_option_block_spans` 1371→**1405**, `_selected_option_title`
> 1322→**1332**, `_option_label` 1335→**1345**, `_decision_identifiers` 1341→**1351**. Verified
> correct and unchanged: `_DECISION_DIRECTIVE_SECTIONS` `:1302-1308`, JSON key `:594`,
> `has_blocking_gaps` `:556`.

- `_unapplied_decision(content: str) -> list[str]` (`scripts/little_loops/issue_parser.py:1449`) returns only formatted reason strings — `"{section} still specifies \`{identifier}\` (rejected option)"` (`:1571`) — not a structured `(section, identifier)` tuple. Phase 7c must parse this string to recover the section name and identifier, since no structured API exists.
- Surfaced today via `ll-issues format-check <ID> --format json` → `unapplied_decision` key (`scripts/little_loops/cli/issues/format_check.py:672-685`, JSON serialization at `issue_parser.py:594`) — a skill-authored Phase 7c can consume this over subprocess without new Python glue.
- `unapplied_decision` is **not** in the `--fix`/`--apply` dispatch list (`format_check.py:98-113`, which covers `prose_dep_drift`, `duplicate_findings_block`, `duplicate_heading`, `empty_provenance_stub`, `template_placeholders`) — there is no existing auto-repair path; Phase 7c must perform its own edits.
- `check_format_gaps` (`issue_parser.py:638`) is the sole caller of `_unapplied_decision`; `unapplied_decision` is a **blocking** (non-advisory) gap class on `FormatGaps.has_blocking_gaps` (`issue_parser.py:556`) — so the pre-fix state already fails `format-check`, independent of this issue.
- `_DECISION_DIRECTIVE_SECTIONS = ("Proposed Solution", "Program Design", "Implementation Steps", "Files to Modify", "Acceptance Criteria")` (`issue_parser.py:1302-1308`) is the closed list of sections `_unapplied_decision` scans — Phase 7c's sweep scope should match this list, not invent a broader one.
- Supporting extraction helpers Phase 7c may need for finer-grained matching beyond the formatted-string output: `_option_block_spans` (`:1405`), `_selected_option_title` (`:1332`), `_option_label` (`:1345`), `_decision_identifiers` (`:1351`) — all private module functions with no CLI wrapper; only reachable in aggregate via `_unapplied_decision`'s output.

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **Correction (pattern-finder, 2026-08-21): `reconcile-issue` is not the only in-place-prose-rewrite precedent.** `decide-issue`'s own existing Phase 3b already rewrites prose in place: "Materialize alternatives, if not already structured (ENH-2715)" (`skills/decide-issue/SKILL.md:284-293`) converts informal `- (a) ...`/`- (b) ...` bullets or an Open-Questions-named alternative into structured `**Option A**`/`**Option B**` blocks, and the skill text names this itself as "additive/rewrite-in-place of the same prose already matched" (`:292`). Two further in-place-rewrite precedents exist outside issue-markdown prose specifically: `skills/improve-claude-md/SKILL.md:89,174` (rewrites `CLAUDE.md` via Edit) and `skills/simplify-loop/SKILL.md:204` ("4b. Rewrite the parent", verified against a reachable-terminal diff at `:92-98`). `wire-issue` and `refine-issue` remain confirmed append-only/marker-only (`skills/wire-issue/SKILL.md:427`, `refine-issue.md`'s marker-only carve-out) — the "Bounded scope" analogy to `reconcile-issue` in this issue's Proposed Solution still holds, but the "no existing skill rewrites prose except reconcile-issue" framing above is inexact; Phase 7c has an in-skill precedent (Phase 3b) as well as the cross-skill one already cited.
- **Audit-trail heading conventions (pattern-finder, 2026-08-21):** two heading families coexist and are not interchangeable. `## CHANGES APPLIED` (decide-issue `reference.md:125`, format-issue `templates.md:318`, review-sprint `review-sprint.md:336`) varies its bullet shape per command (decide-issue: tri-state `[Action | Skipped (idempotent)]`; format-issue: grouped `###` sub-headings; review-sprint: flat `Pruned:`/`Removed:`/`Added:`/`Revalidated:` lines). `## CORRECTIONS_MADE` (reconcile-issue `:288-296`, ready-issue `:463-476`) shares a tighter `[category-tag] description` bullet convention and both end with an explicit `[Or "None" if no corrections needed]` empty-state line. Phase 7c's report block should pick one family deliberately rather than inventing a third shape — decide-issue already owns `## CHANGES APPLIED` in `reference.md:125`, so extending that heading with a new propagated-edits bullet group is the lower-friction fit.

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

- **Anchor refresh (2026-08-23) — supersedes the 2026-08-21 anchor correction above; the file has drifted again since that pass.** `skills/decide-issue/SKILL.md` is now **494 lines** (was 493) against the 500-line `TestSkillLineLimit` cap — headroom is now **6 lines**, one tighter than the "7 lines left" the Line-Budget callout above cites. `skills/decide-issue/reference.md` is now **219 lines** (was cited as "144 lines today") — the growth is attributable at least in part to two BUG-3278-landed sections not present at the 144-line snapshot: `## Phase 7a Marker-Placement Matrix, per decision-group tier (BUG-3278)` (`reference.md:67-91`) and `## Phase 3b Step 4 Exit-Code Disposition (BUG-3278)` (`reference.md:93-99`), together ~32 of the ~75-line delta — some additional growth exists elsewhere in the file beyond these two sections.
- **Phase 7c insertion point, read directly from the current file:** `## Phase 7: Apply Changes` at `SKILL.md:381`, `### 7a: Annotate Issue File` at `:385` (ends `:403`), `### 7b: Update Frontmatter` at `:405` (its `ll-issues decisions add` bash block closes at `:437`), then a blank line, `---` at `:439`, blank line, `## Phase 8: Append Session Log` at `:441`. A new `### 7c` would be written starting at line 438, pushing the `---`/Phase 8 down.
- **`docs/guides/DECISIONS_LOG_GUIDE.md`**: the pipeline-diagram fence now spans lines 168-196 (issue's Documentation section cites 168-194 — close, off by the closing fence line); the "reports only these three issue-file edits" sentence is now at **line 264**, not the cited line 262 (262 is now the closing fence of the preceding sample-output block).
- **`docs/reference/COMMANDS.md`**: `### /ll:decide-issue` section header at line 245; the "Frontmatter write-back (conditional, BUG-3278)" paragraph is at line 256 — this one still matches the issue's citation exactly.

### Conventions in Force
- Lettered sub-phases (`### 7a`, `### 7b`, ...) nest under one `## Phase N` parent, each a discrete ordered write — evidence: `skills/decide-issue/SKILL.md:399-424` (7a/7b under Phase 7) and `skills/wire-issue/SKILL.md:336-452` (8a/8b/8c under Phase 8). No skill in the repo goes past a `c` suffix; Phase 7c would be the first `c`-level sub-phase in `decide-issue`.
- Idempotency guards are phrased "**Idempotency [rule]**: if `<condition>`, skip the write and log `<marker> <message>`" — evidence: `skills/decide-issue/SKILL.md:409` (uses `⚠` for "content already present") and `:424` (uses `✓` for "flag already at target value"). The two symbols are not interchangeable within this skill; ENH-3280's own "Mirroring Phase 7a" points at the `⚠` form since Phase 7c is a content-presence check, not a flag check.
- `/ll:reconcile-issue` (`commands/reconcile-issue.md:46-117`) is the only existing precedent in this codebase for rewriting (not just appending to) issue prose, and it bounds itself with an explicit rewrite allowlist, a preserve-untouched list, and a rule that "every rewritten claim must trace to an existing finding" (`:112-117`). Every other prose-touching skill (`wire-issue`, `refine-issue`) is append-only or marker-only. Phase 7c's "Bounded scope" language should be understood as adopting this same shape, not a novel one.
- Audit-trail reporting of edits made during a rewrite pass uses a dedicated report subsection, one bullet per edit, each citing its driving evidence — evidence: `commands/reconcile-issue.md:288-296` (`## CORRECTIONS_MADE`, `[reconcile]`-tagged bullets citing a quoted finding) and `skills/decide-issue/reference.md:125-128` (`## CHANGES APPLIED`, fixed-choice bullets). No existing report block cites literal `file:line` per edit — reconcile-issue's closest analog cites step numbers, not line numbers; ENH-3280's "with its line reference" requirement has no direct precedent to copy.

## Program Design

### Signatures

- `_unapplied_decision(content: str) -> list[str]` — the sole existing entry point Phase 7c drives
  off; returns formatted reason strings only, one per `(section, identifier)` pair, never a
  structured tuple (`scripts/little_loops/issue_parser.py:1449`)
- `check_format_gaps(content: str) -> FormatGaps` — sole caller of `_unapplied_decision`; invoked
  from `ll-issues format-check <ID> --format json`, which serializes the list under the JSON key
  `"unapplied_decision"` (`issue_parser.py:638`, CLI at `scripts/little_loops/cli/issues/format_check.py:672-685`,
  JSON key at `issue_parser.py:594`) — the subprocess-callable surface Phase 7c uses; no new Python
  glue is required
- `_DECISION_DIRECTIVE_SECTIONS: tuple[str, ...]` — the closed set of section names
  `_unapplied_decision` scans; Phase 7c's sweep scope must match it, not invent a broader one
  (`issue_parser.py:1302-1308`)

### Call Path

`/ll:decide-issue` Phase 7c (new `### 7c` under `## Phase 7: Apply Changes`,
`skills/decide-issue/SKILL.md:399`, inserted after `### 7b` at `:439`) runs after Phase 7a/7b have
already written the callout and frontmatter, so `_unapplied_decision`'s own precondition (a
resolvable `> **Selected:**` callout) is satisfied by the time Phase 7c fires ->
shells out to `ll-issues format-check <ID> --format json` -> `cmd_format_check`
(`format_check.py:476`) -> `check_format_gaps` (`issue_parser.py:638`) -> `_unapplied_decision`
(`issue_parser.py:1449`) -> JSON `unapplied_decision` list returned to the skill -> skill parses
each `"<Section> still specifies \`<identifier>\` (rejected option)"` string to locate the
identifier's occurrence in that section -> Edit tool rewrites/demotes/strikes the matched prose
per the four categories in `## Proposed Solution` -> skill re-invokes `format-check`: an empty
`unapplied_decision` list confirms full propagation; a non-empty list (flag-not-edit residuals)
is carried into Phase 9's flagged-but-not-edited block — either way flow proceeds to Phase 8,
with no retry (see *Proposed Solution → Non-empty re-check*).

### Decision Rules

The four rewrite categories (recommendation markers, conditional blocks, imperative steps, explicit
checklists) are already fully specified with their trigger patterns and per-category disposition in
`## Proposed Solution` above — no separate decision table is needed here. The one rule not yet
pinned down: the **input** to those categories is `_unapplied_decision`'s per-identifier findings
(closed section set above), not a fresh full-text scan — Phase 7c only acts where the detector
already reports a hit. Escape hatch: Phase 7c's own idempotency check (`## Proposed Solution`,
"Idempotency") — skip and log if a post-7a/7b `format-check` shows `unapplied_decision` already
empty.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **Correction (pattern-finder, 2026-08-21): a `c`-level lettered sub-phase already exists in the repo, and one skill goes further.** `skills/wire-issue/SKILL.md` already has `### 8a: Integration Map Updates` (:342), `### 8b: Implementation Steps Updates` (:400), and `### 8c: Preservation Rule & Contradiction Carve-Out` (:425) — a `c`-level sub-phase under Phase 8. `skills/rename-loop/SKILL.md` goes further still: `### 5a. File rename` (:97) through `### 5e. Documentation` (:140), five lettered sub-steps. `decide-issue` itself already has a compound sub-phase one level past a plain letter: `### Phase 3b-i: Skip resolved questions` (`skills/decide-issue/SKILL.md:196`). So Phase 7c would not be "the first `c`-level sub-phase" in the repo, nor in `decide-issue` specifically once the 3b-i precedent is counted — the "Conventions in Force" and this section's framing of that claim should be read as refuted, not merely unconfirmed.
- **Test-slicing precedent (pattern-finder, 2026-08-21):** the closest existing precedent for a test that isolates a lettered/compound sub-heading (rather than only the outer `## Phase N` span) is `TestPhase3bResolvedFilter` (`scripts/tests/test_decide_issue_skill.py:287-300`), which slices from `content.index("## Phase 3b: Inline Decision Scan")` then asserts `"Phase 3b-i" in text` inside that slice. This is closer to what a Phase 7c test needs than the outer-slice-only precedent (`TestDecisionNeededFrontmatterUpdate`) this issue's Tests section currently cites as the template — no existing test binds a start-heading (`### 7a`) and end-heading (`### 7b`) pair to isolate a single lettered sub-phase's own span; `TestPhase3bResolvedFilter`'s single-heading-start-plus-substring-search shape is the nearest analog.
- **Analyzer confirmation, no correction (2026-08-21):** all five points in this section and Codebase Research Findings above were independently re-verified against source and are accurate as stated, including the exact `⚠`/`✓` idempotency-marker distinction (`skills/decide-issue/SKILL.md:409` vs `:424`) and the `--fix`/`--apply` dispatch table exclusion (`scripts/little_loops/cli/issues/format_check.py:98-108`). One precedent is stronger than cited: `skills/confidence-check/SKILL.md:138` (`FC_JSON=$(ll-issues format-check {{issue_id}} --format json 2>/dev/null || true)`) is the same `--format json` + `2>/dev/null || true` shell-out idiom this issue's Call Path already assumes for Phase 7c, not merely an analogous one.

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

- **Anchor refresh (2026-08-23) — supersedes the 2026-08-21 anchor table above; the file drifted again since that pass.** Current defs in `scripts/little_loops/issue_parser.py`: `has_blocking_gaps` `:580` (was cited `:556`), `FormatGaps.to_dict()` `:591-620` with the `"unapplied_decision"` JSON key at `:618` (was cited `:594`), `check_format_gaps` `:663` (was `:638`), the `_unapplied_decision` call site `gaps.unapplied_decision.extend(...)` at `:1164`, `_DECISION_DIRECTIVE_SECTIONS` `:1352-1358` (was `:1302-1308`, membership unchanged), `_selected_option_title` `:1382` (was `:1332`), `_option_label` `:1395` (was `:1345`), `_decision_identifiers` `:1401` (was `:1351`), `_option_block_spans` `:1474-1515` (was `:1405`), `_unapplied_decision` `:1518-1659` (was `:1449`). `ll-issues format-check` call chain: `cmd_format_check` now `format_check.py:484` (was cited `:476`); single-issue JSON emission at `format_check.py:690-693`; `--all` sweep emission at `:618`.
- **`_unapplied_decision`'s signature and return shape are confirmed unchanged** despite the anchor drift — still `(content: str) -> list[str]`, still one formatted reason string per hit via `reasons.append(f"{section_name} still specifies \`{identifier}\` (rejected option)")` at `issue_parser.py:1658`. The issue's existing Signatures entry is accurate in content, only its anchor was stale.
- **BUG-3289's landed fix added a new input surface, not a signature change.** It introduced `_shared_subject_identifiers(content: str) -> set[str]` (`issue_parser.py:1406-1422`), which reads the frontmatter `title` (falling back to the H1) plus `## Summary` — content **outside** `_DECISION_DIRECTIVE_SECTIONS`. It's consumed inside `_unapplied_decision` as a third subtraction term: `discriminating = (rej_ids - subsumed) - sel_ids - shared_ids` (`issue_parser.py:1616-1617`), layered after a pre-existing BUG-3295 `subsumed` containment exclusion (`:1599-1611`). So `_unapplied_decision`'s output now depends on title/Summary content in addition to the closed directive-section set; Phase 7c's own sweep scope (bounded to `_DECISION_DIRECTIVE_SECTIONS`) is unaffected, but this is a new fact about what the detector it drives off actually reads.
- **BUG-3278's `DecisionGroup`/`is_group_resolved` machinery (`issue_parser.py:2823-2973`: `_iter_decision_groups` `:2823`, `is_group_resolved` `:2912`, `locate_unresolved_decisions` `:2956`) and `_unapplied_decision` are two independent systems that do not share state.** `_unapplied_decision` has no per-group scoping parameter — it always scans the entire `## Proposed Solution` section as one decision: it collects all option spans via `_option_block_spans` (`:1531`), finds the first `> **Selected:**` callout in the whole section via `_selected_option_title` (`:1581`, first-occurrence intentional per its docstring `:1382-1392`), and requires exactly one span whose label matches (`issue_parser.py:1588-1591`: `if len(matching) != 1: return []`). On a document with multiple sibling decision groups (BUG-3278's own reason for existing), this document-grain design means Phase 7c — if it drives strictly off `_unapplied_decision`'s output — is reading "all directive sections vs. one globally-first-resolved selection," not "this specific group Phase 3b/7a just resolved." Nothing in the landed BUG-3278 work made `_unapplied_decision` group-aware; it remains the original ENH-3256 identifier-diff detector, unmodified in this respect. There is also a second, independent option-boundary implementation now in the file: `_option_block_spans` (used by `_unapplied_decision`) vs. `_decision_groups_in_body`/`DecisionGroup` (used by the group-resolution gate) — these can disagree about span boundaries and therefore about what "resolved" means for the same document.
- **Idempotency-marker convention has two distinct shapes, both now landed and both live in Phase 7 (pattern-finder, 2026-08-23):** Phase 7a's guard is headed `**Idempotency rule (per-group, BUG-3278)**:` and guards a content-presence/group-resolution check with `⚠` (`SKILL.md:399-403`: "skip the annotation write only when **the selected group** is already resolved per `is_group_resolved` ... Log `⚠ Decision already annotated for this group — skipping annotation (idempotent)`"). Phase 7b's guard is headed bare `**Idempotency**:` (no BUG tag, no "per-group") and guards a flag-already-at-target-value check with `✓` (`SKILL.md:422`: "if `decision_needed` is already `false`, skip the write and log `✓ decision_needed already false — no update needed`"), phrasing repeated verbatim at Phase 3b step 4 (`SKILL.md:303`). The `⚠`/`✓` split maps to *kind* of check (content-presence vs. flag-value), not to phase; Phase 7c's own idempotency guard ("Mirroring Phase 7a") should match Phase 7a's fuller header convention (`**Idempotency rule (...)**:`), not Phase 7b's bare one.
- **No skill anywhere in the codebase currently re-parses a composed `unapplied_decision` gap-reason string back into its `(section, identifier)` parts (pattern-finder, 2026-08-23).** The two existing consumers of `format-check --format json` (`wire-issue` Phase 1.6, `confidence-check` Phase 1.8, which explicitly reuses wire-issue's cached `$FC_JSON` rather than re-invoking `format-check`, `SKILL.md:189-190`) both pull named JSON keys structurally via a one-line `python -c "...json.load(sys.stdin).get('<key>', [])..."` idiom and pass each list's string entries through unmodified for display (`confidence-check`'s `DECISION_GAP` joins entries with `"; "` for advisory display, never splits them, `SKILL.md:198,207`). A repo-wide grep for `"still specifies"`/`"rejected option"` outside `issue_parser.py` finds only that one display-prose hit. Phase 7c's need to parse `"{section} still specifies \`{identifier}\` (rejected option)"` back into structured section/identifier parts is therefore genuinely novel in this codebase — there is no existing string-parsing convention to model it on, only the JSON-key-extraction idiom for getting the raw list.
- **Three distinct "edit then reverify" shapes exist in the codebase and disagree on retry (pattern-finder, 2026-08-23):** (a) `decide-issue`'s own Phase 3b step 4 and Phase 7b — inline reverify immediately after the edit, single check, no retry, residual carried to Phase 9 (`SKILL.md:291-294`, `:407-410`; `reference.md:99` makes this explicit: "exit 2+ ... Treat as exit 1 — never clear on an unverifiable probe"); (b) `reconcile-issue` — no inline reverify at all; convergence is re-evaluated externally on a later loop pass by `autodev.yaml`'s `check_reconcile_needed`, which "routes on marker *presence*, so a marker that survives a completed reconcile pass re-fires the gate on every subsequent pass" (`commands/reconcile-issue.md:83-85`); (c) `ready-issue`'s Learning Tests step — inline, but with one bounded fix-and-recheck cycle before flagging (`commands/ready-issue.md:260-261`). Phase 7c's proposed "Non-empty re-check ... not a failure and must not retry" behavior matches shape (a) exactly — decide-issue's own existing precedent — not shapes (b) or (c).

## Implementation Steps

0. **Resolve `verify_verdict` first (see § *Verify Verdict Note*; added 2026-08-21, epic
   review).** Author the hand-written reproducer fixture Step 4 already requires and re-run
   `/ll:verify-issues 3280` so the verdict flips to `VALID` on real evidence **before this issue
   enters any loop** — otherwise `check_verify_verdict` routes automation into refine cycles
   against a false alarm about a deliberately absent reproducer. This is the Verify Verdict
   Note's option 1, made the first act of implementation.

1. **Prerequisite chain has landed — no external blocker remains.** BUG-3289 (`e3ffd49ce`),
   BUG-3285, BUG-3279, and BUG-3278 are all `status: done`; `blocked_by: BUG-3289` is resolved per
   the status-based resolution rule. Before writing Phase 7c, read the `## Scope Boundary` note
   below: BUG-3289's fix is deliberately partial (title+Summary subtraction only), so a residual of
   shared-vocabulary false positives is an accepted, not eliminated, risk — Phase 7c's bounded-scope
   rule must account for it rather than blindly rewriting every `_unapplied_decision` hit.
2. Write Phase 7c into `skills/decide-issue/SKILL.md` with the four reference categories and the
   explicit bounded-scope statement (option-keyed prose only, never a re-refine).
3. Extend the Phase 9 report template in `skills/decide-issue/reference.md` with a propagated-edits
   block and a flagged-but-not-edited block.
4. Verify against a fixture reconstructed from ENH-3277's pre-repair state — **hand-authored from
   this issue's own Current Behavior quotes (lines 42-51), not `git show`; no commit or abandoned
   ref captures that pre-repair text (confirmed by `/ll:wire-issue`, see Tests § "Flagged, not
   resolved")**: after a run, the `Recommendation: Option C` marker, step 3b's `--raw` instruction,
   and the two `--raw` Signatures entries are gone or demoted, and the stale counts are *flagged*
   rather than silently rewritten. The hand-repaired ENH-3277 doubles as the expected output —
   compare against it rather than inventing an oracle.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/guides/DECISIONS_LOG_GUIDE.md` — revise the pipeline diagram (lines 168-196) and the
  "Sample output" block's "only these three issue-file edits" claim (line 264) to account for
  Phase 7c's propagated-edits report
- Update `docs/reference/COMMANDS.md` — add a Phase 7c behavior sentence to the `/ll:decide-issue`
  section's "Frontmatter write-back" paragraph (~line 256)
- Add a Phase 7c test class to `scripts/tests/test_decide_issue_skill.py` — outer slice
  `## Phase 7:` → `## Phase 8:` per `TestDecisionNeededFrontmatterUpdate` (`:183-208`), method
  shape per `TestPattern3bDirectiveAlternatives` (`:673`)
- Add fixture(s) under `scripts/tests/fixtures/issues/` for the four Phase 7c scenarios, modeled on
  the `BUG-3025-pre-review-original.md` / `BUG-3025-reviewed-uncorrected.md` before/after pairing
  and wired into a test class like `FEAT-398-decide-empty-proposed.md` is
  (`test_decide_issue_skill.py:496-527`)

**Sequencing note — resolved: BUG-3278 already landed.** BUG-3278's `is_group_resolved` machinery
landed first and now defines Phase 7a's idempotency guard (`**Idempotency rule (per-group,
BUG-3278)**:`, `SKILL.md:399-403`). Phase 7c must be written against this already-changed Phase 7
region — inserting the new `### 7c` after the now-landed `### 7b` — not as a concurrent edit needing
a rebase.

## Scope Boundaries

- **In scope**: Phase 7c in `skills/decide-issue/SKILL.md`/`reference.md`, rewriting prose keyed to
  the option set — recommendation markers, conditional blocks, imperative steps, and explicit
  propagation checklists — within the closed `_DECISION_DIRECTIVE_SECTIONS` set (`Proposed
  Solution`, `Program Design`, `Implementation Steps`, `Files to Modify`, `Acceptance Criteria`),
  driven off `_unapplied_decision`'s existing detector output and reported per-edit in Phase 9.
- **Out of scope**: Restating counts, re-deriving scope figures, or re-running analysis — a decision
  pass must not become a refine pass, so unsafe downstream changes are flagged in the report rather
  than edited. Writing a new detector (Phase 7c reuses `_unapplied_decision` rather than duplicating
  it). Fixing `_decision_identifiers`'s shared-vocabulary false positives (BUG-3289, this issue's
  `blocked_by` prerequisite). Widening `_OPTION_HEADING_RE`'s block set (BUG-3285). Resolving
  BUG-3278's separate `decision_needed`-clearing defect (adjacent pass, not this issue's scope).

## Impact

- **Priority**: P2 — the pass currently introduces the contradiction it should resolve, and the
  affected text is imperative (an implementer acts on it)
- **Effort**: Medium — no code, but the propagation rules need care to stay bounded
- **Risk**: Medium — this is the first phase that rewrites arbitrary issue prose rather than
  appending to it. Over-reach turns a decision pass into an unreviewed refine pass; the
  bounded-scope rule and the auditable edit report are the mitigations
- **Breaking Change**: No

## Related Key Documentation

- `skills/decide-issue/SKILL.md` — Phases 6–7 define the current three-write contract
- ENH-3277 — the observed case, including its own line-198 propagation checklist
- BUG-3278 — `decision_needed` cleared while other decision points stay open; same pass, adjacent
  defect
- BUG-3289 — the `blocked_by` prerequisite: `_decision_identifiers`' shared-vocabulary false
  positives, which Phase 7c would otherwise act on as if they were real
- BUG-3279 — landed the span fix (`f39a417e`) that removed the first noise layer; `relates_to` only

## Verify Verdict Note

`verify_verdict: NON_VALID` (recorded by `/ll:verify-issues`) refers to the **reproducer**, not the
defect. The observed case in *Current Behavior* was ENH-3277, whose contradictory prose was repaired
by hand before this issue was verified, and `/ll:wire-issue` separately confirmed that no committed
or abandoned git revision holds the pre-repair text (see *Tests → "Flagged, not resolved"*). So a
verifier checking the issue's claims against the live tree correctly finds nothing to reproduce.

The underlying gap is structural and independently checkable: `skills/decide-issue/SKILL.md` Phases
6–7 define exactly three writes (`> **Selected:**` callout, `### Decision Rationale`,
`decision_needed: false`) and no phase reconciles the rest of the document — confirmed by reading
the skill, not by reproducing ENH-3277. **Do not cull this issue on the NON_VALID verdict.**
Re-verify against the skill's phase list, or against the hand-authored fixture Implementation
Step 4 calls for, once that fixture exists.

### ⚠ This verdict is machine-consumed — the prose above will not be read by the gate

`verify_verdict` is not advisory. Measured 2026-08-21:

```
$ ll-issues check-verify-verdict 3280
VERIFY_VERDICT_NON_VALID: 3280 — verify_verdict='NON_VALID'; run /ll:verify-issues 3280 --auto
$ echo $?
1
```

Exit 1 routes `scripts/little_loops/loops/refine-to-ready-issue.yaml`
`check_verify_verdict` (`:347-351`) → `on_no` → `check_proposal_unsound` (`:353-366`) → `on_no` →
`check_refine_limit` → `refine_followup`. So if this issue enters that loop before implementation,
automation burns refine cycles trying to repair a verdict whose own issue body says is a false
alarm about a **deliberately absent reproducer**. "Do not cull this issue on the NON_VALID verdict"
is a instruction to humans; the FSM reads the field.

**Resolve before this issue enters any loop — pick one:**

1. **Preferred** — author the hand-written fixture Implementation Step 4 already requires (from this
   issue's own *Current Behavior* quotes), then re-run `/ll:verify-issues 3280` so the verdict flips
   to `VALID` on real evidence. This is work the issue owes anyway; doing it first makes the field
   honest instead of suppressed.
2. Clear `verify_verdict` from frontmatter. `check_verify_verdict` fails open on an absent field
   (`on_yes`, per its own comment at `:349`), so the loop proceeds. Cheaper, but discards the record
   of an actual verify run — take it only if this issue is scheduled before the fixture exists.

Deliberately **not** done as part of this review: option 2 deletes evidence and option 1 is
implementation work. Flagged for the implementer to close.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): [BUG-3289]'s decided fix is deliberately partial —
its narrow title+Summary subtraction scope leaves an accepted residual of shared-vocabulary false
positives (its own Decision Rationale names `ProjectConfig`/`to_dict()` on ENH-3277 as surviving,
"expected residual noise"). Phase 7c as specified acts on every `_unapplied_decision` hit with no
filter beyond the detector itself, so those residual false positives will still be rewritten as if
they were real rejected-option prose — the failure mode this issue's own Motivation says landing
BUG-3289 first is supposed to prevent. Before Phase 7c ships, either widen its bounded-scope rule to
flag (not blindly edit) hits whose identifier doesn't also appear inside the option blocks' own
text, or explicitly accept the residual risk with a named mitigation.

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:reconcile-issue` - 2026-08-23T05:28:00 - `547ad306-83f6-4672-bcc1-e1656230f4b2.jsonl`
- `/ll:refine-issue` - 2026-08-23T05:22:39 - `b2d2e7b4-d39e-4d10-a40c-83a347d4aafb.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-22T22:31:16 - `ccec33f2-1527-4aff-b9d7-1a9165839f2e.jsonl`
- `/ll:format-issue` - 2026-08-22T20:15:07 - `918913f6-1ede-43d4-b1f7-bffea0db90c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-21T17:52:58 - `f27d8342-f3ba-42ea-95ca-41ad79008fbf.jsonl`
- `/ll:verify-issues` - 2026-08-21T17:43:58 - `aee80426-6ab1-4a8c-814d-a6f459361121.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:40:24 - `2c542a24-aeb3-46f2-9dc7-120037c4fb74.jsonl`
- `/ll:verify-issues` - 2026-08-21T17:33:43 - `fa57a84b-34e0-4018-9e9e-dd57ed7ef3f3.jsonl`
- `/ll:wire-issue` - 2026-08-21T17:29:04 - `76775aa0-e5e0-4b13-930a-5924b752270f.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:19:06 - `ea08ee55-36d8-4ff2-b8d4-2a20e7e2ad81.jsonl`
- `/ll:capture-issue` - 2026-08-21T16:00:38 - `826fb04a-1812-4193-be3d-c48a972bd311.jsonl`
- `/ll:capture-issue` - 2026-08-21T15:46:43 - `da526826-2179-460f-b823-35695378ac55.jsonl`

## Tests

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

- **Anchor refresh (2026-08-23) — test-file line numbers cited elsewhere in this section are stale, drifted again since the 2026-08-21 refine pass.** `scripts/tests/test_issue_parser.py`: `class TestFormatGradedChecker` now `:3966`, `class TestUnappliedDecision` now `:5093` (was cited `:4757`), `test_all_blocks_carry_selected_line_resolves_single_winner` now `:5248` (was `:4912-4929`), `class TestUnappliedDecisionLiveCorpusSweep` now `:5604` (was `:5063`), `test_corpus_sweep_does_not_crash` now `:5626` (was `:5085`). `scripts/tests/test_decide_issue_skill.py`: `class TestDecisionNeededFrontmatterUpdate` still `:183-208` (exact match, unchanged), `class TestPhase3bResolvedFilter` now `:311` (was cited `:287-300`), `class TestFEAT398Snapshot`/`FIXTURE = Path(...)` now `:520`/`:529` (was `:496-527`), `class TestPattern3bDirectiveAlternatives` now `:673` (was `:649-705`). `scripts/tests/test_enh494_skill_companions.py` citations (`test_skill_links_to_companion` `:63`, `class TestSkillLineLimit` `:73-86`) are confirmed still exact. `scripts/little_loops/cli/issues/format_check.py` `--fix` dispatch-list citation (`:98-113`) is confirmed still exact.
- **Confirmed still true (2026-08-23): no fixture exists yet under `scripts/tests/fixtures/issues/` for the two-option decision shape** (`**Option A**`/`**Option B**` + `> **Selected:**` callout + stale directive-section prose) this issue's four Phase 7c test scenarios need. Only `FEAT-398-decide-empty-proposed.md` and the `BUG-3025-pre-review-original.md`/`BUG-3025-reviewed-uncorrected.md` pair remain the closest decide-issue-adjacent precedents on disk.
