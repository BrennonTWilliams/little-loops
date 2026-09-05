---
id: BUG-3390
type: BUG
title: 'autodev: dead outcome_gate_waived path, stale guard-2 capture provenance,
  no post-implement closure check, and unwired go-no-go escalation'
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-04'
captured_at: '2026-09-04T21:11:07Z'
completed_at: '2026-09-05T17:58:53Z'
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3390: autodev: dead outcome_gate_waived path, stale guard-2 capture provenance, no post-implement closure check, and unwired go-no-go escalation

## Summary

Deep audit of `scripts/little_loops/loops/autodev.yaml` (79 states) and its sub-loops found five real defects and one unwired skill hook:

1. `outcome_gate_waived` is dead end-to-end: `regate_after_atomic_remediation` and `recheck_after_size_review` read it from `ll-issues show --json`, which never emits the key; `check_passed`/`recheck_after_decide`/`recheck_scores` use bare `ll-issues check-readiness`, which never reads it. `/ll:go-no-go`'s designed escalation valve (stamp the waiver on GO over an `oversized_atomic` deferral) therefore never lets an issue through, and the loop never invokes go-no-go anyway. `check-readiness` also lets config thresholds silently override explicit `--readiness/--outcome` args, so a per-run `--context readiness_threshold=NN` is honored by the inline gates but not the CLI gates.
2. Guard-2 stale-capture provenance gap: `check_size_review_ran_this_pass` proceeds to `check_guard2_verdict` (which regexes the run-scoped `captured.size_review_output`) whenever a negative marker written only by `check_broke_down` is absent. `rerun_confidence_after_wire.next` and `rerun_confidence_after_spike.next` reach it via `enqueue_or_skip` without running `run_size_review` or `check_broke_down`, so on a multi-issue run the second issue can be sent through `remediate_oversized_atomic` and deferred `oversized_atomic` on a previous issue's output.
3. No immediate post-implementation verification: `implement_current` exit 0 routes straight to `dequeue_next`; `ll-auto` exits 0 on "Issues processed: 0" (postmortem 2026-07-29). Only caught at `finalize_done`, with no reason, and `autodev-inflight` is never cleared on the success path.
4. Double ledger when the child loop defers a decision: `refine-to-ready-issue.yaml` `record_decision_unresolved` writes `autodev-decision-unresolved.txt` then exits `failed` without `classify_terminal`, so autodev's `skip_inflight` also ledgers `refine_failed`.
5. `refine_current` carries `fragment: with_rate_limit_handling` and `on_rate_limit_exhausted` on a `loop:` call state; both are inert (429 interception is gated on `action_result`, which sub-loop states never produce).
6. `/ll:go-no-go` Step 3f skips the findings write-back (and the waiver stamp) when it has no novel findings, so a GO can fail to stamp.

## Current Behavior

`autodev.yaml` routes runs through six broken paths: (1) `outcome_gate_waived` is written to frontmatter by go-no-go's designed escalation but never read by `ll-issues show --json` or the CLI-based readiness gates (`check_passed`, `recheck_after_decide`, `recheck_scores`), and `/ll:go-no-go` is never invoked from the loop, so an `oversized_atomic` deferral can never be waived through; config thresholds also silently override explicit `--readiness`/`--outcome` CLI args in `check-readiness`. (2) On a multi-issue run, `check_guard2_verdict` can regex a *previous* issue's stale `captured.size_review_output` because `check_size_review_ran_this_pass` only checks for the absence of a negative marker that `check_broke_down` writes, not a positive marker proving `run_size_review` ran for *this* issue this pass. (3) `implement_current` routes straight to `dequeue_next` on exit 0 with no closure check, so an `ll-auto` no-op success (postmortem 2026-07-29: "Issues processed: 0") is only caught later at `finalize_done`, with no reason and `autodev-inflight` never cleared. (4) When `refine-to-ready-issue.yaml`'s `record_decision_unresolved` exits `failed` without `classify_terminal`, autodev's `skip_inflight` double-ledgers the same ID as `refine_failed`. (5) `refine_current` declares `fragment: with_rate_limit_handling` and `on_rate_limit_exhausted`, both inert on a `loop:` call state. (6) `/ll:go-no-go` Step 3f skips its findings write-back — and the waiver stamp — whenever it finds no novel findings.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

