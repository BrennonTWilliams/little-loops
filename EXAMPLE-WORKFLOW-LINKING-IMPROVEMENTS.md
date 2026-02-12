# Workflow Linking Improvements Proposal

**Document Type:** Technical Proposal
**Status:** Draft
**Created:** 2026-01-12
**Author:** Claude Code Analysis
**Related Command:** `/analyze-workflows`

---

## Executive Summary

The `/analyze-workflows` command identifies automation opportunities by analyzing user message patterns and multi-step workflows. This proposal outlines five improvements to the workflow linking mechanism that would significantly increase accuracy in detecting related work across sessions and messages.

**Current State:** Workflow linking operates within session boundaries using category-based sequence matching.

**Proposed State:** Cross-session workflow detection using entity clustering, semantic similarity, temporal weighting, and response context.

**Expected Impact:** More accurate workflow detection, better automation proposals, reduced false groupings of unrelated tasks.

---

## Table of Contents

- [1. Problem Statement](#1-problem-statement)
- [2. Current Architecture](#2-current-architecture)
- [3. Proposed Improvements](#3-proposed-improvements)
  - [A. Cross-Session Workflow Linking](#a-cross-session-workflow-linking)
  - [B. Entity-Based Clustering](#b-entity-based-clustering)
  - [C. Time-Gap Weighted Boundaries](#c-time-gap-weighted-boundaries)
  - [D. Semantic Similarity Scoring](#d-semantic-similarity-scoring)
  - [E. Response Context Capture](#e-response-context-capture)
- [4. Implementation Priority](#4-implementation-priority)
- [5. Schema Changes](#5-schema-changes)
- [6. Agent Modifications](#6-agent-modifications)
- [7. Success Metrics](#7-success-metrics)

---

## 1. Problem Statement

### Current Limitations

The workflow linking process in `workflow-sequence-analyzer` (Step 2) has five key limitations:

| Limitation | Impact |
|------------|--------|
| Session boundaries treated as workflow boundaries | Misses workflows that span multiple sessions |
| Category-based matching is coarse | Groups unrelated tasks that share a category |
| Available context signals ignored | `cwd` and `git_branch` not used for continuity |
| No semantic similarity analysis | Similar messages categorized differently break patterns |
| User messages only, no response context | Cannot track what files were actually modified |

### Evidence from Analysis Output

From the 2026-01-12 workflow analysis:

1. **Session Handoff Pattern** (5 occurrences) proves users continue work across sessions, but cross-session workflows aren't traced.

2. **Reference Cleanup Workflow** (15 occurrences) conflates multiple distinct cleanup efforts (champion-insights, SOW, timestamps) into one workflow type.

3. **50 commit operations** are treated as part of various workflows but lack file-based clustering to identify which edits they actually concluded.

---

## 2. Current Architecture

### Data Flow

```
user-messages.jsonl
        │
        ▼
┌─────────────────────────┐
│ Step 1: Pattern Analyzer │ ──► step1-patterns.yaml
│ (Individual patterns)    │
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│ Step 2: Sequence Analyzer│ ──► step2-workflows.yaml
│ (Workflow linking)       │
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│ Step 3: Proposer         │ ──► step3-proposals.yaml
│ (Automation proposals)   │
└─────────────────────────┘
```

### Current JSONL Schema

```json
{
  "content": "the user's message text",
  "timestamp": "ISO 8601 timestamp",
  "session_id": "UUID of the session",
  "uuid": "unique message ID",
  "cwd": "working directory",
  "git_branch": "git branch at time of message",
  "is_sidechain": false
}
```

### Current Linking Logic (Step 2)

1. Group messages by `session_id`
2. Sort by `timestamp` within each session
3. Classify each message by category
4. Match 2-5 message sequences against predefined patterns
5. Identify handoff points within sessions

**Key Gap:** No mechanism to link related messages across sessions.

---

## 3. Proposed Improvements

### A. Cross-Session Workflow Linking

**Priority:** HIGH
**Effort:** MEDIUM
**Impact:** Enables detection of workflows spanning multiple sessions

#### Problem

Users frequently continue work across sessions using `/ll:handoff` or by returning to the same task later. Current analysis treats each session as isolated, fragmenting single workflows into multiple incomplete sequences.

#### Solution

Add a pre-processing phase that identifies session relationships before sequence analysis.

#### Session Linking Signals

| Signal | Weight | Detection Method |
|--------|--------|------------------|
| Same `git_branch` | HIGH | Exact match on `git_branch` field |
| Explicit handoff | HIGH | Detect `/ll:handoff` or "continue in new session" patterns |
| Shared entities | MEDIUM | Entity overlap > 50% between session ends/starts |
| Temporal proximity | LOW | Sessions within 4 hours of each other |
| Same `cwd` | LOW | Exact match on working directory |

#### Output Schema Addition

```yaml
session_links:
  - link_id: "link-001"
    sessions:
      - session_id: "abc-123"
        position: 1
        link_evidence: "handoff_detected"
      - session_id: "def-456"
        position: 2
        link_evidence: "shared_branch"
      - session_id: "ghi-789"
        position: 3
        link_evidence: "shared_entities"
    unified_workflow:
      name: "Phase 1 Module 1 Reference Cleanup"
      total_messages: 15
      span_hours: 6.5
    confidence: 0.85
```

#### Implementation Notes

1. Create new pre-processing function: `link_related_sessions()`
2. Run before existing sequence analysis
3. Pass linked session groups to sequence analyzer as single units
4. Preserve original session boundaries for reporting

---

### B. Entity-Based Clustering

**Priority:** HIGH
**Effort:** MEDIUM
**Impact:** Groups messages by what they operate on, not just action type

#### Problem

Category-based matching groups all "code_modification" messages together regardless of what files or concepts they modify. This conflates unrelated tasks.

#### Solution

Extract entities (file names, concepts, identifiers) from messages and cluster by entity overlap.

#### Entity Types to Extract

| Entity Type | Pattern Examples | Extraction Method |
|-------------|------------------|-------------------|
| File paths | `champion-insights.md`, `README.md` | Regex: `[\w/-]+\.(md\|py\|json\|yaml)` |
| Directory refs | `phase-1-module-1`, `training-modules/` | Regex: `phase-\d+`, known directories |
| Concepts | "SOW references", "champion quotes" | Keyword matching + NLP |
| Commands | `/ll:commit`, `marp --pdf` | Regex: `^/[\w:-]+`, tool names |
| Identifiers | "Issue 4.2", "Slide 11" | Regex: `(Issue\|Slide\|Step)\s+[\d.]+` |

#### Clustering Algorithm

```
For each message:
  1. Extract entities → entity_set
  2. Compare entity_set to existing clusters
  3. If overlap > 0.3 with existing cluster:
     - Add message to cluster
     - Update cluster entity_set (union)
  4. Else:
     - Create new cluster

For each cluster:
  1. Calculate cohesion score (entity overlap density)
  2. Identify primary entities (appear in >50% of messages)
  3. Generate cluster label from primary entities
```

#### Output Schema Addition

```yaml
entity_clusters:
  - cluster_id: "cluster-champion-insights"
    primary_entities:
      - "champion-insights.md"
      - "phase-1-module-1"
    all_entities:
      - "champion-insights.md"
      - "hands-on-exercises.md"
      - "workshop-prep.md"
      - "phase-1-module-1"
    messages:
      - uuid: "msg-001"
        content: "What documents reference champion-insights.md?"
        entities_matched: ["champion-insights.md"]
      - uuid: "msg-007"
        content: "Remove all references to champion-insights.md"
        entities_matched: ["champion-insights.md"]
      - uuid: "msg-012"
        content: "Did we get hands-on-exercises.md?"
        entities_matched: ["hands-on-exercises.md", "champion-insights.md"]
    span:
      sessions: 3
      time_range: "2026-01-12T06:00:00Z to 2026-01-12T08:30:00Z"
    inferred_workflow: "Reference Cleanup: champion-insights.md"
    cohesion_score: 0.78

  - cluster_id: "cluster-sow-cleanup"
    primary_entities:
      - "SOW"
      - "phase-1-module-1"
    messages:
      - uuid: "msg-003"
        content: "Remove SOW references from Phase 1 Module 1"
        entities_matched: ["SOW", "phase-1-module-1"]
    # ... more messages
    inferred_workflow: "Reference Cleanup: SOW references"
    cohesion_score: 0.82
```

#### Benefits

- Distinguishes multiple cleanup workflows (champion-insights vs SOW vs timestamps)
- Links messages across sessions by shared entities
- Provides more specific automation proposals ("cleanup champion-insights" vs generic "cleanup references")

---

### C. Time-Gap Weighted Boundaries

**Priority:** MEDIUM
**Effort:** SMALL
**Impact:** More accurate workflow boundary detection within sessions

#### Problem

Current analysis treats all sequential messages as potentially linked regardless of time gap. A 10-second gap and a 45-minute gap are weighted equally.

#### Solution

Apply time-gap weighting to workflow boundary detection.

#### Time Gap Interpretation

| Gap Duration | Interpretation | Boundary Weight |
|--------------|----------------|-----------------|
| < 30 seconds | Same atomic action (iteration/refinement) | 0.0 (no boundary) |
| 30 sec - 2 min | Same workflow step | 0.1 |
| 2 - 5 min | Likely same workflow, possible step change | 0.3 |
| 5 - 15 min | Possible workflow boundary | 0.5 |
| 15 - 30 min | Probable workflow boundary | 0.7 |
| 30 min - 2 hours | Likely new workflow (unless entity overlap) | 0.85 |
| > 2 hours | New workflow (override with entity match) | 0.95 |

#### Algorithm

```
For consecutive messages (msg_a, msg_b):
  1. Calculate time_gap = msg_b.timestamp - msg_a.timestamp
  2. Look up boundary_weight from table
  3. If entity_overlap(msg_a, msg_b) > 0.5:
     - Reduce boundary_weight by 0.3 (min 0.0)
  4. If boundary_weight > 0.6:
     - Mark as workflow boundary candidate
  5. Final boundary decision considers:
     - Time gap weight
     - Entity continuity
     - Category sequence patterns
```

#### Output Schema Addition

```yaml
workflow_boundaries:
  - between:
      msg_a: "msg-005"
      msg_b: "msg-006"
    time_gap_seconds: 1847  # ~31 minutes
    time_gap_weight: 0.85
    entity_overlap: 0.0
    final_boundary_score: 0.85
    is_boundary: true

  - between:
      msg_a: "msg-012"
      msg_b: "msg-013"
    time_gap_seconds: 2700  # 45 minutes
    time_gap_weight: 0.85
    entity_overlap: 0.6  # both reference same file
    final_boundary_score: 0.55  # reduced due to entity overlap
    is_boundary: false  # same workflow despite time gap
```

---

### D. Semantic Similarity Scoring

**Priority:** MEDIUM
**Effort:** MEDIUM
**Impact:** Links semantically related messages regardless of category

#### Problem

Messages with similar intent get different categories, breaking sequence patterns:

- "What documents reference champion-insights.md?" → `file_search`
- "Remove all references to champion-insights.md" → `code_modification`
- "Did we miss any champion-insights references?" → `file_search`

These are clearly one workflow but category sequence is `search → modify → search` which may not match templates.

#### Solution

Add semantic similarity scoring using keyword overlap and action pattern matching.

#### Similarity Dimensions

| Dimension | Weight | Calculation |
|-----------|--------|-------------|
| Keyword overlap | 0.3 | Jaccard similarity of significant words |
| Action pattern | 0.3 | Match "verb + object" structures |
| Entity overlap | 0.3 | Shared file/concept references |
| Category match | 0.1 | Same category bonus |

#### Action Pattern Extraction

```
Message: "Remove all references to champion-insights.md"
Action Pattern: {
  verb: "remove",
  verb_class: "deletion",
  object: "references",
  target: "champion-insights.md",
  scope: "all"
}

Message: "Delete the SOW mentions from README"
Action Pattern: {
  verb: "delete",
  verb_class: "deletion",  # Same class as "remove"
  object: "mentions",      # Similar to "references"
  target: "README",
  scope: "the"
}

Similarity: 0.7 (same verb_class, similar object type)
```

#### Verb Class Taxonomy

```yaml
verb_classes:
  deletion:
    verbs: [remove, delete, drop, eliminate, clear, clean up]
  modification:
    verbs: [update, change, modify, edit, fix, adjust, revise]
  creation:
    verbs: [create, add, generate, write, make, build]
  search:
    verbs: [find, search, locate, where, what, which, list]
  verification:
    verbs: [check, verify, validate, confirm, review, ensure]
  execution:
    verbs: [run, execute, launch, start, invoke, call]
```

#### Output Schema Addition

```yaml
semantic_clusters:
  - cluster_id: "sem-001"
    theme: "reference removal"
    action_class: "deletion"
    messages:
      - uuid: "msg-001"
        similarity_to_centroid: 0.92
      - uuid: "msg-007"
        similarity_to_centroid: 0.88
      - uuid: "msg-012"
        similarity_to_centroid: 0.75

similarity_matrix:
  - msg_a: "msg-001"
    msg_b: "msg-007"
    scores:
      keyword_overlap: 0.45
      action_pattern: 0.85
      entity_overlap: 0.90
      category_match: 0.0
    total_similarity: 0.68
```

---

### E. Response Context Capture

**Priority:** HIGH
**Effort:** LARGE (Infrastructure Change)
**Impact:** Enables file-based workflow tracking and success detection

#### Problem

We only capture user messages. The assistant's responses contain critical workflow information:
- What files were actually modified
- What tools were used
- Whether the request succeeded
- What the next suggested action was

Without this, we cannot:
- Cluster messages by files they affected
- Detect workflow completion vs abandonment
- Understand the actual impact of each request

#### Solution

Enhance the message extraction script to capture response metadata.

#### Enhanced JSONL Schema

```json
{
  "content": "Remove all references to champion-insights.md",
  "timestamp": "2026-01-12T07:13:56.678Z",
  "session_id": "abc-123",
  "uuid": "msg-007",
  "cwd": "<external-repo>",
  "git_branch": "master",
  "is_sidechain": false,

  "response_metadata": {
    "tools_used": [
      {"tool": "Grep", "count": 1},
      {"tool": "Edit", "count": 4}
    ],
    "files_read": [
      "training-modules/phase-1-code-review-and-codebase-configuration/module-1-custom-instructions/README.md"
    ],
    "files_modified": [
      "training-modules/phase-1-code-review-and-codebase-configuration/module-1-custom-instructions/hands-on-exercises.md",
      "training-modules/phase-1-code-review-and-codebase-configuration/module-1-custom-instructions/workshop-prep.md",
      "training-modules/phase-1-code-review-and-codebase-configuration/module-1-custom-instructions/README.md",
      "training-modules/phase-1-code-review-and-codebase-configuration/module-1-custom-instructions/custom-instructions-code-review.md"
    ],
    "completion_status": "success",
    "error_message": null,
    "follow_up_suggested": "commit changes"
  }
}
```

#### Implementation Requirements

1. **Modify extraction script** (`scripts/extract_user_messages.py`):
   - Parse full conversation turns, not just user messages
   - Extract tool usage from assistant responses
   - Track file operations (Read, Edit, Write targets)
   - Detect success/failure indicators

2. **Source data access**:
   - Requires access to Claude Code conversation logs
   - May need API integration or log parsing

3. **Privacy considerations**:
   - File paths may contain sensitive information
   - Consider path normalization (relative paths only)
   - Allow opt-out of response capture

#### Benefits of Response Context

| Analysis Capability | Enabled By |
|---------------------|------------|
| File-based workflow clustering | `files_modified` field |
| Workflow completion detection | `completion_status` field |
| Tool usage patterns | `tools_used` field |
| Error recovery workflows | `error_message` + subsequent messages |
| Implicit workflow linking | Same files modified across sessions |

#### File-Based Clustering Example

```yaml
file_workflows:
  - file: "hands-on-exercises.md"
    modifications:
      - msg_uuid: "msg-007"
        action: "Remove champion-insights references"
        timestamp: "2026-01-12T07:13:56Z"
      - msg_uuid: "msg-015"
        action: "Update exercise instructions"
        timestamp: "2026-01-12T08:45:12Z"
      - msg_uuid: "msg-023"
        action: "Fix markdown formatting"
        timestamp: "2026-01-12T09:30:00Z"
    total_modifications: 3
    workflow_inference: "hands-on-exercises.md cleanup and polish"
```

---

## 4. Implementation Priority

| Improvement | Priority | Effort | Dependencies | Recommended Order |
|-------------|----------|--------|--------------|-------------------|
| A. Cross-Session Linking | HIGH | MEDIUM | None | 1 |
| B. Entity-Based Clustering | HIGH | MEDIUM | None | 2 |
| C. Time-Gap Weighting | MEDIUM | SMALL | None | 3 |
| D. Semantic Similarity | MEDIUM | MEDIUM | B (entity extraction) | 4 |
| E. Response Context | HIGH | LARGE | Script changes | 5 (parallel track) |

### Recommended Implementation Phases

**Phase 1: Foundation (Improvements A, B, C)**
- Implement cross-session linking
- Add entity extraction and clustering
- Add time-gap weighting
- No infrastructure changes required
- Estimated completion: 1-2 sessions

**Phase 2: Enhanced Analysis (Improvement D)**
- Add semantic similarity scoring
- Build verb class taxonomy
- Integrate with entity clustering
- Estimated completion: 1 session

**Phase 3: Infrastructure (Improvement E)**
- Modify extraction script
- Capture response metadata
- Add file-based workflow tracking
- Estimated completion: 2-3 sessions

---

## 5. Schema Changes

### step2-workflows.yaml Additions

```yaml
# NEW: Cross-session links
session_links:
  - link_id: string
    sessions: [session_link_entry]
    unified_workflow: workflow_summary
    confidence: float

# NEW: Entity clusters
entity_clusters:
  - cluster_id: string
    primary_entities: [string]
    all_entities: [string]
    messages: [message_entry]
    span: time_span
    inferred_workflow: string
    cohesion_score: float

# NEW: Workflow boundaries
workflow_boundaries:
  - between: {msg_a: string, msg_b: string}
    time_gap_seconds: int
    time_gap_weight: float
    entity_overlap: float
    final_boundary_score: float
    is_boundary: boolean

# NEW: Semantic clusters
semantic_clusters:
  - cluster_id: string
    theme: string
    action_class: string
    messages: [similarity_entry]

# ENHANCED: Existing workflows section
workflows:
  - name: string
    # ... existing fields ...
    # NEW FIELDS:
    session_span: [session_id]  # Sessions this workflow spans
    entity_cluster: string       # Link to entity cluster
    semantic_cluster: string     # Link to semantic cluster
    boundary_confidence: float   # Confidence in workflow boundaries
```

### user-messages.jsonl Additions (Phase 3)

```json
{
  // ... existing fields ...
  "response_metadata": {
    "tools_used": [{"tool": string, "count": int}],
    "files_read": [string],
    "files_modified": [string],
    "completion_status": "success" | "failure" | "partial",
    "error_message": string | null,
    "follow_up_suggested": string | null
  }
}
```

---

## 6. Agent Modifications

### workflow-sequence-analyzer.md Changes

Add new analysis steps to the agent prompt:

```markdown
### NEW Step 1.5: Link Related Sessions

Before grouping messages by session:

1. Identify session relationships using:
   - Shared git_branch
   - Handoff markers (/ll:handoff, "continue in new session")
   - Entity overlap between session end and next session start
   - Temporal proximity (< 4 hours)

2. Create session_links entries for related sessions

3. For linked sessions, analyze as unified workflow span

### NEW Step 2.5: Extract Entities

For each message:

1. Extract file paths (regex: [\w/-]+\.(md|py|json|yaml))
2. Extract directory references (phase-X, module-X patterns)
3. Extract concept keywords (SOW, champion, references, etc.)
4. Extract command references (/command, tool names)

### NEW Step 3.5: Cluster by Entities

1. Group messages with >30% entity overlap
2. Calculate cluster cohesion scores
3. Generate cluster labels from primary entities
4. Link entity clusters to workflow sequences

### MODIFIED Step 4: Identify Sequence Patterns

Add time-gap weighting:

1. Calculate time gap between consecutive messages
2. Apply boundary weight based on gap duration
3. Reduce boundary weight if entity overlap > 50%
4. Mark boundaries where final score > 0.6
```

### workflow-pattern-analyzer.md Changes

Enhance entity extraction in Step 1:

```markdown
### ENHANCED Step 4: Extract Common Phrases

In addition to phrases, extract:

1. **File entities**: All file paths mentioned
2. **Concept entities**: Recurring domain terms
3. **Action patterns**: Verb + object structures

Output entity inventory for Step 2 consumption.
```

---

## 7. Success Metrics

### Quantitative Metrics

| Metric | Current Baseline | Target | Measurement |
|--------|------------------|--------|-------------|
| Cross-session workflow detection | 0% | >80% | % of handoff-linked sessions identified |
| Entity cluster accuracy | N/A | >75% | Manual review of cluster coherence |
| False workflow groupings | Unknown | <15% | Unrelated messages grouped together |
| Workflow boundary accuracy | ~60% (est.) | >85% | Manual review of boundary placement |

### Qualitative Metrics

- Automation proposals are more specific (file-targeted vs generic)
- Workflow names reflect actual work (entity-based naming)
- Cross-session work is visible in analysis output
- Time estimates improve with better workflow scoping

### Validation Approach

1. Re-run analysis on existing 200-message dataset
2. Compare old vs new workflow detection
3. Manual review of:
   - Are session links accurate?
   - Are entity clusters coherent?
   - Are workflow boundaries correctly placed?
4. Generate new automation proposals
5. Assess specificity improvement

---

## Appendix: Reference Implementation Snippets

### Entity Extraction (Python)

```python
import re
from typing import List, Set

def extract_entities(message: str) -> Set[str]:
    entities = set()

    # File paths
    file_pattern = r'[\w/-]+\.(md|py|json|yaml|js|ts|sh)'
    entities.update(re.findall(file_pattern, message, re.IGNORECASE))

    # Phase/module references
    phase_pattern = r'phase[- ]?\d+'
    module_pattern = r'module[- ]?\d+'
    entities.update(re.findall(phase_pattern, message, re.IGNORECASE))
    entities.update(re.findall(module_pattern, message, re.IGNORECASE))

    # Slash commands
    command_pattern = r'/[\w:-]+'
    entities.update(re.findall(command_pattern, message))

    return entities

def entity_overlap(entities_a: Set[str], entities_b: Set[str]) -> float:
    if not entities_a or not entities_b:
        return 0.0
    intersection = entities_a & entities_b
    union = entities_a | entities_b
    return len(intersection) / len(union)
```

### Time Gap Weighting (Python)

```python
from datetime import datetime, timedelta

def calculate_boundary_weight(gap_seconds: int) -> float:
    if gap_seconds < 30:
        return 0.0
    elif gap_seconds < 120:
        return 0.1
    elif gap_seconds < 300:
        return 0.3
    elif gap_seconds < 900:
        return 0.5
    elif gap_seconds < 1800:
        return 0.7
    elif gap_seconds < 7200:
        return 0.85
    else:
        return 0.95

def adjust_for_entity_overlap(weight: float, overlap: float) -> float:
    if overlap > 0.5:
        return max(0.0, weight - 0.3)
    elif overlap > 0.3:
        return max(0.0, weight - 0.15)
    return weight
```

---

*Document Version: 1.0*
*Last Updated: 2026-01-12*
