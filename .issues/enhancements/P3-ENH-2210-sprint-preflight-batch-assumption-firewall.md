---
id: ENH-2210
title: Sprint pre-flight batch assumption-firewall before ll-sprint execution
type: enhancement
priority: P3
status: open
parent: EPIC-2207
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

## API/Interface

- **Config key**: `learning_tests.enabled` (boolean, default `false`) — enables the pre-flight assumption gate
- **CLI flag**: `ll-sprint --skip-learning-gate` — bypasses the pre-flight check for emergency runs when `learning_tests.enabled: true`

## Session Log
- `/ll:format-issue` - 2026-06-18T19:31:56 - `b3ad1547-68da-4676-8ad5-face35377857.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`
