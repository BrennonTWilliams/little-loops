---
id: BUG-3763
type: BUG
title: refine-to-ready-issue has no rung to rewrite Program Design after a decision
  flips the design
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T00:49:18Z'
verify_verdict: VALID
relates_to:
- BUG-3764
- ENH-3765
- BUG-3767
blocks:
- BUG-3764
confidence_score: 95
outcome_confidence: 64
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
risk_factors:
- id: conditional-contract-and-guard-depth
  domain: outcome
  criterion: complexity_depth
  description: Conditional scope change across every reconcile process clause plus
    a new shell guard with explicit frontmatter shape and delimiter validation.
- id: extends-existing-reconcile-contract
  domain: readiness
  criterion: duplicate_implementations
  description: Extends the existing --from-verify-evidence reconcile contract rather
    than adding a new component; must not duplicate or widen ordinary reconcile scope.
- id: model-edit-quality-unproven-by-pytest
  domain: outcome
  criterion: test_coverage
  description: Scripted child-loop tests prove routing only; actual Program Design/Impact
    edit quality depends on an opt-in model evaluation outside pytest.
- id: shared-reconcile-callers-must-keep-scope
  domain: outcome
  criterion: change_surface
  description: prepare-issue, reconcile_revision and unflagged callers share the reconcile
    command and must retain the ordinary scope.
- id: tuning-details-left-open
  domain: outcome
  criterion: ambiguity
  description: max_steps 113 is provisional and ambiguous-delimiter evidence handling
    is specified in prose with edge cases still to settle at implementation.
- id: wide-contract-and-mirror-sweep
  domain: outcome
  criterion: complexity_breadth
  description: 'About 9 change sites: command, bridge skill, loop YAML, three test
    files, two docs, plus regenerated host mirrors.'
---

# BUG-3763: refine-to-ready-issue has no rung to rewrite Program Design after a decision flips the design

## Summary

The existing `DIRECTIVE_DRIFT` remedy cannot rewrite Program Design or decision-derived Impact estimates. When a recorded selection differs from those passages, reconciliation declines them and additive refinement leaves the rejected design intact. Extend the existing evidence-gated reconciliation contract narrowly, and stop sending persistent decision-derived design drift to additive refinement after its one repair attempt.

Observed on BUG-3761 in `.loops/.history/2026-10-07T000313-refine-to-ready-issue`: 33 iterations, 38m11s, terminal `failed`, run record `deferred`. The verify passes also found AC gaps, so the trace does not establish that every other gate was clean.

## Current Behavior

1. `resolve_decision_mid_refine` selected Option B: predicates on existing columns, without a migration. Program Design and Impact Effort/Risk still described Option A: a channel column and migration. Decide's Phase 7c flagged residuals under its bounded propagation contract.
2. Verify at iteration 15 returned `DIRECTIVE_DRIFT`, naming Program Design/Impact and an AC gap. `reconcile_issue` at iteration 18 repaired ACs but refused Program Design/Impact as outside its contract.
3. Verify at iteration 21 again returned `DIRECTIVE_DRIFT`. With reconciliation spent, the loop entered `check_gate_refine_limit` and `refine_followup`. That pass added useful AC/research findings and Option B restatements, but could not remove Option A directives.
4. Verify at iteration 30 returned `NON_VALID` because Program Design was outside the documented remedy scope. `VERIFY:other` reached the exhausted shared retry counter and `record_gate_unmet` at iteration 33.

## Steps to Reproduce

1. Create a disposable fixture with two options, a canonical selected-option callout and Decision Rationale selecting Option B, and Program Design directives describing Option A. Include stale Impact Effort/Risk and preserved research/decision history. The current BUG-3761 file has since been manually repaired.
2. Use the real child-loop harness with scripted slash-command effects: persist `DIRECTIVE_DRIFT` plus evidence naming Program Design and Impact; let reconciliation leave those passages unchanged; persist drift again.
3. Observe reconciliation exhaust and fall through to additive refinement. A separate disposable live evaluation is needed to reproduce and assess actual model edits.

## Expected Behavior

One eligible reconcile pass repairs all named decision-derived passages together with the ordinary directive gaps. It re-enters normalization and fresh verification. If the repair lacks adequate source detail or drift persists after that attempt, fail with explicit non-convergence evidence before spending the additive retry budget.

## Motivation

