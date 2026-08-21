---
id: ENH-3280
type: ENH
title: decide-issue should propagate the selected option through the issue body
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T15:46:10Z'
labels:
- decide-issue
- skills
- pipeline
- consistency
relates_to:
- BUG-3278
- BUG-3279
- ENH-3277
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

Observed on ENH-3277 (2026-08-21), where Option A was selected and the body still contains:

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

### Tests

- A fixture whose body recommends the losing option: assert the marker is rewritten and reported
- A fixture with an `If <loser> is taken` conditional block: assert it is removed or demoted
- A fixture with an implementation step naming the loser: assert the step no longer instructs the
  rejected work
- An already-propagated fixture: assert a second run writes nothing (idempotency)

### Documentation

- `skills/decide-issue/reference.md` — Phase 9 output report template

## Implementation Steps

1. Write Phase 7c into `skills/decide-issue/SKILL.md` with the four reference categories and the
   explicit bounded-scope statement (option-keyed prose only, never a re-refine).
2. Extend the Phase 9 report template in `skills/decide-issue/reference.md` with a propagated-edits
   block and a flagged-but-not-edited block.
3. Verify against ENH-3277 as the live fixture: after a re-run, line 193's `Recommendation: Option
   C`, step 3b's `--raw` instruction, and the two Signatures entries are gone or demoted, and the
   stale counts are *flagged* rather than silently rewritten.

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

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-21T15:46:43 - `da526826-2179-460f-b823-35695378ac55.jsonl`
