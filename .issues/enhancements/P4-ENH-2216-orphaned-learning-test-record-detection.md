---
id: ENH-2216
title: Orphaned learning test record detection
type: enhancement
priority: P4
status: done
parent: EPIC-2207
captured_at: '2026-06-18T15:38:06Z'
completed_at: '2026-06-19T05:09:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
confidence_score: 97
outcome_confidence: 84
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 22
---

# ENH-2216: Orphaned learning test record detection

## Summary

When a package is removed from the project, its learning test record in `.ll/learning-tests/` persists indefinitely. Add detection for orphaned records — registry entries for packages that are no longer imported anywhere in the project source — surfaced either as a `ll-learning-tests orphans` subcommand or as an additional section in the `learning-tests-audit` loop.

## Current Behavior

When a package is removed from the project, its learning test record in `.ll/learning-tests/` persists indefinitely with no automated detection mechanism. Orphaned records accumulate silently, skewing coverage metrics and requiring manual audit to identify stale entries.

## Expected Behavior

Orphaned learning test records — those whose target package is no longer imported anywhere in the project source — are automatically detectable via tooling. Maintainers can run a single command to surface them for review and atomically mark them stale or remove them.

## Motivation

Orphaned records skew coverage metrics and create confusion ("why do we have a proven record for `boto3` — we don't use it"). Detecting them is cheap (a grep across source files) and allows bulk `mark-stale` or deletion.

## Success Metrics

- Detection of all orphaned records from a single CLI invocation
- Completion in under 1 second for the current codebase size
- Zero false positives for standard Python import patterns (simple `import X` / `from X import Y`)
- Configurable scope prevents incorrect classification of packages used only in test files

## Scope Boundaries

- **In scope**: Detection of records whose target package has no `^import <slug>` or `^from <slug>` match in configured source directories (default: `scripts/`)
- **Out of scope**: Transitive dependency detection — if package A is removed and B depends on A, B's record is not flagged
- **Out of scope**: Automatic deletion of records without human review — only `mark-stale` is offered as the mutation
- **Out of scope**: Package-level install detection (pip list or similar) — only import-grep is used

## Proposed Solution

Two options, with Option A preferred for composability:

- **Option A (preferred)**: New `ll-learning-tests orphans` CLI subcommand. Runs `list_records()` to enumerate all known targets, greps configured source directories for `^import <slug>` or `^from <slug>` for each target, and reports records with no import match. Accepts `--mark-stale` for atomic bulk stale marking.
- **Option B**: Extend the `learning-tests-audit.yaml` loop with a `detect_orphans` state that runs the same grep logic and populates an "Orphaned Records" section in the triage report.

The grep-based detection is intentionally simple — packages are imported via standard Python `import`/`from` syntax, making a line-level regex sufficient without AST parsing.

## API/Interface

New CLI subcommand:

```
ll-learning-tests orphans [--mark-stale] [--scope scripts/,src/]
```

- **Default behavior**: Lists all orphaned records with their target package name and last modified date
- **`--mark-stale`**: Atomically marks all orphaned records stale and reports the count
- **`--scope`**: Comma-separated list of directories to scan for imports (default: value of `learning_tests.scan_dirs` config key, fallback `scripts/`)
- **Exit code**: 1 if orphans are found (informational), 0 if none found or `--mark-stale` used

