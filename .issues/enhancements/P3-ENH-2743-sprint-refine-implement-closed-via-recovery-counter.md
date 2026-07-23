---
id: ENH-2743
title: Add closed_via_recovery counter to sprint-refine-and-implement summary.json
  for parked-then-closed issues
type: ENH
priority: P3
status: done
captured_at: '2026-07-23T00:25:52Z'
completed_at: '2026-07-23T01:22:14Z'
discovered_date: 2026-07-23
discovered_by: audit
size: Small
labels:
- loops
- visibility
- captured
confidence_score: 98
outcome_confidence: 86
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 23
---

# ENH-2743: Add closed_via_recovery counter to sprint-refine-and-implement summary.json for parked-then-closed issues

## Summary

`sprint-refine-and-implement`'s `finalize` state currently reports `closed`
and `skipped` counts in `summary.json`, but has no way to tell whether a
skipped/parked issue was later closed via an alternate path within the same
run (e.g. `ll-auto` re-implementing after the sprint queue released the
lock).

In an audited run (`.loops/.history/2026-07-18T045753-sprint-refine-and-implement/`),
2 issues were skipped by the autodev sub-loop (`skipped_breakdown:
low_readiness=1, refine_failed=1`) but both issues' working-tree status ended
up `status: done` by the time the run finished. The current `closed=4` count
misses them, and `parked_rate=0.1429` overstates the actual
permanently-parked ratio. A reviewer reading `summary.json` alone sees a 4/2
split that looks like the run "failed to handle" 2 issues, when actually both
self-resolved.

## Current Behavior

`summary.json` reports `closed`, `skipped`, and `skipped_breakdown` with no
signal distinguishing permanently-parked issues from ones that were
subsequently closed by a different path during the same run.

## Expected Behavior

`summary.json` includes a `closed_via_recovery` field counting skipped
issues whose working-tree status reached `done` before the run's `finalize`
state ran.

## Proposed Solution

In the `finalize` state's action, compute `CLOSED_VIA_RECOVERY` via `comm -12`
between the run's skipped-ids file and a fresh done-ids snapshot, mirroring
the BUG-2403 / ENH-1418 done-now snapshot pattern:

```bash
CLOSED_VIA_RECOVERY=$(comm -12 \
  "$RUN_DIR/$P-skipped-ids.txt" \
  "$RUN_DIR/$P-done-new.txt" \
  | wc -l)
```

Add `"closed_via_recovery": <N>` to the `summary.json` output alongside the
existing `closed`/`skipped`/`skipped_breakdown` fields.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correction on target file**: `sprint-refine-and-implement.yaml`'s
  `read_outcome` state (lines 34-44) just `cat`s the child loop's
  `summary.json` verbatim — no code change needed there. All counter logic
  actually lives in `scripts/little_loops/loops/auto-refine-and-implement.yaml`'s
  `finalize` state (lines 692-967), which `sprint-refine-and-implement`
  delegates to via a `delegate` state sharing the same `run_dir`. This is the
  real implementation target.
- **No new done-ids snapshot needed**: `$RUN_DIR/$P-done-now.txt` (written at
  `auto-refine-and-implement.yaml:733-763`, the existing BUG-2403/ENH-1418
  done-now snapshot) already IS the "fresh done-ids snapshot" this proposal
  calls for. It's the full current done-set at finalize time (not just
  new-since-baseline), so the `comm -12` should target it directly — the
  proposed solution's own snippet references `$P-done-new.txt`, but
  `$P-done-now.txt` is the correct target since a recovered issue may have
  already been done at baseline-check time in edge cases; `$P-done-now.txt`
  is safer than `$P-done-new.txt` for this purpose.
- **The skipped-ids file does not exist yet**: no `$RUN_DIR/$P-skipped-ids.txt`
  (bare-ID-only) file exists anywhere in the codebase today. Only the raw
  `autodev-skipped.txt` ledger (format: `ID  REASON`, written by
  `autodev.yaml` at lines 190, 209, 676, 787, 790, 975, 1207, 1211, 1286,
  1291) exists. It must be derived with the same idiom `autodev.yaml:1315`
  already uses for its own summary: `awk '{print $1}' autodev-skipped.txt |
  sort -u > "$RUN_DIR/$P-skipped-ids.txt"`. The natural insertion point is
  next to the existing `SKIPPED_BREAKDOWN` computation
  (`auto-refine-and-implement.yaml:851-867`), since both read the same
  ledger file.
