---
id: ENH-2214
title: Release gate — block ll-manage-release on stale/refuted active dependencies
type: enhancement
priority: P3
status: open
parent: EPIC-2207
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
---

# ENH-2214: Release gate — block ll-manage-release on stale/refuted active dependencies

## Summary

`/ll:manage-release` prepares changelogs and creates git tags without checking whether any actively-imported packages have stale or refuted learning test records. Add a pre-release check that cross-references `ll-learning-tests list` against packages imported in the project source, and surfaces stale/refuted records as configurable release blockers.

## Current Behavior

`/ll:manage-release` prepares changelogs and creates git tags without any pre-flight check of learning test record health. Stale or refuted records in the learning test registry are not surfaced during the release process, meaning releases can be cut while the project depends on unverified or outdated API assumptions about external packages.

## Expected Behavior

Before creating a git tag, `/ll:manage-release` should run a "Learning Test Pre-Release Audit" step that:

- Queries `ll-learning-tests list` for stale or refuted records
- Cross-references matched package names against imports found in `scripts/`
- Prints a warning table showing any actively-imported packages with stale/refuted records, including package name, status, record date, and days since proven
- Respects the `learning_tests.release_gate` config value: `block` aborts the release with exit 1; `warn` (default) continues with a visible printed warning
- Excludes packages that are not imported anywhere in project source

## Motivation

Shipping a release built on unverified or outdated API assumptions is a latent quality risk. The release moment is a natural forcing function: if you can't prove your external dependencies behave as expected, you should know before you tag.

## Proposed Solution

Add a pre-release audit step to `/ll:manage-release` (in `commands/manage-release.md`) that:

1. Runs `ll-learning-tests list` and filters to records with `status: stale` or `status: refuted`
2. Greps `scripts/` for `^import |^from ` patterns to find actively-used packages
3. Cross-references the two lists to surface stale/refuted records for imported packages
4. Prints a warning table with columns: package, status, record date, days since proven
5. Checks the `learning_tests.release_gate` config key: `block` aborts with exit 1; `warn` (default) continues with a visible warning

## Scope Boundaries

- **In scope**: Adding a configurable pre-release check for stale/refuted learning test records in `/ll:manage-release`
- **Out of scope**: Automated re-running of stale learning tests during the release process; changes to the `ll-learning-tests` CLI itself; retroactive validation of existing releases; integration with other publish channels (e.g., npm publish hooks)

## API/Interface

### New Config Key

```yaml
# In .ll/ll-config.json
learning_tests:
  release_gate: warn  # "block" | "warn" (default: warn)
```

- `LearningTestsConfig` schema in `config-schema.json` extended with `release_gate` enum field (`"block"` | `"warn"`)
- Corresponding dataclass field added to `LearningTestsConfig` in `scripts/little_loops/config/schema.py`

## Integration Map

### Files to Modify
- `commands/manage-release.md` - Add pre-release audit step after changelog generation and before tag creation
- `scripts/little_loops/config/schema.py` - Add `release_gate` field to `LearningTestsConfig` dataclass
- `config-schema.json` - Add `release_gate` enum to `learning_tests` schema definition

### Dependent Files (Callers/Importers)
- TBD - use grep to find references to `LearningTestsConfig` or `manage-release`

### Similar Patterns
- TBD - search for consistency with other release steps and config-driven behavior in the codebase

### Tests
- TBD - identify test files for `/ll:manage-release` and `ll-learning-tests`

### Documentation
- `docs/reference/API.md` - May need update for new `release_gate` config key

### Configuration
- `.ll/ll-config.json` - `learning_tests.release_gate` key added with default `warn`

## Implementation Steps

1. In `/ll:manage-release` (skill file), add a "Learning Test Pre-Release Audit" step after changelog generation and before the tag is created.
2. Run `ll-learning-tests list` and filter to `status: stale` or `status: refuted`.
3. Cross-reference against packages imported in `scripts/` (grep for `^import|^from` patterns).
4. If any stale/refuted records match actively-used packages:
   - Print a table: package | status | record date | days since proven
   - If `learning_tests.release_gate: block` (new config key), abort with exit 1
   - If `learning_tests.release_gate: warn` (default), print warning and continue
5. Add `release_gate` to `LearningTestsConfig` schema and dataclass with default `warn`.

## Acceptance Signals

- Release prep with a stale `anthropic` record prints a warning table
- `release_gate: block` prevents the tag from being created
- `release_gate: warn` continues with a visible warning in release output
- Packages not imported anywhere in source are excluded from the check

## Impact

- **Priority**: P3 - Medium - Important quality safeguard but not blocking existing workflows; releases still function correctly, they just lack visibility into stale dependency knowledge
- **Effort**: Small - Leverages existing `ll-learning-tests list` infrastructure; primarily wiring and config schema changes in `/ll:manage-release` and config layer
- **Risk**: Low - The check is non-destructive (read-only query + config key evaluation); `block` mode is opt-in via explicit config change
- **Breaking Change**: No - Default behavior (`warn`) is additive and non-breaking; existing workflows are unaffected

## Labels

`enhancement`, `learning-tests`, `release`, `quality-gate`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue adds a machine-checkable learning test gate at the release stage. A complementary gate at the pre-implementation/eval stage is covered by ENH-2221. These are distinct lifecycle stages with different data sources (project-wide import scan vs issue-frontmatter targets) and different behaviors (`block`/`warn` config vs `exit_code` criterion in eval YAML). See [[ENH-2221]] for the pre-implementation gate.

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-2216 (orphaned record detection) both independently implement grep-based import scanning of `scripts/`. To avoid duplicated code and divergent behavior, extract a shared `get_imported_packages(source_dirs)` utility into `scripts/little_loops/learning_tests/import_scan.py` that both issues call. See [[ENH-2216]].

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-2217 (history context injection) both query the learning test registry for external display. The registry query pattern is identical (`list_records()`, `check_learning_test()`), but the formatting surface differs (CLI warning table vs Markdown table). No shared formatter needed, but share registry query awareness. See [[ENH-2217]].

**Note** (added by `/ll:audit-issue-conflicts`): This issue's implementation step 2 ("filter to `status: stale` or `status: refuted`") is insufficient after ENH-2208 ships. ENH-2208 adds date-based staleness at runtime without mutating `record.status` on disk — a record can be `status: proven` but date-old, and `ll-learning-tests list` would not surface it. The release gate would give a false clean signal. Replace step 2 with: filter to records where `record.status == 'refuted'` OR where `is_record_stale(record, lt_config)` returns True (using ENH-2208's exportable helper). Load `LearningTestsConfig` and apply the same threshold as the runtime gate. See [[ENH-2208]].

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-18T20:50:30 - `2a1b4900-886d-46f7-9096-478aa4b8e4b3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:04:54 - `e8724251-0b1a-456e-af9e-59fd2df092b4.jsonl`
- `/ll:format-issue` - 2026-06-18T19:33:00 - `d32ab305-2ca5-4ecb-8748-da90ac6cd83b.jsonl`

- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`

**Open** | Created: 2026-06-18 | Priority: P3
