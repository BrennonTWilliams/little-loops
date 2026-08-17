---
id: ENH-3246
type: ENH
title: Widen reconcile-issue's rewrite mandate to the whole Integration Map
priority: P2
status: done
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T19:30:00Z'
completed_at: '2026-08-17T22:11:17Z'
relates_to:
- ENH-3244
- ENH-3247
- ENH-3248
- ENH-3238
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3246: Widen reconcile-issue's rewrite mandate to the whole Integration Map

## Summary

`/ll:reconcile-issue`'s rewrite list covers `### Files to Modify` but not its four sibling
subsections under `## Integration Map` (`### Dependent Files`, `### Similar Patterns`, `### Tests`,
`### Documentation`), so template debris and findings-contradicted claims in those four have no
owner. Widen the mandate to the whole section; the existing tracing requirement already bounds it.

## Current Behavior

`commands/reconcile-issue.md`'s binding contract (lines 44-47) grants in-place rewrite over exactly
three unconditional sections plus one conditional:

1. `## Implementation Steps`
2. `## Acceptance Criteria`
3. `### Files to Modify` (under `## Integration Map`)
4. `## Scope Boundaries` — conditional, only when a claim is directly contradicted by a recorded
   finding (ENH-2937)

`### Files to Modify` is singled out; its four siblings under the same parent heading fall under
"Preserve untouched — never edit, reorder, or delete … Every other section not in the rewrite list
above."

Measured on ENH-3238 after a full `refine-to-ready-issue` run, the `## Integration Map` section
contained five unfilled placeholders:

| Subsection | Content on reaching `done` | Reconcile-eligible |
|---|---|---|
| `### Files to Modify` | `TBD - requires codebase analysis` | ✅ yes |
| `### Dependent Files (Callers/Importers)` | `TBD - use grep to find references` | ❌ no |
| `### Similar Patterns` | `TBD - search for consistency` | ❌ no |
| `### Tests` | `TBD - identify test files to update` | ❌ no |
| `### Documentation` | `TBD - docs that need updates` | ❌ no |

The issue's own `### Codebase Research Findings` **did** contain the material to fill all five —
refine had deposited detailed per-file research — but reconcile is contractually barred from
applying it to four of them.

## Expected Behavior

`/ll:reconcile-issue`'s unconditional rewrite list reads `## Integration Map` (the whole section,
including all subsections) in place of the single `### Files to Modify` entry.

Where a finding supports a subsection's content, reconcile rewrites it. Where no finding supports
it, the existing tracing rule applies unchanged: leave the bullet as-is and note it under
`## CONCERNS`.

## Motivation

The current line is arbitrary. `### Files to Modify` and `### Tests` are the same kind of content —
directive statements about which files this issue touches — derived from the same source (`###
Codebase Research Findings`), and stale in the same way for the same reason (refine only appends).
Nothing in the contract's rationale distinguishes them; `### Files to Modify` was simply the one
enumerated when the contract was written.

The cost of the gap is that four fifths of a section's debris survives a pass that was already
reading the findings needed to clear it, on a file it already had open.

This is also a prerequisite for ENH-3248's retry triage: routing a placeholder-detection failure to
reconcile only helps if reconcile is permitted to fix the subsections where placeholders actually
accumulate.

## Proposed Solution

1. In `commands/reconcile-issue.md`, replace rewrite-list entry 3 (`### Files to Modify`) with
   `## Integration Map` — the whole section, subsections included.
2. Remove `## Integration Map`'s subsections from the "Preserve untouched" enumeration.
3. **Add an explicit wiring-marker preservation rule.** `_Wiring pass added by \`/ll:wire-issue\`:_`
   blocks are reconcile's **input** wherever they appear, and must stay preserved even inside a
   now-rewritable subsection. This is a genuine gap in the current preserve list, not a restatement:
   the existing term preserves the `### Wiring Phase` H3 (under `## Implementation Steps`), but
   `/ll:wire-issue` also deposits marker blocks *directly inside* `### Dependent Files
   (Callers/Importers)`, `### Tests`, and `### Documentation` — exactly the subsections this issue
   makes writable. BUG-3245's own file is the specimen: four separate `_Wiring pass added by …:_`
   blocks nested under Integration Map subsections (`:234-250`, `:254-278`). Without this rule, the
   widening lets reconcile rewrite its own source, which is the circularity the existing
   findings-preservation term exists to prevent.
