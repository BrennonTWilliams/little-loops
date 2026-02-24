---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# BUG-474: `_update_issue_frontmatter` corrupts YAML frontmatter on round-trip

## Summary

The `_update_issue_frontmatter` function in `sync.py` hand-parses and re-serializes YAML frontmatter using simple `key: value` line splitting. This loses YAML quoting, boolean normalization, and multi-line block scalars. Values containing colons (e.g., URLs) can be corrupted on subsequent re-parses.

## Location

- **File**: `scripts/little_loops/sync.py`
- **Line(s)**: 186-204 (at scan commit: 95d4139)
- **Anchor**: `in function _update_issue_frontmatter`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/95d4139206f3659159b727db57578ffb2930085b/scripts/little_loops/sync.py#L186-L204)
- **Code**:
```python
for line in frontmatter_text.split("\n"):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if ":" in line:
        key, value = line.split(":", 1)   # line 193
        existing[key.strip()] = value.strip()

# Re-serialization (lines 201-204):
for key, value in existing.items():
    frontmatter_lines.append(f"{key}: {value}")
```

## Current Behavior

The function parses frontmatter as `key: value` lines and re-serializes as `f"{key}: {value}"`. While `split(":", 1)` correctly handles values with colons, the round-trip doesn't preserve YAML quoting or block scalars. More critically, any pre-existing frontmatter that uses YAML quoting (e.g., `title: "value: with colon"`) will have quotes stripped on re-serialization.

## Expected Behavior

Frontmatter updates preserve all YAML formatting through proper YAML parsing and serialization, or at minimum handle known-problematic value types (URLs, quoted strings) correctly.

## Steps to Reproduce

1. Push a local issue to GitHub (`ll-sync push`)
2. The `github_url` field (containing `https://...`) is written to frontmatter
3. Run any subsequent sync operation that re-parses that file's frontmatter
4. Observe that YAML-quoted values may lose their quoting on the round-trip

## Root Cause

- **File**: `scripts/little_loops/sync.py`
- **Anchor**: `in function _update_issue_frontmatter`
- **Cause**: Custom line-based parser does not handle YAML quoting, boolean normalization, or multi-line block scalars that `yaml.safe_load`/`yaml.dump` would handle correctly.

## Proposed Solution

Replace the manual parse/emit with `yaml.safe_load(frontmatter_text)` and `yaml.dump(merged_dict, default_flow_style=False)`. The `yaml` package is already used in `sprint.py` and available in the environment:

```python
import yaml

def _update_issue_frontmatter(content: str, updates: dict[str, Any]) -> str:
    fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        # No frontmatter, create new
        fm_text = yaml.dump(updates, default_flow_style=False).strip()
        return f"---\n{fm_text}\n---\n{content}"

    existing = yaml.safe_load(fm_match.group(1)) or {}
    existing.update(updates)
    fm_text = yaml.dump(existing, default_flow_style=False).strip()
    return f"---\n{fm_text}\n---{content[fm_match.end():]}"
```

## Implementation Steps

1. Replace manual frontmatter parser in `_update_issue_frontmatter` with `yaml.safe_load`/`yaml.dump`
2. Add round-trip test with URLs, quoted values, and boolean frontmatter
3. Verify existing sync operations work correctly

## Integration Map

### Files to Modify
- `scripts/little_loops/sync.py` — replace manual frontmatter parser in `_update_issue_frontmatter`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/sync.py` — `_update_local_frontmatter` calls `_update_issue_frontmatter`

### Similar Patterns
- `scripts/little_loops/frontmatter.py` — `parse_frontmatter` already uses proper parsing

### Tests
- `scripts/tests/test_sync.py` — add round-trip test with URLs and quoted values

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 — Data corruption risk during sync operations
- **Effort**: Small — Replace ~15 lines with yaml.safe_load/dump
- **Risk**: Low — More correct than current implementation
- **Breaking Change**: No

## Labels

`bug`, `sync`, `yaml`, `data-integrity`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`
- `/ll:format-issue` - 2026-02-24 - auto-format batch

---

## Status

**Open** | Created: 2026-02-24 | Priority: P2