**Landed state (updated 2026-09-05 review)**: items 1, 2, 3, 5, 6 of the Summary are implemented and **committed on `main` in `3e798eeac`** (`fix(autodev): honor outcome_gate_waived and explicit threshold overrides (BUG-3390)`), which touches `check_readiness.py`, `show.py`, `cli/issues/__init__.py`, `autodev.yaml`, and the test files cited below; the go-no-go SKILL.md paragraph landed in `caddec57b`. Do not re-implement them — verify with `ll-loop validate autodev` (clean as of this review) and the cited tests (145 pass across `test_check_readiness.py`, `test_show.py`, `test_autodev_decision_gate.py`).

- Item 1 (`outcome_gate_waived` round-trip + `--honor-waiver` + go-no-go escalation): `ReadinessStatus.outcome_gate_waived`/`meets_outcome_or_waived` (`check_readiness.py:16-55`); `--honor-waiver` wired at `check_readiness.py:147-181` and CLI registration `cli/issues/__init__.py:778-787,1052-1053`; `show.py:148,349-351` emits the key; `autodev.yaml` `check_passed`/`recheck_after_decide`/`recheck_scores` all pass `--honor-waiver` (test: `test_check_readiness_call_sites_pass_honor_waiver`, `test_builtin_loops.py:7488-7494`). Threshold precedence confirmed: explicit CLI `--readiness`/`--outcome` now overwrites the config-or-default value (`check_readiness.py:119-122`) — matches the issue's Expected Behavior. New states `check_go_no_go_eligible → run_go_no_go → check_go_no_go_waiver → reopen_waived` exist at `autodev.yaml:1963-2048`, wired from `check_atomic_design_remedy.on_no` (`autodev.yaml:1960`), matching the Program Design call path exactly.
- Item 2 (guard-2 provenance): positive marker `autodev-size-review-ran-this-pass` written by `count_repair_cycle_size_review` (`autodev.yaml:1505`), required by `check_size_review_ran_this_pass` (`autodev.yaml:1731-1750`, fails closed `on_no`/`on_error → recheck_after_size_review`), cleared per-issue at `dequeue_next` (`autodev.yaml:116`).
- Item 3 (post-implement closure): new state `verify_impl_closed` (`autodev.yaml:921-951`) sits between `implement_current.on_yes` and `dequeue_next`; ledgers `impl_exit0_not_closed` to `autodev-unverified.txt` when status isn't closed; clears `autodev-inflight` unconditionally on both branches (`autodev.yaml:935`).
- Item 5 (inert rate-limit keys): `refine_current` (`autodev.yaml:472-510`) already declares neither `fragment: with_rate_limit_handling` nor `on_rate_limit_exhausted`. Structural test `test_no_loop_call_state_declares_on_rate_limit_exhausted` (`test_builtin_loops.py:7471-7486`) enumerates the exact `loop:` state set (`{"refine_current", "resolve_decision", "resolve_decision_direct"}`) and asserts neither key on any of them; a parallel test for `refine-to-ready-issue.yaml` exists at `test_builtin_loops.py:3048-3061`.
- Item 6 (go-no-go waiver stamp): `skills/go-no-go/SKILL.md:402` adds an explicit paragraph headed "`outcome_gate_waived` escalation (BUG-2734)" beneath Step 3f's findings-write gate, directing the waiver stamp regardless of `HAS_FINDINGS`, citing BUG-3390 by name.

