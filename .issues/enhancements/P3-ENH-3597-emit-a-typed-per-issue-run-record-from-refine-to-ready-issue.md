---
id: ENH-3597
type: ENH
title: Emit a typed per-issue run record from refine-to-ready-issue
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T18:51:49Z'
blocks:
- ENH-3599
- ENH-3601
parent: EPIC-3565
relates_to:
- ENH-3577
---

# ENH-3597: Emit a typed per-issue run record from refine-to-ready-issue

## Summary

Make `refine-to-ready-issue` write one typed per-issue run record
(`${context.run_dir}/refine-run-record.json`) on every terminal, alongside the existing
`refine-terminal-class` / `refine-broke-down` files. Additive: no routing in either loop
changes. Step A of the ENH-3577 decomposition.

## Current Behavior

The child reports its result through two ad-hoc files: `refine-terminal-class` (free-text
`proposal_unsound | gate_unmet | infra | spike_inconclusive | decision_unresolved`, absent =
`quality`) and `refine-broke-down`. Autodev infers everything else by re-reading frontmatter.
The child's `done` terminal does not mean "ready" — autodev re-checks with `check_passed`.

## Expected Behavior

Every child exit (`done`, `no_work`, `failed`, `breakdown_issue` → `done`) writes a JSON
record: `{issue_id, outcome, child_ids, evidence_refs, legacy_class, readiness, outcome_confidence}`
where `outcome` is a `PreparationOutcome`. Legacy files keep being written unchanged.

## Proposed Solution

- Add `PreparationOutcome` (`ready | decomposed | cancelled | blocked | deferred | retryable_error`)
  and a `RunRecord` dataclass with `write_run_record(run_dir, record) -> Path` /
  `read_run_record(run_dir) -> RunRecord | None` in a small `little_loops` module.
- Expose a CLI writer (e.g. `ll-issues run-record write ...`) so FSM shell states don't
  hand-roll JSON.
- Call it from `classify_terminal`, `write_broke_down`, `done` and `no_work` paths.
- `outcome = ready` only when the child's own readiness/outcome thresholds are met with fresh
  scores (same predicate autodev's `check_passed` uses) — otherwise `blocked`.
- Mapping from legacy class: `infra`/rate-limit → `retryable_error`;
  `decision_unresolved`, `proposal_unsound`, `quality` → `blocked`;
  `spike_inconclusive`, `gate_unmet` → `deferred`; broke-down → `decomposed`.
- Mirror the record write in `.claude/workflows/refine-to-ready.js`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- `scripts/little_loops/cli/issues/` (writer subcommand)
- `.claude/workflows/refine-to-ready.js` (gitignored, machine-local mirror of the loop)

### Tests
- New unit tests for the record schema/round-trip
- Real-FSM test: each child terminal writes a record whose `outcome` matches the mapping
- `scripts/tests/test_builtin_loops.py` (structural)

## Program Design

### Types

- `PreparationOutcome: Literal["ready", "decomposed", "cancelled", "blocked", "deferred", "retryable_error"]` — per-issue verdict
- `RunRecord: dataclass` — `issue_id`, `outcome`, `child_ids`, `evidence_refs`, `legacy_class`, `readiness`, `outcome_confidence`

### Signatures

- `write_run_record(run_dir: Path, record: RunRecord) -> Path` — writes `refine-run-record.json` atomically
- `read_run_record(run_dir: Path) -> RunRecord | None` — returns `None` when absent or malformed
- `cmd_run_record_write(config: BRConfig, args: argparse.Namespace) -> int` — `ll-issues run-record write` subcommand used by FSM shell states
- `outcome_from_legacy_class(legacy_class: str | None, broke_down: bool, thresholds_met: bool) -> PreparationOutcome` — the mapping table in ENH-3577

### Call Path

`main_issues` -> `cmd_run_record_write` -> `outcome_from_legacy_class` -> `write_run_record`

`refine-to-ready-issue.yaml:classify_terminal` -> `cmd_run_record_write`

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Medium - new record module, writer CLI, and a write at every child terminal
- **Risk**: Low - additive; no routing changes
- **Breaking Change**: No

## Scope Boundaries

- No routing changes in `autodev.yaml` or any other caller; consumers adopt the record in ENH-3599 / ENH-3601 / ENH-3600.
- Legacy files are not removed here.

## Acceptance Criteria

- [ ] Every terminal of `refine-to-ready-issue` writes a valid run record
- [ ] `outcome == "ready"` iff autodev's `check_passed` would pass for the same issue state
- [ ] Legacy `refine-terminal-class` / `refine-broke-down` output is byte-identical to before
- [ ] No routing change in `autodev.yaml` or any other caller

## Parent Issue

Decomposed from ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Status

**Open** | Created: 2026-09-25 | Priority: P3
