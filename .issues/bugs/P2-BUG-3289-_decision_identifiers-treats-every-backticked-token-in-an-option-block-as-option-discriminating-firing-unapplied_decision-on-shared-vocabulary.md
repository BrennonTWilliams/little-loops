---
id: BUG-3289
type: BUG
title: _decision_identifiers treats every backticked token in an option block as option-discriminating,
  firing unapplied_decision on shared vocabulary
priority: P2
status: done
parent: EPIC-3290
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T18:59:36Z'
completed_at: '2026-08-23T01:16:53Z'
decision_needed: false
size: Medium
labels:
- issue-parser
- format-check
- unapplied-decision
relates_to:
- BUG-3279
- BUG-3278
- BUG-3285
- ENH-3280
- BUG-3295
confidence_score: 98
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 23
score_ambiguity: 23
score_change_surface: 22
---

# BUG-3289: _decision_identifiers treats every backticked token in an option block as option-discriminating, firing unapplied_decision on shared vocabulary

## Summary

`_unapplied_decision` reports "Section still specifies `X` (rejected option)" for any backticked
identifier that appears in a rejected option block but not in the winning one. `_decision_identifiers`
(`issue_parser.py:1351`) extracts **every** backticked span of length >= 3 as an option-discriminating
identifier, with no filter for vocabulary that belongs to the issue's shared subject rather than to
either option. When the winner's own prose happens not to restate a term the rejected option mentions,
`discriminating = rej_ids - sel_ids` (`:1530`) promotes it and the report fires against every directive
section that names it.

Split out of BUG-3279, which measured the effect and explicitly deferred it: after BUG-3279's span
fix (`f39a417e`), ENH-3277 still emits ~23 reports for ordinary vocabulary (`pytest`, `ProjectConfig`,
`rn-refine`, `.ll/ll-config.json`, `to_dict()`, `oracles/code-run-gate.yaml`), and ENH-2692 gains two
new ones for `final_score` — the issue's shared subject, named in its title, Summary, and Files to
Modify before any option exists. These are not span-absorption artifacts; BUG-3279's fix merely
stopped masking them.


## Current Behavior

`_decision_identifiers(text) -> set[str]` (`scripts/little_loops/issue_parser.py:1351`) is two lines:

```python
def _decision_identifiers(text: str) -> set[str]:
    """Backticked identifiers of length >= 3 in *text*."""
    return {m.group(1) for m in _DECISION_IDENTIFIER_RE.finditer(text)}
```

`_DECISION_IDENTIFIER_RE` (`:1329`) is `` r"`([^`\n]{3,})`" `` — any backticked span. There is no
notion of which identifiers *distinguish* the options from each other versus which are simply the
issue's subject matter, mentioned throughout.

`_unapplied_decision` (`:1449`) then computes, at `:1524-1530`:

```python
sel_ids = _decision_identifiers(block_texts[selected_index])
rej_ids: set[str] = set()
for i, block_text in enumerate(block_texts):
    if i != selected_index:
        rej_ids |= _decision_identifiers(block_text)

discriminating = rej_ids - sel_ids
```

The only thing standing between a shared-subject term and a report is whether the *winning* option's
own prose happens to restate it. That is incidental to how the author wrote the winner, not evidence
that the term belongs to the rejected approach.

Two live cases, both measured under BUG-3279:

- **ENH-3277** — ~23 surviving `unapplied_decision` reports naming `pytest`, `ProjectConfig`,
  `rn-refine`, `.ll/ll-config.json`, `to_dict()`, `oracles/code-run-gate.yaml`. None is a
  rejected-option identifier; all are ordinary vocabulary of the issue's subject.
- **ENH-2692** — `Acceptance Criteria still specifies \`final_score\`` and
  `Files to Modify still specifies \`final_score\``. `final_score` is the issue's **shared subject**:
  it is in the title, the Summary, and Files to Modify — all *before* any option exists. It lands in
  `rej_ids` because Option A's text names it, and it is absent from `sel_ids` only because Option B's
  own four-line description is about updating the loop `description` instead. Before BUG-3279 the
  span-absorption bug swept the shared analysis sections into the winner's block, so `sel_ids`
  contained it *by accident* and the subtraction silently suppressed the report.

## Expected Behavior

`unapplied_decision` fires only for identifiers that actually discriminate between the options —
terms introduced by the rejected approach — not for the issue's shared subject vocabulary. An
identifier that the issue already names before either option is defined is, by construction, not
option-discriminating.

## Steps to Reproduce

