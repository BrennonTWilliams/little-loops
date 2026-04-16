---
parent: ENH-1123
discovered_date: 2026-04-16
discovered_by: issue-size-review
size: Medium
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1124: NextIssueConfig Schema Definition and Dataclass

## Summary

Add the `issues.next_issue` configuration block to `config-schema.json` and implement the `NextIssueConfig` dataclass in `scripts/little_loops/config/features.py`, wired into `IssuesConfig`.

## Parent Issue

Decomposed from ENH-1123: Configurable ll-issues next-issue Selection Behavior

## Proposed Solution

1. Extend `config-schema.json` under `issues` with a `next_issue` object (model after `issues.duplicate_detection` at lines 126-146):
   - `strategy`: enum of named presets (`"confidence_first"` default, `"priority_first"`)
   - `sort_keys`: array of `{key, direction}` objects (key enum from sortable `IssueInfo` fields; direction `["asc","desc"]`)
   - Use `additionalProperties: false` on all sub-objects

2. Add `NextIssueConfig` `@dataclass` in `scripts/little_loops/config/features.py` mirroring `DuplicateDetectionConfig` (lines 43-56):
   - Wire `next_issue: NextIssueConfig` field into `IssuesConfig` (line 73) via `IssuesConfig.from_dict`
   - Add validation in `from_dict`: raise `ValueError(f"Unknown strategy: {strategy!r}")` / `ValueError(f"Unknown sort key: {key!r}")` for invalid values (pattern from `scripts/little_loops/issue_template.py:68-69`)

3. Export `NextIssueConfig` from `scripts/little_loops/config/__init__.py` (add to import block ~line 31 and `__all__` ~line 45)

4. Decide `BRConfig.to_dict()` behavior (`config/core.py:362-374`): omit `next_issue` from serialization consistent with `duplicate_detection` precedent.

## Integration Map

