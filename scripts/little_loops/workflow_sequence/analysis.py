"""Analysis functions for workflow sequence detection."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from little_loops.workflow_sequence.io import _load_messages, _load_patterns
from little_loops.workflow_sequence.models import (
    EntityCluster,
    SessionLink,
    Workflow,
    WorkflowAnalysis,
    WorkflowBoundary,
)

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

# Maps content keywords to workflow category labels used by WORKFLOW_TEMPLATES
_CONTENT_CATEGORY_MAP: dict[str, list[str]] = {
    "file_search": ["search", "find", "glob", "grep", "locate"],
    "code_modification": ["edit", "write", "fix", "refactor", "update", "implement"],
    "testing": ["test", "pytest", "assert", "verify", "check"],
    "git_operation": ["commit", "push", "branch", "pr", "merge", "pull"],
    "planning": ["plan", "design", "architect", "outline", "draft"],
    "debugging": ["debug", "trace", "breakpoint", "error", "exception", "bug"],
    "code_review": ["review", "inspect", "audit", "read", "examine"],
    "file_write": ["create", "generate", "scaffold", "write", "add"],
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


def _parse_timestamps(messages: list[dict[str, Any]]) -> list[datetime]:
    """Parse valid ISO timestamps from a list of messages, stripping timezone info."""
    timestamps = []
    for msg in messages:
        ts_str = msg.get("timestamp", "")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is not None:
                    ts = ts.replace(tzinfo=None)
                timestamps.append(ts)
            except (ValueError, AttributeError, TypeError):
                pass
    return timestamps


def _group_by_session(messages: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group messages by session_id."""
    sessions: dict[str, list[dict[str, Any]]] = {}
    for msg in messages:
        session_id = msg.get("session_id", "unknown")
        if session_id not in sessions:
            sessions[session_id] = []
        sessions[session_id].append(msg)
    return sessions


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
                timestamps = _parse_timestamps(session_a + session_b)

                span_hours = 0.0
                if len(timestamps) >= 2:
                    try:
                        span_hours = (max(timestamps) - min(timestamps)).total_seconds() / 3600
                    except TypeError:
                        span_hours = 0.0

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
                            "evidence": evidence,
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
            entities_matched = sorted(msg_entities & matched_cluster.all_entities)
            matched_cluster.all_entities.update(msg_entities)
            matched_cluster.messages.append(
                {
                    "uuid": msg.get("uuid", ""),
                    "content": content[:80] + "..." if len(content) > 80 else content,
                    "entities_matched": entities_matched,
                    "timestamp": msg.get("timestamp"),
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
                        "timestamp": msg.get("timestamp"),
                    }
                ],
                cohesion_score=1.0,
            )
            clusters.append(cluster)

    # Populate span and inferred_workflow for each multi-message cluster
    for cluster in clusters:
        # Compute span from timestamps
        timestamps = _parse_timestamps(cluster.messages)
        if len(timestamps) >= 2:
            cluster.span = {
                "start": min(timestamps).isoformat(),
                "end": max(timestamps).isoformat(),
            }

        # Infer workflow by matching cluster message content against WORKFLOW_TEMPLATES
        cluster_categories: set[str] = set()
        for m in cluster.messages:
            lower = m.get("content", "").lower()
            for category, keywords in _CONTENT_CATEGORY_MAP.items():
                if any(kw in lower for kw in keywords):
                    cluster_categories.add(category)

        best_name: str | None = None
        best_score = 0.0
        for template_name, template_cats in WORKFLOW_TEMPLATES.items():
            template_set = set(template_cats)
            if template_set:
                overlap = len(cluster_categories & template_set) / len(template_set)
                if overlap > best_score:
                    best_score = overlap
                    best_name = template_name
        if best_score >= 0.3:
            cluster.inferred_workflow = best_name

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
        pair_timestamps = _parse_timestamps([msg_a, msg_b])
        if len(pair_timestamps) == 2:
            gap_seconds = int((pair_timestamps[1] - pair_timestamps[0]).total_seconds())
        else:
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


