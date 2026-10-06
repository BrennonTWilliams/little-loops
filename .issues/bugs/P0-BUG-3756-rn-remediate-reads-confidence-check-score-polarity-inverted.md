---
id: BUG-3756
title: rn-remediate reads confidence-check criterion scores with inverted polarity
type: BUG
priority: P0
status: open
discovered_date: '2026-10-05'
parent: BUG-3754
labels:
- confidence-check
- rn-remediate
- scoring
relates_to:
- BUG-3757
- ENH-3742
confidence_score: 95
outcome_confidence: 59
score_complexity: 5
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3756: rn-remediate reads confidence-check criterion scores with inverted polarity

## Summary

The rubric scores outcome criteria as points toward confidence: high = better. rn-remediate reads high as worse, so its complexity band, dimensional diagnosis and convergence deltas target the wrong end of the scale. It also mistakes a zero change-surface score for an absent integration map. Correct those reads together, validate and normalize every assessment snapshot, preserve rejected-assessment routing through the remediation budget, and remove score-only early decomposition: neither D nor a wiring-attempt marker identifies which D scoring pattern applies.

## Parent Issue

Decomposed from BUG-3754. BUG-3757 owns threshold documentation and set-flags configuration drift. This child owns score polarity, score validation, the inventory/wiring predicate, convergence and loop documentation.

## Current Behavior

- `scripts/little_loops/loops/rn-remediate.yaml:179` snapshots `ABOVE_MINIMAL` for A ≥ 15. `check_complexity_pre_implement` and `diagnose` also treat large A/C/D scores as bad. A=5 with passing aggregate scores currently receives the `MINIMAL` band and can skip required preparation.
- `check_wire_pre_implement`, `check_wire_needed_outcome`, and both dimensional WIRE predicates in `diagnose` treat D=0 as an absent integration map. D=0 actually means wide code blast radius (Pattern A) or unenumerated mechanical fanout (Pattern B); D=25 means isolation or well-verified enumeration. Neither value proves map presence.
- `scripts/little_loops/cli/issues/show.py:207` already returns `integration_files`: a positive count of bullets under `### Files to Modify`, or null without a positive count. Scores and positive counts are JSON strings, not JSON numbers.
- Initial and reassessment snapshot states only require aggregate scores. A/C/D reads use `// 0`, conflating a legitimate worst score with missing/null data. JSON errors can also be ignored before a band or delta is computed.
- `check_convergence` uses pre − post for A/C although its confidence/outcome deltas use post − pre. An improvement in A/C can therefore reduce `total_delta` and look stalled.
- `diagnose`'s final rule (`rn-remediate.yaml:401`) is `CHANGE_SURFACE -ge diagnose_change_surface_threshold` → `DECOMPOSE`. Under high = better, D ≥ 15 is the *good* end, so D=25 currently decomposes. Flipping it to `D < 15`, even with a wired marker, is insufficient: Pattern B with enumerated files but no verification command scores D=10, and `wire.on_partial` also writes that marker. The marker proves an attempt, not verified completion or Pattern A.
- `diagnose` has two entry paths. From `check_decision_needed.on_no` the outcome gate has just failed, so the generic outcome-failure REFINE rule (line 399) precedes DECOMPOSE/REFINE_LIGHT and the tail is unreachable. From `check_remediation_budget.on_yes` (after `CONVERGED_IMPROVED`/`CONVERGED_STALLED`) it is **reachable**: `check_outcome` passes → `refine_first` → `re_assess` → budget → `diagnose` with outcome ≥ threshold and confidence in [`diagnose_confidence_floor`, readiness). Once A/C polarity is corrected, A/C ≥ 15 no longer trip the REFINE rule, so those issues fall to the DECOMPOSE/REFINE_LIGHT tail for the first time.
- `assess.on_no` (line 152) routes to `refine_first`, bypassing `verify_scores_persisted`. No `pre_scores`/band artifact is written on that path, so `check_convergence` reports "Pre-scores file not found" and `gate_implement` reads an absent band and fails open to `MINIMAL`.
- `re_assess.on_no` routes directly to `refine_followup` → `re_assess`, bypassing POST validation, convergence accounting, baseline refresh and the remediation budget. Repeated `no` verdicts can continue until `max_steps` instead of the configured pass limit.
- Both assessment states use the generic LLM action-success judge, not a deterministic STOP parser. A completed confidence check can report a hard STOP with passing aggregates; adding validation must preserve an evaluator `no` rather than promote it through numeric readiness. The same STOP output can also receive `yes` from that judge; recognizing such a semantic STOP independently is a separate evaluator follow-up.
- `diagnose` re-fetches live JSON and checks only for empty output, then reads scores with `// 0`. Validating PRE alone leaves this later fetch unchecked; reading the inventory from PRE while taking dimensions/flags from live JSON also mixes assessment generations.
- The `emit_needs_manual_review` handoff (`rn-remediate.yaml:1052-1053`) uses `_score(post_scores, …) or _score(pre_scores, …)`: numeric post 0 falls back to the pre score, while string `"0"` already survives. `_score` returns the truthy display sentinel `"?"` for missing/null, so those values never fall back. The helper and caller both need correction.
- Digit strings such as `"08"` are within the proposed score contract but fail bash arithmetic as invalid octal unless normalized to decimal integers before convergence. Snapshot actions currently write directly to their final paths and can return success after a failed JSON fetch.
- The loop reference documents inverted scores and an obsolete convergence cutoff (`total_delta ≤ 2` versus the implemented `≤ 0`). The rubric implies polarity through its tables; other consumers already use high = better.

