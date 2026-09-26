---
id: ENH-3613
type: ENH
title: Autodev summary.json splits cancelled from implemented closures
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-26'
captured_at: '2026-09-26T05:02:45Z'
parent: EPIC-3565
decision_needed: false
blocks:
- FEAT-3573
- ENH-3600
---

# ENH-3613: Autodev summary.json splits cancelled from implemented closures

## Summary

autodev's `finalize_done` puts `cancelled` closures in the same `closed` bucket as
implemented ones. The run summary cannot tell "implemented and closed" apart from "closed
without implementation". Split out of FEAT-3573. This split sets the `summary.json` shape
that ENH-3600 preserves.

## Current Behavior

`finalize_done` (`scripts/little_loops/loops/autodev.yaml:3041`) promotes every staged ID
whose status is `done|completed|cancelled` to `autodev-passed.txt` (:3058-:3060).
`summary.json` (:3243) reports one `closed` count. The current keys are `verdict`,
`closed`, `not_closed`, `skipped`, `gate_blocked`, `decision_unresolved`, `not_started`,
`inflight_unresolved`, `abandoned`, `stop_reason`, `pending` and `proof_gate_infra`
(12 keys; BUG-3603 added `proof_gate_infra`).

## Expected Behavior

- `closed` stays the total count, for back-compat.
- Two new keys are added: `closed_implemented` (`done`/`completed`) and `closed_cancelled`
  (`cancelled`). The rule `closed_implemented + closed_cancelled == closed` always holds.
- The human-readable summary shows the split, for example `Passed (3): ... (2 implemented, 1 cancelled)`.
- The verdict ladder does not change. A cancelled closure still counts toward
  `success`/`partial`.

## Motivation

A run that cancels every issue reports the same `closed` count as a run that implements
them all. Operators and ENH-3600's run-record ledger need the split.

## Proposed Solution

In the `finalize_done` promotion loop, record the status next to each promoted ID. Two
options: a sidecar `autodev-closed-status.txt` with `ID status` lines, or a separate
`autodev-cancelled.txt`. `autodev-passed.txt` must keep one bare ID per line, because
`auto-refine-and-implement.yaml` `finalize` and the `grep -qxF` checks read it. Count each
bucket and add the two keys to the `summary.json` printf.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

**Option A**: Status sidecar `autodev-closed-status.txt` with `ID status` lines written next to the bare-ID `autodev-passed.txt` append; implemented/cancelled counts derived from the sidecar. Two-column ledgers already exist (`ID  reason` files), so the format has precedent, but the sidecar must be read with regex-anchored greps and kept consistent with `sort -u` dedupe of `autodev-passed.txt`.

**Option B**: Separate bare-ID `autodev-cancelled.txt` bucket ledger (init-truncated, counted via the `grep -c` idiom); `closed_cancelled` is its count and `closed_implemented` is `closed` minus that count. Matches the dominant bare-ID bucket convention and keeps `grep -qxF` usable, but the sum rule holds by construction only if cancelled IDs are always also in `autodev-passed.txt`.

> **Selected:** Option B — one-ledger-per-bucket convention with the least new parsing; bare-ID format keeps `grep -qxF`/`sort -u` readers intact.

**Recommended**: Option B — fits the existing one-ledger-per-bucket convention and the count idiom with the least new parsing; the sum rule must still be asserted by tests, including the resumed-run (ledger-absent) case.

### Decision Rationale

**Selected option:** Option B — separate bare-ID `autodev-cancelled.txt` bucket ledger.

**Reasoning:** Bucket ledgers in `finalize_done` are one bare-ID file per bucket, counted with the `grep -c '[^[:space:]]'` idiom. Option B adds one `echo` in the `cancelled` case arm and one count; Option A introduces a two-column sidecar that needs regex-anchored greps and its own `sort -u` dedupe handling. To keep `closed_implemented + closed_cancelled == closed` by construction, derive `closed_cancelled` from the sorted-unique cancelled IDs that are also present in the deduped `autodev-passed.txt`, and `closed_implemented` as `closed` minus that count.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — status sidecar | 2 | 1 | 2 | 2 | 7/12 |
| B — cancelled ledger | 3 | 2 | 3 | 2 | 10/12 |

**Key evidence:** `finalize_done` promotion `case` arm (`done|completed|cancelled)`) writes bare IDs; existing bucket ledgers (`-staged`, `-gate-blocked`, `-decision-unresolved`, `-proof-gate-infra`) are bare-ID; `auto-refine-and-implement.yaml` `finalize` requires bare sortable IDs in `autodev-passed.txt`. Tests must cover all-implemented, all-cancelled, mixed, and ledger-absent (resumed-run) fixtures.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `finalize_done` promotion loop, counts, printf, human summary
- `docs/guides/LOOPS_REFERENCE.md` — `:1079` `finalize_done` bucket list
- `skills/audit-loop-run/SKILL.md:271` — lists autodev's summary keys; add the two new ones. Mirror regen via `ll-adapt` if this file is mirrored.

