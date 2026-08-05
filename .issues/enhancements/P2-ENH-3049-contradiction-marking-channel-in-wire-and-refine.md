---
id: ENH-3049
title: 'Contradiction-marking channel: port the Superseded marker into wire, fire
  refine''s carve-out on intra-pass contradiction'
type: ENH
priority: P2
status: open
discovered_by: capture-issue
discovered_date: 2026-08-04
captured_at: '2026-08-04T22:10:00Z'
relates_to:
- ENH-3046
- ENH-3045
- ENH-2995
- ENH-2992
- FEAT-2942
labels:
- skills
- issues
- gates
decision_needed: false
testable: true
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# ENH-3049: Contradiction-marking channel in wire and refine

## Summary

ENH-2995 built a contradiction-annotation channel (`⚠ Superseded` markers), ENH-2992 wired it
to a consumer (`autodev.yaml`'s `check_reconcile_needed`), and `/ll:reconcile-issue` exists to
clear it. The machinery is complete and **idle**: 1,703 issues refined, 19 reconciled
(ENH-2992). This issue closes the two gaps that keep it idle.

1. **`/ll:wire-issue` has no channel at all.** `skills/wire-issue/SKILL.md` contains zero
   occurrences of `Superseded`; its Phase 8c is append-only with no annotation carve-out.
2. **`/ll:refine-issue`'s carve-out fires on too narrow a trigger** — a *codebase research
   finding refuting a line* — so the most common contradiction shape (a later pass elaborating
   a hedge into its opposite) never qualifies, even in sections already inside the carve-out's
   scope.

Scope boundary vs. `ENH-3046`: that issue **detects** contradictions (mechanical gap kinds plus
a judgment pass in refine that reports them as findings). This issue gives the passes a way to
**mark and route** one. 3046 finds; 3049 marks. Neither blocks the other; together they close
the detect→mark→route→resolve loop.

## Current Behavior

`ENH-3045` is the worked example — it declares its `missing_behavior_parity` gap kind
**optional** at four sites while simultaneously specifying it as a mandatory ten-touchpoint
change, and passed refine, wire, and confidence-check (100/82) in that state.

Mapping each site to the existing carve-out scope
(`_SUPERSEDED_DIRECTIVE_SECTIONS = ("Implementation Steps", "Files to Modify", "Acceptance
Criteria")`, `scripts/little_loops/issue_parser.py:644`):

| Site | Section | In carve-out scope? |
|---|---|---|
| `:104` "Detection (optional, same change)" | `## Proposed Solution` | No |
| `:118` "optional gap kind" | `### Files to Modify` | **Yes** |
| `:230` "3. Optional `missing_behavior_parity` gap kind" | `## Implementation Steps` | **Yes** |
| `:267` "optional small Python gate" | `## Impact` | No |

**Two of the four sites were already markable and were not marked.** The scope list is not the
binding constraint — the trigger is. `commands/refine-issue.md:529-536` defines the refutation
test as: fires only when the refutation comes from THIS pass's own `### Codebase Research
Findings`, with correction-phrase guidance (`is wrong`, `does not exist`, `is stale`,
`omit entirely`). Refine's wiring here produced no such finding; it produced an *elaboration*
(a ten-site touchpoint list) whose existence contradicts "optional" by implication, not by
refutation. The channel had no way to fire.

Wire's failure is simpler and total: `skills/wire-issue/SKILL.md:400-406` reads "**Do NOT
overwrite** any existing content. Only append." with no carve-out of any kind. Wire authored
the ten-touchpoint Wiring Phase list that contradicts "optional" and had no mechanism to say so.

## Expected Behavior

1. **Wire gains the carve-out.** Phase 8c grows an annotation exception ported from
   `commands/refine-issue.md:518-562` — same marker text, same indentation rule, same
   idempotence test, same three-section scope. Explicitly *not* a second, differently-shaped
   marker lifecycle (`commands/reconcile-issue.md:69-71` forbids inventing one).

   Two rules do **not** port unchanged, and the port is not verbatim:

   - **Provenance substitute.** Refine's "Same pass only" rule keys on THIS pass's own
     `### Codebase Research Findings`. Wire has no such heading — its agent output lands as
     `## Integration Map` bullets tagged `[Agent N finding]` plus the appended
     `### Wiring Phase` list. Wire's rule reads: fires only when the contradicting content is
     content **this wire pass is appending**; never from re-reading a prior pass's appended
     blocks.
   - **No marker-removal right for wire.** Markers carry no provenance (`⚠ Superseded —
     <reason ≤10 words>` is identical whoever wrote it), so a wire pass exercising refine's
     bounded removal right cannot distinguish its own markers from refine's, and would silently
     delete the routing signal `check_reconcile_needed` reads. Wire may **insert** markers and
     must skip idempotently; it may never delete one. Refine keeps its removal right unchanged.

2. **Both passes' refutation test covers self-contradiction.** Extend the trigger beyond
   "a finding refutes this line" to include "content this pass is appending contradicts this
   line" — the elaboration-vs-hedge shape. Concretely, for ENH-3045: appending a Wiring Phase
   that enumerates ten mandatory touchpoints for a component the issue calls "optional" marks
   the `## Implementation Steps` and `### Files to Modify` lines carrying that word.

3. **Reconcile becomes a routine step, not an exceptional one** — see Proposed Solution.

## Motivation

The detect→resolve loop is 75% built and idle. Every component exists (`ENH-2995` annotation,
`ENH-2992` routing, `reconcile-issue` resolution, `superseded_marker_count` public predicate);
only the emitters are missing or misfiring. This is the cheapest possible fix for the defect
class that survives the most passes, because append-only passes accumulate contradictions by
construction and nothing else in the pipeline can retract a line.

## Proposed Solution

**In scope, settled:**

- Port the ENH-2995 carve-out into `skills/wire-issue/SKILL.md` Phase 8c, preserving rule shape
  for the four portable rules and substituting wire's own provenance rule (Expected Behavior 1).
  **Compressed to fit the 500-line cap** — see the line budget under Files to Modify.
- Widen the refutation test in both passes to cover intra-pass contradiction (item 2 above).
  Keep it annotate-only and keep the correction-phrase guidance as the *finding-driven* branch;
  add a *contradiction-driven* branch alongside it.
- Add `/ll:reconcile-issue` to `/ll:refine-issue`'s pipeline diagram and Next Steps block, and
  to the post-wire recommendation in `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — ENH-2992 already
  established that no human path leads to reconcile; this is the prose half of that fix.

**Resolved (record only — `decision_needed: false`): marker scope does not widen to
`## Proposed Solution`. Option C selected; see Decision Rationale below. The options are
retained as the rationale's evidence, not as an open question.**

The original capture proposed extending the carve-out to `## Proposed Solution` and
`## Summary`. Research says do not do this without also changing two other components, and
possibly not at all:

- `_SUPERSEDED_DIRECTIVE_SECTIONS` (`issue_parser.py:644`) is shared verbatim by
  `superseded_marker_count()` (`:661-673`, autodev's routing predicate) and the
  `unmarked_superseded_directive` gap kind (`:591-597`). A marker outside that tuple is inert:
  invisible to routing and to the gate.
- If the tuple **is** widened, `commands/reconcile-issue.md:78-84` lists `## Proposed Solution`
  under "**Preserve untouched — never edit, reorder, or delete**". Reconcile clears markers on
  directive lines it *evaluates*; a marker on a line it may not touch is never cleared. Per
  reconcile's own warning ("a marker that survives a completed reconcile pass re-fires the gate
  on every [pass]"), that is an unbounded re-fire loop in `check_reconcile_needed`.
- ENH-2995 excluded these sections deliberately, mirroring reconcile's preserve-list — this
  would be reversing a considered decision, not filling a gap.

**Option A**: Widen all three (carve-out scope, `_SUPERSEDED_DIRECTIVE_SECTIONS`, and reconcile's
rewrite contract). Precedent exists: ENH-2937 added `## Scope Boundaries` to reconcile as a
conditional carve-out (`reconcile-issue.md:49-65`). Highest fidelity, largest surface,
reverses ENH-2995's design.

**Option B**: Widen the carve-out only. Marker is human-readable but inert. Cheap and near-useless.

**Option C**: Do not widen; fix the trigger only. Two of ENH-3045's four sites are
already in scope, so a working trigger marks the issue and routes it to reconcile regardless.
Reconcile then rewrites the directive sections, and the surviving prose hedge in
`## Proposed Solution` / `## Impact` is a cosmetic inconsistency rather than an implementable
contradiction. Zero reversal of prior design, zero new re-fire risk.

> **Selected:** Option C — zero-surface, matches ENH-2995's deliberate design, and the
> two-of-four-sites-already-in-scope evidence shows the trigger fix alone is sufficient.
> Option A is recorded as a follow-up only if prose-section drift proves to matter independently.

### Decision Rationale

**Selected**: Option C — do not widen `_SUPERSEDED_DIRECTIVE_SECTIONS`, reconcile's rewrite
contract, or the carve-out scope; fix only the refutation trigger (intra-pass contradiction
detection) and port the carve-out into wire-issue unchanged.

**Reasoning**: Independent codebase research for Option A confirms the issue body's own
analysis: widening all three components touches a Python constant shared verbatim by two
detectors (`superseded_marker_count()` and `unmarked_superseded_directive`,
`issue_parser.py:644`), requires a new conditional-rewrite-eligibility mechanism in
`reconcile-issue.md` structurally equivalent to ENH-2937's `## Scope Boundaries` carve-out
(new detection step, two new rewrite branches, new Output Format rows, new test class), and
carries the unbounded re-fire risk `reconcile-issue.md:78-84`'s preserve-list exists to
prevent — a materially larger and riskier surface than ENH-2937's single-file precedent.
Option B produces a marker that is invisible to both routing and the gap detector (inert by
`_SUPERSEDED_DIRECTIVE_SECTIONS`'s current scope), so it does not close the loop this issue
exists to close. Option C requires zero component-scope changes: the wire-issue carve-out
being added by this issue already uses the unchanged three-section scope, and ENH-3045's own
evidence (2 of 4 contradiction sites already fall inside that scope) shows a working trigger
alone routes the issue to reconcile without any widening.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — Widen all three | 1 | 0 | 1 | 0 | 2/12 |
| B — Widen carve-out only | 1 | 3 | 2 | 2 | 8/12 |
| C — Fix trigger only | 3 | 3 | 3 | 3 | **12/12** |

**Key evidence**:
- `_SUPERSEDED_DIRECTIVE_SECTIONS` (`issue_parser.py:644`) is read verbatim by both
  `superseded_marker_count()` and `unmarked_superseded_directive` — no way to widen scope for
  one detector without the other.
- ENH-2937's `## Scope Boundaries` carve-out (`reconcile-issue.md:44-54`) is a *conditional*
  exception requiring new contradiction-detection logic, not a precedent for an unconditional
  scope widen — Option A would need to build that same structure again for
  `## Proposed Solution`.
- `reconcile-issue.md:78-84`'s "Preserve untouched" list explicitly protects
  `## Proposed Solution` from the exact unbounded re-fire failure mode the issue body already
  names.

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md` — Phase 8c annotation carve-out. **Line budget is binding and
  already exhausted**: the file is 455 lines (`wc -l`, verified 2026-08-05) against a 500-line
  cap that fails only above 500 (`test_enh494_skill_companions.py:70-84`), so **45 lines are
  available**. Refine's carve-out block (`commands/refine-issue.md:518-562`) is *exactly 45
  lines*, and wire's version adds a provenance rule — a verbatim port overflows. **Compress to
  fit**: drop refine's worked-example fenced block (`:546-549`) and the
  `_CRITERION_BULLET_PATTERN`/`_OPTION_PATTERNS` rationale prose (`:541-545`, keep the
  never-column-0 rule itself), and omit the removal-right paragraph (`:559-562`, excluded for
  wire anyway). Target ≤ 30 lines added. Companion extraction is **out of scope** — it hits the
  untested mirror-companion gap below; if compression proves impossible, stop and re-scope
  rather than extracting.
- `commands/refine-issue.md` — widen the refutation test at `:529-536` with a
  contradiction-driven branch; add reconcile to the pipeline diagram and Next Steps
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — reconcile as a routine post-wire step
- `docs/reference/COMMANDS.md` — `/ll:wire-issue` description gains the annotation behavior
- `scripts/tests/test_wiring_skills_and_commands.py` — `DOC_STRINGS_PRESENT` entries for the new
  wire carve-out prose and the widened refine trigger

### Dependent Files (Callers/Importers)
- `scripts/tests/test_wiring_skills_and_commands.py::test_wire_issue_skill_mirror_matches_source`
  (`:336-346`, ENH-2996) asserts the post-frontmatter body of `skills/wire-issue/SKILL.md` is
  byte-identical to `.gemini/skills/wire-issue/SKILL.md` and `.kimi-code/skills/wire-issue/SKILL.md`.
  Any edit breaks it until `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply`
  runs. **Note the host name**: that test's own failure message (`:344`) says
  `--host kimi`, which is not a registered host (`ERROR: Host 'kimi' is not registered.
  Available: ['codex', 'gemini', 'kimi-code', 'omp']`). Fix the message to `kimi-code` as part of
  this issue — a one-line change in the same test file already being edited.
- **Mirror companion gap** — the mirrors contain `SKILL.md` only;
  `skills/wire-issue/prose-dependency-gate.md` has no counterpart. If the carve-out is extracted
  to a companion to stay under the 500-line cap, it silently does not reach Gemini or Kimi and
  no test catches it. Budget the addition to fit inline, or bring companion mirroring into scope.

_Wiring pass added by `/ll:wire-issue`:_
- `.gemini/commands/refine-issue.toml` and `.kimi-code/skills/ll-refine-issue/SKILL.md` —
  mirrors of `commands/refine-issue.md`'s carve-out and refutation-test prose. **Correction to
  the original wiring claim**: these are **generated, not hand-maintained**.
  `ll-adapt --host gemini --dry-run` and `ll-adapt --host kimi-code --dry-run` both list
  `DRY ll-refine-issue` in their commands pass (verified 2026-08-05), so
  `ll-adapt --host <h> --apply` regenerates them. Do **not** hand-edit — edits are overwritten on
  the next adapt run. The real risk is *skipping* the regeneration: unlike the wire-issue
  SKILL.md mirrors, no test asserts these are current, so drift is silent. Step 2's regeneration
  covers them.
- `scripts/tests/test_issue_parser.py::TestSupersededMarkerCount` (`:4182-4266`) — existing unit
  tests for `superseded_marker_count()`; confirms no new parser-level test is required since wire
  reuses the function and `_SUPERSEDED_DIRECTIVE_SECTIONS` verbatim (no signature/behavior
  change). Template to mirror if a wire-specific detection function is ever added. [Agent 3 finding]
- `scripts/tests/test_ll_issues_format_check.py::TestUnmarkedSupersededDirective` /
  `TestSupersededMarkerCountKey` (`:846-1029`) — existing JSON-payload integration tests
  exercising the same origin-agnostic detectors; unaffected by this issue's plan but the closest
  precedent for a marker-presence assertion pattern. [Agent 3 finding]
- `scripts/tests/test_reconcile_issue_command.py` — doc-assertion-style tests over
  `commands/reconcile-issue.md` / `skills/ll-reconcile-issue/SKILL.md` (same `assert "text" in
  content` idiom as `DOC_STRINGS_PRESENT`); useful precedent, not required to change. [Agent 3 finding]
- `scripts/tests/test_enh494_skill_companions.py::TestSkillLineLimit` (`:71-84`) — enforces the
  500-line cap (`SKILL_LINE_LIMIT`, `:21`) that bounds how much carve-out prose can land inline in
  `skills/wire-issue/SKILL.md`. **Settled: 455 lines** (`wc -l`, re-verified 2026-08-05); the
  earlier 330 and 456 figures in this issue's research were wrong. The assertion fails only at
  `> 500` (`:77`), so 45 lines are available — see the binding budget under Files to Modify.
  A companion-file split (`EXPECTED_COMPANIONS`, `:24-35`) is the escape hatch this issue
  declines to take. [Agent 2 + Agent 3 finding]

### Configuration
_Checked: `_SUPERSEDED_DIRECTIVE_SECTIONS` is a module constant, not config; no
`config-schema.json` or `.ll/decisions.yaml` entry governs marker scope. Clean unless Option A
is chosen._

### Similar Patterns
- `ENH-2995` — the carve-out being ported (done; read its Scope Boundaries before widening)
- `ENH-2992` — marker→routing consumer, and the 19/1,703 invocation-rate evidence
- `ENH-2937` — the precedent for conditionally extending reconcile's rewrite contract (Option A)
- `ENH-2996` — host-mirror sync test that any wire SKILL.md edit must satisfy

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-04 — based on codebase analysis:_

- `superseded_marker_count()` (`issue_parser.py:648-674`) reads only `_SUPERSEDED_DIRECTIVE_SECTIONS` + `_SUPERSEDED_MARKER_PREFIX` — it is origin-agnostic, so a marker wire-issue writes into one of the three directive sections is counted identically to one refine-issue writes. No change to that function's contract is required.
- `unmarked_superseded_directive` (`issue_parser.py:584-597`) is narrower: it only scans bodies under the `### Codebase Research Findings` heading for correction phrases. Wire-issue's Phase 4 agent output is reported as Integration Map bullets tagged `[Agent N finding]`, not under that heading — so a wire-originated contradiction that lacks a matching refine-issue finding will satisfy `superseded_marker_count()` (and thus route via `check_reconcile_needed`) but will **not** independently trigger `unmarked_superseded_directive`. This is inert for the recommended Option C scope (the gap detector's job is unchanged, not extended) but worth naming so a future reader doesn't assume the two detectors stay in lockstep.
- `skills/wire-issue/SKILL.md` is 455 lines today (corrected from 456) (500-line cap, `test_enh494_skill_companions.py:21,74-84`); `skills/wire-issue/prose-dependency-gate.md` exists on disk as a precedent for extracting Phase-3.7-scale prose but is not in `EXPECTED_COMPANIONS` (`test_enh494_skill_companions.py:24-35`), so it isn't test-enforced for existence/non-emptiness/backlink the way the carve-out's extraction target would need to be if this issue chooses that route.

## Program Design

### Types
- `_SUPERSEDED_DIRECTIVE_SECTIONS: tuple[str, str, str]` — `("Implementation Steps",
  "Files to Modify", "Acceptance Criteria")`, `scripts/little_loops/issue_parser.py:644`.
  Unchanged under Options B/C; the single edit site under Option A.
- `_SUPERSEDED_MARKER_PREFIX: str` — `"⚠ Superseded"`, `issue_parser.py:645`; containment test,
  not equality, because the ≤10-word reason clause varies per pass.

_Wiring pass added by `/ll:wire-issue`:_
- `_SUPERSEDED_CORRECTION_PHRASES: tuple[str, ...]` — `issue_parser.py:635-643`
  (`"is wrong"`, `"does not exist"`, `"will not work"`, `"must be dropped"`, `"target file is
  wrong"`, `"is stale"`, `"omit entirely"`); a code comment at `:632-634` states it "mirrors the
  non-exhaustive LLM guidance in `commands/refine-issue.md`'s Preservation Rule carve-out
  verbatim." Widening the refutation trigger's correction-phrase guidance in prose without
  updating this comment (or the constant itself, if the new contradiction-driven branch needs
  its own phrase vocabulary) leaves the code comment's "mirrors ... verbatim" claim stale. [Agent 2 finding]

### Signatures
- `superseded_marker_count(issue_path: Path) -> int` — `issue_parser.py:661-673`; the public
  presence predicate autodev reads. Returns 0 on unreadable file by design (the FSM predicate
  must never fail the loop on a vanished issue). **No signature change** — this issue adds
  emitters, not new query surface.
- `_heading_bodies(content: str, heading: str) -> list[str]` — `issue_parser.py:677-693`.
  Note the anchored regex `^(#{2,3})\s+{re.escape(heading)}\s*$`: exact heading match, no
  suffix tolerated. Any new section name must match exactly.
- `check_format_gaps(...) -> FormatGaps` — `issue_parser.py:342-347`; unchanged.
  `unmarked_superseded_directive` (`:584-597`) already reports the inverse defect
  (correction language present, marker absent) and will begin firing correctly once wire emits.

### Call Path
- **wire**: Phase 8a Integration Map emission (`skills/wire-issue/SKILL.md:330-380`) produces
  the appended content → new Phase 8c contradiction test compares that content against directive
  lines already present in `## Implementation Steps` / `### Files to Modify` /
  `## Acceptance Criteria` → inserts `> ⚠ Superseded — <reason ≤10 words>` immediately below
  each contradicted line at that line's content column (3 spaces under `1. `, 2 under `- `;
  never column 0, which terminates the CommonMark list and collides with
  `_CRITERION_BULLET_PATTERN`/`_OPTION_PATTERNS`) → idempotent skip when the next line already
  contains the prefix.
- **refine**: `commands/refine-issue.md:529-536` refutation test gains a second branch →
  same insertion path as today (`:544-556`) → same bounded marker-removal right (`:559-562`).
- **routing (unchanged, verified live)**: `superseded_marker_count()` →
  `ll-issues format-check "$ID" --format json` → `autodev.yaml:1536-1556`
  `check_reconcile_needed` → `/ll:reconcile-issue` → markers cleared
  (`commands/reconcile-issue.md:56-69, 192-196`).

## Implementation Steps

1. Port the ENH-2995 carve-out into `skills/wire-issue/SKILL.md` Phase 8c, **compressed to
   ≤ 30 added lines** per the binding budget under Files to Modify (455 + 45 available; a
   verbatim port is exactly 45 and overflows once wire's provenance rule is added). Include
   wire's provenance-substitute rule and **omit the marker-removal right** (Expected Behavior 1).
   Re-run `wc -l skills/wire-issue/SKILL.md` and confirm ≤ 500 before moving on.
2. Regenerate host mirrors: `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply`
   (**not** `--host kimi` — unregistered). This covers both the wire-issue SKILL.md mirrors and
   the generated `refine-issue` mirrors for both hosts.
3. Add the contradiction-driven branch to the refutation test in both wire and refine.
4. Add `/ll:reconcile-issue` to refine's pipeline diagram, Next Steps, and the
   `ISSUE_MANAGEMENT_GUIDE.md` post-wire step.
   _Wiring pass added by `/ll:wire-issue`:_ `commands/refine-issue.md` already references
   `/ll:reconcile-issue` in its Next Steps block (`:907, 915`) and pipeline diagram (`:956, 962`)
   — that half of step 4 is done (ENH-2992). Only `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` is a
   genuine gap: zero occurrences of "reconcile" anywhere in the file today; its nearest relevant
   content is the wire-issue description at `:306` with no reconcile-issue follow-up. [Agent 2 finding]
5. _(Was: resolve the scope question. Already resolved — Option C, see Decision Rationale. No
   `_SUPERSEDED_DIRECTIVE_SECTIONS`, reconcile-contract, or carve-out-scope change is in scope.)_
   Instead: fix the `--host kimi` → `--host kimi-code` typo in
   `test_wiring_skills_and_commands.py:344`'s failure message.
6. `DOC_STRINGS_PRESENT` entries in `scripts/tests/test_wiring_skills_and_commands.py`.
7. Validate against `ENH-3045`: a wire pass over it marks the "optional" lines at `:118` and
   `:230`, `superseded_marker_count` returns ≥1, and `check_reconcile_needed` routes it.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~Hand-update `.gemini/commands/refine-issue.toml` and
  `.kimi-code/skills/ll-refine-issue/SKILL.md`~~ — **retracted, the premise was wrong.** Both are
  generated and *are* covered by step 2's `ll-adapt` run (dry-runs for `gemini` and `kimi-code`
  both list `DRY ll-refine-issue`). Hand edits would be overwritten. What survives from the
  original concern: no test asserts these mirrors are current, so step 2 must not be skipped.
- Confirm `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` gains a `/ll:reconcile-issue` post-wire
  reference (step 4's `commands/refine-issue.md` half is already done — see the note under step 4).

## Acceptance Criteria

**Wire's carve-out (prose gates, `scripts/tests/test_wiring_skills_and_commands.py`)**

- [ ] `skills/wire-issue/SKILL.md` Phase 8c contains the marker prefix `⚠ Superseded` and names
      all three scope sections (`Implementation Steps`, `Files to Modify`, `Acceptance Criteria`)
      — asserted via new `DOC_STRINGS_PRESENT` entries tagged `ENH-3049`.
- [ ] `skills/wire-issue/SKILL.md` states wire's provenance rule (contradiction must come from
      content **this pass is appending**) and states that wire may **not** delete a marker.
- [ ] `DOC_STRINGS_ABSENT` (or an equivalent assertion) proves wire's Phase 8c does **not** grant
      a marker-removal right, so a future edit can't silently reintroduce it.
- [ ] `skills/wire-issue/SKILL.md` is ≤ 500 lines (`test_enh494_skill_companions.py`), with the
      carve-out inline — no new companion file.
- [ ] `commands/refine-issue.md` carve-out contains both a finding-driven and a
      contradiction-driven branch; the existing correction-phrase guidance is unchanged.

**Mirrors**

- [ ] `test_wire_issue_skill_mirror_matches_source` passes for both mirrors after
      `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply`.
- [ ] `ll-adapt --host gemini --dry-run` and `--host kimi-code --dry-run` report no pending
      changes for `wire-issue` or `ll-refine-issue` after the run.
- [ ] `test_wiring_skills_and_commands.py:344`'s failure message says `--host kimi-code`.

**Unchanged surfaces (regression guards)**

- [ ] `_SUPERSEDED_DIRECTIVE_SECTIONS`, `_SUPERSEDED_MARKER_PREFIX`,
      `superseded_marker_count()`, and `unmarked_superseded_directive` are byte-unchanged —
      Option C adds emitters only. `TestSupersededMarkerCount` and
      `TestUnmarkedSupersededDirective` pass without modification.
- [ ] `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` references `/ll:reconcile-issue` as a post-wire
      step (0 occurrences today).
- [ ] `docs/reference/COMMANDS.md`'s `/ll:wire-issue` entry (`:258`) describes the annotation
      behavior.
- [ ] Full suite green: `python -m pytest scripts/tests/`.

**End-to-end validation (manual, recorded in the PR)**

- [ ] A wire pass over `ENH-3045` marks the `optional` lines at `:118` (`### Files to Modify`)
      and `:230` (`## Implementation Steps`); `ll-issues format-check ENH-3045 --format json`
      reports `superseded_marker_count >= 1`; `autodev.yaml`'s `check_reconcile_needed` routes it.
- [ ] Re-running the same wire pass inserts **no** duplicate markers (idempotence), and running
      wire over an issue already carrying a refine-written marker leaves that marker intact.

## Impact

- **Priority**: P2 — unblocks idle infrastructure; the one fix that makes append-only passes
  self-correcting rather than sediment-accumulating
- **Effort**: Low-Medium — prose changes to two markdown artifacts plus mirror regeneration;
  no Python change under the recommended Option C
- **Risk**: Low-Medium — marker over-emission would route issues to reconcile more often, which
  is the intended direction (19/1,703 today), but Option A carries a real unbounded-re-fire risk
  documented above

## Scope Boundaries

- **Not detection.** Finding contradictions is `ENH-3046`'s job (mechanical gap kinds plus a
  judgment pass in refine). This issue only supplies the marking and routing channel for one
  already identified. The two are independently landable.
- **Not a new marker syntax.** The `⚠ Superseded` convention, its indentation rule, its
  idempotence test, and its bounded removal right are ported verbatim.
  `commands/reconcile-issue.md:69-71` explicitly forbids a second marker lifecycle.
- **Not a change to reconcile's rewrite contract** — unless Option A is chosen, in which case
  it becomes the largest part of the work and should probably split into its own issue.
- **Not `## Summary` marking.** The original capture proposed `## Proposed Solution` *and*
  `## Summary`; Summary is dropped from every option. It is a restatement section, so a
  contradiction there is always downstream of one in a directive section that is already in
  scope.

## Related Key Documentation

- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — refine→wire→reconcile pipeline position
- `docs/reference/COMMANDS.md` — `/ll:wire-issue`, `/ll:refine-issue`, `/ll:reconcile-issue`
- `.claude/CLAUDE.md` § Issue File Format

## Status

**Open** | Created: 2026-08-04 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-05T01:17:58 - `62953512-7e33-4a82-a32d-bcc71ad6c3d6.jsonl`
- `/ll:confidence-check` - 2026-08-05T00:47:33 - `85ecbbf3-05c6-44f9-9801-7e9df7c717f1.jsonl`
- `/ll:wire-issue` - 2026-08-05T00:28:34 - `8af00be0-daef-43a2-ae95-a2e448be24ee.jsonl`
- `/ll:decide-issue` - 2026-08-05T00:03:23 - `2f3f7bc8-367e-4fba-936b-eaf8049da3c4.jsonl`
- `/ll:refine-issue` - 2026-08-04T23:58:41 - `81d59bbb-17b9-42e5-908c-ba7206c84d60.jsonl`
