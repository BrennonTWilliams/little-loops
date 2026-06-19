---
id: ENH-2214
title: "Release gate \u2014 block ll-manage-release on stale/refuted active dependencies"
type: enhancement
priority: P3
status: done
parent: EPIC-2207
captured_at: '2026-06-18T15:38:06Z'
completed_at: '2026-06-19T04:05:13Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
confidence_score: 93
outcome_confidence: 80
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 23
score_change_surface: 21
decision_needed: false
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

### New Config Keys

```yaml
# In .ll/ll-config.json
learning_tests:
  release_gate: warn    # "block" | "warn" (default: warn)
  scan_dirs: ["scripts/"]  # source dirs for import scanning (default: ["scripts/"])
```

- `LearningTestsConfig` schema in `config-schema.json` (lines 939–973, `learning_tests` object) extended with `release_gate` enum field (`"block"` | `"warn"`) and `scan_dirs` string-array field
- Corresponding dataclass fields added to `LearningTestsConfig` in `scripts/little_loops/config/features.py:LearningTestsConfig` (line 392)
- Note: `config-schema.json` has `"additionalProperties": false` on the `learning_tests` object (line 972); both the schema and the dataclass must be updated together

## Integration Map

### Files to Modify
- `commands/manage-release.md` — Add "Learning Test Pre-Release Audit" step in `### 5. Wave 2: Synthesis and Execution / #### 5b. Execute Actions`, before `##### Action: tag` (line 280) in the single-action path and before `tag` in the `##### Action: full` sequence (line 365)
- `scripts/little_loops/config/features.py` — Add `release_gate: str = "warn"` and `scan_dirs: list[str] = field(default_factory=lambda: ["scripts/"])` to `LearningTestsConfig` dataclass (line 392); update `from_dict()` to read both new keys
- `config-schema.json` — Add `release_gate` enum property (`"block" | "warn"`, default `"warn"`) and `scan_dirs` string-array property to the `learning_tests` object (lines 939–973); `"additionalProperties": false` at line 972 requires both changes together
- `scripts/little_loops/learning_tests/import_scan.py` — NEW file: extract `get_imported_packages(source_dirs: list[Path]) -> set[str]` from `learning_tests_gate.py:_extract_packages()` using `_PY_IMPORT_RE = re.compile(r"^(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)` (per ENH-2216 shared-utility coordination; see Scope Boundary notes)
- `scripts/little_loops/hooks/learning_tests_gate.py` — Update `_extract_packages()` to delegate to `import_scan.get_imported_packages()` to avoid duplicated regex logic

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/config/core.py:BRConfig._parse_config()` (line 270) — loads `LearningTestsConfig` via `from_dict(data.get("learning_tests", {}))` and stores as `self._learning_tests`; no code changes needed, but the new fields must exist in `from_dict()` before config round-trips
- `scripts/little_loops/hooks/learning_tests_gate.py:gate()` — sibling file that currently owns `_extract_packages()`; will be updated to delegate to `import_scan.py`
- `scripts/little_loops/hooks/install_learning_gate.py:gate()` — shares the `_load_lt_config()` helper pattern; no direct changes, but aware of `LearningTestsConfig` shape
- `skills/ll-manage-release/SKILL.md` — thin Codex bridge shim that redirects to `commands/manage-release.md`; no changes needed

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/hooks/install_learning_gate.py:gate()` — canonical `learning_tests.enabled` guard + `block`/`warn` enum pattern; the `_load_lt_config()` helper (reads `.ll/ll-config.json` via `resolve_config_path()`) is the reference for the config loading idiom
- `scripts/little_loops/cli/sprint/run.py:_run_learning_gate_preflight()` — CLI-level abort-on-fail gate that returns `1` to halt the sprint; the `return 1` / `return 0` pattern is the model for `block`/`warn` behavior
- `config-schema.json` lines 957-961 (`discoverability.mode` enum: `["off", "warn", "block"]`) — exact schema template to copy for the `release_gate` enum
- `scripts/little_loops/learning_tests/gate.py:is_record_stale()` — staleness helper (signature: `is_record_stale(record: LearnTestRecord, stale_after_days: int) -> bool`); must be called instead of relying on `record.status == "stale"` (see ENH-2208 note in Scope Boundary)
- `scripts/little_loops/hooks/learning_tests_gate.py:_PY_IMPORT_RE` — `re.compile(r"^(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)` — reference regex for `import_scan.py`

