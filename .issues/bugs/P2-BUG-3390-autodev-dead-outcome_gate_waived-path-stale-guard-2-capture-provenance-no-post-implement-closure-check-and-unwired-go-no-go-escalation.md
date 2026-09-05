---
id: BUG-3390
type: BUG
title: 'autodev: dead outcome_gate_waived path, stale guard-2 capture provenance,
  no post-implement closure check, and unwired go-no-go escalation'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-04'
captured_at: '2026-09-04T21:11:07Z'
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

**Working-tree state as of this pass**: items 1, 2, 3, 5, 6 of the Summary already have implementations present in the uncommitted working tree (matches `git status`: `check_readiness.py`, `show.py`, `autodev.yaml`, `skills/go-no-go/SKILL.md` all modified, not committed).

- Item 1 (`outcome_gate_waived` round-trip + `--honor-waiver` + go-no-go escalation): `ReadinessStatus.outcome_gate_waived`/`meets_outcome_or_waived` (`check_readiness.py:16-55`); `--honor-waiver` wired at `check_readiness.py:147-181` and CLI registration `cli/issues/__init__.py:778-787,1052-1053`; `show.py:148,349-351` emits the key; `autodev.yaml` `check_passed`/`recheck_after_decide`/`recheck_scores` all pass `--honor-waiver` (test: `test_check_readiness_call_sites_pass_honor_waiver`, `test_builtin_loops.py:7488-7494`). Threshold precedence confirmed: explicit CLI `--readiness`/`--outcome` now overwrites the config-or-default value (`check_readiness.py:119-122`) — matches the issue's Expected Behavior. New states `check_go_no_go_eligible → run_go_no_go → check_go_no_go_waiver → reopen_waived` exist at `autodev.yaml:1963-2048`, wired from `check_atomic_design_remedy.on_no` (`autodev.yaml:1960`), matching the Program Design call path exactly.
- Item 2 (guard-2 provenance): positive marker `autodev-size-review-ran-this-pass` written by `count_repair_cycle_size_review` (`autodev.yaml:1505`), required by `check_size_review_ran_this_pass` (`autodev.yaml:1731-1750`, fails closed `on_no`/`on_error → recheck_after_size_review`), cleared per-issue at `dequeue_next` (`autodev.yaml:116`).
- Item 3 (post-implement closure): new state `verify_impl_closed` (`autodev.yaml:921-951`) sits between `implement_current.on_yes` and `dequeue_next`; ledgers `impl_exit0_not_closed` to `autodev-unverified.txt` when status isn't closed; clears `autodev-inflight` unconditionally on both branches (`autodev.yaml:935`).
- Item 5 (inert rate-limit keys): `refine_current` (`autodev.yaml:472-510`) already declares neither `fragment: with_rate_limit_handling` nor `on_rate_limit_exhausted`. Structural test `test_no_loop_call_state_declares_on_rate_limit_exhausted` (`test_builtin_loops.py:7471-7486`) enumerates the exact `loop:` state set (`{"refine_current", "resolve_decision", "resolve_decision_direct"}`) and asserts neither key on any of them; a parallel test for `refine-to-ready-issue.yaml` exists at `test_builtin_loops.py:3048-3061`.
- Item 6 (go-no-go waiver stamp): `skills/go-no-go/SKILL.md:402` adds an explicit paragraph headed "`outcome_gate_waived` escalation (BUG-2734)" beneath Step 3f's findings-write gate, directing the waiver stamp regardless of `HAS_FINDINGS`, citing BUG-3390 by name.

**Remaining true gap — item 4 is downstream-mitigated only, not root-caused-fixed**: `refine-to-ready-issue.yaml`'s `record_decision_unresolved` (`refine-to-ready-issue.yaml:897-925`) still exits via `next: failed`/`on_error: failed` without calling `classify_terminal` — confirmed absent from that state's block. The double-ledger consequence is instead suppressed one hop downstream: `autodev.yaml`'s `skip_inflight` (`autodev.yaml:512-556`) greps `autodev-decision-unresolved.txt` for the ID via whole-line match (`grep -qxF`, `autodev.yaml:544-549`) and skips writing `refine_failed` when found, tested by `test_skip_inflight_skips_refine_failed_when_decision_unresolved_ledgered` and `test_skip_inflight_decision_ledger_match_is_whole_line` (`test_builtin_loops.py:7502-7520`). This fixes autodev's own ledger but leaves `record_decision_unresolved` itself uncorrected for any other caller that expects `classify_terminal` to have run on this path.

