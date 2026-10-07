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
- BUG-3767
blocked_by:
- BUG-3763
confidence_score: 100
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
risk_factors:
- id: consumer-dependents-surface
  domain: outcome
  criterion: change_surface
  description: Loop guard, reconcile-issue, selector tests and four host mirrors depend
    on the changed contract
- id: semantic-evaluation-unexecuted
  domain: outcome
  criterion: ambiguity
  description: The fixed disposable fixtures and expected verdicts are enumerated;
    actual label, complete evidence and body-preservation outcomes remain unmeasured
- id: failclosed-guard-edit
  domain: outcome
  criterion: complexity
  description: Editing the live check_residual_decision_drift guard can silently change
    routing if boundary rules are wrong
- id: llm-classification-pytest-gap
  domain: outcome
  criterion: test_coverage
  description: Semantic Program Design/Impact classification is model-driven; pytest
    covers only routing, not the new labels
- id: multi-site-contract-sync
  domain: outcome
  criterion: complexity
  description: B6 prose, verdict table, check-mode persistence, 4.1 post-fix sync,
    docs and three generated mirrors must stay consistent
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

**Widen the existing `DIRECTIVE_DRIFT` definition conditionally; do not add a verdict or obligation.** BUG-3763's eligible repair and exhaustion guard landed in commit `daeada0c9` during this review. The structured dependency is satisfied. This issue also aligns that guard's evidence-boundary validation with the producer contract below; no route or retry-budget change is included.

- Update B6, the verdict table, check-mode persistence and normal-mode post-fix sync together. Ordinary directive drift keeps its existing definition. Add an explicit selected-decision propagation sub-check: inspect current Program Design directives and Impact Effort/Risk against the governing selection, even when those passages have no Integration Map entry or scanner candidate. Do not make this incidental to AC coverage.
- Preserve B6's existing precondition: absent, `TBD` or boilerplate Proposed Solution skips B6, including this sub-check. A selection/rationale recorded elsewhere alone does not activate it. Report an unassessed check honestly; the skip is not proof of design alignment and does not originate `DIRECTIVE_DRIFT`. Any independently established clarification/premise defect still uses the existing categories.
- The additional category requires an unambiguous recorded selected option and Decision Rationale for the decision governing the passage, a mechanism that still stands, and a correction restricted to named Program Design directive passages or decision-derived Impact Effort/Risk lines. Another decision group's winner is insufficient. Use canonical `Program Design:` or `Impact:` evidence-item prefixes (not composite headings), in the existing `<section>: <drift> -> <correction>` item format, and identify the specific current passages plus the correction entailed by that selection; do not turn a section heading into blanket rewrite authority.
- Collect all applicable findings in one pass, including ordinary AC/Step/Integration Map drift and decision-derived design/estimate drift. Persist the complete escaped, single-line `verify_evidence` with `DIRECTIVE_DRIFT` in the same frontmatter update, replacing earlier evidence. `--check` remains frontmatter-only.
- Keep the canonical prefixes, `; ` item delimiter and ` -> ` drift/correction separator aligned with BUG-3763's consumer. Normalize payloads before YAML escaping: paraphrase embedded delimiter/separator sequences and quoted pseudo-item prefixes so each item has exactly one structural ` -> ` and `; ` appears only between items. Quotes, ordinary apostrophes/contractions and backslashes are legal payload text; YAML escaping and item-boundary validation are separate contracts. Pin their roundtrip through the real frontmatter parser and actual guard, rather than an invented parser or quote-count rule.
- Consumer validation is syntactic, not an inference about quotation intent. Validate the entire split list before accepting a canonical match or ordinary-only fallback: malformed reserved section items, empty sides, extra structural arrows and observable split fragments fail diagnostically. Legal punctuation does not. A payload delimiter that produces two complete valid-looking items is indistinguishable from a genuine boundary in this format; producer normalization prevents that case, and the guard cannot certify its origin. A syntactically complete canonical item supplies only the existing bounded exhaustion signal; reconciliation still revalidates the governing decision and named passage before any edit.
- Treat `unapplied_decision_detail` as candidate evidence requiring contextual review. The scanner needs recognizable option blocks and discriminating rejected identifiers, scans Program Design but not Impact, and can return no candidates for real prose-only design drift. Inspect both Program Design and Impact semantically; absence of candidates is not a pass. Preserve historical option comparisons and research blocks; a shared-vocabulary candidate alone is insufficient.
- Absent or ambiguous selection, an unsupported new design, general Impact factual errors and an actual refutation of the selected mechanism do not qualify for the carve-out. Apply the existing claim/premise categories or `PROPOSAL_UNSOUND` as appropriate.
- Retain precedence: `NON_VALID` > `EVIDENCE_UNVERIFIED` > `CLAIMS_OUTDATED` > `PROPOSAL_UNSOUND` > `DIRECTIVE_DRIFT` > `VALID`. A higher-priority defect still wins when decision drift coexists; do not force the repair token from raw candidates.
- Use BUG-3767's landed pure Current Behavior citation exception: an eligible citation correction wins as `CLAIMS_OUTDATED`; after that repair, fresh verification can expose remaining `DIRECTIVE_DRIFT`. A genuine Current Behavior premise change remains `NON_VALID` and wins over both. Mixed findings can require successive claims and reconcile cycles; do not promise one repair for every mixed issue or suppress remaining findings.