### Files to Modify
- `config-schema.json` — add `issues.next_issue` block
- `scripts/little_loops/config/features.py` — add `NextIssueConfig` dataclass, wire into `IssuesConfig`
- `scripts/little_loops/config/__init__.py` — export `NextIssueConfig`
- `scripts/little_loops/config/core.py:362-374` — document/confirm omission from `to_dict()`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py:101` — calls `IssuesConfig.from_dict(self._raw_config.get("issues", {}))` (already in Files to Modify; exact wiring point for the new `next_issue` argument)
- `scripts/little_loops/cli/issues/next_issue.py:12` — receives `config: BRConfig`; after this issue `config.issues.next_issue` exists as a field — ENH-1125 wires it into sort logic
- `scripts/little_loops/cli/issues/next_issues.py:12` — same coupling; ENH-1125 scope
- `scripts/tests/test_config.py:9-35` — imports from `little_loops.config`; `NextIssueConfig` must be added to this import block — ENH-1126 scope

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py:154` — `TestIssuesConfig.test_from_dict_with_defaults`: structurally valid but incomplete after this issue (missing `assert config.next_issue.strategy == "confidence_first"`) — ENH-1126 adds the assertion
- `scripts/tests/test_config.py:172-225` — `TestDuplicateDetectionConfig` is the canonical template for `TestNextIssueConfig` (ENH-1126); note it has no `pytest.raises(ValueError)` pattern — source that from `test_issue_template.py` instead
- `scripts/tests/test_config_schema.py:19` — `test_extensions_in_properties` won't break; new `test_issues_next_issue_in_schema` needed (ENH-1126)
- `scripts/tests/test_next_issue.py` — safe; `default_factory=NextIssueConfig` means no CLI test breakage
- `scripts/tests/test_next_issues.py` — same; safe with defaults

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:327-348` — `IssuesConfig` class signature will be stale (missing `next_issue` field); `NextIssueConfig` subsection needed alongside `DuplicateDetectionConfig` — ENH-1126 scope
- `docs/reference/CONFIGURATION.md:37-40` — full config example lacks `issues.next_issue` block — ENH-1126 scope
- `docs/reference/CONFIGURATION.md:247-248` — issues config table lacks `next_issue.*` rows — ENH-1126 scope

### Similar Patterns
- `scripts/little_loops/config/features.py:43-56` — `DuplicateDetectionConfig` is the canonical template
- `scripts/little_loops/config/automation.py:161-222` — `DependencyMappingConfig` for nested-dataclass composition
- `scripts/little_loops/issue_template.py:68-69` — `ValueError` pattern for unknown values

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Precise insertion points** (derived from reading features.py / __init__.py):
- `scripts/little_loops/config/features.py:70` — `IssuesConfig.duplicate_detection` field slot (`field(default_factory=DuplicateDetectionConfig)`); add `next_issue: NextIssueConfig = field(default_factory=NextIssueConfig)` directly beneath it.
- `scripts/little_loops/config/features.py:98-100` — `IssuesConfig.from_dict` hydrates `duplicate_detection=DuplicateDetectionConfig.from_dict(data.get("duplicate_detection", {}))`; add the equivalent `next_issue=NextIssueConfig.from_dict(data.get("next_issue", {}))` call there.
- `scripts/little_loops/config/__init__.py:35` — existing `DuplicateDetectionConfig` import inside the `from little_loops.config.features import (...)` block; add `NextIssueConfig` to that same import tuple.
- `scripts/little_loops/config/__init__.py:63` — existing `"DuplicateDetectionConfig"` entry in `__all__`; add `"NextIssueConfig"` adjacent (ordering is domain-grouped, not alphabetical).
- `scripts/little_loops/config/core.py:364-375` — `to_dict()`'s `"issues"` block currently omits `duplicate_detection`; omit `next_issue` for consistency (serialization is for template-variable substitution, not round-trip persistence).

**Sortable `IssueInfo` fields (enum values for `sort_keys[].key`)** — from `scripts/little_loops/issue_parser.py:202-310`:
- `priority` (via `priority_int` property; lower = higher priority)
- `outcome_confidence` (int | None, 0–100)
- `confidence_score` (int | None, 0–100)
- `effort` (int | None, 1–3)
- `impact` (int | None, 1–3)
- `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface` (int | None, each 0–25)

Note: `age` and `size` are intentionally excluded — `age` isn't an `IssueInfo` field (would require `path.stat().st_mtime`) and `size` has no canonical int form. These defer per parent ENH-1123's scope boundaries.

**Validation precedent caveat**: `NextIssueConfig.from_dict` introduces the **first validating `from_dict` in the config package** — every existing `from_dict` (e.g., `DuplicateDetectionConfig`, `ScoringWeightsConfig`) uses `data.get(..., default)` and silently accepts unknown keys / out-of-range values. The `ValueError` raise pattern is drawn from `issue_template.py:68-69` and `fsm/evaluators.py:836` (non-config modules). Implementer should expect this to be a new convention for the config subpackage.

**Strategy preset semantics** (for schema `description` text and dataclass docstring):
- `"confidence_first"` (default) — current behavior: `(-(outcome_confidence or -1), -(confidence_score or -1), priority_int)`
- `"priority_first"` — `(priority_int, -(outcome_confidence or -1), -(confidence_score or -1))`

The resolver itself is out of scope (ENH-1125), but the schema must enumerate these strategy names now so validation can reference them.

## Scope Boundaries

This issue is strictly **schema + dataclass + exports**. Explicitly out of scope (handled by siblings):

- **Sort-key resolver implementation** — `build_sort_key(config) -> Callable[[IssueInfo], tuple]` → **ENH-1125**
- **CLI wiring** — replacing hardcoded sort tuples in `next_issue.py:33-39` and `next_issues.py:31-37` → **ENH-1125**
- **Unit tests** — `TestNextIssueConfig` in `test_config.py`, schema validation test, preset regression tests → **ENH-1126**
- **Documentation** — `docs/reference/CONFIGURATION.md`, `docs/reference/API.md` field table, `docs/reference/CLI.md` updates → **ENH-1126**

Acceptance criteria below validate the dataclass contract only; full CLI behavior validation belongs to ENH-1125/1126.

## Acceptance Criteria

- `config-schema.json` validates a config with `issues.next_issue.strategy: "priority_first"`
- `NextIssueConfig.from_dict({"strategy": "priority_first"})` returns correct dataclass
- `NextIssueConfig.from_dict({})` returns defaults (strategy=`"confidence_first"`, sort_keys=None)
- `NextIssueConfig.from_dict({"strategy": "bogus"})` raises `ValueError`
- `IssuesConfig.from_dict({"next_issue": {...}})` correctly delegates to `NextIssueConfig.from_dict`

## Session Log
- `/ll:wire-issue` - 2026-04-16T19:49:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/440521b7-a91d-45cb-a303-98153044e62c.jsonl`
- `/ll:refine-issue` - 2026-04-16T19:45:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a48397f-7141-4224-9c75-454a5790de55.jsonl`
- `/ll:issue-size-review` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed68bd1a-5a6f-4d92-94fd-8ff3a80f7d09.jsonl`
- `/ll:confidence-check` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e4020196-7b0d-4e7b-81bf-9ae034a88254.jsonl`

---

**Open** | Created: 2026-04-16 | Priority: P3
