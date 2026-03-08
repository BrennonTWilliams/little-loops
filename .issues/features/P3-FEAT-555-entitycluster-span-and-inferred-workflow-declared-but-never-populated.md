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
- **Line(s)**: 107–119 (`EntityCluster` dataclass), 521–538 (`_cluster_by_entities` new-cluster construction) (at scan commit: a574ea0)
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

- [ ] After analysis, each `EntityCluster` with at least 2 messages has a non-null `span` with `start` and `end` ISO timestamps
- [ ] Each cluster with entity overlap ≥ 0.3 against a `WORKFLOW_TEMPLATES` entry has `inferred_workflow` set to the template name
- [ ] Clusters with no timestamp data have `span: null`
- [ ] Clusters with no matching template have `inferred_workflow: null`
- [ ] Output YAML schema is backward compatible (fields were already present, just always null)

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

**Step 2 — Compute span after cluster construction** (inline the `_link_sessions` pattern from lines 443-460):

```python
for cluster in clusters:
    # Compute span (inline pattern from _link_sessions:443-460)
    timestamps = []
    for m in cluster.messages:
        ts_str = m.get("timestamp") or ""
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is not None:
                    ts = ts.replace(tzinfo=None)
                timestamps.append(ts)
            except (ValueError, TypeError):
                pass
    if len(timestamps) >= 2:
        cluster.span = {
            "start": min(timestamps).isoformat(),
            "end": max(timestamps).isoformat(),
        }
```

**Step 3 — Infer workflow using `_get_message_category`** (correct iteration of `WORKFLOW_TEMPLATES`).

`WORKFLOW_TEMPLATES` is `dict[str, list[str]]` where values are category strings (`"file_search"`, `"code_modification"`). `cluster.all_entities` contains file paths and command strings — a different vocabulary. Direct set overlap is always 0. Use `_get_message_category` to convert message contents to categories, then match against template sequences:

```python
# Collect categories for messages in this cluster
cluster_cats = []
for m in cluster.messages:
    cat = _get_message_category(m.get("content", ""))
    if cat and cat != "unknown":
        cluster_cats.append(cat)

cluster_cat_set = set(cluster_cats)
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

1. In `_cluster_by_entities` (line 490), add `"timestamp": msg.get("timestamp")` to both the new-cluster message dict (line ~537) and the matched-cluster append (line ~517)
2. After the cluster-building loop (before the final filter at line 547), iterate all clusters and compute `span` by inlining the `_link_sessions` timestamp pattern (lines 443-460); requires `datetime` import already present at top of file
3. Compute `inferred_workflow` by collecting message categories via `_get_message_category` and matching against `WORKFLOW_TEMPLATES.items()` (iteration pattern at lines 670-683)
4. Add tests to `TestClusterByEntities` (`test_workflow_sequence_analyzer.py:832`) asserting `span` is non-null for clusters with timestamped messages and `inferred_workflow` is set when category overlap ≥ 0.3

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Timestamp key**: `msg.get("timestamp", "")` — raw messages have this key; `_cluster_by_entities` does not currently read it (lines 497-542 only access `"content"` and `"uuid"`)
- **Timestamp parsing pattern** (`workflow_sequence_analyzer.py:443-460`): `datetime.fromisoformat(ts_str.replace("Z", "+00:00"))` with `ts.replace(tzinfo=None)` for naive comparison; guards `len(timestamps) >= 2` before computing delta
- **WORKFLOW_TEMPLATES iteration** (`workflow_sequence_analyzer.py:670-683`): `for template_name, template_cats in WORKFLOW_TEMPLATES.items()` — values are category strings like `"file_search"`, not entity strings
- **Vocabulary mismatch**: `cluster.all_entities` contains file-path/command tokens (e.g., `"checkout.py"`, `"/ll:commit"`); template categories are semantic labels (`"code_modification"`, `"testing"`) — direct set overlap is always 0; use `_get_message_category` for proper matching
- **`_get_message_category`**: categorizer function that maps message content to one of the WORKFLOW_TEMPLATES category strings — call as `_get_message_category(content_str)` per message
- **Test pattern** (`test_workflow_sequence_analyzer.py:857-866`): message dicts use `{"content": "...", "uuid": "msg-N"}` — new tests for span will need `"timestamp"` key added

## Impact

- **Priority**: P3 - Currently the YAML output has two declared-but-useless fields; populating them makes entity cluster output actionable
- **Effort**: Medium - Requires accessing `WORKFLOW_TEMPLATES` from `_cluster_by_entities` and integrating timestamp helper
- **Risk**: Low - Fields already exist in output, no schema change; only value changes from null to data
- **Breaking Change**: No

## Verification Notes

Verified 2026-03-05 against commit `HEAD`.

**VALID** — Core claim confirmed: `EntityCluster.span` and `inferred_workflow` are declared at lines 107–108 but no assignment occurs anywhere in `_cluster_by_entities` (lines 490–548). Both fields always serialize as `None`.

**NEEDS_UPDATE** (line numbers): `class EntityCluster` starts at **line 100**, not line 107. The scan commit referenced lines 107–119 for the dataclass, but the class header is at 100.

**NEEDS_UPDATE** (proposed solution — `_parse_timestamps`): The helper `_parse_timestamps` referenced in the proposed solution does not exist. It is expected to be introduced by ENH-549. Implementation must either inline timestamp parsing or wait for ENH-549.

**NEEDS_UPDATE** (proposed solution — `WORKFLOW_TEMPLATES` shape): `WORKFLOW_TEMPLATES` is typed as `dict[str, list[str]]` (name → list of category strings), not a list of dicts. The proposed solution's `template.get("entities", [])` and `template.get("name")` calls are incorrect for the actual structure. The correct approach is to iterate `WORKFLOW_TEMPLATES.items()` and match `cluster.all_entities` against the category lists (after converting to entity labels or rethinking the overlap metric).

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

## Status

**Open** | Created: 2026-03-04 | Priority: P3
