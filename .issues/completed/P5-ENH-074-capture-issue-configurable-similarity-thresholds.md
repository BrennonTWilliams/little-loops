---
discovered_date: 2025-01-15
discovered_by: manual_review
---

# ENH-074: Make capture_issue duplicate detection thresholds configurable

## Summary

The `/ll:capture-issue` command uses hardcoded Jaccard similarity thresholds (0.8 for exact duplicate, 0.5 for similar) for duplicate detection. These should be configurable to tune sensitivity per project.

## Current Behavior

Lines 156-158 define fixed thresholds:
```markdown
- Score >= 0.8 = exact duplicate
- Score 0.5-0.8 = similar issue
- Score < 0.5 = likely new issue
```

These values work for many cases but may need adjustment:
- Projects with many similar issues may need higher thresholds
- Projects wanting aggressive deduplication may need lower thresholds

## Expected Behavior

Add configuration options to `config-schema.json`:

```json
"issues": {
  "duplicate_detection": {
    "type": "object",
    "properties": {
      "exact_threshold": {
        "type": "number",
        "description": "Jaccard similarity threshold for exact duplicates",
        "default": 0.8,
        "minimum": 0.5,
        "maximum": 1.0
      },
      "similar_threshold": {
        "type": "number",
        "description": "Jaccard similarity threshold for similar issues",
        "default": 0.5,
        "minimum": 0.1,
        "maximum": 0.9
      }
    }
  }
}
```

Update `capture_issue.md` to reference:
- `{{config.issues.duplicate_detection.exact_threshold}}`
- `{{config.issues.duplicate_detection.similar_threshold}}`

## Files to Modify

- `config-schema.json` - Add `duplicate_detection` under `issues`
- `commands/capture_issue.md` - Use config values instead of hardcoded thresholds

## Impact

- **Priority**: P5
- **Effort**: Low
- **Risk**: Low

## Labels

`enhancement`, `commands`, `configuration`

---

## Verification Notes

**Verified: 2026-01-28**

- Thresholds are now at lines 156-158 (previously 137-140, file has been restructured)
- Values remain hardcoded at 0.8 for exact duplicate, 0.5 for similar issue
- Issue description otherwise remains accurate

---

## Status

**Open** | Created: 2025-01-15 | Verified: 2026-01-28 | Priority: P5

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-01
- **Status**: Completed

### Changes Made
- `config-schema.json`: Added `duplicate_detection` object under `issues` with `exact_threshold` (default: 0.8) and `similar_threshold` (default: 0.5) properties
- `commands/capture_issue.md`: Updated all threshold references to use `{{config.issues.duplicate_detection.exact_threshold}}` and `{{config.issues.duplicate_detection.similar_threshold}}`

### Verification Results
- Schema JSON: Validated with json.tool
