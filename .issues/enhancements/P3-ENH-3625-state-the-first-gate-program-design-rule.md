---
id: ENH-3625
type: ENH
title: State the first-gate Program Design rule
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T01:48:55Z'
parent: EPIC-3565
relates_to:
- ENH-3621
blocks:
- ENH-3623
confidence_score: 95
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
the default is **option A** unless a real probe proves otherwise. ENH-3623's `decide()` has to encode one rule or the other.

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
  with the differential scenario `h2_first_gate_skips_design` and
  `test_h2_first_gate_ignores_design_and_files_no_marker`.
- The inner loop has a tier-1 `DESIGN` obligation (`refine-to-ready-issue.yaml`,
  `select_obligation` → `DESIGN: check_gate_refine_limit`, BUG-3551), so an inner `done`
  normally implies the design gate was handled. The inner loop also has a selector call
  that skips `DESIGN` (`--skip … DESIGN …`), and the refine budget is shared. Whether an
  inner `done` *guarantees* a passing design gate has not been shown.

## Expected Behavior

One stated rule, applied the same way in the YAML (until ENH-3623 lands) and in
`decide()` (after it lands). Choose one:

- **A. The first gate runs check-design too.** `check_passed` hard-ANDs `ll-issues
  check-design`, the same as the later gates. A design failure goes to the second-pass
  ladder (design remedy, then `design_gate_failed`), not to implementation.
- **B. The inner loop owns the design gate at the first gate.** Keep `check_passed`
  readiness-only. Document that the inner loop's tier-1 DESIGN obligation owns the
  Program Design gate on the first pass. Add a test showing that an inner `done` with
  a failing design gate cannot happen, or that it is the accepted exception.

## Motivation

The spike could only keep parity with the asymmetry. It could not say whether the
asymmetry is intended. `decide()` makes the rule explicit in one table row, so the
choice should be made on purpose before the port, not inherited.

## Proposed Solution

1. Trace whether an inner `refine-to-ready-issue` `done` can leave `ll-issues
   check-design` failing. Check the `--skip DESIGN` selector call and the shared
   refine-limit exhaustion path.
   The existing trace is static. Confirm it with a real run or probe (drive an inner
   `done` against a failing design gate) before choosing.
2. If it can, choose A. If it cannot (or only through a documented budget exhaustion
   that ends `failed`), choose B. **Default: A**, per the static trace.
   **A's routing is traced (2026-09-27 review) and needs no retarget.** `check_passed.on_no`
   → `select_obligation_post_refine`, whose `next-obligation` call skips `DESIGN` and
   prints `NONE` once scores pass → `_: check_missing_artifacts`:
   - `on_yes` → `run_wire` → rescore → `recheck_scores`, which ANDs `check-design`;
   - `on_no` → `detect_children` → `run_size_review` → `recheck_after_size_review`,
     which owns the design remedy and the `design_gate_failed` deferral.

   The cost is that a design-only first-gate failure runs size-review before the design
   remedy. That matches what `recheck_scores` already does on a design failure, so it is
   accepted, not new. The probe must confirm this route on a real FSM run.
3. **Post-ENH-3623 placement.** `check_passed` survives ENH-3623 as autodev's gate after
   the wrapper returns READY. The chosen rule must hold in three places: that gate, the
   `decide()` row after a `RUN_CHILD` done fact, and the run-record `ready` predicate.
4. Record the rule:
   - a comment on `check_passed`;
   - a line in `docs/guides/LOOPS_REFERENCE.md` (autodev section);
   - a structural test pinning the chosen gate shape;
   - a row in ENH-3623's `decide()` table tests.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/autodev.yaml`: `check_passed` (comment, or a gate
  change under A)
- `docs/guides/LOOPS_REFERENCE.md`: state the rule
- Under A: `scripts/little_loops/cli/issues/run_record.py` `cmd_run_record_write` gains the
  design check for the `ready` predicate (`check_format_gaps` + `design_gate_failed`
  from `issue_parser.py`), and `scripts/little_loops/run_record.py` updates the
  predicate's documentation (:28, :205)

