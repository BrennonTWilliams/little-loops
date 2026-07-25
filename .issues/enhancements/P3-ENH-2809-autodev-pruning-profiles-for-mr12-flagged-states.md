---
id: ENH-2809
title: Add pruning_profile to the five MR-12-flagged skill-invoking states in autodev.yaml
type: ENH
priority: P3
status: done
captured_at: '2026-07-25T20:11:16Z'
discovered_date: 2026-07-25
discovered_by: human
relates_to:
- ENH-2805
- ENH-2714
labels:
- token-cost
- fsm
- loops
completed_at: '2026-07-25T20:11:16Z'
---

# ENH-2809: Add pruning_profile to the five MR-12-flagged skill-invoking states in autodev.yaml

## Status

done — implemented, validated, and tested on 2026-07-25.

## Summary

Five skill-invoking states in the built-in `autodev.yaml` loop lacked a
`pruning_profile`, triggering ENH-2805 MR-12 Check-3 warnings; matching profiles were
added to all five, eliminating the warnings and saving the full automation-context
static prefix per invocation on CLI-path installs.

## Problem

`ll-loop validate autodev` emitted five ENH-2805 MR-12 Check-3 warnings: `deposit_options`
(/ll:refine-issue), `run_decide` (/ll:decide-issue), `run_spike` (/ll:spike),
`run_size_review` (/ll:issue-size-review), and `reconcile_current` (/ll:reconcile-issue)
invoked skills with no resolvable `pruning_profile`, while eight sibling states in the
same loop already carried one. On the CLI request path each invocation pays the full
automation-context static prefix (catalog + SessionStart digest + CLAUDE.md).

## Investigation Findings

- In this repo the warnings were not a live cost problem: `.ll/ll-config.json` sets
  `orchestration.request_path: "sdk"`, and `_resolve_request_path()`
  (`fsm/executor.py`) falls back to that config default, dispatching prompt-mode
  states via `_dispatch_live` where pruning is a no-op.
- However, MR-12 Check 3 (`fsm/validation.py`, `_validate_pruning_profile`) only
  exempts a **state-level** `request_path: sdk` — it never sees the config default,
  so config-level sdk projects get false-positive warnings. (Known validator gap;
  not fixed here.)
- `autodev.yaml` is a shipped built-in loop, so other installs on the CLI path do
  pay the prefix — adding profiles is a genuine saving there and a no-op on sdk.
- The profile `name` is just a label exported as `LL_AUTOMATION_PROFILE` by
  `host_runner.py`; no registration is required.

## Current Behavior

(Pre-fix) `ll-loop validate autodev` emitted five MR-12 Check-3 WARNs; the five states
resolved no pruning profile, so CLI-path invocations paid the full static prefix.

## Expected Behavior

`ll-loop validate autodev` passes with zero MR-12 warnings, and every skill-invoking
state in `autodev.yaml` resolves a `pruning_profile` so CLI-path invocations skip the
static prefix (catalog + SessionStart digest + CLAUDE.md).

## Impact

No behavior change on sdk-path installs (pruning is a no-op there). On CLI-path
installs, the five high-volume repair-class states stop paying the full static prefix
on every invocation. Validator output for the shipped loop is clean.

## Scope Boundaries

- In scope: adding `pruning_profile:` blocks to the five flagged states in
  `scripts/little_loops/loops/autodev.yaml`.
- Out of scope: fixing the MR-12 Check-3 validator gap (config-level
  `request_path: sdk` invisibility) and the unrelated `ll-marketing` design-tokens
  warning — both noted under Follow-up.

## Resolution

Added `pruning_profile: {enabled: true, name: <skill>-auto, suppress_claude_md: true}`
to all five states in `scripts/little_loops/loops/autodev.yaml`, matching the shape of
the existing sibling profiles (`refine-issue-repair`, `wire-issue-auto`,
`confidence-check-recheck`). Names: `refine-issue-auto`, `decide-issue-auto`,
`spike-auto`, `issue-size-review-auto`, `reconcile-issue-auto`.

Deliberately did NOT use `pruning_profile_ok: true` — it would suppress all three
MR-12 checks including the ERROR-tier tools-allowlist check.

## Verification

- `ll-loop validate autodev` — valid, zero MR-12 warnings.
- `python -m pytest scripts/tests/test_builtin_loops.py` — 1280 passed.

## Follow-up (not done)

Possible enhancement: thread the orchestration config default into
`_validate_pruning_profile` so config-level `request_path: sdk` projects don't get
MR-12 Check-3 false positives.

Also noted during investigation (unrelated to this repo): a design-tokens warning
pointing at `ll-marketing`'s missing `default` token profile — cosmetic, degrades
gracefully; fix belongs in that project.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-25T20:11:50 - `fe35d20e-b1d7-4e57-9b51-73d0a86b9144.jsonl`