**Remaining true gap — item 4 is downstream-mitigated only, not root-caused-fixed**: `refine-to-ready-issue.yaml`'s `record_decision_unresolved` (`refine-to-ready-issue.yaml:897-925`) still exits via `next: failed`/`on_error: failed` without calling `classify_terminal` — confirmed absent from that state's block. The double-ledger consequence is instead suppressed one hop downstream: `autodev.yaml`'s `skip_inflight` (`autodev.yaml:512-556`) greps `autodev-decision-unresolved.txt` for the ID via whole-line match (`grep -qxF`, `autodev.yaml:544-549`) and skips writing `refine_failed` when found, tested by `test_skip_inflight_skips_refine_failed_when_decision_unresolved_ledgered` and `test_skip_inflight_decision_ledger_match_is_whole_line` (`test_builtin_loops.py:7502-7520`). This fixes autodev's own ledger. **Correction (2026-09-05 review)**: there is no "other caller" hazard — `refine-terminal-class` is consumed only by autodev's `skip_inflight` (grep across `loops/`, `skills/`, `commands/`, `docs/` finds no other reader), and `resolve_issue` (`refine-to-ready-issue.yaml:144`) `rm -f`s the file at the start of every issue, so a stale class from a previous issue cannot leak. Root-causing item 4 is therefore optional hygiene, not a correctness fix. If done, mirror the `mark_rate_limit_infra` direct-write pattern (`refine-to-ready-issue.yaml:888-895`): `printf 'decision_unresolved' > ${context.run_dir}/refine-terminal-class` inside `record_decision_unresolved`, keep `next: failed` so `test_record_decision_unresolved_defers_and_routes_to_failed` (`test_builtin_loops.py:2806`) stays valid, and add a write assertion. `skip_inflight` needs no change (it treats any non-`infra` class as quality and already short-circuits on the ledger grep).

**Also corrected**: the earlier claim that `docs/guides/LOOPS_REFERENCE.md` references a "deleted `run_decide` state" is wrong — `LOOPS_REFERENCE.md:680` points at `oracles/resolve-decision.yaml`'s `run_decide`, which exists (`resolve-decision.yaml:146`). The diagram draws it inline rather than via the sub-loop; that is a presentation simplification, not a dangling reference.

**What actually remains** (see the unchecked Acceptance Criteria below): the LOOPS_REFERENCE.md BUG-2744 paragraph (`:1081`) still describes the guard-2 provenance check as a *negative* `autodev-size-review-skipped-this-pass` marker that "fails open" — the shipped code is a *positive* `autodev-size-review-ran-this-pass` marker that fails closed, so the doc now contradicts the code; the diagram also omits `verify_impl_closed` and the `check_go_no_go_eligible → run_go_no_go → check_go_no_go_waiver → reopen_waived` chain. `skills/audit-loop-run/SKILL.md:271` still frames the waiver as a manual human decision. Item 6 has no test. Item 4 is optional per the paragraph above.

## Expected Behavior

`outcome_gate_waived` round-trips through `ll-issues show --json` and is honored (via a new `--honor-waiver` flag) by every CLI-based readiness gate; explicit `--readiness`/`--outcome` always win over config. Autodev invokes `/ll:go-no-go --auto` once per issue per run after an `oversized_atomic` deferral and reopens the issue when the waiver is stamped. `check_guard2_verdict` only fires when a positive, this-pass marker proves `run_size_review` actually ran for the current issue. `implement_current` success is verified immediately — re-reading issue status before dequeuing — with an `autodev-unverified.txt` ledger line and `autodev-inflight` cleared on both branches. `skip_inflight` does not double-ledger an ID already recorded in `autodev-decision-unresolved.txt`. No `loop:` call state declares rate-limit-handling keys that only `action_result` states can consume. `/ll:go-no-go` always writes back its findings — and stamps the waiver on a GO verdict — regardless of whether it found novel findings this pass.

## Steps to Reproduce

1. Run `ll-issues check-readiness <ID> --readiness 50` on an issue whose `.ll/ll-config.json` sets a different `commands.confidence_gate.readiness_threshold`; observe the config value wins instead of the explicit `--readiness 50`.
2. Have `/ll:go-no-go --auto <ID>` stamp `outcome_gate_waived: true` on an issue previously deferred `oversized_atomic`; run `ll-issues show <ID> --json | jq .outcome_gate_waived` — observe the key is absent, and note autodev never called go-no-go to begin with.
3. Run `ll-loop run autodev` over a queue of 2+ issues where the first is deferred `oversized_atomic`; observe the second issue can reach `check_guard2_verdict` even though `run_size_review`/`check_broke_down` never ran for it this pass.
4. Force `implement_current` to exit 0 while the issue's actual status stays open (mirroring `ll-auto`'s "Issues processed: 0" no-op); observe autodev proceeds straight to `dequeue_next` with no failure surfaced until `finalize_done`, and `autodev-inflight` is left set.
5. Run autodev over an issue where the refine-to-ready child loop defers via `record_decision_unresolved`; inspect the run's ledger files — observe `refine_failed` recorded in addition to the decision-unresolved entry for the same ID.
6. Inspect `refine_current` in `scripts/little_loops/loops/autodev.yaml`; note it declares `fragment: with_rate_limit_handling` / `on_rate_limit_exhausted` on a `loop:` call state, which never produces the `action_result` that 429 interception is gated on.

