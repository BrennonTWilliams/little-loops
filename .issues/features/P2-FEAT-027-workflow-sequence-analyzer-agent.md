---
discovered_commit: 8279174
discovered_branch: main
discovered_date: 2026-01-12T12:00:00Z
---

# FEAT-027: Workflow Sequence Analysis Agent

## Summary

Create `workflow-sequence-analyzer` agent (Step 2 of the workflow analysis pipeline) that identifies multi-step workflows, handoff points, and cross-session patterns using advanced linking techniques including entity-based clustering, time-gap weighting, and semantic similarity scoring.

## Motivation

Pattern analysis (FEAT-026) identifies individual message categories and repeated phrases, but doesn't reveal multi-step workflows like "explore → modify → verify" or workflows that span multiple sessions. This agent:

- Links related sessions using git branch, handoff markers, and entity overlap
- Clusters messages by shared entities (files, concepts) rather than just categories
- Uses time gaps to detect workflow boundaries
- Applies semantic similarity to group related requests
- Identifies workflow templates (debug→fix→test, review→fix→commit, etc.)

This enables accurate automation proposals by understanding complete workflows, not just isolated patterns.

## Proposed Implementation

### 1. Agent Definition: `agents/workflow-sequence-analyzer.md`

```yaml
---
name: workflow-sequence-analyzer
description: |
  Second-pass analysis agent that identifies multi-step workflows and cross-session patterns.
  Uses entity clustering, time-gap weighting, and semantic similarity for accurate workflow detection.
  Used as Step 2 of the /ll:analyze-workflows pipeline.

  <example>
  Input: step1-patterns.yaml + user-messages.jsonl
  → Link related sessions
  → Cluster messages by entities
  → Detect workflow boundaries
  → Output step2-workflows.yaml
  </example>

allowed_tools:
  - Read
  - Write
  - Grep
  - Glob
model: sonnet
---
```

### 2. Cross-Session Workflow Linking

Link sessions that are part of the same logical workflow:

| Signal | Weight | Detection Method |
|--------|--------|------------------|
| Same `git_branch` | HIGH | Exact match on `git_branch` field |
| Explicit handoff | HIGH | Detect `/ll:handoff` or "continue in new session" |
| Shared entities | MEDIUM | Entity overlap > 50% between session end/start |
| Temporal proximity | LOW | Sessions within 4 hours of each other |
| Same `cwd` | LOW | Exact match on working directory |

```python
def link_related_sessions(messages: list[UserMessage]) -> list[SessionLink]:
    """Identify sessions that are part of the same workflow."""

    sessions = group_by_session(messages)
    links = []

    for i, session_a in enumerate(sessions):
        for session_b in sessions[i+1:]:
            score = calculate_link_score(session_a, session_b)
            if score > 0.5:
                links.append(SessionLink(
                    sessions=[session_a.id, session_b.id],
                    confidence=score,
                    evidence=get_link_evidence(session_a, session_b)
                ))

    return links
```

### 3. Entity-Based Clustering

Group messages by what they operate on, not just action type:

```python
def extract_entities(message: str) -> set[str]:
    """Extract file paths, commands, concepts from message."""
    entities = set()

    # File paths: checkout.py, README.md, config.json
    file_pattern = r'[\w/-]+\.(md|py|json|yaml|js|ts|sh)'
    entities.update(re.findall(file_pattern, message, re.IGNORECASE))

    # Phase/module references: phase-1, module-2
    phase_pattern = r'phase[- ]?\d+'
    module_pattern = r'module[- ]?\d+'
    entities.update(re.findall(phase_pattern, message, re.IGNORECASE))
    entities.update(re.findall(module_pattern, message, re.IGNORECASE))

    # Slash commands: /ll:commit, /help
    command_pattern = r'/[\w:-]+'
    entities.update(re.findall(command_pattern, message))

    return entities

def cluster_by_entities(messages: list[UserMessage], overlap_threshold: float = 0.3) -> list[EntityCluster]:
    """Cluster messages with significant entity overlap."""
    clusters = []

    for msg in messages:
        msg_entities = set(msg.entities or [])
        matched_cluster = None

        for cluster in clusters:
            overlap = entity_overlap(msg_entities, cluster.all_entities)
            if overlap > overlap_threshold:
                matched_cluster = cluster
                break

        if matched_cluster:
            matched_cluster.add_message(msg)
        else:
            clusters.append(EntityCluster(initial_message=msg))

    return clusters
```

