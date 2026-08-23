# decide-issue reference

Extracted from `SKILL.md` (ENH-494 500-line budget). Referenced from Phase 3b, Phase 4, Phase 6,
Phase 7c, Phase 9, and Integration.

## Phase 7c Rewrite Categories (ENH-3280)

`_unapplied_decision`'s output (surfaced structurally via the `unapplied_decision_detail` format-check
key) is a **candidate list, not an edit list**. A candidate is *edited* only when its surrounding
prose also matches one of the four categories below; every other candidate is *flagged* in the
Phase 9 report and left untouched. This is what keeps BUG-3289's accepted residual of
shared-vocabulary false positives (e.g. a bare `` `ProjectConfig` `` mention in narrative prose)
harmless — it matches none of the four categories, so it is flagged, never rewritten.

1. **Recommendation markers naming a loser** — `Recommendation: <X>`, `Recommended: <X>`,
   `we should take <X>` where `<X>` is not the winner. Rewrite to name the selection, or strike
   and fold into the Decision Rationale as a "considered and rejected" line.
2. **Conditional blocks keyed to an option** — `If <X> is taken, …`, `Under <X>, …`, `conditional
   on the DECISION REQUIRED outcome`. For the winner: unwrap the condition and state it
   declaratively. For a loser: delete, or demote to a parenthetical under the rejected option.
3. **Imperative steps referencing a loser** — any `## Implementation Steps` item naming a rejected
   option. Rewrite to the winner's shape or mark not-applicable — never left as-is.
4. **Sections the issue itself flags** — an explicit propagation checklist for the selected
   option, present in the issue body; apply it item by item and report each edit.

**Bounded scope.** Phase 7c rewrites prose keyed to the option set only — it does not restate
counts, re-derive scope, or re-run analysis. Where propagation implies a downstream change it
cannot safely make (stale counts, an untouched `## Scope Boundaries` figure), flag the location
in the Phase 9 report rather than editing it.

## Phase 3b Provisional Patterns A–D — full match shapes (moved from SKILL.md, BUG-3278)

### Provisional Pattern A — Parenthetical `(e.g., ...)`
```
Match: parenthetical containing `e.g.,` followed by a concrete name
Example: (e.g., completed_at: frontmatter field)
Candidate: the specific approach named inside the parenthetical
```

### Provisional Pattern B — Inline `TBD` design marker
```
Match: `TBD` used as a placeholder for a design decision (not a research gap)
Surrounding context must name a single approach being considered
Example: "field name: TBD (leaning toward completed_at)"
Candidate: the approach mentioned in the surrounding sentence
```

### Provisional Pattern C — Definitive replacement language
```
Match: phrases like "fundamental rethink" / "must be replaced with" / "should be replaced by"
Example: "the existing approach must be replaced with direct file writes"
Candidate: the concrete replacement approach named
```

### Provisional Pattern D — Declarative recommendation
```
Match: prose naming a winning option without a provisional wrapper:
  **Recommended**: (b)  /  the recommendation is now (b)  /  Refresh N supersedes prior — (a)+(b)
Candidate: the referenced option(s); multi-part winners like (a)+(b) are allowed.
Requirement: the referent must exist as a Pattern-4 bullet option in `## Proposed Solution` or
`## Codebase Research Findings` (existing-bullet case), OR the referent must be one of 2+
concrete alternatives named inline in an unresolved `## Open Questions` item (ENH-2715) — e.g.
"could do X or Y" with a stated preference; no pre-existing bullet is required for this shape,
since the alternatives are materialized as structured options in Resolution Logic step 1 below.
A marker (or an Open-Questions item naming a preference) with a resolvable referent is a
**clear winner** — treat as decided. Same shape, **no** stated preference → Pattern E below.
```

## Phase 3b Pattern E — full rationale and worked example (ENH-2936)

Pattern E exists to close a specific remedy-chain gap (ENH-2866): an issue can name 2+ concrete
alternatives plus an explicit imperative to decide ("stamp it or move it to Out of scope with a
stated reason — do not leave it unaddressed") but state no preference. Pattern D requires a
stated preference to materialize inline alternatives, so this shape fell through every
extraction pattern and `decide-issue` exited `NO_ACTIONABLE_DECISIONS`, leaving
`decision_needed: true` unresolved indefinitely — nothing else in the pipeline can clear a
`decision_needed` flag it did not earn.

The imperative marker is what distinguishes this from the settled-informal-list case that Phase
3's auto-mode conservatism protects against elsewhere (automation must not re-litigate a list
the author already settled). Here the issue text explicitly *asks* for a decision, so scoring it
re-litigates nothing.

Worked example (from ENH-2866's `## Scope Boundaries`):
> "stamp it or move it to Out of scope with a stated reason — do not leave it unaddressed"