## Proposed Solution

- `ll-issues show --json` emits `outcome_gate_waived`; `ll-issues check-readiness` gains `--honor-waiver` and lets explicit CLI thresholds win over config; the three CLI-based autodev gates pass `--honor-waiver`.
- Wire `/ll:go-no-go --auto` once per issue per run after an `oversized_atomic` deferral (`check_go_no_go_eligible → run_go_no_go → check_go_no_go_waiver → reopen_waived → decide_current`).
- Positive `autodev-size-review-ran-this-pass` marker written by `count_repair_cycle_size_review`; `check_size_review_ran_this_pass` requires it and fails closed on error.
- New `verify_impl_closed` state after `implement_current` success: re-read status, ledger `impl_exit0_not_closed` to `autodev-unverified.txt` when not closed, clear `autodev-inflight` on both branches; `finalize_done` dedupes reasoned lines.
- `skip_inflight` suppresses `refine_failed` when the ID is already in `autodev-decision-unresolved.txt`.
- Drop the inert keys from `refine_current`; add a structural test forbidding them on any `loop:` state.
- go-no-go SKILL.md: stamp the waiver on GO regardless of `HAS_FINDINGS`.
- Update `docs/guides/LOOPS_REFERENCE.md`: rewrite the BUG-2744 guard paragraph (`:1081`) for the positive fail-closed marker; add `verify_impl_closed` and the go-no-go chain to the autodev diagram/prose; fill in the ~18 omitted states and the four-vs-five entry-point count. (`run_decide` is a valid `oracles/resolve-decision.yaml` state — leave it.)
- Update `skills/audit-loop-run/SKILL.md:271` so `oversized_atomic` is described as an automated one-shot go-no-go escalation, with manual waiver only as the fallback after autodev's attempt.
- Add a text-assertion test that `skills/go-no-go/SKILL.md` stamps the waiver regardless of `HAS_FINDINGS` (item 6 is otherwise untested).
- Do **not** add `--honor-waiver` to `rn-remediate.yaml`'s `check_readiness` (decision recorded below).

## Program Design

### Types

- `outcome_gate_waived: bool` (frontmatter key; already modeled as `ReadinessStatus.outcome_gate_waived` in `check_readiness.py`)

### Signatures

- `readiness_status(config: BRConfig, issue_id: str, *, readiness_override: int | None, outcome_override: int | None) -> ReadinessStatus | None` (`scripts/little_loops/cli/issues/check_readiness.py:69`)
- `ReadinessStatus.meets_outcome_or_waived -> bool` (`check_readiness.py:48`)
- `cmd_check_readiness(config: BRConfig, args: argparse.Namespace) -> int` (`check_readiness.py:147`), consuming a new `--honor-waiver` CLI flag
- new FSM states in `scripts/little_loops/loops/autodev.yaml`: `check_go_no_go_eligible`, `run_go_no_go`, `check_go_no_go_waiver`, `reopen_waived`, `verify_impl_closed`
- `count_repair_cycle_size_review` (`autodev.yaml:1491`) writes the positive marker `${context.run_dir}/autodev-size-review-ran-this-pass`; `check_size_review_ran_this_pass` (`autodev.yaml:1731`) requires it and fails closed on error

### Call Path

`check_atomic_design_remedy.on_no` -> `check_go_no_go_eligible` -> `run_go_no_go` (`/ll:go-no-go --auto`) -> `check_go_no_go_waiver` -> `reopen_waived` -> `decide_current`

