---
id: BUG-3726
type: BUG
title: reconcile-issue --from-verify-evidence adds ACs for context-only inventory
  evidence
priority: P3
status: done
program_design_not_applicable: true
discovered_by: ll-issues-create
discovered_date: '2026-10-04'
captured_at: '2026-10-04T01:57:03Z'
completed_at: '2026-10-04T17:49:18Z'
parent: EPIC-3694
learning_tests_required: []
relates_to:
- ENH-3718
- BUG-3695
confidence_score: 90
outcome_confidence: 72
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3726: reconcile-issue --from-verify-evidence adds ACs for context-only inventory evidence

## Summary

Found by ENH-3718's live evaluation: when `/ll:reconcile-issue --from-verify-evidence` is handed `DIRECTIVE_DRIFT` evidence whose items point at context-only Tests/Documentation inventory entries, a real model (claude-sonnet-5-5) turns each entry into an Acceptance Criterion. `commands/reconcile-issue.md` ("Source extension — `--from-verify-evidence`") says context-only inventory items create no requirement and each added item must be entailed by the selected mechanism.

## Current Behavior

Two independent direct calls (D3, D4) on an issue whose Proposed Solution is a docstring-only change, with `verify_verdict: DIRECTIVE_DRIFT` and `verify_evidence` reading `Acceptance Criteria: 'no AC covers the Integration Map Tests and Documentation entries (tests/test_core.py::test_count_words, tests/test_cli.py::test_count_prints_total, README.md)' -> add an AC for each listed Tests and Documentation entry`, each added three ACs of the form "`tests/test_core.py::test_count_words` passes with no edits to the test file" and "`README.md` is unchanged". Both are requirements derived from an inventory listing, and both D3 and D4 did it. The same command correctly added a Step (no AC) for fixture-invalidation evidence (D1, D2) and changed nothing for a `VALID` verdict with stale evidence (N1, N2).

## Expected Behavior

An evidence target that is a context-only entry (an unchanged caller, test or documentation inventory with no behavior or contract consequence) creates no requirement. Reconcile reports the refused target under `## CONCERNS` in its output. Other targets in the same evidence item can still justify an AC or Step. Existing criteria, including legitimate preservation/compatibility criteria, are not removed merely because their wording includes "unchanged".

If neither accepted evidence nor ordinary findings justify a repair, reconcile leaves the directives unchanged and returns `RECONCILED` with `## CORRECTIONS_MADE: None`. The normal guard/session-log writes and existing superseded-marker cleanup still apply. Refusing evidence must not skip a repair justified by the issue's own findings.

## Proposed Solution

Tighten the `--from-verify-evidence` text in `commands/reconcile-issue.md` so each named target is classified by the same roles B6 uses (observable behavior or contract, required fixture update, context-only) before any addition, and a context-only target is refused with a `## CONCERNS` line. Keep the eligibility conjunction (explicit flag, `DIRECTIVE_DRIFT`, nonempty evidence), existing rewrite/preservation rights, and `check_reconcile_limit` (`target: 2`) unchanged.

The rule already exists in one sentence (`commands/reconcile-issue.md`, "Context-only inventory items create no requirement") and failed to prevent additions in both trials. The evidence's own `-> add an AC for each listed … entry` tail asks for the observed additions; treating that tail as authoritative is a plausible cause, not an attribution established by an ablation. Test explicit precedence and process-level triage rather than assuming a restatement alone will work:

