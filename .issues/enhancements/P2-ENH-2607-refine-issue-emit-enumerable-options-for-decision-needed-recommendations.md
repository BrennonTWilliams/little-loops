---
id: ENH-2607
title: refine-issue should emit enumerable options when depositing a decision recommendation
type: ENH
status: open
priority: P2
captured_at: '2026-07-11T18:07:11Z'
discovered_date: '2026-07-11'
discovered_by: capture-issue
relates_to:
- BUG-2605
- BUG-2606
- ENH-2443
labels:
- refine-issue
- decision-gate
- skills
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-2607: refine-issue should emit enumerable options when depositing a decision recommendation

## Summary

`/ll:refine-issue --auto`'s "Option-Count Detection" step
(`commands/refine-issue.md:284-296`) only sets `decision_needed: true` when it
detects 2+ options matching one of three formal patterns (numbered top-level
items, `### Option A/B/C` headers, or `**Option A/B**` bold labels). When a
research pass identifies competing alternatives but writes them as inline
prose with a recommendation (e.g. "Two viable resolutions: (a) ... or (b) ...
Recommendation: X for v1" — the actual shape of ENH-2492's stuck decision),
none of the three patterns match, so `decision_needed` is left as whatever it
already was. Combined with the Preservation Rule (`refine-issue.md:307-323`,
"append, don't replace, when a section already has meaningful content"),
subsequent refine passes never restructure that prose into a machine-decidable
shape — the issue can cycle through refine indefinitely without ever
acquiring real `### Option A/B` blocks.

## Current Behavior

`ll-issues check-decidable` reports `OPTIONS_MISSING` for ~40 of ~70 issues
currently flagged `decision_needed: true` in this repo's own backlog — the
large majority of them contain a clear prose recommendation naming named
alternatives (matching decide-issue's own Phase 3b Pattern D shape) but never
in a form `count_enumerable_options()` (Patterns 1-4,
`scripts/little_loops/issue_parser.py:285-307`) recognizes.

## Expected Behavior

When refine-issue's research pass (Step 5a / Enrichment Rules) identifies a
decision point with named alternatives — whether from fresh research or from
existing prose it's about to append findings near — it formats the
alternatives using one of the three recognized patterns (bold `**Option A**`
labels are the lowest-friction fit for inline recommendations) rather than
leaving them as unstructured prose. This makes `decision_needed: true`
issues machine-decidable by construction, closing the gap that BUG-2605 and
BUG-2606 currently have to work around after the fact.

## Motivation

BUG-2605 and BUG-2606 fix the *consumption* side (the FSM and the decide-issue
skill both now get more chances to salvage a prose-only decision). This issue
fixes the *production* side: if refine-issue reliably deposits options in a
recognized shape to begin with, decide-issue's Phase 3b provisional-scan
fallback becomes a safety net instead of the primary mechanism, and future
issues don't join the backlog of ~40 stuck ones. Root-causing this prevents
the failure class from recurring as new issues get refined, rather than only
treating issues already in the backlog.

## Proposed Solution

Extend the "Option-Count Detection" enrichment rule
(`commands/refine-issue.md:284-296`) with a fourth case: when the research
pass is about to write a decision point that names 2+ concrete alternatives
(the same shape decide-issue's Phase 3b Pattern D already looks for — a
recommendation naming one option among several named alternatives), format it
as:

```markdown
**Option A**: [first alternative, verbatim from the research/existing text]

**Option B**: [second alternative, verbatim from the research/existing text]

**Recommended**: Option [X] — [existing rationale, preserved verbatim]
```

placed under the relevant subsection (e.g. as a `### Codebase Research
Findings` addendum near the original prose, per the existing Preservation
Rule — this is additive, not a rewrite of the original text) so
`count_enumerable_options()` picks it up via the `**Option A**` bold-label
pattern (Pattern 2) without requiring any parser changes.

This is scoped to refine-issue's *own* freshly-written research content —
it does not retroactively rewrite pre-existing human-authored prose it
didn't write, consistent with the Preservation Rule.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Format confirmed against the actual regex**: Pattern 2 in
  `scripts/little_loops/issue_parser.py:274`
  (`^\*\*Option\s+[A-Za-z0-9]+.*?\*\*`, `re.MULTILINE`) matches the proposed
  `**Option A**: [text]` shape without modification — the lazy `.*?` closes
  the bold span immediately after the letter (`**Option A**`), so the colon
  falling outside the bold span is irrelevant to the match. Verified against
  the existing fixture shape in
  `scripts/tests/test_issue_parser_unresolved.py:84-97`
  (`test_bold_option_label_format`, using `**Option A: Inline rewriting.**`)
  — both the fixture's inline-colon style and this issue's outside-colon
  style match Pattern 2 identically.
- **Placement plan confirmed against the fallback-widening logic**:
  `count_enumerable_options()` (`scripts/little_loops/issue_parser.py:294-307`)
  first scans `## Proposed Solution`; if that yields 0, it widens to
  `_OPTION_FALLBACK_SECTIONS = ("Codebase Research Findings",
  "Implementation Status")` (line 282). This confirms the plan to place the
  `**Option A/B**` block under a `### Codebase Research Findings` addendum
  (rather than editing `## Proposed Solution` directly) will be picked up by
  the same detector without needing a widened section list.
- **Related but out-of-scope drift**: `commands/refine-issue.md`'s own
  "Option-Count Detection" section (lines 286-289) documents only 3 pattern
  families (numbered items, `### Option` headers, `**Option**` bold labels).
  `issue_parser.py`'s actual `_OPTION_PATTERNS` (lines 273-280) has a 4th
  tier — bullet-list `- (a) ...` / `- **Option A**` (Pattern 4,
  `issue_parser.py:277-279`) — that the command's own instructions never
  mention. Not a blocker for this fix (which targets bold-label Pattern 2
  specifically), but the two artifacts have drifted; worth a follow-on issue
  if the command's documented pattern list should stay in sync with the
  parser's.
- **Consumption-side limitation confirmed**: `skills/decide-issue/SKILL.md`
  Phase 3b's "Provisional Pattern D" (lines 242-249) only *resolves* a
  decision when the referenced options already exist as formal Pattern-4
  bullets elsewhere in the document — its own "Requirement" line states the
  referent must already be a bullet option in `## Proposed Solution` or
  `## Codebase Research Findings`. It does not extract options from
  unstructured prose itself. This confirms the issue's own Motivation
  section: BUG-2605/BUG-2606 fixed the consumption side (giving Pattern D
  more chances to run), but only a production-side fix like this one closes
  the gap for prose that never becomes a Pattern-4 bullet in the first
  place.

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — extend the Option-Count Detection section
  (lines 284-296) with the bold-label formatting rule described above.
- `scripts/tests/test_refine_issue_command.py` — add a new test method to the
  existing `TestOptionCountDetectionInCommand` class asserting the new
  bold-label rule text (`**Option A**`, `**Recommended**` markers) is present
  within the Step 5a span, mirroring BUG-2606's
  `test_exhausted_retry_falls_through_to_phase_3` precedent
  (`scripts/tests/test_decide_issue_skill.py:419-430`) — a structural
  presence-assertion that locks in the prompt edit without invoking the LLM.
  _Wiring pass added by `/ll:wire-issue`._

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml:240` — `deposit_options` state runs
  `/ll:refine-issue ${captured.input.output} --auto` when
  `check_decision_decidable` reports not-decidable (already noted in prose in
  Codebase Research Findings below; now listed structurally).
- `scripts/little_loops/loops/rn-remediate.yaml:306,672,686` — three call
  sites for `/ll:refine-issue ${context.issue_id} --auto` in the remediation
  retry chain (already noted in prose; now listed structurally with line
  numbers).
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:86` — calls
  `/ll:refine-issue ${captured.issue_id.output} --auto --gap-analysis`, then
  its `check_decision_mid_refine` state (~line 100-105) gates mid-chain on
  `ll-issues check-flag ... decision_needed`, routing back to autodev's
  `check_decision_after_refine` (`autodev.yaml:165`) → `run_decide` on a hit.
  This is a third production consumer of refine-issue's decision-formatting
  output not previously mentioned anywhere in this issue.
- `scripts/little_loops/loops/harness-multi-item.yaml` — checked and
  excluded: `visibility: example`, a documentation demo loop, not a
  production caller.

### Similar Patterns
- `commands/refine-issue.md:246-269` (Integration Map / Root Cause enrichment
  templates) — existing precedent for structured markdown templates the
  command already asks refine to emit.
- `skills/decide-issue/SKILL.md:241-249` (Provisional Pattern D) — the exact
  shape this fix aims to make refine-issue produce natively instead of
  requiring decide-issue to reverse-engineer it from prose.

### Tests
- No existing automated test targets refine-issue's markdown-generation
  prose (LLM-driven, not Python). Verify manually against 2-3 issues with
  prose-only recommendations (e.g. run `/ll:refine-issue --auto` on a fresh
  copy of ENH-2492's decision text) and confirm
  `ll-issues check-decidable` reports `Decidable` afterward instead of
  `OPTIONS_MISSING`.
- `scripts/tests/test_issue_parser_unresolved.py:84-97`
  (`TestCountUnresolvedOptions.test_bold_option_label_format`) shows the
  exact fixture shape Pattern 2 matches — useful as a manual-verification
  template when checking refine-issue's output by hand.

### Tests (correction — wiring pass added by `/ll:wire-issue`)

_The "No existing automated test targets refine-issue's markdown-generation
prose" claim above is inaccurate: a structural test file already exists for
this exact section._

- `scripts/tests/test_refine_issue_command.py::TestOptionCountDetectionInCommand`
  (lines 18-82, **existing, must be updated**) — already structurally tests
  Step 5a's Option-Count Detection block for the 3 current patterns, by
  slicing `content` between the `### 5a. Fill Gaps with Research Findings`
  and `### 5b. Interactive Refinement` headings and asserting substrings
  (e.g. `test_two_or_more_threshold_documented`, `test_idempotency_guard_mentioned`).
  This is the direct precedent BUG-2606 followed
  (`test_exhausted_retry_falls_through_to_phase_3`,
  `scripts/tests/test_decide_issue_skill.py:419-430`) for prompt-prose
  changes: add a structural presence-assertion test even when full
  LLM-behavior verification stays manual-only. A new test method here
  asserting the bold-label rule's marker text is present within the Step 5a
  span is both consistent with repo convention and directly regression-proofs
  this issue's prompt edit.
- `scripts/tests/test_decide_issue_skill.py::TestOptionsMissingExitCodes`
  (lines 519-542, existing, no change needed) — already unit-tests
  `count_enumerable_options()` end-to-end via the same exit-code contract
  `ll-issues check-decidable` uses; useful reference for confirming Pattern 2
  recognition without needing a new fixture.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Concrete call site**: `scripts/little_loops/loops/autodev.yaml` state
  `deposit_options` (~line 233) runs `/ll:refine-issue
  ${captured.input.output} --auto` when the `check_decision_decidable`
  state (~line 212) reports the issue is not decidable via
  `scripts/little_loops/cli/issues/check_decidable.py:cmd_check_decidable()`
  (line 19). This is the concrete production call site whose output quality
  this fix improves — `rn-remediate.yaml` wires the same
  `check_decision_decidable` → `deposit_options` pattern.
- **Marker-convention precedent beyond decide-issue**: the append-only
  `_Added by ... :_` italic marker used by the Preservation Rule is applied
  identically in `skills/format-issue/templates.md:162-172` and
  `skills/wire-issue/SKILL.md:385-391` — confirming this is an established,
  repo-wide convention for machine-appended content, not a one-off pattern
  specific to refine-issue.

## Implementation Steps

1. Add the bold-label decision-formatting rule to refine-issue.md's
   Option-Count Detection section.
2. Manually verify against a sample of currently-stuck issues that a fresh
   `/ll:refine-issue --auto` pass now produces `**Option A/B**` blocks
   `check-decidable` recognizes.
3. Consider (follow-on, not in scope here) a one-time bulk remediation pass
   over the ~40 already-stuck issues once BUG-2605/BUG-2606/this land, since
   existing prose won't retroactively reformat itself.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

4. Update `scripts/tests/test_refine_issue_command.py`'s
   `TestOptionCountDetectionInCommand` class with a new test method asserting
   the bold-label formatting rule's marker text (`**Option A**`,
   `**Recommended**`) is present within the Step 5a span — corrects the
   issue's own inaccurate "no automated test exists" claim and follows
   BUG-2606's precedent.
5. When validating manually (Implementation Step 2), also exercise
   `scripts/little_loops/loops/refine-to-ready-issue.yaml`'s
   `check_decision_mid_refine` gate (~line 100-105) — a third production
   consumer of refine-issue's decision-formatting output not previously
   covered by this issue, alongside `autodev.yaml` and `rn-remediate.yaml`.

## Impact

- **Priority**: P2 - Root-causes the failure class that BUG-2605/BUG-2606
  otherwise only mitigate after the fact; prevents backlog regrowth.
- **Effort**: Medium - prompt-instruction tuning in a skill/command markdown
  file; needs sampling against real stuck issues to validate the formatting
  rule actually produces Pattern-2-matching output reliably.
- **Risk**: Medium - imprecise prompt wording could either fail to trigger
  (no improvement) or over-trigger (spuriously setting `decision_needed: true`
  on issues with a single clear recommendation and no real ambiguity); needs
  validation against several issue shapes before considering it converged.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `scripts/little_loops/issue_parser.py` | `count_enumerable_options()` — the Pattern 1-4 logic this fix targets |
| `.claude/CLAUDE.md` | Development Preferences — skill/command authoring conventions |

## Status

**Open** | Created: 2026-07-11 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-07-11T20:41:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8f60841-044f-46c6-ba32-0bfa3724b66c.jsonl`
- `/ll:wire-issue` - 2026-07-11T20:37:34 - `37df9e19-5b6b-496d-b642-9c4e836e3f06.jsonl`
- `/ll:refine-issue` - 2026-07-11T20:31:14 - `d3119631-9721-46b9-a9af-0d7109440153.jsonl`
- `/ll:capture-issue` - 2026-07-11T18:07:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/37898a30-ea4e-4972-91db-a694a29a9e31.jsonl`
