---
id: BUG-1258
type: BUG
priority: P3
status: done
discovered_date: 2026-04-22
discovered_by: manual
completed_at: 2026-04-22T00:00:00Z
---

# BUG-1258: `parse_frontmatter` silently drops inline YAML arrays, producing spurious "unknown issue" warnings in `ll-issues clusters`

## Summary

`frontmatter.py`'s custom YAML-subset parser handled block-style lists (`- item`) but not inline array syntax (`[a, b, c]`). Issues with `blocked_by: [ID1, ID2]` frontmatter had the entire bracket string stored as a single scalar value. This caused every such blocker reference to be classified as an "unknown issue" in `DependencyGraph`, flooding `ll-issues clusters` output with false warnings before the cluster diagram.

## Location

- **File**: `scripts/little_loops/frontmatter.py`
- **Anchor**: `in function parse_frontmatter, scalar value branch`
- **Root cause line**: line 76 — `result[key] = value` — hit for any value that starts with `[`, treating it as a plain string

## Current Behavior

```
Issue FEAT-1156 blocked by unknown issue [FEAT-1112, FEAT-1116]
Issue FEAT-1157 blocked by unknown issue [FEAT-1112, FEAT-1156]
Issue FEAT-1158 blocked by unknown issue [FEAT-1112, FEAT-1156]
...
─── Cluster 1 (4 issues) ───
```

All 16 "unknown issue" lines were false positives — every referenced issue existed and was active.

## Root Cause

`parse_frontmatter` is a hand-rolled YAML-subset parser. It processes frontmatter line-by-line:
- Block sequences (`key:` with following `- item` lines) → stored as a Python list ✓
- Inline arrays (`key: [a, b, c]`) → fell through to the scalar branch → stored as the string `"[a, b, c]"` ✗

In `issue_parser.py`, the frontmatter-to-`blocked_by` merge code correctly handles strings:
```python
ids = [fm_val] if isinstance(fm_val, str) else list(fm_val)
```
But `"[FEAT-1112, FEAT-1116]"` IS a str, so it became `['[FEAT-1112, FEAT-1116]']` — a one-element list containing the bracket notation. `DependencyGraph` then looked up that string as an issue ID, found nothing, and warned.

Additionally, `clusters.py` was not passing `all_known_ids` to `DependencyGraph.from_issues`, so even completed issues referenced as blockers would have triggered the same warning (rather than being silently skipped as in other subcommands).

## Expected Behavior

`parse_frontmatter` should parse inline YAML arrays into Python lists, consistent with how block-style lists are handled. `ll-issues clusters` should emit no warnings for valid issue references.

## Resolution

**`scripts/little_loops/frontmatter.py`** — Added an inline-array branch before the scalar fallback:

```python
if value.startswith("[") and value.endswith("]"):
    inner = value[1:-1].strip()
    result[key] = [item.strip() for item in inner.split(",")] if inner else []
    continue
```

**`scripts/little_loops/cli/issues/clusters.py`** — Now gathers `all_known_ids` via `gather_all_issue_ids` and passes it to `DependencyGraph.from_issues`, suppressing spurious warnings for completed/deferred blockers (consistent with `sprint` and `deps` subcommands).

After the fix, `ll-issues clusters` produces zero warnings and Cluster 1 correctly expanded from 8 to 21 issues (all the previously-silently-broken edges now resolved).

## Impact

- **Priority**: P3 — Noisy output only; no incorrect behavior beyond the warnings and missing cluster edges
- **Effort**: Tiny — 5 lines added, 1 line changed
- **Risk**: None — purely additive branch in parser, no existing behavior changed

## Session Log

- Manual investigation — 2026-04-22

---

**Resolved** | Created: 2026-04-22 | Resolved: 2026-04-22 | Priority: P3