Provide a repair owner for selected-decision propagation without broadening ordinary reconciliation into a general design rewrite. The observed failed run cost 38m11s; its six-minute additive retry could not discharge the rewrite obligation.

## Proposed Solution

**Selected approach: conditional extension of the existing `--from-verify-evidence` contract, plus a residual decision-drift guard after reconciliation exhaustion.** No new flag, verdict, Python entry point, or retry counter.

### Repair eligibility and bounds

- Retain the existing eligibility conjunction: explicit `--from-verify-evidence`, `verify_verdict: DIRECTIVE_DRIFT`, and nonempty current `verify_evidence`.
- Additionally require an unambiguous recorded selected option and Decision Rationale for the decision governing the evidenced passage, a selected mechanism that still stands, and evidence naming the specific Program Design passages or Impact Effort/Risk lines that describe the rejected option. Another decision group's selection, conflicting selections or a section name alone do not authorize a rewrite.
- Rewrite those named directive passages in place from the recorded selection and its rationale. Existing recorded findings may substantiate the selected mechanism, but cannot introduce a new design or override the selection. If these sources are insufficient, preserve the passage and report the concern.
- Impact eligibility is limited to decision-derived Effort/Risk text. Severity, affected populations, factual incident history and unrelated estimates remain protected. Preserve accurate Program Design directives, decision records, human rationale, research/provenance blocks and every unrelated section; do not replace the whole H2 around protected material.
- Ordinary reconciliation, unflagged callers and evidence for other verdicts retain their existing scope. A selected mechanism refuted by code belongs to `PROPOSAL_UNSOUND`, not this carve-out.
- Re-read the current issue before editing: each evidence item must still identify the same passage and a correction entailed by the governing selection. Stale, ambiguous or already-resolved evidence does not authorize a new edit; report unresolved items without inventing a replacement. No timestamp field or new evidence schema is needed.
- Extend the entire command process consistently: source extraction, evidence-target roles, stale/no-op detection, bounded rewrite, check-mode plateau detection and `SECTIONS_REWRITTEN` reporting. A design/estimate propagation target is distinct from an AC, fixture or context-only target; the old role table must not silently discard it.
- A substantive design-only or Impact-only edit follows the existing resolved-Concern and six-score-clearing lifecycle even when no old directive section changes. Move only concerns actually resolved. `--check` is read-only, including frontmatter, guards and Session Log; no-op, refusal and marker-only passes do not clear scores. Reconcile does not self-grade or clear `verify_verdict`/`verify_evidence`; normalization and the loop's verdict-clearing state precede fresh verification.

### Exhaustion routing

Insert a shell state named `check_residual_decision_drift` on `check_reconcile_limit.on_no`, before `check_gate_refine_limit`; leave `.on_error` unchanged. It matches only when `ll-issues check-verify-verdict <ID> --directive-drift` succeeds and the current artifact's `verify_evidence` is a nonempty string containing a complete `Program Design:` or `Impact:` item in the existing `; `-separated contract. A qualifying item starts with that exact canonical prefix and contains nonempty drift and correction text (`<section>: <drift> -> <correction>`). A section named only in another item's correction tail is not a match. Resolve the target with `ll-issues path`, read frontmatter through the existing parser, and validate the value's type and item shape explicitly; never stringify a list or mapping. The parser is permissive, so successful parsing alone does not establish valid evidence. Do not inspect free-form model stdout or route from raw format-check candidates. Use the existing shell-exit convention:

- Exit 0 (match): go directly to `record_gate_unmet`, preserving the existing `GATE_UNMET:DIRECTIVE_DRIFT_NON_CONVERGENCE` tag and `directive_drift_nonconvergence` evidence reference.
- Exit 1 (ordinary no-match, absent/non-string/malformed item or unsupported prefix): retain the existing fallback to `check_gate_refine_limit`.
- Exit 2+ (probe/path/read failure or ambiguous item boundaries): go directly to `record_gate_unmet` with retained stderr and a diagnostic under the run directory. Include the capture in terminal reporting and diagnostic prompts/backstop evidence; this route bypasses `diagnose`, so capture alone is insufficient. Do not spend an additive retry when protection cannot be assessed, or claim a failed probe positively established decision drift.

Keep producer and consumer item prefixes/delimiters identical and pin them together. BUG-3764 must paraphrase payload text containing the literal item delimiter `; ` rather than embed quoted pseudo-items; ambiguous legacy delimiter-containing evidence must fail with a diagnostic, not be certified as a clean no-match. A malformed/non-string evidence value without an ambiguous item boundary remains the ordinary no-match case above.