If Option B is chosen instead, no new CLI surface — the audit loop gains a `detect_orphans` state.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/learning_tests.py` — new `orphans` subcommand (or extend existing CLI group)
- If Option B: `.loops/learning-tests-audit.yaml` — add `detect_orphans` state between stale detection and report generation

### Dependent Files (Callers/Importers)
- `scripts/little_loops/learning_tests/__init__.py` — `list_records()` and any bulk update functions used by `--mark-stale` (no `registry.py` exists; public API lives in `__init__.py`)

### Similar Patterns
- The existing `mark-stale` subcommand in `learning_tests.py` serves as the implementation pattern for the `orphans` subcommand

### Tests
- `scripts/tests/test_learning_tests.py` — add test cases for orphans detection, `--mark-stale`, and `--scope` filtering

### Documentation
- `docs/reference/API.md` — document `orphans` subcommand if Option A is selected

### Configuration
- `.ll/ll-config.json` — `learning_tests.scan_dirs: ["scripts/"]` (canonical key, default `["scripts/"]`) — shared with ENH-2214's release gate to drive `get_imported_packages()` in both callers. Do not use `orphan_scope`; the key is named for the broader scan-dirs purpose.

## Implementation Steps

1. Option A — new CLI subcommand: Add `ll-learning-tests orphans` that:
   - Runs `list_records()` to get all known targets
   - Greps `scripts/` for `^import <slug>|^from <slug>` for each target
   - Prints records where no import is found
   - Accepts `--mark-stale` flag to atomically mark all orphans stale

2. Option B — audit loop extension: Add a `detect_orphans` state to `learning-tests-audit.yaml` between stale detection and report generation, populating an "Orphaned Records" section in the triage report.

3. Prefer Option A for composability; Option B if the audit loop already collects the data.

## Impact

- **Priority**: P4 — valuable quality-of-life automation but non-critical; orphaned records don't block any workflow
- **Effort**: Small — detection is a simple grep-based check; CLI subcommand pattern already exists in the codebase (`mark-stale`)
- **Risk**: Low — read-only detection by default; `--mark-stale` is opt-in mutation with well-understood side effects
- **Breaking Change**: No — purely additive functionality

## Acceptance Signals

- `ll-learning-tests orphans` lists records for packages not found in any `scripts/` file
- `ll-learning-tests orphans --mark-stale` marks them all and reports count
- A package that appears only in test files (not production source) is configurable: `orphan_scope: [scripts/, src/]`
- The audit loop (if extended) includes orphans in its triage report

## Labels

`enhancement`, `captured`, `learning-tests`, `registry`, `cli`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-2214 (release gate) both independently implement grep-based import scanning of `scripts/`. To avoid duplicated code and divergent behavior, extract a shared `get_imported_packages(source_dirs)` utility into `scripts/little_loops/learning_tests/import_scan.py` that both issues call. See [[ENH-2214]].

**Note** (added by `/ll:audit-issue-conflicts`): This issue's `--mark-stale` flag writes `status: stale` to disk for orphaned records. ENH-2208 adds a parallel staleness channel: date-based staleness applied at runtime without disk mutation. These are distinct and intentionally separate — disk mutation is appropriate for orphans (packages no longer used), while age-based staleness is a runtime judgment on still-imported packages. Consumers that read `status: stale` from the registry (e.g., ENH-2214's release gate, ENH-2218's dashboard) must handle both channels: check `is_record_stale(record, lt_config)` for age-based staleness in addition to `record.status == "stale"` for disk-marked orphans. See [[ENH-2208]].

**Note** (added by `/ll:audit-issue-conflicts`; resolved by review-epic): The canonical config key is **`learning_tests.scan_dirs`** (defaulting to `['scripts/']`). Both this issue and ENH-2214 must use this key as the `source_dirs` argument to `get_imported_packages()` in `import_scan.py`. The former `orphan_scope` name is retired. See [[ENH-2214]].

## Resolution

Implemented Option A: new `ll-learning-tests orphans` CLI subcommand.

- Added `cmd_orphans()` to `scripts/little_loops/cli/learning_tests.py`
- Reuses `get_imported_packages()` from existing `import_scan.py` (shared with ENH-2214)
- Package name extracted as first whitespace-delimited word of `record.target`, lowercased
- `--mark-stale` atomically marks all orphans stale (exits 0); without flag exits 1 if orphans found
- `--scope` overrides scan directories; falls back to `learning_tests.scan_dirs` config key, then `scripts/`
- 11 new tests in `test_cli_learning_tests.py::TestMainLearningTestsOrphans`

## Session Log
- `/ll:ready-issue` - 2026-06-19T05:00:58 - `28912858-56a2-4740-bb0f-7162ee3ab912.jsonl`
- `/ll:confidence-check` - 2026-06-18T23:00:00 - `7e33f84f-43f1-4a02-839a-6c08a435bb99.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T21:17:06 - `23eb26e5-163c-41e9-bc83-173b75524706.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:50:30 - `2a1b4900-886d-46f7-9096-478aa4b8e4b3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:04:54 - `e8724251-0b1a-456e-af9e-59fd2df092b4.jsonl`
- `/ll:format-issue` - 2026-06-18T19:32:23 - `33db5684-2de8-4975-99ca-a0b1179e0b12.jsonl`

- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`

**Open** | Created: 2026-06-18 | Priority: P4