1. **State precedence.** The evidence's `-> <correction>` tail is verify's proposal, not an instruction. Classify each named *target* from the selected mechanism and the issue's recorded findings (per target, not per item or subsection); the classification wins over the tail. A tail cannot upgrade a context-only target into a coverage obligation. Retain the tail as a proposed correction for applicable targets, subject to entailment.
2. **Name the anti-pattern narrowly.** An inventory listing alone does not entail "file X is unchanged" / "test passes with no edits" ACs. An explicit behavior/compatibility requirement in the selected mechanism can entail a preservation criterion; do not reject it on wording alone. "For each listed entry" triggers scrutiny, not automatic rejection of every target. Triage filters the evidence source; it does not authorize deleting existing ACs or Steps.
3. **Live in the Process, not only the Contract.** Add triage between Step 3 and Step 4. Only accepted, uncovered targets participate in evidence-based stale-section detection. Always continue ordinary contradiction detection in Steps 4/4a; all-refused evidence alone is not an early-return condition. A no-op requires no accepted uncovered target, no ordinary stale directive, and no contradicted Scope Boundaries claim. Preserve marker cleanup, guard/session-log writes, and Step 5b's rule that no-op passes leave scores and confidence notes untouched.
4. **Apply the same triage in `--check`.** Include it in Step 7's read-only sequence: context-only evidence with no other drift yields `CLEAN` / exit 1, while an entailed uncovered target or ordinary contradiction yields `NEEDED` / exit 0. No guard write, rewrite, score clearing, marker removal, or session-log append occurs in check mode.
5. **Update the `## CONCERNS` output template** (it currently covers only "directive bullet with no supporting finding") with `- [refused-evidence] <evidence item / section>: <target> — context-only — <reason from selected mechanism>`. Report one line per refused target, including on a normal no-op pass; list only actual repairs under `## CORRECTIONS_MADE`. This is command output, not a new issue-body section.
6. **Cross-reference B6 for role definitions**, without copying its table. Retain the local executable mapping already in the Contract: behavior/API/compatibility consequence → AC, fixture/mock invalidation → Step, context-only → refusal. Reconcile must work when loaded independently and must not re-research project code to classify targets.

If the candidate fails any required live case, keep the issue open, record the failure and reassess the prompt. Do not silently widen this fix into a structured-evidence protocol or discard correction tails globally: fixture repairs can depend on their concrete correction content. A broader evidence-boundary redesign needs a separately scoped follow-up.

Notes (from Opus second opinion, 2026-10-04):
- Mirror gates may trip on a command edit; run `ll-adapt --host <gemini|kimi-code|qwen> --apply` if so.
- Follow-up, not in scope: `DIRECTIVE_DRIFT_NON_CONVERGENCE` (`refine-to-ready-issue.yaml`) says "repair incomplete" and could misattribute a deliberate refusal if B6 later emits a false positive repeatedly. No such upstream failure was reproduced: B6 returned `VALID` in ENH-3718; this bug concerns reconcile's treatment of injected evidence.
- Review with `/ll:advise` and Opus on 2026-10-04 (confidence 0.80): correct P1, narrow the unchanged-AC rule, prevent all-refused short-circuiting, preserve check-mode parity, and make the live replay portable. The advisor's stdout-parsing concern does not require a loop change: `reconcile_issue` proceeds directly to `normalize_structure`; `check_reconcile_limit` evaluates its own shell counter, not reconcile's concerns output.

## Integration Map

### Files to Modify
- `commands/reconcile-issue.md` — Contract precedence, process triage, no-op/check-mode consistency, and refusal-output template.
- `scripts/tests/test_bug3695_directive_drift_repair.py` — extend the existing section-scoped prompt contract checks; assertions must cover Contract, triage before stale detection, check-mode inclusion, and the output template rather than matching unrelated prose anywhere in the command.
- `postmortems/` — new private BUG-3726 trial scaffolding/results, using the ENH-3718 assets as input: rebuild the launcher with a caller-supplied scratch root or `mktemp -d`, candidate snapshot, and section-aware oracle. Preserve the historical snapshots. Do not commit historical transcripts or absolute scratch paths. Minimal sanitized toy fixtures may be tracked outside the issue-corpus fixture directories if useful; they are not a prerequisite for the prompt fix.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — flagged `reconcile_issue` consumer; preserve `target: 2`, action routing and `max_steps: 113`.
- `scripts/little_loops/loops/prepare-issue.yaml` — ordinary unflagged reconcile consumer; its findings-based repair behavior must remain available.

### Similar Patterns
- `commands/verify-issues.md` — check B6's role-based classification and shared-coverage rule; no upstream behavior change required.
- `scripts/tests/test_reconcile_issue_command.py` — section-scoped contract, preservation, guard, no-op and check-mode assertions.

### Tests
- Existing reconciliation and BUG-3695 suites plus the new prompt assertions; live cases and their oracles below supply behavior evidence. Substring tests alone do not establish model compliance.

### Documentation
- No separate documentation change required unless the implementation changes the existing command contract beyond the refusal clarification.

## Implementation Steps