**Consequence for Acceptance Criteria below**: the AC rows for items 1, 2, 3, 5, 6 describe behavior that already exists uncommitted in the working tree — verify by running `ll-loop validate autodev` and the cited tests rather than treating them as unimplemented. Only the `record_decision_unresolved`/`classify_terminal` root-cause gap (item 4) and the final validate/pytest gate remain outstanding.

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
- Update `docs/guides/LOOPS_REFERENCE.md` (references deleted `run_decide`, omits ~18 states, four-vs-five entry points).

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
- `scripts/little_loops/cli/issues/check_readiness.py` — `--honor-waiver`, explicit-override precedence
- `scripts/little_loops/loops/autodev.yaml` — go-no-go escalation states, positive size-review marker, `verify_impl_closed`, `skip_inflight` fix, drop inert rate-limit keys from `refine_current`
- `skills/go-no-go/SKILL.md` — stamp the waiver on GO regardless of `HAS_FINDINGS`
- `docs/guides/LOOPS_REFERENCE.md` — correct state inventory and entry points

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/__init__.py` — `check-readiness` CLI wiring
- `loops/refine-to-ready-issue.yaml` — `record_decision_unresolved` interacts with autodev's `skip_inflight`

### Similar Patterns

- `scripts/tests/test_autodev_decision_gate.py`, `scripts/tests/test_autodev_loop.py` — existing gate/loop test conventions to extend

### Tests

- `scripts/tests/test_check_readiness.py` — `--honor-waiver` cases
- `scripts/tests/test_autodev_loop.py`, `scripts/tests/test_autodev_decision_gate.py` — new states/markers
- `scripts/tests/test_fsm_topology.py` — forbid `on_rate_limit_exhausted`/`with_rate_limit_handling` on `loop:` states
- `scripts/tests/test_builtin_loops.py` — `ll-loop validate autodev`

### Documentation

- `docs/guides/LOOPS_REFERENCE.md`

### Configuration

- N/A

### Behavior Parity

| File | Preserved | Changed | Dropped |
|------|-----------|---------|---------|
| `docs/guides/LOOPS_REFERENCE.md` | Overall guide structure and unrelated state descriptions | State inventory corrected to include the ~18 currently-omitted states and the true four-vs-five entry-point count | Reference to the deleted `run_decide` state |

## Impact

- **Priority**: P2 - dead escalation/closure paths silently block issue closure and mask no-op successes in unattended `ll-auto` runs; not P1 because each defect has a manual workaround (re-run, manual waiver edit)
- **Effort**: Medium - six largely independent fixes spanning `check_readiness.py`, `show.py`, `autodev.yaml` (new states/markers), and `go-no-go` SKILL.md, plus test coverage for each
- **Risk**: Medium - touches the core autodev gate/guard states that mediate every automated issue closure; a regression could silently block or wrongly pass issues in unattended runs, mitigated by `ll-loop validate` and the existing gate/loop test suites
- **Breaking Change**: No - additive states/flags/markers; existing `check-readiness` callers without `--honor-waiver` keep current behavior

## Acceptance Criteria

- [ ] `ll-issues show <ID> --json` emits `outcome_gate_waived`
- [ ] `ll-issues check-readiness <ID> --honor-waiver` passes the outcome half when the flag is set; readiness still enforced; explicit `--readiness/--outcome` override config
- [ ] `check_passed`, `recheck_after_decide`, `recheck_scores` pass `--honor-waiver`
- [ ] go-no-go escalation states exist with one-shot marker; `check_atomic_design_remedy.on_no → check_go_no_go_eligible`
- [ ] `check_size_review_ran_this_pass` requires the positive marker; only `count_repair_cycle_size_review` writes it; `on_error → recheck_after_size_review`
- [ ] `implement_current.on_yes → verify_impl_closed`; unverified ledger line `ID  impl_exit0_not_closed`; inflight cleared on both branches; `finalize_done` counts a reasoned line once
- [ ] `skip_inflight` does not ledger `refine_failed` for an ID already in `autodev-decision-unresolved.txt`
- [ ] No `loop:` state in autodev declares `on_rate_limit_exhausted` or `with_rate_limit_handling`
- [ ] `ll-loop validate autodev` clean; `python -m pytest scripts/tests/` passes

## Status

**Open** | Created: 2026-09-04 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-09-05T04:32:46 - `251307a7-40ea-42f4-beb3-43e6b4de6744.jsonl`
- `/ll:format-issue` - 2026-09-05T04:22:41 - `adb409c3-bb29-46e0-a080-e89ad1cec8e0.jsonl`