## Steps to Reproduce

1. Extract and render the existing `verify_scores_persisted` shell action in a temporary directory, replacing context variables and unescaping `$$` → `$`. Stub `ll-issues path` and `show --json` on PATH; the issue file has confidence 95 / outcome 80, and JSON has A=`"5"`, C/D=`"25"`. Observe `complexity_band_<ID>.txt` is `MINIMAL`. The intended band is `ABOVE_MINIMAL`.
2. Render the full `diagnose` action with confidence 80 / outcome 60, A/C=`"25"`, D=`"0"`, and `integration_files="2"`. Observe `WIRE` despite a populated inventory. Do not run the complete implementation loop to reproduce a shell routing defect.
3. In initial/reassessment snapshots, omit A or set it to null while keeping aggregate scores present. The current snapshots accept it and later reads invent zero; a real A=`"0"` is indistinguishable under that fallback.
4. Seed pre/post snapshots with below-gate aggregate scores held constant, A 10 → 20 and C unchanged. Execute `check_convergence`: current `delta_complexity` is −10 instead of +10.
5. Execute the handoff action with PRE A=`"25"`/C=`"18"`. POST numeric 0 reports PRE values; POST string `"0"` reports 0; absent/null POST reports `?` rather than PRE. Evaluate `VALUE=08; echo $((VALUE + 1))` in bash to reproduce the accepted digit-string arithmetic hazard.
6. Walk the declared `re_assess.on_no` → `refine_followup` → `mark_refined` → decision check → `re_assess` transitions with the decision flag false. No POST validation or remediation-counter increment occurs. Stub the default judge with `yes` and `no` for the same STOP output to verify that STOP text has no fixed routing mapping; do not infer one from a single live judge response.

## Root Cause

The reader interprets criterion names as risk magnitudes, although the rubric stores confidence points. It also uses D as a structural map-presence and decomposition proxy even though Criterion D has two scoring patterns. Snapshot validation never established the criterion-score contract or covered rejected assessments and later live fetches. Truthiness conflates numeric zero with absence in the handoff. Tests pin old shell text or isolated branches instead of exercising persisted artifacts and complete entry/retry paths.

## Expected Behavior