### Post-fix verdict/evidence ownership

- Every fresh full `--check` publishes a coherent current verdict/evidence pair, including when the winning category changes. `DIRECTIVE_DRIFT`, `CLAIMS_OUTDATED` and `PROPOSAL_UNSOUND` replace prior evidence with their own complete current work list; `VALID`, `NON_VALID` and `EVIDENCE_UNVERIFIED` have no evidence-field contract here and remove stale `verify_evidence`. Seed old design evidence in each competing-category fixture to pin this cleanup. Verdict-driven probes/selectors stay unchanged; raw old evidence never overrides the winner.
- In a normal full-sweep non-check run, retain claims-only correction authority: verification reports Program Design/Impact drift and leaves its repair to flagged reconciliation. When §4.1 synchronizes an already-present verdict after claim corrections, apply precedence to all remaining findings. If the residual is `DIRECTIVE_DRIFT`, revalidate the complete B6 work list against the post-fix issue and replace evidence in the same update; never leave citation-only evidence attached to the new verdict. If a complete current residual assessment cannot be substantiated, remove both fields and require fresh `--check` rather than publishing an unsupported category. Other evidence-bearing residual categories retain their own current work lists; a category without an evidence contract removes stale evidence. When the result is `VALID`, remove stale `verify_evidence`. Keep the existing rule that non-check mode does not insert `verify_verdict` when it was absent.
- A targeted `--from-evidence` pass skips B6 and cannot discover or certify a new design-drift category or whole-issue `VALID`. Recheck/correct only its existing eligible claim work list. When it applies claim corrections or confirms that all listed claims are already resolved, remove the existing verdict/evidence pair and report verification pending; the following fresh full `--check` owns the new category. Missing/empty evidence and refused/no-op passes with unresolved claims retain their existing no-edit behavior and report the concern. The caller must run fresh `--check` before dispatching or scoring; the existing loop already normalizes, clears and verifies. Do not infer `DIRECTIVE_DRIFT` from old evidence or add a B6 sweep/body-rewrite permission to this flag.
- Under `--check`, preserve every body byte, including protected history and Session Log. Existing non-check Verification Notes/Session Log behavior remains unchanged.
- When both `--check` and `--from-evidence` are supplied, the existing check-mode precedence remains: run the full sweep, publish its current pair, and preserve the body. A targeted pass that edits some eligible claims but cannot resolve another still clears the pair and reports both the unresolved concern and pending full verification; a refused pass that makes no correction and has unresolved claims retains the existing pair.