def _build_category_index(patterns: dict[str, Any]) -> dict[str, str]:
    """Build a flat UUID → category mapping from patterns category_distribution."""
    index: dict[str, str] = {}
    for category_info in patterns.get("category_distribution", []):
        category = category_info.get("category")
        if not isinstance(category, str):
            continue
        for example in category_info.get("example_messages", []):
            uuid = example.get("uuid")
            if uuid:
                index[uuid] = category
    return index


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

    # Build category index (uuid -> category) for O(1) lookups
    category_index = _build_category_index(patterns)

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
            cat = category_index.get(msg.get("uuid", ""))
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
            timestamps = _parse_timestamps(segment)

            duration_minutes = 0
            if len(timestamps) >= 2:
                try:
                    duration_minutes = int((max(timestamps) - min(timestamps)).total_seconds() / 60)
                except TypeError:
                    duration_minutes = 0

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
                            "category": category_index.get(msg.get("uuid", "")),
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
    overlap_threshold: float = 0.3,
    boundary_threshold: float = 0.6,
    verbose: bool = False,
    output_format: str = "yaml",
) -> WorkflowAnalysis:
    """Main entry point: analyze workflows from messages and patterns.

    Args:
        messages_file: Path to JSONL file with extracted user messages
        patterns_file: Path to YAML file from Step 1 (workflow-pattern-analyzer)
        output_file: Output path for step2-workflows.yaml (optional)
        overlap_threshold: Minimum entity overlap to cluster messages together (default: 0.3)
        boundary_threshold: Minimum boundary score to split workflow segments (default: 0.6)
        verbose: Emit per-stage progress to stderr (default: False)
        output_format: Output serialization format, "yaml" or "json" (default: "yaml")

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
    if verbose:
        print(f"[1/4] Linking sessions across {len(sessions)} session(s)...", file=sys.stderr)
    session_links = _link_sessions(sessions)
    if verbose:
        print(f"      → {len(session_links)} link(s) found", file=sys.stderr)
    if verbose:
        print("[2/4] Clustering by entities...", file=sys.stderr)
    entity_clusters = _cluster_by_entities(messages, overlap_threshold=overlap_threshold)
    if verbose:
        print(f"      → {len(entity_clusters)} cluster(s) found", file=sys.stderr)
    if verbose:
        print("[3/4] Computing workflow boundaries...", file=sys.stderr)
    boundaries = _compute_boundaries(messages, boundary_threshold=boundary_threshold)
    if verbose:
        print(f"      → {len(boundaries)} boundary/boundaries found", file=sys.stderr)
    if verbose:
        print("[4/4] Detecting workflows...", file=sys.stderr)
    workflows = _detect_workflows(messages, boundaries, patterns)
    if verbose:
        print(f"      → {len(workflows)} workflow(s) detected", file=sys.stderr)

    # Cross-reference: link workflows to entity clusters and populate handoff_points
    uuid_to_cluster: dict[str, str] = {}
    for cluster in entity_clusters:
        for msg in cluster.messages:
            uuid = msg.get("uuid", "")
            if uuid:
                uuid_to_cluster[uuid] = cluster.cluster_id

    uuid_to_content: dict[str, str] = {
        m.get("uuid", ""): m.get("content", "") for m in messages if m.get("uuid", "")
    }

    for workflow in workflows:
        cluster_votes: dict[str, int] = {}
        for msg in workflow.messages:
            cluster_id = uuid_to_cluster.get(msg.get("uuid", ""))
            if cluster_id:
                cluster_votes[cluster_id] = cluster_votes.get(cluster_id, 0) + 1
        if cluster_votes:
            workflow.entity_cluster = max(cluster_votes, key=cluster_votes.__getitem__)

        for msg in workflow.messages:
            uuid = msg.get("uuid", "")
            if uuid and _detect_handoff(uuid_to_content.get(uuid, "")):
                workflow.handoff_points.append({"uuid": uuid, "type": "explicit_handoff"})

    # Compute handoff analysis
    handoff_count = sum(
        1
        for link in session_links
        if "handoff_detected" in link.unified_workflow.get("evidence", [])
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
            if output_format == "json":
                json.dump(analysis.to_dict(), f, indent=2, default=str)
            else:
                yaml.dump(analysis.to_dict(), f, default_flow_style=False, sort_keys=False)

    return analysis
