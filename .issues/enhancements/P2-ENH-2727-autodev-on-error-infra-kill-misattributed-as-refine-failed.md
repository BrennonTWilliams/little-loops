---
id: ENH-2727
title: autodev refine_current on_error collapses infra kills into the refine_failed
  ledger reason
type: ENH
status: open
priority: P2
captured_at: '2026-07-21T22:10:00Z'
discovered_date: '2026-07-21'
discovered_by: audit-loop-run
labels:
- loops
- fsm
- termination-taxonomy
relates_to:
- ENH-1679
- ENH-2522
- ENH-2404
---

# ENH-2727: autodev `refine_current.on_error` collapses infra kills into the `refine_failed` ledger reason

## Summary

In `scripts/little_loops/loops/autodev.yaml`, `refine_current` routes
`on_no: skip_inflight` and `on_error: skip_inflight` — the same target.
`skip_inflight` appends a hard-coded reason:

```
echo "${captured.input.output}  refine_failed" >> ${context.run_dir}/autodev-skipped.txt
```

An infrastructure failure (host CLI SIGTERM'd, OOM, crash) is therefore ledgered
identically to a genuine refine-quality failure. ENH-1679 fixed the earlier
`on_yes == on_no` laundering; the `on_error == on_no` collapse remains.

## Evidence (run `2026-07-21T214941-autodev`)

The refine sub-loop's `refine_issue` action exited **143 (SIGTERM, external kill
after 156s)**, yet `autodev-skipped.txt` records `ENH-2722  refine_failed` — the
operator-facing summary and any downstream triage (`ll-issues deferred-triage`,
`skipped_breakdown`) cannot distinguish "refine produced a bad result" from "the
process was killed mid-flight; just re-run it".

## Proposed Fix

Route `on_error` to a distinct state (e.g. `skip_inflight_infra`) that ledgers a
different reason code (`infra_error` or `refine_killed`), mirroring the
ENH-2005 artifact-channel guidance that infra crashes be attributed separately.
Alternatively keep one state but interpolate a reason derived from the sub-loop
verdict/exit code.

> **Decided (2026-07-22, coordinated with [[BUG-2731]]'s `/ll:refine-issue`
> pass):** new-state shape (Option A above) selected via `/ll:decide-issue`
> on BUG-2731 (10/12 vs 7/12 — see BUG-2731's Decision Rationale). Reason-code
> literal: `refine_failed_infra`, not `infra_error`/`refine_killed` — derived
> from `record_gate_error`'s `GATE_FAILED_INFRA` precedent (stem-suffix on the
> existing failure token), case-matched to `skip_inflight`'s lowercase
> convention. See BUG-2731's Proposed Solution for the full reasoning; both
> issues should land on this same literal string.

## Acceptance Criteria

- [ ] `on_error` from `refine_current` produces a ledger entry with a reason code
      distinct from `refine_failed`
- [ ] The `done` summary surfaces infra-skipped issues separately (re-runnable)
- [ ] `ll-loop validate autodev` passes; existing routing tests updated


## Session Log
- `/ll:refine-issue` - 2026-07-22T02:53:11 - `7f3d9a33-9486-4122-8fd1-85fd59741abd.jsonl`
- `/ll:verify-issues` - 2026-07-21T23:08:30 - `9fc8185c-278a-4573-8071-af3d44765f41.jsonl`
