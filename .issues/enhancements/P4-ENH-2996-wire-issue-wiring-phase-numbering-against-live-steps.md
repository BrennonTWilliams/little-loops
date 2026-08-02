---
id: ENH-2996
status: open
priority: P4
captured_at: '2026-08-02T13:43:01Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to:
- ENH-2995
decision_needed: false
blocked_by:
- ENH-2995
confidence_score: 86
outcome_confidence: 81
score_complexity: 23
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 23
---

# wire-issue's Wiring Phase numbers against live steps only

## Summary

`/ll:wire-issue` Phase 8b appends a `### Wiring Phase` whose entries continue
the numbering of the existing `## Implementation Steps` list. When some of
those earlier steps have been refuted by a prior `/ll:refine-issue` pass, the
continued numbering asserts a sequence that includes dead steps.

## Current Behavior

`skills/wire-issue/SKILL.md:383-396` (Phase 8b) instructs:

```markdown
### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

N. Update `path/to/caller.py` — adjust calls to `changed_function()` with new signature
N+1. Update `tests/test_affected.py` — adapt existing tests to new behavior
```

`N` continues from the existing list's last number, with no check on whether
those steps are still live.

Observed in `ENH-2500`
(`.issues/enhancements/P3-ENH-2500-per-run-dir-pending-file-and-scope-for-prompt-across-issues.md:287-298`):
the Wiring Phase is numbered 10-17, continuing a 1-9 list in which steps 1, 3,
6 and 7 are each explicitly refuted by an intervening
`### Codebase Research Findings` block ("Revised step 1: **omit entirely**",
"Step 6 target file is wrong"). The numbering presents a 17-step plan of which
four steps are dead.

## Expected Behavior

The Wiring Phase either:
- numbers against live steps only (skipping refuted ones), or
- uses an independent, unnumbered or letter-keyed list that makes no claim
  about position in the parent sequence.

The second is simpler and does not require wire-issue to re-derive which steps
are live.

## Motivation

Low severity on its own — the numbering is cosmetic and the wiring entries
themselves are sound (a corpus check found only 2% of 9,377 wiring bullets are
explicitly no-op, so wire-issue is not padding). The value is in not
compounding ENH-2995's contradiction problem with a numbering scheme that
implies the dead steps are part of the sequence.

## Proposed Solution

Two options, only one of which needs ENH-2995's superseded markers:

**Option A**: Wiring Phase entries become an unnumbered bulleted list, or
letter-keyed (`W1`, `W2`, …), making no positional claim. Zero dependency on
detecting live steps; shippable independently of ENH-2995.

> **Selected:** Option A — matches the unnumbered `-` bullet convention already
> used by 3 of 4 sibling Phase-8a subsections in `skills/wire-issue/SKILL.md`,
> has zero downstream code/test/doc coupling to the current `N.` numbering,
> and ships independently of the blocked ENH-2995 dependency.

**Option B**: wire-issue skips superseded-marked steps when computing `N`.
Requires ENH-2995's marker to exist and be parseable.

Option A is recommended — it removes the false claim rather than computing a
truer one, and the Wiring Phase is a distinct set of touchpoints that does not
genuinely need to interleave with the parent sequence.

### Decision Rationale

**Selected: Option A** (unnumbered/letter-keyed Wiring Phase entries).

Two `ll:codebase-pattern-finder` agents independently evaluated each option
against the codebase. Option A matches an existing, dominant convention with
zero downstream coupling; Option B is currently blocked and would introduce
new parsing logic that has no precedent.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 0 |
| Simplicity | 3 | 0 |
| Testability | 3 | 1 |
| Risk | 3 | 0 |
| **Total** | **12/12** | **1/12** |

Key evidence:
- 3 of 4 sibling Phase-8a subsections in `skills/wire-issue/SKILL.md`
  (`### Dependent Files`, `### Documentation`, `### Tests`, `### Configuration`)
  already use unnumbered `-` bullets with an italic attribution line — Phase
  8b's numbered `N.`/`N+1.` format is the sole outlier.
- No code, test, or doc anywhere in the repo parses or depends on the
  Wiring Phase's `N.`-style numbering (`output-report.md`'s `[N]` is a
  step-count placeholder, not a parsed sequence number).
