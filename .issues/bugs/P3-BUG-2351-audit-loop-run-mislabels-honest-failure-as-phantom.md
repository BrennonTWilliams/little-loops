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

## Root Cause

- **File**: `skills/audit-loop-run/SKILL.md`
- **Anchor**: Verdict determination table (~"Determine the verdict" section, `phantom` row)
- **Cause**: The verdict table keys the `phantom` label on `"artifacts unchanged OR threshold unverified"` without cross-checking the run's own claimed outcome in `summary.json`. Because the check is mutation-count-only, a run that honestly reports `failed: N` in its summary receives the same `phantom` verdict as one that falsely reports `implemented: N` — the claimed-success signal is never consulted.

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

## Implementation Steps

1. Locate the verdict determination block in `skills/audit-loop-run/SKILL.md`
2. Before the `phantom` verdict row, add a `summary.json` parse step: read `implemented`, `failed`, and `decomposed` counters from the run's terminal summary
3. Split the `phantom` verdict row into two branches: `phantom` (claimed-success > 0 AND no mutation) vs. `honest-failure` (claimed-success == 0 AND no mutation)
4. Update the verdict output template to include `honest-failure` as a valid verdict value with its own rationale template
5. Verify by re-auditing the `rn-implement` run `2026-06-27T210732` — verdict should now be `honest-failure`, not `phantom`

## Steps to Reproduce

1. Run a loop whose terminal `summary.json` records `implemented: 0, failed: N`
   due to an external/environment failure (e.g. unconfigured `ll-auto` auth).
2. Run `/ll:audit-loop-run <loop> <run-id>`.
3. Observe the verdict is `phantom` despite the honest failure record.

## Integration Map

### Files to Modify
- `skills/audit-loop-run/SKILL.md` — update verdict determination logic and verdict table

### Dependent Files (Callers/Importers)
- Any loop YAML whose states invoke `audit-loop-run` (grep `audit-loop-run` in `loops/`)
- `commands/audit-loop-run.md` if it documents the verdict enum

### Similar Patterns
- `skills/debug-loop-run/SKILL.md` — check whether it has analogous verdict logic needing the same split

### Tests
- N/A — no dedicated unit test file; verify manually by re-auditing `rn-implement` run `2026-06-27T210732`

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — references `phantom` verdict; update to document `honest-failure` alongside it

### Configuration
- N/A

## Impact

- **Priority**: P3 — degrades audit signal quality but causes no incorrect mutations or data loss
- **Effort**: Small — isolated change to verdict logic in one skill file; no new infrastructure
- **Risk**: Low — additive change introducing a new verdict label; existing `phantom` verdict behavior is preserved for the true self-deception case
- **Breaking Change**: No — `honest-failure` is a new label; existing `phantom` verdicts are unaffected

## Session Log
- `/ll:format-issue` - 2026-06-27T22:06:41 - `afd5fe8f-ea36-4c89-928b-aa3adf4d581c.jsonl`
- `/ll:capture-issue` - 2026-06-27T21:58:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09e0f30a-d9cd-4afe-a20d-1b4ab9afdd5a.jsonl`

---

## Status

- **Status**: open
- **Created**: 2026-06-27
