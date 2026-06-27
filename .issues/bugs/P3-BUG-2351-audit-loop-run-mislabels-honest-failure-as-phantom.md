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
- **Anchor**: `## Step 6: Goal-vs-Outcome Scorecard`, `phantom` row of the verdict table
- **Cause**: The verdict table keys the `phantom` label on `"artifacts unchanged OR threshold unverified"` without cross-checking the run's own claimed outcome in `summary.json`. Because the check is mutation-count-only, a run that honestly reports `failed: N` in its summary receives the same `phantom` verdict as one that falsely reports `implemented: N` — the claimed-success signal is never consulted.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Anchor confirmed: `## Step 6: Goal-vs-Outcome Scorecard` — the `phantom` row condition is exactly `Terminal reached AND (artifacts unchanged OR threshold unverified — only model self-reported via llm_structured evaluator)`. No branch tests claimed-success counters.
- `summary.json` is **never read** at any step in the skill (grep confirmed no matches for `summary.json`, `implemented`, `failed`, or `decomposed`). The `loop_complete` event's `terminated_by` field (`"terminal"`, `"max_steps"`, `"signal"`, `"error"`) is the only per-run signal the verdict table consults.
- The verdict enum appears in **two locations** in the file — both must be updated: the table in `## Step 6` and the output template in `## Step 9: Conclusion` (`` `<met | phantom | partial | degraded>` ``).
- `summary.json` field names confirmed from `rn-implement.yaml` state `report`: `implemented` (from `implemented_count.txt`), `decomposed`, `failed`, `sub_loop_crashes`, `scores_missing`, `size_review_failed`, `rate_limited`.

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

1. Locate the verdict determination block in `skills/audit-loop-run/SKILL.md` → `## Step 6: Goal-vs-Outcome Scorecard`
2. Before the `phantom` verdict row, add a `summary.json` parse step: read `implemented`, `failed`, and `decomposed` counters from the run's terminal summary (file is at `${run_dir}/summary.json`)
3. Split the `phantom` verdict row into two branches: `phantom` (claimed-success > 0 AND no mutation) vs. `honest-failure` (claimed-success == 0 AND no mutation)
4. Update the Step 6 scorecard output template to include `honest-failure` as a valid verdict value with its own rationale template
5. Update the Step 9 conclusion template (`## Step 9: Conclusion`) — the verdict enum is also hard-coded there as `` `<met | phantom | partial | degraded>` ``; add `honest-failure`
6. Update `test_skill_scorecard_has_four_verdicts` in `scripts/tests/test_audit_loop_run_skill.py` (lines 107–112) — add `"honest-failure"` to the verdict loop; rename test to `test_skill_scorecard_verdicts` or similar
7. Add `TestHonestFailureDiscriminator` alongside `TestPhantomSuccessDiscriminator` (lines 143–189) in the same test file — assert a run with `implemented: 0, failed: N` AND no mutation produces `honest-failure`
8. Check `scripts/little_loops/loops/outer-loop-eval.yaml` — if it branches on verdict values, add an `honest-failure` route
9. Verify by re-auditing the `rn-implement` run `2026-06-27T210732` (see `rn-implement-audit-2026-06-27.md`) — verdict should now be `honest-failure`, not `phantom`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `docs/reference/COMMANDS.md` — in `### /ll:audit-loop-run` verdict table (line 848): narrow the `phantom` row condition to "claimed-success > 0 AND no mutation"; add `honest-failure` row with condition "claimed-success == 0 AND no mutation". Update output template line 863 to include `honest-failure` in the enum string
11. Update `commands/help.md` — in the `/ll:audit-loop-run` entry, add `honest-failure` to the `Verdicts:` list alongside `met, partial, phantom, degraded`
12. Update `README.md` — change "four-valued verdict" (line 69) to "five-valued verdict"
13. Create `scripts/tests/fixtures/fsm/assess-honest-failure.yaml` — new fixture (parallel to `assess-phantom-success.yaml`) with context fields `failed: N, implemented: 0`; loop exits `terminal: true` without artifact mutation; used by the `TestHonestFailureDiscriminator` tests added in step 7

## Steps to Reproduce

1. Run a loop whose terminal `summary.json` records `implemented: 0, failed: N`
   due to an external/environment failure (e.g. unconfigured `ll-auto` auth).
2. Run `/ll:audit-loop-run <loop> <run-id>`.
3. Observe the verdict is `phantom` despite the honest failure record.

## Integration Map

