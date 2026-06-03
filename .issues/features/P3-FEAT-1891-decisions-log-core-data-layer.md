---
id: FEAT-1891
title: "Decisions Log \u2014 Core Data Layer (schema, config, CRUD)"
type: FEAT
priority: P3
parent: FEAT-948
size: Large
discovered_date: 2026-06-02
completed_at: 2026-06-03 05:24:16+00:00
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
status: done
---

# FEAT-1891: Decisions Log — Core Data Layer (schema, config, CRUD)

## Summary

Implement the foundational data layer for the rules and decisions log: entry type dataclasses, YAML storage at `.ll/decisions.yaml`, `DecisionsConfig` integration into `BRConfig`, and all core CRUD operations.

## Use Case

A developer using the little-loops system wants to track architectural decisions and team-enforced rules as persistent, queryable entries. They log a rule ("All PRs must link an issue ID", enforcement: `required`), record a decision to use YAML over SQLite (with alternatives rejected), and grant a one-time exception for a legacy issue. Later, they query active rules and check which decisions have recorded outcomes — all via a consistent CRUD API backed by `.ll/decisions.yaml`.

## Current Behavior

No decisions/rules log data layer exists. There is no `decisions.py` module, no `DecisionsConfig` class in the config system, no `.ll/decisions.yaml` storage, and no CRUD API for managing rules, decisions, or exceptions.

## Expected Behavior

A complete data layer exists at `scripts/little_loops/decisions.py` providing: typed dataclasses (`RuleEntry`, `DecisionEntry`, `ExceptionEntry`, `DecisionOutcome`), atomic YAML storage, and CRUD functions (`load_decisions`, `save_decisions`, `add_entry`, `list_entries`, `resolve_active`, `set_outcome`). `DecisionsConfig` is integrated into `BRConfig` with full config-schema support and re-exported from the config package.

## Impact

- **Priority**: P3 — Foundational sub-issue of FEAT-948; unblocks UI/CLI layers
- **Effort**: Large — New module, multiple dataclasses, CRUD layer, config integration, schema update, and test coverage
- **Risk**: Low — Fully additive (new module + new config key); no modifications to existing behavior
- **Breaking Change**: No

## Labels

`data-layer`, `decisions-log`, `config`, `feature`

## Parent Issue

Decomposed from FEAT-948: Rules and Decisions Log for Issue Compliance

## Proposed Solution

**Storage**: Single `.ll/decisions.yaml` with a `type` field (`rule | decision | exception`). Follow `scripts/little_loops/sprint.py:142-202` dataclass + YAML pattern.

**IDs**: `CATEGORY-NNN` format (e.g., `NAMING-001`, `WORKFLOW-003`). IDs are stable and never reused; superseded rules retain their ID with a `supersedes` pointer on the replacement.

**Rule evolution**: When a rule is refined or reversed, add a new entry with `supersedes: PRIOR-ID`. Tools treat superseded entries as inactive.

**Extensibility**: Use an open dispatch pattern (registry dict or `elif` chain with a documented extension point) rather than a closed match on the three MVP types, so FEAT-1736's `coupling` type can be added without modifying core dispatch logic.

**PM-Layer schema extension**: Support optional `scope: issue | sprint | quarter | project` and `outcome: {result, measured_at, notes}` fields on `decision` entries (addendum from PM-layer integration discussion).

### Implementation Steps

1. **Design + schema** — define `@dataclass` entry types (`RuleEntry`, `DecisionEntry`, `ExceptionEntry`) in `scripts/little_loops/decisions.py`:
   - Common fields: `id: str`, `type: str`, `timestamp: str`, `category: str`, `labels: list[str]`, `rationale: str`
   - `RuleEntry`: adds `rule: str`, `enforcement: str` (`required | advisory`), `supersedes: str | None`, `issue: str | None`
   - `DecisionEntry`: adds `rule: str`, `alternatives_rejected: str | None`, `issue: str | None`, `scope: str = "issue"`, `outcome: DecisionOutcome | None`
   - `ExceptionEntry`: adds `rule_ref: str`, `issue: str`, `alternatives_rejected: str | None`
   - `@dataclass DecisionOutcome`: `result: str`, `measured_at: str`, `notes: str | None`
   - Use `yaml.safe_load` / `yaml.dump(default_flow_style=False, sort_keys=False)` from `scripts/little_loops/sprint.py:184`

2. **Config** — add `DecisionsConfig` to `scripts/little_loops/config/features.py` (after `IssuesConfig:192`):
   - Fields: `enabled: bool = False`, `log_path: str = ".ll/decisions.yaml"`, `auto_generate: list[str] = []`
   - `from_dict()` factory following `IssuesConfig` pattern
   - Wire into `BRConfig._parse_config()` at `scripts/little_loops/config/core.py:190`: add `self._decisions = DecisionsConfig.from_dict(self._raw_config.get("decisions", {}))`
   - Update `BRConfig.to_dict()` at `core.py:493` — add `decisions` block to the serialization dict
   - Add `from_dict()` import in the import block at `core.py:23-33`
   - Update `config-schema.json` — add `decisions` object schema (`enabled`, `log_path`, `auto_generate`) matching `DecisionsConfig` fields
   - Re-export `DecisionsConfig` from `scripts/little_loops/config/__init__.py`

