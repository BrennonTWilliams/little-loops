---
id: BUG-3754
title: 'Confidence-check score contract drift: rn-remediate reads score polarity inverted,
  skill text states a stale 75 outcome threshold'
type: BUG
priority: P0
status: done
discovered_date: '2026-10-05'
verify_verdict: VALID
labels:
- confidence-check
- rn-remediate
- scoring
confidence_score: 95
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 25
size: Very Large
completed_at: '2026-10-06T06:49:39Z'
---

## Summary

**Decomposed; implementation proceeds through BUG-3756 and BUG-3757.** This parent remains `done` for the decomposition, not because either fix has shipped. The 2026-10-06 review below and the child issues replace the parent's earlier open scope choices; its previous research and confidence scores are historical context.

The confidence-check score contract is read two ways inside little-loops, and its documented outcome threshold is wrong.

**(1) Inverted polarity.** The rubric scores outcome criteria as points toward confidence: higher means better. Criterion A gives 1-2 change sites 12/12 breadth and a simple isolated change 25/25 (`skills/confidence-check/rubric.md`, Criterion A tables and worked examples). Criterion C gives "no ambiguity" 25. `preparation_policy.py` (around line 647) agrees: it treats the lowest of the scores as the worst dimension.

`rn-remediate.yaml` reads high as worse:
- Its band snapshot (line ~180) writes `ABOVE_MINIMAL` for `score_complexity >= diagnose_complexity_threshold` (15), and `gate_implement` then forces a refine+wire pass on those issues.
- Its diagnose step routes `score_ambiguity >= 15` to REFINE ("residual ambiguity") and `score_complexity >= 15` to WIRE/REFINE ("High complexity").
- `docs/guides/LOOPS_REFERENCE.md` (delta table, around line 659) documents `delta_complexity` and `delta_ambiguity` as "lower = improved".

So the complexity- and ambiguity-keyed remediation fires on the simple, well-specified end of the scale. Complex or ambiguous issues reach REFINE only through the separate confidence-floor and outcome-threshold branch.

**(2) Threshold drift.** `skills/confidence-check/SKILL.md` (around line 424) and `rubric.md` (around line 360) say `outcome_threshold` defaults to 75, so the unproven-mechanism hard cap is documented as 74. The real default is 65 (`config/automation.py` around line 160; `config-schema.json` `outcome_threshold` default 65), so the default cap is 64. Review also confirmed that `set-flags` falls back to 75 and ignores merged local overrides. BUG-3757 includes that runtime defect; the canonical gate stays at 65.

## Current Behavior

- `rn-remediate.yaml` treats a high `score_complexity` / `score_ambiguity` as the problem case: the `verify_scores_persisted` band snapshot writes `ABOVE_MINIMAL` at `>= diagnose_complexity_threshold` (15), `diagnose` routes `>= 15` to REFINE/WIRE, and `gate_implement` forces a refine+wire pass on that band.
- The rubric scores those same dimensions high = better (25/25 for a simple isolated change, 25 for no ambiguity), so remediation fires on the simple, well-specified issues and skips the complex, ambiguous ones (they reach REFINE only via the confidence-floor / outcome-threshold branch).
- `skills/confidence-check/SKILL.md` and `rubric.md` document `outcome_threshold` default 75 (cap 74); the real default is 65 (cap 64).

## Steps to Reproduce

1. Take an issue whose confidence-check scored `score_complexity: 25` (simple, isolated) and `score_ambiguity: 25` (no ambiguity), with confidence and outcome above their thresholds.
2. Run it through `rn-remediate` (`ll-loop run rn-remediate`); inspect `${context.run_dir}/complexity_band_<ID>.txt` written by `verify_scores_persisted`.
3. Observe `ABOVE_MINIMAL`, then `gate_implement` routing to the refine+wire pass; repeat with `score_complexity: 5` and observe the band is not `ABOVE_MINIMAL`.
4. Compare `grep -n "default" skills/confidence-check/rubric.md` (75) against `config-schema.json` `outcome_threshold` (65).

## Expected Behavior

- One polarity, high = better, stated once in `rubric.md` and followed by the band snapshot, `diagnose` routing, and the `LOOPS_REFERENCE.md` delta table (`delta_*` higher = improved).
- A low `score_complexity` / `score_ambiguity` (hard / ambiguous) takes the `ABOVE_MINIMAL` / REFINE path; 25 does not.
- `SKILL.md` and `rubric.md` state default 65 and cap 64, tied to `config-schema.json` by a test.

## Prior work this touches

