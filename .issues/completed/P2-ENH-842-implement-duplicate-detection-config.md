---
discovered_date: 2026-03-22T00:00:00Z
discovered_by: audit-docs
confidence_score: 95
outcome_confidence: 86
---

# ENH: Implement `duplicate_detection` config for `IssuesConfig`

## Summary

`CONFIGURATION.md` documents a `duplicate_detection` config section with `exact_threshold` and `similar_threshold` fields that are never read by the Python config system. The underlying thresholds exist as hardcoded constants in `issue_discovery/matching.py:87,92`. The skill files (`skills/capture-issue/SKILL.md`, `templates.md`) already reference these as `{{config.issues.duplicate_detection.*}}` template variables. The fix is to implement the config wiring — making the thresholds user-configurable as designed.

## Current Behavior

`docs/reference/CONFIGURATION.md` includes `duplicate_detection` in two places:

1. **Full JSON example** (lines 37–40):
```json
"duplicate_detection": {
  "exact_threshold": 0.8,
  "similar_threshold": 0.5
}
```

2. **`issues` section reference table** (~lines 203–205):
```
| `duplicate_detection.exact_threshold` | `0.8` | Jaccard similarity threshold ... |
| `duplicate_detection.similar_threshold` | `0.5` | Jaccard similarity threshold ... |
```

## Expected Behavior

Users can set `issues.duplicate_detection.exact_threshold` and `issues.duplicate_detection.similar_threshold` in `ll-config.json` and have the values take effect in duplicate detection. `IssuesConfig` reads the values, `config-schema.json` validates them, and `FindingMatch` properties in `matching.py` use them instead of hardcoded constants.

## Root Cause

- **File**: `scripts/little_loops/config/features.py`
- **Anchor**: `IssuesConfig.from_dict` (lines 56-81) and `IssuesConfig` dataclass (lines 43-53)
- **Cause**: The config plumbing was never implemented. `IssuesConfig` has no `duplicate_detection` field and `from_dict` never reads it. Meanwhile the thresholds exist as hardcoded literals in `issue_discovery/matching.py`: `should_skip` (line 87) uses `>= 0.8` and `should_update` (line 92) uses `0.5 <= score < 0.8` — exactly the documented default values. Additionally, `config-schema.json` (root-level) has `"additionalProperties": false` in the `issues` block (line 127), so any user-supplied `duplicate_detection` key would be rejected by schema validation. The skill files (`skills/capture-issue/SKILL.md`, `skills/capture-issue/templates.md`) already correctly reference `{{config.issues.duplicate_detection.exact_threshold}}` and `{{config.issues.duplicate_detection.similar_threshold}}` — they are wired correctly on the prompt side, waiting for the Python config to back them.

## Integration Map

