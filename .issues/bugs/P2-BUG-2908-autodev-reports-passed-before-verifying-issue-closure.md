---
id: BUG-2908
type: BUG
priority: P2
status: done
captured_at: '2026-07-29T02:59:11Z'
completed_at: '2026-07-29T04:50:43Z'
discovered_date: 2026-07-29
discovered_by: capture-issue
labels:
- loops
- fsm
- autodev
- observability
relates_to:
- BUG-2907
- BUG-2636
confidence_score: 100
outcome_confidence: 76
score_complexity: 14
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 20
---

# BUG-2908: `autodev` reports `Passed` at threshold-pass time, never verifying closure

## Summary

`autodev.yaml` appends an issue ID to `autodev-passed.txt` in `check_passed`,
which runs *before* `implement_current`. Nothing ever revokes that entry if the
implementation no-ops or fails, so `finalize_done` reports `Passed (1)` for a run
that closed nothing. The loop emits no `summary.json` and no verdict at all, so
there is no channel through which a failed implementation could downgrade the
run. The audited run reached terminal `done` with FEAT-108 still `status: open`.

## Steps to Reproduce

1. Pick an issue whose readiness/outcome scores pass the configured thresholds
   (defaults 85 / 65) but whose implementation cannot complete — e.g. one with an
   unmet `blocked_by` edge, which makes `ll-auto --only` a no-op (BUG-2907).
2. Run `ll-loop run autodev <ID>`.
3. Observe the run reaches terminal `done`, `failure_terminal: false`.
4. Read the `finalize_done` summary: `Passed (1): <ID>` printed alongside
   `WARNING: in-flight issue not resolved: <ID>`.
5. `ll-issues show <ID> --json` → `status: Open`.
6. `ls .loops/.history/<run>/summary.json` → absent.

## Current Behavior

`check_passed` (`scripts/little_loops/loops/autodev.yaml`) writes on threshold
pass alone:

```yaml
  check_passed:
    action: |
      ll-issues check-readiness ... \
        && echo "${captured.input.output}" >> ${context.run_dir}/autodev-passed.txt
    on_yes: implement_current
```

The same pre-implementation write appears in `recheck_scores` and the other
recheck/regate states. `finalize_done` then counts that file directly:

```yaml
      PASSED_IDS=$(cat ${context.run_dir}/autodev-passed.txt ... | sort -u || true)
      PASSED_COUNT=$(echo "$PASSED_IDS" | grep -c '[^[:space:]]' || true)
      ...
      printf 'Passed       (%d): %s\n' "$PASSED_COUNT" "$${PASSED_LIST:-none}"
      ...
      INFLIGHT=$(cat ${context.run_dir}/autodev-inflight ...)
      if [ -n "$INFLIGHT" ]; then
        printf 'WARNING: in-flight issue not resolved: %s (re-queue to retry)\n' "$INFLIGHT"
      fi
```

`finalize_done` already holds the contradicting evidence and prints both lines
side by side without reconciling them. Observed verbatim from the audited run:

```
=== Autodev Summary ===

Passed       (1): FEAT-108
Skipped      (0): none
WARNING: in-flight issue not resolved: FEAT-108 (re-queue to retry)
```

`ll-issues show FEAT-108 --json` after the run: `status: Open`.

`finalize_done` has `next: done` unconditionally — no exit-code branch, no
`summary.json`, no verdict token.

## Expected Behavior

An ID reaches `autodev-passed.txt` only after its status is verified to be
`done` or `cancelled`. Anything staged-but-unclosed at finalize is reported in
its own bucket with a distinct reason, and the run's verdict reflects it:

```
=== Autodev Summary ===

Passed       (0): none
Unverified   (1): FEAT-108  (threshold passed; implementation did not close — re-queue to retry)
```

`finalize_done` emits a `summary.json` carrying at minimum `verdict`, `closed`,
`not_closed`, `inflight_unresolved`, and `abandoned`, and exits non-zero on a
`phantom` verdict so the run does not render green `done`.

## Motivation

