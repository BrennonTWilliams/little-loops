# FEAT-027: Workflow Sequence Analysis Module - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-027-workflow-sequence-analyzer-python.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

The workflow analysis pipeline has Steps 1 and 3 defined (agent and skill), but Step 2 (the Python module for algorithmic analysis) is missing.

### Key Discoveries
- `scripts/little_loops/user_messages.py:35-68` - `UserMessage` dataclass defines input message structure
- `scripts/little_loops/cli.py:307-430` - `main_messages()` pattern to follow for CLI structure
- `agents/workflow-pattern-analyzer.md:138-190` - Step 1 output schema (input for Step 2)
- `scripts/pyproject.toml:47-52` - CLI entry point registration pattern

### Existing Infrastructure
- FEAT-011 complete: `ll-messages` CLI extracts messages to JSONL
- FEAT-026 complete: `workflow-pattern-analyzer` agent outputs `step1-patterns.yaml`
- Dependencies installed: `pyyaml>=6.0`

## Desired End State

A Python module `workflow_sequence_analyzer.py` that:
1. Reads JSONL messages and YAML patterns from Step 1
2. Identifies multi-step workflows using entity clustering, time-gap boundaries, and semantic similarity
3. Links related sessions across handoffs
4. Outputs `step2-workflows.yaml` with workflow analysis

### How to Verify
- `ll-workflows analyze --help` displays usage
- Module can be imported: `from little_loops.workflow_sequence_analyzer import analyze_workflows`
- Tests pass: `python -m pytest scripts/tests/test_workflow_sequence_analyzer.py`
- Type checking passes: `python -m mypy scripts/little_loops/workflow_sequence_analyzer.py`

## What We're NOT Doing

- Not implementing Step 3 (automation proposals) - that's FEAT-028
- Not creating the orchestration command - that's FEAT-029
- Not adding LLM dependencies - this is algorithmic processing only
- Not building a full semantic similarity system with embeddings - using heuristics

## Problem Analysis

Users cannot identify multi-step workflows or cross-session patterns from their Claude Code history. Step 1 (FEAT-026) categorizes individual messages but doesn't reveal:
- Workflow sequences like `debug → fix → test`
- Workflows spanning multiple sessions
- Entity-based clusters (messages about same files)
- Time-based workflow boundaries

## Solution Approach

Build a pure Python module using:
1. **Entity extraction** via regex (file paths, commands, phases)
2. **Time-gap weighting** via datetime arithmetic
3. **Session linking** via shared git_branch, entity overlap, handoff markers
4. **Workflow template matching** via category sequence detection

## Implementation Phases

### Phase 1: Core Data Structures

#### Overview
Create dataclasses for the workflow analysis output schema.

#### Changes Required

**File**: `scripts/little_loops/workflow_sequence_analyzer.py`
**Changes**: Create new module with dataclasses

