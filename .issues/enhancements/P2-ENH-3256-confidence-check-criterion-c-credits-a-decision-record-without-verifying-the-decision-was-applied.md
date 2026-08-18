---
id: ENH-3256
type: ENH
title: confidence-check Criterion C credits a decision record without verifying the
  decision was applied
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-18'
captured_at: '2026-08-18T20:48:19Z'
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
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 15
score_change_surface: 20
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

Proposed direction: when an issue contains a `### Decision Rationale` with a
selected option, cap Criterion C unless the selected option's key identifiers
appear in the Proposed Solution / Program Design / Acceptance Criteria — or
route the mismatch to `/ll:reconcile-issue`, which already exists to rewrite
directive sections from findings.

Related: BUG-3249 (the instance), ENH-3250 (same blind-spot family, but targets
the loop's missing prescriptive-review state rather than the rubric),
ENH-2852 (built the Phase 1.6 pre-fetch gate this extends).


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

**Option A**: Cap Criterion C unless the selected option's key identifiers
appear in Proposed Solution / Program Design / Acceptance Criteria.

> **Selected:** Option A — reuses established `issue_parser` gap-detection patterns (unmarked_superseded_directive, Criterion 4 cap); avoids scope violation that BUG-3002 already rejected.

**Option B**: Route the mismatch to `/ll:reconcile-issue`, which already
exists to rewrite directive sections from findings.

A relevant constraint for whichever route is chosen: `/ll:reconcile-issue`'s
own documented rewrite scope is `## Implementation Steps`, `## Acceptance
Criteria`, `## Integration Map`, and conditionally `## Scope Boundaries`
(`commands/reconcile-issue.md:44-60`) — `## Proposed Solution`, where
`### Decision Rationale` and the `> **Selected:**` callout actually live
(`skills/decide-issue/SKILL.md:388,391,407`), is not in that enumerated
list. Option B as stated would route to a command whose rewrite scope does
not cover the section carrying the signal being checked.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — Criterion C (Ambiguity) detection logic; currently three pure text scans of the issue body (ambiguity-indicator phrases, unresolved alternatives in Proposed Solution, hedge phrases) with no read of `### Decision Rationale` or `> **Selected:**`
- `skills/confidence-check/rubric.md:307-314` — Criterion C scoring table; the "No ambiguity" row (25 pts) has no gap-key precondition, unlike Criterion 4's Parity/Claim Cap row

### Dependent Files (Callers/Importers)
- `skills/decide-issue/SKILL.md:383-409` — Phase 6/7a writes the `> **Selected:** [option title]` callout and `### Decision Rationale` subsection, scoped only to `## Proposed Solution`; never touches `## Program Design`, `## Implementation Steps`, or `## Acceptance Criteria`. Idempotency rule (`:409`): if `### Decision Rationale` already exists, the annotation write is skipped — so a later edit that diverges the directive sections from the recorded `**Selected**` is never re-detected by `decide-issue` itself.
- `scripts/little_loops/issue_parser.py:576` `design_gate_failed(gaps: FormatGaps) -> bool` — the deterministic gate `ll-issues check-design` delegates to; checks only `program_design_nonspecific` and Program Design presence, never Decision Rationale propagation
- `scripts/little_loops/issues/program_design.py:348-387` `grade_program_design()` — grades `## Program Design` as `is_specific` iff it has a signature-shaped line and a resolvable Call Path anchor; per its own docstring "Known limit" (`:22-31`), any repo-resolvable symbol satisfies it regardless of relevance to the issue's actual decision

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_parser.py:1942-1975` `_RESOLVED_OPTION_MARKER_RE`, `_is_option_resolved(block_body)` — the exact `### Decision Rationale` / `> **Selected:**` detection primitive Option A's Decision Rationale (line 125) cites for reuse; already exists and is unit-tested, no new regex needed
- `scripts/little_loops/loops/autodev.yaml:653,1296-1309,2169-2172` — reads `score_ambiguity` as a decidability proxy (`<= 10 OR decision_needed` routes to `resolve_decision_direct`; a separate remedy classifier at `:2169` compares `amb` against other subscores to pick `spike` vs `reconcile`). A cap that lowers Criterion C for decision-drift issues changes which branch autodev takes here — no code change required, but the routing behavior shifts and should be verified post-fix
- `scripts/little_loops/loops/rn-remediate.yaml:68,367,384-389` — `AMBIGUITY=$(... jq -r '.score_ambiguity // 0')`; `diagnose_ambiguity_threshold: 15` gates a `WIRE`-token route to `/ll:wire-issue`. Same downstream-consumer risk as autodev.yaml above
- `skills/issue-workflow/SKILL.md:84-85` — prose duplicate of the `score_ambiguity ≤ 10` / `> 10` escalation thresholds Criterion C's rubric row encodes; not a `{{...}}` include, so a semantic change to what the top score means needs a matching prose edit here too
- `skills/issue-size-review/SKILL.md:166` — qualitative-skip guard requires `score_ambiguity ≥ 18` (with `score_complexity ≥ 18`) to skip decomposition; if the cap prevents Criterion C reaching 18-25 for decision-drift issues, this guard's trigger rate changes even though its code is untouched

### Conventions in Force
- Gap signals extracted once from an already-fetched JSON payload cap (never escalate to STOP) a specific criterion — evidence: `PARITY_GAP`/`CLAIM_GAP` capping Criterion 4 at 10 (`skills/confidence-check/SKILL.md:187-207`, `rubric.md:241-256`), explicitly documented as "a ceiling, never a floor" and "not... a STOP verdict"
- A precedent for reading one section's recorded finding and checking whether it was propagated into the directive sections already exists for a different signal: `unmarked_superseded_directive` fires when `### Codebase Research Findings` contains a correction phrase but none of the directive sections carry a `⚠ Superseded` marker (`scripts/little_loops/issue_parser.py:1071-1074`) — no equivalent exists for `### Decision Rationale`
- `/ll:reconcile-issue` is cited elsewhere as the remedy for directive-section drift, always as a prose aside rather than an automatic call (`skills/confidence-check/SKILL.md:361`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:320`) — see Proposed Solution above for the scope caveat this raises for Option 2

### Tests
- `scripts/tests/test_confidence_check_skill.py` — structural tests for the confidence-check skill (phase layout, rubric references)
- `scripts/tests/test_ll_issues_check_design.py`, `scripts/tests/test_program_design_gate.py` — design gate tests; neither currently exercises Decision Rationale propagation

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_confidence_check_skill.py:502-578` `TestConfidenceCheckClaimParityPrefetch`, `TestConfidenceCheckRubricClaimParityCap` — the exact pattern to mirror for the new cap: `_phase_text()`/rubric-section-slice helpers, heading-existence assertion, gap-key-named assertion, "advisory/cap not STOP" assertion, and a `test_phase_3_does_not_name_*` negative check
- `scripts/tests/test_issue_parser_unresolved.py:157-235` `TestCountUnresolvedOptions` — existing unit tests for `_RESOLVED_OPTION_MARKER_RE`/`_is_option_resolved`, the detection primitive this fix reuses
- `scripts/tests/test_autodev_loop.py:595,638-881`, `scripts/tests/test_rn_remediate.py:397`, `scripts/tests/test_issue_size_review_skill.py:79-130` — hardcode `score_ambiguity` fixture values/thresholds (`5`, `18`, `20`) at exactly the boundary this cap changes the meaning of; not expected to break (no shape change) but worth re-running after implementation to confirm no regression

### Documentation
- N/A — no doc updates identified beyond the skill/rubric files themselves

_Wiring pass added by `/ll:wire-issue`:_
- Host skill mirrors `.gemini/skills/confidence-check/`, `.kimi-code/skills/confidence-check/`, `.qwen/skills/confidence-check/` (both `SKILL.md` and `rubric.md`) are git-tracked verbatim copies enforced by `scripts/tests/test_wiring_skills_and_commands.py:413-443` (`test_skill_mirrors_carry_companions`, generic over `SKILL_MIRROR_ROOTS`). After editing `skills/confidence-check/SKILL.md`/`rubric.md`, run `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply && ll-adapt --host qwen --apply` or the mirror-companion test fails on drift.

### Configuration
- N/A

### Decision Rationale

Option A was selected because it composes existing, proven patterns in the `issue_parser` module (`unmarked_superseded_directive`, `_heading_bodies`, marker regex from `_RESOLVED_OPTION_MARKER_RE`) with the established Criterion 4 gap-cap approach (SKILL.md:187-207, rubric.md:241-256). The implementation is low-risk (scoped to confidence-check only, cap-never-STOP semantics), testable (deterministic text scanning), and requires ~20 lines of new code.

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
- `design_gate_failed(gaps: FormatGaps) -> bool` — current deterministic gate (`scripts/little_loops/issue_parser.py:576`); reads only `program_design_nonspecific` and Program Design presence, never Decision Rationale propagation
- `grade_program_design(body: str, resolver: Resolver) -> DesignVerdict` — shape/specificity grading only (`scripts/little_loops/issues/program_design.py:348`), no comparison against `### Decision Rationale`

### Call Path
`decide_issue` writes `> **Selected:**` + `### Decision Rationale`, scoped only to `## Proposed Solution` (`skills/decide-issue/SKILL.md:388-409`) -> confidence-check Criterion C detection reads the issue body for ambiguity phrases, never `### Decision Rationale` (`skills/confidence-check/SKILL.md`) -> rubric.md's Criterion C table awards 25 with no gap-key precondition -> gate check via `design_gate_failed` -> `grade_program_design` (shape/specificity only, both defined above)

### Decision Rules
N/A — the Summary names two directions (cap Criterion C vs. route to
reconcile-issue) but neither is pinned to exact inputs/thresholds yet; see
Proposed Solution above.

## Implementation Steps

1. Criterion C's scoring must account for whether a recorded `### Decision
   Rationale` selection is reflected outside `## Proposed Solution` — the
   gap today is that `skills/confidence-check/SKILL.md`'s three ambiguity
   checks never read that block.
2. Whichever mechanism is chosen must not rely on `/ll:reconcile-issue`
   alone if the check needs to act on `## Proposed Solution` content, since
   that section is outside reconcile's documented rewrite scope
   (`commands/reconcile-issue.md:44-60`).
3. `python -m pytest scripts/tests/test_confidence_check_skill.py -v` passes,
   and a new test exercises an issue carrying a `### Decision Rationale`
   whose selection is not reflected in Program Design/Implementation
   Steps/Acceptance Criteria.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Current Pain Point

## Success Metrics

## Scope Boundaries

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


## Session Log
- `/ll:confidence-check` - 2026-08-18T22:04:27 - `bb66018c-ab8d-4e0a-a8d9-81ae552f7d58.jsonl`
- `/ll:wire-issue` - 2026-08-18T22:00:39 - `b37bf726-239f-4f1a-b2e3-9f5b456cd984.jsonl`
- `/ll:decide-issue` - 2026-08-18T21:54:55 - `566f5be8-a458-4a02-9f56-cd168a320037.jsonl`
- `/ll:refine-issue` - 2026-08-18T21:39:54 - `1598a616-9bb3-45c4-9fb9-f9f87bed73c9.jsonl`
- `/ll:capture-issue` - 2026-08-18T20:48:46 - `fdfd9556-8841-4d2f-baeb-50bd68feb80e.jsonl`
