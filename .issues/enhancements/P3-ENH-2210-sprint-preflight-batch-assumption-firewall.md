---
id: ENH-2210
title: Sprint pre-flight batch assumption-firewall before ll-sprint execution
type: enhancement
priority: P3
status: open
parent: EPIC-2207
depends_on: [ENH-2209, ENH-2208]
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
---

# ENH-2210: Sprint pre-flight batch assumption-firewall before ll-sprint execution

## Summary

`ll-sprint` dispatches claude invocations per issue without first validating that the external-API assumptions of those issues are proven. Add a pre-flight phase that aggregates all `learning_tests_required` targets across the sprint, deduplicates them, and gates the sprint on a single `ready-to-implement-gate` run before any implementation begins.

## Motivation

Running an issue mid-sprint only to hit an unproven assumption wastes a full worktree invocation. Batching the gate check upfront surfaces the gap in seconds, before any expensive agent work is committed.

## Implementation Steps

1. In `ll-sprint` (or the sprint FSM, per FEAT-1899), add a pre-flight state after issue parsing and before the first wave dispatch.
2. Parse `learning_tests_required` from each sprint issue's frontmatter via `ll-issues show --json`.
3. Flatten and deduplicate the full target list across all issues.
4. If the list is empty, skip the pre-flight (no-op).
5. Run `ll-loop run ready-to-implement-gate --context "targets=<comma-list>"`.
6. On `done`: proceed with sprint execution.
7. On `blocked`: print which targets failed and which issues depend on them; abort with exit code 1 unless `--skip-learning-gate` is passed.
8. Gate the pre-flight behind `learning_tests.enabled` so it's opt-in.

## Success Metrics

- A sprint with two issues both requiring `anthropic` only probes the registry once
- If any target is unproven, sprint aborts with a clear message naming the blocking issue IDs
- `--skip-learning-gate` bypasses the pre-flight for emergency runs
- When `learning_tests.enabled: false`, pre-flight is skipped entirely

## Scope Boundaries

- **In scope**: Pre-flight validation of learning test targets before sprint execution; deduplication of targets across sprint issues; gating sprint execution on `ready-to-implement-gate` results; integration with sprint FSM dispatch logic
- **Out of scope**: Changes to how learning tests are defined or registered in the registry; modification of individual issue execution logic within a sprint

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` or sprint FSM definition — Add pre-flight state after issue parsing and before wave dispatch
- Sprint loop YAML (`.loops/sprints/`) — Integrate `ready-to-implement-gate` as a pre-flight step, routing `done` to execution and `blocked` to abort

### Dependent Files (Callers/Importers)
- TBD — identify callers of `ll-sprint` that need `--skip-learning-gate` propagated

### Tests
- TBD — add tests for pre-flight gate: dedup behavior, empty-target no-op, abort on unproven, bypass with flag

### Documentation
- TBD — document `learning_tests.enabled` config option and `--skip-learning-gate` CLI flag

### Configuration
- `learning_tests.enabled` (boolean, default `false`) — new config key to opt into the pre-flight gate

---

## Cross-Reference: Shared Utility with ENH-2219

**Note** (added by EPIC-2207 scoping review): The gating logic for sprint pre-flight should be extracted into a shared utility at `scripts/little_loops/learning_tests/gate.py` that both ENH-2210 (sprint-level batch gate) and ENH-2219 (per-worktree gate for `ll-parallel`) call. This avoids two separate implementations needing identical changes when gating behavior evolves.

- **Shared API surface**: `run_proof_gate(issue_file: str) -> tuple[GateResult, list[str]]` where `GateResult` is a `ProofGate` enum (`PASS`, `BLOCKED`) and `list[str]` are the blocking target names
- ENH-2210 calls this once per sprint (batch mode, aggregating all issues)
- ENH-2219 calls this per worktree (single-issue mode)
- `--skip-learning-gate` flag is handled at the caller level, not inside the utility

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue depends on ENH-2209 (auto-population of `learning_tests_required`). The sprint pre-flight's effectiveness relies on `learning_tests_required` being reliably populated in issue frontmatter. To handle issues refined before ENH-2209 ships, the pre-flight should include a fallback: for issues without `learning_tests_required`, perform ad-hoc extraction by importing the shared extraction utility from ENH-2209 rather than duplicating the logic inline.

**Lifecycle note**: The fallback is a temporary compatibility shim for issues refined before ENH-2209 ships. Once ENH-2209 is shipped and all active sprint issues have been re-refined, the fallback path should be flagged for removal via a `TODO(stale-after-ENH-2209)` comment.

This issue is declared as `depends_on: ENH-2209` in frontmatter — soft ordering, not a hard block, because the fallback provides resilience. See [[ENH-2209]].

**Note** (added by `/ll:audit-issue-conflicts`): ENH-2210's sprint pre-flight routes through `ll-loop run ready-to-implement-gate`, which runs via the FSM executor. `executor.py`'s `_execute_learning_state` calls `check_learning_test()` directly — bypassing ENH-2208's stale-age gate. After ENH-2208 ships, a date-old proven record will be passed by the sprint pre-flight even though the same record would block the discoverability hook. The integration map must include `scripts/little_loops/fsm/executor.py` with a note that `_execute_learning_state` must be updated to call `is_record_stale()` (exposed by ENH-2208). This issue is declared `depends_on: ENH-2208` in frontmatter as a hard dependency — the sprint pre-flight gives false confidence without ENH-2208's helper. See [[ENH-2208]].

**Note** (added by `/ll:audit-issue-conflicts`): The canonical path for the shared gate utility is `scripts/little_loops/learning_tests/gate.py` (confirmed by ENH-2208). Downstream calls from this issue should import from that path. See [[ENH-2208]].

**Note** (added by `/ll:audit-issue-conflicts`): The Configuration section of this issue labels `learning_tests.enabled` as a "new config key." This is incorrect — the key already exists in `config-schema.json` (added in an earlier feature). ENH-2210 must not add a new schema entry for this key. Only the pre-flight logic wiring is new; the config key itself requires no schema changes. See [[ENH-2212]].

**Note** (added by `/ll:audit-issue-conflicts`): The fallback for issues without `learning_tests_required` ("import the shared extraction utility from ENH-2209") requires ENH-2209 to deliver `scripts/little_loops/learning_tests/extractor.py` with `extract_learning_targets(issue_text: str) -> list[str]`. Without this helper, the fallback cannot be implemented as a Python import. Verify ENH-2209 has committed to this artifact before implementing the fallback. See [[ENH-2209]].

## API/Interface

- **Config key**: `learning_tests.enabled` (boolean, default `false`) — enables the pre-flight assumption gate
- **CLI flag**: `ll-sprint --skip-learning-gate` — bypasses the pre-flight check for emergency runs when `learning_tests.enabled: true`

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-18T21:17:06 - `23eb26e5-163c-41e9-bc83-173b75524706.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:50:29 - `2a1b4900-886d-46f7-9096-478aa4b8e4b3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:04:54 - `e8724251-0b1a-456e-af9e-59fd2df092b4.jsonl`
- `/ll:format-issue` - 2026-06-18T19:31:56 - `b3ad1547-68da-4676-8ad5-face35377857.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`
