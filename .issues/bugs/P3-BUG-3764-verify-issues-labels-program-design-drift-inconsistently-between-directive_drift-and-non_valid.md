---
id: BUG-3764
type: BUG
title: verify-issues labels Program Design drift inconsistently between DIRECTIVE_DRIFT
  and NON_VALID
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T00:49:19Z'
relates_to:
- BUG-3763
- ENH-3765
---

# BUG-3764: verify-issues labels Program Design drift inconsistently between DIRECTIVE_DRIFT and NON_VALID

## Summary

`/ll:verify-issues --check --auto` used different verdict categories for unresolved Program Design drift across three passes on BUG-3761 (run `.loops/.history/2026-10-07T000313-refine-to-ready-issue`). Reconcile and gap-analysis edited the issue between passes, so this trace demonstrates an ambiguous classification contract, not nondeterminism on byte-identical input:

- Pass 1 and pass 2: `DIRECTIVE_DRIFT` (routed to `check_reconcile_limit`).
- Pass 3: `NON_VALID`, which `ll-issues next-obligation` surfaces as `VERIFY:other` (routed to `check_gate_refine_limit`). The pass-3 output reasoned that Program Design is not among the sections `DIRECTIVE_DRIFT` covers.

`commands/verify-issues.md` defines `DIRECTIVE_DRIFT` as a check-B6 finding whose fix is confined to Implementation Steps / Acceptance Criteria / Integration Map, and names `reconcile-issue --from-verify-evidence` as its remedy. Program Design drift fits neither that definition nor any other verdict, so the model picks one non-deterministically. And when it does pick `DIRECTIVE_DRIFT`, the remedy refuses the section (see the companion Program Design rewrite-gap bug).

Side effect: `record_gate_unmet` only emits the `GATE_UNMET:DIRECTIVE_DRIFT_NON_CONVERGENCE` evidence tag when `check-verify-verdict --directive-drift` passes, so the flip to `NON_VALID` suppressed it on this run.

## Current Behavior

Program Design / Impact drift against a selected decision matches neither the `DIRECTIVE_DRIFT` definition (fix confined to Implementation Steps / Acceptance Criteria / Integration Map) nor the `NON_VALID` never-auto-correct set, so `/ll:verify-issues --check --auto` picks a verdict non-deterministically. On BUG-3761 it returned `DIRECTIVE_DRIFT` twice then `NON_VALID` (surfaced as `VERIFY:other`), and the flip suppressed the `GATE_UNMET:DIRECTIVE_DRIFT_NON_CONVERGENCE` evidence tag.

## Steps to Reproduce

1. Create a disposable fixture whose selected decision contradicts its `## Program Design`; optionally include an ordinary AC gap and stale Impact estimates. The current BUG-3761 file has been manually repaired.
2. Verify the fixture, reconcile its ACs, verify again, then perform additive gap-analysis and verify again. This matches the observed edits between iterations 15, 21 and 30.
3. The historical trace classified the first two passes as `DIRECTIVE_DRIFT` and the third as `NON_VALID`, explicitly because Program Design was outside the documented remedy scope. A fixed-input model evaluation is a separate validation, not an established reproduction from that trace.

## Expected Behavior

Program Design / Impact drift against a selected decision gets one deterministic verdict, with a defined remedy rung.

## Motivation

This fix would:
- Make `refine-to-ready-issue` routing deterministic: the same unchanged issue always takes the same repair rung.
- Restore the `GATE_UNMET:DIRECTIVE_DRIFT_NON_CONVERGENCE` evidence tag, which only `record_gate_unmet` emits when `check-verify-verdict --directive-drift` passes, so loop failures stay diagnosable.

## Proposed Solution

Decide where Program Design drift belongs: either widen `DIRECTIVE_DRIFT`'s section list (only sound if reconcile's contract also widens) or add an explicit verdict/obligation for it. Make the check-B6 classification text and the `next-obligation` token mapping agree.

## Integration Map

### Files to Modify
- `commands/verify-issues.md` — check-B6 classification text and the verdict table (`DIRECTIVE_DRIFT` row, `NON_VALID` never-auto-correct set, §2.5 precedence)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `route_pre_score_obligation` routes, `record_gate_unmet` non-convergence tag

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `classify_verify_verdict` (verdict → class) and the `--directive-drift` query used by `record_gate_unmet`
- `scripts/little_loops/cli/issues/next_obligation.py` — `_verify_class` maps `verify_verdict` to the `VERIFY:*` token

### Similar Patterns
- `PROPOSAL_UNSOUND` / `CLAIMS_OUTDATED` — verdicts persisted as their own value (not collapsed into `NON_VALID`) so a dedicated `VERIFY:*` route exists

### Tests
- `scripts/tests/test_ll_issues_check_verify_verdict.py`
- `scripts/tests/test_ll_issues_next_obligation.py`
- `scripts/tests/test_builtin_loops.py` (loop route assertions)

### Documentation
- `docs/reference/CLI.md` if a verdict/token is added (check `next-obligation` and `check-verify-verdict` entries)

### Configuration
- N/A

## Program Design

### Types

- `verify_verdict: str` — frontmatter enum persisted by verify-issues; gains an explicit value (or a widened `DIRECTIVE_DRIFT` definition) for Program Design / Impact drift

### Signatures

- `classify_verify_verdict(verdict: object) -> str` — accept the chosen verdict value
- `_verify_class(fm: dict[str, Any]) -> str` — map it to a `VERIFY:*` token

### Call Path

`/ll:verify-issues --check --auto` -> `verify_verdict` frontmatter -> `select_next_obligation` -> `_verify_class` -> `route_pre_score_obligation` -> `check_reconcile_limit` | `check_gate_refine_limit` -> `record_gate_unmet`

## Implementation Steps

1. Decide whether Program Design / Impact drift widens `DIRECTIVE_DRIFT` (requires the companion BUG-3763 reconcile-contract change) or gets its own verdict.
2. Update the check-B6 classification text and verdict-precedence table in `commands/verify-issues.md` to name that verdict.
3. Align `classify_verify_verdict`, `_verify_class`, and the `route_pre_score_obligation` / `record_gate_unmet` handling with it.
4. Add tests and run `python -m pytest scripts/tests/test_ll_issues_check_verify_verdict.py scripts/tests/test_ll_issues_next_obligation.py`.

## Impact

- **Severity**: Low on its own (the end state was the same here); makes loop failures harder to diagnose and breaks the non-convergence tag.
- **Affected**: `commands/verify-issues.md`, `scripts/little_loops/loops/refine-to-ready-issue.yaml` (`route_pre_score_obligation`, `record_gate_unmet`).

## Acceptance Criteria

- `commands/verify-issues.md` names the verdict for Program Design / Impact drift explicitly.
- Repeated `--check` passes on the same unchanged issue return the same verdict.
- `record_gate_unmet` tags non-convergence for that verdict.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-07 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-10-07T00:52:19 - `8092456a-7bf3-47b0-86f7-42712002052b.jsonl`
- `/ll:capture-issue` - 2026-10-07T00:49:25 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