This is the defect class BUG-2636 already fixed in the sibling loop
`auto-refine-and-implement.yaml`, which now emits `verdict=phantom` /
`incomplete-abandoned` → `exit 1` with `inflight_unresolved` and `abandoned`
counts in `summary.json`. `autodev` never received the same treatment despite
being the loop that sibling *delegates to*, so a phantom autodev run is
laundered into a green terminal at the layer where operators actually look.

`autodev` also currently violates **MR-13** (`.claude/CLAUDE.md`): it has an
abandonment mechanism (`autodev-inflight`, `autodev-skipped.txt`) but no state
emitting an `"abandoned"` key into a summary JSON, and no conditional branch on
a failure counter. Fixing this closes the lint violation as a side effect.

## Root Cause

Two coupled facts:

1. `check_passed` (and its `recheck_*` / `regate_*` twins) treat "readiness and
   outcome thresholds passed" as the success event, when the loop's actual
   deliverable is issue closure. The write happens one state too early.
2. `finalize_done` has no verdict model — it prints a summary and unconditionally
   routes `next: done`, so even a correctly-computed failure count would have
   nowhere to go.

## Proposed Solution

Port BUG-2636's verdict model from `auto-refine-and-implement.yaml` rather than
inventing new bash.

**Step 1 — stage instead of pass.** In `check_passed`, `recheck_scores`, and the
other recheck/regate writers, redirect to `autodev-staged.txt`:

```yaml
  check_passed:
    action: |
      ll-issues check-readiness ${captured.input.output} \
        --readiness ${context.readiness_threshold} \
        --outcome ${context.outcome_threshold} \
        && echo "${captured.input.output}" >> ${context.run_dir}/autodev-staged.txt
```

**Step 2 — promote on verified closure in `finalize_done`.** Reuse the
already-present `mark_gate_blocked` status-probe idiom (which correctly handles
the display-cased `ll-issues show --json` status — see
`reference_ll_issues_show_json_status_display_cased`):

```yaml
      STAGED=$(cat ${context.run_dir}/autodev-staged.txt 2>/dev/null \
        | grep -v '^[[:space:]]*$' | sort -u || true)
      : > ${context.run_dir}/autodev-unverified.txt
      for ID in $STAGED; do
        STATUS=$(ll-issues show "$ID" --json 2>/dev/null \
          | python3 -c "import json,sys; print((json.load(sys.stdin).get('status') or '').lower())" \
          2>/dev/null || echo "")
        case "$STATUS" in
          done|completed|cancelled)
            echo "$ID" >> ${context.run_dir}/autodev-passed.txt ;;
          *)
            echo "$ID" >> ${context.run_dir}/autodev-unverified.txt ;;
        esac
      done
```

Note the `done|completed|cancelled` triple — `--json` returns display-cased
values, so lowercase *and* accept the `completed` synonym.

**Step 3 — verdict + summary.json + non-zero exit.** Mirror
`auto-refine-and-implement.yaml`'s finalize: compute `VERDICT` (`success` /
`partial` / `phantom` — `phantom` when `closed == 0` and staged/inflight > 0),
`printf` a `summary.json` with the `verdict` / `closed` / `not_closed` /
`inflight_unresolved` / `abandoned` keys, and `exit 1` on `phantom` so the run
routes to a `failed`-class terminal instead of `done`.

**Step 4 — fold the inflight warning into accounting.** Any residual
`autodev-inflight` at finalize is written to `autodev-unverified.txt` with reason
`inflight_at_finalize` rather than being printed as a standalone advisory.

## Integration Map