Update `record_gate_unmet`'s human text and comments: this new early exit exhausts the applicable reconcile budget while the additive counter can still be zero. Describe unresolved design/estimate drift, an incomplete repair or insufficient eligible sources; do not claim the shared refine budget was spent or limit the explanation to AC/Step edits. Stable tags and the closed `gate_unmet` class remain unchanged.

One reconciliation per run remains the bound. If a prior ineligible AC-route reconcile spent it before design drift was discovered, fail explicitly rather than resetting the counter or silently granting another repair. This is a known bounded limitation; VERIFY normally precedes ACCEPTANCE_CRITERIA. Ordinary AC/Step/Integration Map drift without named design/estimate evidence retains its additive fallback. The observed gap pass added useful ACs, so bypassing every DIRECTIVE_DRIFT case would remove a valid recovery path. Budget checks still increment on entry: distinguish counter value 2 from two executed repairs.

### Decision Rationale

Review on 2026-10-06 selected this narrow variant of original Option A. Full refinement would expand edits and research unnecessarily; widening decide's Phase 7c would defeat its candidate-versus-edit and bounded-analysis protections. A separate rewrite rung remains a follow-up only if live evaluation demonstrates missed classification or a real need for an independent budget.

`/ll:advise` with `claude-opus-5-5` recommended this approach at confidence 0.75. Its dissent favored a post-decision rewrite rung if verifier classification proves unreliable. Its principal limitations are thin selected-option descriptions and an already-spent reconcile budget; both must end as explicit unmet obligations, not invented designs. The review narrows Opus's suggested all-DIRECTIVE_DRIFT exhaustion guard to section-named design/estimate drift: the trace itself shows that additive refinement can still repair missing ACs.

## Review Findings

- `commands/reconcile-issue.md` — Contract and source-extension clauses currently exclude Program Design/Impact. Its existing selected-rationale source and substantive-edit cleanup provide the relevant precedent.
- `scripts/little_loops/issue_parser.py` — `_DECISION_DIRECTIVE_SECTIONS` includes Program Design but excludes Impact. `unapplied_decision_detail` is a candidate list, not an edit list; shared-vocabulary false positives are documented in `skills/decide-issue/reference.md`.
- A disposable parser probe reported a Program Design candidate, no Impact-only candidate, and the same Program Design candidate after appending a selected-option restatement. Do not require every raw candidate to disappear or delete legitimate history just to clear the scanner.
- `scripts/little_loops/cli/issues/next_obligation.py` — DESIGN checks missing/empty/nonspecific design, not decision propagation. `_verify_class` already delegates to the shared verdict classifier.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — reconciliation exhaustion currently enters the shared increment-before-command retry counter. A refusal after `refine_followup` starts cannot refund it.
- `commands/reconcile-issue.md` — the process and output repeat the old section scope; its score-cleanup trigger currently says only "rewrote at least one directive section", which would miss an Impact-only edit without an explicit update.
- The guard is a routing backstop, not semantic proof or edit permission. Multiple decision groups and the permissive frontmatter parser require the separate eligibility and evidence-shape checks above.
- A second Opus review on 2026-10-06 supported the narrow combined plan at confidence 0.75 and identified the probe-error additive fallback as a remaining contradictory-write path. This review changes that guard error route to diagnostic `gate_unmet` without requiring ENH-3765 to land first; ordinary AC-only no-match fallback remains intact.

## Integration Map

### Files to Modify

- `commands/reconcile-issue.md` — conditional scope across Contract and every Process/output clause, evidence-target role table, preservation, in-place edits, check-mode and design-only/Impact-only score lifecycle.
- `skills/ll-reconcile-issue/SKILL.md` — bridge description and argument documentation; the command remains the contract source.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — exhaustion guard, terminal human text, route comments, persisted/captured diagnostic context and state-budget explanation. Keep `max_steps: 113` provisionally and exercise a longest legitimate harness path; increase only if the added valid path requires it.
- `scripts/tests/test_reconcile_issue_command.py`, `scripts/tests/test_builtin_loops.py`, `scripts/tests/test_bug3695_directive_drift_repair.py` — contract pins and existing-route expectations; preserve the ordinary AC-only fall-through assertions.
- `docs/reference/COMMANDS.md`, `docs/guides/LOOPS_REFERENCE.md` — conditional scope and exhaustion behavior.
- Existing generated host mirrors of changed command/skill metadata — regenerate with the registered adapters and run `scripts/tests/test_wiring_skills_and_commands.py`; do not hand-edit generated bodies.

