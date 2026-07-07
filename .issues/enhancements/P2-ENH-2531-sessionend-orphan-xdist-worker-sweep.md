---
id: ENH-2531
title: "SessionEnd defensive sweep for orphaned pytest-xdist workers"
type: ENH
priority: P2
status: done
captured_at: '2026-07-07T21:38:05Z'
discovered_date: 2026-07-07
discovered_by: audit
size: Small
completed_at: '2026-07-07T21:38:05Z'
labels:
- hooks
- tests
- performance
---

# ENH-2531: SessionEnd defensive sweep for orphaned pytest-xdist workers

## Summary

Killed pytest runs leave xdist workers behind: `setproctitle` rewrites their
command line to `[pytest-xdist running]`, so `pkill -f "pytest scripts/tests"`
misses them, and each orphan spins at ~100% CPU (cumulative load=20 spikes
observed). Added a SessionEnd hook that reaps them.

Source: audit run `.loops/runs/general-task-20260707T133447/audit-report.md`
(S6 / Finding #2 / Recommendation R2).

## Implementation

- New `hooks/scripts/orphan-worker-sweep.sh`, registered as a second
  `SessionEnd` entry in `hooks/hooks.json` (after `scratch-cleanup.sh`).
- **Deviation from the audit's recipe:** the report suggested a blanket
  `pkill -9 -f "pytest-xdist running"`, which would also kill workers of a
  pytest run still live in a concurrent session. The sweep instead kills only
  workers reparented to init (PPID 1) — the audit's own orphan definition —
  via `ps -axo pid,ppid,command` + awk.
- Avoids the documented `pgrep -af` self-match trap by building the match
  needle from a split literal so the pipeline never matches itself.
- Cleanup-script contract: never fails; always exits 0.

## Verification

- `bash -n` syntax check and a live run of the script (exit 0, no-op with
  zero orphans present).
- `hooks/hooks.json` validated as JSON after the edit.