- ENH-2163 (done) introduced the marker-gated refine+wire enforcement on the `ABOVE_MINIMAL` band, and BUG-2306 (done) closed its degenerate pre-implement gate. Both were written on the inverted reading. Fixing the polarity changes which issues that gate catches, so the gate's intent ("hard issues must be refined and wired before implement") should be re-checked against the corrected band, not just flipped mechanically.
- BUG-2007, ENH-2229 and BUG-2230 fixed other rn-remediate routing defects; none addressed polarity.

## Implementation Steps

**Historical plan, replaced by the child implementation steps.** BUG-3756 now defines score validation, minimum-score boundaries, inventory-based wiring and preserved routing order. BUG-3757 explicitly includes the runtime flag-threshold resolver and documentation. Do not reopen the old “decide scope” tasks below or implement this parent separately.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

1. One polarity (high = better) is stated once in `rubric.md` and every rn-remediate read agrees: band snapshot, `check_complexity_pre_implement`, `diagnose`, `gate_implement`, and the convergence deltas (`delta_*` positive = improved). Verified by behavioral tests that run the extracted shell with score 25 and score 5.
2. `score_change_surface` handling is decided against the same polarity (it is inverted the same way), or its exclusion is stated explicitly. Verified by a `diagnose` routing test.
3. Missing criterion scores have a stated, tested band (the `// 0` default no longer silently selects a band by accident).
4. The ENH-2163 intent ("hard issues must be refined and wired before implement") is re-checked against the corrected band; `TestDiagnoseAmbiguityWireDiscrimination`, `TestMarkerGate` and the delta/threshold pin tests are updated deliberately with the old values called out, not mechanically flipped.
5. `SKILL.md` and `rubric.md` state default 65 and cap 64, and a test ties the documented number to `config-schema.json` (resolved via `importlib.resources`). Host mirrors regenerate cleanly and the mirror gates pass.
6. `docs/guides/LOOPS_REFERENCE.md` rows (`:616`, `:641`, `:649-650`, `:659-660`) agree with the loop.
7. `python -m pytest scripts/tests/test_rn_remediate.py scripts/tests/test_confidence_check_skill.py scripts/tests/test_builtin_loops.py scripts/tests/test_preparation_policy.py -v` passes, then the full `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/guides/LOOPS_REFERENCE.md` rows `:651`, `:662`, `:728` as well as the already-listed `:616`, `:641`, `:649-650`, `:659-660` — `:662` also carries stale `total_delta ≤ 2` / `→ implement` wording
- Update `skills/confidence-check/rubric.md` — state polarity once, and keep it consistent with the `score_ambiguity ≤ 10` escalation branch at `:442-443`
- Keep `skills/confidence-check/SKILL.md:424` an in-place edit (file is 499/500 lines); put any new prose in `rubric.md`
- Regenerate mirrors with `ll-adapt --host <gemini|kimi-code|qwen> --apply` after the skill edits; `test_skill_mirrors_carry_companions` fails otherwise
- Update `scripts/little_loops/loops/rn-remediate.yaml` `emit_needs_manual_review` (`:1081`) "Complexity band" wording and the stale `outcome >= 75` comment at `:206`
- Preserve `# ll-lint: mr11-ok(context.X)` marker adjacency when editing `diagnose`, `verify_scores_persisted`, `check_complexity_pre_implement`, `gate_implement`; add `MR11_MARKER_ALLOWLIST` entries for any new `${context.*}` ref (`test_builtin_loops.py` `TestMr11MarkerSet`)
- Update `scripts/tests/test_rn_remediate.py` `TestDiagnoseAmbiguityWireDiscrimination` (both `ambiguity=18` cases and `_run` defaults), `test_context_has_diagnose_thresholds` if defaults change, and the `:661` docstring
- Add behavioral tests in `scripts/tests/test_rn_remediate.py` for `verify_scores_persisted`, `gate_implement`, `check_convergence` and `check_complexity_pre_implement`, following the `test_rn_implement.py` `check_learning_ready` `_run` pattern (`$$` → `$`, stubs on `PATH`)
- Add `test_documented_outcome_threshold_matches_schema` to `scripts/tests/test_confidence_check_skill.py` via `schema_default("commands.confidence_gate.outcome_threshold")`; avoid `scripts/tests/…` / `scripts/little_loops/…` citations in skill and doc text (`test_docs_audience_gate.py`)
- Decide `scripts/little_loops/cli/issues/set_flags.py` scope (`:34`, `:239`, `:243`, `:252`, `:255`, `:297`); if in, add a 65–74 boundary case to `scripts/tests/test_set_flags_cli.py` and a default-equals-schema assertion
- Decide `docs/reference/CLI.md:1844` (`70` vs actual 65) as a sibling stale default

## Impact

