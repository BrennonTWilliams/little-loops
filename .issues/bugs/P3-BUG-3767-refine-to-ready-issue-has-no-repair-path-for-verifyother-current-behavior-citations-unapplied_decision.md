---
id: BUG-3767
type: BUG
title: Current Behavior citation corrections have no bounded repair path
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T01:12:47Z'
relates_to:
- BUG-3763
- BUG-3764
- ENH-3765
risk_factors:
- id: preserve-current-behavior-premise
  domain: readiness
  criterion: architecture
  description: Citation edits require direct proof of the unchanged assertion; a
    rewritten premise could otherwise pass the independent check unnoticed.
- id: semantic-edit-quality
  domain: outcome
  criterion: complexity
  description: Prompt-guided correction must distinguish exact citation spans from
    assertions and ambiguous locations; scripted routing tests do not prove this.
- id: shared-verify-command-contract
  domain: outcome
  criterion: change_surface
  description: Correctable scope repeats in classification, persistence, correction,
    final sync and generated host mirrors; all must agree with BUG-3764.
---

# BUG-3767: Current Behavior citation corrections have no bounded repair path

## Summary

Verification sends a stale citation inside Current Behavior to `NON_VALID` even when the original factual assertion remains true and only its source location needs correction. Preparation then chooses additive gap-analysis, which cannot replace the citation. Permit a narrowly evidenced citation-only correction through the existing `CLAIMS_OUTDATED` / `correct_claims` route while preserving BUG-3637's protection against rewriting an issue's premise.

The observed BUG-3762 run failed after 26 iterations. This establishes a failed historical route, not deterministic model classification on byte-identical input. Genuine selected-decision directive drift belongs to BUG-3763/BUG-3764; raw `unapplied_decision` candidates are not independently proven defects.

## Current Behavior

Observed run (transient, gitignored): `.loops/runs/refine-to-ready-issue-20261006T180316/`, with captured output in the corresponding `.loops/.running/` log. Final state `failed`; run-record outcome `deferred`, legacy class `gate_unmet`. <!-- ll-evidence-ok: run artifacts are transient and gitignored -->

1. BUG-3762's Current Behavior used two shorthand source locations that pointed at different statements. The final verifier confirmed the underlying assertions: the capped `CASE` in `_projection` and the missing-value guard in `_plan_column` were present, but the citation locations were stale.
2. Verify at iterations 15 and 23 persisted `NON_VALID`, citing the Current Behavior exclusion in `commands/verify-issues.md` §2C. Its current rule excludes that section regardless of how narrow the change is.
3. `VERIFY:other` enters `check_gate_refine_limit` and `/ll:refine-issue --auto --gap-analysis`. That pass cannot replace stale metadata; it reported no correction. The shared increment-before-command retry counter exhausted, and preparation reached `record_gate_unmet`.
4. Earlier output also questioned decision-related text. The final verifier explicitly treated all four raw `unapplied_decision` candidates as consistent with the selected A+C mechanism and gave them no verdict effect. The decision rejects Option B's page-bound-growth mechanism, not every use of its vocabulary or per-row flag. Those identifiers must not be erased to clear a scanner.
5. B8 reported no blocking citation gaps. The shorthand references have no exact occurrence entries in current `examined_refs`; there is no basis to claim those occurrences received `line_in_range: ok`. In any event, a range pass cannot establish what a line says or whether the cited assertion holds.

## Steps to Reproduce

1. Build a disposable issue with an otherwise-accurate Current Behavior assertion and a citation pointing at the wrong statement. Provide a uniquely identifiable correct source location; do not run against the live BUG-3762 artifact.
2. In a real-child scripted harness, persist the current `NON_VALID` classification for that finding and leave the citation unchanged during gap-analysis.
3. Observe `VERIFY:other` consume the additive retry and terminate at `record_gate_unmet`. Evaluate actual classification/correction separately using disposable model fixtures; the scripted harness establishes routing only.

