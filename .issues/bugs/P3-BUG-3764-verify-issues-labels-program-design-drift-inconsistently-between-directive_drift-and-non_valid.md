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
blocked_by:
- BUG-3763
---

# BUG-3764: verify-issues labels Program Design drift inconsistently between DIRECTIVE_DRIFT and NON_VALID

## Summary

Verification has no explicit category for selected-decision drift in Program Design or Impact Effort/Risk. In BUG-3761's historical run, verify classified these residuals as `DIRECTIVE_DRIFT` twice, then `NON_VALID`, because the documented directive-drift remedy excluded Program Design. Define a narrow classification aligned with BUG-3763's repair contract; keep the existing verdict and token machinery.

## Current Behavior

The run `.loops/.history/2026-10-07T000313-refine-to-ready-issue` returned `DIRECTIVE_DRIFT` at iterations 15 and 21, then `NON_VALID` at iteration 30. Reconcile and gap-analysis edited the issue between those checks. This demonstrates an ambiguous classification contract across related revisions, not nondeterminism on byte-identical input.

`commands/verify-issues.md` B6 defines `DIRECTIVE_DRIFT` by repairs confined to Implementation Steps, Acceptance Criteria or Integration Map. The third pass explicitly excluded Program Design on that basis. `NON_VALID` becomes `VERIFY:other`, so the classification also changes the remedy and suppresses the current-verdict-dependent non-convergence tag.

## Steps to Reproduce

1. Create a disposable fixture with a selected option and Decision Rationale, rejected-option Program Design directives, stale decision-derived Impact estimates and an ordinary AC gap. The current BUG-3761 file is already manually repaired.
2. Verify, reconcile the ACs, verify again, perform additive gap-analysis, then verify again. These are the edits between the observed iterations 15, 21 and 30.
3. Compare the documented B6 scope with those verdicts. A fixed-input model evaluation is a separate validation; this trace does not establish its results.

## Expected Behavior

A selected mechanism that still stands, with specifically identified rejected-option Program Design directives or Impact Effort/Risk text, qualifies for `DIRECTIVE_DRIFT` and names the conditional reconcile remedy. Verification retains higher-priority defects and reports uncertainty rather than authorizing invented design.

## Motivation

Align finding classification with an actual repair owner and keep repeated evaluations of the same drift class on the same intended route. Prompt improvements can reduce misclassification; they cannot guarantee deterministic model behavior.

## Proposed Solution

**Widen the existing `DIRECTIVE_DRIFT` definition conditionally; do not add a verdict or obligation.** Blocked by BUG-3763, whose eligible remedy must exist before verification advertises it.

- Update B6, the verdict table and check-mode persistence guidance together. Ordinary directive drift keeps its existing definition.
- The additional category requires a recorded selected option and Decision Rationale, a mechanism that still stands, and a correction restricted to named Program Design directive passages or decision-derived Impact Effort/Risk lines. Use canonical `Program Design:` or `Impact:` evidence-item prefixes (not composite headings), and identify the specific passages plus the correction entailed by the selection; do not turn a section heading into blanket rewrite authority.
- Collect all applicable findings in one pass, including ordinary AC/Step/Integration Map drift and decision-derived design/estimate drift. Persist the complete escaped, single-line `verify_evidence` with `DIRECTIVE_DRIFT` in the same frontmatter update, replacing earlier evidence. `--check` remains frontmatter-only.
- Treat `unapplied_decision_detail` as candidate evidence requiring contextual review. It scans Program Design but not Impact; inspect Impact semantically. Preserve historical option comparisons and research blocks; a shared-vocabulary candidate alone is insufficient.
- Absent or ambiguous selection, an unsupported new design, general Impact factual errors and an actual refutation of the selected mechanism do not qualify for the carve-out. Apply the existing claim/premise categories or `PROPOSAL_UNSOUND` as appropriate.
- Retain precedence: `NON_VALID` > `EVIDENCE_UNVERIFIED` > `CLAIMS_OUTDATED` > `PROPOSAL_UNSOUND` > `DIRECTIVE_DRIFT` > `VALID`. A higher-priority defect still wins when decision drift coexists; do not force the repair token from raw candidates.

`classify_verify_verdict` already recognizes `DIRECTIVE_DRIFT`; `_verify_class` delegates to it. Their implementation and `next-obligation` tokens remain unchanged. BUG-3763 owns the loop exhaustion guard and existing non-convergence message. For genuine `NON_VALID`, the absence of that drift-specific tag remains correct.

### Decision Rationale

Review on 2026-10-06, including `/ll:advise` with `claude-opus-5-5` (confidence 0.75), selected the existing category plus BUG-3763's narrow remedy. A new verdict would duplicate mapping, persistence and routing machinery for a correction that preserves the chosen mechanism. Opus cautioned that an LLM may still mislabel; validate actual classification with a disposable evaluation rather than promising identical repeat outputs.

## Review Findings