- `scripts/little_loops/loops/autodev.yaml` — `check_passed`, `recheck_scores`,
  `regate_after_atomic_remediation` and the other `autodev-passed.txt` writers
  (grep shows writes at 6 distinct sites); `finalize_done`; the `failed` terminal
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — the reference
  implementation to port (`verdict` / `summary.json` / `exit 1` block); it
  *consumes* autodev's outcome, so its own verdict recovery must be re-checked
  against the new summary
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop`; BUG-2636's
  `TestAutoRefineAndImplementLoop` is the pattern for the assertions
- `scripts/little_loops/fsm/validation/` — MR-13 lint (`abandonment_verdict_ok`)
  should stop flagging `autodev` once this lands

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- All 6 `autodev-passed.txt` write sites in `scripts/little_loops/loops/autodev.yaml`,
  confirmed by line number:
  - `init` (line 63) — clears the file (`printf '' > ${context.run_dir}/autodev-passed.txt`), not an append
  - `check_passed` (line 365) — the site quoted in Current Behavior above
  - `recheck_after_decide` (line 539) — same `check-readiness && echo ... >>` shape,
    reached via `on_yes: assert_decision_cleared` → still pre-implementation
  - `recheck_scores` (line 983) — readiness/outcome + Program-Design hard-AND gate
  - `regate_after_atomic_remediation` (line 1492) — `GATE=PASS` python-computed
    gate (checks `confidence`/`outcome`/`outcome_gate_waived` via
    `ll-issues show --json`), not a `check-readiness` shell call like the others
  - `recheck_after_size_review` (line 1656) — same `GATE=PASS` shape as
    `regate_after_atomic_remediation`
  - So Step 3's "redirect every writer" touches 5 append sites (the `init`
    clear stays as-is, just renamed to `autodev-staged.txt`).
- `finalize_done` spans lines 1792–1859; the `failed` terminal immediately
  follows at 1860–1862 and is reached only via `finalize_done`'s `on_error`
  (per the ENH-2825 comment at 1857–1859) — i.e. only if the summary-printing
  shell itself throws, never as a function of ledger contents. This confirms
  Root Cause point 2: there is no verdict-driven route to `failed` today.
- `auto-refine-and-implement.yaml`'s `finalize` state spans lines 692–982.
  It does **not** read any `summary.json` from autodev (autodev writes none) —
  it re-derives ground truth independently from `.issues/completed/` and
  `ll-issues list --json --status done` diffs against a pre-run baseline, and
  treats `autodev-passed.txt` as unverified raw input feeding its own
  `NOT_CLOSED` computation (`comm -23` at lines 817–828). Concretely:
  - `CLOSED` union computed at lines 716–772
  - `NOT_CLOSED` = passed-ledger minus closed-union, lines 817–828
  - `VERDICT` cascade (`incomplete-abandoned` > `success` > `partial-with-errors`
    > `partial` > `phantom` > `no-op`) at lines 937–953
  - `summary.json` emission at lines 955–956; exit-code branch
    (`phantom|incomplete-abandoned` → `exit 1`) at lines 964–981
  - This is the exact shape Proposed Solution Step 3 should port.
- `delegate` (lines 258–281) in `auto-refine-and-implement.yaml` routes both
  `on_success` and `on_failure` to `recheck_set` regardless of autodev's
  terminal name — the comment at 262–264 notes this is deliberate, since
  `finalize`'s ground-truth diff is already treated as authoritative. This
  means Implementation Step 7 ("re-check auto-refine-and-implement's verdict
  recovery") is lower-risk than it sounds: the parent loop does not currently
  branch on autodev's terminal at all, only on the shared ledger files, so
  adding `autodev-staged.txt`/`autodev-unverified.txt` alongside the existing
  `autodev-passed.txt` should not require changing `delegate`'s routing —
  only confirming `finalize`'s `NOT_CLOSED` diff still sees the same (now
  correctly-gated) `autodev-passed.txt` contents.
- Existing `ll-issues show <ID> --json` + lowercase-status idiom (the same
  one this issue's Proposed Solution Step 2 already specifies) is already used
  three more times in `autodev.yaml` itself — `mark_gate_blocked` (~line 733),
  `record_decision_unresolved` (~line 571), `check_parent_resolved` (~line 896)
  — confirming it's the established in-repo convention, not a new idiom.
- MR-13 lint (`abandonment_verdict_ok`) lives in
  `scripts/little_loops/fsm/validation/evaluator_rules.py` lines 160–238
  (suppression flag registered in `_base.py:124`). The rule requires either an
  abandonment-counter-gated verdict branch or a literal `"abandoned":` key in
  the same `printf`/write — port the `"abandoned":%s` field name verbatim from
  `auto-refine-and-implement.yaml` line 955–956 to satisfy it without needing
  the suppression flag.
- Test file: `scripts/tests/test_builtin_loops.py` — `TestAutoRefineAndImplementLoop`
  spans lines 2508–3577 (`test_finalize_writes_summary_json` at line 2573 is
  the closest existing model). `TestAutodevLoop` spans lines 4127–6126; there
  is currently no test asserting closure verification in `finalize_done` —
  confirming this is a real gap, not just an operational observation.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — line 977 references `autodev-passed.txt`/`autodev-skipped.txt` closure accounting, and the FSM flow diagram (lines 998–1050) has no `failed` terminal edge at all, only `done`. Both go stale once the ledger is renamed and `finalize_done` gains a `phantom` → `failed` route — update the diagram and the ledger-name prose together.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestAutoRefineAndImplementLoop::test_finalize_sources_autodev_ledgers` (~line 2866) — asserts `"autodev-passed.txt" in action` against `auto-refine-and-implement.yaml`'s own `finalize` action, which reads autodev's ledger directly (see `auto-refine-and-implement.yaml` line 821's `NOT_CLOSED` diff). Once autodev only populates `autodev-passed.txt` post-verification inside `finalize_done`, this cross-loop consumer's read must be re-verified for ordering (does `auto-refine-and-implement`'s `finalize` run after autodev's `finalize_done` has already promoted verified IDs?) — not just the literal string.
- `scripts/tests/test_fsm_validation_evaluator_rules.py` — covers the MR-13 `abandonment_verdict_ok` rule (`scripts/little_loops/fsm/validation/evaluator_rules.py` lines 160–238, flag registered in `scripts/little_loops/fsm/validation/_base.py:124`); needs a case confirming `autodev.yaml` no longer triggers the warning once `finalize_done` emits the `"abandoned"` key.
- `scripts/tests/test_builtin_loops.py::TestAutodevLoop::test_finalize_done_buckets_already_resolved_separately` (~line 4666) — asserts literal `printf`-derived stdout lines (`"Passed"`/`"Skipped"`/`"Already-resolved"`) from the current unconditional summary format; breaks once `finalize_done` moves to `summary.json`-based verdict emission and must be rewritten against the new JSON keys (or kept alongside the `printf` block if both are retained).
- `scripts/tests/test_builtin_loops.py::TestAutoRefineAndImplementLoop::test_finalize_stale_inflight_counts_as_unresolved` (line 3302) and `test_finalize_inflight_not_counted_when_issue_closed` (line 3316) — closest existing analog to the closure-verification gap this issue fixes; fork `finalize_done`'s new tests from these rather than from scratch. Reuse the `_run_finalize`-style harness (`_write_done_in_place_fixture` line 2874, `_run_finalize` line 2886) and the `script.replace("$${", "${")` bash-unescape convention (line 4683) when executing `finalize_done`'s raw action under `bash -c`.

## Implementation Steps

1. Read `auto-refine-and-implement.yaml`'s finalize block end to end; it is the
   contract to match, including the `exit 1` verdict routing.
2. Add failing tests: a simulated run where thresholds pass but the issue stays
   `open` must produce `Passed (0)`, a non-empty unverified bucket,
   `verdict: phantom` in `summary.json`, and a non-`done` terminal.
3. Redirect every `autodev-passed.txt` writer to `autodev-staged.txt`.
4. Add the closure-verification promotion loop to `finalize_done`.
5. Add `summary.json` emission and the `phantom` → `exit 1` branch; wire the
   `on_error`/failure route (`finalize_done` currently has `on_error: failed`
   per ENH-2825 — reuse that terminal).
6. Confirm `ll-loop validate autodev` no longer reports the MR-13 warning.
7. Re-check `auto-refine-and-implement`'s verdict recovery against the new
   autodev summary so the parent does not double-count.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `auto-refine-and-implement.yaml`'s `finalize` state (line 821's `NOT_CLOSED` diff, and the `test_finalize_sources_autodev_ledgers` test) to read the post-verification `autodev-passed.txt` — confirm `finalize_done` runs and promotes verified IDs before the parent loop's `finalize` reads the shared `run_dir`, or switch the parent to read autodev's new `summary.json` `closed`/`not_closed` fields directly instead of the raw ledger.
