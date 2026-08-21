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

`issue_parser._unapplied_decision` (`:1392`) already **detects** this defect: it enumerates option
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

## Integration Map

### Files to Modify

- `skills/decide-issue/SKILL.md` — new Phase 7c; Phase 9 report gains a propagated-edits block
- `skills/decide-issue/reference.md` — the Phase 9 output template lives here

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
- `_unapplied_decision` test coverage: `scripts/tests/test_issue_parser.py:4757-4965`, class
  `TestUnappliedDecision`, using an inline `_issue()` builder helper (`:4765-4770`) rather than
  on-disk `.md` fixtures — no fixture file for this detector exists under
  `scripts/tests/fixtures/issues/`
- A live-corpus sweep test already exists and documents a known precision limit:
  `scripts/tests/test_issue_parser.py:4968`, `TestUnappliedDecisionLiveCorpusSweep.test_corpus_sweep_does_not_crash`
  — asserts `_unapplied_decision` never raises across `.issues/`, and is explicitly
  report-only/non-blocking due to ~40% false-positive rate on the real corpus (this is the noise
  BUG-3279 is fixing)
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

- `_unapplied_decision(content: str) -> list[str]` (`scripts/little_loops/issue_parser.py:1392`) returns only formatted reason strings — `"{section} still specifies \`{identifier}\` (rejected option)"` (`:1513`) — not a structured `(section, identifier)` tuple. Phase 7c must parse this string to recover the section name and identifier, since no structured API exists.
- Surfaced today via `ll-issues format-check <ID> --format json` → `unapplied_decision` key (`scripts/little_loops/cli/issues/format_check.py:672-685`, JSON serialization at `issue_parser.py:594`) — a skill-authored Phase 7c can consume this over subprocess without new Python glue.
- `unapplied_decision` is **not** in the `--fix`/`--apply` dispatch list (`format_check.py:98-113`, which covers `prose_dep_drift`, `duplicate_findings_block`, `duplicate_heading`, `empty_provenance_stub`, `template_placeholders`) — there is no existing auto-repair path; Phase 7c must perform its own edits.
- `check_format_gaps` (`issue_parser.py:1114`) is the sole caller of `_unapplied_decision`; `unapplied_decision` is a **blocking** (non-advisory) gap class on `FormatGaps.has_blocking_gaps` (`issue_parser.py:555-565`) — so the pre-fix state already fails `format-check`, independent of this issue.
- `_DECISION_DIRECTIVE_SECTIONS = ("Proposed Solution", "Program Design", "Implementation Steps", "Files to Modify", "Acceptance Criteria")` (`issue_parser.py:1302-1308`) is the closed list of sections `_unapplied_decision` scans — Phase 7c's sweep scope should match this list, not invent a broader one.
- Supporting extraction helpers Phase 7c may need for finer-grained matching beyond the formatted-string output: `_option_block_spans` (`:1371`), `_selected_option_title` (`:1322`), `_option_label` (`:1335`), `_decision_identifiers` (`:1341`) — all private module functions with no CLI wrapper; only reachable in aggregate via `_unapplied_decision`'s output.

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **Correction (pattern-finder, 2026-08-21): `reconcile-issue` is not the only in-place-prose-rewrite precedent.** `decide-issue`'s own existing Phase 3b already rewrites prose in place: "Materialize alternatives, if not already structured (ENH-2715)" (`skills/decide-issue/SKILL.md:284-293`) converts informal `- (a) ...`/`- (b) ...` bullets or an Open-Questions-named alternative into structured `**Option A**`/`**Option B**` blocks, and the skill text names this itself as "additive/rewrite-in-place of the same prose already matched" (`:292`). Two further in-place-rewrite precedents exist outside issue-markdown prose specifically: `skills/improve-claude-md/SKILL.md:89,174` (rewrites `CLAUDE.md` via Edit) and `skills/simplify-loop/SKILL.md:204` ("4b. Rewrite the parent", verified against a reachable-terminal diff at `:92-98`). `wire-issue` and `refine-issue` remain confirmed append-only/marker-only (`skills/wire-issue/SKILL.md:427`, `refine-issue.md`'s marker-only carve-out) — the "Bounded scope" analogy to `reconcile-issue` in this issue's Proposed Solution still holds, but the "no existing skill rewrites prose except reconcile-issue" framing above is inexact; Phase 7c has an in-skill precedent (Phase 3b) as well as the cross-skill one already cited.
- **Audit-trail heading conventions (pattern-finder, 2026-08-21):** two heading families coexist and are not interchangeable. `## CHANGES APPLIED` (decide-issue `reference.md:125`, format-issue `templates.md:318`, review-sprint `review-sprint.md:336`) varies its bullet shape per command (decide-issue: tri-state `[Action | Skipped (idempotent)]`; format-issue: grouped `###` sub-headings; review-sprint: flat `Pruned:`/`Removed:`/`Added:`/`Revalidated:` lines). `## CORRECTIONS_MADE` (reconcile-issue `:288-296`, ready-issue `:463-476`) shares a tighter `[category-tag] description` bullet convention and both end with an explicit `[Or "None" if no corrections needed]` empty-state line. Phase 7c's report block should pick one family deliberately rather than inventing a third shape — decide-issue already owns `## CHANGES APPLIED` in `reference.md:125`, so extending that heading with a new propagated-edits bullet group is the lower-friction fit.

