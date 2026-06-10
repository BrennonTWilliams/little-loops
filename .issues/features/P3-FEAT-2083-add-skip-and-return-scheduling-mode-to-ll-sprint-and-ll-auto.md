---
id: FEAT-2083
title: Add skip-and-return scheduling mode to ll-sprint and ll-auto
type: FEAT
priority: P3
status: open
captured_at: "2026-06-10T18:12:09Z"
discovered_date: "2026-06-10"
discovered_by: capture-issue
relates_to: [EPIC-2087]
---

# FEAT-2083: Add skip-and-return scheduling mode to ll-sprint and ll-auto

## Motivation

Sprint and auto processing currently run issues in fixed priority order. Strong agents skip hard problems and return after building supporting infrastructure — a dynamic deferral strategy that improves throughput. When a Claude session encounters a blocked or unexpectedly complex issue mid-sprint, there is no mechanism to defer it and proceed to unblocked work.

## Use Case

During a sprint, an issue blocks because a dependency isn't merged. Rather than failing the sprint or halting, `ll-sprint --skip-on-block` defers the blocked issue and continues processing the next unblocked issues. After all unblocked issues complete, the deferred set is retried automatically.

## Proposed Solution

Add a `--skip-on-block` flag to `ll-sprint` and `ll-auto` that enables runtime deferral:
- If a session emits a `BLOCKED` signal or exceeds a per-issue iteration ceiling, push the issue to a deferred queue
- Continue with the next unblocked issue in the sprint
- Retry deferred issues after all initially-unblocked issues complete
- Persist the deferred queue to `${run_dir}/deferred.json` so it survives interruptions
- Log skip/return events in the sprint summary

## Implementation Steps

1. Add `--skip-on-block` flag to `ll-sprint` and `ll-auto` CLI parsers
2. Implement `BLOCKED` signal detection from session output
3. Add per-issue iteration ceiling check
4. Implement deferred queue with persistence to `${run_dir}/deferred.json`
5. Add retry pass after initial unblocked issues complete
6. Log skip/return events in sprint summary output

## Acceptance Criteria

- [ ] `ll-sprint --skip-on-block` defers blocked issues and continues with unblocked ones
- [ ] `ll-auto --skip-on-block` applies the same deferral behavior
- [ ] Deferred queue persists to `${run_dir}/deferred.json`
- [ ] Deferred issues are retried after initial pass completes
- [ ] Sprint summary includes skip/return event log

## Status

open
