---
id: ENH-2352
type: ENH
priority: P3
status: open
captured_at: '2026-06-27T21:58:52Z'
discovered_date: 2026-06-27
discovered_by: capture-issue
labels:
- captured
- audit-loop-run
- false-positive
---

# ENH-2352: `audit-loop-run` laundering check false-positives on the ENH-2005 sidecar pattern

## Summary

The sub-loop verdict-laundering check in `/ll:audit-loop-run` flags any state
where `on_success == on_failure` (or `on_yes == on_no`). This re-fires on the
**intentional** ENH-2005 artifact-channel sidecar pattern used by `rn-implement`
(`run_remediation`, `run_decomposition`) and similar recursive loops, producing
a false positive on every `rn-*` audit.

## Motivation

In the ENH-2005 pattern the collapse is by design: the child's real verdict is
read from `subloop_outcome_<ID>.txt` by a downstream classifier, and `on_error`
is deliberately split out to a distinct crash state (`record_sub_loop_crash`) so
an infrastructure crash is never laundered into a generic failure token. The
audit acknowledges the mitigation but flags it anyway (see
`rn-implement-audit-2026-06-27.md` "Sub-Loop Verdict Laundering Check"). A check
that cries wolf on a documented, correct pattern erodes trust in the audit and
buries genuine laundering.

## Current Behavior

The laundering check matches `on_success == on_failure` literally and flags the
state, regardless of whether the parent recovers the true verdict via an
artifact channel.

## Expected Behavior

Recognize the artifact-channel sidecar signature and suppress (or downgrade to
INFO with the mitigation noted). A state matches the safe pattern when **all**
hold:

1. `on_success`/`on_yes` and `on_failure`/`on_no` route to the same next state,
   AND that state (or its immediate successor) reads `subloop_outcome_<ID>.txt`
   (a per-issue outcome artifact under `run_dir`); AND
2. `on_error` routes to a **distinct** state (not the shared classifier) — i.e.
   a crash is attributed separately, not collapsed.

When both hold, do not raise a laundering finding (or mark it INFO/mitigated).
When `on_error` is *also* collapsed into the same target, keep flagging it —
that is the genuinely unsafe case.

## Proposed Solution

In the laundering-detection step of `audit-loop-run`:

- After detecting `on_success == on_failure`, inspect the shared target's action
  for a `subloop_outcome_` (or configurable outcome-artifact) read.
- Inspect `on_error` and confirm it differs from the shared target.
- Emit `mitigated` / suppress when both conditions pass; otherwise flag as today.

Anchor references: `rn-implement.yaml` `run_remediation`/`classify_remediation`
and `run_decomposition`/`classify_decomposition`; the ENH-2005 rationale is
documented inline in those states. Relates to BUG-2351 (sibling verdict-accuracy
fix in the same skill).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Suppression precedent**: `skills/confidence-check/SKILL.md` Phase 4.5 implements an identical shape — detect finding, apply a secondary structural test, suppress and log if matched. Follow that pattern: (1) detect `on_yes == on_no`, (2) inspect shared target's `action` for `subloop_outcome_` read and confirm `on_error` is distinct, (3) suppress/downgrade if both hold.
- **FSM JSON structure**: `scripts/little_loops/fsm/schema.py:StateConfig.from_dict()` normalizes `on_success`/`on_failure` YAML keys → `on_yes`/`on_no` during parse; `to_dict()` serializes only `on_yes`/`on_no`. The audit receives `on_yes`/`on_no` exclusively in the resolved JSON (via `ll-loop show <loop> --resolved --json` in Step 2). `on_error` IS preserved as-is.
- **Exact secondary-check algorithm**: After detecting `state.on_yes == state.on_no`, (1) look up the shared target state by name in the FSM JSON's `states` dict, (2) read its `action` field and test for `subloop_outcome_` as a substring, (3) check that `state.on_error` is non-null and not equal to the shared target. If all three pass → suppress/mitigated.
- **Three sidecar invocation sites exist** (not two): `rn-implement.yaml` `run_remediation` (on_error → `record_sub_loop_crash`) and `run_decomposition` (on_error → `record_sub_loop_crash`), plus `rn-refine.yaml` `refine_node` (on_error → `record_node_crash`, reads `node_outcome_<node_id>.txt`). The `rn-refine.yaml` variant is structurally safe but uses a different artifact prefix — out of scope for this issue per Scope Boundaries.
- **Counter-example to keep flagging**: `rn-build.yaml` `refine_seed` collapses `on_success`, `on_failure`, AND `on_error` into the same target — there is no distinct crash route and no artifact-channel read. This MUST continue to flag.
- **The ENH-2005 decision is canonical**: `.ll/decisions.yaml` line 1312 registers this pattern as the established convention; the audit false-positive directly contradicts a recorded decision.

## Scope Boundaries