- All four outcome criteria are 0–25 confidence points, high = better. `diagnose_complexity_threshold` and `diagnose_ambiguity_threshold` remain 15 and become minimum acceptable scores: deficient is `< threshold`, equality is acceptable. Retain `diagnose_change_surface_threshold: 15` as a compatibility context key with no routing effect after removing the D-only rule. `diagnose_confidence_floor` remains an aggregate readiness floor of 50 with its existing `<` comparison; its semantics do not invert. The existing `≤ 10` advisory ambiguity escalation stays unchanged.
- The initial A score alone defines the stable band against `diagnose_complexity_threshold` (default 15): `< minimum` → `ABOVE_MINIMAL`, `≥ minimum` → `MINIMAL`. Later score improvements do not erase the initial requirement for both preparation markers. Keep existing artifact/token names, opt-out and intentional marker-gate error policy.
- Both `verify_scores_persisted` and `verify_re_assess_scores` validate confidence/outcome (0–100) and consumed A/C/D (0–25) on every `yes`/`partial`/`no` assessment path. Accept integer-valued JSON numbers and strings matching `^[0-9]+$`; preserve real zero. Reject missing/null, booleans, objects, arrays, fractional/nonnumeric/out-of-range values, signed or whitespace-padded strings, a non-object JSON root, and failed/malformed JSON fetches. Normalize accepted score fields to JSON base-10 integers (`"08"` → 8), preserving the rest of the full `show --json` document. Rejections go to existing `emit_scores_missing` → `failed`, with `SCORES_MISSING`, before any band or implementation decision.
- Fetch into a temporary file in the run directory, check command status, validate/normalize, then promote the complete snapshot with a checked atomic replacement. Publish the initial band only after successful validation/persistence. A failed fetch or validation cannot consume a stale prior POST, replace the stable band, or return success; snapshot/band write failures also terminate through `emit_scores_missing`. Refresh POST → PRE atomically before the next diagnosis. Explicitly classify snapshot read/refresh failures as `SCORES_MISSING` in `diagnose`/`check_convergence` and route to that emitter; do not let a nonzero arithmetic/copy exit fall through to convergence's generic `_error: gate_implement` fallback. Preserve that fallback for unrelated faults. Temporary files are per issue/run and cleaned up on failure.
- Wiring predicates use a populated `integration_files` inventory independently of D. Null/zero means no inventory; positive means an inventory was found. A `wired_<ID>.txt` marker prevents a repeated WIRE caused solely by the counter still returning null/zero.
- Preserve first-match routing order while correcting comparisons and inventory predicates. Keep explicit decision/missing-artifact handling and the generic outcome-failure REFINE rule. Do not enable early decomposition merely because D is low: Pattern B may need enumeration or verification, rather than splitting.
- **DECOMPOSE tail rule (decided, supersedes the prior marker heuristic):** remove the score-only DECOMPOSE condition. Residual D deficiencies fall through to `REFINE_LIGHT`, with or without a wired marker. A/C=25, test coverage=18, D=10, outcome=78 and readiness=80 is a mechanical-verification gap that must not prematurely decompose after wiring. Keep the existing DECOMPOSE route/token and emitter for compatibility, but diagnosis no longer emits it from scores. Decomposition remains available through the existing remediation-budget exhaustion → `emit_stalled_needs_decompose`; pattern-aware early decomposition is a separate follow-up.
- The wired-marker consult applies only to `diagnose`'s two inventory-only WIRE rules. It does not suppress explicit `missing_artifacts`. `check_wire_pre_implement` and `check_wire_needed_outcome` are first-pass-only and use the inventory predicate alone. Diagnosis reads dimensions, aggregates, inventory and flags from one validated PRE snapshot, without a live refetch; reassessment refreshes that snapshot before budget re-entry.
- Add `capture: assess` and `capture: re_assess` to preserve the evaluator verdict across validation. `assess.on_no` routes through `verify_scores_persisted` before a post-validation verdict gate: `no` → `refine_first`, `yes`/`partial` → existing readiness gates. Passing numbers must never promote a captured `no`. Initial validation captures the stable band on both paths; invalid scores go to `emit_scores_missing`. Preserve existing error/rate-limit/abstention behavior; do not claim that textual STOP deterministically maps to `on_no`.
- `re_assess.on_no` also routes through `verify_re_assess_scores`. Every validated reassessment computes/logs deltas, increments the shared counter exactly once and refreshes PRE. A captured `no` cannot emit `CONVERGED_PASS` or enter score-based diagnosis: route it through a rejection-specific budget check using the same counter/maximum, then `refine_followup` if budget remains, otherwise `emit_stalled_needs_decompose`. Ordinary `yes`/`partial` convergence and existing decision/manual-review behavior remain intact. The repeated-no path is bounded by `max_remediation_passes`, not just `max_steps`.
- The handoff's `_score` helper returns `None` for an absent dict/key or null. Fall back from post to pre only on `None`, preserving numeric 0 and string `"0"`; convert unresolved `None` to `?` only when formatting display fields.
- A/C convergence deltas become post − pre, with positive = improved. Keep the existing four-term sum, pass-over-pass baseline refresh, threshold gates and shared remediation budget; run all shell arithmetic on normalized decimal scores.

## Program Design

### Types

- Input fields `confidence`, `outcome`, `score_complexity`, `score_ambiguity`, `score_change_surface`: integer-valued JSON numbers or digit strings within the ranges above; missing is distinct from zero. Validated snapshots store canonical integers in these fields and preserve the rest of the JSON object.
- `integration_files`: existing positive count string or null from `show --json`; this is a heuristic for a populated file inventory, not proof of complete integration wiring.
- `complexity_band_<ID>.txt`: existing `ABOVE_MINIMAL | MINIMAL` token, written from the validated initial A score and retained across passes.
- `refined_<ID>.txt`, `wired_<ID>.txt`: existing monotonic preparation markers.
- `captured.assess.verdict`, `captured.re_assess.verdict`: existing executor-provided evaluator verdicts, used after validation. Add an internal rejected-reassessment routing token/budget hop without changing parent outcome tokens or public score schema.

