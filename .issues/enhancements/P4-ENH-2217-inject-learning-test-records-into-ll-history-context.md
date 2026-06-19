---
id: ENH-2217
title: Inject learning test records into ll-history-context output
type: enhancement
priority: P4
status: done
parent: EPIC-2207
captured_at: '2026-06-18T15:38:06Z'
completed_at: '2026-06-19T05:23:55Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
confidence_score: 88
outcome_confidence: 84
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 17
score_change_surface: 25
---

# ENH-2217: Inject learning test records into ll-history-context output

## Summary

`ll-history-context` generates a `## Historical Context` block for an issue from session corrections and FTS matches. Extend it to also surface relevant learning test records: for each target in `learning_tests_required` (or extracted from the issue text), append the assertion summary so the implementing agent has proof evidence inline without querying the registry separately.

## Current Behavior

`ll-history-context` generates a historical context block for an issue from session corrections and FTS matches, but does not surface learning test records. Agents must query the `ll-learning-tests` registry separately or assume proofs are current with no indication of recency.

## Motivation

Agents starting a new session on an issue must either re-query the registry themselves or assume the proofs are current. Injecting the record summary into the history context block removes that friction and ensures the agent knows both (a) what was proven and (b) how recently.

## Success Metrics

- Learning test records are present in `ll-history-context` output for issues with `learning_tests_required` in frontmatter
- Stale records are visually distinguished in the output (e.g., `stale` status label in the table)
- Empty-results case produces no section markdown at all (not an empty table)
- Added latency under 500ms for typical registry sizes (local filesystem reads)

## Scope Boundaries

- **In scope**: Extending `ll-history-context` output with a `## Learning Test Evidence` subsection; parsing `learning_tests_required` from issue frontmatter; querying the learning test registry per target; gating behind `learning_tests.enabled` and `--for-skill`
- **Out of scope**: Modifying the learning test registry itself (records, staleness, or discoverability); changing the `ll-history-context` CLI interface or argument parsing; creating new CLI commands; modifying issue files

## Implementation Steps

1. In `ll-history-context` (CLI handler at `scripts/little_loops/cli/history_context.py` or similar), after the corrections/FTS block is generated:
2. Parse `learning_tests_required` from the issue frontmatter via `ll-issues show --json <ISSUE_ID>`.
3. For each target, call `check_learning_test(target)`.
4. Append a `## Learning Test Evidence` subsection:
   ```markdown
   ## Learning Test Evidence
   | Target | Status | Date | Pass/Fail/Untested |
   |--------|--------|------|--------------------|
   | anthropic | proven | 2026-05-10 | 4/0/1 |
   | httpx | stale | 2026-01-03 | 3/0/0 |
   ```
5. Gate behind `learning_tests.enabled` and the existing `--for-skill` gating mechanism.

## Acceptance Signals

- `ll-history-context <ISSUE_ID>` for an issue with `learning_tests_required: [anthropic]` includes the record summary
- Stale records are visually distinguished in the table (e.g., `stale` status in the Status column)
- If no records exist for any target, the section is omitted (not an empty table)
- Runs in under 500ms added latency (registry reads are local filesystem)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history_context.py` — extend with learning test registry query and output formatting after the corrections/FTS block

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py` — registers `main_history_context` entry point
- `scripts/little_loops/init/writers.py` — generates `ll-history-context` allowlist entries
- `scripts/tests/test_history_context_cli.py` — CLI integration tests for history context output

### Similar Patterns
- `scripts/little_loops/learning_tests/__init__.py:140` — `check_learning_test(target, base_dir)` registry query
- `scripts/little_loops/learning_tests/gate.py:32` — `is_record_stale(record, stale_after_days)` staleness check
- `scripts/little_loops/learning_tests/release_gate.py` — pattern for iterating targets and formatting status output

### Tests
- `scripts/tests/test_history_context_cli.py` — add tests for `## Learning Test Evidence` section presence/absence

### Documentation
- `docs/reference/API.md` — may need updates for new output format

### Configuration
- `.ll/ll-config.json` — `learning_tests.enabled` gating already defined

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-2214 (release gate) both query the learning test registry for external display. The registry query pattern (`list_records()`, `check_learning_test()`) is shared, but the formatting differs (Markdown table here vs CLI warning table in ENH-2214). No shared formatter is needed, but coordination on registry query shape avoids divergence. See [[ENH-2214]].

**Note** (added by `/ll:audit-issue-conflicts`): Implementation step 3 calls `check_learning_test(target)` and displays its `status` field in the table. After ENH-2208, a record with `status: proven` on disk may be date-old and treated as stale by the runtime gate. The table would display "proven" while the gate blocks — actively misleading the implementing agent. After step 3, apply: `effective_status = "stale (age)" if is_record_stale(record, lt_config) else record.status`. Load `LearningTestsConfig` from project config (accessible via the existing `BRConfig` pattern in `history_context.py`). The acceptance signal "Stale records are visually distinguished" must explicitly cover date-stale records, not only records with `status: stale` on disk. See [[ENH-2208]].

**Note** (added by `/ll:audit-issue-conflicts`): ENH-2217 and ENH-2215 both parse `learning_tests_required` from issue frontmatter independently. To prevent divergent field-name handling or fallback logic, use the same read mechanism as ENH-2215: `ll-issues show --json <ISSUE_ID> | jq '.learning_tests_required // []'` (or a shared Python helper if one is extracted). Coordinate with [[ENH-2215]] to avoid two divergent parsing implementations.

## Session Log
- `/ll:ready-issue` - 2026-06-19T05:16:17 - `330436d7-3e2b-43ef-a129-2c8346d50835.jsonl`
- `/ll:confidence-check` - 2026-06-19T00:00:00Z - `19d86e05-f5a8-4ab9-bddc-73b416dfed97.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T21:17:06 - `23eb26e5-163c-41e9-bc83-173b75524706.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:50:30 - `2a1b4900-886d-46f7-9096-478aa4b8e4b3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:04:54 - `e8724251-0b1a-456e-af9e-59fd2df092b4.jsonl`
- `/ll:format-issue` - 2026-06-18T19:33:28 - `bd499794-07ed-4db0-8537-8038ebf61e47.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`