### Dependent Files
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `finalize` reads `autodev-passed.txt` (bare IDs) and writes its own `summary.json`. Keep the bare-ID format unchanged. The parent does not need the split.
- `scripts/little_loops/fsm/persistence.py`, `scripts/little_loops/cli/loop/audit.py`, `scripts/little_loops/cli/loop/evidence.py`, `scripts/little_loops/hooks/pre_compact_handoff.py` — shape-agnostic summary.json consumers. Adding keys is safe.

### Tests
- `scripts/tests/test_builtin_loops.py` `TestAutodevLoop` — `_run_finalize_done` harness; the promotion, phantom, no-op and BUG-3390 dedupe tests. Add cases for all implemented, all cancelled, and mixed runs, and assert the new keys and the sum rule.
- `scripts/tests/data/loop_interpolation_baseline.json` / `TestInterpSweepBaseline` — the `finalize_done` entry stays valid if no new `${...}` refs are added.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- **Anchors have drifted from the Current Behavior/Integration Map text.** In `scripts/little_loops/loops/autodev.yaml` the `finalize_done` state header is now at `:3115`, the promotion `case` arm (`done|completed|cancelled)`) at `:3133`, the `Passed (%d)` human line at `:3237`, and the `summary.json` printf at `:3317`. In `docs/guides/LOOPS_REFERENCE.md` the `finalize_done` bucket prose is the "Diagram omissions" paragraph at `:1081`; in `skills/audit-loop-run/SKILL.md` the per-key additive paragraphs (ENH-2404, ENH-2743, BUG-3603) sit at `:271-:275` (Step 6a). Re-resolve by symbol, not line number.
- **The verdict ladder keys on `PASSED_COUNT`** (`autodev.yaml` ~`:3295-:3315`), so a cancelled-only run currently yields `success`. The Expected Behavior constraint that the ladder does not change means the new keys must be derived alongside, never substituted into, `PASSED_COUNT`.
- **`autodev-passed.txt` has exact-line readers.** `finalize_done` itself uses `grep -qxF "$INFLIGHT"` against it (~`:3210`), and `auto-refine-and-implement.yaml` `finalize` (~`:1088-:1095`) pipes it through `sort -u` into `comm -23`. Both require bare, sortable IDs; any status data must live outside this file.
- **Only `finalize_done` writes `autodev-passed.txt`** (BUG-2908; pinned by `test_check_passed_stages_instead_of_passes`). The promotion loop is therefore the sole point where implemented-vs-cancelled is observable; after the `case` arm the status is discarded.
- **Staged IDs are deduped by `sort -u`** before promotion, and `autodev-passed.txt` is re-deduped at count time. A split derived from a second ledger must survive the same dedupe or `closed_implemented + closed_cancelled == closed` can drift (e.g. an ID appended twice across a resumed run).
- **Resumed runs bypass `init`.** Every existing ledger key has a "ledger absent → 0" companion test; a new ledger-derived key inherits that requirement.
- **`summary.json` consumers are shape-agnostic.** `cli/loop/audit.py` (~`:194`, `:242-:247`) stores the whole dict; `evidence.py` copies it by filename. `auto-refine-and-implement` never reads autodev's `closed`; it computes its own from filesystem snapshots. `skills/audit-loop-run/SKILL.md` Step 6a treats `closed` as the claimed-success signal and treats absent additive keys as "no data".

### Conventions in Force
- **Bucket ledgers are `${context.run_dir}/autodev-<bucket>.txt`, truncated at init and read only by `finalize_done`** — evidence: `autodev.yaml` init `:63-:74`. Two line formats coexist: bare-ID (`-passed`, `-staged`, `-gate-blocked`, `-decision-unresolved`, `-proof-gate-infra`) and `ID  reason` two-space (`-skipped`, `-not-started`, `-unverified`). Reasoned files need regex-anchored greps (`grep -qE "^$ID([[:space:]]|$)"`, BUG-3390) because `grep -qxF`/`sort -u` cannot match them.
- **Counts use `grep -c '[^[:space:]]' || true` followed by `[ -z "$COUNT" ] && COUNT=0`** (BUG-2827 guard against the two-line `grep -c ... || echo 0` bug) — evidence: `finalize_done` counting block `:3145-:3234`.
- **New `summary.json` keys are appended at the end of both the format string and the argument list; keys are flat scalars** — evidence: `proof_gate_infra` (BUG-3603), `pending`, `not_started` at the `:3317` printf.
- **Splitting one ledger into display buckets is done in `finalize_done` by stem filtering** (`grep`/`awk` on the reason column, with each new stem excluded from the generic bucket to prevent double-counting) — evidence: skipped-ledger chain ENH-2727/2868/2909/2989 and `test_finalize_done_buckets_already_resolved_separately`.
- **FSM escaping**: bash `${...}` in the action must be `$${...}`, and interpolation covers the whole action including comments — evidence: `$${PASSED_LIST:-none}` at `:3237`; harness substitution in `_run_finalize_done`. `finalize_done` has no entry in `loop_interpolation_baseline.json`, so introducing a heredoc with `${...}` would add one (the file forbids additions).
- **Docs/skill convention for a new additive key** is a bolded per-key paragraph in `skills/audit-loop-run/SKILL.md` Step 6a ending "additive; older `summary.json` files will lack it — treat absence as zero", plus one inline mention in `LOOPS_REFERENCE.md` `:1081`. `SKILL.md` is capped at 500 lines (`ll-verify-skills`); skill edits can trip `ll-adapt` mirror gates.

