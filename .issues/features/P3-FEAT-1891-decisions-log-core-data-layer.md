---
id: FEAT-1891
title: "Decisions Log — Core Data Layer (schema, config, CRUD)"
type: FEAT
priority: P3
parent: FEAT-948
size: Large
discovered_date: 2026-06-02
---

# FEAT-1891: Decisions Log — Core Data Layer (schema, config, CRUD)

## Summary

Implement the foundational data layer for the rules and decisions log: entry type dataclasses, YAML storage at `.ll/decisions.yaml`, `DecisionsConfig` integration into `BRConfig`, and all core CRUD operations.

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

## Session Log
- `/ll:issue-size-review` - 2026-06-02T00:00:00Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
