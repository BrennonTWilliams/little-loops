"""Data models for workflow sequence analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
