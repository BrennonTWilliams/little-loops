---
id: ENH-3246
type: ENH
title: Widen reconcile-issue's rewrite mandate to the whole Integration Map
priority: P2
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T19:30:00Z'
relates_to:
- ENH-3244
- ENH-3247
- ENH-3248
- ENH-3238
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
3. Leave every other contract term unchanged — in particular the two guardrails that make this safe:
   - **Source restriction**: "You are reconciling the issue *against itself* — do not go re-research
     the codebase (that is `/ll:refine-issue`'s job) and do not verify paths against the tree (that
     is `/ll:ready-issue`'s job)."
   - **Tracing requirement**: "Every rewritten claim must trace to an existing finding … if a
     directive bullet has no supporting finding, leave it as-is and note it under `## CONCERNS`."
4. Regenerate host mirrors with `ll-adapt` (see Integration Map).

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
- **Why unconditional**: unlike ENH-2937's Scope Boundaries carve-out, these subsections hold
  machine-deposited directive content, not human prose, so no contradiction precondition is needed.

### Signatures
- `superseded_marker_count(issue_path: Path) -> int` — `scripts/little_loops/issue_parser.py:1173`;
  the deterministic count arming `check_reconcile_needed`. Unchanged by this issue, listed because
  the gate contract must be verified untouched.

## Implementation Steps

1. Replace rewrite-list entry 3 with `## Integration Map` in `commands/reconcile-issue.md`.
2. Remove those subsections from the "Preserve untouched" enumeration.
3. Regenerate the three host mirrors via `ll-adapt`.
4. Add the content-assertion tests.
5. `python -m pytest scripts/tests/` exits 0.

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
its own source would be circular. Structural debris inside them is ENH-3247's subject.

## Related Issues

- ENH-3247 — deterministic repair of structural debris in the sections reconcile must not touch.
- ENH-3248 — the retry triage that depends on this widening to be worth routing to.
- ENH-3244 — placeholder detection, which produces the signal that would route here.
- ENH-3238 — the run that surfaced all of this.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-17 | Priority: P2