## Expected Behavior

An otherwise-valid citation-only fixture is classified `CLAIMS_OUTDATED`, repaired once by the existing `correct_claims` state, then independently verified after normalization and verdict/evidence clearing. The assertion remains unchanged. A finding that requires changing behavior, a condition, a causal claim or other premise remains `NON_VALID` and is not automatically rewritten under this exception.

Mixed eligible citation and genuine directive drift can require successive claim and reconcile cycles. A persistent or unprovable citation obligation exhausts the existing single claim-correction attempt and produces `gate_unmet`; no new budget is introduced.

## Root Cause

- **File**: `commands/verify-issues.md`
- **Anchor**: `Correctable scope for CLAIMS_OUTDATED`, `In-place claim correction`, and verdict persistence/final sync clauses.
- **Cause**: The section-wide Current Behavior exclusion intentionally protects premises, but also excludes source-location metadata that can be corrected without changing the assertion. Its `NON_VALID` fallback selects an additive remedy with no authority to replace the citation.

## Motivation

Remove an avoidable manual correction and preparation failure while retaining the existing premise boundary. A broad route from `VERIFY:other` into reconcile would grant rewrite authority to unrelated defects; the existing targeted claim-correction owner is sufficient for this narrower case.

## Proposed Solution

> **Selected:** Narrow original Option B to pure citation-location corrections in Current Behavior, using existing `CLAIMS_OUTDATED` and `correct_claims`. Delegate genuine selected-decision drift to BUG-3763/BUG-3764 and additive protection to ENH-3765.

No new verdict, token, CLI flag, route, counter, Python helper or reconcile permission. Do not route all `VERIFY:other` findings into a rewrite.

### Eligibility and preservation

- Require a uniquely locatable original citation occurrence in Current Behavior and a uniquely supported replacement. Verify directly against the source that the existing assertion remains true verbatim; finding a nearby symbol or an in-range line is insufficient.
- For this initial exception, confine the edit to the numeric line/range suffix of an existing citation in the same source file. Accept an explicit `path:N`/`path:N-M`, or shorthand `:N` only when the same sentence/bullet identifies its source file unambiguously. Do not change its path or asserted symbol, introduce a new anchor, or expand shorthand through a prose rewrite. Exact substring replacement of the authorized numeric span is the edit operation; everything else in Current Behavior remains byte-identical.
- Require a symbol literal or backticked code expression in that sentence/bullet that directly identifies the asserted source, plus its enclosing symbol when needed. The literal must occur verbatim exactly once in that file or named enclosing symbol, be present at the replacement range and absent at the old range. Repeated identical citations require uniquely discriminating local context; otherwise decline. A nearest function name, bare prose pointer, in-range line or literal occurring in several branches cannot establish the exception.
- Do not change asserted symbols, literals, thresholds, conditions, behavior, causation, scope, rationale, code snippets or incident evidence. A symbol used as an asserted subject is not metadata merely because the finding calls it an anchor. Other premise sections retain their existing exclusions; this is not a general factual-rewrite permission.
- Decline the exception when the original occurrence, replacement target or unchanged-assertion proof is ambiguous or unsupported. A location pointing to a different fact, a changed source assertion or an unsupported premise remains `NON_VALID`. Never substitute another true statement to make the issue verify.
- Preserve historical quotations and decision/research provenance. A literal historical citation is not a current-state correction target; if its age is unclear, report uncertainty instead of rewriting history.
- `resolve_anchor` / anchor-sweep are optional mechanical aids only. The resolver scans backward for definitions and clamps out-of-range lines; it neither validates assertions nor distinguishes branches in one function. It cannot establish eligibility or choose the replacement on its own.

### Evidence, classification and correction