```python
"""
Workflow Sequence Analyzer - Step 2 of the workflow analysis pipeline.

Identifies multi-step workflows and cross-session patterns using:
- Entity-based clustering
- Time-gap weighted boundaries
- Semantic similarity scoring
- Workflow template matching
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "analyze_workflows",
    "SessionLink",
    "EntityCluster",
    "WorkflowBoundary",
    "Workflow",
    "WorkflowAnalysis",
]

# Module-level compiled regex patterns
FILE_PATTERN = re.compile(r"[\w./-]+\.(?:md|py|json|yaml|yml|js|ts|tsx|jsx|sh|toml)", re.IGNORECASE)
PHASE_PATTERN = re.compile(r"phase[- ]?\d+", re.IGNORECASE)
MODULE_PATTERN = re.compile(r"module[- ]?\d+", re.IGNORECASE)
COMMAND_PATTERN = re.compile(r"/[\w:-]+")
ISSUE_PATTERN = re.compile(r"(?:BUG|FEAT|ENH)-\d+", re.IGNORECASE)

# Verb class taxonomy for semantic similarity
VERB_CLASSES = {
    "deletion": {"remove", "delete", "drop", "eliminate", "clear", "clean"},
    "modification": {"update", "change", "modify", "edit", "fix", "adjust", "revise"},
    "creation": {"create", "add", "generate", "write", "make", "build"},
    "search": {"find", "search", "locate", "where", "what", "which", "list"},
    "verification": {"check", "verify", "validate", "confirm", "review", "ensure"},
    "execution": {"run", "execute", "launch", "start", "invoke", "call"},
}

# Workflow templates: category sequences that indicate common patterns
WORKFLOW_TEMPLATES = {
    "explore → modify → verify": ["file_search", "code_modification", "testing"],
    "create → refine → finalize": ["file_write", "code_modification", "git_operation"],
    "review → fix → commit": ["code_review", "code_modification", "git_operation"],
    "plan → implement → verify": ["planning", "code_modification", "testing"],
    "debug → fix → test": ["debugging", "code_modification", "testing"],
}


@dataclass
class SessionLink:
    """Link between related sessions."""

    link_id: str
    sessions: list[dict[str, Any]]  # session_id, position, link_evidence
    unified_workflow: dict[str, Any]  # name, total_messages, span_hours
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "sessions": self.sessions,
            "unified_workflow": self.unified_workflow,
            "confidence": self.confidence,
        }


@dataclass
class EntityCluster:
    """Cluster of messages sharing entities."""

    cluster_id: str
    primary_entities: list[str]
    all_entities: set[str] = field(default_factory=set)
    messages: list[dict[str, Any]] = field(default_factory=list)
    span: dict[str, Any] | None = None
    inferred_workflow: str | None = None
    cohesion_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "primary_entities": self.primary_entities,
            "all_entities": sorted(self.all_entities),
            "messages": self.messages,
            "span": self.span,
            "inferred_workflow": self.inferred_workflow,
            "cohesion_score": round(self.cohesion_score, 2),
        }


@dataclass
class WorkflowBoundary:
    """Boundary between workflows based on time gaps and entity overlap."""

    msg_a: str
    msg_b: str
    time_gap_seconds: int
    time_gap_weight: float
    entity_overlap: float
    final_boundary_score: float
    is_boundary: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "between": {"msg_a": self.msg_a, "msg_b": self.msg_b},
            "time_gap_seconds": self.time_gap_seconds,
            "time_gap_weight": round(self.time_gap_weight, 2),
            "entity_overlap": round(self.entity_overlap, 2),
            "final_boundary_score": round(self.final_boundary_score, 2),
            "is_boundary": self.is_boundary,
        }


@dataclass
class Workflow:
    """Identified multi-step workflow."""

    workflow_id: str
    name: str
    pattern: str
    pattern_confidence: float
    messages: list[dict[str, Any]]
    session_span: list[str]
    entity_cluster: str | None = None
    semantic_cluster: str | None = None
    duration_minutes: int = 0
    handoff_points: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "pattern": self.pattern,
            "pattern_confidence": round(self.pattern_confidence, 2),
            "messages": self.messages,
            "session_span": self.session_span,
            "entity_cluster": self.entity_cluster,
            "semantic_cluster": self.semantic_cluster,
            "duration_minutes": self.duration_minutes,
            "handoff_points": self.handoff_points,
        }


@dataclass
class WorkflowAnalysis:
    """Complete workflow analysis output."""

    metadata: dict[str, Any]
    session_links: list[SessionLink] = field(default_factory=list)
    entity_clusters: list[EntityCluster] = field(default_factory=list)
    workflow_boundaries: list[WorkflowBoundary] = field(default_factory=list)
    workflows: list[Workflow] = field(default_factory=list)
    handoff_analysis: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_metadata": self.metadata,
            "session_links": [s.to_dict() for s in self.session_links],
            "entity_clusters": [c.to_dict() for c in self.entity_clusters],
            "workflow_boundaries": [b.to_dict() for b in self.workflow_boundaries],
            "workflows": [w.to_dict() for w in self.workflows],
            "handoff_analysis": self.handoff_analysis,
        }
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/workflow_sequence_analyzer.py`
- [ ] Lint passes: `ruff check scripts/little_loops/workflow_sequence_analyzer.py`
- [ ] Module imports: `python -c "from little_loops.workflow_sequence_analyzer import *"`

---

### Phase 2: Core Analysis Functions

#### Overview
Implement entity extraction, time-gap boundaries, and session linking.

#### Changes Required

**File**: `scripts/little_loops/workflow_sequence_analyzer.py`
**Changes**: Add analysis functions