- Option B hard-depends on `ENH-2995` (still `status: open`) for a
  superseded-step marker that does not yet exist anywhere in the codebase,
  and would additionally require new step-filtering logic in wire-issue's
  Phase 3 that has no precedent today.

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md` — Phase 8b (lines 383-396)

_Wiring pass added by `/ll:wire-issue`:_
- `.gemini/skills/wire-issue/SKILL.md` — byte-identical mirror of Phase 8b
  (its own lines 387-395), produced by `GeminiEmitter.emit_skill()`
  (`scripts/little_loops/adapters/gemini.py`), which only rewrites
  frontmatter and copies the body verbatim. Will silently keep the old
  `N.`/`N+1.` numbering after this edit unless `ll-adapt --host gemini
  --apply` is re-run.
- `.kimi-code/skills/wire-issue/SKILL.md` — same situation (its own lines
  391-394), regenerated via `ll-adapt --host kimi --apply`.

### Dependent Files (Callers/Importers)
- `skills/wire-issue/output-report.md:44` — `## IMPLEMENTATION STEPS CHANGES`
  reports `[N] new steps added to Wiring Phase` as a *count* (from
  `new_impl_steps`'s length), not a positional sequence number. No change
  needed here regardless of which option is chosen.
- No Python code parses `## Implementation Steps` numbering. The only
  `\d+\.`-matching regex in the codebase
  (`scripts/little_loops/issue_parser.py:39`,
  `_CRITERION_BULLET_PATTERN`) is scoped to `extract_criteria()`
  (line 1758) and only scans the Acceptance Criteria / Expected Behavior
  sections, never Implementation Steps.
  `scripts/little_loops/cli/issues/size.py:41` references the
  `Implementation Steps` heading only to detect presence for size scoring,
  not to parse numbering.

_Wiring pass added by `/ll:wire-issue`:_
- `commands/reconcile-issue.md:60-61,66-67,111,126` — describes reading
  "every bullet under `### Wiring Phase`" as a source-of-truth section.
  Format-agnostic prose (reads "bullets," not "numbered items") — no
  functional change needed, but it is a genuine consumer of the section's
  rendered shape.

### Similar Patterns
- `commands/refine-issue.md:425-442` — Implementation Steps enrichment rules
  and the "Constraints, Not Recipes" register guidance on when imperative
  sequencing is legitimate at all

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Where `N` currently comes from: `skills/wire-issue/SKILL.md` Phase 3
  (lines 100-121) reads the issue's `## Implementation Steps` section and
  records only a raw count as `implementation_steps_count: N` inside the
  `EXISTING_WIRING` structured summary (line 120) — a prose-level scan by
  the executing agent, not a deterministic parser. Phase 8b (lines 383-396)
  then continues straight off that count with no live/dead filtering
  applied at any stage.
- No refutation-detection mechanism exists yet anywhere in the wire-issue or
  refine-issue pipeline. Refutation language ("Revised step 1: omit
  entirely", "Step 6 target file is wrong") currently lands only as
  freeform prose inside a `### Codebase Research Findings` subsection
  following the list — never as an in-place marker on the original
  directive line. `ENH-2995` (still `status: open`) is the issue that would
  introduce such a marker (a `> ⚠ Superseded — see § ...` blockquote,
  explicitly designed per its own Proposed Solution to leave `^\d+\.`
  numbering and downstream parsers unaffected). Option B of this issue has
  a hard dependency on ENH-2995 landing first; Option A has none.
- Marker-convention precedent: every other additive block in this
  template system — `skills/wire-issue/SKILL.md`'s own sibling Phase-8a
  subsections (`### Dependent Files (Callers/Importers)` at lines 338-343,
  `### Documentation` at 354-360, `### Tests` at 364-371, `### Configuration`
  at 375-381) plus `commands/refine-issue.md`'s `### Codebase Research
  Findings` (lines 454-460, and reused at line 604 for gap-analysis mode) —
  uses a `###` heading with an italicized attribution line
  (`_Wiring pass added by `/ll:wire-issue`:_` / `_Added by
  `/ll:refine-issue` — based on codebase analysis:_`) and **plain
  unnumbered `-` bullets**. The current Wiring Phase (`N.`/`N+1.`
  numbering) is the only one of wire-issue's own Phase-8 sub-blocks that
  departs from this convention.
- No existing `W1`/`W2`-style lettered list convention exists in this
  codebase's issue-template system to align Option A with; the only
  `W1`/`W2` hits found are Mermaid diagram participant labels in
  `docs/ARCHITECTURE.md` (unrelated). The nearest actual lettering
  precedent (`8a`/`8b`/`8c` in `skills/wire-issue/SKILL.md`, `5a`/`5b` in
  `commands/refine-issue.md`) letters phase headings in the skill's own
  procedural instructions, not list items written into generated issue
  content — a different surface.

### Tests
- No dedicated test file covers Phase 8b's numbering behavior specifically
  (it is markdown-template prose interpreted by the executing agent, not
  code); no test needs updating for either option.

### Documentation
- None found referencing Phase 8b's numbering scheme outside
  `skills/wire-issue/SKILL.md` itself and `skills/wire-issue/output-report.md`
  (confirmed not to need changes, see Dependent Files above).

### Configuration
- N/A

## Implementation Steps

TBD — requires codebase analysis

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Edit `skills/wire-issue/SKILL.md` Phase 8b per the selected option (Option A).
- Re-run `ll-adapt --host gemini --apply` and `ll-adapt --host kimi --apply`
  so `.gemini/skills/wire-issue/SKILL.md` and
  `.kimi-code/skills/wire-issue/SKILL.md` pick up the same template change
  (both are byte-for-byte mirrors, regenerated from source, not
  hand-edited).
- No test changes required — confirmed no test parses or asserts on
  Phase 8b's numbering or bullet format (`test_wiring_skills_and_commands.py`,
  `test_enh494_skill_companions.py`, and others checked; none couple to
  this section's list-marker style).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Whichever option is chosen, the change is confined to
  `skills/wire-issue/SKILL.md` Phase 8b (lines 383-396) — no other file
  needs to change for the numbering scheme itself (see Integration Map →
  Dependent Files).
- The Wiring Phase's sibling Phase-8a subsections already use a `###`
  heading + italic attribution + plain unnumbered `-` bullets
  (`skills/wire-issue/SKILL.md:338-381`); Option A brings Phase 8b in line
  with that existing pattern rather than introducing a new one.
- Nothing downstream parses `## Implementation Steps` numbering (no `\d+.`
  regex scoped to that section anywhere in `scripts/little_loops/`), so
  either option is safe to make without a companion code change.
- If Option B is chosen, it is blocked on `ENH-2995` (still open) — that
  issue is what would give wire-issue a parseable in-place marker for
  refuted steps. `check_reconcile_needed`-style staleness detection has no
  equivalent for Implementation Steps today.
- Verification: after editing Phase 8b's template text, exercise
  `/ll:wire-issue` against an issue whose `## Implementation Steps` has 9
  entries (e.g. re-run against `ENH-2500`'s issue file, cited in this
  issue's Current Behavior, or a synthetic fixture) and confirm the emitted
  Wiring Phase entries carry no numeric claim about position in the parent
  sequence.

## Impact

- Cosmetic correctness in issues that have been through both refine and wire.
- Small: affects the 1,140 issues carrying a wiring marker, only where refine
  also deposited a contradiction.

## Success Metrics

- A wire pass over an issue with refuted steps produces a Wiring Phase that
  makes no false positional claim.

## Scope Boundaries

- Does **not** change what wire-issue discovers or how it writes Integration
  Map entries — the coupling findings are sound and stay as-is.
- Does **not** address wiring-block accumulation (that is ENH-2993's optional
  second half).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/wire-issue/SKILL.md` | Contains Phase 8b, the section being changed |
| `commands/refine-issue.md` | Source of the refuted-step condition |

## Confidence Check Notes

**Readiness**: 86/100 — **Outcome Confidence**: 81/100 — **Recommendation**: STOP — ADDRESS GAPS (hard override)

### Gaps to Address
- Program Design gate (ENH-2852): `## Program Design` section is missing and the
  project's gate is armed (`.ll/program-design-cutover.json`, 2026-07-30 —
  this issue's `captured_at` of 2026-08-02 postdates the cutover, so it is not
  grandfathered). Remedy: add a `## Program Design` section with the concrete
  before/after text of Phase 8b (signature-shaped diff) and a `Call Path`
  anchor into `skills/wire-issue/SKILL.md`, or set
  `program_design_not_applicable: true` in frontmatter if this is judged
  genuinely trivial template-text editing.
- `blocked_by: [ENH-2995]` is unmet — ENH-2995 is still `status: open`. The
  issue's own Decision Rationale states the selected Option A has "zero
  dependency on ENH-2995" and "ships independently of the blocked ENH-2995
  dependency," which contradicts the frontmatter `blocked_by` edge. If Option A
  is truly independent, `blocked_by: [ENH-2995]` should be removed (or
  narrowed to only gate Option B, which this issue does not select).

## Session Log
- `/ll:confidence-check` - 2026-08-02T15:45:51 - `20ea844a-65cc-4307-b288-00dcc23e4621.jsonl`
- `/ll:wire-issue` - 2026-08-02T15:40:19 - `54b8b61c-90df-41f1-af64-799342e6500a.jsonl`
- `/ll:decide-issue` - 2026-08-02T15:26:29 - `0a208318-6b67-47ba-88f1-23b17a2f5884.jsonl`
- `/ll:refine-issue` - 2026-08-02T15:21:01 - `1a6be5be-a3c2-4f65-a811-ac343eeaa258.jsonl`
- `/ll:capture-issue` - 2026-08-02T13:45:57 - `fac7dff4-61c1-4496-95b8-7bd1993d2971.jsonl`

## Status

- **Status**: open
