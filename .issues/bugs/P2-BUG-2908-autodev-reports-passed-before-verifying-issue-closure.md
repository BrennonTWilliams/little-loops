---
id: BUG-2908
type: BUG
priority: P2
status: open
captured_at: "2026-07-29T02:59:11Z"
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

## Session Log
- `/ll:capture-issue` - 2026-07-29T02:59:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a15bf47-b270-4d12-a74c-47b9c005a000.jsonl`

---

## Status

`open`