```python
def extract_entities(content: str) -> set[str]:
    """Extract file paths, commands, and concepts from message content."""
    entities: set[str] = set()

    # File paths
    entities.update(FILE_PATTERN.findall(content))

    # Phase/module references
    entities.update(PHASE_PATTERN.findall(content.lower()))
    entities.update(MODULE_PATTERN.findall(content.lower()))

    # Slash commands
    entities.update(COMMAND_PATTERN.findall(content))

    # Issue IDs
    entities.update(match.upper() for match in ISSUE_PATTERN.findall(content))

    return entities


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


def entity_overlap(entities_a: set[str], entities_b: set[str]) -> float:
    """Calculate Jaccard similarity between two entity sets."""
    if not entities_a or not entities_b:
        return 0.0
    intersection = len(entities_a & entities_b)
    union = len(entities_a | entities_b)
    return intersection / union if union > 0 else 0.0


def get_verb_class(content: str) -> str | None:
    """Extract verb class from message content."""
    content_lower = content.lower()
    words = set(re.findall(r"\b\w+\b", content_lower))

    for verb_class, verbs in VERB_CLASSES.items():
        if words & verbs:
            return verb_class
    return None


def semantic_similarity(content_a: str, content_b: str,
                       entities_a: set[str], entities_b: set[str],
                       category_a: str | None, category_b: str | None) -> float:
    """Calculate semantic similarity between two messages."""
    # Keyword overlap (simple word-level Jaccard)
    words_a = set(re.findall(r"\b[a-z]{3,}\b", content_a.lower()))
    words_b = set(re.findall(r"\b[a-z]{3,}\b", content_b.lower()))
    keyword_sim = len(words_a & words_b) / len(words_a | words_b) if words_a | words_b else 0.0

    # Verb class similarity
    verb_a = get_verb_class(content_a)
    verb_b = get_verb_class(content_b)
    verb_sim = 1.0 if verb_a and verb_a == verb_b else 0.0

    # Entity overlap
    entity_sim = entity_overlap(entities_a, entities_b)

    # Category match
    category_sim = 1.0 if category_a and category_a == category_b else 0.0

    # Weighted combination
    return (keyword_sim * 0.3 + verb_sim * 0.3 + entity_sim * 0.3 + category_sim * 0.1)
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/workflow_sequence_analyzer.py`
- [ ] Lint passes: `ruff check scripts/little_loops/workflow_sequence_analyzer.py`

---

### Phase 3: Main Analysis Pipeline

#### Overview
Implement the main `analyze_workflows()` function that orchestrates the analysis.

#### Changes Required

**File**: `scripts/little_loops/workflow_sequence_analyzer.py`
**Changes**: Add main analysis function