### Conventions in Force
- Lettered sub-phases (`### 7a`, `### 7b`, ...) nest under one `## Phase N` parent, each a discrete ordered write — evidence: `skills/decide-issue/SKILL.md:399-424` (7a/7b under Phase 7) and `skills/wire-issue/SKILL.md:336-452` (8a/8b/8c under Phase 8). No skill in the repo goes past a `c` suffix; Phase 7c would be the first `c`-level sub-phase in `decide-issue`.
- Idempotency guards are phrased "**Idempotency [rule]**: if `<condition>`, skip the write and log `<marker> <message>`" — evidence: `skills/decide-issue/SKILL.md:409` (uses `⚠` for "content already present") and `:424` (uses `✓` for "flag already at target value"). The two symbols are not interchangeable within this skill; ENH-3280's own "Mirroring Phase 7a" points at the `⚠` form since Phase 7c is a content-presence check, not a flag check.
- `/ll:reconcile-issue` (`commands/reconcile-issue.md:46-117`) is the only existing precedent in this codebase for rewriting (not just appending to) issue prose, and it bounds itself with an explicit rewrite allowlist, a preserve-untouched list, and a rule that "every rewritten claim must trace to an existing finding" (`:112-117`). Every other prose-touching skill (`wire-issue`, `refine-issue`) is append-only or marker-only. Phase 7c's "Bounded scope" language should be understood as adopting this same shape, not a novel one.
- Audit-trail reporting of edits made during a rewrite pass uses a dedicated report subsection, one bullet per edit, each citing its driving evidence — evidence: `commands/reconcile-issue.md:288-296` (`## CORRECTIONS_MADE`, `[reconcile]`-tagged bullets citing a quoted finding) and `skills/decide-issue/reference.md:125-128` (`## CHANGES APPLIED`, fixed-choice bullets). No existing report block cites literal `file:line` per edit — reconcile-issue's closest analog cites step numbers, not line numbers; ENH-3280's "with its line reference" requirement has no direct precedent to copy.

## Program Design

### Signatures

- `_unapplied_decision(content: str) -> list[str]` — the sole existing entry point Phase 7c drives
  off; returns formatted reason strings only, one per `(section, identifier)` pair, never a
  structured tuple (`scripts/little_loops/issue_parser.py:1392`)