Keep the existing escaped, single-line `verify_evidence` format. Each eligible `Current Behavior:` item must identify the original citation occurrence and its unique local assertion/context, the old/new range in the same file, the identifying literal/enclosing symbol and direct support for the unchanged assertion. Use the existing `<section>: <drift> -> <correction>` item grammar; for example `Current Behavior: '<path>:<old>' [context: '<unique local text>'] -> '<path>:<new>' [anchor: '<literal>' in '<symbol>', support: '<unchanged assertion proof>']`. Paraphrase delimiter-containing payload so `; ` appears only between items. No new structured field is needed. Enumerate all eligible findings and replace evidence together with the verdict; source proof is more than literal matching alone.

Apply the existing precedence `NON_VALID` > `EVIDENCE_UNVERIFIED` > `CLAIMS_OUTDATED` > `PROPOSAL_UNSOUND` > `DIRECTIVE_DRIFT` > `VALID`. Any noncorrectable/current-premise or never-auto-correct finding prevents a `CLAIMS_OUTDATED` verdict. An otherwise-correctable citation plus lower-priority directive drift uses `CLAIMS_OUTDATED` first; fresh verification rediscovers remaining drift rather than treating a citation edit as its repair. Raw decision candidates never determine the verdict.

Under `--from-evidence`, the new Current Behavior exception additionally requires current `verify_verdict: CLAIMS_OUTDATED`; re-read the issue and source before each numeric-span replacement. Revalidate the original occurrence, unique literal, old/new ranges and unchanged assertion; stale evidence that no longer uniquely matches or evidence for a different verdict is not authority to edit. Missing/empty evidence remains the existing no-op. Eligible corrections in an ordinary non-check verify run require its own fresh `CLAIMS_OUTDATED` classification and follow the same bounds; no flag is inferred from a field's presence. `--check` remains body-read-only and persists only verdict/evidence under its existing contract.

B8 remains a read-only, property-exact evidence consumer and still "never repairs citations" in that checking step. The explicitly eligible §4 correction is a separate owner. Update §2C, §2.5 persistence, §4 correction, §4.1 final sync, flag documentation and repeated exclusion text consistently so none retains an unconditional Current Behavior ban that contradicts this exception. Preserve `## Context` and every other excluded section's existing scope.

The loop remains `VERIFY:CLAIMS_OUTDATED` -> `check_claim_correction_budget` -> `correct_claims` -> `normalize_structure` -> `clear_verify_verdict` -> independent `verify_issue`. One executed correction per run; recurring citation findings end through the existing exhaustion route. Both classifier and `_verify_class` already support this token, so their implementation remains unchanged.

### Decision Rationale

Review on 2026-10-06 selected the bounded variant of Option B. Original Option A would require a new discriminator and Current Behavior reconcile authority for an existing claim-correction responsibility; original Option C duplicated the decision-drift work already owned by BUG-3763/BUG-3764. The observed final BUG-3762 pass supports source-location correction, not automatic removal of all scanner candidates.

The exception must prove that the original assertion survives unchanged. Independent verification alone cannot guard against a silently rewritten premise, because a newly consistent assertion could pass; preservation and source-support evaluation are therefore explicit acceptance requirements.

`/ll:advise --signal user_requested` with `claude-opus-5-5` supported citation-only Option B at confidence 0.75. This review adopts its exact-substring edit, adjacent unique-literal proof, same-file numeric-span boundary and stale-evidence safeguards; unambiguous shorthand has the same constraints. Opus's dissent favored manual/upstream correction to retain the unconditional premise boundary. A runtime before/after preservation guard is a possible follow-up; this issue accepts model-enforced exact-span editing plus disposable byte-preservation evaluation as a remaining risk, without adding another state or retry.

## Review Findings