```python
def _load_messages(messages_file: Path) -> list[dict[str, Any]]:
    """Load messages from JSONL file."""
    messages = []
    with open(messages_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append(json.loads(line))
    return messages


def _load_patterns(patterns_file: Path) -> dict[str, Any]:
    """Load patterns from Step 1 YAML output."""
    with open(patterns_file, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _group_by_session(messages: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group messages by session_id."""
    sessions: dict[str, list[dict[str, Any]]] = {}
    for msg in messages:
        session_id = msg.get("session_id", "unknown")
        if session_id not in sessions:
            sessions[session_id] = []
        sessions[session_id].append(msg)
    return sessions


def _detect_handoff(content: str) -> bool:
    """Check if message indicates a session handoff."""
    handoff_markers = [
        "/ll:handoff",
        "continue in new session",
        "pick up in next session",
        "resuming from",
        "continuation of",
    ]
    content_lower = content.lower()
    return any(marker in content_lower for marker in handoff_markers)


def _link_sessions(sessions: dict[str, list[dict[str, Any]]]) -> list[SessionLink]:
    """Identify sessions that are part of the same workflow."""
    links: list[SessionLink] = []
    session_ids = list(sessions.keys())
    link_counter = 0

    for i, session_a_id in enumerate(session_ids):
        session_a = sessions[session_a_id]
        if not session_a:
            continue

        # Extract session metadata
        last_msg_a = session_a[-1] if session_a else {}
        entities_a = set()
        for msg in session_a:
            entities_a.update(extract_entities(msg.get("content", "")))
        branch_a = last_msg_a.get("git_branch")

        for session_b_id in session_ids[i + 1:]:
            session_b = sessions[session_b_id]
            if not session_b:
                continue

            first_msg_b = session_b[0] if session_b else {}
            entities_b = set()
            for msg in session_b:
                entities_b.update(extract_entities(msg.get("content", "")))
            branch_b = first_msg_b.get("git_branch")

            # Calculate link score
            score = 0.0
            evidence = []

            # Same git branch (HIGH weight)
            if branch_a and branch_a == branch_b:
                score += 0.4
                evidence.append("shared_branch")

            # Explicit handoff marker (HIGH weight)
            if any(_detect_handoff(msg.get("content", "")) for msg in session_a):
                score += 0.4
                evidence.append("handoff_detected")

            # Shared entities (MEDIUM weight)
            overlap = entity_overlap(entities_a, entities_b)
            if overlap > 0.5:
                score += 0.2
                evidence.append("entity_overlap")
            elif overlap > 0.3:
                score += 0.1
                evidence.append("partial_entity_overlap")

            if score > 0.3:
                link_counter += 1

                # Calculate span
                timestamps = []
                for msg in session_a + session_b:
                    ts_str = msg.get("timestamp", "")
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            timestamps.append(ts)
                        except ValueError:
                            pass

                span_hours = 0.0
                if len(timestamps) >= 2:
                    span_hours = (max(timestamps) - min(timestamps)).total_seconds() / 3600

                links.append(SessionLink(
                    link_id=f"link-{link_counter:03d}",
                    sessions=[
                        {"session_id": session_a_id, "position": 1, "link_evidence": evidence[0] if evidence else "score"},
                        {"session_id": session_b_id, "position": 2, "link_evidence": evidence[-1] if evidence else "score"},
                    ],
                    unified_workflow={
                        "name": f"Linked workflow {link_counter}",
                        "total_messages": len(session_a) + len(session_b),
                        "span_hours": round(span_hours, 1),
                    },
                    confidence=min(score, 1.0),
                ))

    return links


def _cluster_by_entities(messages: list[dict[str, Any]],
                        overlap_threshold: float = 0.3) -> list[EntityCluster]:
    """Cluster messages with significant entity overlap."""
    clusters: list[EntityCluster] = []
    cluster_counter = 0

    for msg in messages:
        content = msg.get("content", "")
        msg_entities = extract_entities(content)

        if not msg_entities:
            continue

        # Find matching cluster
        matched_cluster = None
        best_overlap = overlap_threshold

        for cluster in clusters:
            overlap = entity_overlap(msg_entities, cluster.all_entities)
            if overlap > best_overlap:
                best_overlap = overlap
                matched_cluster = cluster

        if matched_cluster:
            matched_cluster.all_entities.update(msg_entities)
            matched_cluster.messages.append({
                "uuid": msg.get("uuid", ""),
                "content": content[:80] + "..." if len(content) > 80 else content,
                "entities_matched": sorted(msg_entities & matched_cluster.all_entities),
            })
            # Update cohesion score (average overlap of messages)
            matched_cluster.cohesion_score = (
                matched_cluster.cohesion_score * (len(matched_cluster.messages) - 1) + best_overlap
            ) / len(matched_cluster.messages)
        else:
            cluster_counter += 1
            # Create new cluster
            primary = sorted(msg_entities)[:3]  # Top 3 entities
            cluster = EntityCluster(
                cluster_id=f"cluster-{cluster_counter:03d}",
                primary_entities=primary,
                all_entities=msg_entities.copy(),
                messages=[{
                    "uuid": msg.get("uuid", ""),
                    "content": content[:80] + "..." if len(content) > 80 else content,
                    "entities_matched": sorted(msg_entities),
                }],
                cohesion_score=1.0,
            )
            clusters.append(cluster)

    # Filter out single-message clusters
    return [c for c in clusters if len(c.messages) >= 2]


def _compute_boundaries(messages: list[dict[str, Any]],
                       boundary_threshold: float = 0.6) -> list[WorkflowBoundary]:
    """Compute workflow boundaries between consecutive messages."""
    boundaries: list[WorkflowBoundary] = []

    # Sort by timestamp
    sorted_msgs = sorted(messages, key=lambda m: m.get("timestamp", ""))

    for i in range(len(sorted_msgs) - 1):
        msg_a = sorted_msgs[i]
        msg_b = sorted_msgs[i + 1]

        # Parse timestamps
        ts_a_str = msg_a.get("timestamp", "")
        ts_b_str = msg_b.get("timestamp", "")

        try:
            ts_a = datetime.fromisoformat(ts_a_str.replace("Z", "+00:00"))
            ts_b = datetime.fromisoformat(ts_b_str.replace("Z", "+00:00"))
            gap_seconds = int((ts_b - ts_a).total_seconds())
        except (ValueError, AttributeError):
            gap_seconds = 0

        # Calculate time gap weight
        time_weight = calculate_boundary_weight(gap_seconds)

        # Calculate entity overlap
        entities_a = extract_entities(msg_a.get("content", ""))
        entities_b = extract_entities(msg_b.get("content", ""))
        overlap = entity_overlap(entities_a, entities_b)

        # Adjust for entity overlap (reduce boundary weight if same topic)
        final_score = time_weight
        if overlap > 0.5:
            final_score = max(0.0, time_weight - 0.3)
        elif overlap > 0.3:
            final_score = max(0.0, time_weight - 0.15)

        is_boundary = final_score >= boundary_threshold

        boundaries.append(WorkflowBoundary(
            msg_a=msg_a.get("uuid", ""),
            msg_b=msg_b.get("uuid", ""),
            time_gap_seconds=gap_seconds,
            time_gap_weight=time_weight,
            entity_overlap=overlap,
            final_boundary_score=final_score,
            is_boundary=is_boundary,
        ))

    return boundaries


def _get_message_category(msg_uuid: str, patterns: dict[str, Any]) -> str | None:
    """Look up message category from Step 1 patterns."""
    for category_info in patterns.get("category_distribution", []):
        for example in category_info.get("example_messages", []):
            if example.get("uuid") == msg_uuid:
                return category_info.get("category")
    return None


def _detect_workflows(messages: list[dict[str, Any]],
                     boundaries: list[WorkflowBoundary],
                     patterns: dict[str, Any]) -> list[Workflow]:
    """Detect multi-step workflows using template matching."""
    workflows: list[Workflow] = []
    workflow_counter = 0

    # Sort messages by timestamp
    sorted_msgs = sorted(messages, key=lambda m: m.get("timestamp", ""))

    # Build boundary index (msg_b uuid -> is_boundary)
    boundary_before: dict[str, bool] = {}
    for b in boundaries:
        boundary_before[b.msg_b] = b.is_boundary

    # Segment messages by boundaries
    segments: list[list[dict[str, Any]]] = []
    current_segment: list[dict[str, Any]] = []

    for msg in sorted_msgs:
        uuid = msg.get("uuid", "")
        if boundary_before.get(uuid, False) and current_segment:
            segments.append(current_segment)
            current_segment = []
        current_segment.append(msg)

    if current_segment:
        segments.append(current_segment)

    # Match each segment against workflow templates
    for segment in segments:
        if len(segment) < 2:
            continue

        # Get categories for segment messages (from patterns)
        segment_categories: list[str] = []
        for msg in segment:
            cat = _get_message_category(msg.get("uuid", ""), patterns)
            if cat:
                segment_categories.append(cat)

        if len(segment_categories) < 2:
            continue

        # Find best matching template
        best_match: tuple[str, float] | None = None

        for template_name, template_cats in WORKFLOW_TEMPLATES.items():
            # Check if template categories appear in sequence (allowing gaps)
            template_idx = 0
            matches = 0

            for cat in segment_categories:
                if template_idx < len(template_cats) and cat == template_cats[template_idx]:
                    matches += 1
                    template_idx += 1

            if matches >= 2:  # At least 2 template steps matched
                confidence = matches / len(template_cats)
                if best_match is None or confidence > best_match[1]:
                    best_match = (template_name, confidence)

        if best_match:
            workflow_counter += 1

            # Calculate duration
            timestamps = []
            for msg in segment:
                ts_str = msg.get("timestamp", "")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        timestamps.append(ts)
                    except ValueError:
                        pass

            duration_minutes = 0
            if len(timestamps) >= 2:
                duration_minutes = int((max(timestamps) - min(timestamps)).total_seconds() / 60)

            # Get sessions
            session_ids = list({msg.get("session_id", "") for msg in segment})

            workflows.append(Workflow(
                workflow_id=f"wf-{workflow_counter:03d}",
                name=f"Detected: {best_match[0]}",
                pattern=best_match[0],
                pattern_confidence=best_match[1],
                messages=[
                    {
                        "uuid": msg.get("uuid", ""),
                        "category": _get_message_category(msg.get("uuid", ""), patterns),
                        "step": i + 1,
                    }
                    for i, msg in enumerate(segment)
                ],
                session_span=session_ids,
                duration_minutes=duration_minutes,
            ))

    return workflows


def analyze_workflows(
    messages_file: Path,
    patterns_file: Path,
    output_file: Path | None = None,
) -> WorkflowAnalysis:
    """Main entry point: analyze workflows from messages and patterns.

    Args:
        messages_file: Path to JSONL file with extracted user messages
        patterns_file: Path to YAML file from Step 1 (workflow-pattern-analyzer)
        output_file: Output path for step2-workflows.yaml (optional)

    Returns:
        WorkflowAnalysis with all analysis results
    """
    # Load inputs
    messages = _load_messages(messages_file)
    patterns = _load_patterns(patterns_file)

    # Build metadata
    metadata = {
        "source_file": messages_file.name,
        "patterns_file": patterns_file.name,
        "message_count": len(messages),
        "analysis_timestamp": datetime.now().isoformat(),
        "module": "workflow-sequence-analyzer",
        "version": "1.0",
    }

    # Run analysis pipeline
    sessions = _group_by_session(messages)
    session_links = _link_sessions(sessions)
    entity_clusters = _cluster_by_entities(messages)
    boundaries = _compute_boundaries(messages)
    workflows = _detect_workflows(messages, boundaries, patterns)

    # Compute handoff analysis
    handoff_count = sum(1 for link in session_links if any(
        s.get("link_evidence") == "handoff_detected" for s in link.sessions
    ))

    handoff_analysis = {
        "total_handoffs": handoff_count,
        "handoff_patterns": [
            {"pattern": "explicit_handoff", "count": handoff_count},
            {"pattern": "session_timeout", "count": len(session_links) - handoff_count},
        ],
        "recommendations": [],
    }

    if len(session_links) > handoff_count:
        handoff_analysis["recommendations"].append(
            "Consider using /ll:handoff for cleaner session transitions"
        )

    # Build result
    analysis = WorkflowAnalysis(
        metadata=metadata,
        session_links=session_links,
        entity_clusters=entity_clusters,
        workflow_boundaries=boundaries,
        workflows=workflows,
        handoff_analysis=handoff_analysis,
    )

    # Write output if path provided
    if output_file:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(analysis.to_dict(), f, default_flow_style=False, sort_keys=False)

    return analysis
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/workflow_sequence_analyzer.py`
- [ ] Lint passes: `ruff check scripts/little_loops/workflow_sequence_analyzer.py`
- [ ] Function exists: `python -c "from little_loops.workflow_sequence_analyzer import analyze_workflows; print('OK')"`