`classify_verify_verdict` already recognizes `DIRECTIVE_DRIFT`; `_verify_class` delegates to it. Their implementation and `next-obligation` tokens remain unchanged. BUG-3763 supplies the existing loop exhaustion guard and non-convergence message; this issue changes only its evidence-boundary validation for producer compatibility. For genuine `NON_VALID`, the absence of that drift-specific tag remains correct.

### Decision Rationale

Review on 2026-10-06, including `/ll:advise` with `claude-opus-5-5` (confidence 0.75), selected the existing category plus BUG-3763's narrow remedy. A new verdict would duplicate mapping, persistence and routing machinery for a correction that preserves the chosen mechanism. Opus cautioned that an LLM may still mislabel; validate actual classification with a disposable evaluation rather than promising identical repeat outputs.

A further `/ll:advise --signal user_requested --host claude-code --model opus` review on 2026-10-06 (confidence 0.74) supported the explicit semantic check, retained B6 precondition and paired post-fix persistence. Its critique tightened targeted mode to pending fresh verification and required malformed design-prefixed evidence to fail diagnostically; the matching BUG-3763 contract is updated with this review, and the remaining landed-guard boundary corrections are assigned here. Opus suggested tolerating one positive miss in three evaluation trials. This issue instead requires all predefined trials to pass as a bounded smoke gate: an inconsistent core label is precisely the defect being repaired. Passing still establishes no production error rate or determinism guarantee. A closed five-prefix consumer grammar was not adopted because the existing guard must preserve ordinary evidence compatibility; this change reserves structural delimiters and aligns only the existing boundary checks.

## Review Findings

- `commands/verify-issues.md` — B6, the DIRECTIVE_DRIFT table/persistence clauses and §4.1 post-fix sync need the same conditional definition. B6 currently skips incomplete proposals and otherwise names only consequence/AC checks; the new semantic propagation check needs its own explicit scope.
- §4.1 currently changes an existing verdict after corrections without refreshing evidence. A mixed citation/design full-sweep pass can leave `DIRECTIVE_DRIFT` with the prior citation work list; targeted `--from-evidence` cannot certify residual B6 findings because it skips that sweep.
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `classify_verify_verdict` is already the shared classifier; no independent mapping in `next_obligation.py` needs changing.
- Review validation on 2026-10-06: the focused verdict-probe and next-obligation suites passed (78 tests); both issue format checks are clean. The live classification/mixed-mode evaluation remains implementation acceptance work, not a completed result of this review.
- `scripts/little_loops/issue_parser.py` — the existing candidate detector excludes Impact and can report shared vocabulary. Raw candidates cannot override verdict precedence.
- The historical run's captured verify outputs at iterations 15/21/30 were re-read on inspected branch `main` during this review. The first two named Program Design and Impact; later edits removed AC gaps but did not clear the unowned design rewrite. This corroborates the classification-contract gap without establishing fixed-input nondeterminism.
- A disposable probe of BUG-3763's in-progress guard found three boundary mismatches: a grammatical apostrophe in an Impact item returned diagnostic exit 2; a single no-arrow Program Design item returned 2 while the issue still specified no-match 1; a quoted delimiter inside an AC-only item returned 1 instead of an ambiguity diagnostic. This review aligns the malformed canonical-item contract to diagnostic failure; grammatical punctuation remains legal and actual delimiter ambiguity must be checked before concluding ordinary fallback. BUG-3763 has since landed with those boundary defects still present. The minimal guard corrections and boundary tests now belong here: remove apostrophe parity as an ambiguity rule, diagnose malformed canonical items (including empty sides), and assess actual delimiter ambiguity before a no-prefix fallback. A matching prefix is a routing signal, not semantic edit permission.
- Additional review on 2026-10-06 found that full check-mode winner changes also leave stale evidence unless cleanup is explicit; valid-looking embedded item boundaries cannot be diagnosed from this string format alone. The fixed fixture tables below replace the previously unspecified evaluation matrix. BUG-3763, ENH-3765 and BUG-3767 are now done; retain their landed ownership and the satisfied dependency. The current focused baseline passed 674 tests across the redaction/CLI/ingest/remote/docs and verifier/repair/probe/selector suites. This is baseline evidence, not a result for the proposed classifier or expanded redaction path. Recorded confidence scores are retained without a new assessment.

