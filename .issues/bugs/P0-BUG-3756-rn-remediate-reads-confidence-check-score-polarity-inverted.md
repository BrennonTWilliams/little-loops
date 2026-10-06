---
id: BUG-3756
title: 'rn-remediate reads confidence-check criterion scores with inverted polarity'
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
---

# BUG-3756: rn-remediate reads confidence-check criterion scores with inverted polarity

## Summary

The rubric scores outcome criteria as points toward confidence: high = better. rn-remediate reads high as worse, so its complexity band, dimensional diagnosis and convergence deltas target the wrong end of the scale. It also mistakes a zero change-surface score for an absent integration map. Correct those reads together, validate missing scores explicitly, and preserve the bounded refine/wire gate and existing routing priority.

## Parent Issue

Decomposed from BUG-3754. BUG-3757 owns threshold documentation and set-flags configuration drift. This child owns score polarity, score validation, the inventory/wiring predicate, convergence and loop documentation.

## Current Behavior

- `scripts/little_loops/loops/rn-remediate.yaml:179` snapshots `ABOVE_MINIMAL` for A ≥ 15. `check_complexity_pre_implement` and `diagnose` also treat large A/C/D scores as bad. A=5 with passing aggregate scores currently receives the `MINIMAL` band and can skip required preparation.
- `check_wire_pre_implement`, `check_wire_needed_outcome`, and both dimensional WIRE predicates in `diagnose` treat D=0 as an absent integration map. D=0 actually means wide code blast radius (Pattern A) or unenumerated mechanical fanout (Pattern B); D=25 means isolation or well-verified enumeration. Neither value proves map presence.
- `scripts/little_loops/cli/issues/show.py:207` already returns `integration_files`: a positive count of bullets under `### Files to Modify`, or null without a positive count. Scores and positive counts are JSON strings, not JSON numbers.
- Initial and reassessment snapshot states only require aggregate scores. A/C/D reads use `// 0`, conflating a legitimate worst score with missing/null data. JSON errors can also be ignored before a band or delta is computed.
- `check_convergence` uses pre − post for A/C although its confidence/outcome deltas use post − pre. An improvement in A/C can therefore reduce `total_delta` and look stalled.
- `diagnose`'s final rule (`rn-remediate.yaml:401`) is `CHANGE_SURFACE -ge diagnose_change_surface_threshold` → `DECOMPOSE`. Under high = better, D ≥ 15 is the *good* end, so D=25 currently decomposes. Flipping it mechanically to `D < 15` would make low D alone decompose, which this issue rejects (Pattern B may need enumeration/verification, not splitting).
- `diagnose` has two entry paths. From `check_decision_needed.on_no` the outcome gate has just failed, so the generic outcome-failure REFINE rule (line 399) precedes DECOMPOSE/REFINE_LIGHT and the tail is unreachable. From `check_remediation_budget.on_yes` (after `CONVERGED_IMPROVED`/`CONVERGED_STALLED`) it is **reachable**: `check_outcome` passes → `refine_first` → `re_assess` → budget → `diagnose` with outcome ≥ threshold and confidence in [`diagnose_confidence_floor`, readiness). Once A/C polarity is corrected, A/C ≥ 15 no longer trip the REFINE rule, so those issues fall to the DECOMPOSE/REFINE_LIGHT tail for the first time.
- `assess.on_no` (line 152) routes to `refine_first`, bypassing `verify_scores_persisted`. No `pre_scores`/band artifact is written on that path, so `check_convergence` reports "Pre-scores file not found" and `gate_implement` reads an absent band and fails open to `MINIMAL`.
- The `emit_needs_manual_review` handoff (`rn-remediate.yaml:1052-1053`) uses `_score(post_scores, …) or _score(pre_scores, …)`, so a legitimate post score of 0 falls back to the pre score.
- The loop reference documents inverted scores and an obsolete convergence cutoff (`total_delta ≤ 2` versus the implemented `≤ 0`). The rubric implies polarity through its tables; other consumers already use high = better.

## Steps to Reproduce