### Files to Modify
- `scripts/little_loops/config/features.py` — add `DuplicateDetectionConfig` dataclass; add `duplicate_detection` field to `IssuesConfig`; update `from_dict` (line 73 block) to parse it
- `config-schema.json` (root-level, line 127) — add `duplicate_detection` object to `issues.properties` before `"additionalProperties": false`
- `scripts/little_loops/issue_discovery/matching.py` — replace hardcoded `0.8` (line 87) and `0.5` (lines 92, 97, 102) in `FindingMatch` properties with configurable fields
- `scripts/little_loops/issue_discovery/search.py` — thread `IssuesConfig` into `find_existing_issue` and pass thresholds to the 4 `FindingMatch(...)` instantiation sites (lines 180, 206, 251, 283)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config/__init__.py` — export `DuplicateDetectionConfig` alongside existing exports
- `scripts/little_loops/config/core.py` — imports `IssuesConfig`; no change needed (field is added transparently)

### No Changes Needed (Already Correct)
- `docs/reference/CONFIGURATION.md` — already documents `duplicate_detection` correctly at lines 37-40 (JSON example) and 204-205 (reference table)
- `skills/capture-issue/SKILL.md` — already references `{{config.issues.duplicate_detection.exact_threshold}}` (6 times)
- `skills/capture-issue/templates.md` — already references these config vars (3 times)

### Tests
- `scripts/tests/test_config.py` — `TestIssuesConfig` (line 108); add `TestDuplicateDetectionConfig` cases for default values and `from_dict` parsing
- New test: verify that custom thresholds propagate to `FindingMatch` decision properties

### Documentation
- `docs/reference/API.md` — add `DuplicateDetectionConfig` to `IssuesConfig` entry

## Implementation Steps

1. **Add `DuplicateDetectionConfig` dataclass** to `config/features.py` — follow the `CategoryConfig` pattern (lines 25-40): `exact_threshold: float = 0.8`, `similar_threshold: float = 0.5`, with a `from_dict` classmethod
2. **Add field to `IssuesConfig`** — add `duplicate_detection: DuplicateDetectionConfig = field(default_factory=DuplicateDetectionConfig)` and update `from_dict` line 73 block to call `DuplicateDetectionConfig.from_dict(data.get("duplicate_detection", {}))`
3. **Export from `config/__init__.py`** — add `DuplicateDetectionConfig` to the public exports
4. **Update `config-schema.json`** (root-level) — insert `duplicate_detection` object into `issues.properties` (before line 127) with `exact_threshold` (number, 0.0-1.0, default 0.8) and `similar_threshold` (number, 0.0-1.0, default 0.5) properties
5. **Update `matching.py` `FindingMatch`** — add `exact_threshold: float = 0.8` and `similar_threshold: float = 0.5` fields to the dataclass; update `should_skip` (line 87) to use `self.exact_threshold`, `should_update` (line 92) and `should_create` (line 97) to use `self.exact_threshold`/`self.similar_threshold`, `should_reopen` (line 102) to use `self.similar_threshold`
6. **Thread config through `search.py` `find_existing_issue`** — accept optional `issues_config: IssuesConfig | None = None`; extract thresholds from config if provided; pass to the 4 `FindingMatch(...)` calls at lines 180, 206, 251, 283
7. **Add tests** — in `test_config.py` alongside `TestIssuesConfig`: default values, custom values via `from_dict`, schema validation; confirm `FindingMatch` uses configured thresholds
8. **Verify** — `python -m pytest scripts/tests/test_config.py -v -k "duplicate" && python -m pytest scripts/tests/ -v`

## Impact

- **Priority**: P2 — config docs describe fields users can't actually use; skill templates reference config values that are never read
- **Effort**: Small — ~40 lines of Python across 4 files; schema update; tests
- **Risk**: Low — backward-compatible: `DuplicateDetectionConfig` defaults (0.8, 0.5) preserve current hardcoded behavior exactly
- **Breaking Change**: No

## Labels

`docs`, `configuration`, `issue-discovery`

## Status

**Completed** | Created: 2026-03-22 | Resolved: 2026-03-23 | Priority: P2

## Resolution

Implemented `duplicate_detection` config wiring across 6 files:

- Added `DuplicateDetectionConfig` dataclass to `config/features.py` with `exact_threshold=0.8` and `similar_threshold=0.5`; added field to `IssuesConfig`; updated `from_dict` to parse it
- Exported `DuplicateDetectionConfig` from `config/__init__.py`
- Added `duplicate_detection` object to `issues.properties` in `config-schema.json` (with range validation 0.0–1.0)
- Added `exact_threshold` and `similar_threshold` fields to `FindingMatch` dataclass in `matching.py`; updated all 6 property methods to use them instead of hardcoded literals
- Threaded thresholds through `find_existing_issue` in `search.py`; all 4 `FindingMatch` instantiation sites now pass configured values; Pass 3 condition uses `similar_threshold`
- Added `DuplicateDetectionConfig` to `docs/reference/API.md`

5 new tests added covering defaults, `from_dict`, `IssuesConfig` integration, and `FindingMatch` threshold propagation. All 3852 tests pass.

## Session Log
- `/ll:ready-issue` - 2026-03-23T16:34:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2b0600f3-5e7c-4cd8-aed4-54083da0e121.jsonl`
- `/ll:refine-issue` - 2026-03-23T16:03:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d106e83-f07c-4417-a00b-467c82f88f42.jsonl`
- `/ll:confidence-check` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/834df235-fade-4c5c-9680-95839070d795.jsonl`
- `/ll:ready-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/memory/MEMORY.md`
- `/ll:manage-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
