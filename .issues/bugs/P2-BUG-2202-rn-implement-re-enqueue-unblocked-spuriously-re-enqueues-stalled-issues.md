---
id: BUG-2202
title: 'rn-implement: re_enqueue_unblocked spuriously re-enqueues stalled issues'
type: BUG
priority: P2
status: open
discovered_date: 2026-06-17
discovered_by: audit-loop-run
captured_at: '2026-06-17T02:40:00Z'
relates_to:
  - ENH-2195
labels:
  - rn-implement
  - orchestration
  - queue
---

# BUG-2202: rn-implement — re_enqueue_unblocked spuriously re-enqueues stalled issues

## Summary

`re_enqueue_unblocked` (added by ENH-2195) checks whether all `blocked_by` deps are done and
re-enqueues if so — but it does not check *why the issue was deferred*. An issue deferred for
"remediation stalled" gets re-enqueued if its `blocked_by` deps happen to be done, triggering a
wasteful second remediation pass that reaches the same stall.

## Reproduction (from run 2026-06-17T002343 / rn-implement)

1. FEAT-1156 is deferred in pass 1 — reason: `"remediation stalled (scores did not converge
   across passes)"`. Deferral line in `deferred.txt`:
   ```
   FEAT-1156  remediation stalled (...) and decomposition declined to split; ...
   ```
2. FEAT-1262 is implemented.
3. `re_enqueue_unblocked` runs. It reads FEAT-1156's `blocked_by: FEAT-1112` frontmatter, sees
   FEAT-1112 is `done` → no unmet deps → re-enqueues FEAT-1156.
4. FEAT-1156 enters a second remediation pass (13 more iterations) → same stall → deferred again.
   **Wasted: ~13 loop iterations and ~10 minutes of wall-clock time.**

## Root Cause

`re_enqueue_unblocked` action in `loops/rn-implement.yaml` (`re_enqueue_unblocked` state):

```bash
# Current logic (simplified):
for each line in deferred.txt:
    ID = line[0]
    UNMET = check_blocked_by_deps(ID)
    if UNMET is empty:
        re-enqueue ID   # <-- re-enqueues regardless of deferral reason
```

The `deferred.txt` format already encodes the reason:
- `FEAT-1156  remediation stalled ...` — deferred for stall, NOT for blocked deps
- `FEAT-1157  blocked_by FEAT-1156 (not done)` — deferred for unmet dep (correct to re-enqueue)

## Fix

Filter `deferred.txt` entries by reason before checking deps. Only re-enqueue entries whose
reason line contains `blocked_by`:

```bash
# In the re_enqueue_unblocked while-loop:
REASON=$(echo "$line" | cut -d' ' -f2-)
if ! echo "$REASON" | grep -q "blocked_by"; then
    echo "$line" >> "$NEW_DEFERRED"   # keep in deferred; not blocked-by-driven
    continue
fi
# Existing blocked_by dep check follows...
```

Alternatively, parse the deferred reason from a structured format (e.g. JSON per entry) to
make filtering unambiguous.

## Impact

- Every run that implements any issue after a stalled issue causes the stalled issue to be
  re-attempted, burning iterations and time with zero probability of different outcome.
- In the observed run: 13 wasted depth-0 iterations + 13 wasted depth-1 (rn-remediate) iterations.

## Acceptance Criteria

- [ ] `re_enqueue_unblocked` only re-enqueues entries whose deferral reason contains `blocked_by`
- [ ] Issues deferred for "remediation stalled", "depth-capped", "skipped", etc. remain in
      `deferred.txt` unchanged after `re_enqueue_unblocked` runs
- [ ] Add a test: seed `deferred.txt` with a stalled entry + a blocked entry; after implementing
      the blocker dependency, only the blocked entry is re-enqueued