**In scope:**
- Suppressing (or downgrading to INFO) the laundering warning when the ENH-2005 artifact-channel sidecar signature is detected: `on_success`/`on_yes` and `on_failure`/`on_no` share a next-state whose action reads `subloop_outcome_<ID>.txt`, AND `on_error` routes to a distinct crash state.
- Preserving the existing warning for all other same-target routing (the genuinely unsafe case, including `on_error` collapsed into the same target).

**Out of scope:**
- Modifying the ENH-2005 sidecar pattern itself in `rn-implement.yaml` or sibling loops.
- Changes to other audit-loop-run checks beyond the laundering-detection step.
- Generalizing to other artifact naming conventions beyond `subloop_outcome_` (can be a follow-on).
- User-visible output format changes beyond suppressing/downgrading the specific false-positive finding.

## Success Metrics

- `rn-implement` audits no longer raise a laundering warning for `run_remediation` and `run_decomposition` states.
- Loops that collapse `on_success == on_failure` without an artifact channel still produce the warning.
- No regression in detection of genuinely unsafe laundering patterns.

## Implementation Steps

1. Open `skills/audit-loop-run/SKILL.md` at **Step 8: Sub-Loop Verdict Laundering Check** (the "Laundering defect" paragraph). The exact text to extend: _"Laundering defect: `state.on_yes == state.on_no` (after any `${context.*}` interpolation). This means the parent loop treats child success and child failure identically — the child verdict is silently discarded."_
2. After detecting `on_yes == on_no`, add a conditional check for the ENH-2005 sidecar signature:
   - Inspect the shared target state's `action` for a `subloop_outcome_` read (e.g., `cat ".../subloop_outcome_<ID>.txt"`).
   - Confirm `on_error` routes to a **distinct** state (not the shared classifier target).
   - If both hold → emit `mitigated`/suppressed with a note; otherwise flag as before.
3. The sidecar pattern to match against is in `scripts/little_loops/loops/rn-implement.yaml`: `run_remediation` (on_success/on_failure → `classify_remediation`, on_error → `record_sub_loop_crash`) and `run_decomposition` (on_success/on_failure → `classify_decomposition`, on_error → `record_sub_loop_crash`). `classify_remediation`/`classify_decomposition` each contain `cat ".../subloop_outcome_<ID>.txt"`.
4. Add a new test fixture `scripts/tests/fixtures/fsm/assess-subloop-laundering-mitigated.yaml` that models the safe pattern (same-target on_yes/on_failure, distinct on_error, classifier state reading `subloop_outcome_`), and add a test in `scripts/tests/test_audit_loop_run_skill.py` (near lines 275–312) verifying the skill does NOT flag this fixture as a laundering defect.
5. Run existing tests: `python -m pytest scripts/tests/test_audit_loop_run_skill.py -v` to confirm no regressions.
6. Verify with a live audit of `rn-implement` that `run_remediation` and `run_decomposition` no longer produce the false positive.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. In `scripts/tests/test_audit_loop_run_skill.py`, add **4 test methods** (not the 1 implied by Step 4) in `TestAssessLoopSkill` near lines 278–315: `test_fixture_subloop_laundering_mitigated_validates`, `test_subloop_laundering_mitigated_has_distinct_on_error`, `test_subloop_laundering_mitigated_shared_target_reads_artifact`, and `test_subloop_laundering_mitigated_skill_does_not_flag` — all load `assess-subloop-laundering-mitigated.yaml` via `_load_fixture()` and follow the fixture-shape validator pattern of the existing four `test_subloop_laundering_*` tests
8. Note for follow-on: `skills/debug-loop-run/reference.md` has a parallel `BUG — Sub-loop verdict discarded` rule with the same trigger; ENH-2352 only fixes `audit-loop-run`, leaving a residual false positive in `debug-loop-run` — create a follow-on ENH if that signal path is exercised regularly

## Integration Map

