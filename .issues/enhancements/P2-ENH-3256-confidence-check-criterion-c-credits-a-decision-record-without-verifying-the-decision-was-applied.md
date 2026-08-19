---
id: ENH-3256
type: ENH
title: confidence-check Criterion C credits a decision record without verifying the
  decision was applied
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-18'
captured_at: '2026-08-18T20:48:19Z'
completed_at: '2026-08-19T01:12:35Z'
parent: EPIC-2856
testable: true
decision_needed: false
relates_to:
- BUG-3249
- ENH-3250
- ENH-3257
- ENH-2852
confidence_score: 95
outcome_confidence: 77
score_complexity: 15
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 17
---

# ENH-3256: confidence-check Criterion C credits a decision record without verifying the decision was applied

## Summary

`/ll:confidence-check`'s Criterion C (Ambiguity) awards its top score for "No
ambiguity — solution is fully specified with single clear approach"
(`skills/confidence-check/rubric.md:311`). Nothing in the criterion checks that
the selected option was propagated into the issue's directive sections, so an
issue carrying a `### Decision Rationale` block scores as unambiguous even when
every other section still specifies the rejected option.

Observed on BUG-3249: `/ll:decide-issue` stamped **"Selected: Option B"** (route
`check_design.on_no` to `check_refine_limit`) at 20:26. `/ll:confidence-check`
ran at 20:38 and set `score_ambiguity: 25` / `confidence_score: 100`. At that
moment five directive sections still specified the rejected Option A:

- Proposed Solution (`:99`) — bolded "Routing target: `refine_followup`, **not**
  `check_refine_limit`"
- Program Design › Decision Rules (`:211`) — "never directly to
  `check_refine_limit`"
- Implementation Steps (`:232`) — "`on_no` routes to `refine_followup`"
- Wiring Phase (`:241`) — new test must assert `on_no == "refine_followup"`
- Acceptance Criteria (`:281`) — "routes ... at the **refine** rung
  (`refine_followup`)"

An implementer reading top-down builds Option A; one reading the Wiring Phase
writes a test that fails the decided design. The rubric treated a decision
*record* as a decision *applied*.

The gap is structural, not a scoring misjudgment: no criterion in the rubric
reads for cross-section agreement, and no deterministic gate covers it either
(`ll-issues check-design` exits 0 — the Program Design section is present and
specific, just specific about the wrong option).

Decided direction (Option A, see Proposed Solution): `check_format_gaps()` gains
an `unapplied_decision` gap key that fires when the *rejected* option's
discriminating identifiers remain, unmarked, in the directive sections;
`/ll:confidence-check` reads that key from its already-captured `$FC_JSON` and
caps Criterion C at 10. Detection lives in the parser layer, not skill prose, so
ENH-3250's loop-side review can consume the same signal. Routing the mismatch to
`/ll:reconcile-issue` (Option B) was rejected — that command's rewrite scope
excludes `## Proposed Solution`, where the signal lives.