### Dependent Files (Callers/Importers)

- `commands/verify-issues.md` — the widened evidence producer is owned by BUG-3764 and lands after this repair contract.
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — existing `--directive-drift` probe, unchanged.
- `scripts/little_loops/frontmatter.py` — existing `parse_frontmatter` reader for the shell guard, unchanged.
- `scripts/little_loops/cli/issues/next_obligation.py`, `scripts/little_loops/cli/issues/run_record.py` — unchanged token mapping and closed terminal-class contract.
- `scripts/little_loops/loops/prepare-issue.yaml`, `scripts/little_loops/loops/refine-to-ready-issue.yaml` — unflagged reconcile callers, shared AC route and `reconcile_revision` must retain their scope.

### Similar Patterns

- BUG-3695's evidence-gated AC/Step repair and its real child-loop harness in `scripts/tests/test_bug3695_directive_drift_repair.py`.
- Reconciliation's conditional Scope Boundaries carve-out and substantive score clearing.

### Tests

- Successful scripted repair: one flagged reconcile, normalize, clear old verdict/evidence, fresh VALID verdict, fresh scores and `done`; assert additive retry count remains zero.
- Persistent section-named design/estimate drift: one reconcile, exhaustion guard, `record_gate_unmet`, closed `gate_unmet` class and existing non-convergence evidence; no `refine_followup`, no decomposition.
- Earlier ineligible AC-route reconcile, then discovered design drift: explicit exhaustion without an extra repair or counter reset.
- Ordinary AC-only DIRECTIVE_DRIFT, empty/non-string/malformed-item evidence, VALID plus AC-route exhaustion, NON_VALID/`VERIFY:other` and missing verdict retain their documented fallback behavior. Probe/path/read errors and ambiguous item boundaries terminate with a diagnostic instead of additive retry; preserve `check_reconcile_limit.on_error` unchanged.
- Contract fixtures for no flag, another verdict, empty evidence, absent/ambiguous selection, insufficient winner detail, `--check`, no-op scores and provenance preservation.
- Guard cases for non-string evidence, section-only items, canonical prefixes mentioned only in a correction tail, quoted delimiter/pseudo-item ambiguity, valid mixed items and 2+ probe/path/read failures with persisted diagnostics. Pin producer/consumer prefixes together. Check governing versus unrelated/conflicting decision groups and stale/currently resolved evidence separately.
- Program Design-only and Impact-only repairs each clear all six scores and move only resolved concerns; refusal/no-op/marker-only and check-mode passes preserve scores. Check-mode reports an eligible design-only/Impact-only plateau without edits.
- Opt-in model evaluation on disposable copies verifies actual Program Design/Impact edits and protected-byte preservation. Scripted effects establish routing, not model compliance or convergence.

### Documentation

Update command and loop references. No CLI enum/flag change is intended; update `docs/reference/CLI.md` only where it describes exhaustion behavior.

### Configuration

No new setting. Counters and any evaluation artifacts remain isolated under the run directory.

## Program Design

### Types

Existing `verify_verdict: str`, escaped single-line `verify_evidence: str`, and the selected-option/rationale text supply eligibility. The exhaustion guard also checks the canonical section names in current evidence; an empty or unparseable value is not a positive match. `FormatGaps.unapplied_decision_detail: list[dict[str, str]]` remains advisory candidate evidence for semantic review; it is not unconditional edit authority.

### Signatures

No new Python signature. The existing interfaces are:

- `classify_verify_verdict(verdict: object) -> str` — unchanged shared classifier backing the shell probe.
- `parse_frontmatter(content: str, *, coerce_types: bool = False) -> dict[str, Any]` — existing parser used to read current section-named evidence.
- `ll-issues check-verify-verdict <ID> --directive-drift` — existing query used by the new shell guard.
- `/ll:reconcile-issue <ID> --from-verify-evidence` — existing invocation with the conditional contract extension above.

The only new executable loop component is the shell guard described above.

### Call Path

`VERIFY:DIRECTIVE_DRIFT` -> `check_reconcile_limit` -> eligible `reconcile_issue` -> `normalize_structure` -> `clear_verify_verdict` -> `verify_issue`.

On exhaustion: `check_reconcile_limit` -> `check_residual_decision_drift` -> `record_gate_unmet` for persisted section-named design/estimate drift, otherwise the existing additive-budget fallback.