3. **Core CRUD** — implement in `scripts/little_loops/decisions.py`:
   - `load_decisions(path: Path) -> list[...]` — `yaml.safe_load`; returns empty list if file absent (graceful degradation)
   - `save_decisions(entries, path: Path)` — atomic write using `tempfile.mkstemp` + `os.replace` pattern from `scripts/little_loops/state.py:134-155`
   - `add_entry(entry, path: Path)` — load, append, save
   - `list_entries(path, type=None, category=None, label=None) -> list[...]` — filter support
   - `resolve_active(entries) -> list[...]` — exclude entries superseded by a newer entry with `supersedes` pointing to their ID
   - `set_outcome(entry_id, result, measured_at, notes, path, force=False)` — populate outcome on a `decision` entry; refuse to overwrite without `--force`

### Wiring (included per TDD mode)

- Step 12 from parent: Extend `BRConfig.to_dict()` at `core.py:493` (included in Step 2 above)
- Step 13 from parent: Re-export `DecisionsConfig` from `config/__init__.py` (included in Step 2 above)
- Step 19: Update `scripts/tests/test_config.py` — add `DecisionsConfig` to import block; add `TestDecisionsConfig` class and `TestBRConfigDecisionsIntegration` class following `TestBRConfigLearningTestsIntegration` at line 2250; add `assert "decisions" in result` to `TestBRConfig.test_to_dict()` at line 743
- Step 20: Update `scripts/tests/test_config_schema.py` — add `test_decisions_in_schema()` method following `test_learning_tests_in_schema()` at line 164

### Tests

**New test files (create):**
- `scripts/tests/test_decisions.py` — unit tests:
  - Load empty / absent log (graceful degradation)
  - Add entries per type (`rule`, `decision`, `exception`)
  - List with filters (type, category, label)
  - Exception suppression: `rule_ref` lookup
  - Supersedes resolution: superseded entries treated as inactive
  - Auto-generation stub
  - Optional fields round-trip: `scope: quarter` entries with null `issue`; outcome population; outcome overwrite refusal without `--force`; `list --no-outcome --before=...` filtering
- Use `temp_project_dir` fixture (conftest.py:56) — write `decisions.yaml` to `temp_project_dir / ".ll" / "decisions.yaml"`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Update `skills/configure/SKILL.md` — add `decisions` row to Area Mapping table, `--list` output display, Arguments enumeration, and interactive area picker (one paginated screen slot)
5. Update `skills/configure/show-output.md` — add `## decisions --show` section with `config.decisions.enabled`, `config.decisions.log_path`, `config.decisions.auto_generate`
6. Update `skills/configure/areas.md` — add `## Area: decisions` interactive flow section following the `## Area: learning-tests` pattern
7. Update `docs/reference/CONFIGURATION.md` — add `"decisions"` block to Full Configuration Example JSON; add `### decisions` section with fields table
8. Update `docs/reference/API.md` — add `decisions | DecisionsConfig` row to BRConfig Properties table; add `little_loops.decisions` to Module Overview table
9. Update `docs/ARCHITECTURE.md` — add `├── decisions.py` entry near `├── learning_tests.py` in the directory structure listing

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Atomic write utility exists**: `scripts/little_loops/file_utils.py:atomic_write()` — use this directly in `save_decisions()` instead of re-implementing the `tempfile.mkstemp + os.replace` pattern from `state.py`. Call `path.parent.mkdir(parents=True, exist_ok=True)` before invoking it (the function does not create the parent dir itself).
- **Closer config template**: `LearningTestsConfig` at `features.py:~398` is the simpler, more direct template for `DecisionsConfig` than `IssuesConfig:192`; `IssuesConfig` has complex nested `CategoryConfig` dict handling that `DecisionsConfig` does not need.
- **`to_dict()` inlining**: `BRConfig.to_dict()` inlines each feature config's scalar fields directly (see `learning_tests` block at `core.py:583`); `DecisionsConfig`'s flat fields do not need a `to_dict()` method on the config class itself — `BRConfig.to_dict()` can access them by attribute.
- **Schema `additionalProperties`**: `config-schema.json` uses `"additionalProperties": false` on every feature object and nested object — the schema tests at `test_config_schema.py:164` enforce this; omitting it will cause test failures.
- **CRUD test structure**: Model `test_decisions.py` class organization after `scripts/tests/test_learning_tests.py` — one class per operation: `TestLoadDecisions`, `TestSaveDecisions`, `TestAddEntry`, `TestListEntries`, `TestResolveActive`, `TestSetOutcome`.
- **Confirmed line references**: `_parse_config()` at `core.py:190`, `to_dict()` at `core.py:493`, import block at `core.py:23-33`, `TestBRConfigLearningTestsIntegration` at `test_config.py:2250`, `test_to_dict()` at `test_config.py:743`, `test_learning_tests_in_schema()` at `test_config_schema.py:164` — all verified as current.