**Behavior change under A (record tokens).** The run-record `ready` predicate is shared
by every writer, including `refine-to-ready-issue`. A child `done` record whose design
gate fails becomes `BLOCKED`, not `READY`. autodev's `route_refine_success` sends
`READY`, `BLOCKED` and `MISSING` all to `check_passed`, so routing does not change, but
record tokens are a field the ENH-3618 characterization suite compares. Pin the new
token in the h2-shaped scenario and list it as an accepted change.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` `select_obligation_pre_implement` (~:943) ends with `next-obligation` passing `--skip … DESIGN`, and `select_obligation_post_refine` (~:803) has the same skip list. Neither can catch a design failure at the first gate, so they do not backstop `check_passed` [Agent 2+4 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `route_pre_score_obligation` (DESIGN → `check_gate_refine_limit`, BUG-3551) and `route_score_obligation` (`--skip … DESIGN`, ~:825) are the two inner selector calls the trace turns on [Agent 1+4 finding]
- `scripts/little_loops/loops/recursive-refine.yaml` `check_passed` (~:256, recheck copy ~:502 "Mirrors check_passed logic exactly") has no `check-design` either; out of scope, but decide whether the stated rule should name it [Agent 1 finding]
- `scripts/little_loops/cli/issues/check_design.py:19` (`cmd_check_design`), dispatched at `cli/issues/__init__.py:1096`; `cli/issues/next_obligation.py` `_tier1_probe()` is the tier-1 `DESIGN` branch [Agent 1+4 finding]
- `scripts/little_loops/run_record.py` (:28, :205) and `cli/issues/run_record.py:271` — the run-record `ready` predicate is documented as "`check_passed`'s exact one"; under option A it must gain the design condition too, or `test_run_record.py::test_ready_iff_check_passed_would_pass` (:330, :467) flags the drift [Agent 1+3 finding]

### Tests

- `scripts/tests/test_autodev_characterization.py`: re-pin `h2`-shaped behavior under A
- `scripts/tests/test_autodev_loop.py` or `test_autodev_scores_freshness.py`: a
  structural pin of the first gate

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_autodev_loop.py` `TestDesignGateStep0Detection` (:522-557) — the closest convention: `test_recheck_scores_calls_check_design` (:527) and `test_recheck_scores_composes_design_fail_with_check_readiness_exit_code` (:535, asserts `"&& ll-issues check-design" in action`). Add `check_passed` as a fourth method or extend the three-state loop at :557. Under B assert `"ll-issues check-readiness" in action` and `"check-design" not in action`; under A assert the AND [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — no test pins `check_passed`'s action for `check-readiness` / `check-design`; `test_check_readiness_call_sites_pass_honor_waiver` (loops `("check_passed", "recheck_scores")`), `test_check_passed_stages_instead_of_passes` (~:7181) and the edge pins `test_check_passed_on_yes_routes_to_implement_current` / `_on_no_routes_to_post_refine_selector` / `_on_error_routes_to_detect_children` (~:8277-8310) stay green under either option if edges are kept [Agent 2+3 finding]
- `scripts/tests/test_autodev_characterization.py` — no h2-shaped scenario exists (`h2_first_gate_skips_design` and `test_h2_first_gate_ignores_design_and_files_no_marker` are cited only in this issue and the spike report). Add one: `frontmatter=READY`, `DESIGN_GATE_ARMED` (:51-52), `inner_runs=done()`. Only `design_gate_failed` (:274) arms the gate today, and it uses `LOW_READINESS`, so it never reaches `check_passed.on_yes`. Under A the scenario routes to the ladder; the four unarmed scenarios (~:253, :458, :513, :595) may break if the harness `check-design` fake fails unarmed [Agent 3 finding]
- `scripts/tests/test_run_record.py::test_ready_iff_check_passed_would_pass` (:330, :467) — see Dependent Files; A must update the run-record `ready` predicate together with `check_passed` [Agent 3 finding]
- `scripts/tests/test_autodev_scores_freshness.py:181-189` — its `ll-issues` shim already answers `check-design` (exit 0) [Agent 3 finding]
- No test drives an inner `refine-to-ready-issue` `done` against the design gate; under B the "cannot happen or accepted exception" test is new [Agent 3 finding]

### Documentation

- `docs/guides/LOOPS_REFERENCE.md`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — `check_passed → [thresholds met?]` diagram lines (~:1053, :1057, :1189) and long lines :1101, :1107; no existing "first gate" or `check-design` text in the autodev section, so the rule is new prose [Agent 1+4 finding]
- `docs/reference/CLI.md` — `ll-issues check-design` section (~:2335) lists `recheck_scores`, `regate_after_atomic_remediation`, `recheck_after_size_review` as callers (not `check_passed`); ~:2922 says `check_passed` and `recheck_scores` pass `--honor-waiver`. Update the caller list under A, or state the exception under B [Agent 1 finding]

### Trace Evidence for Step 1 (added by `/ll:wire-issue`)

_Static trace of `refine-to-ready-issue.yaml` and `next_obligation.py`, not a run; confirm before choosing:_
- The Program Design gate is checked once inside the inner loop, at `route_pre_score_obligation` (tier-1 `DESIGN` → `check_gate_refine_limit`). A DESIGN failure seen there with the refine budget spent goes `record_gate_unmet` → `failed`, never `done`.
- `route_score_obligation` passes `--skip DESIGN`, so nothing re-checks the gate after scoring. Edits made after the pre-score check (`check_decide_attempts` → `resolve-decision`, `check_spike_needed` / `run_spike`) come back through `route_score_obligation` without re-reading DESIGN.
- A low score with the refine budget exhausted goes `check_refine_limit.on_no` → `breakdown_issue` → `write_broke_down` → `done`, also without a DESIGN check. **Correction (2026-09-27 review)**: this path writes `broke_down`, so the record is `DECOMPOSED` and autodev routes it to `detect_children`, never to `check_passed.on_yes`; it is not an exposure. `check_missing_artifacts.on_yes` → `check_decision_before_done` → `check_proof_before_done` → `write_done_record` → `done` does skip it and is an exposure.
- **The real exposure**: edits made after the pre-score DESIGN check (`check_decide_attempts` → `resolve-decision`, `check_spike_needed` → `run_spike`) return through `route_score_obligation`, which skips DESIGN, and reach `done`. The probe should drive exactly this: an issue that is READY on scores, DESIGN-armed after the pre-score check, and whose inner run ends `done`.
- Downstream, `select_obligation_pre_implement` passes no `--skip`, so its `next-obligation` call can emit `DESIGN`, but its route table has no `DESIGN` entry and `_` falls to `check_proof_defer_or_implement`. Nothing after `check_passed.on_yes` blocks on a failing design gate.
- Reading: an inner `done` can leave `check-design` failing, which points to option A per Proposed Solution step 2. Not read in this pass: `check_wire_done`, `wire_issue` and `verify_issue` bodies, and the `PROOF_CLEAR` route block of `check_proof_defer_or_implement`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Put the `check_passed` rule comment above `action:`, not inside the `action: |` block: a comment inside the block is part of the action string and is visible to `yaml.safe_load` tests and MR-11 marker scanning. Do not write the string `autodev-dequeue-sha` in it (`test_autodev_loop.py::test_no_dequeue_sha_run_dir_artifact` scans the raw file)
- Under A, an added `ll-issues check-design` line must use `"$ID"` from `autodev-inflight` (as `recheck_scores` does), not `${captured.input.output}`, to avoid a new MR-11 marker (`MR11_MARKER_ALLOWLIST` is an exact-set test) and a new `loop_interpolation_baseline.json` entry (its only `check_passed` entry is `recursive-refine.yaml`)
- Under A, update the run-record `ready` predicate (`run_record.py:28`, `:205`; `cli/issues/run_record.py:271`) with `check_passed`, and add a parity test across the three places that must agree: `check_passed`, the run-record `ready` predicate and ENH-3623's `decide()` first-gate row
- State whether the rule also covers `recursive-refine.yaml`'s `check_passed` (same gap, out of scope to change)
- Add the h2-shaped characterization scenario and the `check_passed` structural pin; add the ENH-3623 `decide()` first-gate table row

## Program Design

### Types

- N/A — no new types; the rule is a gate shape in `autodev.yaml` and one row in ENH-3623's `decide()` table

### Signatures

- `cmd_check_design(config: BRConfig, args: argparse.Namespace) -> int` — the existing Program Design gate; exit 0 passes. Under option A, `check_passed` calls it; unchanged either way
- `decide(snapshot: IssueSnapshot, facts: Facts) -> Step` — ENH-3623's pure policy; gains one first-gate row encoding the chosen rule

### Call Path

`autodev.yaml:check_passed` -> `ll-issues check-readiness` -> `cmd_check_readiness`; under option A, then `ll-issues check-design` -> `cmd_check_design`

## Impact

- **Priority**: P3 (raised from P4: it blocks ENH-3623). Probably intended behavior; this issue makes it explicit before the
  policy port.
- **Effort**: Small under B. Small-Medium under A (no routing change needed; the
  run-record predicate change and the characterization re-pin are the extra work).
- **Risk**: Low under B (docs and tests only). Low-Medium under A (more issues take the
  size-review → design-remedy path, and child record tokens change for design failures).
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: the decision, the comment/doc/test, and, under option A, the
  `check_passed` change and its characterization re-pin.
- **Out of scope**: changing the later gates, changing `check-design` itself, and changing
  `recursive-refine.yaml`'s `check_passed` (the stated rule may name it).
- **Ordering**: lands before ENH-3623, so the characterization suite is re-pinned on the
  YAML and ENH-3623 ports the chosen rule instead of inheriting the asymmetry.

## Acceptance Criteria

- [ ] The rule (A or B) is chosen, with the trace evidence recorded in this issue, confirmed by a run or probe (not the static trace alone)
- [ ] Under A: a real-FSM test shows a first-gate design failure reaching the design remedy / `design_gate_failed` through `select_obligation_post_refine` → `check_missing_artifacts` → size-review (the traced route; no retarget)
- [ ] Under A: `check_passed`, the run-record `ready` predicate and the `decide()` first-gate row agree (parity test)
- [ ] Under A: a `refine-to-ready-issue` `done` record with a failing design gate is `BLOCKED`, not `READY`; the h2-shaped characterization scenario pins the token as an accepted change
- [ ] `check_passed` carries a comment stating the rule
- [ ] A test pins the chosen first-gate shape
- [ ] ENH-3623's `decide()` table tests include the rule

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-27T03:42:25 - `7853641e-1dad-4830-bad1-b40be31584c3.jsonl`
- `/ll:wire-issue` - 2026-09-27T02:33:30 - `951684ed-7b41-4bf8-9307-a4474a28eb29.jsonl`
- `/ll:refine-issue` - 2026-09-27T02:19:49 - `c775572e-2829-4f8b-9fae-12aeff48a4bc.jsonl`
- `/ll:format-issue` - 2026-09-27T02:13:31 - `eab069d8-1487-4826-8057-122a54e92dfd.jsonl`