1. Extract and render the existing `verify_scores_persisted` shell action in a temporary directory, replacing context variables and unescaping `$$` → `$`. Stub `ll-issues path` and `show --json` on PATH; the issue file has confidence 95 / outcome 80, and JSON has A=`"5"`, C/D=`"25"`. Observe `complexity_band_<ID>.txt` is `MINIMAL`. The intended band is `ABOVE_MINIMAL`.
2. Render the full `diagnose` action with confidence 80 / outcome 60, A/C=`"25"`, D=`"0"`, and `integration_files="2"`. Observe `WIRE` despite a populated inventory. Do not run the complete implementation loop to reproduce a shell routing defect.
3. In initial/reassessment snapshots, omit A or set it to null while keeping aggregate scores present. The current snapshots accept it and later reads invent zero; a real A=`"0"` is indistinguishable under that fallback.
4. Seed pre/post snapshots with below-gate aggregate scores held constant, A 10 → 20 and C unchanged. Execute `check_convergence`: current `delta_complexity` is −10 instead of +10.

## Root Cause

The reader interprets criterion names as risk magnitudes, although the rubric stores confidence points. It also uses D as a structural map-presence proxy even though Criterion D has two scoring patterns. Snapshot validation never established the criterion-score contract, and tests pin the old shell text or isolated branches instead of exercising the persisted artifacts and real entry path.

## Expected Behavior

- All four outcome criteria are 0–25 confidence points, high = better. Each `diagnose_*_threshold` remains 15 and means a minimum acceptable score: deficient is `< threshold`, equality is acceptable. The existing `≤ 10` advisory ambiguity escalation is a separate heuristic and stays unchanged.
- The initial A score alone defines the stable band: `< 15` → `ABOVE_MINIMAL`, `≥ 15` → `MINIMAL`. Later score improvements do not erase the initial requirement for both preparation markers. Keep the existing artifact/token names, opt-out and intentional gate error policy.
- Both `verify_scores_persisted` and `verify_re_assess_scores` validate confidence/outcome (0–100) and consumed A/C/D (0–25) before proceeding. Accept integer-valued JSON numbers and digit strings; preserve real zero. Missing/null/noninteger/nonnumeric/out-of-range data or a failed JSON fetch goes to existing `emit_scores_missing` → `failed`, with `SCORES_MISSING`. It gets no invented score or band and never falls through to implementation.
- Wiring predicates use a populated `integration_files` inventory independently of D. Null/zero means no inventory; positive means an inventory was found. A `wired_<ID>.txt` marker prevents a repeated WIRE caused solely by the counter still returning null/zero.
- Preserve first-match routing order while correcting comparisons and inventory predicates. Keep explicit decision/missing-artifact handling and the generic outcome-failure REFINE rule. Do not enable early decomposition merely because D is low: Pattern B may need enumeration or verification, rather than splitting.
- **DECOMPOSE tail rule (decided):** replace the inverted `D ≥ threshold` rule with `D < diagnose_change_surface_threshold` **AND** `wired_<ID>.txt` present → `DECOMPOSE` (enumeration already ran and the change surface is still deficient ⇒ blast radius, not a missing map). D deficient without the wired marker falls through to `REFINE_LIGHT`. This is the only route by which low D can decompose before budget exhaustion; budget exhaustion → `emit_stalled_needs_decompose` is unchanged.
- The wired-marker consult applies to `diagnose`'s two WIRE rules and the DECOMPOSE tail only. `check_wire_pre_implement` and `check_wire_needed_outcome` are first-pass-only (marker cannot exist yet) and use the inventory predicate alone. `integration_files` is read from the PRE snapshot.
- `assess.on_no` routes through `verify_scores_persisted` (same validation, band capture and PRE snapshot as the success path) before continuing to `refine_first`/`check_readiness` behavior; confirm the STOP-verdict → `on_no` mapping by execution before relying on it. Invalid scores still go to `emit_scores_missing`.
- The manual-review handoff falls back from post to pre score only when the post score is `None`, never on a zero.
- A/C convergence deltas become post − pre, with positive = improved. Keep the existing four-term sum, pass-over-pass baseline refresh, threshold gates and remediation budget.

## Program Design

### Types

- Snapshot fields `confidence`, `outcome`, `score_complexity`, `score_ambiguity`, `score_change_surface`: integer values or digit strings within the ranges above; missing is distinct from zero.
- `integration_files`: existing positive count string or null from `show --json`; this is a heuristic for a populated file inventory, not proof of complete integration wiring.
- `complexity_band_<ID>.txt`: existing `ABOVE_MINIMAL | MINIMAL` token, written from the validated initial A score and retained across passes.
- `refined_<ID>.txt`, `wired_<ID>.txt`: existing monotonic preparation markers.