`implement_current.on_yes` -> `verify_impl_closed` (re-reads `ll-issues show --json`) -> `dequeue_next` | ledger `autodev-unverified.txt`

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/show.py` — emit `outcome_gate_waived`
  > ⚠ Superseded — landed in `3e798eeac`; no further change needed
- `scripts/little_loops/cli/issues/check_readiness.py` — `--honor-waiver`, explicit-override precedence
  > ⚠ Superseded — landed in `3e798eeac`; no further change needed
- `scripts/little_loops/loops/autodev.yaml` — go-no-go escalation states, positive size-review marker, `verify_impl_closed`, `skip_inflight` fix, drop inert rate-limit keys from `refine_current`
  > ⚠ Superseded — landed in `3e798eeac`; no further change needed
- `skills/go-no-go/SKILL.md` — stamp the waiver on GO regardless of `HAS_FINDINGS`
  > ⚠ Superseded — landed in `caddec57b`; only the test for it remains
- `docs/guides/LOOPS_REFERENCE.md` — rewrite the BUG-2744 guard paragraph (`:1081`) for the positive fail-closed marker; add `verify_impl_closed` and the go-no-go chain; correct state inventory and entry points
- `skills/audit-loop-run/SKILL.md` — reframe `oversized_atomic` as automated go-no-go escalation (`:271`)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — (optional) `record_decision_unresolved` direct `refine-terminal-class` write

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/__init__.py` — `check-readiness` CLI wiring
- `loops/refine-to-ready-issue.yaml` — `record_decision_unresolved` interacts with autodev's `skip_inflight`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py` — imports `readiness_status` from `check_readiness.py` (`issue_manager.py:818-820`) and consumes `ReadinessStatus` directly in `process_issue_inplace`'s gate logic; a second, non-CLI consumer of the module beyond the three named autodev states [Agent 1 finding]
- `scripts/little_loops/loops/rn-remediate.yaml` — its own `check_readiness` state (~lines 194-205) shells out `ll-issues check-readiness "$ID" --readiness ... --outcome ...` without `--honor-waiver`; it is silently affected by the config-vs-explicit-override precedence fix (its own explicit context-seeded thresholds now win over config, unlike before) even though it isn't one of the three call sites this issue names in scope [Agent 1 + Agent 2 finding]

### Similar Patterns

- `scripts/tests/test_autodev_decision_gate.py`, `scripts/tests/test_autodev_loop.py` — existing gate/loop test conventions to extend

### Tests

- `scripts/tests/test_check_readiness.py` — `--honor-waiver` cases
- `scripts/tests/test_autodev_loop.py`, `scripts/tests/test_autodev_decision_gate.py` — new states/markers
- `scripts/tests/test_fsm_topology.py` — forbid `on_rate_limit_exhausted`/`with_rate_limit_handling` on `loop:` states
- `scripts/tests/test_builtin_loops.py` — `ll-loop validate autodev`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_manager.py` — imports/patches `little_loops.cli.issues.check_readiness.readiness_status`/`ReadinessStatus` (15+ sites) to exercise `process_issue_inplace`'s gate behavior; verify unaffected or update for the new precedence rule [Agent 1 + Agent 3 finding]
- Item 6 (go-no-go SKILL.md "stamp the waiver regardless of `HAS_FINDINGS`") has **no test coverage anywhere in the repo** — searched `HAS_FINDINGS`/`outcome_gate_waived`/`go_no_go` across all test files with no hits against this specific behavior; new coverage is needed [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::test_record_decision_unresolved_defers_and_routes_to_failed` (~line 2806-2819) asserts `record_decision_unresolved.next == "failed"`; this will likely need updating once item 4 (`record_decision_unresolved` → `classify_terminal`) is implemented — either to `next == "classify_terminal"` (if routed through it) or augmented with a `refine-terminal-class` write assertion (if fixed via the `mark_rate_limit_infra` direct-write pattern, `refine-to-ready-issue.yaml:888-895`) [Agent 3 finding]

### Documentation

- `docs/guides/LOOPS_REFERENCE.md`