- `commands/verify-issues.md` — B8 distinguishes mechanical coverage from content/premise judgment. Its no-repair clause applies to B8, so it need not be removed to permit separately bounded §4 edits.
- `scripts/little_loops/cli/issues/check_verify_verdict.py` and `next_obligation.py` — the shared classifier already handles `CLAIMS_OUTDATED`; no duplicate token mapping or special flag is needed.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — existing claim-correction budget, normalization/recheck chain and exhaustion route provide the owner without topology changes.
- `scripts/little_loops/cli/issues/anchor_sweep.py` — nearest-definition resolution is not assertion proof and can produce an incorrect anchor for an otherwise in-range citation.
- `skills/decide-issue/reference.md` — `unapplied_decision_detail` is candidate evidence; bounded propagation permits residuals, and selected mechanisms can intentionally retain identifiers shared with rejected options.
- The original 85/50 confidence assessment and Large size predate scope selection. Its six active scores, size and VALID verification marker are invalidated by this substantive issue rewrite; fresh confidence/verification must assess the new contract. Current risk factors describe the remaining proof and prompt-consistency risks.

## Integration Map

### Files to Modify

- `commands/verify-issues.md` — narrow Current Behavior exception across classification, complete evidence, persistence, §4/from-evidence edits, final sync and output/flag descriptions; preserve B8's read-only contract.
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — correctable-scope exclusions plus the specific exception, precedence and evidence persistence pins.
- `scripts/tests/test_bug3708_verify_issues_b8.py` — B8 remains read-only/property-exact, shorthand fallback and premise/scope protections.
- `scripts/tests/test_bug3753_historical_verification_notes.py` — historical-note preservation precedent and existing targeted correction lifecycle.
- `scripts/tests/test_bug3695_directive_drift_repair.py`, `scripts/tests/test_builtin_loops.py`, `scripts/tests/test_ll_issues_next_obligation.py` — focused real-child/token compatibility coverage where existing fixtures fit; add a BUG-3767 real-child scenario module if clearer. Existing route/budget/step-cap assertions remain intact.
- `docs/reference/COMMANDS.md`, `docs/guides/LOOPS_REFERENCE.md` — describe the conditional citation correction and existing claim-correction route. Update `docs/reference/CLI.md` only if prose currently repeats the correctable-scope restriction; no CLI enum/flag change.
- `.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md`, `.kimi-code/skills/ll-verify-issues/SKILL.md` — regenerate full command mirrors through `ll-adapt`, not handwritten edits.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — unchanged consumer of `VERIFY:CLAIMS_OUTDATED`; existing single-attempt budget, diagnostic signal and `max_steps: 113` remain.
- `scripts/little_loops/cli/issues/check_verify_verdict.py`, `next_obligation.py`, `clear_verify_verdict.py` — unchanged classifier/delegate and value-agnostic clearing lifecycle.
- `commands/reconcile-issue.md` — retains Current Behavior protection; BUG-3763 owns design/estimate repair.
- `scripts/little_loops/issue_parser.py`, `cli/issues/anchor_sweep.py` — unchanged scanners/mechanical aids; not semantic edit authority.
- `skills/ll-verify-issues/SKILL.md` — minimal Codex command bridge; source-body edits ordinarily require no bridge change. Existing registered-host adapter gate remains authoritative.

### Similar Patterns

BUG-3637's evidence-limited claim correction and independent recheck; BUG-3753's historical verification-note protection; BUG-3708's property-exact citation demotion; BUG-3764's semantic review of raw decision candidates.

### Tests