### Signatures

- `_run_action(state: str, scores: dict[str, object], run_dir: Path, *, thresholds: dict[str, int]) -> subprocess.CompletedProcess[str]` — proposed test-only renderer executing extracted shell actions with stubbed `ll-issues`; support JSON strings/nulls and marker files. No new public CLI or score schema is required.

### Call Path

`assess` → validated initial snapshot/band → readiness/outcome gates → inventory check or `diagnose` → one remediation action/marker → `re_assess` → validated post snapshot → corrected convergence → stable `gate_implement` or budget-gated retry. Validation failures terminate through `emit_scores_missing`; they cannot use the gate's absent-band fallback.

## Implementation Steps

1. Ship the comparison corrections and snapshot validation together. Check the JSON command's exit status and validate A/C/D plus aggregates at both persistence states before computing artifacts. Do not add a score-repair loop or silently coerce absent values to zero. Keep existing frontmatter checks where pinned tests depend on them; JSON validation supplies the authoritative numeric contract.
2. Flip A/C/D risk comparisons to `<` with existing context thresholds. Replace the D==0 inventory proxy in `check_wire_pre_implement`, `check_wire_needed_outcome`, and both diagnose WIRE rules; in the two diagnose WIRE rules only, consult the existing wired marker before another inventory-only WIRE (read `integration_files` from the PRE snapshot). Rewrite the diagnose tail per Expected Behavior: `D < threshold AND wired marker` → `DECOMPOSE`, else `REFINE_LIGHT`. Keep `# Priority-ordered routing`, token forms, threshold defaults and first-match ordering. Preserve MR11 marker adjacency; update marker enumeration only if new context references require it.
3. Use post − pre for A/C deltas, retaining the existing sum and POST → PRE refresh. Relabel the handoff's raw "Complexity band" value as a criterion score; the stable band artifact is a separate concept. Replace the handoff's `_score(post) or _score(pre)` with an `is None` fallback (lines ~1052-1053). Leave gate behavior intact apart from consuming the corrected initial band.
3a. Route `assess.on_no` through `verify_scores_persisted` so band capture, validation and the PRE snapshot also run on the STOP path; verify the confidence-check STOP → `on_no` mapping by execution first. Ship the flip, validation, band capture and tail rule in a single commit (live local-editable consumers).
4. Add one polarity statement to `skills/confidence-check/rubric.md`, including D's distinction from inventory presence. Keep new prose out of the 499/500-line SKILL.md. Regenerate the tracked gemini/kimi-code/qwen mirrors with `ll-adapt --host <host> --apply` and verify generated artifacts/companions.
5. Update the whole rn-remediate section of `docs/guides/LOOPS_REFERENCE.md`: parameter semantics, wiring/diagnosis table, delta formulas, actual `≤ 0` convergence cutoff, PASS through `gate_implement`, and marker-gate prose. State that DECOMPOSE and REFINE_LIGHT are unreachable on first entry from a failed outcome gate but reachable on budget re-entry, that early DECOMPOSE requires low D plus the wired marker, and that decomposition otherwise remains available after remediation-budget exhaustion. Document the threshold-semantics change for all four `diagnose_*` parameters. Describe the inventory counter's limitations, including placeholder bullets and alternative headings. Correct the stale readiness comment/docstring in coordination with BUG-3757.
6. Replace tests that pin inverted behavior deliberately, including `TestDiagnoseAmbiguityWireDiscrimination` (its current A/D defaults of zero and C=18 are no longer appropriate), `TestMarkerGate`, delta/threshold text pins and MR11 enumerations. Keep passing tests for other high = better consumers unchanged.
7. Add the behavioral matrix below, exercising complete rendered actions rather than only routing substrings. Include a small transition walk from initial verification and from reassessment verification to prove invalid scores reach `SCORES_MISSING`/`failed`, never `gate_implement` or `implement`.
8. Run `python -m pytest scripts/tests/test_rn_remediate.py scripts/tests/test_confidence_check_skill.py scripts/tests/test_builtin_loops.py scripts/tests/test_preparation_policy.py scripts/tests/test_preparation_policy_parity.py scripts/tests/test_wiring_skills_and_commands.py scripts/tests/test_enh494_skill_companions.py scripts/tests/test_docs_audience_gate.py -q`, then the full `python -m pytest scripts/tests/`. Validate the loop with no new warnings. Document changed custom-threshold semantics in the loop reference now and the normal release notes during release prep; do not create an unrelated Unreleased section.

