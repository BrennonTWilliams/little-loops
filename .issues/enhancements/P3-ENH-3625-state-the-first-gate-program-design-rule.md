---
id: ENH-3625
type: ENH
title: State the first-gate Program Design rule
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T01:48:55Z'
completed_at: '2026-09-27T04:10:16Z'
parent: EPIC-3565
relates_to:
- ENH-3621
blocks:
- ENH-3623
confidence_score: 90
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3625: State the first-gate Program Design rule

## Summary

Decide the Program Design rule for autodev's first post-refine gate, and write it down.
Today the first gate (`check_passed`) ignores the Program Design verdict, while every
later gate in the ladder hard-ANDs it. The ENH-3621 spike found this asymmetry as quirk
Q3 (report `thoughts/spikes/preparation-policy-spike.md`, § "H2 — first gate skips
check-design" and § Quirks). No comment, doc or test states it as a rule. The static trace
below (see "Trace Evidence") shows an inner `done` can leave `check-design` failing, so
this issue **chooses option A** (see "Decision"). ENH-3623's `decide()` encodes the same rule.

## Current Behavior

- `check_passed` (`scripts/little_loops/loops/autodev.yaml`, state at `:726`) runs only
  `ll-issues check-readiness … --honor-waiver`. It does not run `ll-issues
  check-design`. `on_yes` goes on toward implementation.
- `recheck_scores` (`:1890`), `regate_after_atomic_remediation` (`:2277`) and
  `recheck_after_size_review` (`:2589`) each run `ll-issues check-design` and require it
  to pass, together with the readiness/outcome gate.
- As a result, an issue whose scores pass right after the inner `refine-to-ready-issue`
  run is implemented even when its Program Design gate fails. An issue that goes through
  any second-pass remedy cannot pass with a failing design gate. The spike pinned this
  with a differential scenario (`h2_first_gate_skips_design`,
  `test_h2_first_gate_ignores_design_and_files_no_marker`). These names exist only in the
  spike report. They are not in the repo's test suite; this issue adds the scenario.
- The inner loop has a tier-1 `DESIGN` obligation (`refine-to-ready-issue.yaml`,
  `select_obligation` → `DESIGN: check_gate_refine_limit`, BUG-3551), so an inner `done`
  normally implies the design gate was handled. The inner loop also has a selector call
  that skips `DESIGN` (`--skip … DESIGN …`), and the refine budget is shared. Whether an
  inner `done` *guarantees* a passing design gate has not been shown.

## Expected Behavior

One stated rule, applied the same way in the YAML and the run-record `ready` predicate
(this issue), and in `decide()` (ENH-3623):

- **Rule (option A): the first gate runs check-design too.** `check_passed` hard-ANDs
  `ll-issues check-design`, the same as the later gates. A design failure goes to the
  second-pass ladder (design remedy, then `design_gate_failed`), not to implementation.

### Decision (2026-09-27 review)

Option A is chosen now, without waiting for a probe. A is safe whatever a probe would
find. If an inner `done` did guarantee a passing design gate, the added `check-design`
is a fast no-op, and it passes automatically (exit 0) on projects without
`.ll/program-design-cutover.json`. A probe would only matter to justify the rejected
alternative. The static trace already shows a real exposure (edits after the pre-score
DESIGN check reach `done`). The h2-shaped characterization scenario, a real FSM run of
autodev, is the confirmation.

Rejected alternative (option B): keep `check_passed` readiness-only and make the inner
loop's tier-1 DESIGN obligation own the gate on the first pass. Rejected because the
trace shows the inner loop does not re-check DESIGN after scoring.

## Motivation

The spike could only keep parity with the asymmetry. It could not say whether the
asymmetry is intended. `decide()` makes the rule explicit in one table row, so the
choice should be made on purpose before the port, not inherited.

## Proposed Solution

1. **Rule A is decided** (see "Decision"). The static trace in "Trace Evidence" is the
   rationale; no separate probe gates the choice.
2. Change `check_passed` to mirror `recheck_scores` (`autodev.yaml:1904-1911`) exactly:
   `ID="${captured.input.output}"` with the same `mr11-ok(captured.input.output) ENH-3358`
   marker, then `ll-issues check-readiness "$ID" … --honor-waiver && ll-issues
   check-design "$ID" && echo "$ID" >> …/autodev-staged.txt`.
   **Exit codes:** `check-design` returns 0 (pass or not armed), 1 (gate fails) or 2
   (issue ID not resolved). It never returns 3, so it cannot collide with the
   `harness_exit` abstain code (exit 3 = scores absent). Exit 2 maps to `error` →
   `check_passed.on_error` → `detect_children`, the same route `check-readiness` exit 2
   takes today. Accepted; pin it.
   **A's routing is traced (2026-09-27 review) and needs no retarget.** `check_passed.on_no`
   → `select_obligation_post_refine`, whose `next-obligation` call skips `DESIGN` and
   prints `NONE` once scores pass → `_: check_missing_artifacts`:
   - `on_yes` → `run_wire` → rescore → `recheck_scores`, which ANDs `check-design`;
   - `on_no` → `detect_children` → `run_size_review` → `recheck_after_size_review`,
     which owns the design remedy and the `design_gate_failed` deferral.

   The cost is that a design-only first-gate failure runs size-review before the design
   remedy. That matches what `recheck_scores` already does on a design failure, so it is
   accepted, not new. The h2-shaped characterization scenario confirms this route on a
   real FSM run.
3. **Post-ENH-3623 placement.** `check_passed` survives ENH-3623 as autodev's gate after
   the wrapper returns READY. The rule must hold in three places: that gate, the
   run-record `ready` predicate (both in this issue), and the `decide()` row after a
   `RUN_CHILD` done fact. The `decide()` row belongs to ENH-3623 (its AC at `:521`),
   because `decide()` does not exist until then. ENH-3623 extends this issue's two-way
   parity test to three.
4. Record the rule:
   - a comment on `check_passed` stating the rule. Rewrite the whole comment block
     (`autodev.yaml:727-733`), which is stale in two places. It says
     `breakdown_issue → done` reaches this state, but that exit writes `DECOMPOSED` and
     routes to `detect_children`. It also ends with the dangling fragment "and routes to
     implement_current to interleave implementation.", but `on_yes` now goes to
     `select_obligation_pre_implement`;
   - a line in `docs/guides/LOOPS_REFERENCE.md` (autodev section). It also states that
     `recursive-refine.yaml`'s `check_passed` does not apply the rule: a known gap, out
     of scope here;
   - a structural test pinning the gate shape.
5. **`recursive-refine.yaml`:** not changed here. Capture a follow-up issue for its
   `check_passed` (and the recheck copy) if the same rule should apply there.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/autodev.yaml`: `check_passed` (gate change and rewritten
  comment)
- `docs/guides/LOOPS_REFERENCE.md`: state the rule
- `scripts/little_loops/cli/issues/run_record.py` `cmd_run_record_write` gains the
  design check for the `ready` predicate (`check_format_gaps` + `design_gate_failed`
  from `issue_parser.py`) and updates its docstring (:271, "autodev `check_passed`'s
  exact one"). `scripts/little_loops/run_record.py` updates the predicate's
  documentation (:28, :205)

**Behavior change (record tokens).** The run-record `ready` predicate is shared
by every writer, including `refine-to-ready-issue`. A child `done` record whose design
gate fails becomes `BLOCKED`, not `READY`. autodev's `route_refine_success` sends
`READY`, `BLOCKED` and `MISSING` all to `check_passed`, so routing does not change. The
only readers of run records are autodev's `route_refine_success` (:691) and
`route_refine_outcome` (:526); a `done` record reaches only the first. Pin the new token
in `test_run_record.py`, not the characterization suite: the existing
`design_gate_failed` scenario's `Expected.records` holds the final record
(`DEFERRED:gate_unmet`), not the child's `done` record, so the `READY`→`BLOCKED` change
may not be visible there. List it as an accepted change.

### Behavior Parity

`scripts/little_loops/loops/autodev.yaml`: the `check_passed` change is additive (one `&& ll-issues check-design` clause). Preserved: readiness/`--honor-waiver` semantics, `on_yes`/`on_no`/`on_error` edges, staging append, MR-11 marker triple. Changed (accepted): a design-failing issue with READY scores now goes `on_no` → `select_obligation_post_refine` → size-review → design remedy instead of implementation; a child `done` record with a failing design gate becomes `BLOCKED` (not `READY`) — routing unchanged since `route_refine_success` sends both to `check_passed`.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` `select_obligation_pre_implement` (~:943) ends with `next-obligation` passing `--skip … DESIGN`, and `select_obligation_post_refine` (~:803) has the same skip list. Neither can catch a design failure at the first gate, so they do not backstop `check_passed` [Agent 2+4 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `route_pre_score_obligation` (DESIGN → `check_gate_refine_limit`, BUG-3551) and `route_score_obligation` (`--skip … DESIGN`, ~:825) are the two inner selector calls the trace turns on [Agent 1+4 finding]
- `scripts/little_loops/loops/recursive-refine.yaml` `check_passed` (~:256, recheck copy ~:502 "Mirrors check_passed logic exactly") has no `check-design` either; out of scope. **Decided:** the LOOPS_REFERENCE line names it as a known gap; a follow-up issue covers it if wanted [Agent 1 finding]
- `scripts/little_loops/cli/issues/check_design.py:19` (`cmd_check_design`), dispatched at `cli/issues/__init__.py:1096`; `cli/issues/next_obligation.py` `_tier1_probe()` is the tier-1 `DESIGN` branch [Agent 1+4 finding]
- `scripts/little_loops/run_record.py` (:28, :205) and `cli/issues/run_record.py:271` — the run-record `ready` predicate is documented as "`check_passed`'s exact one"; it must gain the design condition too. **Correction (2026-09-27 review):** `test_run_record.py::test_ready_iff_check_passed_would_pass` (:467) will *not* flag this drift. It runs `check-readiness --honor-waiver` directly, not the YAML action, and its fixtures do not turn the design gate on, so it stays green while the predicate drifts. See Tests [Agent 1+3 finding]

### Tests

- `scripts/tests/test_autodev_characterization.py`: add the h2-shaped scenario
- `scripts/tests/test_autodev_loop.py`: a structural pin of the first gate
- `scripts/tests/test_run_record.py`: update the parity test and pin the `BLOCKED` token

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_autodev_loop.py` `TestDesignGateStep0Detection` (:569; locate by name — earlier anchors drifted) — the closest convention: `test_recheck_scores_calls_check_design` (:527) and `test_recheck_scores_composes_design_fail_with_check_readiness_exit_code` (:535, asserts `"&& ll-issues check-design" in action`). Add `check_passed` as a fourth method or extend the three-state loop at :557, asserting `"&& ll-issues check-design" in action` [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — no test pins `check_passed`'s action for `check-readiness` / `check-design`; `test_check_readiness_call_sites_pass_honor_waiver` (loops `("check_passed", "recheck_scores")`), `test_check_passed_stages_instead_of_passes` (~:7181) and the edge pins `test_check_passed_on_yes_routes_to_implement_current` / `_on_no_routes_to_post_refine_selector` / `_on_error_routes_to_detect_children` (~:8277-8310) stay green under either option if edges are kept [Agent 2+3 finding]
- `scripts/tests/test_autodev_characterization.py` — no h2-shaped scenario exists (`h2_first_gate_skips_design` and `test_h2_first_gate_ignores_design_and_files_no_marker` are cited only in this issue and the spike report). Add one: `frontmatter=READY`, `DESIGN_GATE_ARMED` (:51-52), `inner_runs=done()`. Only `design_gate_failed` (:274) arms the gate today, and it uses `LOW_READINESS`, so it never reaches `check_passed.on_yes`. The new scenario routes `check_passed` → `select_obligation_post_refine` → `check_missing_artifacts` → size-review → `recheck_after_size_review` → design remedy. **Correction (2026-09-27 review):** the unarmed scenarios (~:253, :458, :513, :595) cannot change path. The harness shims the real `ll-issues` (`autodev_harness.py:724`), not a fake, and `check-design` passes automatically (exit 0) when `.ll/program-design-cutover.json` is absent [Agent 3 finding]
- `scripts/tests/test_run_record.py::test_ready_iff_check_passed_would_pass` (:467) — make the reference command match the new gate: run `check-readiness --honor-waiver` and then `check-design`, and treat `ready` as both exiting 0. Add a case with the design gate on: READY scores, `.ll/program-design-cutover.json` present, no `## Program Design` section → outcome `blocked` (token `BLOCKED`). This is the accepted token change [Agent 3 finding, corrected]
- `scripts/tests/test_autodev_scores_freshness.py:181-189` — its `ll-issues` shim already answers `check-design` (exit 0) [Agent 3 finding]
- No test drives an inner `refine-to-ready-issue` `done` against the design gate. Under A none is needed: the outer gate catches the case whatever the inner loop does [Agent 3 finding]

### Documentation

- `docs/guides/LOOPS_REFERENCE.md`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — `check_passed → [thresholds met?]` diagram lines (~:1053, :1057, :1189) and long lines :1101, :1107; no existing "first gate" or `check-design` text in the autodev section, so the rule is new prose [Agent 1+4 finding]
- `docs/reference/CLI.md` — `ll-issues check-design` section (~:2335) lists `recheck_scores`, `regate_after_atomic_remediation`, `recheck_after_size_review` as callers (not `check_passed`); ~:2922 says `check_passed` and `recheck_scores` pass `--honor-waiver`. Add `check_passed` to the caller list [Agent 1 finding]

### Trace Evidence for Step 1 (added by `/ll:wire-issue`)

_Static trace of `refine-to-ready-issue.yaml` and `next_obligation.py`, not a run. It is the rationale for rule A; see "Decision" for why no probe is needed:_
- The Program Design gate is checked once inside the inner loop, at `route_pre_score_obligation` (tier-1 `DESIGN` → `check_gate_refine_limit`). A DESIGN failure seen there with the refine budget spent goes `record_gate_unmet` → `failed`, never `done`.
- `route_score_obligation` passes `--skip DESIGN`, so nothing re-checks the gate after scoring. Edits made after the pre-score check (`check_decide_attempts` → `resolve-decision`, `check_spike_needed` / `run_spike`) come back through `route_score_obligation` without re-reading DESIGN.
- A low score with the refine budget exhausted goes `check_refine_limit.on_no` → `breakdown_issue` → `write_broke_down` → `done`, also without a DESIGN check. **Correction (2026-09-27 review)**: this path writes `broke_down`, so the record is `DECOMPOSED` and autodev routes it to `detect_children`, never to `check_passed.on_yes`; it is not an exposure. `check_missing_artifacts.on_yes` → `check_decision_before_done` → `check_proof_before_done` → `write_done_record` → `done` does skip it and is an exposure.
- **The real exposure**: edits made after the pre-score DESIGN check (`check_decide_attempts` → `resolve-decision`, `check_spike_needed` → `run_spike`) return through `route_score_obligation`, which skips DESIGN, and reach `done`. The h2-shaped characterization scenario models the outer view of this: an issue that is READY on scores, with the design gate on and failing, whose inner run ends `done`.
- Downstream, `select_obligation_pre_implement` passes no `--skip`, so its `next-obligation` call can emit `DESIGN`, but its route table has no `DESIGN` entry and `_` falls to `check_proof_defer_or_implement`. Nothing after `check_passed.on_yes` blocks on a failing design gate.
- Reading: an inner `done` can leave `check-design` failing, which supports rule A. Not read in this pass: `check_wire_done`, `wire_issue` and `verify_issue` bodies, and the `PROOF_CLEAR` route block of `check_proof_defer_or_implement`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Put the `check_passed` rule comment above `action:`, not inside the `action: |` block: a comment inside the block is part of the action string and is visible to `yaml.safe_load` tests and MR-11 marker scanning. Do not write the string `autodev-dequeue-sha` in it (`test_autodev_loop.py::test_no_dequeue_sha_run_dir_artifact` scans the raw file)
- Mirror `recheck_scores`' action shape exactly (`autodev.yaml:1904-1911`): `ID="${captured.input.output}"` with the same `# ll-lint: mr11-ok(captured.input.output) ENH-3358 …` marker, then `"$ID"` throughout. **Correction (2026-09-27 review):** `recheck_scores` does not read `$ID` from `autodev-inflight`. `MR11_MARKER_ALLOWLIST` is a set keyed on `(file, var, issue)` (`test_builtin_loops.py:20589`), so another marker with the triple `("loops/autodev.yaml", "captured.input.output", "ENH-3358")`, which is already listed, leaves the set unchanged. Marker-suppressed lines add no `loop_interpolation_baseline.json` entry
- Update the run-record `ready` predicate (`run_record.py:28`, `:205`; `cli/issues/run_record.py:271`) with `check_passed`. The parity test covers the two places this issue owns: `check_passed` and the run-record `ready` predicate. ENH-3623 adds the `decide()` first-gate row and extends the parity test to three
- `recursive-refine.yaml`'s `check_passed`: named in the LOOPS_REFERENCE line as a known gap, out of scope (see Proposed Solution step 5)
- Add the h2-shaped characterization scenario and the `check_passed` structural pin

## Program Design

### Types

- N/A — no new types; the rule is a gate shape in `autodev.yaml` and one row in ENH-3623's `decide()` table

### Signatures

- `cmd_check_design(config: BRConfig, args: argparse.Namespace) -> int` — the existing Program Design gate; exit 0 passes (or not armed), 1 fails, 2 unresolved ID. `check_passed` now calls it; the function itself is unchanged
- `cmd_run_record_write(config: BRConfig, args: argparse.Namespace) -> int` — existing; its `ready` predicate gains the design condition
- `decide(snapshot: IssueSnapshot, facts: Facts) -> Step` — ENH-3623's pure policy (not in this issue); ENH-3623 adds the first-gate row encoding rule A

### Call Path

`autodev.yaml:check_passed` -> `ll-issues check-readiness` -> `cmd_check_readiness`, then `ll-issues check-design` -> `cmd_check_design`

## Impact

- **Priority**: P3 (raised from P4: it blocks ENH-3623). Probably intended behavior; this issue makes it explicit before the
  policy port.
- **Effort**: Small-Medium (no routing change needed; the run-record predicate change,
  its parity-test update and the new characterization scenario are the work).
- **Risk**: Low-Medium (more issues take the size-review → design-remedy path, and child
  record tokens change for design failures; neither changes autodev routing).
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: the `check_passed` gate change, the run-record `ready` predicate change,
  the comment/doc/tests, and the new characterization scenario.
- **Out of scope**: changing the later gates, changing `check-design` itself, changing
  `recursive-refine.yaml`'s `check_passed` (named as a known gap), and the `decide()`
  row (ENH-3623).
- **Ordering**: lands before ENH-3623, so the characterization suite is re-pinned on the
  YAML and ENH-3623 ports the chosen rule instead of inheriting the asymmetry.

## Acceptance Criteria

- [x] `check_passed` hard-ANDs `ll-issues check-design "$ID"` after `check-readiness`, mirroring `recheck_scores`' action shape and MR-11 marker (rule A)
- [ ] A real-FSM characterization scenario (READY scores, `DESIGN_GATE_ARMED`, inner `done()`) shows a first-gate design failure reaching the design remedy / `design_gate_failed` through `select_obligation_post_refine` → `check_missing_artifacts` → size-review (the traced route; no retarget)
- [x] `check_passed` and the run-record `ready` predicate agree: `test_ready_iff_check_passed_would_pass` uses `check-readiness` and then `check-design` as its reference and has a case with the design gate on
- [ ] A `refine-to-ready-issue` `done` record with a failing design gate is `BLOCKED`, not `READY`, pinned in `test_run_record.py` as an accepted change
- [x] `check_passed` carries a rewritten comment stating the rule, with the stale `breakdown_issue → done` and `implement_current` text removed
- [ ] A structural test pins the first-gate shape (`"&& ll-issues check-design" in action`)
- [x] `docs/guides/LOOPS_REFERENCE.md` states the rule and names `recursive-refine.yaml` as a known gap; `docs/reference/CLI.md` lists `check_passed` as a `check-design` caller

## Status

**Done** | Created: 2026-09-27 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-26_

**Readiness Score**: 90/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 75/100 → MODERATE

### Concerns
- `format-check` flags `missing_behavior_parity` (`scripts/little_loops/loops/autodev.yaml`): no `### Behavior Parity` subsection. Criterion 4 is capped at 10. The change is additive (one `&&` clause), but the record-token change (`READY` → `BLOCKED` for design failures) deserves a parity line.
- Line anchors in the issue have drifted (e.g. `TestDesignGateStep0Detection` is now at `test_autodev_loop.py:569`, not `:522-557`). Locate by name, not line.

### Outcome Risk Factors
- Moderate per-site complexity: the run-record `ready` predicate is shared by all writers, and the parity test needs a design-gate-on fixture
- Breadth across ~8 sites (YAML, run-record CLI + module, 3 test files, 2 docs)

## Session Log
- `/ll:manage-issue` - 2026-09-27T04:10:16 - `4b1c5ade-bd97-4871-b4cf-1f3dcd7cc5d1.jsonl`
- `/ll:ready-issue` - 2026-09-27T04:00:52 - `be769a1d-f85c-4a8c-bc10-519b325dfa77.jsonl`
- `/ll:confidence-check` - 2026-09-27T03:55:48 - `3ba31817-1733-43ed-8c15-8642253df06f.jsonl`
- `/ll:confidence-check` - 2026-09-27T03:42:25 - `7853641e-1dad-4830-bad1-b40be31584c3.jsonl`
- `/ll:wire-issue` - 2026-09-27T02:33:30 - `951684ed-7b41-4bf8-9307-a4474a28eb29.jsonl`
- `/ll:refine-issue` - 2026-09-27T02:19:49 - `c775572e-2829-4f8b-9fae-12aeff48a4bc.jsonl`
- `/ll:format-issue` - 2026-09-27T02:13:31 - `eab069d8-1487-4826-8057-122a54e92dfd.jsonl`

## Resolution

Implemented rule A: `check_passed` hard-ANDs `ll-issues check-design`; run-record `ready` predicate gained the design condition (design-failing child `done` → `BLOCKED`); comment rewritten; LOOPS_REFERENCE/CLI docs updated; structural pin, run-record parity/BLOCKED tests, and `first_gate_design_failure` characterization scenario added.