### Files to Modify
- `skills/audit-loop-run/SKILL.md` — update verdict determination logic and verdict table

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — verdict table at `### /ll:audit-loop-run` (line 848): narrow `phantom` row condition; add `honest-failure` row. Output template at line 863: `` `<met | phantom | partial | degraded>` `` → add `honest-failure`
- `commands/help.md` — `/ll:audit-loop-run` entry (line ~215): `Verdicts: met, partial, phantom, degraded` → add `honest-failure`
- `README.md` — line 69: "four-valued verdict catches failure modes humans miss" → "five-valued verdict"

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/outer-loop-eval.yaml` — loop YAML confirmed to invoke `audit-loop-run`; if it branches on verdict values, add an `honest-failure` route
- `commands/audit-loop-run.md` — **does not exist**; verdict enum is documented only within `skills/audit-loop-run/SKILL.md` itself

### Similar Patterns
- `skills/debug-loop-run/SKILL.md` — check whether it has analogous verdict logic needing the same split

### Tests
- `scripts/tests/test_audit_loop_run_skill.py` — `test_skill_scorecard_has_four_verdicts` (lines 107–112) asserts each of `met`, `phantom`, `partial`, `degraded` appears in the skill; must be updated to include `honest-failure`
- `scripts/tests/test_audit_loop_run_skill.py` — `TestPhantomSuccessDiscriminator` class (lines 143–189) covers the phantom detection path; a parallel `TestHonestFailureDiscriminator` test should be added
- `scripts/tests/fixtures/fsm/assess-phantom-success.yaml` — existing phantom fixture; no change needed (phantom path preserved)
- `scripts/tests/fixtures/fsm/assess-honest-failure.yaml` — **new fixture file required** (parallel to `assess-phantom-success.yaml`): loop whose context records `failed: N, implemented: 0`, exits `terminal: true` without artifact mutation; loaded by the new `TestHonestFailureDiscriminator` discriminator tests [Agent 1 + 3 finding]
- `scripts/tests/test_outer_loop_eval.py` — integration test verifying `outer-loop-eval.yaml` invokes `audit-loop-run` (lines 126, 136); does not assert on verdict string — no update needed, but run after fix to confirm it still passes [Agent 1 + 3 finding]
- Manual verification: re-audit `rn-implement` run `2026-06-27T210732` (see `rn-implement-audit-2026-06-27.md`) — verdict should change from `phantom` to `honest-failure`

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — **does not reference `phantom`** (confirmed by grep); no update needed
- `docs/guides/LOOPS_REFERENCE.md` — documents `summary.json` field set (line 415); low-priority candidate to note `honest-failure` verdict alongside run artifact descriptions
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — references `summary.json` in `rn-implement` context (lines 251–253); low-priority update candidate

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `### /ll:audit-loop-run` section (lines 834–888): verdict table (line 848) lists four verdicts; `phantom` row condition and `honest-failure` row must be added; output template line 863 `**Verdict**: \`<met | phantom | partial | degraded>\`` must include `honest-failure` [Agent 1 + 2 finding]
- `commands/help.md` — `/ll:audit-loop-run` entry (~line 215): `Verdicts: met, partial, phantom, degraded` quick-reference must add `honest-failure` [Agent 2 finding]
- `README.md` — line 69: "four-valued verdict catches failure modes humans miss" → "five-valued verdict" [Agent 2 finding]

### Configuration
- N/A

## Impact

- **Priority**: P3 — degrades audit signal quality but causes no incorrect mutations or data loss
- **Effort**: Small — isolated change to verdict logic in one skill file; no new infrastructure
- **Risk**: Low — additive change introducing a new verdict label; existing `phantom` verdict behavior is preserved for the true self-deception case
- **Breaking Change**: No — `honest-failure` is a new label; existing `phantom` verdicts are unaffected

## Session Log
- `/ll:wire-issue` - 2026-06-27T22:28:20 - `e0ce2dea-8fca-4b08-b38d-f983f2d62cd9.jsonl`
- `/ll:refine-issue` - 2026-06-27T22:19:27 - `b87fb21f-6776-487a-a31c-d78f2b3cc986.jsonl`
- `/ll:format-issue` - 2026-06-27T22:06:41 - `afd5fe8f-ea36-4c89-928b-aa3adf4d581c.jsonl`
- `/ll:capture-issue` - 2026-06-27T21:58:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09e0f30a-d9cd-4afe-a20d-1b4ab9afdd5a.jsonl`

---

## Status

- **Status**: open
- **Created**: 2026-06-27