### Tests

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_config.py:TestLearningTestsConfig` (line 2294) — add `test_release_gate_defaults_to_warn` and `test_release_gate_block_from_dict` alongside existing `test_enabled_defaults_to_false` and `test_from_dict_with_all_fields`
- `scripts/tests/test_learning_tests_discoverability.py:TestGateDisabled` — reference pattern for `enabled=False` no-op tests using `_write_config()` and `_write_record()` helpers
- `scripts/tests/test_sprint_integration.py:TestSprintPreflightGate` — reference pattern for abort-on-fail gate tests using `patch("subprocess.run")`
- New test class `TestReleaseGate` (in `scripts/tests/test_learning_tests.py` or new `test_release_gate.py`) — test `release_gate: block` aborts (returns 1), `release_gate: warn` continues (returns 0), `enabled: false` skips entirely, packages not found in `scan_dirs` are excluded

### Documentation
- `docs/reference/API.md` — May need update for new `release_gate` and `scan_dirs` config keys
- `docs/guides/LEARNING_TESTS_GUIDE.md` — Covers learning tests registry and gate patterns; may need a section for the release gate

### Configuration
- `.ll/ll-config.json` — `learning_tests.release_gate` key (default `warn`) and `learning_tests.scan_dirs` key (default `["scripts/"]`)

## Implementation Steps

1. **Extend `LearningTestsConfig`** in `scripts/little_loops/config/features.py:LearningTestsConfig` (line 392):
   - Add `release_gate: str = "warn"` field (valid values: `"block"` | `"warn"`)
   - Add `scan_dirs: list[str] = field(default_factory=lambda: ["scripts/"])` field (canonical key per Scope Boundary note; used as source dirs for import scanning)
   - Update `from_dict()` to read `data.get("release_gate", "warn")` and `data.get("scan_dirs", ["scripts/"])`

2. **Update `config-schema.json`** learning_tests object (lines 939–973):
   - Add `release_gate` enum property: `{"type": "string", "enum": ["block", "warn"], "default": "warn"}` (mirror `discoverability.mode` pattern at lines 957-961)
   - Add `scan_dirs` array property: `{"type": "array", "items": {"type": "string"}, "default": ["scripts/"]}`
   - Note: `"additionalProperties": false` at line 972 — adding without updating schema causes config validation errors

3. **Create `scripts/little_loops/learning_tests/import_scan.py`** — shared utility (per ENH-2216 Scope Boundary coordination):
   - `_PY_IMPORT_RE = re.compile(r"^(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)`
   - `def get_imported_packages(source_dirs: list[Path]) -> set[str]` — walks each dir, reads `*.py` files, applies regex, returns unique top-level package names
   - Update `scripts/little_loops/hooks/learning_tests_gate.py:_extract_packages()` to delegate to `import_scan.get_imported_packages()`

4. **Add pre-release audit step to `commands/manage-release.md`** — insert before `##### Action: tag` (line 280) and before `tag` in the `full` sequence (line 365):
   - Guard: check `{{config.learning_tests.enabled}}`; if false or absent, skip the entire audit
   - Load registry: call `ll-learning-tests list` (outputs JSON array of records)
   - Filter: keep records where `status == "refuted"` OR `is_record_stale(record, stale_after_days)` — do NOT rely solely on `status == "stale"` (ENH-2208 stores staleness at runtime without mutating disk status)
   - Scan imports: grep `{{config.learning_tests.scan_dirs}}` directories using `_PY_IMPORT_RE` pattern to get active package names
   - Cross-reference: intersection of stale/refuted record `target` names with actively-imported packages; exclude packages not found in source
   - If matches found: print warning table (package | status | record_date | days_since_proven)
   - Apply gate: `{{config.learning_tests.release_gate}}` == `"block"` → abort with exit 1; `"warn"` (default) → continue with visible warning

5. **Add tests**:
   - In `scripts/tests/test_config.py:TestLearningTestsConfig`: add `test_release_gate_defaults_to_warn` and `test_release_gate_block_from_dict`
   - New test class `TestReleaseGate`: test `block` mode aborts, `warn` mode continues, `enabled: false` skips, unimported packages excluded (model after `test_learning_tests_discoverability.py:TestGateDisabled` and `test_sprint_integration.py:TestSprintPreflightGate`)

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

**Note** (added by `/ll:audit-issue-conflicts`): The pre-release audit step must be skipped entirely when `learning_tests.enabled` is `false` (or absent), consistent with the opt-in pattern across all EPIC-2207 issues. ENH-2217 gates its output on `learning_tests.enabled`; this issue must do the same. A project that opts out of learning test tooling via `enabled: false` should not receive a release-gate warning table. Add this guard at the top of the pre-release step: "if not `lt_config.enabled`, skip the audit." See [[ENH-2217]].

**Note** (added by `/ll:audit-issue-conflicts`; resolved by review-epic): The canonical config key is **`learning_tests.scan_dirs`** (defaulting to `['scripts/']`). Both this issue and ENH-2216 must use this key as the `source_dirs` argument to `get_imported_packages()` in `import_scan.py`. Do not hardcode `scripts/`. See [[ENH-2216]].

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-18_

**Readiness Score**: 81/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 78/100 → MODERATE

### Concerns
- **Wrong file path in Integration Map**: "Files to Modify" lists `scripts/little_loops/config/schema.py` — this file does not contain `LearningTestsConfig`. The correct file is `scripts/little_loops/config/features.py` (line 392).
- **TBD sections require pre-implementation research**: Dependent Files, Similar Patterns, and Tests in the Integration Map are all TBD. Run `grep -rn "LearningTestsConfig" scripts/` and review `test_config.py` coverage before starting.
- **`scan_dirs` config key is undefined**: The Scope Boundary note specifies `learning_tests.scan_dirs` as the canonical source dirs argument, but this field doesn't yet exist in `LearningTestsConfig`. Decide whether this issue adds it to the dataclass/schema or uses `scripts/` as a hardcoded default.

## Session Log
- `/ll:ready-issue` - 2026-06-19T03:49:01 - `df086dae-88f2-43bc-a8b6-ca7fb7d7ec59.jsonl`
- `/ll:confidence-check` - 2026-06-18T00:00:00Z - `df086dae-88f2-43bc-a8b6-ca7fb7d7ec59.jsonl`
- `/ll:refine-issue` - 2026-06-19T03:41:31 - `2a4d8a56-cb18-4817-9724-740e4c1e15f7.jsonl`
- `/ll:confidence-check` - 2026-06-18T00:00:00Z - `7246f1b0-c60a-4639-aac4-6038698839cb.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T21:17:06 - `23eb26e5-163c-41e9-bc83-173b75524706.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:50:30 - `2a1b4900-886d-46f7-9096-478aa4b8e4b3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:04:54 - `e8724251-0b1a-456e-af9e-59fd2df092b4.jsonl`
- `/ll:format-issue` - 2026-06-18T19:33:00 - `d32ab305-2ca5-4ecb-8748-da90ac6cd83b.jsonl`

- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`

**Open** | Created: 2026-06-18 | Priority: P3