- **Priority**: P0 - the loop's complexity/ambiguity remediation is inverted for every issue it processes, so refine+wire effort goes to easy issues and hard ones skip the gate
- **Effort**: Medium - one YAML (band snapshot, `diagnose`, `gate_implement`), two skill docs, one reference table, plus tests; the ENH-2163 gate intent needs re-checking against the corrected band
- **Risk**: Medium - changes which issues take the refine+wire path in all `local-editable` projects immediately; covered by the existing rn-remediate suite plus new pins
- **Breaking Change**: No

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **Files to Modify**
  - `scripts/little_loops/loops/rn-remediate.yaml` — band snapshot, `check_complexity_pre_implement`, `diagnose`, `gate_implement`, `check_convergence` delta math; also the stale comment at `:206`
  - `skills/confidence-check/SKILL.md:424`, `skills/confidence-check/rubric.md:360-361` — default/cap text; `rubric.md` is also the place the polarity statement belongs
  - `docs/guides/LOOPS_REFERENCE.md:616`, `:641`, `:649-650`, `:659-660` — polarity wording
  - `.gemini/skills/confidence-check/`, `.kimi-code/skills/confidence-check/`, `.qwen/skills/confidence-check/` — host mirrors of both skill files; regenerate with `ll-adapt --host <gemini|kimi-code|qwen> --apply` rather than hand-editing
  - `scripts/little_loops/cli/issues/set_flags.py:34`, `docs/reference/CLI.md:1587` — stale 75, scope is a judgment call (see Root Cause)
- **Dependent Files (Callers/Importers)**
  - `rn-remediate` is invoked by `scripts/little_loops/loops/rn-implement.yaml` per dequeued issue; it passes `outcome_threshold` and `readiness_threshold` via `with:`. No other loop reads `ABOVE_MINIMAL` or `complexity_band_` — repo-wide hits are rn-remediate, its tests, docs and `.issues/` only.
  - `diagnose_complexity_threshold` / `diagnose_ambiguity_threshold` / `diagnose_change_surface_threshold` are overridable context keys; any caller or doc that overrides them with `-ge`-era values is affected by a polarity change. `test_builtin_loops.py:20011` allowlists the `mr11-ok` lint marker for `context.diagnose_complexity_threshold`.
- **Conventions in Force**
  - Rubric scores are points toward confidence (high = better) and every consumer outside rn-remediate reads them that way — evidence: `preparation_policy.py:646-648`, `rubric.md:442-443`, `skills/issue-size-review/SKILL.md:166`.
  - Documented-vs-configured defaults are tied by tests that resolve the schema through `importlib.resources`, so they work in editable and wheel installs — evidence: `test_wiring_skills_and_commands.py` (`CONFIG_SCHEMA_PATH`), `little_loops.init.core:schema_default`, `test_init_audit_fixes.py:295`. No existing test compares a number in `skills/**/*.md` or `docs/` to the schema; this fix introduces the first such tie.
  - Skill-text tests slice a section by heading and assert substrings with the issue ID in the failure message — evidence: `test_confidence_check_skill.py` `TestConfidenceCheckRubricOutcomeConfidenceCap._cap_section_text()` (slices the section holding the stale text).
  - Drift fixes land lockstep with the tests that pinned the old value — evidence: BUG-2768 updated the old `== 75` pins in `test_rn_remediate.py` and `test_rn_implement.py` when it changed the defaults.
  - `SKILL.md` files are capped at 500 lines and the mirror gates trip on `skills/` edits (see memory notes `reference_skill_line_limit_companion_pattern`, `reference_mirror_gates_after_skill_or_readme_edits`).
- **Tests**
  - Existing tests that pin the current inverted behavior and must be revisited, not merely kept green: `test_rn_remediate.py` `TestDiagnoseAmbiguityWireDiscrimination` (substitutes thresholds with `15`, runs `diagnose` with `AMBIGUITY=18`, asserts `WIRE`/`REFINE`; its `_run` defaults `complexity=0`), `TestMarkerGate` (`:707-713`, `:748`), the `DELTA_COMPLEXITY`/`DELTA_AMBIGUITY` assertions (`:893-894`), threshold-pin tests (`:964-965`, `:1137-1138`).
  - No test executes `verify_scores_persisted` or `gate_implement` in bash today; the band is pinned by substring only. The only precedent for rendering a whole state action is `test_rn_implement.py` (~`:1395-1415`): replace `${context.*}`, unescape `$$` → `$`, stub binaries on `PATH`, run `bash -c` in `tmp_path`. `verify_scores_persisted` calls `ll-issues path` and `ll-issues show --json`, so a behavioral band test needs those stubbed.
  - `test_preparation_policy.py` / `test_preparation_policy_parity.py` already use high = better fixtures (`score_ambiguity=20, score_complexity=5`) and should stay green unchanged.
  - `test_confidence_check_skill.py` asserts the cap text mentions `outcome_threshold` but not the number (`:197-228`, `:794-795`).