This matches Pattern E: two alternatives ("stamp it" / "move it to Out of scope") within 3 lines
of an imperative marker ("do not leave it unaddressed"), no stated preference between them. It
is materialized as `**Option A**: stamp it` / `**Option B**: move it to Out of scope` and routed
to Phase 4 scoring.

**Match shape.** The Phase 3 `locate-options` call's JSON result carries `pattern ==
"provisional_e"`; the single `options[0].text` entry is the matched window — 2+ concrete
alternatives ("X or Y", enumerated alternatives) named within ~3 lines of an imperative
decide-marker ("decide before implementation", "do not leave (it/this) unaddressed", "must be
decided", "decision needed/required before", "pick one"), with NO stated preference (no
Pattern-D-style recommendation marker naming one of them as the winner). Bare "X or Y" prose
with no imperative marker is explicitly NOT Pattern E (the settled-informal-list case Phase 3's
auto-mode conservatism already protects against).

**Scan scope** (narrower than Patterns A–D, and already applied by the CLI): `## Scope
Boundaries`, `## Proposed Change` / `## Proposed Solution`, and unresolved `## Open Questions`
items. The precedence/exclusion regexes themselves live only in
`issue_parser._locate_directive_alternatives` (ENH-2950).

## Phase 7a Marker-Placement Matrix, per decision-group tier (BUG-3278)

| Tier | Marker | Placement |
| --- | --- | --- |
| `section_header` / `bold_label` | `> **Selected:** [title] — [rationale]` | Immediately after the winning option's title line |
| `bullet` / `numbered` | `> **Selected:** (x) — per the stated recommendation` | Immediately after the winning bullet's line (part 1's span rule keeps this inside the group) |
| `provisional_e` | Retirement is **probe suppression**, never a callout — see below | On the directive line itself, nowhere else |

A `provisional_e` group has no option title line to attach a callout to, and
`_locate_directive_alternatives`' sliding-window suppressors only see a marker placed **on the
directive line itself** — a marker on a neighbouring line always leaves one window that holds the
imperative but not the marker, so the group re-emits forever. The prescribed form is a bare
`**RESOLVED**` bold run — closing **immediately** at `RESOLVED` — with the reason **outside** the
bold run:

```markdown
**RESOLVED** — the shim. **DECISION — pick one before step 4: use the shim or rewrite the caller.**
```

Verified against the live tree (2026-08-23). A decorated bold run (`**RESOLVED — the shim.**`,
`**RESOLVED:** the shim.`) matches **nothing** — `_RESOLVED_QUESTION_MARKER_RE`'s alternatives all
require the closing `**` immediately after `RESOLVED` — and leaves the group emitting forever. An
appended `> **Selected:**` callout also suppresses the probe (via `_PREFERENCE_MARKER_RE`), but is
not itself a valid `_SELECTED_CALLOUT_RE` match (line-anchored) and a mid-line `>` is not valid
blockquote syntax — so it is not the prescribed form, even though it happens to work.

## Phase 3b Step 4 Exit-Code Disposition (BUG-3278)

| `check-unresolved-decisions` exit | Meaning | Phase 3b step 4 action |
| --- | --- | --- |
| 0 | No unresolved decision group remains | Write `decision_needed: false`, log success |
| 1 | A real residual group survives | No frontmatter write; log `decision_needed remains true`; carry groups to Phase 9 |
| 2+ | Unresolvable ID / unverifiable probe | Treat as exit 1 — never clear on an unverifiable probe |

## When to Use vs. Related Commands