### Test Constraints
- `TestAutodevLoop` `_run_finalize_done` (`test_builtin_loops.py` ~`:7481`) runs the action under `bash -c`; existing `ll-issues` stubs return **one fixed status for every ID** and none emits a cancelled status. A mixed implemented/cancelled fixture needs a per-ID stub, and the cancelled status string `ll-issues show --json` actually emits was not verified — check it against the lowercase-and-match logic rather than assuming `"Cancelled"`.
- No `TestAutodevLoop` test asserts autodev's full `summary.json` key list; tests assert individual keys (`test_finalize_done_promotes_verified_closure_to_passed` asserts `closed==1`). `test_finalize_summary_has_closure_keys` (~`:5426`) and `test_finalize_does_not_count_cancelled_as_closed` (~`:5364`) belong to `auto-refine-and-implement`, not autodev.
- If the change adds no new state, the pinned state count in `test_fsm_topology.py` (~`:263`) is unaffected.
- `test_audit_loop_run_skill.py` (~`:145-:170`) carries per-key Step 6a tests for ENH-2404/ENH-2743; a matching test for the new keys is the local convention (no BUG-3603 test was confirmed there).

## Implementation Steps

1. In the promotion loop, append the bare ID to `autodev-cancelled.txt` (truncated at init) when the status is `cancelled`, next to the bare-ID `autodev-passed.txt` append.
2. Compute `CLOSED_CANCELLED` from the deduped `autodev-cancelled.txt` IDs that are also in `autodev-passed.txt` (`grep -c` idiom, absent ledger → 0) and `CLOSED_IMPLEMENTED` as `PASSED_COUNT` minus that, and add both to the printf and the human summary.
3. Add tests; update `LOOPS_REFERENCE.md` and `audit-loop-run` docs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Anchors cited in the steps above resolve by symbol (`finalize_done`, its promotion `case` arm, the `summary.json` printf), not by the older line numbers in Current Behavior — see Integration Map findings.
- Verification target: the new keys satisfy `closed_implemented + closed_cancelled == closed` for all-implemented, all-cancelled, mixed, and ledger-absent (resumed-run) fixtures, and `autodev-passed.txt` remains bare-ID/`grep -qxF`-matchable.

## Impact

- **Priority**: P3
- **Effort**: Small
- **Risk**: Low

## Program Design

### Types

- `summary.json` (autodev `finalize_done`) gains two integer keys: `closed_implemented` and `closed_cancelled`. The rule `closed_implemented + closed_cancelled == closed` always holds.
- Cancelled bucket ledger `${run_dir}/autodev-cancelled.txt`: bare IDs, init-truncated, written next to the bare-ID `autodev-passed.txt` (Option B selected; cancelled IDs are always also in `autodev-passed.txt`).

### Signatures

- `cmd_show(config: BRConfig, args: argparse.Namespace) -> int` — `scripts/little_loops/cli/issues/show.py:786`; `ll-issues show --json` supplies the display-cased `status` that `finalize_done` lowercases before bucketing. Unchanged.

### Call Path

`autodev.yaml:finalize_done` (:3041) → per staged ID `ll-issues show --json` (`cmd_show`, `show.py:786`) → lowercased status → `done|completed` counts as implemented, `cancelled` counts as cancelled → `autodev-passed.txt` (bare ID) + `autodev-cancelled.txt` (cancelled only) → counts → `summary.json` printf (:3243).

### Decision Rules

- `done` and `completed` count as implemented. `cancelled` counts as cancelled.
- The verdict ladder does not change. A cancelled closure still counts as `closed`.
- The `autodev-passed.txt` format does not change (bare IDs).


## Acceptance Criteria

- [ ] `summary.json` has `closed_implemented` and `closed_cancelled`, and their sum equals `closed`
- [ ] `autodev-passed.txt` format is unchanged (bare IDs)
- [ ] The verdict is unchanged for all existing `TestAutodevLoop` fixtures
- [ ] Docs list the new keys

## Scope Boundaries

- FEAT-3573 adds the quality-gate bucket (`quality_failed`) on top of this shape. This
  issue does not add it.
- The parent `auto-refine-and-implement` summary is out of scope.

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Session Log
- `/ll:decide-issue` - 2026-09-26T06:01:33 - `95a3ad40-ecc6-4e5c-befd-9be7a282a332.jsonl`
- `/ll:refine-issue` - 2026-09-26T05:58:48 - `e3c050f9-1131-496e-87dd-53db8a85423f.jsonl`