### Behavioral Test Matrix

| Area | Cases and observable result |
|------|-----------------------------|
| Band / A / C boundary | 0, 5, 14 are deficient; 15, 25 acceptable. Initial A=5 → `ABOVE_MINIMAL`; A=25 → `MINIMAL`. A custom minimum 20 makes 18 deficient. |
| Validation | At both snapshots, numeric 0 and string `"0"` are valid; absent/null, `"abc"`, negative, fractional and 26 criterion scores are rejected. Include aggregate out-of-range and failed/malformed JSON fetches. No rejection writes a new band or reaches implementation. |
| Stable marker gate | Initial A=10, then A=20 after reassessment: original band remains. Neither marker → `NEED_REFINE`; refined only → `NEED_WIRE`; both → `IMPLEMENT`. Also cover minimal/absent band behavior and `require_refine_and_wire=false` as existing deliberate bypasses. |
| Independent inventory | D=0 with positive inventory does not imply WIRE; D=25 with null/zero inventory is eligible for WIRE. Cover both pre-implement/outcome wiring gates and low-A/C diagnose branches. Positive inventories with low A/C refine rather than re-wire. |
| Repeated wiring | A wired marker plus null/zero inventory does not cause another inventory-only WIRE. Explicit `missing_artifacts` handling remains separate. |
| Real routing path | Passing aggregates and all-25 criteria preserve readiness → wire check → gate behavior. Below-outcome snapshots cover decision/artifact precedence and dimensional remediation. D=0 with outcome failing gives WIRE or REFINE, never premature DECOMPOSE; retain budget exhaustion → decomposition. |
| Budget re-entry tail | Outcome ≥ threshold, confidence in [floor, readiness), A/C = 25: D=25 → `REFINE_LIGHT` (never DECOMPOSE); D=5 without wired marker → `REFINE_LIGHT`; D=5 with wired marker → `DECOMPOSE`; D=15 (equality) → `REFINE_LIGHT`. |
| `assess` STOP path | `assess.on_no` writes the band/PRE snapshot via validation; invalid scores → `SCORES_MISSING`; never an absent-band fail-open to `implement`. |
| Handoff fallback | Post score `"0"` is reported as 0, not the pre score; post `None` falls back to pre. |
| Convergence | Hold below-gate aggregates constant and raise/lower/hold A and C: signs are +/−/0. Assert the four-term sum, output token, refreshed baseline and stable initial band. Include passing aggregates and decision-flag precedence. |

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/rn-remediate.yaml` — both snapshot states; complexity band/check; both wiring gates; diagnose predicates; convergence A/C deltas; handoff label/comments.
- `scripts/tests/test_rn_remediate.py` — state-action harness, contract/transition matrix and revised existing pins.
- `skills/confidence-check/rubric.md` — explicit points polarity and D/inventory distinction.
- `docs/guides/LOOPS_REFERENCE.md` — score thresholds, wiring heuristics, dormant routes, delta/convergence and gate behavior.
- `.gemini/skills/confidence-check/`, `.kimi-code/skills/confidence-check/`, `.qwen/skills/confidence-check/` — regenerated tracked mirrors.
- `scripts/tests/test_builtin_loops.py` — MR11 enumeration only if changed references require it.

### Dependent Files

- `scripts/little_loops/cli/issues/show.py` already exposes nullable `integration_files` and string-valued scores; consume its existing contract without a parser/API extension.
- `scripts/little_loops/loops/rn-implement.yaml` passes thresholds and consumes sidecar summaries; it does not interpret delta signs or stable bands.
- The shared `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` persistence oracle is not the rn-remediate snapshot implementation; do not rename its states or widen this bug to other loops.
- BUG-3757 shares the readiness comment/test docstring and rubric. ENH-3742 shares confidence-check documents. Coordinate shared-file edits; no hard implementation dependency is required.

### Existing Patterns and Tests

Use `scripts/tests/test_rn_implement.py`'s rendered action/stubbed-PATH pattern and `scripts/tests/test_rn_remediate.py`'s existing loop loader. Preserve loop warning/MR11 gates, the preparation-policy suites' established high = better fixtures, and the docs-audience/skill companion gates.

## Scope Boundaries

- No scoring-table, aggregate weighting, threshold-default, persistent-score migration or new Criterion D pattern field. The existing 15 minimum is an explicit choice; a mirrored ≤10 cutoff is not selected.
- No reordering of `diagnose` rules. The DECOMPOSE tail is changed only as specified (low D **and** wired marker); a richer discriminator between broad code changes and remediable mechanical verification gaps (e.g. a Criterion D pattern field) is a separate routing design. Rejected alternative: deleting the D rule and relying solely on budget exhaustion (costs up to three refine passes per Pattern A issue); the author may revisit.
- No change to the intentionally fail-open gate's absent-band/error fallback, opt-out, monotonic marker semantics, explicit decision/artifact guards or remediation budget. Strict validation must stop bad snapshots before those fallbacks can be used.
- Apply between runs or start a fresh run directory after deployment: retained bands from a pre-fix run have old semantics. Automatic migration of active-run sidecars is outside this change.

## Impact

- **Priority**: P0 - criterion polarity is inverted for every processed issue; hard issues can skip the preparation gate
- **Effort**: Medium
- **Risk**: Medium - live local-editable projects pick up the fix immediately; validation, stable bands and wiring markers must ship together
- **Breaking Change**: Yes for custom routing-threshold semantics: values now mean minimum acceptable confidence points. Artifact names and score data remain compatible; start fresh runs rather than resuming pre-fix sidecars.

## Acceptance Criteria

- A/C/D consistently use high = better and `< configured minimum` for deficiency, with default/equality/custom-threshold tests and a stable initial complexity band.
- Both snapshot states accept legitimate zero/string-valued scores, reject invalid/missing scores explicitly, and terminate through `SCORES_MISSING` without reaching an implementation path.
- All inventory-based wiring predicates use `integration_files` independently of D and honor prior wiring markers. The low-D/outcome-failing case does not prematurely decompose Pattern B issues, and the budget re-entry tail decomposes only on low D plus the wired marker (D=25 never decomposes).
- `assess.on_no` runs validation and band capture; the manual-review handoff reports a real zero post score.
- A/C deltas are post − pre; the existing sum, baseline refresh, marker gate, budget and decision handling are preserved and behaviorally tested.
- Rubric, loop reference, tracked mirrors and migration notes agree. Targeted/full local tests and loop/artifact/doc gates pass without new warnings.

## Review Notes

Reviewed on 2026-10-06 using extracted shell actions and an Opus `/ll:advise` consult (`signal=user_requested`, confidence 0.75). The advisor supported the corrected polarity, snapshot validation, independent inventory and expanded sibling threshold scope; it rejected activating the dormant decomposition branch without a Criterion D discriminator. Its dissent proposed a mirrored cutoff of ≤10; this issue explicitly chooses the existing configurable minimum 15 instead.

Second review on 2026-10-06 (Fable `/ll:advise`, confidence 0.8) found: the unspecified inverted DECOMPOSE tail rule; the "dormant" claim being false on `check_remediation_budget` re-entry; `assess.on_no` bypassing band capture; the handoff's `or` zero-conflation; and wired-marker scope (diagnose only). All folded into Current Behavior, Expected Behavior, Steps 2/3/3a, the test matrix, Scope Boundaries and Acceptance Criteria. Strict A/C/D validation was kept (unscored issues pre-date the rubric and `assess` always re-scores first). Unverified: the confidence-check STOP verdict → `assess.on_no` mapping. Low-severity notes kept as documentation items: `integration_files` counts placeholder bullets (`- None`); threshold semantics change for all four `diagnose_*` parameters (no caller passes custom values).

Pre-change baseline: 287 tests passed across rn-remediate, confidence-check and set-flags. Direct probes still reproduced A=5 → `MINIMAL` and D=0 with a populated inventory → `WIRE`; new behavioral coverage is required. No runtime implementation was made during this review.

## Status

**Open** | Created: 2026-10-06 | Priority: P0


## Session Log
- `/ll:issue-size-review` - 2026-10-06T06:49:38 - `cede7154-079d-47b6-bd61-dd96bcbe90b1.jsonl`
