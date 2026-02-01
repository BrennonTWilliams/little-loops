"""Workflow Sequence Analyzer - Step 2 of the workflow analysis pipeline.

Identifies multi-step workflows and cross-session patterns using:
- Entity-based clustering
- Time-gap weighted boundaries
- Semantic similarity scoring
- Workflow template matching

Usage as CLI:
    ll-workflows analyze --input messages.jsonl --patterns step1.yaml
    ll-workflows analyze -i messages.jsonl -p patterns.yaml -o output.yaml

Usage as library:
    from little_loops.workflow_sequence_analyzer import analyze_workflows

    result = analyze_workflows(
        messages_file=Path("user-messages.jsonl"),
        patterns_file=Path("step1-patterns.yaml"),
        output_file=Path("step2-workflows.yaml"),
    )
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
    "extract_entities",
    "calculate_boundary_weight",
    "entity_overlap",
    "get_verb_class",
    "semantic_similarity",
]

# Module-level compiled regex patterns
FILE_PATTERN = re.compile(r"[\w./-]+\.(?:md|py|json|yaml|yml|js|ts|tsx|jsx|sh|toml)", re.IGNORECASE)
PHASE_PATTERN = re.compile(r"phase[- ]?\d+", re.IGNORECASE)
MODULE_PATTERN = re.compile(r"module[- ]?\d+", re.IGNORECASE)
COMMAND_PATTERN = re.compile(r"/[\w:-]+")
ISSUE_PATTERN = re.compile(r"(?:BUG|FEAT|ENH)-\d+", re.IGNORECASE)

# Verb class taxonomy for semantic similarity
VERB_CLASSES: dict[str, set[str]] = {
    "deletion": {"remove", "delete", "drop", "eliminate", "clear", "clean"},
    "modification": {"update", "change", "modify", "edit", "fix", "adjust", "revise"},
    "creation": {"create", "add", "generate", "write", "make", "build"},
    "search": {"find", "search", "locate", "where", "what", "which", "list"},
    "verification": {"check", "verify", "validate", "confirm", "review", "ensure"},
    "execution": {"run", "execute", "launch", "start", "invoke", "call"},
}

# Workflow templates: category sequences that indicate common patterns
WORKFLOW_TEMPLATES: dict[str, list[str]] = {
    "explore → modify → verify": ["file_search", "code_modification", "testing"],
    "create → refine → finalize": ["file_write", "code_modification", "git_operation"],
    "review → fix → commit": ["code_review", "code_modification", "git_operation"],
    "plan → implement → verify": ["planning", "code_modification", "testing"],
    "debug → fix → test": ["debugging", "code_modification", "testing"],
}


# -----------------------------------------------------------------------------
# Data Classes
# -----------------------------------------------------------------------------


@dataclass
class SessionLink:
    """Link between related sessions."""

    link_id: str
    sessions: list[dict[str, Any]]  # session_id, position, link_evidence
    unified_workflow: dict[str, Any]  # name, total_messages, span_hours
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
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
        """Convert to dictionary for YAML serialization."""
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
        """Convert to dictionary for YAML serialization."""
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
        """Convert to dictionary for YAML serialization."""
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
        """Convert to dictionary for YAML serialization."""
        return {
            "analysis_metadata": self.metadata,
            "session_links": [s.to_dict() for s in self.session_links],
            "entity_clusters": [c.to_dict() for c in self.entity_clusters],
            "workflow_boundaries": [b.to_dict() for b in self.workflow_boundaries],
            "workflows": [w.to_dict() for w in self.workflows],
            "handoff_analysis": self.handoff_analysis,
        }


# -----------------------------------------------------------------------------
# Core Analysis Functions
# -----------------------------------------------------------------------------


def extract_entities(content: str) -> set[str]:
    """Extract file paths, commands, and concepts from message content.

    Args:
        content: Message text content

    Returns:
        Set of extracted entities (file paths, commands, issue IDs, etc.)
    """
    entities: set[str] = set()

    # File paths
    entities.update(FILE_PATTERN.findall(content))

    # Phase/module references
    entities.update(PHASE_PATTERN.findall(content.lower()))
    entities.update(MODULE_PATTERN.findall(content.lower()))

    # Slash commands
    entities.update(COMMAND_PATTERN.findall(content))

    # Issue IDs (normalize to uppercase)
    entities.update(match.upper() for match in ISSUE_PATTERN.findall(content))

    return entities


def calculate_boundary_weight(gap_seconds: int) -> float:
    """Calculate workflow boundary weight based on time gap.

    Args:
        gap_seconds: Time gap between messages in seconds

    Returns:
        Boundary weight from 0.0 to 0.95
    """
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
    """Calculate Jaccard similarity between two entity sets.

    Args:
        entities_a: First set of entities
        entities_b: Second set of entities

    Returns:
        Jaccard similarity coefficient (0.0 to 1.0)
    """
    if not entities_a or not entities_b:
        return 0.0
    intersection = len(entities_a & entities_b)
    union = len(entities_a | entities_b)
    return intersection / union if union > 0 else 0.0


def get_verb_class(content: str) -> str | None:
    """Extract verb class from message content.

    Args:
        content: Message text content

    Returns:
        Verb class name or None if no match
    """
    content_lower = content.lower()
    words = set(re.findall(r"\b\w+\b", content_lower))

    for verb_class, verbs in VERB_CLASSES.items():
        if words & verbs:
            return verb_class
    return None


def semantic_similarity(
    content_a: str,
    content_b: str,
    entities_a: set[str],
    entities_b: set[str],
    category_a: str | None,
    category_b: str | None,
) -> float:
    """Calculate semantic similarity between two messages.

    Uses weighted combination of:
    - Keyword overlap (0.3)
    - Verb class match (0.3)
    - Entity overlap (0.3)
    - Category match (0.1)

    Args:
        content_a: First message content
        content_b: Second message content
        entities_a: Entities from first message
        entities_b: Entities from second message
        category_a: Category of first message
        category_b: Category of second message

    Returns:
        Similarity score (0.0 to 1.0)
    """
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
    return keyword_sim * 0.3 + verb_sim * 0.3 + entity_sim * 0.3 + category_sim * 0.1


# -----------------------------------------------------------------------------
# Internal Analysis Functions
# -----------------------------------------------------------------------------


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
        return yaml.safe_load(f) or {}


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
        entities_a: set[str] = set()
        for msg in session_a:
            entities_a.update(extract_entities(msg.get("content", "")))
        branch_a = last_msg_a.get("git_branch")

        for session_b_id in session_ids[i + 1 :]:
            session_b = sessions[session_b_id]
            if not session_b:
                continue

            first_msg_b = session_b[0] if session_b else {}
            entities_b: set[str] = set()
            for msg in session_b:
                entities_b.update(extract_entities(msg.get("content", "")))
            branch_b = first_msg_b.get("git_branch")

            # Calculate link score
            score = 0.0
            evidence: list[str] = []

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
                timestamps: list[datetime] = []
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

                links.append(
                    SessionLink(
                        link_id=f"link-{link_counter:03d}",
                        sessions=[
                            {
                                "session_id": session_a_id,
                                "position": 1,
                                "link_evidence": evidence[0] if evidence else "score",
                            },
                            {
                                "session_id": session_b_id,
                                "position": 2,
                                "link_evidence": evidence[-1] if evidence else "score",
                            },
                        ],
                        unified_workflow={
                            "name": f"Linked workflow {link_counter}",
                            "total_messages": len(session_a) + len(session_b),
                            "span_hours": round(span_hours, 1),
                        },
                        confidence=min(score, 1.0),
                    )
                )

    return links


def _cluster_by_entities(
    messages: list[dict[str, Any]], overlap_threshold: float = 0.3
) -> list[EntityCluster]:
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
            matched_cluster.messages.append(
                {
                    "uuid": msg.get("uuid", ""),
                    "content": content[:80] + "..." if len(content) > 80 else content,
                    "entities_matched": sorted(msg_entities & matched_cluster.all_entities),
                }
            )
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
                messages=[
                    {
                        "uuid": msg.get("uuid", ""),
                        "content": content[:80] + "..." if len(content) > 80 else content,
                        "entities_matched": sorted(msg_entities),
                    }
                ],
                cohesion_score=1.0,
            )
            clusters.append(cluster)

    # Filter out single-message clusters
    return [c for c in clusters if len(c.messages) >= 2]


def _compute_boundaries(
    messages: list[dict[str, Any]], boundary_threshold: float = 0.6
) -> list[WorkflowBoundary]:
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

        boundaries.append(
            WorkflowBoundary(
                msg_a=msg_a.get("uuid", ""),
                msg_b=msg_b.get("uuid", ""),
                time_gap_seconds=gap_seconds,
                time_gap_weight=time_weight,
                entity_overlap=overlap,
                final_boundary_score=final_score,
                is_boundary=is_boundary,
            )
        )

    return boundaries


def _get_message_category(msg_uuid: str, patterns: dict[str, Any]) -> str | None:
    """Look up message category from Step 1 patterns."""
    for category_info in patterns.get("category_distribution", []):
        for example in category_info.get("example_messages", []):
            if example.get("uuid") == msg_uuid:
                category = category_info.get("category")
                return category if isinstance(category, str) else None
    return None


def _detect_workflows(
    messages: list[dict[str, Any]],
    boundaries: list[WorkflowBoundary],
    patterns: dict[str, Any],
) -> list[Workflow]:
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
            timestamps: list[datetime] = []
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

            workflows.append(
                Workflow(
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
                )
            )

    return workflows


# -----------------------------------------------------------------------------
# Main API
# -----------------------------------------------------------------------------


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
    handoff_count = sum(
        1
        for link in session_links
        if any(s.get("link_evidence") == "handoff_detected" for s in link.sessions)
    )

    handoff_analysis: dict[str, Any] = {
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


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


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
  %(prog)s analyze --input .claude/user-messages.jsonl \\
                   --patterns .claude/workflow-analysis/step1-patterns.yaml
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # analyze subcommand
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze workflows from messages and patterns",
    )
    analyze_parser.add_argument(
        "-i",
        "--input",
        type=Path,
        required=True,
        help="Input JSONL file with user messages",
    )
    analyze_parser.add_argument(
        "-p",
        "--patterns",
        type=Path,
        required=True,
        help="Input YAML file from Step 1 (workflow-pattern-analyzer)",
    )
    analyze_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output YAML file (default: .claude/workflow-analysis/step2-workflows.yaml)",
    )
    analyze_parser.add_argument(
        "-v",
        "--verbose",
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