---

### Phase 4: CLI Entry Point

#### Overview
Add CLI interface with argument parsing and integrate with cli.py.

#### Changes Required

**File**: `scripts/little_loops/workflow_sequence_analyzer.py`
**Changes**: Add `main()` function

```python
def main() -> int:
    """Entry point for ll-workflows command.

    Analyze workflows from user messages and Step 1 patterns.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Workflow Sequence Analyzer - Step 2 of workflow analysis pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s analyze --input messages.jsonl --patterns step1.yaml
  %(prog)s analyze -i messages.jsonl -p patterns.yaml -o output.yaml
  %(prog)s analyze --input .claude/user-messages.jsonl --patterns .claude/workflow-analysis/step1-patterns.yaml
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # analyze subcommand
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze workflows from messages and patterns",
    )
    analyze_parser.add_argument(
        "-i", "--input",
        type=Path,
        required=True,
        help="Input JSONL file with user messages",
    )
    analyze_parser.add_argument(
        "-p", "--patterns",
        type=Path,
        required=True,
        help="Input YAML file from Step 1 (workflow-pattern-analyzer)",
    )
    analyze_parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output YAML file (default: .claude/workflow-analysis/step2-workflows.yaml)",
    )
    analyze_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print verbose progress information",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "analyze":
        # Validate input files
        if not args.input.exists():
            print(f"Error: Input file not found: {args.input}", file=sys.stderr)
            return 1

        if not args.patterns.exists():
            print(f"Error: Patterns file not found: {args.patterns}", file=sys.stderr)
            return 1

        # Set default output path
        output_path = args.output
        if output_path is None:
            output_path = Path(".claude/workflow-analysis/step2-workflows.yaml")

        if args.verbose:
            print(f"Input: {args.input}")
            print(f"Patterns: {args.patterns}")
            print(f"Output: {output_path}")

        try:
            analysis = analyze_workflows(
                messages_file=args.input,
                patterns_file=args.patterns,
                output_file=output_path,
            )

            # Print summary
            print(f"Analyzed {analysis.metadata['message_count']} messages")
            print(f"Found {len(analysis.session_links)} session links")
            print(f"Found {len(analysis.entity_clusters)} entity clusters")
            print(f"Detected {len(analysis.workflows)} workflows")
            print(f"Output written to: {output_path}")

            return 0

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

**File**: `scripts/pyproject.toml`
**Changes**: Add entry point

Add after line 52:
```toml
ll-workflows = "little_loops.workflow_sequence_analyzer:main"
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/workflow_sequence_analyzer.py`
- [ ] Lint passes: `ruff check scripts/little_loops/workflow_sequence_analyzer.py`
- [ ] CLI help works: `python -m little_loops.workflow_sequence_analyzer --help`
- [ ] After reinstall: `pip install -e ./scripts && ll-workflows --help`

---

### Phase 5: Tests

#### Overview
Create unit tests for the module.

#### Changes Required

**File**: `scripts/tests/test_workflow_sequence_analyzer.py`
**Changes**: Create test file

```python
"""Tests for workflow_sequence_analyzer module."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from little_loops.workflow_sequence_analyzer import (
    EntityCluster,
    SessionLink,
    Workflow,
    WorkflowAnalysis,
    WorkflowBoundary,
    analyze_workflows,
    calculate_boundary_weight,
    entity_overlap,
    extract_entities,
    get_verb_class,
    semantic_similarity,
)


class TestExtractEntities:
    """Tests for extract_entities function."""

    def test_file_paths(self) -> None:
        """Extracts file paths from content."""
        content = "Fix the bug in checkout.py and update config.json"
        entities = extract_entities(content)
        assert "checkout.py" in entities
        assert "config.json" in entities

    def test_slash_commands(self) -> None:
        """Extracts slash commands from content."""
        content = "Run /ll:commit and then /ll:check-code"
        entities = extract_entities(content)
        assert "/ll:commit" in entities
        assert "/ll:check-code" in entities

    def test_issue_ids(self) -> None:
        """Extracts issue IDs from content."""
        content = "Working on BUG-123 and FEAT-045"
        entities = extract_entities(content)
        assert "BUG-123" in entities
        assert "FEAT-045" in entities

    def test_phase_references(self) -> None:
        """Extracts phase references from content."""
        content = "Complete phase-1 and move to phase 2"
        entities = extract_entities(content)
        # Normalized to lowercase
        assert any("phase" in e.lower() for e in entities)

    def test_empty_content(self) -> None:
        """Returns empty set for empty content."""
        assert extract_entities("") == set()


class TestCalculateBoundaryWeight:
    """Tests for calculate_boundary_weight function."""

    def test_very_short_gap(self) -> None:
        """Gaps < 30s return 0.0."""
        assert calculate_boundary_weight(0) == 0.0
        assert calculate_boundary_weight(29) == 0.0

    def test_short_gap(self) -> None:
        """Gaps 30s-2min return 0.1."""
        assert calculate_boundary_weight(30) == 0.1
        assert calculate_boundary_weight(119) == 0.1

    def test_medium_gap(self) -> None:
        """Gaps 2-5min return 0.3."""
        assert calculate_boundary_weight(120) == 0.3
        assert calculate_boundary_weight(299) == 0.3

    def test_large_gap(self) -> None:
        """Gaps 5-15min return 0.5."""
        assert calculate_boundary_weight(300) == 0.5
        assert calculate_boundary_weight(899) == 0.5

    def test_very_large_gap(self) -> None:
        """Gaps > 2hr return 0.95."""
        assert calculate_boundary_weight(7200) == 0.95
        assert calculate_boundary_weight(10000) == 0.95


class TestEntityOverlap:
    """Tests for entity_overlap function."""

    def test_identical_sets(self) -> None:
        """Identical sets return 1.0."""
        entities = {"a", "b", "c"}
        assert entity_overlap(entities, entities) == 1.0

    def test_no_overlap(self) -> None:
        """Disjoint sets return 0.0."""
        assert entity_overlap({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self) -> None:
        """Partial overlap returns Jaccard similarity."""
        # {a, b} & {b, c} = {b}; union = {a, b, c}
        # Jaccard = 1/3
        result = entity_overlap({"a", "b"}, {"b", "c"})
        assert abs(result - 1/3) < 0.01

    def test_empty_sets(self) -> None:
        """Empty sets return 0.0."""
        assert entity_overlap(set(), set()) == 0.0
        assert entity_overlap({"a"}, set()) == 0.0


class TestGetVerbClass:
    """Tests for get_verb_class function."""

    def test_deletion_verbs(self) -> None:
        """Detects deletion verbs."""
        assert get_verb_class("Remove the old file") == "deletion"
        assert get_verb_class("Delete this function") == "deletion"

    def test_modification_verbs(self) -> None:
        """Detects modification verbs."""
        assert get_verb_class("Update the config") == "modification"
        assert get_verb_class("Fix the bug") == "modification"

    def test_creation_verbs(self) -> None:
        """Detects creation verbs."""
        assert get_verb_class("Create a new file") == "creation"
        assert get_verb_class("Add a feature") == "creation"

    def test_no_verb_class(self) -> None:
        """Returns None when no verb class matched."""
        assert get_verb_class("Hello world") is None


class TestDataclasses:
    """Tests for dataclass serialization."""

    def test_session_link_to_dict(self) -> None:
        """SessionLink serializes correctly."""
        link = SessionLink(
            link_id="link-001",
            sessions=[{"session_id": "abc", "position": 1, "link_evidence": "test"}],
            unified_workflow={"name": "Test", "total_messages": 5, "span_hours": 1.0},
            confidence=0.85,
        )
        d = link.to_dict()
        assert d["link_id"] == "link-001"
        assert d["confidence"] == 0.85

    def test_entity_cluster_to_dict(self) -> None:
        """EntityCluster serializes correctly."""
        cluster = EntityCluster(
            cluster_id="cluster-001",
            primary_entities=["file.py"],
            all_entities={"file.py", "test.py"},
            cohesion_score=0.756,
        )
        d = cluster.to_dict()
        assert d["cluster_id"] == "cluster-001"
        assert d["cohesion_score"] == 0.76  # Rounded

    def test_workflow_boundary_to_dict(self) -> None:
        """WorkflowBoundary serializes correctly."""
        boundary = WorkflowBoundary(
            msg_a="uuid-1",
            msg_b="uuid-2",
            time_gap_seconds=300,
            time_gap_weight=0.5,
            entity_overlap=0.333,
            final_boundary_score=0.35,
            is_boundary=False,
        )
        d = boundary.to_dict()
        assert d["between"]["msg_a"] == "uuid-1"
        assert d["entity_overlap"] == 0.33  # Rounded


class TestAnalyzeWorkflows:
    """Integration tests for analyze_workflows function."""

    @pytest.fixture
    def sample_messages(self) -> list[dict[str, Any]]:
        """Sample messages for testing."""
        base_time = datetime(2026, 1, 15, 10, 0, 0)
        return [
            {
                "content": "Find where the bug is in checkout.py",
                "timestamp": base_time.isoformat(),
                "session_id": "session-1",
                "uuid": "msg-001",
            },
            {
                "content": "Fix the null pointer in checkout.py",
                "timestamp": (base_time.replace(minute=5)).isoformat(),
                "session_id": "session-1",
                "uuid": "msg-002",
            },
            {
                "content": "Run the tests for checkout",
                "timestamp": (base_time.replace(minute=10)).isoformat(),
                "session_id": "session-1",
                "uuid": "msg-003",
            },
        ]

    @pytest.fixture
    def sample_patterns(self) -> dict[str, Any]:
        """Sample Step 1 patterns for testing."""
        return {
            "analysis_metadata": {
                "source_file": "test.jsonl",
                "message_count": 3,
            },
            "category_distribution": [
                {
                    "category": "debugging",
                    "count": 1,
                    "example_messages": [{"uuid": "msg-001", "content": "Find where..."}],
                },
                {
                    "category": "code_modification",
                    "count": 1,
                    "example_messages": [{"uuid": "msg-002", "content": "Fix the..."}],
                },
                {
                    "category": "testing",
                    "count": 1,
                    "example_messages": [{"uuid": "msg-003", "content": "Run the..."}],
                },
            ],
        }

    def test_basic_analysis(
        self,
        sample_messages: list[dict[str, Any]],
        sample_patterns: dict[str, Any],
    ) -> None:
        """Runs basic analysis pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Write input files
            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in sample_messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump(sample_patterns, f)

            output_file = tmpdir_path / "output.yaml"

            # Run analysis
            result = analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
                output_file=output_file,
            )

            # Verify result
            assert result.metadata["message_count"] == 3
            assert output_file.exists()

            # Verify output YAML
            with open(output_file) as f:
                output_data = yaml.safe_load(f)

            assert "analysis_metadata" in output_data
            assert "entity_clusters" in output_data
            assert "workflow_boundaries" in output_data

    def test_entity_clustering(
        self,
        sample_messages: list[dict[str, Any]],
        sample_patterns: dict[str, Any],
    ) -> None:
        """Entity clustering groups related messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in sample_messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump(sample_patterns, f)

            result = analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
            )

            # Should cluster messages about checkout.py
            if result.entity_clusters:
                checkout_cluster = next(
                    (c for c in result.entity_clusters if "checkout.py" in c.all_entities),
                    None,
                )
                if checkout_cluster:
                    assert len(checkout_cluster.messages) >= 2
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_workflow_sequence_analyzer.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_workflow_sequence_analyzer.py`

---

## Testing Strategy

### Unit Tests
- Entity extraction with various content types
- Boundary weight calculations for all time ranges
- Entity overlap edge cases (empty sets, identical sets)
- Verb class detection
- Dataclass serialization

### Integration Tests
- Full pipeline with sample messages and patterns
- Entity clustering behavior
- Output file generation and format

## References

- Original issue: `.issues/features/P2-FEAT-027-workflow-sequence-analyzer-python.md`
- Step 1 agent: `agents/workflow-pattern-analyzer.md`
- Existing CLI pattern: `scripts/little_loops/cli.py:307-430`
- UserMessage dataclass: `scripts/little_loops/user_messages.py:35-68`