## Integration Map

### Files to Modify
- `scripts/little_loops/config/features.py` — add `DecisionsConfig` dataclass after `LearningTestsConfig` (~line 398)
- `scripts/little_loops/config/core.py` — add `DecisionsConfig` to the import tuple at lines 23–33 (alphabetically: after `DesignTokensConfig`, before `EventsConfig`); wire in `_parse_config()` at ~line 190; add `@property decisions`; inline-serialize fields in `to_dict()` at ~line 493
- `scripts/little_loops/config/__init__.py` — add `DecisionsConfig` to import tuple and `__all__` list
- `config-schema.json` — add `"decisions"` object schema with `"enabled"`, `"log_path"`, `"auto_generate"` properties, each with `"type"` and `"default"`; add `"additionalProperties": false` at the object level
- `skills/configure/SKILL.md` — add `decisions` row to Area Mapping table, `--list` output block, Arguments enumeration, and interactive area selection menus [wire-issue finding]
- `skills/configure/show-output.md` — add `## decisions --show` section for `enabled`, `log_path`, `auto_generate` [wire-issue finding]
- `skills/configure/areas.md` — add `## Area: decisions` interactive flow section following `## Area: learning-tests` pattern [wire-issue finding]

### New Files
- `scripts/little_loops/decisions.py` — core data layer (entry dataclasses + CRUD functions)
- `scripts/tests/test_decisions.py` — unit tests for CRUD, filtering, supersedes resolution, exception suppression

### Test Files to Update
- `scripts/tests/test_config.py` — add `TestDecisionsConfig` and `TestBRConfigDecisionsIntegration` classes after `TestBRConfigLearningTestsIntegration` at line 2250; add `assert "decisions" in result` to `TestBRConfig.test_to_dict()` at line 743
- `scripts/tests/test_config_schema.py` — add `test_decisions_in_schema()` method after `test_learning_tests_in_schema()` at line 164

### Key Patterns
- `scripts/little_loops/config/features.py:LearningTestsConfig` (~line 398) — flat `from_dict()` template for `DecisionsConfig`
- `scripts/little_loops/file_utils.py:atomic_write` — reuse for `save_decisions()` instead of re-implementing mkstemp logic
- `scripts/tests/conftest.py:56` — `temp_project_dir` fixture (yields `Path` with `.ll/` subdir already created)
- `scripts/tests/test_learning_tests.py` — CRUD test class structure template for `test_decisions.py`

### Configuration
- `.ll/ll-config.json` — opt-in block: `{"decisions": {"enabled": true, "log_path": ".ll/decisions.yaml"}}`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — add `"decisions"` block to Full Configuration Example JSON; add `### decisions` section with fields table
- `docs/reference/API.md` — add `decisions | DecisionsConfig` row to the BRConfig Properties table; add `little_loops.decisions` row to the Module Overview table
- `docs/ARCHITECTURE.md` — add `├── decisions.py` entry near `├── learning_tests.py` in the directory structure listing

## Acceptance Criteria

- [ ] `@dataclass` entry types defined for `rule`, `decision`, `exception`, and `DecisionOutcome`
- [ ] `load_decisions()` returns empty list when `.ll/decisions.yaml` does not exist
- [ ] `save_decisions()` uses atomic write (tempfile + os.replace)
- [ ] `list_entries()` supports filtering by `type`, `category`, `label`
- [ ] `resolve_active()` excludes superseded entries
- [ ] `set_outcome()` refuses overwrite without `--force`
- [ ] `scope` and `outcome` fields supported on `decision` entries
- [ ] `DecisionsConfig` added to `config/features.py` with `enabled`, `log_path`, `auto_generate`
- [ ] `BRConfig._parse_config()` wires `DecisionsConfig`
- [ ] `BRConfig.to_dict()` includes `decisions` block
- [ ] `config-schema.json` declares `decisions` properties
- [ ] `DecisionsConfig` re-exported from `config/__init__.py`
- [ ] `test_config.py` has `TestDecisionsConfig` and `TestBRConfigDecisionsIntegration`
- [ ] `test_config_schema.py` has `test_decisions_in_schema()`
- [ ] `test_decisions.py` covers CRUD, supersedes resolution, exception suppression, optional fields

## Status

**Open** | Created: 2026-06-02 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-03T05:11:58 - `3cfe0d5c-d34a-4162-ace6-ef150d81703f.jsonl`
- `/ll:confidence-check` - 2026-06-03T00:00:00Z - `89af3cce-20a5-4fd9-a0c4-f9202acd20b6.jsonl`
- `/ll:wire-issue` - 2026-06-03T05:05:27 - `d1811f93-56bf-4d9f-b71b-40ca0763633e.jsonl`
- `/ll:refine-issue` - 2026-06-03T04:59:50 - `e34c0489-f664-4486-8102-247cf8340205.jsonl`
- `/ll:issue-size-review` - 2026-06-02T00:00:00Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