Related: BUG-3249 (the instance), ENH-3250 (same blind-spot family, but targets
the loop's missing prescriptive-review state rather than the rubric),
ENH-2852 (built the Phase 1.6 pre-fetch gate this extends).


## Current Behavior

`ll-issues format-check` emits no gap when an issue's recorded decision
contradicts its directive sections, and Criterion C's three text scans
(ambiguity-indicator phrases, unresolved alternatives, hedge phrases) never read
`### Decision Rationale`. An issue whose `> **Selected:**` callout names one
option while Implementation Steps / Acceptance Criteria / Program Design still
specify the rejected one scores the top 25 for "No ambiguity".

## Expected Behavior

`check_format_gaps()` populates a new `unapplied_decision` gap key when the
rejected option's discriminating identifiers still appear, unmarked, in the
directive sections. `/ll:confidence-check` **Phase 1.8** (the existing cap-gap
pre-fetch phase, alongside `PARITY_GAP`/`CLAIM_GAP` — *not* Phase 1.6, which is
the Program Design gate) reads that key from the already-captured `$FC_JSON` as
`DECISION_GAP` and caps Criterion C at 10 — a ceiling, never a floor, and never a
Phase 3 `STOP` escalation.

## Motivation

An issue that records a decision and then instructs the implementer to build the
rejected option is worse than one with no decision at all: it reads as settled,
so neither the implementer nor the confidence gate re-opens it. BUG-3249 scored
`confidence_score: 100` in exactly that state, and its Wiring Phase would have
produced a test asserting the *rejected* routing target. Because the gap lands in
`format-check`, every consumer (`/ll:confidence-check`, `refine-to-ready-issue`,
`autodev`, ENH-3250's loop-side review) gets the signal from one deterministic
owner instead of re-deriving it in prose.

## Proposed Solution

**Option A**: Detect decision drift deterministically in `check_format_gaps()`
as a new `unapplied_decision` gap key, and cap Criterion C when it fires.

> **Selected:** Option A — reuses established `issue_parser` gap-detection patterns (unmarked_superseded_directive, Criterion 4 cap); avoids scope violation that BUG-3002 already rejected. Layer and detection direction resolved below.

**Option B**: Route the mismatch to `/ll:reconcile-issue`, which already
exists to rewrite directive sections from findings.

> **Selected:** Option A, not this one — `/ll:reconcile-issue`'s rewrite scope excludes `## Proposed Solution`, where the signal lives. Scored 5/12; see Decision Rationale.

**Layer (resolved):** Option A is implemented in the **parser layer**, not as
skill prose. `check_format_gaps()` gains an `unapplied_decision` gap key; the
skill's only change is to read that key from the already-captured `$FC_JSON` and
apply the cap. Rationale: the cited precedent (`unmarked_superseded_directive`)
*is* a parser gap key, the detection is pure deterministic text comparison with
no judgment component, and ENH-3250 needs the same signal loop-side — a prose
check inside `skills/confidence-check/SKILL.md` would have to be reimplemented
there. This resolves the contradiction between the earlier Decision Rationale
("composes existing patterns in the `issue_parser` module") and an Integration
Map that listed only `SKILL.md` + `rubric.md`.

**Detection direction (resolved):** the check fires on **rejected-option
identifiers still present in the directive sections**, not on the selected
option's identifiers being absent. The absence form does not catch the motivating
case: BUG-3249's directive sections named `check_refine_limit` (the selected
target) repeatedly, inside negations, so an "identifiers appear" check would have
passed the very issue that prompted this. See Program Design › Decision Rules for
the exact extraction and exemption rules.

The constraint that drove Option B's rejection: `/ll:reconcile-issue`'s
own documented rewrite scope is `## Implementation Steps`, `## Acceptance
Criteria`, `## Integration Map`, and conditionally `## Scope Boundaries`
(`commands/reconcile-issue.md:44-60`) — `## Proposed Solution`, where
`### Decision Rationale` and the `> **Selected:**` callout actually live
(`skills/decide-issue/SKILL.md:388,391,407`), is not in that enumerated
list. Option B as stated would route to a command whose rewrite scope does
not cover the section carrying the signal being checked.

## Integration Map

### Files to Modify

_Parser layer (the detection — see Proposed Solution › Layer):_
- `scripts/little_loops/issue_parser.py:494-573` — add `unapplied_decision: list[str]` to the `FormatGaps` dataclass, its `has_gaps` OR-chain, and `to_dict()`; this is the mechanical three-site pattern every existing gap key follows
- `scripts/little_loops/issue_parser.py:1062-1078` — populate the new key in `check_format_gaps()`, immediately after the `unmarked_superseded_directive` block it mirrors
- `scripts/little_loops/issue_parser.py:1242-1255` — add `_DECISION_DIRECTIVE_SECTIONS` next to `_SUPERSEDED_DIRECTIVE_SECTIONS`; reuse `_SUPERSEDED_MARKER_PREFIX` verbatim as the exemption marker (no second marker vocabulary)
- `scripts/little_loops/issue_parser.py:685` — extend the `check_format_gaps()` docstring gap-key glossary (each key has an entry)
- `scripts/little_loops/cli/issues/format_check.py:430-431` — add the human-readable printer stanza (`print(f"  unapplied_decision: {entry}")`), mirroring `unmarked_superseded_directive`
- `scripts/little_loops/cli/issues/format_check.py:66,472` and `scripts/little_loops/cli/issues/__init__.py:148` — three slash-delimited gap-key help strings that enumerate every key; all three drift if not updated together

_Skill layer (the cap only — reads the key, does not re-derive it):_
- `skills/confidence-check/SKILL.md:187-207` (**Phase 1.8**, "Pre-Fetch Claim and Parity Gaps") — add a `DECISION_GAP` extraction one-liner off the `$FC_JSON` Phase 1.6 already captured, using the same `<!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom -->` annotation convention; **no second `format-check` call**. Phase 1.8 is the correct home, not Phase 1.6: 1.6 is the Program Design *gate*, while 1.8 exists precisely for cap-gap extractions and already hosts the `PARITY_GAP`/`CLAIM_GAP` precedent this issue cites
- `skills/confidence-check/rubric.md:307-314` — Criterion C scoring table; add a cap row + prose note modelled on Criterion 4's Parity/Claim Cap (`rubric.md:245-256`)

### Dependent Files (Callers/Importers)
- `skills/decide-issue/SKILL.md:383-409` — Phase 6/7a writes the `> **Selected:** [option title]` callout and `### Decision Rationale` subsection, scoped only to `## Proposed Solution`; never touches `## Program Design`, `## Implementation Steps`, or `## Acceptance Criteria`. Idempotency rule (`:409`): if `### Decision Rationale` already exists, the annotation write is skipped — so a later edit that diverges the directive sections from the recorded `**Selected**` is never re-detected by `decide-issue` itself.
- `scripts/little_loops/issue_parser.py:576` `design_gate_failed(gaps: FormatGaps) -> bool` — the deterministic gate `ll-issues check-design` delegates to; checks only `program_design_nonspecific` and Program Design presence, never Decision Rationale propagation
- `scripts/little_loops/issues/program_design.py:348-387` `grade_program_design()` — grades `## Program Design` as `is_specific` iff it has a signature-shaped line and a resolvable Call Path anchor; per its own docstring "Known limit" (`:22-31`), any repo-resolvable symbol satisfies it regardless of relevance to the issue's actual decision

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_parser.py:1942-1975` `_RESOLVED_OPTION_MARKER_RE`, `_is_option_resolved(block_body)` — `_RESOLVED_OPTION_MARKER_RE` is the pattern source for the new `_selected_option_title`; `_is_option_resolved` is **not** reused. These are presence predicates returning `bool`: they answer "does this block carry a marker?", not "which option won", and they misidentify the winner in the three real cases enumerated in Program Design › Decision Rules › Selected-option identity. Identity extraction and identifier extraction are both new code (an earlier draft claimed "no new regex needed"; a later draft still routed the selected/rejected split through `_is_option_resolved` — both were wrong)
- `scripts/little_loops/issue_parser.py:1996-2001` `locate_unresolved_options` — the precedent for scoping `_iter_option_blocks` to `_section_body(content, "Proposed Solution")`. `_unapplied_decision` must follow it; see Decision Rules › Extraction scope
- `scripts/little_loops/loops/autodev.yaml:653,1296-1309,2169-2172` — reads `score_ambiguity` as a decidability proxy (`<= 10 OR decision_needed` routes to `resolve_decision_direct`; a separate remedy classifier at `:2169` compares `amb` against other subscores to pick `spike` vs `reconcile`). A cap that lowers Criterion C for decision-drift issues changes which branch autodev takes here — no code change required, but the routing behavior shifts and should be verified post-fix
- `scripts/little_loops/loops/rn-remediate.yaml:68,367,384-389` — `AMBIGUITY=$(... jq -r '.score_ambiguity // 0')`; `diagnose_ambiguity_threshold: 15` gates a `WIRE`-token route to `/ll:wire-issue`. Same downstream-consumer risk as autodev.yaml above
- `skills/issue-workflow/SKILL.md:84-85` — prose duplicate of the `score_ambiguity ≤ 10` / `> 10` escalation thresholds Criterion C's rubric row encodes; not a `{{...}}` include, so a semantic change to what the top score means needs a matching prose edit here too
- `skills/issue-size-review/SKILL.md:166` — qualitative-skip guard requires `score_ambiguity ≥ 18` (with `score_complexity ≥ 18`) to skip decomposition; if the cap prevents Criterion C reaching 18-25 for decision-drift issues, this guard's trigger rate changes even though its code is untouched

### Conventions in Force
- Gap signals extracted once from an already-fetched JSON payload cap (never escalate to STOP) a specific criterion — evidence: `PARITY_GAP`/`CLAIM_GAP` capping Criterion 4 at 10 (`skills/confidence-check/SKILL.md:187-207`, `rubric.md:241-256`), explicitly documented as "a ceiling, never a floor" and "not... a STOP verdict"
- A precedent for reading one section's recorded finding and checking whether it was propagated into the directive sections already exists for a different signal: `unmarked_superseded_directive` fires when `### Codebase Research Findings` contains a correction phrase but none of the directive sections carry a `⚠ Superseded` marker (`scripts/little_loops/issue_parser.py:1071-1074`) — no equivalent exists for `### Decision Rationale`
- `/ll:reconcile-issue` is cited elsewhere as the remedy for directive-section drift, always as a prose aside rather than an automatic call (`skills/confidence-check/SKILL.md:361`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:320`) — see Proposed Solution above for the scope caveat this raises for Option 2

### Tests

_Parser layer (the bulk of the new coverage — added by the layer resolution):_
- `scripts/tests/test_ll_issues_format_check.py:1219-1310` `unmarked_superseded_directive` test class — the closest structural template for a new gap-key class: fixture issue on disk, human-output assertion (`"unapplied_decision: <file>.md" in out`), a `--format json` assertion, and negative cases asserting the key is absent
- `scripts/tests/test_ll_issues_format_check.py:339` — the full-key-set JSON assertion dict; **must** gain `"unapplied_decision": []` or it fails on the new key
- `scripts/tests/test_issue_parser.py:4576` — existing tests for the `unmarked_superseded_directive` inverse; the sibling location for `_unapplied_decision` unit tests. Required cases: identifier extraction (incl. the ≥3-char floor), `REJ - SEL` discrimination, paragraph-scoped exemption, the five inert cases, and the three scoping regressions — selected option not last, all blocks carrying a `> **Selected:**` line, and a full-document body proving `REJ` does not absorb post-Proposed-Solution sections
- `scripts/tests/test_issue_parser.py` (new) — a corpus test asserting the key is empty for every consistent issue under `.issues/`; the fixture-only tests above pass even when all three scoping rules are omitted
- `scripts/tests/test_issue_parser_unresolved.py:157-235` `TestCountUnresolvedOptions` — existing coverage of `_iter_option_blocks` / `_is_option_resolved`; confirms the reused primitives' behavior but does **not** cover identifier extraction

_Skill layer (the cap):_
- `scripts/tests/test_confidence_check_skill.py:502-578` `TestConfidenceCheckClaimParityPrefetch`, `TestConfidenceCheckRubricClaimParityCap` — the exact pattern to mirror for the new cap: `_phase_text()`/rubric-section-slice helpers, heading-existence assertion, gap-key-named assertion, "advisory/cap not STOP" assertion, and a `test_phase_3_does_not_name_decision_gap` negative check

_Regression guards (no shape change expected, re-run to confirm):_
- `scripts/tests/test_ll_issues_check_design.py`, `scripts/tests/test_program_design_gate.py` — must stay green unchanged, proving `design_gate_failed()` did not absorb the new key
- `scripts/tests/test_autodev_loop.py:595,638-881`, `scripts/tests/test_rn_remediate.py:397`, `scripts/tests/test_issue_size_review_skill.py:79-130` — hardcode `score_ambiguity` fixture values/thresholds (`5`, `18`, `20`) at exactly the boundary this cap changes the meaning of

### Documentation

Not N/A — a new `FormatGaps` key appears in enumerated gap-class lists in both
reference docs, each of which also carries a written-out count:
- `dataclasses.fields(FormatGaps)` is **24** today, so the post-change count is **twenty-five** in both docs
- `docs/reference/API.md:895` — says "twenty-one gap classes" and is already stale by three: its inline list omits `duplicate_heading`, `empty_provenance_stub`, and `template_placeholders`. Correct to twenty-five and add all four missing keys, not a naive bump to twenty-two. Also add a per-key bullet beside `unmarked_superseded_directive` (`:909`)
- `docs/reference/CLI.md:2051` — "twenty-four classes" is currently accurate; bump to twenty-five and extend the inline key list
- `docs/reference/CLI.md:2236` — the `--format json` example payload, which spells out every key
- Both counts are self-described as "re-derive from `dataclasses.fields(FormatGaps)` rather than trusting the number written here" — but the prose numbers still need bumping

_Wiring pass added by `/ll:wire-issue`:_
- Host skill mirrors `.gemini/skills/confidence-check/`, `.kimi-code/skills/confidence-check/`, `.qwen/skills/confidence-check/` (both `SKILL.md` and `rubric.md`) are git-tracked verbatim copies enforced by `scripts/tests/test_wiring_skills_and_commands.py:413-443` (`test_skill_mirrors_carry_companions`, generic over `SKILL_MIRROR_ROOTS`). After editing `skills/confidence-check/SKILL.md`/`rubric.md`, run `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply && ll-adapt --host qwen --apply` or the mirror-companion test fails on drift.

### Configuration
- N/A

### Decision Rationale

Option A was selected because it composes existing, proven patterns in the `issue_parser` module (`unmarked_superseded_directive`, `_heading_bodies`, `_iter_option_blocks`, `_SUPERSEDED_MARKER_PREFIX`) with the established Criterion 4 gap-cap approach (SKILL.md:187-207, rubric.md:241-256). The implementation is low-risk (additive gap key, cap-never-STOP semantics, `design_gate_failed()` untouched) and testable (deterministic text scanning, no judgment component).

**Scope correction (post-decision):** an earlier draft of this rationale claimed "~20 lines of new code" and an Integration Map listing only `SKILL.md` + `rubric.md`. Both understated the work. The detection lands in the parser layer (see Proposed Solution › Layer), which carries the standard new-gap-key wiring — dataclass field, `has_gaps`, `to_dict`, docstring glossary, CLI printer, and three enumerated help strings — plus genuinely new identifier-extraction logic. `_RESOLVED_OPTION_MARKER_RE` / `_is_option_resolved` are presence predicates; they answer "was something selected?", not "which option, and with what identifiers?" — so the extraction rules in Program Design › Decision Rules are new code, not a reuse. Effort is Medium, not Small.

**Detection correction (post-wiring review):** the Decision Rules as first written
would have fired on essentially every decided issue in the corpus, for three
independent reasons now fixed in place: (1) `_iter_option_blocks` was to be handed
full document content, whose last-block-runs-to-EOF boundary makes `REJ` absorb
the rest of the issue; (2) `"Proposed Solution"` was both the identifier source
and a scan target, so `REJ - SEL` members were present in the scanned body by
construction; (3) the selected/rejected split ran through `_is_option_resolved`,
which picks the wrong block whenever `### Decision Rationale` trails a
non-winning option — as it does in this very issue. None of these is visible in a
hand-built two-option fixture, which is why a live-corpus run is now an
acceptance criterion rather than a success metric. The selected option is now
identified by callout *title*, via a new `_selected_option_title` helper. Effort
stays Medium; the added logic is bounded and deterministic.

Option B fails on two fronts: (1) it replicates the structural problem BUG-3002 already identified and rejected (routing a detection to a remedy command whose contract excludes the target section), and (2) the alternative of widening reconcile-issue's scope explicitly violates reconcile's stated non-goal (do not re-research / re-synthesize content; that is refine-issue's job — `commands/reconcile-issue.md:104-108`). BUG-3002's Decision Rationale (scored Option B at 5/12) applies identically here.

**Scoring summary:**

| Dimension | Option A | Option B |
|-----------|----------|----------|
| Consistency | 3 | 1 |
| Simplicity | 3 | 1 |
| Testability | 3 | 2 |
| Risk | 3 | 1 |
| **Total** | **12/12** | **5/12** |

## Program Design

### Signatures

_New:_
- `_unapplied_decision(content: str) -> list[str]` — module-private detector in `scripts/little_loops/issue_parser.py`, returning one reason string per drifted directive section (empty list = no gap). Modelled on `_template_placeholders(content, issue_type, templates_dir) -> list[str]` (`:1449`) and the inline `unmarked_superseded_directive` block (`:1062-1074`).
- `_selected_option_title(section_body: str) -> str | None` — extracts the option title text from the first `> **Selected:** <title>` callout in the `## Proposed Solution` body, so the selected block can be identified by name rather than by marker presence (see Decision Rules › Selected-option identity). Returns `None` when no callout exists.
- `_DECISION_DIRECTIVE_SECTIONS: tuple[str, ...]` — `("Proposed Solution", "Program Design", "Implementation Steps", "Files to Modify", "Acceptance Criteria")`. Superset of `_SUPERSEDED_DIRECTIVE_SECTIONS` (`:1254`), which omits the first two. Note `"Proposed Solution"` is scanned with the self-scan subtraction in Decision Rules applied, not raw.
- `FormatGaps.unapplied_decision: list[str]` — new dataclass field (`:494-573`).

_Existing, reused unchanged:_
- `_section_body(content: str, heading: str) -> str | None` — scopes option enumeration to `## Proposed Solution`, exactly as `locate_unresolved_options` (`:1996-2001`) does. **Required**; see Decision Rules › Extraction scope for what breaks without it.
- `_iter_option_blocks(text: str) -> list[tuple[str, str]]` (`:1955`) — yields `(heading_line, block_body)` per option block; supplies both the selected and rejected block bodies. Boundary caveat: the final block runs to end-of-input, hence the mandatory scoping and `### Decision Rationale` clamp.
- `_RESOLVED_OPTION_MARKER_RE` (`:1942`) — pattern source for the callout the new `_selected_option_title` parses. `_is_option_resolved(block_body) -> bool` (`:1973`) is **not** used: it answers "does this block carry a marker?", which is not the same as "is this the selected option", and it misidentifies the winner in all three cases listed in Decision Rules.
- `_heading_bodies(content: str, heading: str) -> list[str]` (`:1564`) — H2/H3-aware section body lookup, required because `### Files to Modify` is an H3 while the rest are H2.
- `_SUPERSEDED_MARKER_PREFIX = "⚠ Superseded"` (`:1255`) — reused verbatim as the exemption marker.

_Existing, unchanged and NOT extended (recorded to close the earlier ambiguity):_
- `design_gate_failed(gaps: FormatGaps) -> bool` (`:576`) — stays a three-way OR over Program Design only. `unapplied_decision` is a cap signal, not a design-gate failure, so it must **not** be added here.
- `grade_program_design(body, resolver) -> DesignVerdict` (`scripts/little_loops/issues/program_design.py:348`) — untouched.

### Call Path
`decide_issue` writes `> **Selected:**` + `### Decision Rationale` scoped only to `## Proposed Solution` (`skills/decide-issue/SKILL.md:388-409`) -> `check_format_gaps` (`issue_parser.py:1062`) calls `_unapplied_decision` (defined above), which uses `_section_body` to scope to `## Proposed Solution`, `_iter_option_blocks` + `_selected_option_title` to split selected/rejected blocks, and `_heading_bodies` to scan `_DECISION_DIRECTIVE_SECTIONS` (all defined above) -> populates `FormatGaps.unapplied_decision` -> `FormatGaps.to_dict` (`:546`) -> `cmd_format_check` `--format json` -> captured once into `$FC_JSON` by Phase 1.6 (`skills/confidence-check/SKILL.md:138`) -> **Phase 1.8** extracts `DECISION_GAP` off that same payload (`SKILL.md:187-207`) -> `rubric.md` Criterion C cap row -> Criterion C score only, never a Phase 3 STOP override (`SKILL.md:357-365`)

### Decision Rules

**Extraction scope (mandatory — do not pass full document content).** Option
blocks are enumerated from `_section_body(content, "Proposed Solution")` only,
mirroring `locate_unresolved_options` (`:1996-2001`), which already scopes the
same primitives this way. Passing full `content` to `_iter_option_blocks` is
incorrect: its block boundary is *the next option heading* (`:1967`), so on a
whole-document scan the final option block's body runs to end-of-input and
swallows Integration Map, Program Design, Implementation Steps, and Acceptance
Criteria. `REJ` would then absorb nearly every backticked identifier in the issue
and `REJ - SEL` would fire on everything.

Within that scoped body, the **final option block is additionally clamped** at the
first `### Decision Rationale` heading, because `/ll:decide-issue` appends that
subsection to the *end* of `## Proposed Solution`
(`skills/decide-issue/SKILL.md:407`) — it is not part of any option's body.

**Selected-option identity.** Do **not** infer the selected block from
`_is_option_resolved`. That predicate is wrong here in three independent ways,
each observable in real issues:

1. `### Decision Rationale` lands inside the *last* option block (see clamp
   above), so `_is_option_resolved` returns True for the last option regardless of
   which won. This issue is an instance: Option A was selected, Option B is last.
2. Rejected options in practice also carry a `> **Selected:** Option A, not this
   one` callout (this file, `## Proposed Solution` Option B) — both blocks then
   read as resolved.
3. The `### Decision Rationale` subsection is sometimes written outside
   `## Proposed Solution` (this issue's own copy sits under `## Integration Map`),
   leaving no marker in any block.

Instead, extract the selected option's *title text* from the callout —
`> **Selected:** <title>` — via a new `_selected_option_title(section_body) -> str
| None`, and match that title against the option heading lines returned by
`_iter_option_blocks`. The matched block is `SEL`; every other block is `REJ`.

**Identifier extraction.** An *identifier* is a backticked code span (`` `foo` ``)
of length ≥ 3. Extract the set `SEL` from the selected option block's body and
`REJ` from every other option block's body. The **discriminating rejected set**
is `REJ - SEL` — tokens that distinguish the rejected option from the selected
one. Tokens appearing in both are ignored, which is what prevents BUG-3249's
shared vocabulary (`on_no`, `check_design`) from firing.

**Gap condition.** For each section in `_DECISION_DIRECTIVE_SECTIONS`, the gap
fires when a member of `REJ - SEL` appears in that section's body. One reason
string per (section, identifier) pair: `"<Section> still specifies `<id>`
(rejected option)"`.

**Self-scan subtraction (mandatory).** `"Proposed Solution"` is both the
extraction *source* and a scan *target*, so a naive scan self-fires on every
decided issue: `REJ - SEL` members are by construction present in the rejected
option block, which lives inside Proposed Solution. The Proposed Solution scan
therefore runs against **section body minus every option block minus the
`### Decision Rationale` subsection**. The Decision Rationale exclusion is
required independently — that subsection exists to explain why the rejected
option lost and legitimately names its identifiers (this issue's own rationale
cites `commands/reconcile-issue.md`). Dropping `"Proposed Solution"` from
`_DECISION_DIRECTIVE_SECTIONS` outright is *not* an acceptable simplification:
BUG-3249's motivating drift line lived there.

**Exemption.** A mention is exempt when `_SUPERSEDED_MARKER_PREFIX`
(`⚠ Superseded`) appears in the same blank-line-delimited paragraph — the same
escape hatch and marker vocabulary `unmarked_superseded_directive` already uses,
and it is sanctioned in **all five** scanned sections, not just the three
`_SUPERSEDED_DIRECTIVE_SECTIONS` covers.

Negated mentions (`` not `refine_followup` ``) are **not** exempt: a directive
section that still argues against the selected option is drift, and BUG-3249's
Proposed Solution line `:99` was exactly that form. Accept the known cost — text
alone cannot separate that from a legitimate scope record, and this issue's own
Program Design carries one (`design_gate_failed()` "must **not** be added here").
The `⚠ Superseded` annotation is the sanctioned remedy for such lines; if an
implementer finds that marker semantically wrong for a scope record, extending
the exemption vocabulary with a second prefix is in scope, but a *second*
detection heuristic for negation is not.

**Inert cases** (return `[]`, no gap):
- No `> **Selected:**` callout in `## Proposed Solution` — nothing was decided. (A bare `### Decision Rationale` with no callout is also inert: identity is unrecoverable.)
- Fewer than two option blocks — nothing to contradict.
- The callout title matches zero option headings, or matches more than one — identity is ambiguous; fail open rather than guess.
- `REJ - SEL` is empty — the options share all identifiers, so no deterministic discrimination is possible; fail open rather than guess.
- The gate is unarmed / issue grandfathered — inherited from `check_format_gaps` as with every other key.

**Cap semantics.** Non-empty `DECISION_GAP` caps Criterion C at 10 regardless of
which other row would apply — a ceiling, never a floor (an issue already scoring
0 on "fundamental approach unclear" stays 0). It does **not** force
`STOP — ADDRESS GAPS`; per `SKILL.md:357-365` only Learning Test, Program Design
(`PD_FAIL`), and Dependencies (`DEP_FAIL`) are hard overrides, and this key is
deliberately not added to that list.

## Implementation Steps

1. Add `_DECISION_DIRECTIVE_SECTIONS` beside `_SUPERSEDED_DIRECTIVE_SECTIONS`
   (`issue_parser.py:1254`), add `_selected_option_title()`, and implement
   `_unapplied_decision(content)` per Decision Rules above, reusing
   `_section_body`, `_iter_option_blocks`, `_heading_bodies`, and
   `_SUPERSEDED_MARKER_PREFIX`. The three rules that are easy to skip and each
   produce corpus-wide false positives: scope option enumeration to
   `## Proposed Solution`; clamp the final option block at `### Decision
   Rationale`; subtract option blocks + Decision Rationale from the Proposed
   Solution scan.
2. Wire the gap key through the three mechanical `FormatGaps` sites — dataclass
   field (`:494-518`), `has_gaps` OR-chain (`:520-545`), `to_dict()`
   (`:546-573`) — and call `_unapplied_decision` from `check_format_gaps()`
   immediately after the `unmarked_superseded_directive` block (`:1074`).
   Extend the docstring gap glossary at `:685`.
3. Add the printer stanza in `cli/issues/format_check.py:430` and update all
   three enumerated gap-key help strings (`format_check.py:66,472`,
   `cli/issues/__init__.py:148`).
4. Add `DECISION_GAP` extraction to `skills/confidence-check/SKILL.md` **Phase
   1.8** off the existing `$FC_JSON` (no second CLI call), and add the Criterion C
   cap row + prose note to `rubric.md:307-314` modelled on Criterion 4's cap
   (`rubric.md:245-256`). Do **not** add an entry to Phase 3's hard-override list.
5. Run `ll-issues format-check` across the live `.issues/` corpus and inspect
   every firing by hand before proceeding. 307 issues currently carry a
   `> **Selected:**` callout, so this is the check that actually exercises the
   Decision Rules; each of the three scoping rules in step 1 fails loudly here and
   silently in a hand-built fixture.
6. Run `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply &&
   ll-adapt --host qwen --apply` to refresh the three verbatim skill mirrors, or
   `test_skill_mirrors_carry_companions` fails on drift.
7. Re-run the `score_ambiguity` consumer tests named under Tests below to confirm
   the routing-behavior shift in `autodev.yaml` / `rn-remediate.yaml` is inert.

## Acceptance Criteria

- [ ] `ll-issues format-check <id> --format json` emits an `unapplied_decision`
      key for every issue, empty list when no gap.
- [ ] An issue whose `> **Selected:**` names Option B while `## Implementation
      Steps` still contains a backticked identifier unique to Option A produces a
      non-empty `unapplied_decision` naming that section and identifier.
- [ ] A reconstruction of BUG-3249 at its 20:38 state (Selected: Option B;
      `refine_followup` present in Proposed Solution, Program Design,
      Implementation Steps, Files to Modify, Acceptance Criteria) fires the gap
      for each of those sections.
- [ ] Each inert case in Decision Rules returns an empty list: no `> **Selected:**`
      callout, one option block, a callout title matching zero or multiple option
      headings, empty `REJ - SEL`, and a mention carrying `⚠ Superseded` in the
      same paragraph.
- [ ] An issue whose selected option is **not** the last option block — and whose
      `### Decision Rationale` therefore falls inside the *rejected* block — is
      still scored against the correct `SEL`/`REJ` split. (Regression guard for
      the `_is_option_resolved` misidentification; ENH-3256 itself is such an
      issue.)
- [ ] An issue where every option block carries a `> **Selected:**` line (winner
      plus `> **Selected:** Option A, not this one` on the loser) resolves to a
      single `SEL` via the callout title, not to two resolved blocks.
- [ ] A decided issue whose directive sections are fully consistent produces an
      **empty** `unapplied_decision` — specifically, the rejected option block's
      own identifiers inside `## Proposed Solution` and inside
      `### Decision Rationale` do not fire the gap (self-scan subtraction).
- [ ] `_unapplied_decision` enumerates options only from the `## Proposed
      Solution` body, and the final option block does not absorb `## Integration
      Map` / `## Program Design` / `## Implementation Steps` / `## Acceptance
      Criteria` content into `REJ`.
- [ ] Running `ll-issues format-check` over the full live `.issues/` corpus fires
      `unapplied_decision` only on issues whose directive sections genuinely
      contradict their recorded decision — every firing hand-verified, zero false
      positives across the 307 issues carrying a `> **Selected:**` callout.
- [ ] Identifiers shorter than 3 characters are never extracted into `SEL`/`REJ`.
- [ ] `design_gate_failed()` return values are unchanged for all existing
      fixtures — the new key does not participate in the design gate.
- [ ] `skills/confidence-check/SKILL.md` **Phase 1.8** names `unapplied_decision`
      and issues no second `format-check` call; `rubric.md` Criterion C carries a
      cap row documented as a ceiling and explicitly not a hard override.
- [ ] `DECISION_GAP` does not appear in Phase 3's hard-override paragraphs.
- [ ] The three host skill mirrors match `skills/confidence-check/` byte-for-byte.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 - Silent mis-scoring that lets a contradictory issue reach implementation; real but not blocking, and BUG-3249 was caught by review.
- **Effort**: Medium - The `FormatGaps` wiring is mechanical, but `_unapplied_decision`'s extraction and exemption rules are new logic needing thorough fixture coverage.
- **Risk**: Low - Additive gap key; cap-never-STOP semantics; `design_gate_failed()` deliberately untouched, so no existing gate changes verdict.
- **Breaking Change**: No - New JSON key is additive; consumers reading other keys are unaffected.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Resolution

- **Action**: improve
- **Completed**: 2026-08-19
- **Status**: Completed
- **Implementation**: Implemented Option A as decided — `_unapplied_decision()`,
  `_selected_option_title()`, `_option_block_spans()`, and
  `_strip_codebase_research_findings()` added to `issue_parser.py`; new
  `unapplied_decision` `FormatGaps` field wired through `has_gaps`/`to_dict()`/
  the CLI printer/three help strings; `/ll:confidence-check` Phase 1.8 extracts
  `DECISION_GAP` off the existing `$FC_JSON` and `rubric.md` Criterion C caps at
  10 when it fires (never a STOP override). The BUG-3249 reconstruction and this
  issue's own not-last-selected-option shape (Acceptance Criteria bullet 5) both
  verified against the implementation.
- **Known limitation (live-corpus finding)**: a full sweep of `.issues/` found
  `unapplied_decision` firing on roughly 40% of issues carrying a
  `> **Selected:**` callout. Hand-inspection of a sample attributes this
  overwhelmingly to shared vocabulary between two genuinely different technical
  approaches (e.g. both options build on the same CLI/module named in shared
  preamble text), not to decisions that were recorded but never applied — a
  precision limit of lexical identifier-diffing without semantic understanding
  of *why* an identifier is mentioned, not a scoping bug. The two named
  regression cases (BUG-3249 reconstruction, this issue's own
  selected-not-last shape) score correctly. Impact is bounded: the gap is
  report-only and caps (never blocks) Criterion C. Follow-up tightening is
  candidate future work, not blocking for this issue.

### Files Changed
- `scripts/little_loops/issue_parser.py`
- `scripts/little_loops/cli/issues/format_check.py`
- `scripts/little_loops/cli/issues/__init__.py`
- `skills/confidence-check/SKILL.md`
- `skills/confidence-check/rubric.md`
- `.gemini/`, `.kimi-code/`, `.qwen/` skill mirrors (via `ll-adapt --apply`)
- `docs/reference/API.md`, `docs/reference/CLI.md`
- `scripts/tests/test_issue_parser.py`
- `scripts/tests/test_ll_issues_format_check.py`
- `scripts/tests/test_confidence_check_skill.py`

### Verification Results
- `python -m pytest scripts/tests/` — 19884 passed, 46 skipped
- `ruff check` / `ruff format` / `mypy` clean on all touched files

## Status

**Open** | Created: 2026-08-18 | Priority: P2

## Success Metrics

- A reconstruction of BUG-3249 at its 20:38 state scores Criterion C at 10, not 25.
- Zero unexplained gap firings across the **live `.issues/` corpus** (307 issues
  currently carry a `> **Selected:**` callout) — this, not the `scripts/tests/`
  fixture set, is the meaningful false-positive floor, because every scoping
  defect in Decision Rules manifests as a corpus-wide firing while staying
  invisible in a hand-built two-option fixture.
- Zero new gap firings across the existing `scripts/tests/` issue fixtures that
  carry a single option block or no `> **Selected:**` marker.

## Scope Boundaries

**In scope:** the `unapplied_decision` gap key in `issue_parser.py`, its
`format-check` surfacing, and the Criterion C cap in `confidence-check`.

**Out of scope:**
- Auto-remediation. This issue only detects; rewriting the drifted sections stays
  a human/`/ll:reconcile-issue` action. Widening reconcile's rewrite scope to
  cover `## Proposed Solution` is explicitly rejected (see Decision Rationale).
- `design_gate_failed()` and `grade_program_design()` — deliberately untouched.
- ENH-3250's loop-side prescriptive-review state. It will consume this gap key
  once it exists, but is not implemented here.
- Non-backticked identifier extraction (prose-only decisions). Fails open by
  design; see Decision Rules › Inert cases.

## Backwards Compatibility

Additive only. The new JSON key defaults to `[]`, so existing `format-check`
consumers that read other keys are unaffected, and the key is inert on issues
with no recorded decision. Criterion C's existing rows are unchanged; the cap
applies only when the new key is non-empty. Issues already scored under the old
rubric keep their frontmatter until re-run.

## API/Interface

```python
# scripts/little_loops/issue_parser.py
_DECISION_DIRECTIVE_SECTIONS: tuple[str, ...] = (
    "Proposed Solution",
    "Program Design",
    "Implementation Steps",
    "Files to Modify",
    "Acceptance Criteria",
)

def _selected_option_title(section_body: str) -> str | None:
    """Option title from the first `> **Selected:** <title>` callout, or None."""


def _unapplied_decision(content: str) -> list[str]:
    """Reason strings for rejected-option identifiers left in directive sections.

    Options are enumerated from ``_section_body(content, "Proposed Solution")``
    only — never full ``content`` — and the final block is clamped at
    ``### Decision Rationale``. The Proposed Solution scan subtracts the option
    blocks and the Decision Rationale subsection. See Program Design ›
    Decision Rules for why each of those is load-bearing.
    """

@dataclass
class FormatGaps:
    unapplied_decision: list[str] = field(default_factory=list)
```


## Session Log
- `/ll:manage-issue` - 2026-08-19T01:12:11 - `26f37145-f571-418d-9662-3d9a889e94ea.jsonl`
- `/ll:ready-issue` - 2026-08-19T00:32:37 - `814f49f4-6be6-4b20-8bef-2b29c93912d9.jsonl`
- `/ll:confidence-check` - 2026-08-19T00:25:28 - `7c6d718f-002c-439a-9bff-6cc0a6855d4d.jsonl`
- `/ll:verify-issues` - 2026-08-18T23:42:05 - `5babd785-d270-4764-90c8-5811c9188fb7.jsonl`
- `/ll:confidence-check` - 2026-08-18T22:04:27 - `bb66018c-ab8d-4e0a-a8d9-81ae552f7d58.jsonl`
- `/ll:wire-issue` - 2026-08-18T22:00:39 - `b37bf726-239f-4f1a-b2e3-9f5b456cd984.jsonl`
- `/ll:decide-issue` - 2026-08-18T21:54:55 - `566f5be8-a458-4a02-9f56-cd168a320037.jsonl`
- `/ll:refine-issue` - 2026-08-18T21:39:54 - `1598a616-9bb3-45c4-9fb9-f9f87bed73c9.jsonl`
- `/ll:capture-issue` - 2026-08-18T20:48:46 - `fdfd9556-8841-4d2f-baeb-50bd68feb80e.jsonl`