_Wiring pass added by `/ll:wire-issue`:_
- `skills/audit-loop-run/SKILL.md` (~line 271) — its "oversized_atomic ... `outcome_gate_waived` decision" paragraph frames the waiver as a manual human follow-up; post-fix this is an automated one-shot-per-run escalation (`check_go_no_go_eligible → run_go_no_go`), so the framing goes stale [Agent 2 finding]

### Configuration

- N/A

### Behavior Parity

| File | Preserved | Changed | Dropped |
|------|-----------|---------|---------|
| `docs/guides/LOOPS_REFERENCE.md` | Overall guide structure, unrelated state descriptions, and the `run_decide` reference (a valid `oracles/resolve-decision.yaml` state) | BUG-2744 paragraph rewritten for the positive fail-closed marker; `verify_impl_closed` and go-no-go chain added; state inventory corrected to include the ~18 currently-omitted states and the true four-vs-five entry-point count | Description of the negative `autodev-size-review-skipped-this-pass` marker and its "fails open" semantics |
| `skills/audit-loop-run/SKILL.md` | All other summary-key guidance | `oversized_atomic` paragraph reframed as automated go-no-go escalation with manual waiver as fallback | "manual human `outcome_gate_waived` decision" as the primary framing |

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- **Decided (2026-09-05 review): `rn-remediate.yaml`'s `check_readiness` does NOT get `--honor-waiver`.** rn-remediate exists to *earn* the pass through refinement; the waiver is autodev's post-`oversized_atomic` escalation valve and has no meaning mid-remediation. The config-vs-explicit precedence change *is* intended for rn-remediate too: its state comment (ENH-1977 Fix 2) already assumes the context-seeded `--readiness/--outcome` values win, which was silently untrue before `3e798eeac`. No code change; do not relitigate.
- Add test coverage for item 6 (go-no-go SKILL.md's "stamp waiver regardless of `HAS_FINDINGS`") — a text assertion on the skill body under the `outcome_gate_waived` escalation paragraph is sufficient; currently untested anywhere in the repo
- Item 4 (optional): if the direct-write fix is applied, keep `next: failed` so `test_record_decision_unresolved_defers_and_routes_to_failed` (`test_builtin_loops.py:2806`) remains valid, and add a `refine-terminal-class` write assertion alongside it. If skipped, add a one-line descope note to this issue's Resolution.
- Reconcile `skills/audit-loop-run/SKILL.md:271`'s stale "manual `outcome_gate_waived` decision" framing with the new automated escalation chain

## Impact

- **Priority**: P2 - dead escalation/closure paths silently block issue closure and mask no-op successes in unattended `ll-auto` runs; not P1 because each defect has a manual workaround (re-run, manual waiver edit)
- **Effort**: Medium - six largely independent fixes spanning `check_readiness.py`, `show.py`, `autodev.yaml` (new states/markers), and `go-no-go` SKILL.md, plus test coverage for each
- **Risk**: Medium - touches the core autodev gate/guard states that mediate every automated issue closure; a regression could silently block or wrongly pass issues in unattended runs, mitigated by `ll-loop validate` and the existing gate/loop test suites
- **Breaking Change**: No - additive states/flags/markers; existing `check-readiness` callers without `--honor-waiver` keep current behavior

## Acceptance Criteria

Landed in `3e798eeac` / `caddec57b` (verified 2026-09-05):

- [x] `ll-issues show <ID> --json` emits `outcome_gate_waived`
- [x] `ll-issues check-readiness <ID> --honor-waiver` passes the outcome half when the flag is set; readiness still enforced; explicit `--readiness/--outcome` override config
- [x] `check_passed`, `recheck_after_decide`, `recheck_scores` pass `--honor-waiver`
- [x] go-no-go escalation states exist with one-shot marker; `check_atomic_design_remedy.on_no → check_go_no_go_eligible`
- [x] `check_size_review_ran_this_pass` requires the positive marker; only `count_repair_cycle_size_review` writes it; `on_error → recheck_after_size_review`
- [x] `implement_current.on_yes → verify_impl_closed`; unverified ledger line `ID  impl_exit0_not_closed`; inflight cleared on both branches; `finalize_done` counts a reasoned line once
- [x] `skip_inflight` does not ledger `refine_failed` for an ID already in `autodev-decision-unresolved.txt`
- [x] No `loop:` state in autodev declares `on_rate_limit_exhausted` or `with_rate_limit_handling`
- [x] `skills/go-no-go/SKILL.md` stamps the waiver on GO regardless of `HAS_FINDINGS`

Landed in this pass (2026-09-05):

- [x] `docs/guides/LOOPS_REFERENCE.md` BUG-2744 paragraph rewritten for the positive `autodev-size-review-ran-this-pass` marker and fail-closed `on_error`; no remaining mention of `autodev-size-review-skipped-this-pass` or "fails open"
- [x] `docs/guides/LOOPS_REFERENCE.md` autodev diagram/prose includes `verify_impl_closed` and the `check_go_no_go_eligible → run_go_no_go → check_go_no_go_waiver → reopen_waived` chain; entry-point count corrected from four to five (`triage_outcome_failure` was missing) and the stale pre-ENH-3075 `check_decision_decidable`/`deposit_options` inline-state description replaced with a pointer to the already-accurate Decidability gate parity paragraph
- [x] `skills/audit-loop-run/SKILL.md:271` describes `oversized_atomic` as an automated one-shot go-no-go escalation, with manual waiver as the fallback
- [x] A test asserts the go-no-go SKILL.md waiver paragraph directs stamping regardless of `HAS_FINDINGS` (`test_go_no_go_skill.py::TestGoNoGoWaiverStampRegardlessOfFindings`)
- [x] `rn-remediate.yaml` `check_readiness` left without `--honor-waiver` (decision recorded in Wiring Phase — no code change)
- [x] Item 4 fixed: `record_decision_unresolved` now writes `decision_unresolved` directly to `refine-terminal-class` (mirroring `mark_rate_limit_infra`), `next: failed` preserved, write assertion added (`test_record_decision_unresolved_writes_refine_terminal_class`)
- [x] `ll-loop validate autodev` and `ll-loop validate refine-to-ready-issue` clean; `python -m pytest scripts/tests/` passes (23128 passed, 43 skipped)

## Resolution

All six Summary defects and the previously-remaining doc/test gaps are now closed:

- Items 1, 2, 3, 5, 6 were already landed in `3e798eeac`/`caddec57b` prior to this pass (see Codebase Research Findings above).
- Item 4 (double ledger on decision-unresolved): root-caused via a direct `refine-terminal-class` write in `record_decision_unresolved` (`refine-to-ready-issue.yaml`), mirroring the existing `mark_rate_limit_infra` pattern. `skip_inflight`'s ledger-grep suppression stays in place as a second, now-redundant safety net.
- `docs/guides/LOOPS_REFERENCE.md`: rewrote the BUG-2744 guard-2 paragraph for the positive fail-closed marker, added the go-no-go escalation chain and `verify_impl_closed` to the diagram-omissions/prose, and corrected the stale four-entry-point decidability description (superseded by ENH-3075's sub-loop refactor but never updated) to five entries.
- `skills/audit-loop-run/SKILL.md`: reframed the `oversized_atomic` paragraph to describe the automated one-shot go-no-go escalation, with manual waiver review as the fallback only when that attempt already ran (or the issue wasn't eligible).
- Added test coverage for item 6 (`test_go_no_go_skill.py`) and item 4 (`test_builtin_loops.py`).

## Status

**Done** | Created: 2026-09-04 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-09-05T17:58:53 - `feee162a-3cb7-4905-b19e-dab36da67db1.jsonl`
- `/ll:ready-issue` - 2026-09-05T17:43:22 - `d7442692-130e-400a-9f60-d1270eae1420.jsonl`
- `/ll:confidence-check` - 2026-09-05T17:28:26 - `42bd48b8-704c-4d15-b248-a77d6a520c33.jsonl`
- `/ll:wire-issue` - 2026-09-05T04:57:34 - `7ad2c895-8f68-4859-96fb-41e7c667e5b1.jsonl`
- `/ll:refine-issue` - 2026-09-05T04:32:46 - `251307a7-40ea-42f4-beb3-43e6b4de6744.jsonl`
- `/ll:format-issue` - 2026-09-05T04:22:41 - `adb409c3-bb29-46e0-a080-e89ad1cec8e0.jsonl`