## Integration Map

### Files to Modify

- `commands/verify-issues.md` — explicit B6 propagation check/precondition, verdict table, complete evidence, check-mode persistence and §4.1 post-fix verdict/evidence synchronization; preserve §4's claims-only edit authority.
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py`, `scripts/tests/test_bug3695_directive_drift_repair.py` — conditional classification, precondition, semantic no-candidate checking and normal/targeted/check persistence contract pins.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — align only existing `check_residual_decision_drift` evidence-boundary checks/comments with legal punctuation, malformed canonical items and actual ambiguity before fallback; preserve every state edge, counter and budget.
- `scripts/tests/test_bug3763_decision_drift_repair.py` — extend the landed actual-guard harness for producer serialization/boundary compatibility, including the observed regressions.
- `scripts/tests/test_ll_issues_check_verify_verdict.py`, `scripts/tests/test_ll_issues_next_obligation.py` — executable compatibility cases using section-named evidence and competing/absent verdicts.
- `docs/reference/COMMANDS.md` — describe the conditional verifier/remedy scope and frontmatter-only exception to `--check`; retain the already-landed bounded citation correction description.
- `.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md`, `.kimi-code/skills/ll-verify-issues/SKILL.md` — generated command mirrors; regenerate through `ll-adapt`, not handwritten patches.
- `scripts/tests/test_wiring_skills_and_commands.py` — existing registered-host mirror gate; source-body edits ordinarily need no change to the minimal Codex bridge `skills/ll-verify-issues/SKILL.md`.

### Dependent Files (Callers/Importers)

- `commands/reconcile-issue.md` — BUG-3763 owns the eligible Program Design/Impact repair.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — existing token route and exhaustion behavior supplied by BUG-3763; no route changes.
- `scripts/little_loops/cli/issues/check_verify_verdict.py`, `scripts/little_loops/cli/issues/next_obligation.py` — unchanged classifier and token consumer.

### Similar Patterns

Existing B6 distinction between a mechanism-preserving directive repair and a refuted proposal; BUG-3695's complete section-named evidence contract.

### Tests

- Use identical Program Design/Impact evidence with `DIRECTIVE_DRIFT`, `NON_VALID`, `PROPOSAL_UNSOUND`, `CLAIMS_OUTDATED`, `EVIDENCE_UNVERIFIED`, `VALID` and absent/null verdicts: probe/selector behavior follows only the verdict, with no new enum or route. Keep the existing empty-evidence drift-probe case; repair eligibility additionally checks evidence and selection.
- Contract cases cover selected/ambiguous/absent selection, incomplete-proposal B6 skip, Impact-only drift, natural-language Program Design drift with no scanner candidates or Integration Map entry, mixed ordinary/design drift, shared-vocabulary/history false positives and higher-priority defects. Every full-check category transition replaces or removes old evidence according to the winning category's contract; seed stale design evidence to make cleanup observable.
- Pin §4.1 full-sweep claim-correction to residual-drift sync, resolved-to-VALID evidence cleanup, absent-verdict non-insertion and targeted `--from-evidence` scope. Targeted correction/already-resolved completion removes the pair and reports pending full verification; refusal/unresolved no-op and missing evidence preserve their existing no-edit behavior. Fresh full `--check` owns new B6 classification/dispatch; no normal verifier mode rewrites Program Design/Impact.
- Roundtrip colons, double quotes, grammatical apostrophes and backslashes through YAML and the actual BUG-3763 guard. Normalized payloads and complete mixed items pass; canonical prefixes solely inside another item's tail do not match. Malformed reserved Program Design/Impact items (including section-only/no-arrow/empty sides), extra structural arrows and observable split fragments fail diagnostically, even if another item is valid or there is no canonical match. Absent/non-string/empty evidence or a syntactically complete ordinary-only list retains no-match. Validate all items before deciding; a valid first item cannot hide a malformed later item. Punctuation alone is not ambiguity. Pin wrong verdict and probe/path/read errors as well. Producer normalization and contextual edit revalidation cover the valid-looking faux-boundary case the grammar cannot diagnose.
- Joint BUG-3767 fixture: eligible citation plus decision drift first emits `CLAIMS_OUTDATED`, then fresh verification exposes `DIRECTIVE_DRIFT`; adding a true premise defect keeps `NON_VALID`. Include multiple decision groups and intentional selected-mechanism/shared-vocabulary candidates so no raw candidate is treated as rejected-option proof.

### Disposable classification evaluation

Use a synthetic disposable project with known source truth and fixtures whose expected winning verdict, required evidence items and protected body are recorded **before** running the model. Exercise the real `/ll:verify-issues --check --auto` command, parse its persisted fields, and pass eligible produced evidence through BUG-3763's actual guard. Do not inject scripted verdicts and call that semantic validation. Keep fixtures, outputs and a concise result report under an isolated `postmortems/` evaluation directory; record inspected prompt commit/diff, the actual command source/mirror and prompt hash used, host/model, invocation and fixture hashes.

Use these fixed fixtures; all unmentioned claims and directives are valid. `guard` is the actual residual-decision guard's exit code after parsing the produced frontmatter: 0 means a complete canonical design/Impact item, 1 means ordinary no-match. Any diagnostic exit on eligible produced evidence fails the evaluation. Missing selection alone is not a defect: the negative fixtures explicitly contain unresolved or contradictory active alternatives requiring clarification.

| Fixture | Expected persisted winner | Required evidence / guard | Trials |
|---------|---------------------------|---------------------------|--------|
| F01: recorded Option B and rationale; two current Program Design passages still mandate rejected migration | `DIRECTIVE_DRIFT` | Both named passages and entailed corrections; guard 0 | 3 |
| F02: same governing selection; only Impact Effort and Risk price the rejected migration | `DIRECTIVE_DRIFT` | Both stale estimate lines; guard 0 | 3 |
| F03: design, Impact, AC and fixture-step residuals together | `DIRECTIVE_DRIFT` | Complete combined list; guard 0 | 1 |
| F04: prose-only rejected design with no scanner candidate or Integration Map entry | `DIRECTIVE_DRIFT` | Specific design passage; guard 0 | 1 |
| F05: ordinary AC-only gap, concrete sound proposal, no recorded option decision | `DIRECTIVE_DRIFT` | Ordinary AC evidence only; guard 1 | 1 |
| F06: conflicting active A/B selections and rationale requiring clarification | `NON_VALID` (`NEEDS_UPDATE`) | No design repair evidence; guard 1 | 3 |
| F07: missing governing selection with explicitly unresolved Proposed Solution alternatives | `NON_VALID` (`NEEDS_UPDATE`) | No design repair evidence; guard 1 | 1 |
| F08: only another decision group has a winner; governing alternatives remain unresolved | `NON_VALID` (`NEEDS_UPDATE`) | No borrowed selection authority; guard 1 | 1 |
| F09: intentional selected-mechanism identifiers and historical rejected-option comparisons | `VALID` | No evidence field; guard 1 | 1 |
| F10: absent/TBD/boilerplate proposal, selection elsewhere, every assessed claim true | `VALID`, B6 reported unassessed | No B6 evidence; guard 1; exercise each skip form | 1 per form |
| F11: current-state claims true but selected mechanism demonstrably contradicted by code | `PROPOSAL_UNSOUND` | Replace old evidence with the actual proposal consequence; guard 1 | 1 |
| F12: general Impact factual error outside decision-derived Effort/Risk | `NON_VALID` | No conditional carve-out or evidence field; guard 1 | 1 |
| F13: true Current Behavior premise defect plus design drift | `NON_VALID` | Higher-priority premise defect wins; no evidence field; guard 1 | 1 |
| F14: provably nonexistent attributed quote plus design drift, no higher-priority claim defect | `EVIDENCE_UNVERIFIED` | Confirm B7 finds the controlled fabrication; no stale evidence field; guard 1 | 1 |
| F15: eligible Current Behavior citation plus design drift | `CLAIMS_OUTDATED` | Complete eligible citation work list first; guard 1 | 1 |

Seed stale design evidence in F09 and F11–F14. In every fixture, compare the complete body and Session Log bytes before/after check. Pre-record the specific required passage set for positive fixtures so a correct category with an omitted finding still fails.

Run each boundary case once; repeat the eligible design-only, Impact-only and ambiguous-selection cases on three fresh identical copies total per case. Never feed a prior run's verdict/evidence back into the next copy. Check expected precedence and complete evidence, exact body/Session Log preservation and guard outcome. Report every trial and failure rather than retrying until a favorable answer appears. An observed false repair classification, omitted eligible passage, conflicting persistence pair or body edit fails acceptance; correct the prompt/contract and rerun the fixed matrix. Passing this bounded smoke evaluation supports the change, not a determinism or production error-rate claim. Deterministic pytest covers contract/routing compatibility separately.

Also exercise real mixed-mode sequences on separate copies of the citation-plus-design fixture, starting with a real check's persisted `CLAIMS_OUTDATED` state: full-sweep `--auto` corrects the citation, preserves design text and synchronizes to complete residual `DIRECTIVE_DRIFT`; targeted `--from-evidence --auto` corrects only the listed claims, removes the verdict/evidence pair, and a following full check exposes remaining `DIRECTIVE_DRIFT`. Include an already-resolved targeted list, unresolved refusal, absent initial verdict and a post-fix residual assessment that cannot be substantiated. These sequences validate §4.1 behavior that check-only runs cannot exercise.

| Sequence | Required outcome |
|----------|------------------|
| M01: F15 then full normal `--auto` | Only eligible claim changes; design preserved; current residual `DIRECTIVE_DRIFT` plus complete design evidence |
| M02: F15 then targeted correction then fresh full check | Only listed claim changes; pair removed and verification pending; fresh check emits `DIRECTIVE_DRIFT` |
| M03: targeted list already fully resolved | Pair removed, verification pending; no claim/body rewrite beyond existing non-check logging |
| M04: targeted pass corrects one claim but another remains unresolved | Pair removed after correction; unresolved concern reported; fresh full check required |
| M05: targeted refusal/no correction with unresolved claims, or missing/empty evidence | Existing no-edit/pair-preservation behavior and concern/no-op report |
| M06: full normal correction with no initial verdict | No verdict insertion; no orphan evidence creation |
| M07: post-fix complete residual assessment cannot be substantiated | Pair removed; fresh full check required |
| M08: both check and targeted flags | Full check wins; current category/evidence and byte-identical body/Session Log |

### Documentation

No enum, token or CLI flag change. Keep verifier command prose aligned with the conditional remedy.

### Configuration

No new setting.

## Program Design

### Types

Existing `verify_verdict: str` retains `DIRECTIVE_DRIFT`. Existing `verify_evidence: str` gains section-named, selection-entailed Program Design/Impact findings; serialization is unchanged. Normalize item-boundary payloads before YAML escaping; synchronize the evidence with the winning current/residual verdict, and remove it when §4.1 resolves to `VALID`.

### Signatures

No new or changed Python signature:

- `classify_verify_verdict(verdict: object) -> str` — existing shared verdict classifier, unchanged.
- `_verify_class(fm: dict[str, Any]) -> str` — existing delegate in next-obligation, unchanged.

### Call Path

`/ll:verify-issues --check --auto` -> escaped verdict/evidence frontmatter -> existing `select_next_obligation` -> `VERIFY:DIRECTIVE_DRIFT` -> BUG-3763's eligible reconcile contract and bounded exhaustion guard.

## Implementation Steps

1. Use BUG-3763's landed remedy; align the guard's boundary checks without changing routes/counters, add the explicit B6 propagation sub-check with the retained proposal precondition, and align the table, full-check evidence cleanup, persistence and post-fix sync clauses. Validate the whole evidence list before a canonical match/fallback without claiming to infer hidden quotation intent.
2. Add contract cases, executable verdict/token tests and real-guard serialization compatibility cases; leave classifier and selector code unchanged unless a regression exposes a separate defect.
3. Run the fixed disposable classification matrix and fresh-copy repeats above, including higher-priority/ambiguous and mixed-mode cases; report every outcome and its limits separately from scripted routing results.
4. Update command documentation and regenerate affected registered-host mirrors with `ll-adapt --host <host> --apply`; check codex, gemini, kimi-code, qwen and omp where tracked artifacts exist. Run the named focused tests, `scripts/tests/test_wiring_skills_and_commands.py` and `ll-loop validate refine-to-ready-issue`, then `python -m pytest scripts/tests/`.

## Scope Boundaries

This issue owns classification, evidence production/synchronization and the minimal matching boundary corrections in the existing consumer guard. BUG-3763 supplies repair/routing; ENH-3765 owns additive protection. No consumer state edge, retry counter, budget or edit-eligibility expansion belongs here. No new verdict, deterministic design classifier or broad Impact fact correction is included.

## Impact

- **Severity**: Ambiguous classification changes remedy selection and diagnostic evidence; it compounds the repair gap.
- **Affected**: Verify B6, verdict/evidence persistence and preparation dispatch consumers.
- **Priority**: P3 — an explicit contract gap in issue preparation, with the repair capability supplied by BUG-3763.
- **Effort**: Small/Medium — verifier prose, minimal existing-guard boundary corrections, contract/compatibility tests, documentation/mirrors and a bounded live smoke evaluation; existing Python verdict machinery is reused.
- **Risk**: Medium — semantic classification is model-driven, and evidence serialization must agree with a fail-closed consumer. Mapping tests alone cannot prove the new labels or passage coverage.

## Acceptance Criteria

- B6, verdict table, persistence and post-fix sync consistently define conditional selected-decision Program Design/Impact drift as `DIRECTIVE_DRIFT`, naming the supported remedy and bounds. Concrete proposals receive a semantic propagation check even without scanner candidates or Integration Map coverage; incomplete proposals retain the existing B6 skip.
- Evidence identifies every applicable passage and entailed correction, respects precedence and is replaced with the winning verdict. Every fresh full check removes stale evidence for categories without an evidence contract. Full-sweep post-fix sync cannot leave old claim evidence with residual drift; resolved-to-VALID sync clears it. Targeted mode reports pending full verification after corrections/already-resolved work, including partial correction, removes its stale pair and cannot originate B6 findings or whole-issue `VALID`. Refused unresolved no-op passes keep their existing behavior. Check mode wins over the targeted flag and preserves the entire body/Session Log; ordinary verification does not repair design/estimate drift itself.
- Probe/token cases and YAML/actual-guard roundtrips pass across the complete verdict and punctuation/boundary matrix, without a new enum, route or quote-count restriction. The entire list is validated before match/fallback; syntactically valid-looking boundaries grant no semantic edit authority, and producer normalization owns hidden payload delimiters.
- The fixed disposable evaluation matrix and fresh-copy repeats pass the predefined verdict/evidence/body/guard checks, with every trial recorded and no determinism claim. Focused and full local tests pass.
- Mixed citation/design/premise fixtures preserve shared precedence and successive fresh-verification remedies; governing decision groups and intentional historical/selected identifiers are handled correctly. Generated mirrors pass the registered-host gate.

## Related Key Documentation

- `docs/reference/COMMANDS.md` — verify/reconcile command descriptions.
- `docs/guides/LOOPS_REFERENCE.md` — token dispatch and evidence lifecycle.

## Status

**Open** | Created: 2026-10-07 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-10-07T03:02:33 - `a01917d3-707e-49be-b1b2-6bcd8c610f5e.jsonl`
- `/ll:ready-issue` - 2026-10-07T01:51:25 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
- `/ll:format-issue` - 2026-10-07T00:52:19 - `8092456a-7bf3-47b0-86f7-42712002052b.jsonl`
- `/ll:capture-issue` - 2026-10-07T00:49:25 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