- **Documentation**
  - `docs/guides/LOOPS_REFERENCE.md` (rows above); `docs/reference/CONFIGURATION.md:437` and `docs/reference/CLI.md` already state default 65 / the 85+75 pair respectively.
- **Configuration**
  - `scripts/little_loops/config-schema.json:534-539` (`outcome_threshold` default 65), `scripts/little_loops/config/automation.py:160,169`, `.ll/ll-config.json:62`.
  - BUG-2768's decision record (`.ll/decisions.d/a978652a-a263-42cc-80e8-1050a568b333.json`) chose to delete confidence-threshold literals from the rn-* loops and rejected keeping rn-implement/rn-remediate at 75 as a deviation; the loop reads thresholds from `commands.confidence_gate`, so the 65 default in the schema is what the loop sees at runtime.

### Files to Modify (wiring)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/confidence-check/rubric.md` — second site beyond `:360-361`: the escalation branch near `:442-443` already reads `score_ambiguity ≤ 10` as high = better; the new polarity statement must be consistent with it [Agent 1 finding]
- `docs/guides/LOOPS_REFERENCE.md:651` — `DECOMPOSE` trigger row (`change_surface ≥ 15`) in `rn-remediate` section; polarity-dependent, missing from the issue's row list [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md:662` — "Convergence rules" prose in `rn-remediate` section; states `total_delta ≤ 2` and `CONVERGED_PASS → implement` but the loop uses `TOTAL_DELTA -le 0` (ENH-2061) and routes via `gate_implement`, so fix alongside the delta table [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md:728` — `gate_implement` marker-gate paragraph (ENH-2163): states `score_complexity ≥ diagnose_complexity_threshold, default 15`; the main prose statement of the `ABOVE_MINIMAL` band [Agent 2 finding]
- `scripts/little_loops/cli/issues/set_flags.py:243` — docstring of `_resolve_outcome_threshold` says "defaulting to 75"; `:252`, `:255` are its fallbacks, `:297` in `apply_flags_from_notes` branches on `threshold == _DEFAULT_OUTCOME_THRESHOLD`. If the 75 → 65 change is taken, all four move together with `:34` and `:239` [Agent 2 finding]
- `docs/reference/CLI.md:1844` — `next-action --outcome-threshold` default documented as `70`; argparse default in `cli/issues/__init__.py` is 65. Third stale value, not 75 [Agent 2 finding]
- `scripts/little_loops/loops/rn-remediate.yaml` — `emit_needs_manual_review` heredoc (`:1081`) prints `Complexity band: {complexity} (ambiguity=…)` from the raw score; relabel or re-word under the corrected polarity (no test asserts on the output) [Agent 2 finding]