1. `ll-issues format-check ENH-2692` — reports `Acceptance Criteria still specifies \`final_score\``
   and `Files to Modify still specifies \`final_score\``.
2. Read ENH-2692's title, Summary, and Files to Modify — `final_score` appears in all three, above
   the option blocks.
3. `ll-issues format-check ENH-3277` — ~23 further reports naming ordinary subject vocabulary.

Assert the *relation* (a shared-subject identifier is reported), not the counts: both issues are
actively refined and their report totals drift.

## Motivation

`format-check` gates `ensure_formatted` in several FSM loops, and its report list is what a human or
an LLM reads when deciding whether an issue is structurally sound. A check whose output is mostly
false positives trains readers to skim past it, which costs the *true* `unapplied_decision`
detections ENH-3256 built the mechanism for. The noise also scales with refinement depth — the more
codebase vocabulary an issue accumulates, the more shared terms are available to fire — so it is
loudest on exactly the issues whose decisions matter most.

Splitting this out was BUG-3279's explicit instruction: *"File **one** follow-up for that breadth
problem … Do not widen this issue's scope to cover it."*

## Proposed Solution

Subtract the issue's shared subject vocabulary from `discriminating` before reporting. The candidate
rule recorded in BUG-3279:

> subtract identifiers that appear in the issue's title/Summary, or in any section preceding
> `## Proposed Solution`, before computing `discriminating`.

Both halves needed deciding before implementation — **pick one scope per bullet, do not leave
unaddressed**. ✅ **Both decided 2026-08-21**; the selections are inline below and the reasoning is
in § *Decision Rationale*:

> **✅ Decided 2026-08-21 — `decision_needed` is now `false`.** Both bullets were a real, undecided
> decision point that the frontmatter did not declare; `decision_needed: true` was set, and
> `/ll:decide-issue 3289` ran the same day (session log `570c3914…`). Both selections and their
> rationale are recorded in § *Decision Rationale* below, and the `> **Selected:**` callouts are on
> each bullet. **No decide pass is owed.** Noted at EPIC-3290 § *Undeclared decision points on this
> epic's own children*, which was stale on this point until 2026-08-21.
>
> Note for anyone re-checking with the gate: `ll-issues check-decidable 3289` still exits **0** with
> `2 enumerable option(s)`. That command reports *decidability*, not *resolution* — it is not an
> oracle for whether a decision has been made. That conflation is BUG-3278's subject.
>
> **Pre-scheduling passes still owed (added 2026-08-21, epic review — NOT closed by the decide
> pass).** This issue has had no `/ll:refine-issue`, `/ll:wire-issue`, or `/ll:verify-issues` pass
> (session log: capture, conflict-audit, decide, confidence-check) despite now being the head of
> this epic's critical path — the hard `blocked_by` of P2 ENH-3280. Run **refine → wire → verify
> before implementation**. The decision was made against unverified claims, so the verify pass may
> reopen it; that is the accepted cost of having decided first. Its `issue_parser.py` anchors are
> also on the stale pre-`93270c37` set (+50 lines: `_decision_identifiers` is at `:1401`,
> `_unapplied_decision` at `:1499`, `discriminating` at `:1580` as of this review — resolve by
> symbol name at implementation time, per the epic's anchor note, rather than trusting these).

- **Scope of the subtraction corpus** — title + `## Summary` only (narrow, cheap, catches ENH-2692),
  or everything above `## Proposed Solution` (wider; catches more of ENH-3277's ~23 but risks
  suppressing a genuine rejected-option identifier that an earlier section happens to name).

  > **Selected:** title + `## Summary` only (narrow) — see Decision Rationale below.
- **Where the subtraction lands** — inside `_decision_identifiers` (would change every caller), or as
  a separate `_shared_subject_identifiers(content) -> set[str]` subtracted once in
  `_unapplied_decision` at `:1530`. The second is almost certainly right: `_decision_identifiers`
  is a pure per-block extractor and has no access to document-level context.

  > **Selected:** separate `_shared_subject_identifiers` helper, subtracted once in
  > `_unapplied_decision` at `:1530` — per the stated recommendation; `_decision_identifiers` stays
  > a pure per-block extractor.

Measure the corpus effect both directions before landing, per BUG-3279's precedent: report totals
before/after across all of `.issues/`, and **`new_reports == 0`** (a subtraction can only remove
reports, so any gain means the implementation is wrong).

### Sequencing — BUG-3285 is a preference, not a block (revised 2026-08-21)

This issue previously declared `blocked_by: BUG-3285`. **Demoted to `relates_to`.** The rationale for
the block was that BUG-3285's phantom blocks pollute the `rej_ids` / `sel_ids` sets this issue
subtracts from, so the corpus measurement reads cleaner once they are gone. That is a *readability*
benefit, not a correctness dependency:

- This issue's own guard — `new_reports == 0`, measured against the tree the change lands on — is
  self-contained and holds regardless of how many phantom blocks exist at that moment.
- The report-total drop is already declared an **observation, not an assertion** (Implementation
  Step 3), so a shifting baseline costs nothing.
- BUG-3285 is under redesign (its proposed regex was measured to drop two real *selected* options
  and to widen across line boundaries — see that issue's *Proposed Solution → Corpus differential*).
  A hard block would hold this issue behind that rework for no correctness gain.

Land BUG-3285 first if it is ready; otherwise land this one and re-baseline the recorded drop when
BUG-3285 arrives. Mirrors BUG-3285's own framing of its relationship to BUG-3279: *"Not a hard
dependency in either direction."*

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-21.

This issue bundled two decisions ("pick one scope per bullet, do not leave unaddressed"); both are
resolved here.

**Decision 1 — Scope of the subtraction corpus**

**Selected**: title + `## Summary` only (narrow)

**Reasoning**: An exact precedent already exists in the same file — the `testable` gap class
(`issue_parser.py:1061-1069`) computes `scan_text = f"{title}\n{summary}"` from the title (with H1
fallback) and `_section_body(content, "Summary")`, the identical shape this option needs. The wide
option ("everything above `## Proposed Solution`") has no existing "prefix before heading" primitive
in the file and, more importantly, direct corpus evidence (BUG-3287, ENH-3277) shows `## Current
Behavior` sections in this repo's issue-writing convention routinely reuse the same identifiers
that later become option-discriminating inside `## Proposed Solution`'s nested decision blocks.
Since this issue's own Impact section already names over-suppression (dropping a genuine
`unapplied_decision` detection) as the risk to bound, and Implementation Step 3's `new_reports == 0`
gate has zero tolerance for that failure mode, the narrow scope is the safer choice. It comes with
an accepted tradeoff: 2 of the 6 ENH-3277 terms spot-checked (`ProjectConfig`, `to_dict()`) live in
`## Current Behavior`/`## Proposed Solution` rather than Summary and will not be suppressed by this
fix — expected residual noise, consistent with this issue's own precedent of being split from
BUG-3279 for an incremental, measured fix rather than a one-shot complete one.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Narrow (title + Summary) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Wide (everything above Proposed Solution) | 2/3 | 2/3 | 2/3 | 1/3 | 7/12 |

**Key evidence**:
- Narrow: exact reusable precedent at `issue_parser.py:1061-1069` (the `testable` gap class); no
  over-suppression risk since `## Summary` is written before options exist.
- Wide: no existing "prefix before heading" helper in `issue_parser.py` (new code, composed from
  `_section_body_with_offset`/`_option_span_boundary`'s fence-aware primitives); demonstrated
  over-suppression risk in BUG-3287 and ENH-3277, where `## Current Behavior` reuses identifiers
  that later distinguish rejected options in `## Proposed Solution`.

**Decision 2 — Where the subtraction lands**

**Selected**: a separate `_shared_subject_identifiers(content) -> set[str]` helper, subtracted once
in `_unapplied_decision` at `:1530`.

**Reasoning**: Locked in per the issue's own stated recommendation — `_decision_identifiers` is a
pure per-block extractor with no access to document-level context, so folding document-level scope
logic into it would change every caller's contract for no benefit. Not independently scored;
recorded here for completeness per "pick one scope per bullet, do not leave unaddressed."

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — `_unapplied_decision` (`:1449`, the `discriminating`
  computation at `:1530`); new `_shared_subject_identifiers` helper if that shape is chosen.
  `_decision_identifiers` (`:1351`) and `_DECISION_IDENTIFIER_RE` (`:1329`) are likely unchanged

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/format_check.py` — surfaces `unapplied_decision` gaps; consumes
  the list, no code change expected
- FSM `ensure_formatted` states that shell out to `ll-issues format-check` read only the exit code,
  so a strictly-narrowing change can flip a gate from fail to pass but never the reverse

### Similar Patterns

- `_strip_codebase_research_findings` (`issue_parser.py:1356`) is the existing precedent for
  excluding a region from `_unapplied_decision`'s scan surface — ENH-3256 introduced it after a
  corpus run showed 128 false-positive firings from research prose. Same shape of fix, different
  axis (region-based there, vocabulary-based here)

### Tests

- `scripts/tests/test_issue_parser.py::TestUnappliedDecision` (builds fixtures via its local
  `_issue(self, proposed_solution, **directive_sections)` helper) — add a fixture mirroring the
  ENH-2692 shape: a shared identifier in the title/Summary, named in the rejected option, absent
  from the winner's own description, and present in a directive section. Assert **no** report
- Pair it with a negative control: an identifier introduced *only* by the rejected option still
  reports, so the subtraction has not swallowed the real detection
- BUG-3279's *Residual Work* item 1 adds a fixture asserting the ENH-2692 report **does** fire,
  documenting it as this issue's defect. **That fixture inverts when this lands** — update it in
  the same commit rather than leaving two tests asserting opposite things

### Documentation

- `docs/reference/CLI.md` — the `ll-issues format-check` gap-kind list, if it describes
  `unapplied_decision`'s matching rule

### Configuration

N/A

## Program Design

### Types

N/A — no new data structures. The change operates on `set[str]` values that already flow through
`_unapplied_decision`.

### Signatures

- `_decision_identifiers(text: str) -> set[str]` — every backticked span of length >= 3 in *text*,
  as a set. Pure per-block extractor with no document context; unchanged by the preferred shape.
  Defined at `scripts/little_loops/issue_parser.py:1351`.
- `_unapplied_decision(content: str) -> list[str]` — produces the `unapplied_decision` gap strings;
  the subtraction lands here, at the `discriminating = rej_ids - sel_ids` line. Defined at
  `scripts/little_loops/issue_parser.py:1449`.
- `_shared_subject_identifiers(content: str) -> set[str]` — new; identifiers drawn from the issue's
  shared subject region, to be subtracted from `discriminating`. Exact region depends on the scope
  decision above.
- `_strip_codebase_research_findings(body: str) -> str` — unchanged; the existing region-based
  exclusion this fix parallels on the vocabulary axis. Defined at
  `scripts/little_loops/issue_parser.py:1356`.

### Call Path

Before: `ll-issues format-check ID` -> `cmd_format_check` -> `check_format_gaps` ->
`_unapplied_decision` -> `_option_block_spans` -> `_decision_identifiers` per block ->
`discriminating = rej_ids - sel_ids` -> gap string per directive-section mention.

After: the same path, with `_shared_subject_identifiers(content)` subtracted from `discriminating`
before the directive-section scan.

### Decision Rules

The two scope questions in *Proposed Solution* are the decision rules this issue introduces — which
region defines "shared subject", and where the subtraction lands. **Both are settled** (2026-08-21,
`/ll:decide-issue`): the shared-subject region is the **title + `## Summary`** only, and the
subtraction lands in a separate `_shared_subject_identifiers(content) -> set[str]` helper applied
once inside `_unapplied_decision`. Rationale and scoring in § *Decision Rationale*; the accepted
residual is that identifiers living only in `## Current Behavior` / `## Proposed Solution` (2 of the
6 ENH-3277 terms spot-checked) stay unsuppressed.

## Implementation Steps

1. ~~Decide both scope questions in *Proposed Solution* (subtraction corpus; helper placement).~~
   ✅ **Done 2026-08-21** — narrow (title + `## Summary`) and a separate
   `_shared_subject_identifiers` helper; see § *Decision Rationale*. Replaced by: run
   `/ll:refine-issue` → `/ll:wire-issue` → `/ll:verify-issues` (still owed — see the callout in
   *Proposed Solution*), and re-open the decision only if verification contradicts its evidence.
2. Implement the subtraction; add the ENH-2692-shaped fixture and its negative control to
   `TestUnappliedDecision`.
3. Corpus-measure across `.issues/`: record the report-total drop as an observation, assert
   `new_reports == 0` strictly.
   > **Baseline against the tree this lands on, not a fixed commit** (added 2026-08-21, epic
   > review). `new_reports == 0` holds for *this* change in isolation — a subtraction can only
   > remove reports. But **BUG-3285** also moves `_unapplied_decision`'s output, from the other
   > side: tightening `_OPTION_HEADING_RE` changes `_option_block_spans`' block set and therefore
   > `sel_ids`/`rej_ids`/`spans[-1]`, and reports there can move in *both* directions. If BUG-3285
   > lands first, re-baseline before asserting — see BUG-3285 § *Second blast radius*, and
   > BUG-3278 assertion (c5), which coordinates the same snapshot across all three issues.
4. Re-check ENH-2692 and ENH-3277 by hand — the two issues whose reports motivated this — and
   confirm the surviving reports are genuine.
5. Invert BUG-3279's residual fixture (item 1) in the same commit.

## Impact

- **Priority**: P2 — raised from P3 2026-08-21 (epic review). On its own merits this is report
  noise in an advisory check, but it is now the hard `blocked_by` prerequisite of P2 ENH-3280
  (whose Phase 7c rewrites prose against this detector's report list), so it inherits the
  effective priority of the work it gates
- **Effort**: Small-to-Medium — one subtraction plus a corpus measurement; the scope decisions are
  the real work
- **Risk**: Low-Medium — a subtraction can only *remove* reports, so the failure mode is suppressing
  a genuine `unapplied_decision` detection, not creating false ones. The negative-control test and
  the `new_reports == 0` assertion bound it
- **Breaking Change**: No

## Root Cause

- **File**: `scripts/little_loops/issue_parser.py`
- **Anchor**: `in _decision_identifiers() (:1351), consumed by _unapplied_decision() (:1524-1530)`
- **Cause**: `_decision_identifiers` extracts every backticked span of length >= 3 with no notion of
  option-discriminating versus shared-subject vocabulary. `discriminating = rej_ids - sel_ids`
  therefore relies on the *winner's* prose incidentally restating a shared term to suppress it — a
  property of how the author wrote the winning option, not evidence about the term.

## Related Key Documentation

- BUG-3279 — measured this defect (ENH-3277's ~23 survivors, ENH-2692's 2 new reports), traced it to
  `_decision_identifiers`, and required this follow-up in *Implementation Steps* step 5
- ENH-3256 — introduced `_unapplied_decision`'s existing false-positive mitigations
  (`_strip_codebase_research_findings`, the `> **Selected:**` callout trim); the precedent for
  narrowing this check without deleting it
- **ENH-3280 — the downstream consumer, and this issue is now its hard prerequisite.** Phase 7c
  drives its prose rewrites off `_unapplied_decision`'s report list, so every false positive this
  issue leaves in place is prose Phase 7c would rewrite *correctly-written* text to satisfy.
  ENH-3280 originally declared `blocked_by: BUG-3279` on the strength of that argument; BUG-3279's
  parser fix has since landed (`f39a417e`) and the residual noise is this issue's. The edge was
  re-pointed here on 2026-08-21

| Document | Relevance |
| --- | --- |
| `docs/reference/API.md` | Module reference for `little_loops.issue_parser`; update if a new `_shared_subject_identifiers` helper becomes part of the documented surface |

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): the narrow (title + `## Summary` only) subtraction
scope decided here is knowingly incomplete — this issue's own Decision Rationale accepts that
"2 of the 6 ENH-3277 terms spot-checked (`ProjectConfig`, `to_dict()`) live in `## Current
Behavior`/`## Proposed Solution` rather than Summary and will not be suppressed by this fix —
expected residual noise." [ENH-3280]'s Phase 7c acts on every `_unapplied_decision` hit with no
filter beyond the detector itself, so it will still rewrite correct prose on residual cases this fix
leaves in place — the exact failure ENH-3280 states this issue is a hard prerequisite to prevent.
ENH-3280 must account for this residual before Phase 7c ships.

## Status

**Open** | Created: 2026-08-21 | Priority: P2

_(Footer corrected 2026-08-21, epic review — read `P3`, contradicting the frontmatter, the filename,
and the Impact bullet, all of which record the raise to P2 as the `blocked_by` prerequisite of
ENH-3280.)_


## Session Log
- `/ll:manage-issue` - 2026-08-23T01:16:30 - `9bb27d14-2ec6-4493-aa41-2f8eebadcfe8.jsonl`
- `/ll:ready-issue` - 2026-08-23T01:02:51 - `836be84d-5cca-4649-a6a6-ab8992e3fb30.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-22T22:31:16 - `ccec33f2-1527-4aff-b9d7-1a9165839f2e.jsonl`
- `/ll:confidence-check` - 2026-08-21T23:23:24 - `6c8de875-3d34-466f-bb1f-5d9046d922b9.jsonl`
- `/ll:decide-issue` - 2026-08-21T23:04:25 - `570c3914-e306-4cb1-bfda-e25386251081.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-21T19:06:56 - `8c9f6596-f570-42d1-a2a2-c4e750b706f8.jsonl`
- `/ll:capture-issue` - 2026-08-21T19:00:46 - `f4a44238-acd8-4729-ac3b-34de58926055.jsonl`
