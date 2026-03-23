---
discovered_date: 2026-03-22T00:00:00Z
discovered_by: audit-docs
---

# ENH: Remove unimplemented `duplicate_detection` config from documentation

## Summary

`CONFIGURATION.md` documents a `duplicate_detection` config section with `exact_threshold` and `similar_threshold` fields that don't exist anywhere in the codebase, misleading users into configuring values that have no effect.

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

Either:
- **Option A**: Remove the `duplicate_detection` documentation entirely (if the feature was abandoned)
- **Option B**: Implement the feature in `IssuesConfig.from_dict` and `config-schema.json`, then use it in `issue_discovery/`

## Root Cause

- **File**: `docs/reference/CONFIGURATION.md`
- **Anchor**: `issues` config section
- **Cause**: Documentation was written for a planned feature that was never implemented. `IssuesConfig` (`config/features.py`) has no `duplicate_detection` field. `config-schema.json` has no `duplicate_detection` entry. Zero matches for `duplicate_detection`, `exact_threshold`, or `similar_threshold` in `scripts/little_loops/`.

## Integration Map

### Files to Modify
- `docs/reference/CONFIGURATION.md` — remove `duplicate_detection` from JSON example and issues table

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config/features.py` — would need new field if implementing
- `scripts/little_loops/config-schema.json` — would need new entry if implementing
- `scripts/little_loops/issue_discovery/` — where the logic would live if implementing

### Tests
- N/A for removal; new tests if implementing

### Documentation
- `docs/reference/API.md` — `IssuesConfig` would need update if implementing

### Configuration
- `config-schema.json` — needs update either way (add entry or confirm absent)

## Implementation Steps

1. Decide: remove docs (fast) or implement feature (substantial)
2. If removing: delete the two `duplicate_detection` blocks from `CONFIGURATION.md`
3. If implementing: add `DuplicateDetectionConfig` dataclass, wire into `IssuesConfig.from_dict`, add to `config-schema.json`, use in `issue_discovery/matching.py`

## Impact

- **Priority**: P2 — actively misleads users who read the config reference
- **Effort**: Tiny (removal) or Large (implementation)
- **Risk**: Low (removal) or Medium (implementation — affects issue capture workflows)
- **Breaking Change**: No

## Labels

`docs`, `configuration`, `issue-discovery`

## Status

**Open** | Created: 2026-03-22 | Priority: P2