### Signatures

- `_run_action(state: str, scores: dict[str, object], run_dir: Path, *, thresholds: dict[str, int]) -> subprocess.CompletedProcess[str]` — proposed test-only renderer executing extracted shell actions with stubbed `ll-issues`; extend fixtures for captured verdicts, JSON/fetch/write failures and marker files. Pair it with a small executor walk using stubbed action/evaluator results to exercise actual transitions. No new public CLI or score schema is required.

### Call Path

`assess` (`yes`/`partial`/`no`, captured) → validated initial snapshot/band → verdict gate (`no` → `refine_first`; otherwise readiness/outcome gates) → inventory check or snapshot-based `diagnose` → one remediation action/marker → `re_assess` (`yes`/`partial`/`no`, captured) → validated POST → delta logging/counter/PRE refresh → ordinary convergence or rejected-assessment budget check. Ordinary retries retain `diagnose`; rejected reassessments retry via `refine_followup`. Both use the same pass limit and exhaustion emitter. Validation failures terminate through `emit_scores_missing`; they cannot use the gate's absent-band fallback.

## Implementation Steps

1. Ship comparison corrections, strict snapshot validation/normalization and rejected-assessment routing together. Check JSON command status; validate A/C/D plus aggregates at both persistence states; normalize accepted scores to decimal JSON integers. Publish the full JSON object only after validation via checked temporary-file replacement, then capture the stable initial band. Check persistence failures and avoid stale-sidecar reuse. Do not add a score-repair loop or silently invent zero; JSON validation supplies the authoritative numeric contract.
2. Flip A/C deficiency comparisons to `<` with existing context thresholds. Replace the D==0 inventory proxy in `check_wire_pre_implement`, `check_wire_needed_outcome`, and both diagnose WIRE rules. Only diagnose's inventory-only WIRE rules consult the wired marker; explicit artifact gaps remain separate. Diagnose consumes one validated PRE document for scores, inventory and flags instead of refetching live JSON. Remove the D-only DECOMPOSE condition; keep the compatibility route/emitter and retained inactive D context key. Keep `# Priority-ordered routing`, token forms, remaining first-match ordering and defaults. Preserve MR11 marker adjacency; update marker enumeration for changed/new references and remove any marker orphaned by the deleted D condition.
3. Capture both assessment verdicts and route `no` through their existing snapshot validators. Add an initial post-validation verdict gate so `no` still leads to `refine_first`, even with passing numbers. Add a rejection-specific reassessment budget route to `refine_followup` or the existing exhaustion emitter. Reuse the shared count/limit and increment/refresh once per validated POST; do not let rejected assessments take PASS or diagnose's IMPLEMENT route. Preserve error/rate-limit/abstention behavior. Test captured `yes`/`partial`/`no` through the executor; textual STOP is not a deterministic judge verdict.
4. Use post − pre for A/C deltas, retaining the existing sum and checked atomic POST → PRE refresh. Run arithmetic only on normalized scores. Add explicit `SCORES_MISSING` classification/routes for snapshot read/refresh failures in convergence and diagnosis so they cannot use generic error-to-gate fallback. Relabel the handoff's raw "Complexity band" value as a criterion score; the stable band artifact is separate. Change `_score` to return `None` for absent/null, use an `is None` fallback, and render `?` only at display time. Leave the marker gate's deliberate error/opt-out behavior intact. Ship these runtime changes in one commit because local-editable consumers see them immediately.
5. Add one polarity statement to `skills/confidence-check/rubric.md`, including D's distinction from inventory presence and decomposition evidence. Keep new prose out of the 499/500-line SKILL.md. Regenerate the tracked gemini/kimi-code/qwen mirrors with `ll-adapt --host <host> --apply` and verify generated artifacts/companions.
6. Update the whole rn-remediate section of `docs/guides/LOOPS_REFERENCE.md`: parameter semantics, wiring/diagnosis table, snapshot and rejected-verdict paths, delta formulas, actual `≤ 0` convergence cutoff, PASS through `gate_implement`, and marker-gate prose. Explain why REFINE_LIGHT is reachable on budget re-entry, why diagnosis no longer emits score-only DECOMPOSE, and how the shared budget still escalates. Document reversed A/C minimum-score thresholds, the retained inactive D threshold, and the unchanged aggregate confidence floor; do not say all four parameters invert. Describe inventory-count limitations, including placeholder bullets and alternative headings. Correct the stale readiness comment/docstring in coordination with BUG-3757.
7. Replace tests that pin inverted behavior deliberately, including `TestDiagnoseAmbiguityWireDiscrimination` (its current A/D defaults of zero and C=18 are no longer appropriate), `TestMarkerGate`, delta/threshold/tail text pins and MR11 enumerations. Revise the existing direct-no routing pins to assert post-validation destinations and compatibility tests that assume diagnosis still emits DECOMPOSE. Keep passing tests for other high = better consumers unchanged.
8. Add the behavioral matrix below, exercising complete rendered actions and executor transitions rather than only routing substrings. Include initial/reassessment `yes`/`partial`/`no` walks to prove invalid scores reach `SCORES_MISSING`/`failed`, never `gate_implement` or `implement`, and repeated rejected assessments exhaust the configured pass budget.
9. Run `python -m pytest scripts/tests/test_rn_remediate.py scripts/tests/test_confidence_check_skill.py scripts/tests/test_builtin_loops.py scripts/tests/test_preparation_policy.py scripts/tests/test_preparation_policy_parity.py scripts/tests/test_wiring_skills_and_commands.py scripts/tests/test_enh494_skill_companions.py scripts/tests/test_docs_audience_gate.py -q`, then the full `python -m pytest scripts/tests/`. Validate the loop with no new warnings. Document A/C threshold reversal and removal of D-threshold routing in the loop reference now and normal release notes during release prep; do not create an unrelated Unreleased section.