### 4. Time-Gap Weighted Boundaries

Use time between messages to detect workflow boundaries:

| Gap Duration | Boundary Weight | Interpretation |
|--------------|-----------------|----------------|
| < 30 seconds | 0.0 | Same atomic action (iteration/refinement) |
| 30 sec - 2 min | 0.1 | Same workflow step |
| 2 - 5 min | 0.3 | Likely same workflow, possible step change |
| 5 - 15 min | 0.5 | Possible workflow boundary |
| 15 - 30 min | 0.7 | Probable workflow boundary |
| 30 min - 2 hours | 0.85 | Likely new workflow (unless entity overlap) |
| > 2 hours | 0.95 | New workflow (override with entity match) |

```python
def calculate_boundary_weight(gap_seconds: int) -> float:
    """Calculate workflow boundary weight based on time gap."""
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
    """Reduce boundary weight if messages share entities."""
    if overlap > 0.5:
        return max(0.0, weight - 0.3)
    elif overlap > 0.3:
        return max(0.0, weight - 0.15)
    return weight
```

### 5. Semantic Similarity Scoring

Link semantically related messages regardless of category:

**Verb Class Taxonomy:**

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

**Action Pattern Extraction:**

```python
def extract_action_pattern(message: str) -> ActionPattern:
    """Extract verb + object + target structure."""
    # Example: "Remove all references to champion-insights.md"
    return ActionPattern(
        verb="remove",
        verb_class="deletion",
        object="references",
        target="champion-insights.md",
        scope="all"
    )

def semantic_similarity(msg_a: UserMessage, msg_b: UserMessage) -> float:
    """Calculate semantic similarity between messages."""
    scores = {
        'keyword_overlap': jaccard_similarity(keywords(msg_a), keywords(msg_b)),  # 0.3 weight
        'action_pattern': action_pattern_similarity(msg_a, msg_b),                 # 0.3 weight
        'entity_overlap': entity_overlap(msg_a.entities, msg_b.entities),          # 0.3 weight
        'category_match': 1.0 if msg_a.category == msg_b.category else 0.0,        # 0.1 weight
    }
    return (scores['keyword_overlap'] * 0.3 +
            scores['action_pattern'] * 0.3 +
            scores['entity_overlap'] * 0.3 +
            scores['category_match'] * 0.1)
```

### 6. Workflow Template Matching

Identify common workflow patterns:

| Pattern | Description | Category Sequence |
|---------|-------------|-------------------|
| `explore → modify → verify` | Search/read, then change, then test/lint | file_search → code_modification → testing |
| `create → refine → finalize` | Initial creation, iteration, completion | file_write → code_modification → git_operation |
| `review → fix → commit` | Code review, apply fixes, commit changes | code_review → code_modification → git_operation |
| `plan → implement → verify` | Discussion/planning, coding, testing | planning → code_modification → testing |
| `debug → fix → test` | Investigation, fix, verification | debugging → code_modification → testing |

### 7. Output Schema: `step2-workflows.yaml`

