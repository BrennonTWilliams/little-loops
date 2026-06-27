---
id: BUG-2351
type: BUG
priority: P3
status: open
captured_at: '2026-06-27T21:58:52Z'
discovered_date: 2026-06-27
discovered_by: capture-issue
labels:
- captured
- audit-loop-run
- verdict-accuracy
---

# BUG-2351: `audit-loop-run` mislabels honest-failure runs as `phantom`

## Summary

The `/ll:audit-loop-run` skill assigns the `phantom` verdict to a run that
recorded failures honestly (e.g. `summary.json` → `{implemented: 0, failed: 5}`)
purely because no source-code or issue-status mutations occurred. "Phantom"
should mean *the loop claimed success while producing no real change* (self-
deception). A run that **claims failure** and produces no change is an *honest
failure* — a categorically different outcome that the verdict logic currently
collapses into the same bucket.

Surfaced during the `rn-implement` run `2026-06-27T210732` audit
(`rn-implement-audit-2026-06-27.md`): all 5 issues failed at `ll-auto` with an
environment auth error, `summary.json` honestly recorded `failed: 5`, yet the
verdict was `phantom`. The audit's own Recommendation #5 conceded the
conflation ("Both share the verdict but for different reasons").

## Current Behavior

The phantom-detection logic keys the verdict on "thresholds/gates passed +
artifacts written + zero repo mutations" without checking whether the loop's
own summary **claimed success**. A run whose summary reports `implemented: 0,
failed: N` is labeled `phantom` identically to a run that reports
`implemented: N` with no corresponding mutation.

## Expected Behavior

Split the verdict space:

- **`phantom`** — the summary/outcome claims success (`implemented > 0`, status
  flipped to `done`, or an equivalent success token) but no source/issue
  mutation is observable. This is the self-deception case worth flagging loudly.
- **`honest-failure`** (or `no-op-failure`) — the summary claims failure
  (`failed > 0`, `implemented: 0`) and no mutation occurred. The loop told the
  truth; the root cause is upstream (here, missing auth). Report it, but do not
  brand it `phantom`.

The distinguishing signal is the run's own claimed outcome (`summary.json`
success counters / status flips) cross-checked against observed mutations — not
mutation-count alone.

## Motivation

`phantom` is the audit's highest-severity integrity signal. Diluting it with
honest failures trains operators to ignore it and masks the genuine upstream
cause (an environment/auth misconfiguration vs. a loop that lies about its
work). Keeping the label precise preserves its alarm value.

## Proposed Solution

In the `audit-loop-run` skill's verdict step, before emitting `phantom`:

1. Read the run's claimed outcome from `summary.json` (success counters such as
   `implemented`/`decomposed`, plus any status flips the loop reports).
2. If claimed-success > 0 AND observed mutations == 0 → `phantom`.
3. If claimed-success == 0 (failures recorded) AND observed mutations == 0 →
   `honest-failure`, with the upstream cause summarized (e.g. "all N failures
   share root cause: `ll-auto` auth error").

Relates to BUG-2352 (a sibling precision fix to the same skill's laundering
check).

## Steps to Reproduce

1. Run a loop whose terminal `summary.json` records `implemented: 0, failed: N`
   due to an external/environment failure (e.g. unconfigured `ll-auto` auth).
2. Run `/ll:audit-loop-run <loop> <run-id>`.
3. Observe the verdict is `phantom` despite the honest failure record.

## Impact

- **Severity**: Low-Medium — no incorrect mutation, but degraded audit signal.
- **Scope**: Every audited run that fails honestly with no repo change.

## Session Log
- `/ll:capture-issue` - 2026-06-27T21:58:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09e0f30a-d9cd-4afe-a20d-1b4ab9afdd5a.jsonl`

---

## Status

- **Status**: open
- **Created**: 2026-06-27