9. Update `docs/guides/LOOPS_REFERENCE.md` — the ledger-name prose (line 977) and the FSM flow diagram (lines 998–1050, which currently has no `failed` terminal edge).
10. Update `scripts/tests/test_fsm_validation_evaluator_rules.py` to assert the MR-13 `abandonment_verdict_ok` warning no longer fires on `autodev.yaml`.
11. Disambiguate the `phantom` verdict namespace: `auto-refine-and-implement.yaml`'s `finalize` already computes its own independent `phantom` verdict (line 990) into its own `summary.json`, unrelated to autodev's new `phantom` verdict — the two loops' `summary.json` files use the same term for different things; call this out in review so it isn't mistaken for the same signal.

## Impact

- **Correctness**: the loop stops reporting success for runs that closed nothing.
  This is the operator-facing half of the phantom-run defect; BUG-2907 is the
  signal half.
- **Behavior change**: runs that previously ended green `done` will now end
  non-zero when nothing closed. Any wrapper keying on autodev's terminal
  (`auto-refine-and-implement`, `ll-sprint` waves, `ll-queue` LOOP dispatch)
  needs its route re-verified.
- **Scope**: `autodev.yaml` is ~1870 lines with 6 `autodev-passed.txt` write
  sites; the change is mechanical but wide, and every site must move together or
  the accounting splits.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.claude/CLAUDE.md` § Loop Authoring (MR-13) | abandonment must reach `summary.json` and downgrade the verdict |
| `scripts/little_loops/loops/auto-refine-and-implement.yaml` | reference verdict/summary implementation from BUG-2636 |
| `audit-loop-run-autodev-2026-07-29T013824.md` | audit report with verbatim run evidence |

## Resolution

Implemented per the Proposed Solution: all 5 `autodev-passed.txt` writer sites
(`check_passed`, `recheck_after_decide`, `snap_and_size_review`,
`regate_after_atomic_remediation`, `recheck_after_size_review`) now write to
`autodev-staged.txt` instead. `finalize_done` promotes staged IDs to
`autodev-passed.txt` only after verifying `ll-issues show <ID> --json` reports
`done`/`completed`/`cancelled`; anything else lands in `autodev-unverified.txt`
and is printed as its own "Unverified" bucket. A residual `autodev-inflight`
sentinel not present in the closed set is folded into the unverified bucket
(`inflight_at_finalize`) rather than a standalone warning line. `finalize_done`
now computes a `verdict` (`success`/`partial`/`phantom`/`no-op`), writes
`summary.json` (`verdict`/`closed`/`not_closed`/`skipped`/`gate_blocked`/
`decision_unresolved`/`inflight_unresolved`/`abandoned`), and uses the
`shell_exit` fragment to route `phantom` to the existing `failed` terminal
instead of unconditionally reaching `done` — mirroring BUG-2636's fix to the
sibling `auto-refine-and-implement.yaml` loop. `ll-loop validate autodev`
reports no MR-13 violation. `auto-refine-and-implement.yaml`'s `finalize`
required no change: it already reads `autodev-passed.txt` as unverified input
and independently re-derives `NOT_CLOSED` from ground truth, so it now sees a
stricter (verified) `autodev-passed.txt` for free.

Added 5 new tests in `TestAutodevLoop` covering the staging rename, the
`shell_exit` routing, the phantom-verdict path (staged but not closed), the
success-verdict promotion path (staged and closed), and the no-op path (empty
run). Full suite (16998 passed, 42 skipped), mypy, ruff, and `ll-loop validate
autodev` all pass.

## Session Log
- `/ll:ready-issue` - 2026-07-29T04:39:37 - `af9a0a97-5511-494a-bcc3-920e9cd2b956.jsonl`
- `/ll:manage-issue` - 2026-07-29T04:49:58 - `8931f7da-faad-4eb5-a844-90797caee5f7.jsonl`
- `/ll:confidence-check` - 2026-07-28T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2828a3ac-fb8d-434e-9f4b-6464bcd9a41a.jsonl`
- `/ll:wire-issue` - 2026-07-29T04:37:08 - `e826257c-e24e-4ba3-8c9a-ad010fb5afa6.jsonl`
- `/ll:refine-issue` - 2026-07-29T04:30:27 - `02359fbd-135a-4ebd-8765-9966522956be.jsonl`
- `/ll:capture-issue` - 2026-07-29T02:59:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a15bf47-b270-4d12-a74c-47b9c005a000.jsonl`

---

## Status

`open`