```yaml
analysis_metadata:
  source_file: user-messages-20260112.jsonl
  patterns_file: step1-patterns.yaml
  message_count: 200
  analysis_timestamp: 2026-01-12T10:15:00Z
  agent: workflow-sequence-analyzer
  version: "1.0"

session_links:
  - link_id: "link-001"
    sessions:
      - session_id: "abc-123"
        position: 1
        link_evidence: "handoff_detected"
      - session_id: "def-456"
        position: 2
        link_evidence: "shared_branch"
    unified_workflow:
      name: "Authentication Feature Implementation"
      total_messages: 15
      span_hours: 6.5
    confidence: 0.85

entity_clusters:
  - cluster_id: "cluster-checkout"
    primary_entities:
      - "checkout.py"
      - "cart.py"
    all_entities:
      - "checkout.py"
      - "cart.py"
      - "payment.py"
    messages:
      - uuid: "msg-007"
        content: "Fix the null pointer in checkout.py"
        entities_matched: ["checkout.py"]
      - uuid: "msg-015"
        content: "Update cart.py to call checkout"
        entities_matched: ["cart.py", "checkout.py"]
    span:
      sessions: 2
      time_range: "2026-01-12T06:00:00Z to 2026-01-12T08:30:00Z"
    inferred_workflow: "Checkout System Bug Fix"
    cohesion_score: 0.78

workflow_boundaries:
  - between:
      msg_a: "msg-005"
      msg_b: "msg-006"
    time_gap_seconds: 1847
    time_gap_weight: 0.85
    entity_overlap: 0.0
    final_boundary_score: 0.85
    is_boundary: true
  - between:
      msg_a: "msg-012"
      msg_b: "msg-013"
    time_gap_seconds: 2700
    time_gap_weight: 0.85
    entity_overlap: 0.6
    final_boundary_score: 0.55
    is_boundary: false

semantic_clusters:
  - cluster_id: "sem-001"
    theme: "reference removal"
    action_class: "deletion"
    messages:
      - uuid: "msg-001"
        similarity_to_centroid: 0.92
      - uuid: "msg-007"
        similarity_to_centroid: 0.88

workflows:
  - workflow_id: "wf-001"
    name: "Checkout Bug Fix"
    pattern: "debug → fix → test"
    pattern_confidence: 0.82
    messages:
      - uuid: "msg-007"
        category: debugging
        step: 1
      - uuid: "msg-008"
        category: code_modification
        step: 2
      - uuid: "msg-009"
        category: testing
        step: 3
    session_span: ["abc-123"]
    entity_cluster: "cluster-checkout"
    semantic_cluster: "sem-001"
    duration_minutes: 25
    handoff_points: []

  - workflow_id: "wf-002"
    name: "Authentication Feature"
    pattern: "plan → implement → verify"
    pattern_confidence: 0.75
    messages: [...]
    session_span: ["abc-123", "def-456"]
    entity_cluster: "cluster-auth"
    duration_minutes: 180
    handoff_points:
      - after_message: "msg-045"
        reason: "session_end"
        continued_in: "def-456"

handoff_analysis:
  total_handoffs: 3
  handoff_patterns:
    - pattern: "session_timeout"
      count: 2
    - pattern: "explicit_handoff"
      count: 1
  recommendations:
    - "Consider using /ll:handoff for cleaner session transitions"
```

## Location

| Component | Path |
|-----------|------|
| Agent | `agents/workflow-sequence-analyzer.md` |
| Output | `.claude/workflow-analysis/step2-workflows.yaml` |

## Current Behavior

No workflow sequence analysis exists. Users cannot see multi-step workflows or cross-session patterns.

## Expected Behavior

```bash
# After running /ll:analyze-workflows, Step 2 produces:
$ cat .claude/workflow-analysis/step2-workflows.yaml

session_links:
  - link_id: "link-001"
    sessions: [...]
    confidence: 0.85
    ...

entity_clusters:
  - cluster_id: "cluster-checkout"
    primary_entities: ["checkout.py", "cart.py"]
    ...

workflows:
  - workflow_id: "wf-001"
    name: "Checkout Bug Fix"
    pattern: "debug → fix → test"
    ...
```

## Impact

- **Severity**: High - Core component of workflow analysis pipeline
- **Effort**: High - Complex linking algorithms
- **Risk**: Medium - Accuracy depends on heuristics; may need tuning

## Dependencies

None external. Uses standard text processing and datetime operations.

## Blocked By

- FEAT-011: User Message History Extraction (provides raw message data)
- FEAT-026: Workflow Pattern Analyzer Agent (provides category data)

## Blocks

- FEAT-028: Workflow Automation Proposer Agent (consumes workflow data)
- FEAT-029: `/ll:analyze-workflows` Command (orchestrates this agent)

## Labels

`feature`, `agent`, `workflow-analysis`, `cross-session`, `entity-clustering`

---

## Verification Notes

**Verified: 2026-01-17**

- Blocker FEAT-011 (User Message History Extraction) is now **completed** (in `.issues/completed/`)
- Blocker FEAT-026 (Workflow Pattern Analyzer Agent) is now **completed** (in `.issues/completed/`)
- `agents/workflow-pattern-analyzer.md` exists
- This feature is now **unblocked** and ready for implementation

---

## Status

**Open** | Created: 2026-01-12 | Priority: P2
