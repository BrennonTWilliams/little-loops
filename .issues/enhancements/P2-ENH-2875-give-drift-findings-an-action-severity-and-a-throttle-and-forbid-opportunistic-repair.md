---
id: 2875
title: Give drift findings an action-severity and a throttle, and forbid opportunistic repair
type: ENH
parent: EPIC-2872
priority: P2
status: open
discovered_date: 2026-07-27
labels:
- verification
- ll-doctor
---

# ENH-2875: Give drift findings an action-severity and a throttle, and forbid opportunistic repair

Origin: ll-product #ENH-059

Parent EPIC: routed alongside this issue — "Self-describing drift and deprecation signals".

## Summary

`ll-verify-docs`, `ll-check-links`, and `ll-doctor --full` all report drift as an undifferentiated list. Nothing distinguishes a finding the tool can safely fix itself from one that needs a human, or from one that a specific other command already owns. The result is a wall of findings with no encoded next action, and no throttle — so the same low-value items resurface every run until they are tuned out entirely.

## Reference pattern

In the reference pattern, staleness findings are shaped `{ id, artifact, path, severity, summary, fix }` where **severity names the action, not the badness**:

- `auto` — fixed silently on the next write to that file
- `mention` — state once
- `route` — name the command that owns the repair

Around that:

- `doctor --fix` applies **only** `auto` findings.
- Noise is throttled rather than suppressed: **one** aggregate directive per boot for the whole set, and `mention` / `route` findings repeat at most **once a week per project** via a small state file. An environment variable opts out entirely, and tests asserting on other boot output are required to set it.
- A hard behavioral rule accompanies it: **"Never repair drift as a side effect of a design task. A staleness finding is reported, not acted on, unless the user asks."**
- The boot-time check operates under an explicit **performance contract**: it "may only spend what a boot already spends: markdown already in memory, a bounded set of stats — no directory walks, no git, no cross-workspace sweep." This is called "a performance contract, not a preference".
- Where findings are surfaced through an edit-time hook, the hook's contract is **"never break a turn. Always exit 0"** — a thin adapter with a top-level catch that audit-logs and exits zero regardless, swallowing per-file detector exceptions into an empty result plus a flag rather than propagating. Budgets replace retries throughout: caps on files scanned, findings emitted, characters emitted, and a re-entrancy guard so the hook cannot recurse through child processes.

## Proposed change

1. Give drift findings an action-severity (`auto` / `mention` / `route`) across `ll-verify-docs`, `ll-check-links`, and `ll-doctor`.
2. Restrict `--fix` to `auto` findings. A `route` finding must name the command that owns the repair.
3. Emit one aggregate notice per session rather than per-finding noise, and throttle repeat `mention` / `route` findings per project with an opt-out.
4. Adopt the no-opportunistic-repair rule: a drift finding surfaced during an unrelated task is reported, not acted on, unless the user asks.
5. Apply the boot performance contract to any session-start drift check: no directory walks, no git invocation, no cross-workspace sweep.
6. Any hook surfacing these findings catches everything, audit-logs, and exits 0; budgets (max files, max findings, max chars) replace retry logic, with a re-entrancy guard.

## Acceptance criteria

- Every drift finding carries an action-severity, and `--fix` applies only auto-fixable ones.
- A routed finding names the command that owns its repair.
- Repeat findings are throttled per project, with a documented opt-out that tests can set.
- A session-start drift check performs no directory walk, no git call, and no cross-workspace sweep.
- A hook that surfaces findings exits 0 on malformed input and on internal error, and never fails the turn.