### Behavioral Test Matrix

| Area | Cases and observable result |
|------|-----------------------------|
| Band / A / C boundary | 0, 5, 14 are deficient; 15, 25 acceptable. Initial A=5 → `ABOVE_MINIMAL`; A=25 → `MINIMAL`. A custom minimum 20 makes 18 deficient. |
| Validation / normalization | At both snapshots and on `yes`/`partial`/`no`, numeric 0, string `"0"`, integral JSON floats and digit string `"08"` are accepted and normalized. Reject absent/null, boolean/object/array fields, `"abc"`, signed/padded strings, negative/fractional/26 criterion scores, invalid JSON roots and out-of-range aggregates. Include command failure with plausible stdout, malformed JSON and failed writes. No rejection publishes a new band or reaches implementation. |
| Snapshot integrity | Seed an old POST then fail the next fetch: terminate through `SCORES_MISSING`, never reuse it. Verify normalized full snapshots retain inventory/flags. Diagnosis uses refreshed PRE without a live `show` call. Missing/unreadable snapshots and failed POST → PRE replacement classify `SCORES_MISSING`, never generic `_error` → gate. Successful refresh preserves the initial band. |
| Stable marker gate | Initial A=10, then A=20 after reassessment: original band remains. Neither marker → `NEED_REFINE`; refined only → `NEED_WIRE`; both → `IMPLEMENT`. Also cover minimal/absent band behavior and `require_refine_and_wire=false` as existing deliberate bypasses. |
| Independent inventory | D=0 with positive inventory does not imply WIRE; D=25 with null/zero inventory is eligible for WIRE. Cover both pre-implement/outcome wiring gates and low-A/C diagnose branches. Positive inventories with low A/C refine rather than re-wire. |
| Repeated wiring | A wired marker plus null/zero inventory does not cause another inventory-only WIRE. Explicit `missing_artifacts` handling remains separate. |
| Real routing path | Passing aggregates and all-25 criteria preserve readiness → wire check → gate behavior. Below-outcome snapshots cover decision/artifact precedence and dimensional remediation. D=0 with outcome failing gives WIRE or REFINE, never premature DECOMPOSE; retain budget exhaustion → decomposition. |
| Budget re-entry tail | Outcome ≥ threshold, confidence in [floor, readiness), A/C = 25: D=0/5/10/15/25 → `REFINE_LIGHT`, with and without a wired marker. Explicitly test Pattern B A/C=25, B=18, D=10, outcome=78, confidence=80 after partial/full wiring; never premature DECOMPOSE. Persistent deficiencies still exhaust the shared budget and emit `STALLED_NEEDS_DECOMPOSE`. Custom D threshold has no routing effect. |
| Initial verdict preservation | Captured `no` writes band/PRE via validation then reaches `refine_first`, including a STOP fixture with passing aggregates and both markers present. `yes`/`partial` retain readiness routing. Invalid scores on every path → `SCORES_MISSING`; never an absent-band fail-open to implementation. Stub the judge explicitly; do not assert STOP text always means `no`. |
| Reassessment rejection budget | Captured `no` validates POST, logs deltas, increments once and refreshes PRE, even when aggregates pass; no PASS/IMPLEMENT/diagnose. Remaining budget → `refine_followup`; repeated `no` exhausts at the configured maximum and emits the existing stall token. Invalid scores on `no` fail immediately. Cover nondefault max passes and preserved decision/error/rate-limit routes. |
| Handoff fallback | Numeric post 0 and string `"0"` are both preserved; absent/null POST falls back to PRE; both absent displays `?`. This exercises `_score` and formatting together. |
| Convergence | Hold below-gate aggregates constant and raise/lower/hold A and C: signs are +/−/0. Assert the four-term sum, output token, refreshed baseline and stable initial band. Include passing aggregates and decision-flag precedence. |

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/rn-remediate.yaml` — both assessment captures/no paths and snapshot validators; initial verdict gate; rejection budget hop; complexity band/check; wiring gates; snapshot-based diagnose/tail; convergence A/C deltas/accounting; handoff helper/label/comments.
- `scripts/tests/test_rn_remediate.py` — state-action harness, contract/transition matrix and revised existing pins.
- `skills/confidence-check/rubric.md` — explicit points polarity and D/inventory distinction.
- `docs/guides/LOOPS_REFERENCE.md` — active/retained threshold semantics, wiring heuristics, snapshot/verdict routing, removal of score-only decomposition, delta/convergence and gate behavior.
- `.gemini/skills/confidence-check/`, `.kimi-code/skills/confidence-check/`, `.qwen/skills/confidence-check/` — regenerated tracked mirrors.
- `scripts/tests/test_builtin_loops.py` — MR11 enumeration for deleted/new references and warning budget. Remove an orphaned change-surface marker if deleting its condition leaves it unused.

### Dependent Files

- `scripts/little_loops/cli/issues/show.py` already exposes nullable `integration_files` and string-valued scores; consume its existing contract without a parser/API extension.
- `scripts/little_loops/loops/rn-implement.yaml` passes thresholds and consumes sidecar summaries; it does not interpret delta signs or stable bands.
- The shared `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` persistence oracle is not the rn-remediate snapshot implementation; do not rename its states or widen this bug to other loops.
- `scripts/little_loops/fsm/executor.py:2355` already stores captured evaluator verdicts after evaluation; use its existing interpolation contract without executor/schema changes. The default judge (`executor.py:3247`, `evaluators.py:123`) checks action success; a semantic STOP-to-success mismatch is a separate follow-up.
- `skills/confidence-check/SKILL.md:393` requires persisting aggregate/dimensional scores after scoring with no STOP exception. Rejecting absent scores on `no` enforces that existing contract rather than adding a score-repair retry.
- BUG-3757 shares the readiness comment/test docstring and rubric. ENH-3742 shares confidence-check documents. Coordinate shared-file edits; no hard implementation dependency is required.

### Existing Patterns and Tests

Use `scripts/tests/test_rn_implement.py`'s rendered action/stubbed-PATH pattern and `scripts/tests/test_rn_remediate.py`'s existing loop loader. Preserve loop warning/MR11 gates, the preparation-policy suites' established high = better fixtures, and the docs-audience/skill companion gates.

## Scope Boundaries

- No scoring-table, aggregate weighting, threshold-default, persistent-score migration or new Criterion D pattern field. The existing A/C minimum of 15 is an explicit choice; a mirrored ≤10 cutoff is not selected. Preserve the D context key/default for compatibility while disabling its unsupported score-only decomposition effect.
- No reordering of the remaining `diagnose` rules. Remove only the D-only DECOMPOSE condition; keep the token/route/emitter as compatibility surface. A Criterion D pattern discriminator and pattern-aware early decomposition are a separate, nonblocking enhancement. Rejected alternative: low D plus wired marker still falsely decomposes enumerated Pattern B without verification, especially after a partial wire. Accepted tradeoff: genuine broad changes may consume up to the existing three remediation passes before budget escalation.
- No change to the marker gate's intentional absent-band/error fallback, opt-out, monotonic markers, explicit decision/artifact priority or budget maximum. Extend validation and accounting to rejected assessments so bad snapshots cannot use those fallbacks and `no` retries cannot evade the budget.
- No generic evaluator redesign or promise that textual STOP maps to `no`. Preserve captured evaluator rejection in this fix. A separate, nonblocking follow-up should make semantic hard STOP outcomes machine-readable and authoritative even when the generic action-success judge says `yes`/`partial`; the new verdict-preservation tests must not be presented as closing that gap.
- Apply between runs or start a fresh run directory after deployment: retained bands from a pre-fix run have old semantics. Automatic migration of active-run sidecars is outside this change.

## Impact

- **Priority**: P0 - criterion polarity is inverted for every processed issue; hard issues can skip the preparation gate
- **Effort**: Medium
- **Risk**: Medium - live local-editable projects pick up the fix immediately; validation, stable bands and wiring markers must ship together
- **Breaking Change**: Yes for custom routing: A/C thresholds become minimum acceptable confidence points; the retained D threshold no longer drives early decomposition. The aggregate confidence floor is unchanged. Artifact names and persistent score data remain compatible; internal snapshots normalize numbers and callers should start fresh runs rather than resume pre-fix sidecars.

## Acceptance Criteria

- Criterion polarity is high = better; A/C deficiency uses `< configured minimum`, with default/equality/custom-threshold tests and a stable initial band. D no longer implies inventory absence or early decomposition; the retained D key is inactive and the aggregate confidence floor remains unchanged.
- Both snapshot states cover `yes`/`partial`/`no`, accept/normalize legitimate zero/digit-string/integral-number scores, reject invalid/missing scores and failed fetch/write operations explicitly, and terminate through `SCORES_MISSING` without reaching implementation. Only validated full snapshots are published/consumed; diagnosis cannot mix generations or invent zeros.
- Inventory-based diagnosis honors prior wiring markers without suppressing explicit artifact gaps; first-pass inventory gates retain their marker-free contract. Pattern B D=10 after partial/full wiring and D=25 never prematurely decompose. Persistently deficient issues still reach existing budget-based decomposition.
- Initial `no` runs validation/band capture and then `refine_first`, regardless of passing aggregates. Reassessment `no` validates, logs, refreshes and counts once, then retries additively or exhausts the shared configured budget; it cannot take PASS or score-based IMPLEMENT routes.
- The handoff preserves numeric and string zero, falls back for absent/null POST and displays `?` only when both snapshots lack a score.
- A/C deltas are post − pre with decimal arithmetic; the existing sum, baseline refresh, marker gate, budget maximum and decision handling are preserved and behaviorally tested.
- Rubric, loop reference, tracked mirrors and migration notes agree. Targeted/full local tests and loop/artifact/doc gates pass without new warnings.

## Review Notes

First review on 2026-10-06 used extracted shell actions and an Opus `/ll:advise` consult (`signal=user_requested`, confidence 0.75). It supported corrected polarity, validation, independent inventory and expanded sibling threshold scope, and rejected early decomposition without a D discriminator. Its ≤10-cutoff dissent was not selected; A/C retain the configured minimum 15.

Second review on 2026-10-06 (Fable `/ll:advise`, confidence 0.8) found the tail reachable on budget re-entry, initial `on_no` bypassing band capture, handoff truthiness, and diagnose-only marker scope. Its proposed low-D-plus-wired DECOMPOSE rule and claim that all four `diagnose_*` parameters change semantics are superseded by the third review below.

Third review on 2026-10-06 used `/ll:advise --signal user_requested --host claude-code --model opus` (confidence 0.78). The advisor recommended removing score-only early decomposition because partial wiring sets the marker and Pattern B D=10 still needs verification, plus validating/accounting for reassessment `no`, preserving captured initial rejection, using one validated snapshot generation, normalizing decimal scores, and fixing the helper's missing sentinel. All are included above. Its dissent proposed a new complete-wiring marker and D=0 heuristic to save passes; that remains insufficient proof of the D pattern and is outside this fix. The advisor suggested three threshold inversions, but deleting the D rule leaves that key inactive; only A/C invert and the confidence floor stays unchanged.

Evidence from this review: full handoff-action probes reproduced numeric-zero replacement, string-zero preservation and missing/null failing to fall back; bash rejected `"08"` in arithmetic. An executor evaluation probe with a stubbed judge accepted either `yes` or `no` for the identical STOP output, confirming there is no deterministic STOP-to-`on_no` parser. This proves a routing-contract gap, not how a live judge will decide a particular run. The skill requires score persistence after scoring with no STOP exception; the executor already exposes captured verdicts. The repeated-no budget bypass and unchecked live diagnosis reads are present in the declared code paths.

Earlier baseline: 287 tests passed across rn-remediate, confidence-check and set-flags; direct probes reproduced A=5 → `MINIMAL` and populated inventory/D=0 → `WIRE`. This review reran rn-remediate and confidence-check: **268 passed**. Those existing tests do not cover the new behavioral matrix. No runtime implementation was made during these reviews.

## Status

**Open** | Created: 2026-10-06 | Priority: P0

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-06_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 59/100 → LOW

### Concerns
- Architecture (15/20): the rejected-reassessment budget hop and the initial post-validation verdict gate are new FSM routing shapes in `rn-remediate.yaml`. Precedent for rendered-action tests exists in `test_rn_implement.py`, but `test_rn_remediate.py` has no executor-walk harness yet, so the `_run_action` helper is net-new test infrastructure.
- Cited line `rn-remediate.yaml:179` is now line 181 (`ABOVE_MINIMAL` snapshot); `:401` (DECOMPOSE rule), `:152` (`assess.on_no`) and `:1052-1053` (handoff) are accurate.

### Outcome Risk Factors
- Deep per-site complexity: the single runtime file restructures control flow (new validation states, captured-verdict gates, atomic snapshot promotion, rejection budget routing) and must ship in one commit because local-editable consumers see changes immediately.
- Broad enumeration across 8 sites (loop YAML, tests, rubric, LOOPS_REFERENCE, 3 mirrors, test_builtin_loops), plus ~6 dependent loops/tests (rn-implement, autodev, refine-to-ready-issue, preparation-policy suites, MR11 enumeration).
- Existing tests pin shell text rather than behavior (194 test items, none render the shell actions); the 11-row behavioral matrix is effectively all new test code, so regressions in untouched branches could go undetected until it lands.
- Minor ambiguity: how the post-validation verdict gate reads `${captured.assess.verdict}` from a shell state is specified by contract but not by concrete state wiring; resolve while implementing.

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-10-06_ — **GO**

**Deciding Factor**: The defect is confirmed and the fix is well understood; remaining objections concern scope, sequencing and priority, not validity.

### Key Arguments For
- Inversion reproduces at `rn-remediate.yaml:180`, `:215`, `:384-399` against `rubric.md:281-345`; `rn-remediate` is the lone inverted consumer (`preparation_policy.py`, `rubric.md:442`, `issue_parser.py` all use high = better).
- Mixed delta signs (A/C pre−post vs confidence/outcome post−pre, lines 797-801) make an A/C improvement look like a stall; `assess.on_no` (152) and `re_assess.on_no` (733) bypass validation and the budget.

### Key Arguments Against
- Unlisted tests pin current behavior and must be updated: `scripts/tests/test_fsm_topology.py:319-331` (hard-pins 48 states), `scripts/tests/test_fsm_executor.py:2831-2842` (BUG-3489 pins `check_convergence._error → gate_implement`), `scripts/tests/test_builtin_loops.py:15617-15625` (`assess.on_no == "refine_first"`) and the MR11 allowlist at `:20009-20018`, and `scripts/tests/data/loop_interpolation_baseline.json:797` (`emit_needs_manual_review` heredoc line numbers).
- `check_convergence` emits `CONVERGED_STALLED` and exits (lines 774-778) before the counter increment (806-810) and the POST → PRE refresh, so a missing PRE never counts against the budget; trace this path when adding the `SCORES_MISSING` classification.
- `${captured.<state>.verdict}` has no shipped precedent for being read from a shell state (only a test fixture and `scaffold_verify.py`).
- Shared-file collisions with BUG-3757 (readiness comment, test docstring, `rubric.md`, mirrors) and ENH-3742 (`rubric.md`, `SKILL.md`, mirrors); sequence or coordinate those edits.
- The core polarity/delta-sign fix is ~10 lines; validation/atomic-snapshot/verdict-gate work could be split if the single-commit scope proves too large (outcome confidence 59).

### Rationale
Both sides agree the polarity inversion is real. `rn-remediate` is the lone inverted consumer, and it silently misroutes hard issues in tooling every local-editable project shares. The con side's objections concern scope and sequencing, and can be handled during implementation.

## Session Log
- `/ll:go-no-go` - 2026-10-06T17:31:50 - `6f6f118e-a57b-482f-b8e5-4dc2eadf81d3.jsonl`
- `/ll:confidence-check` - 2026-10-06T17:24:54 - `4c721804-b470-47a2-a026-f84f3bc78843.jsonl`
- `/ll:confidence-check` - 2026-10-06T17:08:39 - `06682c99-4a6d-4e45-b7d6-4e7235d06590.jsonl`
- `/ll:issue-size-review` - 2026-10-06T06:49:38 - `cede7154-079d-47b6-bd61-dd96bcbe90b1.jsonl`