- **`comm -12` is a new primitive for this codebase**: `finalize` already uses
  `comm -13` (baseline vs. now — `auto-refine-and-implement.yaml:764-765`)
  and `comm -23` (set exclusion — lines 809-815, 821-828). No `comm -12`
  (intersection) call exists anywhere under `scripts/little_loops/loops/`
  today; this would be the first, but it composes directly from the same
  file-snapshot conventions.
- **Exact `summary.json` assembly point**: the single `printf` write site is
  `auto-refine-and-implement.yaml:940-941`. Adding `closed_via_recovery`
  means adding `"closed_via_recovery":%s` to the format string and
  `"$CLOSED_VIA_RECOVERY"` to the positional argument list, plus mirroring it
  in the human-readable stdout line at 946-947.

## Implementation Steps

1. Confirm the `finalize` state already writes a skipped-ids file (per the
   `skipped_breakdown` mechanism, ENH-2404) and identify/add an equivalent
   done-ids snapshot at finalize time.
   - **Research finding**: neither exists in the needed form. Add
     `awk '{print $1}' autodev-skipped.txt | sort -u > "$RUN_DIR/$P-skipped-ids.txt"`
     near `SKIPPED_BREAKDOWN` (`auto-refine-and-implement.yaml:851-867`).
     `$RUN_DIR/$P-done-now.txt` (line 733) already exists and needs no change.
2. Add the `comm -12` computation for `CLOSED_VIA_RECOVERY`, targeting
   `$P-done-now.txt` (not `$P-done-new.txt`) so recovery is detected
   regardless of when the recovering path closed the issue relative to the
   `done_baseline` snapshot.
3. Add `"closed_via_recovery":%s` / `$CLOSED_VIA_RECOVERY` to the `printf` at
   `auto-refine-and-implement.yaml:940-941`, and mirror it in the
   human-readable summary line at 946-947.
4. Add a test/fixture run asserting a skipped-then-done issue is counted —
   extend `TestAutoRefineAndImplementLoop` in `scripts/tests/test_builtin_loops.py`,
   combining the `_run_finalize` fixture's existing `skipped_reasons=` kwarg
   (seeds `autodev-skipped.txt`) with `done_in_place=` (seeds a `status: done`
   `.md` fixture via `_write_done_in_place_fixture`, lines 2632-2642) for the
   same issue ID, then assert `summary["closed_via_recovery"] == 1`. Follow
   the "new keys exist" smoke-test shape of
   `test_finalize_summary_has_enh_2404_keys` (lines 2914-2920) for a
   companion presence check.