- `commands/verify-issues.md` — B6 and the DIRECTIVE_DRIFT table/persistence clauses all need the same conditional definition. Changing just the table would leave conflicting instructions.
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `classify_verify_verdict` is already the shared classifier; no independent mapping in `next_obligation.py` needs changing.
- `scripts/little_loops/issue_parser.py` — the existing candidate detector excludes Impact and can report shared vocabulary. Raw candidates cannot override verdict precedence.
- The run's verify outputs explicitly named Program Design and Impact in the first two passes. Its later edits removed AC gaps but did not clear the unowned design rewrite.

## Integration Map

### Files to Modify

- `commands/verify-issues.md` — B6 classification, verdict table, complete evidence and check-mode persistence guidance.
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py`, `scripts/tests/test_bug3695_directive_drift_repair.py` — conditional classification and persistence contract pins.
- `scripts/tests/test_ll_issues_check_verify_verdict.py`, `scripts/tests/test_ll_issues_next_obligation.py` — executable compatibility cases using section-named evidence and competing/absent verdicts.
- `docs/reference/COMMANDS.md` — verifier/remedy description if its current wording lists the old section scope.

### Dependent Files (Callers/Importers)

- `commands/reconcile-issue.md` — BUG-3763 owns the eligible Program Design/Impact repair.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — existing token route; exhaustion changes belong to BUG-3763.
- `scripts/little_loops/cli/issues/check_verify_verdict.py`, `scripts/little_loops/cli/issues/next_obligation.py` — unchanged classifier and token consumer.

### Similar Patterns

Existing B6 distinction between a mechanism-preserving directive repair and a refuted proposal; BUG-3695's complete section-named evidence contract.

### Tests

- DIRECTIVE_DRIFT plus Program Design/Impact evidence still yields `VERIFY:DIRECTIVE_DRIFT`; NON_VALID with the same evidence yields `VERIFY:other`; PROPOSAL_UNSOUND and absent verdict preserve their own routes.
- `check-verify-verdict --directive-drift` classifies the verdict alone, including empty evidence; repair eligibility additionally checks evidence and selection. Do not conflate the probe and permission contracts.
- Document-contract cases cover selected/ambiguous/absent selection, Impact-only drift, mixed ordinary/design drift, shared-vocabulary/history false positives and higher-priority defects.
- Disposable model evaluation checks the intended classification and complete evidence for these cases. Deterministic Python tests establish mapping, not the model's semantic decisions.

### Documentation

No enum, token or CLI flag change. Keep verifier command prose aligned with the conditional remedy.

### Configuration

No new setting.

## Program Design

### Types

Existing `verify_verdict: str` retains `DIRECTIVE_DRIFT`. Existing `verify_evidence: str` gains section-named, selection-entailed Program Design/Impact findings; serialization is unchanged.

### Signatures

No new or changed Python signature:

- `classify_verify_verdict(verdict: object) -> str` — existing shared verdict classifier, unchanged.
- `_verify_class(fm: dict[str, Any]) -> str` — existing delegate in next-obligation, unchanged.

### Call Path

`/ll:verify-issues --check --auto` -> escaped verdict/evidence frontmatter -> existing `select_next_obligation` -> `VERIFY:DIRECTIVE_DRIFT` -> BUG-3763's eligible reconcile contract and bounded exhaustion guard.

## Implementation Steps

1. Land BUG-3763's remedy first; then amend all three verifier definition/persistence locations consistently.
2. Add contract cases and executable verdict/token tests; leave classifier and selector code unchanged unless a regression exposes a separate defect.
3. Run the disposable classification evaluation, including higher-priority/ambiguous cases, and record its limits separately from scripted routing results.
4. Update command documentation; run the named focused tests, then `python -m pytest scripts/tests/`.

## Scope Boundaries

This issue owns classification and evidence production. BUG-3763 owns repair/routing; ENH-3765 owns additive protection. No new verdict, deterministic design classifier or broad Impact fact correction is included.

## Impact

- **Severity**: Ambiguous classification changes remedy selection and diagnostic evidence; it compounds the repair gap.
- **Affected**: Verify B6, verdict/evidence persistence and preparation dispatch consumers.

## Acceptance Criteria

- B6, verdict table and persistence guidance consistently define conditional selected-decision Program Design/Impact drift as `DIRECTIVE_DRIFT`, naming the supported remedy and its bounds.
- Evidence identifies every applicable passage and entailed correction, respects precedence, and is replaced atomically with the verdict; check mode makes no body edits.
- Existing probe/token tests cover DIRECTIVE_DRIFT, NON_VALID, PROPOSAL_UNSOUND and absent verdicts without a new enum or route.
- Disposable evaluation covers eligible, ambiguous, Impact-only, mixed and false-positive cases; results do not claim deterministic model behavior. Focused and full local tests pass.

## Related Key Documentation

- `docs/reference/COMMANDS.md` — verify/reconcile command descriptions.
- `docs/guides/LOOPS_REFERENCE.md` — token dispatch and evidence lifecycle.

## Status

**Open** | Created: 2026-10-07 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-10-07T00:52:19 - `8092456a-7bf3-47b0-86f7-42712002052b.jsonl`
- `/ll:capture-issue` - 2026-10-07T00:49:25 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