- Otherwise-valid citation-only fixture: persist `CLAIMS_OUTDATED`, execute one `correct_claims`, normalize, clear old verdict/evidence and independently verify `VALID`; assert no additive retry, decomposition or reconcile. Do not promise the historical BUG-3762 artifact qualifies without testing its unique-literal conditions. Scripted command effects test routing only.
- Persistent/unprovable correction: one executed correction followed by existing `record_gate_unmet`, closed `gate_unmet` class and no added counter or reset. Count executions separately from the increment-before-command counter value.
- Mixed fixtures: eligible citation plus true directive drift uses claim correction, fresh `DIRECTIVE_DRIFT`, then BUG-3763's reconcile; a true premise defect dominates as `NON_VALID`. Intentional A+C floor/shared-vocabulary candidates cause no semantic decision-drift finding. Do not require one cycle for mixed defects.
- Contract fixtures cover ordinary non-check correction, `--check`, `--from-evidence`, absent/empty/stale/wrong-verdict evidence, repeated identical citations, ambiguous occurrences/targets, unexamined shorthand with/without a scoped file, bare prose pointers, literals at the old range or multiple locations, in-range wrong-content references and different branches under the same function. Path/symbol changes are refused under this initial exception.
- Disposable model evaluation verifies actual surgical edits: original Current Behavior bytes are identical except authorized citation spans, historical/provenance blocks survive, every corrected assertion remains directly supported, and ambiguous/changed assertions are refused. Record these results separately from pytest and scripted routing.
- Preserve all other premise exclusions, Context protection, B8 no-repair/property-exact demotion, full precedence and the existing route/token/step-cap tests. Run `scripts/tests/test_wiring_skills_and_commands.py` after mirror regeneration.

### Documentation

Align verify command and loop-guide prose with the narrow exception and sequential mixed-finding behavior. No general `VERIFY:other` repair promise.

### Configuration

No new setting, frontmatter schema, host call or enum. Disposable evaluation artifacts stay under an isolated run directory.

## Program Design

### Types

Existing `verify_verdict: str` uses `CLAIMS_OUTDATED`; escaped single-line `verify_evidence: str` carries exact occurrence, replacement location and unchanged-assertion support. Raw `unapplied_decision_detail` remains a candidate list requiring semantic review.

### Signatures

No Python signature change:

- `classify_verify_verdict(verdict: object) -> str` — existing shared classifier already handles `CLAIMS_OUTDATED`.
- `_verify_class(fm: dict[str, Any]) -> str` — existing selector delegate, unchanged.

`resolve_anchor` is not an eligibility discriminator.

### Call Path

`select_next_obligation` -> `_verify_class` -> `classify_verify_verdict` supplies the existing `VERIFY:CLAIMS_OUTDATED` token from current verdict/evidence. The loop then uses `check_claim_correction_budget` -> `/ll:verify-issues --auto --from-evidence` -> normalization -> clear verdict/evidence -> fresh independent verification. Exhaustion uses existing `record_gate_unmet`.

## Implementation Steps

1. Add the citation-only exception and proof/preservation rules consistently across the verify command's repeated scope, persistence, correction and final-sync clauses. Retain B8 and all other premise exclusions.
2. Add focused contract and real-child routing/exhaustion cases without changing classifier, token, counter, route table or step cap. Coordinate mixed-finding fixtures with BUG-3764 after its repair dependency lands.
3. Run disposable edit-quality evaluation for uniquely supported anchors, branch ambiguity, changed assertions, repeated citations, stale evidence and historical preservation. Record actual edits/refusals separately from scripted outcomes.
4. Update documentation and regenerate affected registered-host mirrors via `ll-adapt --host <host> --apply`; check codex, gemini, kimi-code, qwen and omp where tracked artifacts exist.
5. Run the named focused suites, the mirror gate, `ll-loop validate refine-to-ready-issue`, then `python -m pytest scripts/tests/`.

## Scope Boundaries

This issue owns only the bounded Current Behavior citation exception and its existing claim-correction lifecycle. BUG-3763/BUG-3764 own genuine selected-decision design/estimate drift, and ENH-3765 owns additive protection. No blanket raw-candidate repair, new verdict/token, general premise rewrite, widened reconcile scope or independent retry is included. Citation-only behavior can land independently; joint evaluation runs after the related decision-drift fixes.

## Impact

- **Priority**: P3 — preparation can fail on correction-only source metadata; manual correction is available and no data loss is established.
- **Effort**: Medium — prompt contract, focused fixtures, docs and generated mirrors; reuses existing route/budget.
- **Risk**: Medium — an overbroad exception could hide a changed premise, so unchanged assertion/source proof and byte-preservation evaluation are required.
- **Breaking Change**: No new CLI or verdict contract.