4. Leave every other contract term unchanged — in particular the two guardrails that make this safe:
   - **Source restriction**: "You are reconciling the issue *against itself* — do not go re-research
     the codebase (that is `/ll:refine-issue`'s job) and do not verify paths against the tree (that
     is `/ll:ready-issue`'s job)."
   - **Tracing requirement**: "Every rewritten claim must trace to an existing finding … if a
     directive bullet has no supporting finding, leave it as-is and note it under `## CONCERNS`."
5. Regenerate host mirrors with `ll-adapt` (see Integration Map).

### Behavior Parity

This issue replaces a term in `commands/reconcile-issue.md`'s binding contract. Each behavior of the
current contract, with its disposition:

| Current behavior | Disposition |
|---|---|
| Rewrites `## Implementation Steps` | **Preserved** — untouched |
| Rewrites `## Acceptance Criteria` | **Preserved** — untouched |
| Rewrites `### Files to Modify` | **Changed** — subsumed by the widened `## Integration Map` entry; the subsection is still rewritable, now alongside its four siblings |
| Conditionally rewrites `## Scope Boundaries` on a findings contradiction (ENH-2937) | **Preserved** — the conditional guard and its precondition are unchanged |
| Clears `⚠ Superseded` markers on every directive line evaluated, including the no-op branch | **Preserved** — unchanged; `autodev.yaml`'s `check_reconcile_needed` routes on marker presence and must keep working |
| Preserves `### Codebase Research Findings` / `### Wiring Phase` | **Preserved** — these are reconcile's input; still never written |
| Preserves `_Wiring pass added by …:_` blocks nested *inside* Integration Map subsections | **Newly stated** — previously covered only incidentally, by the blanket preservation of those subsections. That blanket is being dropped, so this becomes an explicit term (Proposed Solution § 3). Same rationale as the findings-preservation term: it is reconcile's input. |
| Preserves `## Summary` / `## Motivation` / `## Current Behavior` / `## Expected Behavior` / `## Proposed Solution` | **Preserved** — unchanged |
| Preserves `## Integration Map`'s four non-`Files to Modify` subsections | **Dropped** — this is the point of the issue; they become rewritable |
| Source restriction: reconciles the issue against itself, never re-researches the codebase | **Preserved** — explicitly unchanged |
| Tracing requirement: unsupported bullets stay as-is and go to `## CONCERNS` | **Preserved** — this is the guardrail that makes the widening safe |
| Arms `reconcile_attempted: true` before rewriting | **Preserved** — unchanged |

Nothing is dropped except the preservation of the four subsections, which is the change itself — and
the wiring-marker blocks nested inside them are re-preserved by an explicit term so that drop does
not silently take them along. No behavior is silently lost.

## Integration Map

### Files to Modify
- `commands/reconcile-issue.md` — the Contract block (lines 44-47) and the "Preserve untouched"
  enumeration (lines ~80-86).
- Host mirrors are generated, never hand-edited: `ll-adapt --host <gemini|qwen|kimi-code> --apply`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml:1557-1608` — `check_reconcile_needed`, the only current
  caller. Widening what reconcile rewrites does not change what arms this gate
  (`superseded_marker_count` plus the readiness-plateau terms), so the routing contract is untouched.
- `scripts/little_loops/loops/autodev.yaml:1921` — the `reconcile_current` invocation.
- ENH-3248 — the proposed second caller, in `refine-to-ready-issue.yaml`.

### Similar Patterns
- ENH-2937's `## Scope Boundaries` carve-out — the precedent for extending reconcile's rewrite scope.
  That one needed a conditional guard because Scope Boundaries is human prose; `## Integration Map`
  subsections are machine-deposited directive content, so this widening is unconditional and simpler.

### Tests
- `scripts/tests/` — assert the widened section list appears in `commands/reconcile-issue.md` and
  that the four subsections no longer appear in the preserve list. Follow the content-assertion
  pattern used for command-file changes elsewhere in the suite.

### Documentation
- N/A — the contract lives in the command file itself.

### Configuration
- N/A

## Program Design

### Call Path

`check_reconcile_needed` -> `reconcile_current` -> `superseded_marker_count`

- `check_reconcile_needed` (`scripts/little_loops/loops/autodev.yaml:1557`) arms on a readiness
  plateau or a non-zero `superseded_marker_count`; unchanged by this issue.
- `reconcile_current` (`autodev.yaml:1921`) invokes `/ll:reconcile-issue ${captured.input.output}`.
- `superseded_marker_count(issue_path: Path) -> int`
  (`scripts/little_loops/issue_parser.py:1173`) is the deterministic signal the gate reads.

### Decision Rules

- **Scope of the widening**: `## Integration Map` and every `###` subsection under it. Not a general
  loosening — the rewrite list stays a closed enumeration.
- **Bounding guardrails (unchanged)**: self-referential source only; every rewritten claim traces to
  an existing finding; unsupported bullets go to `## CONCERNS` rather than being invented.
- **Input blocks stay preserved regardless of which section holds them.** The preserve/rewrite line is
  drawn by *provenance*, not by *location*: a `_Wiring pass added by …:_` or
  `_Added by \`/ll:refine-issue\` …:_` block is machine-deposited research that reconcile reads, so it
  is preserved even when nested inside a subsection that is otherwise rewritable. Location-based
  preservation was sufficient only while the whole subsection was off-limits.
- **Why unconditional**: unlike ENH-2937's Scope Boundaries carve-out, these subsections hold
  machine-deposited directive content, not human prose, so no contradiction precondition is needed.

### Signatures
- `superseded_marker_count(issue_path: Path) -> int` — `scripts/little_loops/issue_parser.py:1173`;
  the deterministic count arming `check_reconcile_needed`. Unchanged by this issue, listed because
  the gate contract must be verified untouched.

## Implementation Steps

1. Replace rewrite-list entry 3 with `## Integration Map` in `commands/reconcile-issue.md`.
2. Remove those subsections from the "Preserve untouched" enumeration.
3. Add the wiring-marker preservation term to the preserve list, scoped by provenance rather than
   location (Proposed Solution § 3).
4. Regenerate the three host mirrors via `ll-adapt`.
5. Add the content-assertion tests, including one asserting the wiring-marker term is present and
   that `### Tests` / `### Dependent Files (Callers/Importers)` no longer appear in the preserve list.
6. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 - Unblocks four fifths of the Integration Map debris that survives a refine run,
  and is a prerequisite for ENH-3248. Not P1: the capability exists and the gap degrades issue
  quality rather than breaking behavior.
- **Effort**: Small - a contract edit in one markdown file plus regeneration and tests.
- **Risk**: Low - the two guardrails that prevent reconcile from inventing content are untouched, so
  the worst case is a subsection left as-is with a `## CONCERNS` note, which is the current behavior.
- **Breaking Change**: No

## Scope Boundaries

**Not loosening reconcile's source restriction.** It still reconciles the issue against itself and
never re-researches the codebase. This issue widens *which sections it may write*, not *what it may
read*. The substantive errors on ENH-3238 (a wrong edit-site and a wrong generated-file claim)
required codebase probing and remain out of reconcile's reach by design — that class belongs to
`verify_issue` and is ENH-3238's subject.

**Not touching the preserved research sections.** `### Codebase Research Findings` and
`### Wiring Phase` stay on the preserve list — they are reconcile's *input*, and letting it rewrite
its own source would be circular. **This extends to `_Wiring pass added by …:_` and `_Added by
\`/ll:refine-issue\` …:_` blocks nested inside the newly-rewritable Integration Map subsections** —
preservation follows provenance, not location (Proposed Solution § 3, Decision Rules). Structural
debris inside any of them is ENH-3247's subject.

## Related Issues

- ENH-3247 — deterministic repair of structural debris in the sections reconcile must not touch.
- ENH-3248 — the retry triage that depends on this widening to be worth routing to.
- ENH-3244 — placeholder detection, which produces the signal that would route here.
- ENH-3238 — the run that surfaced all of this.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._


## Blocks

- ENH-3248

## Status

**Open** | Created: 2026-08-17 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-17T22:10:54 - `a1cb8198-d1dc-40cc-a534-5a26f3efa932.jsonl`
- `/ll:capture-issue` - 2026-08-17T19:29:38 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