| Skill | Purpose |
|-------|---------|
| `refine-issue` | Fills knowledge gaps; may deposit competing options |
| `decide-issue` | Selects the best option from competing alternatives using codebase evidence |
| `wire-issue` | Traces all wiring touchpoints for the selected implementation |
| `confidence-check` | Evaluates implementation readiness score |

`decide-issue` is specifically for the "refine-issue deposited multiple options but hasn't
selected one" problem. It consumes `decision_needed: true` and produces a clear, annotated
winner so the pipeline can continue.

## Phase 6 Decision Rationale Subsection Template

```markdown
### Decision Rationale

Decided by `/ll:decide-issue` on YYYY-MM-DD.

**Selected**: [option title]

**Reasoning**: [2-3 sentence explanation citing specific codebase evidence]

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| [Option A] | N/3 | N/3 | N/3 | N/3 | N/12 |
| [Option B] | N/3 | N/3 | N/3 | N/3 | N/12 |

**Key evidence**:
- [Option A]: [1-2 sentence evidence summary]
- [Option B]: [1-2 sentence evidence summary]
```

## Phase 4 Agent Prompt Template

For each option, the agent prompt template is:

```
Use Agent tool with subagent_type="ll:codebase-pattern-finder"

Prompt:
Find codebase evidence for or against this implementation option for {{ISSUE_ID}}.

Issue: {{ISSUE_ID}} — {{issue title}}

Option being evaluated: "{{option_title}}"
Option description: {{option_description}}

Find:
1. Existing patterns that use this approach — similar implementations already in the codebase
2. Call site count — how many places currently use a similar pattern
3. Existing utilities, helpers, or modules that this option could reuse
4. Patterns that conflict with or differ from this approach (evidence against)
5. Test patterns for this type of implementation

Return:
- Evidence FOR: existing patterns, utilities, call sites (with file:line references)
- Evidence AGAINST: conflicting patterns or missing utilities that would require new infrastructure
- Reuse score: 0 (builds from scratch) to 3 (reuses existing utilities directly)
- Summary: 1-2 sentence assessment of codebase fit
```

## Phase 9 Output Report Template

```
================================================================================
DECIDE ISSUE: {{ISSUE_ID}}
================================================================================

## ISSUE
- File: [path]
- Type: [BUG|FEAT|ENH|EPIC]
- Title: [title]
- Mode: [Interactive | Auto] [--dry-run]
- decision_needed was: [true | false | absent]

## OPTIONS FOUND (N total)
- Option A: [title] — [one-line description]
- Option B: [title] — [one-line description]
...

## SCORING

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| [A]    | N/3         | N/3        | N/3         | N/3  | N/12  |
| [B]    | N/3         | N/3        | N/3         | N/3  | N/12  |

## DECISION
✓ Selected: [option title] (score: N/12)

Reasoning: [2-3 sentences]

## CHANGES APPLIED
- [Annotated issue with > **Selected:** callout | Skipped (idempotent)]
- [Appended ### Decision Rationale section | Skipped (idempotent)]
- decision_needed: [set to false | already false — no change | remains true — see below]
- Propagation (Phase 7c):
  - [section] (line [N]): `[identifier]` — [rewritten | demoted | struck]  ← one bullet per edit
  - ... | Skipped (idempotent) | Skipped — N decision point(s) still unresolved

⚠ decision_needed remains true — N unresolved decision point(s):  ← only shown on
  - [heading] (lines [start]-[end])                                 check-unresolved-decisions exit 1/2+ (BUG-3278)

⚠ Flagged, not edited (Phase 7c) — N candidate(s) matched no rewrite category:  ← only shown when
  - [section] (line [N]): `[identifier]`                                          residuals survive the bounded-scope rule

## DRY RUN PREVIEW  ← only shown when --dry-run
---
[Full annotation content that would be written]
---
Propagation (Phase 7c): not evaluated under --dry-run

## FILE STATUS
- [Modified | Not modified (--dry-run | nothing to change)]

## NEXT STEPS
- Run `/ll:wire-issue {{ISSUE_ID}}` to add integration wiring (callers, entry points, test hooks)
- Run `/ll:ready-issue {{ISSUE_ID}}` to validate the issue is ready to implement
- Run `/ll:manage-issue feature implement {{ISSUE_ID}}` to implement

================================================================================
```