- `check_format_gaps(content: str) -> FormatGaps` — sole caller of `_unapplied_decision`; invoked
  from `ll-issues format-check <ID> --format json`, which serializes the list under the JSON key
  `"unapplied_decision"` (`issue_parser.py:1114`, CLI at `scripts/little_loops/cli/issues/format_check.py:672-685`,
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
(`format_check.py:476`) -> `check_format_gaps` (`issue_parser.py:1114`) -> `_unapplied_decision`
(`issue_parser.py:1392`) -> JSON `unapplied_decision` list returned to the skill -> skill parses
each `"<Section> still specifies \`<identifier>\` (rejected option)"` string to locate the
identifier's occurrence in that section -> Edit tool rewrites/demotes/strikes the matched prose
per the four categories in `## Proposed Solution` -> skill re-invokes `format-check` to confirm
`unapplied_decision` is now empty before proceeding to Phase 8.

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

## Implementation Steps

1. **Land BUG-3289 first** — Phase 7c drives off `_unapplied_decision`, whose report list is still
   dominated by shared-subject false positives (~23 on ENH-3277, 2 on ENH-2692) even after
   BUG-3279's span fix landed in `f39a417e`. Rewriting prose to satisfy those reports damages
   correct text. See *Motivation § Half of this already exists*, item 2, for why the prerequisite
   moved from BUG-3279 to BUG-3289.
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

- Update `docs/guides/DECISIONS_LOG_GUIDE.md` — revise the pipeline diagram (lines 168-194) and the
  "Sample output" block's "only these three issue-file edits" claim (line 262) to account for
  Phase 7c's propagated-edits report
- Update `docs/reference/COMMANDS.md` — add a Phase 7c behavior sentence to the `/ll:decide-issue`
  section's "Frontmatter write-back" paragraph (~line 256)
- Add a Phase 7c test class to `scripts/tests/test_decide_issue_skill.py` — outer slice
  `## Phase 7:` → `## Phase 8:` per `TestDecisionNeededFrontmatterUpdate` (`:183-208`), method
  shape per `TestPattern3bDirectiveAlternatives` (`:649-705`)
- Add fixture(s) under `scripts/tests/fixtures/issues/` for the four Phase 7c scenarios, modeled on
  the `BUG-3025-pre-review-original.md` / `BUG-3025-reviewed-uncorrected.md` before/after pairing
  and wired into a test class like `FEAT-398-decide-empty-proposed.md` is
  (`test_decide_issue_skill.py:496-527`)

**Sequencing note (not auto-resolved):** `BUG-3278` independently edits the same
`## Phase 7: Apply Changes` region of `skills/decide-issue/SKILL.md` (lines 399-441) — it inserts a
residual-probe re-scan into Phase 7b's internals, while this issue inserts a new Phase 7c after
Phase 7b. Both issues touch the same ~40-line span concurrently; whichever lands second should
rebase against the other rather than assuming a clean merge [Agent 2 finding].

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

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-21T17:52:58 - `f27d8342-f3ba-42ea-95ca-41ad79008fbf.jsonl`
- `/ll:verify-issues` - 2026-08-21T17:43:58 - `aee80426-6ab1-4a8c-814d-a6f459361121.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:40:24 - `2c542a24-aeb3-46f2-9dc7-120037c4fb74.jsonl`
- `/ll:verify-issues` - 2026-08-21T17:33:43 - `fa57a84b-34e0-4018-9e9e-dd57ed7ef3f3.jsonl`
- `/ll:wire-issue` - 2026-08-21T17:29:04 - `76775aa0-e5e0-4b13-930a-5924b752270f.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:19:06 - `ea08ee55-36d8-4ff2-b8d4-2a20e7e2ad81.jsonl`
- `/ll:capture-issue` - 2026-08-21T16:00:38 - `826fb04a-1812-4193-be3d-c48a972bd311.jsonl`
- `/ll:capture-issue` - 2026-08-21T15:46:43 - `da526826-2179-460f-b823-35695378ac55.jsonl`
