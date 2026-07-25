---
id: BUG-2820
type: BUG
priority: P2
status: open
captured_at: "2026-07-25T22:53:35Z"
discovered_date: 2026-07-25
discovered_by: capture-issue
labels: [refine-issue, decision-gate, skills, autodev]
relates_to: [ENH-2607, ENH-2443, ENH-2446, BUG-2605, FEAT-2817]
---

# BUG-2820: refine-issue deposits Option A/B into a section the decidability probes never scan

## Summary

`/ll:refine-issue --auto` formats a decision point as a `**Option A** / **Option B** /
**Recommended**` block (ENH-2607) and sets `decision_needed: true`, but places the block *"under
a `### Codebase Research Findings` addendum near the original prose"*
(`commands/refine-issue.md:299-300`). When the original prose lives outside the three H2 sections
that `count_enumerable_options()` scans, the deposited options are invisible to
`ll-issues check-decidable`. The issue then carries `decision_needed: true` with zero
machine-visible options — a gate that can never be satisfied — and `autodev` defers it as
`decision_unresolved`.

## Current Behavior

FEAT-2817, refined 2026-07-25. `refine-issue` correctly identified a genuine architectural fork,
formatted it exactly as ENH-2607 specifies, and set `decision_needed: true`. It placed the block
under the pre-existing decision prose, which lived in `## Open Questions`:

```
 96  ## Proposed Solution
124    ### Codebase Research Findings                                  ← scanned; contains no options
158  ## Implementation Steps
231  ## Open Questions
238    ### Codebase Research Findings — delegation architecture decision
         **Option A**: ...   **Option B**: ...   **Recommended**: Option A   ← never scanned
```

Measured on the real file:

```
count_enumerable_options(content)        -> 0
count_unresolved_options(content)        -> 0
count_open_questions_in_sections(content)-> 1
```

`autodev.yaml`'s `check_decision_decidable` therefore exits 1 with both probes failing:

```
OPEN_QUESTIONS_REMAIN: FEAT-2817 — 1 open question(s) and 0 unresolved option(s)
OPTIONS_MISSING: FEAT-2817 — decision_needed is true but ## Proposed Solution has no
                 enumerable alternatives; run /ll:refine-issue FEAT-2817 --auto
```

The `deposit_options` remedy re-runs the same `/ll:refine-issue --auto` that just produced this
state, so even absent BUG-2818 it would deposit into the same unscanned location and the gate
would fail identically on the retry.

Two independent mismatches cause the miss. `_section_body()`
(`scripts/little_loops/issue_parser.py:115-127`) matches `^##\s+{heading}\s*$` — **H2 only, exact
text** — and options are counted only in `Proposed Solution` plus the
`_OPTION_FALLBACK_SECTIONS = ("Codebase Research Findings", "Implementation Status")`
(`issue_parser.py:300`):

1. The addendum is an **H3 nested under a non-scanned H2** (`## Open Questions`), so it is not
   reachable by any scanned section.
2. Even promoted to H2, the `— delegation architecture decision` suffix breaks the exact-heading
   match.

## Expected Behavior

When `refine-issue` sets `decision_needed: true`, the options it deposited are always countable
by `ll-issues check-decidable`. Concretely: the Option block is written into
`## Proposed Solution` (at any depth within it), or into a heading the probes actually scan, and
the skill verifies this before setting the flag — `decision_needed: true` and
`count_enumerable_options() == 0` should be an unreachable combination for refine-written
content.

## Motivation

This is the exact failure ENH-2443 and ENH-2446 built the deterministic probes to prevent, and
that ENH-2607 built the formatting rule to prevent — reached anyway through the gap between
them. The cost is a fully-refined, well-researched issue being deferred with a misleading
`decision_unresolved` code that says "decide-issue produced no actionable decision" when in
truth a clear recommendation ("Option A") was sitting in the file the whole time. The operator
is pointed at `/ll:decide-issue`, which will hit the same invisible-options wall.

## Steps to Reproduce

1. Take an issue whose decision prose lives under `## Open Questions` (not `## Proposed
   Solution`) — e.g. FEAT-2817 at commit `5525e9ae`.