### Dependent Files (Callers/Importers) (wiring)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-implement.yaml` — report/summary state embeds `pre_scores_/post_scores_/convergence_<ID>.json` verbatim into `summary.json` `per_issue[*]` without reading delta fields; the delta sign flip surfaces only as different numbers in that sidecar [Agent 2 finding]
- `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` — holds the oracle states `verify_scores_persisted` / `verify_scores_persisted_final` (referenced from `rn-remediate.yaml`, `autodev.yaml`, `refine-to-ready-issue.yaml`); checks persistence only, not polarity, so no change [Agent 1 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — comment near `:1018` ("0/25 ambiguity") already assumes high = better; no change [Agent 2 finding]
- `skills/issue-size-review/SKILL.md` (Phase 5 qualitative-skip guard) and `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:394-397`, `:410` — duplicates of the already-known high = better consumers (`score_ambiguity ≥ 18`, `≤ 10`/`> 10`); reference only, no change [Agent 1/2 finding]
- No other loop, command, agent or hook reads `score_complexity` / `score_ambiguity` / `score_change_surface`, `ABOVE_MINIMAL`, `complexity_band_`, `delta_*` or any `diagnose_*_threshold` override (repo-wide searches excluding `.issues/`, `CHANGELOG.md`, `thoughts/`); `rn-implement.yaml` passes only `issue_id`, `readiness_threshold`, `outcome_threshold`, `max_remediation_passes` [Agent 1/2 finding]

### Tests (wiring)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `MR11_MARKER_ALLOWLIST` (~`:20009-20018`) and `TestMr11MarkerSet::test_marker_set_matches_enumeration` compare `(file, var, issue)` tuples; `TestValidatorWarningBudget` fails on any new `unsafe-context-interp` / `stale-mr11-marker` warning. Keep each `# ll-lint: mr11-ok(context.X)` marker on or directly above its `${context.X}` line when reordering the `diagnose` elif chain (`:383-401`), and add an allowlist entry for any new `${context.*}` ref [Agent 2/3 finding]
- `scripts/tests/test_rn_remediate.py` `TestDiagnoseAmbiguityWireDiscrimination::test_ambiguity_high_change_surface_zero_routes_to_wire` and `::test_ambiguity_high_change_surface_nonzero_routes_to_refine` — fail without input changes (`ambiguity=18` becomes the good end; `_run` defaults `complexity=0`/`change_surface=0` become the worst end); redesign inputs and expected tokens, do not just flip [Agent 3 finding]
- `scripts/tests/test_rn_remediate.py` `TestDiagnoseAmbiguityWireDiscrimination._routing_script` — slices from the literal `# Priority-ordered routing` and string-replaces the four `${context.diagnose_*}` tokens; keep that comment and token form or the helper breaks for the wrong reason [Agent 2/3 finding]
- `scripts/tests/test_rn_remediate.py` `TestBug2007Fixes::test_diagnose_routing_has_no_bare_magic_literals` — forbids literal `-ge 15` / `-lt 50` in `diagnose`; flipped branches must keep using `${context.diagnose_*}` refs. `::test_diagnose_uses_context_thresholds_not_literals` requires all four refs [Agent 2/3 finding]
- `scripts/tests/test_rn_remediate.py` `TestTopLevelDeclarations::test_context_has_diagnose_thresholds` — pins ctx defaults 15/15/15 and `diagnose_confidence_floor == 50`; update only if default semantics change [Agent 2/3 finding]
- `scripts/tests/test_rn_remediate.py` `TestDiagnoseRouting::test_diagnose_catch_all_outputs_refine_light` — asserts `REFINE_LIGHT` follows the first `DECOMPOSE` in the action text; branch reordering must preserve that [Agent 2 finding]
- `scripts/tests/test_rn_remediate.py` `TestReassessAndConvergence::test_check_convergence_computes_total_delta` — name-presence only; passes with the wrong delta sign, so the new `check_convergence` behavioral test is what pins the fix [Agent 3 finding]
- `scripts/tests/test_rn_remediate.py` `test_check_complexity_pre_implement_on_yes_routes_to_wire_check` — docstring (`:661`) says "outcome >= 75"; stale prose only [Agent 3 finding]
- `scripts/tests/test_wiring_skills_and_commands.py::test_skill_mirrors_carry_companions` — parametrized over `.qwen`, `.kimi-code`, `.gemini`, `.omp`; requires mirror `rubric.md` / `reference.md` byte-identical to `skills/confidence-check/`. Editing source `rubric.md` fails it until `ll-adapt --host <h> --apply` is run. Mirror `SKILL.md` (e.g. `.gemini/skills/confidence-check/SKILL.md:423`) is not byte-compared and is regenerated by the same command [Agent 2/3 finding]
- `scripts/tests/test_enh494_skill_companions.py::TestSkillLineLimit::test_all_skills_within_limit` — `skills/confidence-check/SKILL.md` is 499 lines (cap 500); the `:424` fix must be an in-place edit with no net added line, put new polarity prose in `rubric.md` [Agent 2/3 finding]
- `scripts/tests/test_docs_audience_gate.py` — scans `docs/guides`, `docs/reference`, `README.md`, `skills/**/*.md`; new text must not cite `scripts/tests/…` or `scripts/little_loops/…` (use `little_loops.<module>` dotted names) [Agent 2/3 finding]
- `scripts/tests/test_set_flags_cli.py` — only dedicated `set_flags` test file; no reference to `_DEFAULT_OUTCOME_THRESHOLD` and fixtures use `outcome_confidence` 50/59/90, so a 75 → 65 change flips none of them. Add a boundary case (e.g. `outcome_confidence=70`) [Agent 3 finding]
- `scripts/tests/test_confidence_check_skill.py` `TestFlagRules` (~`:155-190`) imports `FLAG_RULES`; also `TestPhase45OutcomeThreshold` (outcome_threshold must appear in Phase 4.5) and the Phase 2b cap-text test (~`:794`, cap text must contain `outcome_threshold` and "cap"/"penalty") constrain the SKILL.md/rubric.md wording [Agent 2/3 finding]
- `scripts/tests/test_issue_size_review_skill.py` `test_guard_reads_score_complexity`, `test_guard_uses_18_point_threshold` — separate high = better consumer; no change, listed so it is not "fixed" by mistake [Agent 1/3 finding]
- **New tests (gaps):** (1) behavioral `verify_scores_persisted` band test — render the action, `.replace("$$", "$")`, stub `ll-issues path` / `show --json` on `PATH` (action also greps the issue file for `confidence_score:` and `outcome_confidence:`), assert `complexity_band_<ID>.txt` is `ABOVE_MINIMAL` for 5 and `MINIMAL` for 25; (2) behavioral `gate_implement` test over band file (absent / `MINIMAL` / `ABOVE_MINIMAL`) × `refined_`/`wired_` markers → `IMPLEMENT` / `NEED_REFINE` / `NEED_WIRE`; (3) behavioral `check_convergence` test seeding `pre_scores_<ID>.json` / `post_scores_<ID>.json`, asserting `delta_complexity`, `delta_ambiguity`, `total_delta` in `convergence_<ID>.json`; (4) `check_complexity_pre_implement` exit-code test (both routes go to `check_wire_pre_implement`, only exit code observable); (5) `test_documented_outcome_threshold_matches_schema` using `little_loops.init.core.schema_default("commands.confidence_gate.outcome_threshold")` plus section slices from `test_confidence_check_skill.py` `_cap_section_text`; (6) `_DEFAULT_OUTCOME_THRESHOLD == schema_default(...)` if `set_flags.py` is brought into scope [Agent 3 finding]
- **Test helper patterns:** `scripts/tests/test_rn_implement.py` `check_learning_ready` `_run` (~`:1383-1415`) for the `$$` → `$` unescape + stub on `PATH`; `scripts/tests/test_spike_verdict_routing.py` `_stub_path` / `_run` and `test_route_spike_verdict_classification` for a parametrized `show --json` → token table; `scripts/tests/test_advise_ready_gate.py` `_Stub` for an `ll-issues` stub with a call log (its `re.sub` raises `KeyError` on `$${…}` escapes, so use `.replace` instead); `scripts/tests/test_config_schema.py:16` `CONFIG_SCHEMA = importlib.resources.files("little_loops").joinpath("config-schema.json")` [Agent 3 finding]

### Documentation (wiring)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` `rn-remediate` section, rows `:651`, `:662`, `:728` — see Files to Modify (wiring) above [Agent 2 finding]
- `docs/reference/CLI.md:1844` — `next-action --outcome-threshold` default `70` vs actual 65 [Agent 2 finding]
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` `rn-remediate` section (~`:200-222`) and `scripts/little_loops/loops/README.md:66` mention `rn-remediate` with no polarity text; no change [Agent 2 finding]
- `CHANGELOG.md` — newest section is `## [1.166.0] - 2026-09-27`; per project convention, no `[Unreleased]` entry — promote during release prep [Agent 2 finding]
- `docs/guides/POLICY_ROUTER_GUIDE.md:4,73`, `docs/reference/CLI.md:1587`, `scripts/little_loops/loops/lib/policy-router.yaml:184` — `outcome >= 75` is rule-syntax example text, not a default claim; `CLI.md:1587` stays a judgment call per Root Cause [Agent 1/2 finding]

### Configuration (wiring)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json:534-540`, `scripts/little_loops/config/automation.py` `ConfidenceGateConfig`, `scripts/little_loops/fsm/context_seed.py` `seed_confidence_thresholds`, `.ll/ll-config.json:62`, `scripts/little_loops/init/core.py` `schema_default` — all already 65; no change, `schema_default` is the helper for the new tie test [Agent 1/2 finding]
- `.claude/worktrees/bug-3755/` holds a full second copy of the repo (stale 75 text, mirrors, `.issues`); repo-wide greps return it, it is not a gate-scan path and must not be edited as part of this fix [Agent 2 finding]
- `.opencode`, `.codex`, `.agents` mirror dirs were not searched by Agent 1; `test_skill_mirrors_carry_companions` covers `.qwen`/`.kimi-code`/`.gemini`/`.omp` only. Confirm with `ll-adapt` output after regeneration [Agent 1/3 finding]

## Program Design

### Types

- `diagnose_complexity_threshold: int` — rn-remediate context key (default 15), reinterpreted as a floor where scores below it are the hard band
- `outcome_threshold: int` — default 65, documented default must match `config-schema.json`

### Signatures

- `test_complexity_band_polarity(score_complexity: int, expected_band: str) -> None` — new test in `scripts/tests/test_rn_remediate.py` pinning 25 → not `ABOVE_MINIMAL`, 5 → `ABOVE_MINIMAL`
- `test_documented_outcome_threshold_matches_schema() -> None` — new test in `scripts/tests/test_confidence_check_skill.py` tying SKILL.md / rubric.md default to the schema

### Call Path

`snapshot_issue` -> `decide` (preparation_policy, polarity already high = better) vs `rn-remediate` states `verify_scores_persisted` -> `diagnose` -> `gate_implement` (to be aligned)

## Acceptance Criteria

Acceptance: (a) one documented polarity, high = better, stated once in the rubric and followed by rn-remediate's band snapshot, its diagnose routing and the LOOPS_REFERENCE delta table; a test pins it (for example, in test_rn_remediate.py, a score_complexity of 25 issue does not take the ABOVE_MINIMAL path, and a score of 5 does). (b) SKILL.md and rubric.md state default 65 and cap 64, and a test or lint check ties the documented default to config-schema.json. (c) The existing rn-remediate and confidence-check suites pass.

Verified against main 4c6be4c26 on 2026-10-05.

## Status

**Done (decomposed)** | Created: 2026-10-05 | Priority: P0 | Fixes remain open in BUG-3756 and BUG-3757

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-06_

Historical assessment of the unsplit parent. The child review resolves its scope questions; these 95/63 scores are not new assessments of the revised children.

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Concerns
- Several scope decisions are left open for the implementer: how a missing criterion score (`// 0`) maps to a band under corrected polarity, whether `score_change_surface` is flipped in this fix, and whether `set_flags.py` (`_DEFAULT_OUTCOME_THRESHOLD = 75`) and `CLI.md:1844` are in scope.
- `SKILL.md` is 499/500 lines, so the `:424` default/cap fix must be an in-place edit with no net added line; new prose goes in `rubric.md`.

### Outcome Risk Factors
- Moderate per-site complexity: the polarity flip spans several `rn-remediate` states that share state through band and score files (`verify_scores_persisted`, `diagnose`, `gate_implement`, `check_convergence`), and the ENH-2163 gate intent must be re-checked rather than mechanically flipped.
- Broad enumeration across ~10 sites (YAML, two skill files, host mirrors, `LOOPS_REFERENCE.md` rows, tests), and no existing test runs `verify_scores_persisted` or `gate_implement` in bash, so the behavioral tests must be written from scratch.
- Open design decisions (missing-score band, `score_change_surface` scope, `set_flags.py` scope) carry the ambiguity penalty; settling them via `/ll:decide-issue` would raise outcome confidence.


## Session Log
- `/ll:issue-size-review` - 2026-10-06T06:49:39 - `cede7154-079d-47b6-bd61-dd96bcbe90b1.jsonl`
- `/ll:confidence-check` - 2026-10-06T06:47:46 - `586b4dff-46f5-4091-8248-f1ef355743c9.jsonl`
- `/ll:verify-issues` - 2026-10-06T06:46:04 - `cfa49509-cace-4a06-bbf2-798faf3ea26a.jsonl`
- `/ll:wire-issue` - 2026-10-06T06:44:11 - `e586ce31-b6f7-4e11-b7b0-8dfc5eb050eb.jsonl`
- `/ll:refine-issue` - 2026-10-06T06:32:19 - `36b5fcae-efac-4a64-867a-1aa8c8364275.jsonl`
- `/ll:format-issue` - 2026-10-06T06:24:58 - `1ee33109-df36-4bca-a06f-a5d8efc7650f.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **Loop path**: the loop file is `scripts/little_loops/loops/rn-remediate.yaml` (the issue text cites it by bare name). Every polarity-sensitive read sits in this one file: `verify_scores_persisted` band snapshot (`:179-184`), `check_complexity_pre_implement` (`:213-215`), `diagnose` (`:365-366`, branches `:384`, `:388`, `:392`, `:399`), `gate_implement` band read (`:438-439`), and `check_convergence` deltas (`:788-804`).
- **The inversion is wider than the issue states.** Three further sites carry the same wrong reading:
  - `check_convergence` computes `DELTA_COMPLEXITY=$((PRE_COMPLEXITY - POST_COMPLEXITY))` and `DELTA_AMBIGUITY` the same way, under a comment saying "improvement means score went DOWN, so invert delta" (`:799-801`). Under the rubric's high = better polarity a refine pass that *raises* those scores is an improvement and currently subtracts from `TOTAL_DELTA` (`:804`). That sum drives the `TOTAL_DELTA -le 0` stall branch (`:834`), so remediation can be declared stalled on passes that helped.
  - `score_change_surface` is read the same inverted way. Rubric Criterion D scores 0-2 callers as 25 and 11+ callers as 0 (`rubric.md` Criterion D, Pattern A). The loop treats `CHANGE_SURFACE -eq 0` as "no integration map exists" (`:385`, `:393`, `check_wire_pre_implement` `:225`) and `>= diagnose_change_surface_threshold` (15) as "surface area too large" → DECOMPOSE (`:401`). Under the rubric, 0 is the widest blast radius and 25 the narrowest, so DECOMPOSE fires on isolated changes. The issue's scope lists complexity and ambiguity only.
  - `docs/guides/LOOPS_REFERENCE.md:616` ("complexity↓, ambiguity↓"), `:641`, `:649-650` (`ambiguity ≥ 15`, `complexity ≥ 15` trigger rows), `:659-660` (delta rows) all state the inverted reading, not only the delta table.
- **Missing-score default flips meaning.** Every read uses `jq -r '.score_X // 0'` (`:179`, `:213`, `:365-367`, `:788-794`) and `snapshot_issue` uses `_opt_int(...) or 0` (`preparation_policy.py:840-843`). Under the current reading an absent score reads as 0 = low complexity = `MINIMAL`; under the corrected reading 0 is the worst score and an unscored issue would land in `ABOVE_MINIMAL`/REFINE. `verify_scores_persisted` only requires `confidence_score` and `outcome_confidence` to be present (`:166-172`), not the criterion scores, so unscored-issue behavior is a decision the fix must make knowingly.
- **Polarity is implied, never stated.** `rubric.md` has no sentence declaring direction; it is carried only by the score tables. The other consumers already follow high = better: `preparation_policy.py:646-648` (`amb < min(others)` picks spike), `rubric.md:442-443` and `skills/issue-workflow/SKILL.md:84-85` (`score_ambiguity ≤ 10` = unresolved options), `skills/issue-size-review/SKILL.md:166` and `docs/reference/COMMANDS.md:407` (`≥ 18` = well-specified, skip decomposition). rn-remediate and the LOOPS_REFERENCE rows are the outliers.
- **Stale 75 is wider than two files.** Beyond `SKILL.md:424` and `rubric.md:360-361`: `scripts/little_loops/cli/issues/set_flags.py:34` (`_DEFAULT_OUTCOME_THRESHOLD = 75`, feeds `FLAG_RULES` at `:239` and the `_resolve_outcome_threshold` fallback); comments at `rn-remediate.yaml:206` and `test_rn_remediate.py:661`; `docs/reference/CLI.md:1587`; and the `.gemini/`, `.kimi-code/`, `.qwen/` copies of both skill files. `policy-router.yaml:184` and `POLICY_ROUTER_GUIDE.md:4,73` use `outcome >= 75` as rule-syntax examples and are not default claims. Whether `set_flags.py`'s 75 is in scope is a judgment call; it is a code default, not documentation, and the issue says the 65 gate stays where it is.

---

## Resolution

- **Status**: done
- **Closed**: 2026-10-06
- **Resolution**: Decomposed; runtime fixes not yet implemented
- **Decomposed into**: BUG-3756, BUG-3757

Work for BUG-3754 is now carried by its child issues; this parent was closed by rn-decompose.

## Pre-Implementation Review

Reviewed on 2026-10-06 against the working tree, with `/ll:advise --signal user_requested --host claude-code --model opus` (advisor confidence 0.75).

- **BUG-3756:** keep threshold defaults at 15 and define deficiency as `< minimum acceptable score`; equality is acceptable. Validate aggregate and consumed criterion scores at both snapshots; missing/null/invalid scores terminate as `SCORES_MISSING`, while zero is valid. Include the overlooked `check_wire_needed_outcome` state. Use existing `integration_files` independently of Criterion D, and skip repeat inventory-only wiring after a wired marker. Preserve the initial band and four-term convergence sum; correct A/C delta signs only.
- **Routing scope:** direct DECOMPOSE/REFINE_LIGHT rules are dormant on normal diagnosis entry. Do not make them reachable by reordering this bugfix: Criterion D also measures mechanical-fanout verifiability, so a low value can need enumeration rather than decomposition. Keep budget-based escalation; separate pattern-aware routing can be reviewed later. Opus dissented that a mirrored ≤10 cutoff might better preserve intent; the explicit decision here is to retain configurable minimum 15.
- **BUG-3757:** include the default-75 flag evaluator and its bypass of loaded/local configuration. Use the existing effective configuration, document default 65 / relative cap 64, correct next-action's documented 70, and preserve custom policy examples using 75. Preserve set-only flags. Retain P2 because the runtime drift affects omitted keys/local overrides rather than every configured project.
- **Implementation readiness:** child files now include reproduction steps, concrete program design, integration maps, resolved scope boundaries and behavioral acceptance tests. Coordinate shared rubric/YAML edits and ENH-3742; no hard dependency is needed. Document reversed custom-threshold semantics and use fresh run directories rather than pre-fix sidecars.
- **Evidence:** the pre-change rn-remediate, confidence-check and set-flags suites passed (287 tests), while extracted actions reproduced A=5 → `MINIMAL` and D=0 with a positive inventory → `WIRE`. Temporary configs reproduced gate/flag disagreement both for an omitted key (65/75) and a local override (75/65). Passing baseline tests do not cover these defects.

No runtime code, skill or loop implementation was changed during this review.