### Files to Modify
- `skills/audit-loop-run/SKILL.md` — Step 8 "Sub-Loop Verdict Laundering Check", the "Laundering defect" paragraph; add ENH-2005 sidecar exemption condition after the equality check
- `scripts/tests/fixtures/fsm/assess-subloop-laundering-mitigated.yaml` — new fixture (does not yet exist) modelling the safe sidecar pattern for the test suite
- `scripts/tests/test_audit_loop_run_skill.py` — add test(s) near `test_subloop_laundering_*` (lines 278–312) asserting the skill does NOT flag the mitigated fixture

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/outer-loop-eval.yaml` — invokes `/ll:audit-loop-run` in `generate_report` and `refine_analysis` states; evaluates output via `llm_structured` checking `"None identified."` — suppressing the false positive changes the finding count but not the evaluator gate; no code change needed [Agent 1 finding]
- `scripts/tests/test_debug_loop_run_synthesis.py` — loads the same `assess-subloop-laundering.yaml` fixture (at lines 202, 210, 221, 233) for parallel `debug-loop-run` laundering tests; not modified by ENH-2352 but tracks the same fixture [Agent 2 finding]

### Reference Files (Read-Only — No Changes Needed)
- `scripts/little_loops/fsm/schema.py:StateConfig.from_dict()` — normalizes `on_success`/`on_failure` → `on_yes`/`on_no`; explains why the audit JSON always uses `on_yes`/`on_no` keys regardless of YAML source
- `scripts/little_loops/loops/rn-implement.yaml` — verify after fix: `run_remediation` (on_success/on_failure → `classify_remediation`, on_error → `record_sub_loop_crash`) and `run_decomposition` (on_success/on_failure → `classify_decomposition`, on_error → `record_sub_loop_crash`) should no longer produce a laundering flag

### Similar Patterns
- `scripts/little_loops/loops/rn-refine.yaml` — uses the sidecar pattern with `refine_node`/`classify_node` states and `on_error: record_node_crash`; reads `node_outcome_<node_id>.txt` (not `subloop_outcome_`) — a variant that would also false-positive if audited; out of scope per Scope Boundaries but worth noting
- `scripts/little_loops/loops/rn-remediate.yaml` — child loop that WRITES `subloop_outcome_<ID>.txt`; not the parent using the sidecar, but context for understanding the pattern
- `skills/confidence-check/SKILL.md` Phase 4.5 — suppression precedent: detects a structural pattern (mechanical fanout with verification chain), then suppresses a normally-flagged finding and logs `mechanical_fanout_suppressed: true`; follow the same secondary-structural-test + suppress shape
- `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` — the existing (genuinely unsafe) fixture; keep as-is to verify unsafe case still flags
- **Note**: `rn-plan.yaml` does NOT use the sidecar pattern (distinct `on_success`/`on_failure` targets); `rn-build.yaml`'s `refine_seed` collapses all three routes including `on_error` — that IS genuinely unsafe and should keep flagging
- `skills/debug-loop-run/reference.md` — defines an independent `BUG — Sub-loop verdict discarded` rule with the same trigger (`loop:` + `on_yes == on_no`); **residual gap**: after ENH-2352, `/ll:audit-loop-run` suppresses the rn-implement sidecar false positive but `/ll:debug-loop-run` will still flag it — a parallel fix in `debug-loop-run/reference.md` is a follow-on [Agent 2 finding]

### Tests
- `scripts/tests/test_audit_loop_run_skill.py` (lines 275–312) — existing laundering tests using the fixture below; extend or add alongside
- `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` — the fixture that exercises the unsafe (genuinely laundering) case; keep this fixture and its tests unchanged
- New fixture needed: `scripts/tests/fixtures/fsm/assess-subloop-laundering-mitigated.yaml` — models the ENH-2005 safe pattern (`on_success == on_failure` with `on_error` distinct and shared target reading `subloop_outcome_<ID>.txt`); skill should NOT flag it as a laundering defect
- `scripts/tests/fixtures/fsm/inner-eval.yaml` — existing dependency fixture referenced by `assess-subloop-laundering.yaml` for the `loop:` key; the new mitigated fixture should reference it too [Agent 3 finding]

_Wiring pass added by `/ll:wire-issue`:_
- **4 test methods to add** in `TestAssessLoopSkill` (Step 4 implies 1; wiring analysis identifies 4), following the `_load_fixture()` + fixture-shape-validator pattern from the existing `test_subloop_laundering_*` block:
  - `test_fixture_subloop_laundering_mitigated_validates` — `load_and_validate(FIXTURES_DIR / "assess-subloop-laundering-mitigated.yaml")` + `validate_fsm()`, assert no ERROR-severity results
  - `test_subloop_laundering_mitigated_has_distinct_on_error` — assert the sidecar state's `on_error` ≠ its `on_yes`/`on_no` shared target
  - `test_subloop_laundering_mitigated_shared_target_reads_artifact` — assert the shared target state's `action` contains `subloop_outcome_`
  - `test_subloop_laundering_mitigated_skill_does_not_flag` — assert `skills/audit-loop-run/SKILL.md` Step 8 prose contains the sidecar exemption condition (artifact-channel check + distinct `on_error` check)

### Documentation
- N/A — behavioral fix; no new docs needed

### Configuration
- N/A

## Impact

- **Priority**: P3 — Low-severity cosmetic issue, but fires on every recursive-loop audit and erodes signal-to-noise for the laundering finding.
- **Effort**: Small — additive condition check within a single detection branch; no protocol or FSM changes required.
- **Risk**: Low — the unsafe case (`on_error` also collapsed) continues to flag unchanged; only the specifically detected safe pattern is suppressed.
- **Breaking Change**: No

## Session Log
- `/ll:wire-issue` - 2026-06-27T22:27:58 - `df3795a0-4c42-418a-b848-17bf2aaaccc9.jsonl`
- `/ll:refine-issue` - 2026-06-27T22:13:25 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `/ll:format-issue` - 2026-06-27T22:07:01 - `6b0c656c-eeda-41cc-b69d-3c47161977e7.jsonl`
- `/ll:capture-issue` - 2026-06-27T21:58:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09e0f30a-d9cd-4afe-a20d-1b4ab9afdd5a.jsonl`

---

## Status

- **Status**: open
- **Created**: 2026-06-27