## Acceptance Criteria

- Uniquely supported, otherwise-valid Current Behavior citation-only findings persist `CLAIMS_OUTDATED` and use the existing one-attempt correction/recheck chain, without an additive retry or new route/token/counter.
- Only authorized citation-number/range spans change through exact substring replacement. Paths, asserted symbols, assertions, conditions, causal claims, snippets and historical/provenance material stay unchanged; ambiguous/missing/nonunique literal support, stale/wrong-verdict evidence and changed/unproven assertions confer no edit authority.
- All verifier scope/persistence/correction/sync clauses agree with the exception while B8 remains read-only and all other premise exclusions remain. Genuine premise defects persist `NON_VALID`.
- Persistent citation findings follow existing budget exhaustion; mixed citation/directive findings preserve precedence and successive fresh verification. Raw selected-mechanism/history candidates do not force rewrite or scanner clearance.
- Contract, scripted child-loop and disposable model evaluations cover the distinct guarantees above; generated mirrors, loop validation, focused and full local tests pass.

## Related Key Documentation

- `docs/reference/COMMANDS.md` — verifier correction behavior.
- `docs/guides/LOOPS_REFERENCE.md` — claim-correction routing and one-attempt budget.
- `docs/reference/CLI.md` — current verdict/token and citation evidence contracts.

## Status

**Open** | Created: 2026-10-07 | Priority: P3

## Confidence Check Notes

Historical assessment by `/ll:confidence-check` on 2026-10-06, before the scope choice: readiness 85/100 and outcome confidence 50/100. These are historical results, not scores for the revised proposal; the active score keys and stale verification marker were removed. Reassess after review.

### Resolved Concerns

- [resolved 2026-10-06 by issue review] Original concern: Options A/B/C had no Selected decision, leaving discriminator, route and candidate handling open. Resolution: select bounded citation-only Option B, reuse existing CLAIMS_OUTDATED/correct_claims, and assign genuine decision drift to BUG-3763/BUG-3764.
- [resolved 2026-10-06 by issue review] Original concern: Option B conflicts with B8's "never repairs citations" and the BUG-3637 premise guard. Resolution: B8 remains read-only; §4 owns an explicit citation-span exception requiring direct proof of the unchanged assertion and preserving all premise prose.
- [resolved 2026-10-06 by issue review] Original concern: existing DIRECTIVE_DRIFT/reconcile and CLAIMS_OUTDATED/correct_claims paths overlap. Resolution: the revised issue introduces neither path nor token and leaves Current Behavior protected under reconcile.

### Remaining Outcome Risks

Prompt-guided assertion proof and surgical edits still need disposable model evaluation. The command repeats its correction scope in several places and generated mirrors; stale copies could reintroduce conflicting instructions. Original risk notes about an unresolved option, 16-site token/topology change and four changed step-cap pins no longer describe the selected scope.

## Session Log
- `/ll:ready-issue` - 2026-10-07T01:51:25 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
- `/ll:confidence-check` - 2026-10-07T01:31:37 - `e18126dd-317b-417c-86ac-4401ea214536.jsonl`
- `/ll:verify-issues` - 2026-10-07T01:29:30 - `b059f0e8-765a-45cb-b2ac-1828f56d58b5.jsonl`
- `/ll:wire-issue` - 2026-10-07T01:27:14 - `ce6bd152-644a-4781-8ad3-92fcd1e54a6a.jsonl`
- `/ll:refine-issue` - 2026-10-07T01:17:50 - `67f77c85-f910-4236-837b-e92f1170426b.jsonl`
- `/ll:format-issue` - 2026-10-07T01:16:48 - `7610b26f-db95-4e3a-b048-687107034721.jsonl`
- `/ll:capture-issue` - 2026-10-07T01:12:58 - `26bbdec0-accc-4f17-94d6-3d59f60b2e3f.jsonl`