2. Run `/ll:refine-issue FEAT-2817 --auto`.
3. Observe `decision_needed: true` in frontmatter and a well-formed `**Option A**/**Option B**`
   block under `## Open Questions`.
4. `ll-issues check-decidable FEAT-2817` → exit 1, `OPTIONS_MISSING`.
5. `ll-loop run autodev FEAT-2817` → deferred, `deferred_reason: decision_unresolved`.

## Environment

- little-loops @ `main`, 2026-07-25
- Observed on FEAT-2817 in run `.loops/runs/autodev-20260725T171820/`

## Frequency

Every issue whose pre-existing decision prose sits outside the three scanned H2 sections —
`## Open Questions` is the common case, since that is where capture and confidence-check
naturally record unresolved questions.

## Root Cause

`commands/refine-issue.md:299-300` specifies placement relative to *prose location* ("near the
original prose", per the Preservation Rule) while the consumers
(`count_enumerable_options` / `count_unresolved_options`) select by *section identity*. The two
rules were written against different models of where content lives and nothing cross-checks them.
The skill's Option-Count Detection step (`refine-issue.md:305-315`) counts options in the content
it just wrote — not in the sections the probes will read — so it sets `decision_needed: true` on
evidence the downstream gate cannot reproduce.

## Proposed Solution

Make the deposit location match what the probes read, and verify rather than assume:

1. **Placement rule** — amend `commands/refine-issue.md`'s Decision-Point Formatting step: the
   Option block always goes inside `## Proposed Solution` (appending a `### Options` /
   `### Codebase Research Findings` subsection there), regardless of where the source prose sat.
   Leave a one-line cross-reference at the original prose location so the Preservation Rule's
   intent — don't orphan human context — is still met.
2. **Verify before flagging** — before setting `decision_needed: true`, shell out to
   `ll-issues check-decidable <ID>`. If it exits 1, the options were deposited somewhere the gate
   cannot see: fix the placement (or do not set the flag) rather than creating an unsatisfiable
   gate. This turns an invisible mismatch into a self-correcting step and reuses the existing
   deterministic probe rather than duplicating its logic in prose.
3. Keep the exact-heading requirement in mind for any generated heading text — no `— suffix`
   decoration on headings the probes match by name.

BUG-2820 and the generalized probe-scope widening (ENH-2821) are complementary: this issue makes
the writer deposit where the reader looks; ENH-2821 makes the reader more forgiving. Landing
either alone fixes FEAT-2817; landing both closes the class.

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — Decision-Point Formatting (lines ~284-303) and Option-Count
  Detection (lines ~305-315)
- `scripts/tests/` — a skill-contract test asserting the placement/verification rule is present

### Similar Patterns
- `skills/decide-issue/SKILL.md` Phase 3b-i — the resolved-marker vocabulary the probes mirror
- ENH-2446's `check-open-questions` — precedent for a coverage-aware deterministic probe

### Tests
- Fixture issue with decision prose under `## Open Questions`, run the placement rule, assert
  `count_enumerable_options() >= 2` afterwards.
- Assert the `decision_needed: true` + `check-decidable == 1` combination is not producible from
  a refine-written fixture.

## Implementation Steps

1. Rewrite the placement rule in `commands/refine-issue.md` to target `## Proposed Solution`.
2. Add the `ll-issues check-decidable` verification step before the `decision_needed: true` write.
3. Add the fixture-based tests above.
4. Re-refine FEAT-2817 and confirm `ll-issues check-decidable FEAT-2817` exits 0.

## Impact

- **Severity**: High — creates unsatisfiable decision gates that defer fully-researched issues.
- **Scope**: `autodev`, `rn-remediate`, and every loop routing through `check_decision_decidable`.
- **Known instance**: FEAT-2817 (currently `deferred` / `decision_unresolved`).
- **Workaround**: manually move the Option block into `## Proposed Solution`.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` § Issue File Format | deferral reason codes, `decision_unresolved` |
| `commands/refine-issue.md` | Decision-Point Formatting / Option-Count Detection |
| `skills/decide-issue/SKILL.md` | resolved-option marker vocabulary |

## Session Log
- `/ll:capture-issue` - 2026-07-25T22:53:35Z - `ae9c212c-ff4e-4576-a5c4-7457be6284e5.jsonl`

---

## Status

open
