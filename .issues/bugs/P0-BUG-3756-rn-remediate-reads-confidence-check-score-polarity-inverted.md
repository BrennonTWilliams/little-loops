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
---

# BUG-3756: rn-remediate reads confidence-check criterion scores with inverted polarity

## Summary

The rubric scores outcome criteria as points toward confidence (high = better): Criterion A gives a simple isolated change 25/25, Criterion C gives "no ambiguity" 25, Criterion D gives 0-2 callers 25. `rn-remediate.yaml` reads those same scores as high = worse, so complexity/ambiguity/change-surface remediation fires on simple, well-specified issues and skips hard ones. Align every rn-remediate read, the rubric, and `LOOPS_REFERENCE.md` on one stated polarity (high = better), with behavioral tests.

## Parent Issue

Decomposed from BUG-3754: Confidence-check score contract drift: rn-remediate reads score polarity inverted, skill text states a stale 75 outcome threshold. The stale-threshold half of the parent lives in the sibling child (BUG-3757).

## Current Behavior

- `verify_scores_persisted` band snapshot (`rn-remediate.yaml:179-184`) writes `ABOVE_MINIMAL` for `score_complexity >= diagnose_complexity_threshold` (15); `gate_implement` (`:438-439`) forces a refine+wire pass on that band.
- `check_complexity_pre_implement` (`:213-215`) reads the same inverted way.
- `diagnose` (`:365-366`, branches `:384`, `:388`, `:392`, `:399`, `:401`) routes `score_ambiguity >= 15` to REFINE, `score_complexity >= 15` to WIRE/REFINE, and `score_change_surface >= 15` to DECOMPOSE; `CHANGE_SURFACE -eq 0` is read as "no integration map" (`:385`, `:393`, `check_wire_pre_implement` `:225`).
- `check_convergence` (`:788-804`) computes `DELTA_COMPLEXITY=$((PRE - POST))` and `DELTA_AMBIGUITY` the same way ("improvement means score went DOWN"), so a refine pass that raises scores subtracts from `TOTAL_DELTA`, which drives the `TOTAL_DELTA -le 0` stall branch (`:834`).
- Missing criterion scores default via `jq -r '.score_X // 0'`, which under the corrected polarity would silently select the worst band.
- `docs/guides/LOOPS_REFERENCE.md` rows `:616`, `:641`, `:649-651`, `:659-660`, `:662`, `:728` document the inverted reading.
- `rubric.md` never states polarity; it is implied only by the score tables. Other consumers (`preparation_policy.py:646-648`, `rubric.md:442-443`, `skills/issue-size-review/SKILL.md:166`) already read high = better.

## Expected Behavior

- One polarity, high = better, stated once in `skills/confidence-check/rubric.md` (consistent with the `score_ambiguity ≤ 10` escalation branch at `:442-443`) and followed by the band snapshot, `check_complexity_pre_implement`, `diagnose`, `gate_implement`, and the convergence deltas (`delta_*` positive = improved).
- Low `score_complexity` / `score_ambiguity` takes the `ABOVE_MINIMAL` / REFINE path; 25 does not.
- `score_change_surface` is flipped against the same polarity, or its exclusion is stated explicitly.
- Missing criterion scores have a stated, tested band.
- The ENH-2163 gate intent ("hard issues must be refined and wired before implement") is re-checked against the corrected band, not mechanically flipped.

## Implementation Steps

1. Decide and record: missing-score band, `score_change_surface` scope. Update `rn-remediate.yaml` (band snapshot, `check_complexity_pre_implement`, `diagnose`, `gate_implement`, `check_convergence`, `emit_needs_manual_review` `:1081` "Complexity band" wording). Preserve `# ll-lint: mr11-ok(context.X)` marker adjacency; add `MR11_MARKER_ALLOWLIST` entries for any new `${context.*}` ref (`test_builtin_loops.py` `TestMr11MarkerSet`). Keep `diagnose` using `${context.diagnose_*}` refs (no bare `-ge 15` / `-lt 50` literals).
2. Add the polarity statement to `skills/confidence-check/rubric.md` (new prose in `rubric.md`, not `SKILL.md`, which is 499/500 lines). Regenerate mirrors with `ll-adapt --host <gemini|kimi-code|qwen> --apply`; avoid `scripts/tests/…` / `scripts/little_loops/…` citations in skill/doc text (`test_docs_audience_gate.py`).
3. Update `docs/guides/LOOPS_REFERENCE.md` rows `:616`, `:641`, `:649-651`, `:659-660`, `:662` (also fix stale `total_delta ≤ 2` → `TOTAL_DELTA -le 0` / `gate_implement` wording), `:728`.
4. Update pinned tests deliberately, calling out old values: `test_rn_remediate.py` `TestDiagnoseAmbiguityWireDiscrimination` (both `ambiguity=18` cases and `_run` defaults; keep the `# Priority-ordered routing` slice marker and token form), `TestMarkerGate` (`:707-713`, `:748`), `DELTA_COMPLEXITY`/`DELTA_AMBIGUITY` assertions (`:893-894`), threshold-pin tests (`:964-965`, `:1137-1138`), `test_context_has_diagnose_thresholds` if defaults change, and `test_diagnose_catch_all_outputs_refine_light` ordering.
5. Add behavioral tests in `test_rn_remediate.py` (render the action, `$$` → `$`, stub `ll-issues path` / `show --json` on `PATH`, following `test_rn_implement.py` `check_learning_ready` `_run`): `verify_scores_persisted` band (`test_complexity_band_polarity`: 25 → not `ABOVE_MINIMAL`, 5 → `ABOVE_MINIMAL`), `gate_implement` (band absent/`MINIMAL`/`ABOVE_MINIMAL` × `refined_`/`wired_` markers → `IMPLEMENT`/`NEED_REFINE`/`NEED_WIRE`), `check_convergence` (seed `pre_scores_`/`post_scores_`, assert `delta_*` and `total_delta`), `check_complexity_pre_implement` exit code, and a `diagnose` change-surface routing test.
6. Run `python -m pytest scripts/tests/test_rn_remediate.py scripts/tests/test_confidence_check_skill.py scripts/tests/test_builtin_loops.py scripts/tests/test_preparation_policy.py -v`, then the full `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P0 - the loop's complexity/ambiguity remediation is inverted for every issue it processes; refine+wire effort goes to easy issues and hard ones skip the gate
- **Effort**: Medium
- **Risk**: Medium - changes which issues take the refine+wire path in all `local-editable` projects immediately
- **Breaking Change**: No

## Acceptance Criteria

(a) One documented polarity, high = better, stated once in the rubric and followed by rn-remediate's band snapshot, `diagnose` routing, convergence deltas, and the LOOPS_REFERENCE tables; a behavioral test pins it (score_complexity 25 does not take the `ABOVE_MINIMAL` path, 5 does). (b) Missing-score and `score_change_surface` handling are decided and tested. (c) The existing rn-remediate and confidence-check suites pass, and mirror gates pass.

## Status

**Open** | Created: 2026-10-06 | Priority: P0


## Session Log
- `/ll:issue-size-review` - 2026-10-06T06:49:38 - `cede7154-079d-47b6-bd61-dd96bcbe90b1.jsonl`
