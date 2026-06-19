---
id: ENH-2218
title: ll-ctx-stats learning test coverage dashboard section
type: enhancement
priority: P4
status: done
parent: EPIC-2207
captured_at: '2026-06-18T15:38:06Z'
completed_at: '2026-06-19T05:56:36Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
confidence_score: 90
outcome_confidence: 81
score_complexity: 20
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 23
---

# ENH-2218: ll-ctx-stats learning test coverage dashboard section

## Summary

`ll-ctx-stats` shows context-window analytics and cache hit rates but nothing about learning test health. Add a `## Learning Tests` section to its output that summarizes registry coverage: total records, proven/stale/refuted breakdown, packages imported in `scripts/` with no record (gap list), and the last audit date.

## Current Behavior

`ll-ctx-stats` provides context-window analytics (per-tool bytes, cache hit rates) and skill-health signals but does not surface any learning test registry information. Users must run the full audit loop (`ll-loop run`) or query the registry CLI (`ll-learning-tests list`) manually to check registry coverage, stale records, or gaps.

## Expected Behavior

`ll-ctx-stats` output should include a `## Learning Tests` section that summarizes registry coverage (total records, proven/stale/refuted counts, gap list, last audit date) whenever `learning_tests.enabled: true`. The section should be omitted entirely when `learning_tests.enabled: false`.

## Motivation

There's currently no at-a-glance view of registry health without running the full audit loop or querying the CLI manually. `ll-ctx-stats` is already the health dashboard for the session; learning test coverage belongs there.

## Implementation Steps

1. In `ll-ctx-stats` CLI handler, add a `learning_tests_stats()` function:
   - Call `list_records()` → compute proven/stale/refuted counts and last record date
   - Grep `scripts/` for all imported packages → cross-reference against registry slugs
   - Compute gap list: packages imported but not in registry
2. Render as a `## Learning Tests` section in the stats output:
   ```
   ## Learning Tests
   Records: 12 total (9 proven, 2 stale, 1 refuted)
   Last record: 2026-06-10
   Coverage gaps (imported, no record): boto3, stripe
   ```
3. Gate behind `learning_tests.enabled`.

## Success Metrics

- `ll-ctx-stats` output includes the learning tests section when `learning_tests.enabled: true`
- The gap list matches packages found in imports but absent from the registry
- Stale records are counted separately from refuted
- Section is omitted (not an empty block) when `learning_tests.enabled: false`

## Scope Boundaries

- **In scope**: Adding a `## Learning Tests` section to `ll-ctx-stats` output; computing proven/stale/refuted counts from the registry; detecting coverage gaps via import scan of `scripts/`; gating behind `learning_tests.enabled`
- **Out of scope**: Automated remediation of stale or refuted records; deep audit of individual learning tests; modifying the `ll-learning-tests` CLI itself

## Impact

- **Priority**: P4 - Dashboard improvement, not blocking any current workflow, tracked under EPIC-2207
- **Effort**: Small - Adds one function call and a render section to existing `ll-ctx-stats` output
- **Risk**: Low - Gated behind `learning_tests.enabled` config flag; no risk to existing stats output
- **Breaking Change**: No - New optional section, gated by config

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Implementation step 1 ("Call `list_records()` → compute proven/stale/refuted counts") reads `record.status` from the registry. After ENH-2208, a record with `status: proven` may be date-old and would be treated as stale at runtime. The dashboard would show it as "proven" while the gate blocks — misleading users who check `ll-ctx-stats` before running the sprint. The proven/stale counts must apply date-aware arithmetic: call `is_record_stale(record, lt_config)` (from ENH-2208) for each proven record and reclassify date-old ones into a stale bucket. The stat output should reflect gate-truth, not raw registry status. See [[ENH-2208]].

**Note** (added by `/ll:audit-issue-conflicts`): Implementation step 1 also includes "Grep `scripts/` for all imported packages" to build the gap list. ENH-2214 and ENH-2216 are already extracting a shared `get_imported_packages(source_dirs)` utility into `scripts/little_loops/learning_tests/import_scan.py`. ENH-2218 must call that utility rather than reimplementing the grep inline. If ENH-2218 ships before ENH-2214/ENH-2216, it should own `import_scan.py` creation and publish the utility for the others to consume. The regex must match the canonical pattern in `learning_tests_gate.py` to avoid a third divergent implementation. See [[ENH-2214]] and [[ENH-2216]].

## Labels

`enhancement`, `captured`, `learning-tests`, `dashboard`

## Resolution

Added `## Learning Tests` section to `ll-ctx-stats` output:
- `_load_lt_config()` reads `LearningTestsConfig` from `.ll/ll-config.json`
- `_compute_learning_tests_stats()` applies date-aware staleness reclassification (proven records beyond `stale_after_days` counted as stale per ENH-2208), uses `get_imported_packages()` from `import_scan.py` (per ENH-2214/2216 note), and builds the gap list via `slugify()` cross-reference
- `_render_learning_tests_section()` prints the section after Skill health
- `lt_stats` threaded through `_render()` and `_print_json()` (JSON key: `learning_tests`)
- Section gated behind `learning_tests.enabled`; omitted entirely when disabled
- 9 new tests covering: enabled/disabled gating, count rendering, date-aware stale reclassification, gap list detection, no-gap case, JSON mode (enabled/disabled)

## Session Log
- `/ll:ready-issue` - 2026-06-19T05:36:41 - `609c7567-dd74-4539-85d9-3c10cfd22637.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:50:30 - `2a1b4900-886d-46f7-9096-478aa4b8e4b3.jsonl`
- `/ll:format-issue` - 2026-06-18T19:33:27 - `0f6c8504-40cd-42d9-863b-234192efbe8e.jsonl`

- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`

- `/ll:manage-issue` - 2026-06-19T05:56:36Z - current session

**Open** | Created: 2026-06-18 | Priority: P4