## Implementation Steps

1. Extend only the evidence-gated reconcile contract, all matching process/output clauses and bridge metadata, with the bounds above. Keep ordinary scope, current evidence entailment rules and read-only mode intact.
2. Add the shell exhaustion guard, corrected terminal prose and persisted/captured diagnostics; preserve per-run counter isolation and closed run-record classes.
3. Add real-child harness tests and contract pins; retain prior BUG-3695 AC-only additive fallback cases and add the section-named decision-drift matrix.
4. Add the disposable opt-in model evaluation for actual edit quality, false-positive/history preservation, Impact-only evidence and insufficient source detail. Record its result separately from pytest.
5. Update command/loop documentation and regenerate affected host mirrors via `ll-adapt --host <host> --apply`; include codex, gemini, kimi-code, qwen and omp where tracked artifacts exist. Run the focused tests, mirror gate, `ll-loop validate refine-to-ready-issue`, and finally `python -m pytest scripts/tests/`. Classification changes belong to BUG-3764; command-level additive protection belongs to ENH-3765.

## Scope Boundaries

This issue owns reconcile repair capability and loop exhaustion routing. BUG-3764 owns verifier classification; ENH-3765 owns additive command protection. It does not broaden decide's rewrite contract, introduce a general full rewrite, change decision-detection semantics or add retry capacity.

## Impact

- **Severity**: A selected-decision propagation gap can fail preparation after a long run; the observed run lasted 38m11s.
- **Affected**: Evidence-gated reconciliation and persistent decision-derived design-drift exhaustion. Normal AC-route and unflagged reconciliation protections remain required.

## Acceptance Criteria

- The contract permits one eligible pass to rewrite all specifically evidenced rejected-option Program Design directives and Impact Effort/Risk lines from the recorded selection, with no new mechanism or lost provenance. Disposable model evaluation verifies the edit behavior.
- Real-child scripted tests reach `done` after successful repair and fresh verification/scoring, with one reconcile and no additive retry.
- Persistent section-named design/estimate drift, including an already-spent reconcile budget, reaches `record_gate_unmet` with the existing non-convergence evidence and no additive pass or decomposition.
- Missing eligibility and check/no-op modes preserve their documented scope and mutation rules. Raw false-positive candidates do not authorize edits or forced scanner clearance.
- Independent design-only/Impact-only edits clear stale scores; stale evidence and unrelated/ambiguous decision groups confer no rewrite authority. The guard distinguishes complete canonical items, non-matches and diagnostic failures; early-exit prose correctly names the spent repair budget.
- Existing higher/absent verdict paths, non-drift exhaustion and guard-error behavior pass the regression matrix; focused and full local tests and loop validation pass.

## Related Key Documentation

- `docs/guides/LOOPS_REFERENCE.md` — claim-verification dispatch and bounded repair routing.
- `docs/reference/COMMANDS.md` — reconcile command contract.
- `docs/reference/CLI.md` — verdict query and typed run records.

## Status

**Open** | Created: 2026-10-07 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-07_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Outcome Risk Factors
- Broad enumeration across about 9 change sites (command, bridge skill, loop YAML, three test files, two docs, regenerated host mirrors).
- Deep per-site complexity: a conditional scope change across every reconcile process clause plus a new shell guard with explicit shape and delimiter validation.
- Scripted child-loop tests prove routing only; the quality of actual Program Design/Impact edits rests on an opt-in model evaluation outside pytest.
- The `max_steps: 113` budget is provisional and ambiguous-delimiter handling still has edge cases to settle during implementation.
- The reconcile command is shared with prepare-issue, `reconcile_revision` and unflagged callers, which must keep the ordinary scope.

### Risk Factor Delta
- Baseline: none recorded

## Session Log
- `/ll:confidence-check` - 2026-10-07T01:59:32 - `46b6f9fa-ff1d-4adc-917b-97222f85316f.jsonl`
- `/ll:verify-issues` - 2026-10-07T01:56:29 - `07f0fbdf-7493-4e19-9704-1bfc9798a017.jsonl`
- `/ll:ready-issue` - 2026-10-07T01:51:25 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
- `/ll:format-issue` - 2026-10-07T00:52:19 - `8092456a-7bf3-47b0-86f7-42712002052b.jsonl`
- `/ll:capture-issue` - 2026-10-07T00:49:25 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