1. Add target-over-tail precedence and triage to the command, keep ordinary findings-based repair active, update check-mode coverage and refusal output, and add section-scoped contract assertions.
2. Rebuild the throwaway-project launcher from the ENH-3718 assets with portable scratch paths. Pin the live model to `claude-sonnet-5-5` for comparison, record the host version, and disable the shared cached plugin in the throwaway project. Load an immutable plugin snapshot containing the candidate command, including uncommitted candidate edits if necessary; record the base SHA and candidate command hash. Historical `d960240d4` is the reproduction baseline, not the candidate under test. Abort the batch if transcript/source-hash preflight cannot prove the candidate was loaded; never modify the shared plugin cache.
3. Freeze complete pristine input files and hashes for D3, D1/D2, N1/N2, P1, P2, M1 and R1. Run five independent D3 trials and each control once in fresh sessions/projects, restoring all issue bytes (including evidence, scores and guards) before each trial. Run the two check-mode controls separately. Keep trial fixtures outside this checkout's active `.issues/` and issue-corpus fixture directories.
4. Compare ACs, Steps, Integration Map, protected body sections and frontmatter against the pristine snapshots with the case-specific allowed changes below; inspect stdout for verdict, actual corrections and per-target refusals. Record all trials, command/model hashes, before/after snapshots and stdout under a new private postmortems run directory. Five D3 passes are a smoke test with no observed failures, not a reliability estimate.
5. Regenerate affected host mirrors if their gates require it. Run the focused reconciliation suites and the authoritative local suite (`python -m pytest scripts/tests/`) before implementation closure; keep retry limits and loop routing unchanged.

## Acceptance Criteria

- [x] Section-scoped deterministic checks enforce target-over-tail precedence, the inventory-only anti-pattern (with legitimate compatibility/preservation coverage permitted), triage before stale detection, continued ordinary repair, triage in `--check`, and `[refused-evidence]` under the output `## CONCERNS` template. Existing flag eligibility, fixture→Step mapping and preservation checks pass.
- [x] Five live direct calls on a pristine copy of `postmortems/ENH-3718-live-eval-20261003/fixtures/D3.ENH-8803.md` pass (zero tolerance, 5/5) with the candidate command proven loaded. ACs, Steps, the entire Integration Map and protected body are byte-identical, including the existing "tests still pass unchanged" AC; frontmatter is unchanged except `reconcile_attempted: true` and the only body addition is Session Log. Stdout returns `RECONCILED`, `## CORRECTIONS_MADE` is `None`, and `## CONCERNS` has exactly three `[refused-evidence]` lines naming the two test targets and README target with their context-only reasons. A silent no-op fails. Use section/frontmatter-aware comparisons, not `analyze.py`'s whole-file `bodychg` as the no-op oracle.
- [x] Regression controls D1/D2 each add the entailed fixture-update Step without an AC or Integration Map addition; N1/N2 (VALID plus stale evidence) preserve ACs/Steps/Integration Map and protected body, with only normal guard/log writes. On every normal trial `verify_verdict` and `verify_evidence` remain unchanged; no-op trials preserve any existing six score fields and confidence notes.
- [x] P1 is N1 with exactly the opt-out AC removed, `verify_verdict: DIRECTIVE_DRIFT`, and evidence restricted to the uncovered `skip_stopwords=False` contract. One matching AC is added, verifying `top_words("the cat the dog", 1, skip_stopwords=False)` returns `[("the", 2)]`; existing ACs remain unchanged and no context-only refusal is reported. This tests preservation of the old ranking as an explicit compatibility contract.
- [x] P2 is unmodified N1 with `verify_verdict: DIRECTIVE_DRIFT` and its stale evidence retained. Already-covered targets add no duplicate AC/Step, produce no `[refused-evidence]` line, and return a no-op with only guard/log writes. Covered applicable evidence is distinct from refused context-only evidence.
- [x] M1 starts with one missing CLI-output AC and one context-only inventory entry. A **single** evidence item names both targets and proposes an AC "for each listed entry". The real consequence is stated in a Tests or Documentation entry, so subsection name cannot determine its role. Reconcile adds only the entailed CLI-output AC, reports exactly one `[refused-evidence]` line for the context-only target, and preserves all other directives/Integration Map entries. Separate-item classification alone does not satisfy this control.
- [x] R1 combines D3's context-only evidence with an existing Implementation Step contradicted by a recorded Codebase Research Finding. Reconcile refuses the three inventory targets but still rewrites the stale Step from that finding; it does not add an AC or short-circuit into a no-op. Normal rewrite score-clearing rules still apply.
- [x] Check-mode controls run with `--check --from-verify-evidence`: D3 returns `CLEAN` / exit 1; P1 returns `NEEDED` / exit 0. Full issue-file hashes remain unchanged in both, including guard, scores, markers and Session Log. The check-mode sequence includes triage and ordinary contradiction detection.
- [x] All required live cases are recorded with the resolved model, pristine fixture hashes, candidate command hash and before/after/stdout evidence; no required trial is discarded solely because it failed. The local test suite passes, and retry limits/routing remain unchanged.