5. Consider updating `docs/reference/json-output-contracts.md` and
   `skills/audit-loop-run/SKILL.md` (Step 6a's ENH-2404 key list) to document
   the new field, since both currently enumerate the `summary.json` schema
   explicitly.
   - **Correction**: `json-output-contracts.md` has no existing schema
     enumeration for this artifact — this is a net-new section, not an edit.
     `docs/guides/LOOPS_REFERENCE.md`'s "Closure accounting" paragraph does
     already enumerate the schema and is a better/required target.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

6. Before writing the Step 4 test, fix the `_run_finalize` fixture's ID
   mismatch between `skipped_reasons=` (synthetic `ID-{i}` lines) and
   `done_in_place=` (real issue IDs) — add a way to seed
   `autodev-skipped.txt` with a real issue ID so a single fixture ID can be
   both skipped and done-in-place. Without this, Step 4's test can't
   express "issue X was skipped, then recovered" for the same ID.
7. Add the `closed_via_recovery` sentence to `docs/guides/LOOPS_REFERENCE.md`'s
   "Closure accounting" paragraph (this is the file that actually documents
   the schema — `json-output-contracts.md` doesn't).
8. If the `skills/audit-loop-run/SKILL.md` update should be test-enforced
   (matching the ENH-2404 precedent), add
   `test_skill_step6a_reads_closed_via_recovery_key` to
   `scripts/tests/test_audit_loop_run_skill.py`, following
   `test_skill_step6a_reads_enh_2404_keys` (lines 144-155).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `finalize`
  state (lines 692-967); this is the actual implementation target where
  `summary.json` is assembled. `sprint-refine-and-implement.yaml` itself
  needs no code change.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:34-44` —
  `read_outcome` state `cat`s the child's `summary.json` verbatim; any new
  key propagates automatically.
- `scripts/little_loops/loops/autodev.yaml` — writes `autodev-skipped.txt`
  (`ID  REASON` ledger) at park sites: lines 190, 209, 676, 787, 790, 975,
  1207, 1211, 1286, 1291.
- `skills/audit-loop-run/SKILL.md` — Step 6a checks for the ENH-2404 key set
  (`skipped_breakdown`, `gate_blocked`, `parked_rate`); may want an update to
  recognize `closed_via_recovery`.

### Similar Patterns
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:733-765` — the
  BUG-2403/ENH-1418 done-now snapshot pattern (`comm -13` baseline vs. now).
- `scripts/little_loops/loops/autodev.yaml:1315` — existing
  `awk '{print $1}'` idiom for extracting bare IDs from the `ID  REASON`
  ledger.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:707` — shared
  `count()` awk helper (`awk 'NF{c++} END{print c+0}'`).

### Tests
- `scripts/tests/test_builtin_loops.py`, class `TestAutoRefineAndImplementLoop`
  — fixture `_run_finalize` (lines 2644-2747) and `_write_done_in_place_fixture`
  (lines 2632-2642).
- `test_finalize_summary_has_enh_2404_keys` (lines 2914-2920) — smoke-test
  pattern for new key presence.

_Wiring pass added by `/ll:wire-issue`:_
- **Fixture gap (blocks Implementation Step 4 as written)**: `_run_finalize`'s
  `skipped_reasons=` kwarg seeds synthetic `ID-0  {reason}`, `ID-1  {reason}`
  ... lines into `autodev-skipped.txt` (index-based fake IDs), while
  `done_in_place=` writes a real `.issues/<category>/P3-<issue_id>-x.md`
  fixture keyed by the real issue ID passed in. The two kwargs don't share an
  ID space, so a test can't currently simulate "issue X was skipped, then
  closed via recovery for that same issue X" — `_run_finalize` needs either a
  new kwarg that seeds `autodev-skipped.txt` with the real issue ID used by
  `done_in_place`, or `skipped_reasons` needs to accept real IDs directly.
  [Agent 3 finding]
- `test_finalize_parked_rate_computation` (lines 3223-3238) — closest
  structural template for the new counter: single-integer/ratio computation
  with an inline arithmetic comment and a `pytest.approx`/`==` assertion, vs.
  `test_finalize_skipped_breakdown_aggregates_by_reason`'s per-reason dict
  shape (not applicable here since `closed_via_recovery` is a scalar count).
  [Agent 3 finding]
- `test_finalize_parked_rate_zero_when_input_size_unavailable` (lines
  3240-3248) — template for a "defaults to 0, doesn't crash" test when the
  skipped-ids/done-now snapshot is absent (e.g. no skips this run). [Agent 3
  finding]
- `scripts/tests/test_audit_loop_run_skill.py::test_skill_step6a_reads_enh_2404_keys`
  (lines 144-155) — doc-coupling test: greps the SKILL.md `## Step 6:`–
  `## Step 7:` slice for `"skipped_breakdown"`, `"gate_blocked"`,
  `"parked_rate"`, `"additive"`/`"legacy"`. This test won't fail from adding
  `closed_via_recovery` prose to SKILL.md, but if the SKILL.md update should
  be test-enforced (matching the ENH-2404/ENH-2601 precedent), add an
  analogous new test (e.g. `test_skill_step6a_reads_closed_via_recovery_key`).
  [Agent 1 + Agent 2 finding, confirmed by both]
- **Confirmed no breakage**: `test_finalize_writes_summary_json` (lines
  3284-3289) substring-checks the action text for `"summary.json"`,
  `"verdict"`, `"subloop_outcome_..."` only — not the literal printf format
  string — and no test asserts on `summary.json` key order (all consumption
  is `json.loads` + dict `in`/index lookups). A new key can be spliced
  anywhere in the printf format string or appended at the end with zero risk
  to existing tests. [Agent 2 + Agent 3 finding]

### Documentation
- `docs/reference/json-output-contracts.md` — documents `summary.json`
  schema.
- `skills/audit-loop-run/SKILL.md` — Step 6a's ENH-2404 key list.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — the `auto-refine-and-implement` section's
  "Closure accounting" paragraph (immediately after the FSM-flow diagram)
  prose-enumerates the current schema (`verdict`, `NOT_CLOSED`/`SKIPPED`,
  `ERRORED`, `verify_verdict`, `verify_returncode`) and needs a
  `closed_via_recovery` sentence added, mirroring how it documents
  `verify_verdict`'s provenance. [Agent 2 finding]
- **Correction**: `docs/reference/json-output-contracts.md` currently has
  **no existing enumeration** of `closed`/`skipped`/`skipped_breakdown`/
  `parked_rate`/`gate_blocked` at all (confirmed via grep — zero matches).
  Step 5's "consider updating" implies an existing schema table to amend;
  there isn't one — this would be a net-new schema section, not an edit.
  [Agent 2 finding]

## Scope Boundaries

**In scope**:
- Adding `closed_via_recovery` computation and field to `auto-refine-and-implement.yaml`'s `finalize` state
- Writing the `$RUN_DIR/$P-skipped-ids.txt` derived-IDs snapshot
- Test coverage for the new counter and its zero-input default
- Documenting the field in `docs/guides/LOOPS_REFERENCE.md`

**Out of scope**:
- Changes to `sprint-refine-and-implement.yaml` (propagates the new key automatically via its existing `cat summary.json`)
- Changes to `autodev.yaml`'s ledger-writing sites (already emit the needed data)
- Any change to `parked_rate`'s existing computation or meaning

## Impact

- **Priority**: P3 - visibility/reporting improvement, not a correctness bug
- **Effort**: Small - single counter added to an existing `finalize` state, following established snapshot/diff patterns
- **Risk**: Low - additive field in `summary.json`; no existing test asserts on key order or exhaustive key set
- **Breaking Change**: No

## Resolution

Implemented as specified. `auto-refine-and-implement.yaml`'s `finalize` state
now derives `$RUN_DIR/auto-refine-and-implement-skipped-ids.txt` from
`autodev-skipped.txt` (next to the existing `SKIPPED_BREAKDOWN` computation),
intersects it against the existing `$P-done-now.txt` snapshot via `comm -12`
into `CLOSED_VIA_RECOVERY`, and adds `closed_via_recovery` to both the
`summary.json` printf and the human-readable finalize log line. Added the
`skipped_recovered` kwarg to `_run_finalize` (seeds real-ID skip-ledger lines
so the same ID can also be seeded via `done_in_place`) plus two new tests
(`test_finalize_closed_via_recovery_counts_skipped_then_done`,
`test_finalize_closed_via_recovery_zero_when_no_overlap`) and a key-presence
smoke test (`test_finalize_summary_has_enh_2743_key`). Documented the field in
`docs/guides/LOOPS_REFERENCE.md`'s "Closure accounting" paragraph and
`skills/audit-loop-run/SKILL.md` Step 6a, with a matching doc-coupling test
(`test_skill_step6a_reads_closed_via_recovery_key`). Full test suite passes
(15875 passed, 38 skipped); ruff clean; `ll-loop validate` reports the loop
valid (pre-existing unrelated warning only).

## Status

Open

## Sources

- `audit-loop-run-sprint-refine-and-implement-2026-07-18T045753.md` —
  Proposal #3 (visibility)

## Session Log
- `/ll:manage-issue` - 2026-07-23T01:21:36Z - `4c513c9a-ad0e-4ba6-8bb2-b15c00f0558c.jsonl`
- `/ll:ready-issue` - 2026-07-23T01:14:52 - `4947a177-2cdd-4fa8-9397-409b7a6a5e4b.jsonl`
- `/ll:confidence-check` - 2026-07-23T01:10:47 - `13e4240e-f967-43a4-89f6-192093f578f8.jsonl`
- `/ll:wire-issue` - 2026-07-23T01:07:46 - `a8ab3605-cd33-4d01-b372-adc21e63f213.jsonl`
- `/ll:refine-issue` - 2026-07-23T01:01:49 - `8c0250f9-ef2b-4eb5-b183-6f897ea1b541.jsonl`
- `/ll:capture-issue` - 2026-07-23T00:25:52Z - `01b32c17-cae1-4173-b77e-b51fe2c99146.jsonl`
