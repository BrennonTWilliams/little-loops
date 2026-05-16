---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
confidence_score: 94
outcome_confidence: 95
---

# FEAT-555: `EntityCluster.span` and `inferred_workflow` declared but never populated

## Summary

The `EntityCluster` dataclass declares two output fields — `span` (intended to hold start/end timestamps for the cluster's message range) and `inferred_workflow` (intended to name the matching workflow pattern) — that always serialize as `null` in the YAML output. The data needed to populate both fields is available from the cluster's `messages` list and `WORKFLOW_TEMPLATES`, but no code path assigns them.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 101–120 (`EntityCluster` dataclass), 529–560 (`_cluster_by_entities` new-cluster construction) (at scan commit: a574ea0)
- **Anchor**: `class EntityCluster`, `in function _cluster_by_entities`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/little_loops/workflow_sequence_analyzer.py#L107-L119)
- **Code**:
```python
@dataclass
class EntityCluster:
    cluster_id: str
    primary_entities: list[str]
    all_entities: set[str] = field(default_factory=set)
    messages: list[dict[str, Any]] = field(default_factory=list)
    span: dict[str, Any] | None = None          # always None in output
    inferred_workflow: str | None = None         # always None in output
    cohesion_score: float = 0.0
```

## Current Behavior

All `EntityCluster` objects in the output YAML have `span: null` and `inferred_workflow: null`. Users cannot tell from the output when a cluster's messages occurred or whether the cluster matches a known workflow pattern.

## Expected Behavior

- `span` is populated with `{"start": "<iso-timestamp>", "end": "<iso-timestamp>"}` derived from the min/max timestamps of `cluster.messages`.
- `inferred_workflow` is populated with the name of the closest matching `WORKFLOW_TEMPLATES` entry (by entity overlap), or `null` if no template matches above a threshold.

## Motivation

Populating `span` and `inferred_workflow` makes entity cluster output actionable. Currently both fields always serialize as `null`, so developers cannot tell from the output when a cluster was active or what kind of work it represents. Completing these fields eliminates two dead output fields and lets `ll-workflows analyze` surface meaningful temporal and categorical context for each cluster — directly improving the utility of workflow analysis results.

## Use Case

A developer runs `ll-workflows analyze` after a busy week. In the output, they see entity clusters with `span` showing which days the cluster was active and `inferred_workflow: "bug_fix_workflow"` — telling them at a glance what kind of work each cluster represents. Currently both fields are always `null`, making the cluster output much less useful.

## Acceptance Criteria

- [x] After analysis, each `EntityCluster` with at least 2 messages has a non-null `span` with `start` and `end` ISO timestamps
- [x] Each cluster with entity overlap ≥ 0.3 against a `WORKFLOW_TEMPLATES` entry has `inferred_workflow` set to the template name
- [x] Clusters with no timestamp data have `span: null`
- [x] Clusters with no matching template have `inferred_workflow: null`
- [x] Output YAML schema is backward compatible (fields were already present, just always null)

## Proposed Solution

After building each cluster in `_cluster_by_entities`, populate the fields.

**Note**: The original proposed code had two bugs discovered during codebase research (see Verification Notes and Codebase Research Findings). The corrected approach is below.

### Corrected Implementation

**Step 1 — Store timestamps during cluster construction.**
The message dicts stored in `cluster.messages` currently omit timestamps (lines 517-523, 536-542 only store `uuid`, `content`, `entities_matched`). Add `"timestamp"` to each stored dict:

```python
# In matched_cluster branch (line ~517):
matched_cluster.messages.append({
    "uuid": msg.get("uuid", ""),
    "content": content[:80] + "..." if len(content) > 80 else content,
    "entities_matched": entities_matched,
    "timestamp": msg.get("timestamp"),   # ADD THIS
})

# In new cluster branch (line ~537):
messages=[{
    "uuid": msg.get("uuid", ""),
    "content": content[:80] + "..." if len(content) > 80 else content,
    "entities_matched": sorted(msg_entities),
    "timestamp": msg.get("timestamp"),   # ADD THIS
}],
```

**Step 2 — Compute span after cluster construction** using `_parse_timestamps` (line 396, added by ENH-549):

```python
for cluster in clusters:
    timestamps = _parse_timestamps(cluster.messages)
    if len(timestamps) >= 2:
        cluster.span = {
            "start": min(timestamps).isoformat(),
            "end": max(timestamps).isoformat(),
        }
```

**Step 3 — Infer workflow against `WORKFLOW_TEMPLATES`** (line 677 iteration pattern).

`WORKFLOW_TEMPLATES` is `dict[str, list[str]]` where values are category strings (`"file_search"`, `"code_modification"`). `_get_message_category(msg_uuid, patterns)` (line 618) requires a patterns dict from Step 1 output — not available in `_cluster_by_entities`. Use a direct keyword-based category mapping instead, or pass `patterns` as a parameter:

```python
# Simple approach: derive category from content keywords
_CONTENT_CATEGORY_MAP = {
    "file_search": ["search", "find", "glob", "grep"],
    "code_modification": ["edit", "write", "fix", "refactor"],
    "testing": ["test", "pytest", "assert"],
    "git": ["commit", "push", "branch", "pr"],
}

def _category_from_content(content: str) -> str | None:
    lower = content.lower()
    for category, keywords in _CONTENT_CATEGORY_MAP.items():
        if any(kw in lower for kw in keywords):
            return category
    return None

# In the cluster post-processing loop:
cluster_cat_set = set()
for m in cluster.messages:
    cat = _category_from_content(m.get("content", ""))
    if cat:
        cluster_cat_set.add(cat)

best_name, best_score = None, 0.0
for template_name, template_cats in WORKFLOW_TEMPLATES.items():
    template_set = set(template_cats)
    if template_set:
        overlap = len(cluster_cat_set & template_set) / len(template_set)
        if overlap > best_score:
            best_score, best_name = overlap, template_name
if best_score >= 0.3:
    cluster.inferred_workflow = best_name
```

**Note**: `_get_message_category(msg_uuid, patterns)` (line 618) looks up UUID in a patterns dict — it cannot be used here without threading `patterns` through `_cluster_by_entities`. The content-keyword approach above is simpler and self-contained. If `patterns` is available at the call site, passing it as a parameter is cleaner.

## API/Interface

`EntityCluster.span` changes from always-`None` to `dict[str, str] | None`:
```python
span: {"start": "2026-03-01T09:00:00+00:00", "end": "2026-03-01T17:00:00+00:00"} | None
inferred_workflow: "bug_fix_workflow" | None
```

No schema breaking change — the fields already existed in the YAML output.

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — `_cluster_by_entities`, populate fields after cluster construction

### Dependent Files (Callers/Importers)
- `scripts/tests/test_workflow_sequence_analyzer.py` — `TestClusterByEntities` class, add span/workflow assertions

### Similar Patterns
- `_link_sessions` computes `span_hours` from timestamps — reuse the same approach

### Tests
- Add assertions in `TestClusterByEntities` for non-null `span` and `inferred_workflow` when data is available

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `_cluster_by_entities` (line 505), add `"timestamp": msg.get("timestamp")` to both the new-cluster message dict (line ~551) and the matched-cluster append (line ~532)
2. After the cluster-building loop (before the final filter at line 562), iterate all clusters and compute `span` using `_parse_timestamps(cluster.messages)` (line 396, already imported); guard with `len(timestamps) >= 2`
3. Compute `inferred_workflow` using content-keyword category matching against `WORKFLOW_TEMPLATES.items()` (iteration pattern at line 677); see Step 3 in Proposed Solution for the self-contained approach
4. Add tests to `TestClusterByEntities` (`test_workflow_sequence_analyzer.py:1215`) asserting `span` is non-null for clusters with timestamped messages and `inferred_workflow` is set when category overlap ≥ 0.3

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Timestamp key**: `msg.get("timestamp", "")` — raw messages have this key; `_cluster_by_entities` does not currently read it (lines 497-542 only access `"content"` and `"uuid"`)
- **Timestamp parsing pattern**: `_parse_timestamps(messages)` at line 396 (added by ENH-549) — wraps `datetime.fromisoformat` with `tzinfo` stripping and error guards. Use directly.
- **WORKFLOW_TEMPLATES iteration** (`workflow_sequence_analyzer.py:670-683`): `for template_name, template_cats in WORKFLOW_TEMPLATES.items()` — values are category strings like `"file_search"`, not entity strings
- **Vocabulary mismatch**: `cluster.all_entities` contains file-path/command tokens (e.g., `"checkout.py"`, `"/ll:commit"`); template categories are semantic labels (`"code_modification"`, `"testing"`) — direct set overlap is always 0; use `_get_message_category` for proper matching
- **`_get_message_category`**: `(msg_uuid: str, patterns: dict[str, Any]) -> str | None` at line 618 — looks up UUID in a patterns dict from Step 1 output; NOT callable with just content. Use the content-keyword approach in Step 3 instead.
- **Test pattern** (`test_workflow_sequence_analyzer.py:1215`, `TestClusterByEntities`): message dicts use `{"content": "...", "uuid": "msg-N"}` — new tests for span will need `"timestamp"` key added

## Impact

- **Priority**: P3 - Currently the YAML output has two declared-but-useless fields; populating them makes entity cluster output actionable
- **Effort**: Medium - Requires accessing `WORKFLOW_TEMPLATES` from `_cluster_by_entities` and integrating timestamp helper
- **Risk**: Low - Fields already exist in output, no schema change; only value changes from null to data
- **Breaking Change**: No

## Verification Notes

Verified 2026-03-05 against commit `HEAD`.

**VALID** — Core claim confirmed: `EntityCluster.span` and `inferred_workflow` are declared at lines 107–108 but no assignment occurs anywhere in `_cluster_by_entities` (lines 490–548). Both fields always serialize as `None`.

**NEEDS_UPDATE** (line numbers): `class EntityCluster` starts at **line 100**, not line 107. The scan commit referenced lines 107–119 for the dataclass, but the class header is at 100.

**OK** (updated by `/ll:ready-issue` 2026-03-16): `_parse_timestamps` exists at line 396 — ENH-549 was completed and introduced this helper. Step 2 of the Proposed Solution updated to use it directly.

**OK** (updated by `/ll:ready-issue` 2026-03-16): `WORKFLOW_TEMPLATES` is `dict[str, list[str]]`. Step 3 of the Proposed Solution updated: `_get_message_category(msg_uuid, patterns)` (line 618) cannot be used directly without a patterns dict — updated to use a content-keyword approach that is self-contained within `_cluster_by_entities`.

**OK** — `WORKFLOW_TEMPLATES` exists at line 66. `_cluster_by_entities` at line 490. `_link_sessions` span pattern at lines 455–460.

**OK** — Dependency backlinks: FEAT-557 and FEAT-559 both reference FEAT-555 in their `## Blocked By` sections. No broken refs or missing backlinks.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `workflow-analyzer`, `captured`

## Blocks

- FEAT-559 — both modify `scripts/little_loops/workflow_sequence_analyzer.py`

_(FEAT-557 and ENH-552 removed from Blocks — both completed)_

## Session Log
- `/ll:ready-issue` - 2026-03-17T01:05:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7084c6d0-5594-450c-ac22-eff538eb9c12.jsonl`
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: fields declared but always None
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: `EntityCluster.span` and `inferred_workflow` still always None; removed stale Blocks: FEAT-557, ENH-552 (both completed)

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5880f51-7be9-45bd-acc9-e01380324f20.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5880f51-7be9-45bd-acc9-e01380324f20.jsonl`
- `/ll:map-dependencies` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5880f51-7be9-45bd-acc9-e01380324f20.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5880f51-7be9-45bd-acc9-e01380324f20.jsonl`
- `/ll:refine-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5880f51-7be9-45bd-acc9-e01380324f20.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5880f51-7be9-45bd-acc9-e01380324f20.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`

## Resolution

**Completed** 2026-03-16 by `/ll:manage-issue`.

- Added `"timestamp": msg.get("timestamp")` to both message dict builds in `_cluster_by_entities`
- Added `_CONTENT_CATEGORY_MAP` module-level constant mapping content keywords to WORKFLOW_TEMPLATES category labels
- Added post-processing loop after cluster construction to compute `span` via `_parse_timestamps` and infer workflow via keyword-category overlap against `WORKFLOW_TEMPLATES`
- Added 4 tests to `TestClusterByEntities`: span populated from timestamps, span null without timestamps, inferred_workflow set on match, inferred_workflow null on no match
- All 3586 tests pass, lint clean

## Status

**Completed** | Created: 2026-03-04 | Priority: P3