## Impact

- **Priority**: P3 - exposure needs a B6 false positive first, and the added ACs are no-op "unchanged" assertions
- **Effort**: Medium (command text + focused contract assertions + portable replay setup and positive/mixed/ordinary-repair/check-mode controls; historical shim is reusable after removing its stale scratch-path assumptions)
- **Risk**: Low (main risk is over-correction or suppressing ordinary repair, covered by P1/P2/M1/R1 and check-mode controls)

## Steps to Reproduce

The evidence is synthetic: a real B6 pass returned `VALID` on this fixture, so the end-to-end loop does not reach reconcile on it. This is a reconcile-side robustness gap against a B6 false positive, not an observed loop failure. Fixtures, the shim and per-trial before/after snapshots are in `postmortems/ENH-3718-live-eval-20261003/` (`postmortems/ENH-3718-live-eval-20261003/fixtures/D3.ENH-8803.md`, and the `logs/D3`, `logs/D4` directories beside it).

1. Build a throwaway project with `D3.ENH-8803.md` committed under `.issues/enhancements/`.
2. Run `/ll:reconcile-issue ENH-8803 --from-verify-evidence` with the snapshot of commit `d960240d4`.
3. Diff the issue file: three new ACs, none entailed by the docstring-only mechanism.

## Labels

`reconcile-issue`, `directive-drift`, `epic-3694`

## Resolution

- **Action**: fix
- **Completed**: 2026-10-04
- **Status**: Completed

### Changes Made
- `commands/reconcile-issue.md`: Contract now states target classification wins over the evidence `-> correction` tail, names the narrow inventory-only anti-pattern (preservation ACs still allowed), new Step 3b triages each evidence target (role decided first; refused / covered / accepted-uncovered), Step 4 stale detection and no-op use only accepted uncovered targets (all-refused is not an early return), Step 7 `--check` includes triage, and the `## CONCERNS` template gains `[refused-evidence]`.
- `scripts/tests/test_bug3695_directive_drift_repair.py`: `TestBug3726ContextOnlyTriage` section-scoped contract assertions.
- `postmortems/BUG-3726-live-eval-20261004/` (private): portable launcher, candidate snapshot shim, section-aware oracle, fixtures P1/P2/M1/R1, results and `RESULTS.md`.

### Verification
- Live (claude-sonnet-5-5, candidate proven loaded via transcript marker): 15/15 required trials pass the oracle — D3 x5, D1 x2, N1 x2, P1, P2, M1, R1, check-clean-D3, check-needed-P1. Five D3 passes are a smoke test, not a reliability estimate.
- Recorded non-clean events: first candidate text refused only README (tests folded into a "covered" note) → added "decide the role first" to Step 3b; oracle strictness bugs and a harness flag-splitting defect (check trials) were fixed and rerun, invalid runs kept.
- Focused suites 57 passed. Full suite: 27848 passed; failures unrelated to this change — `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` (BUG-3696 file quote vs `pricing.py`) and 8 `test_libsql_integration.py::TestLive` errors (no live endpoint); the latter fail identically with this change stashed. Ruff clean.

## Status

**Completed** | Created: 2026-10-04 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-10-04T17:48:58 - `9fc9c631-6fa5-49fc-b42f-887aa38e1bf9.jsonl`
- `/ll:ready-issue` - 2026-10-04T17:35:08 - `b970e509-7d69-406a-af5f-a9beada13c52.jsonl`
- `/ll:ready-issue` - 2026-10-04T17:23:31 - `44b0fc74-7bed-48d3-bb6f-bfd73dcfe916.jsonl`
- `/ll:confidence-check` - 2026-10-04T17:20:47 - `8a3efb4e-00d3-4735-b344-4003dc6dc953.jsonl`
