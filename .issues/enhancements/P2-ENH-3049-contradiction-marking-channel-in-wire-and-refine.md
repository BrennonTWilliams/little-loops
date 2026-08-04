---
id: ENH-3049
title: 'Contradiction-marking channel: port the Superseded marker into wire, fire refine''s carve-out on intra-pass contradiction'
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
decision_needed: true
testable: true
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

1. **Wire gains the carve-out.** Phase 8c grows an annotation exception ported rule-for-rule
   from `commands/refine-issue.md:518-562` — same marker text, same indentation rule, same
   idempotence test, same bounded marker-removal right, same three-section scope. Explicitly
   *not* a second, differently-shaped marker lifecycle (`commands/reconcile-issue.md:69-71`
   forbids inventing one).

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

- Port the ENH-2995 carve-out into `skills/wire-issue/SKILL.md` Phase 8c, verbatim in rule
  shape, with wire's own provenance line.
- Widen the refutation test in both passes to cover intra-pass contradiction (item 2 above).
  Keep it annotate-only and keep the correction-phrase guidance as the *finding-driven* branch;
  add a *contradiction-driven* branch alongside it.
- Add `/ll:reconcile-issue` to `/ll:refine-issue`'s pipeline diagram and Next Steps block, and
  to the post-wire recommendation in `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — ENH-2992 already
  established that no human path leads to reconcile; this is the prose half of that fix.

**Open decision (`decision_needed`): should marker scope widen to `## Proposed Solution`?**

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

Options:

- **A — Widen all three** (carve-out scope, `_SUPERSEDED_DIRECTIVE_SECTIONS`, and reconcile's
  rewrite contract). Precedent exists: ENH-2937 added `## Scope Boundaries` to reconcile as a
  conditional carve-out (`reconcile-issue.md:49-65`). Highest fidelity, largest surface,
  reverses ENH-2995's design.
- **B — Widen the carve-out only.** Marker is human-readable but inert. Cheap and near-useless.
- **C — Do not widen; fix the trigger only. (Recommended.)** Two of ENH-3045's four sites are
  already in scope, so a working trigger marks the issue and routes it to reconcile regardless.
  Reconcile then rewrites the directive sections, and the surviving prose hedge in
  `## Proposed Solution` / `## Impact` is a cosmetic inconsistency rather than an implementable
  contradiction. Zero reversal of prior design, zero new re-fire risk.

Recommendation: **C**, with A recorded as a follow-up if prose-section drift proves to matter
independently.

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md` — Phase 8c annotation carve-out (455/500 lines today; the ENH-494
  companion pattern applies if this overflows, and see the mirror note below)
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
  Any edit breaks it until `ll-adapt --host gemini --apply && ll-adapt --host kimi --apply` runs.
- **Mirror companion gap** — the mirrors contain `SKILL.md` only;
  `skills/wire-issue/prose-dependency-gate.md` has no counterpart. If the carve-out is extracted
  to a companion to stay under the 500-line cap, it silently does not reach Gemini or Kimi and
  no test catches it. Budget the addition to fit inline, or bring companion mirroring into scope.

### Configuration
_Checked: `_SUPERSEDED_DIRECTIVE_SECTIONS` is a module constant, not config; no
`config-schema.json` or `.ll/decisions.yaml` entry governs marker scope. Clean unless Option A
is chosen._

### Similar Patterns
- `ENH-2995` — the carve-out being ported (done; read its Scope Boundaries before widening)
- `ENH-2992` — marker→routing consumer, and the 19/1,703 invocation-rate evidence
- `ENH-2937` — the precedent for conditionally extending reconcile's rewrite contract (Option A)
- `ENH-2996` — host-mirror sync test that any wire SKILL.md edit must satisfy

## Program Design

### Types
- `_SUPERSEDED_DIRECTIVE_SECTIONS: tuple[str, str, str]` — `("Implementation Steps",
  "Files to Modify", "Acceptance Criteria")`, `scripts/little_loops/issue_parser.py:644`.
  Unchanged under Options B/C; the single edit site under Option A.
- `_SUPERSEDED_MARKER_PREFIX: str` — `"⚠ Superseded"`, `issue_parser.py:645`; containment test,
  not equality, because the ≤10-word reason clause varies per pass.

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

1. Port the ENH-2995 carve-out into `skills/wire-issue/SKILL.md` Phase 8c; confirm the 500-line
   cap holds inline (455 today) before considering companion extraction.
2. Regenerate host mirrors: `ll-adapt --host gemini --apply && ll-adapt --host kimi --apply`.
3. Add the contradiction-driven branch to the refutation test in both wire and refine.
4. Add `/ll:reconcile-issue` to refine's pipeline diagram, Next Steps, and the
   `ISSUE_MANAGEMENT_GUIDE.md` post-wire step.
5. Resolve the `decision_needed` scope question (Options A/B/C); implement only if A.
6. `DOC_STRINGS_PRESENT` entries in `scripts/tests/test_wiring_skills_and_commands.py`.
7. Validate against `ENH-3045`: a wire pass over it marks the "optional" lines at `:118` and
   `:230`, `superseded_marker_count` returns ≥1, and `check_reconcile_needed` routes it.

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
