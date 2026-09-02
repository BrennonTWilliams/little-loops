"""Deterministic-only (Option A) evidence bundle assembly, isolated from production.

Proves the segregation mechanism FEAT-3182's `## Program Design` flags as
unprecedented: no field sourced from an LLM-graded `evaluate` event (one
carrying `llm_model`) is ever allowed into the `evidentiary` list. Everything
of that origin lands in `context_non_evidentiary`, always labeled
`llm_sourced: True`. Inputs are plain data (a `loop_runs`-row-shaped dict, an
archived-run-directory path, a git-facts dict) -- no sqlite read, no `git`
subprocess call; those are separate, already-precedented, unrisky mechanisms
this spike deliberately does not re-derive.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvidenceEntry:
    """One enumerable, source-traced evidentiary fact."""

    key: str
    value: Any
    source: str  # "git_ref" | "history_db_row" | "run_dir_file"

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value, "source": self.source}


@dataclass
class ContextEntry:
    """One segregated, labeled-non-evidentiary LLM-sourced fact."""

    key: str
    value: Any
    llm_sourced: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value, "llm_sourced": self.llm_sourced}


@dataclass
class GapEntry:
    """One explicit, enumerable evidence gap (never a silent omission)."""

    category: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"category": self.category, "detail": self.detail}


_EVIDENTIARY_SOURCES = frozenset({"git_ref", "history_db_row", "run_dir_file"})


@dataclass
class EvidenceBundle:
    """Top-level Option A bundle: deterministic facts plus segregated LLM context."""

    evidentiary: list[EvidenceEntry] = field(default_factory=list)
    context_non_evidentiary: list[ContextEntry] = field(default_factory=list)
    gaps: list[GapEntry] = field(default_factory=list)

    @property
    def has_gaps(self) -> bool:
        return bool(self.gaps)

    def to_dict(self) -> dict[str, Any]:
        """Locked stable-JSON shape -- plain dict/list/str/bool/int, no custom types."""
        return {
            "evidentiary": [e.to_dict() for e in self.evidentiary],
            "context_non_evidentiary": [c.to_dict() for c in self.context_non_evidentiary],
            "gaps": [g.to_dict() for g in self.gaps],
            "has_gaps": self.has_gaps,
        }

    def canonical_json(self) -> str:
        """Byte-identical across renders of unchanged inputs (AC2)."""
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_events(run_dir: Path) -> list[dict[str, Any]]:
    events_file = run_dir / "events.jsonl"
    events: list[dict[str, Any]] = []
    if not events_file.exists():
        return events
    with open(events_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def assemble_bundle(
    loop_runs_row: dict[str, Any] | None,
    run_dir: Path | None,
    git_facts: dict[str, str],
) -> EvidenceBundle:
    """Assemble an Option A bundle from three plain-data inputs.

    Any of the three inputs being absent produces an explicit `GapEntry`
    rather than a bundle that silently omits the corresponding evidence.
    """
    bundle = EvidenceBundle()

    for gk, gv in sorted(git_facts.items()):
        bundle.evidentiary.append(EvidenceEntry(key=f"git.{gk}", value=gv, source="git_ref"))

    if loop_runs_row is None:
        bundle.gaps.append(
            GapEntry("missing_loop_runs_row", "no loop_runs row supplied for this run")
        )
    else:
        for k, v in sorted(loop_runs_row.items()):
            bundle.evidentiary.append(
                EvidenceEntry(key=f"loop_runs.{k}", value=v, source="history_db_row")
            )

    if run_dir is None or not run_dir.is_dir():
        bundle.gaps.append(
            GapEntry("missing_run_dir", f"archived run directory not found: {run_dir}")
        )
        return bundle

    for name in ("state.json", "events.jsonl", "summary.json"):
        p = run_dir / name
        if p.exists():
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            bundle.evidentiary.append(
                EvidenceEntry(key=f"file.{name}.sha256", value=digest, source="run_dir_file")
            )

    probe_files = sorted(run_dir.glob("probe-*.json"))
    bundle.evidentiary.append(
        EvidenceEntry(key="probe_file_count", value=len(probe_files), source="run_dir_file")
    )
    if probe_files and len(probe_files) < 3:
        bundle.gaps.append(
            GapEntry(
                "missing_probe_file",
                f"expected 3 probe result files, found {len(probe_files)}",
            )
        )

    state_data = _read_json_file(run_dir / "state.json") or {}
    captured = state_data.get("captured", {})
    if isinstance(captured, dict):
        for key, entry in sorted(captured.items()):
            if isinstance(entry, dict) and "verdict" in entry:
                bundle.context_non_evidentiary.append(
                    ContextEntry(key=f"captured.{key}.verdict", value=entry["verdict"])
                )
                if "reason" in entry:
                    bundle.context_non_evidentiary.append(
                        ContextEntry(key=f"captured.{key}.reason", value=entry["reason"])
                    )

    for event in _read_events(run_dir):
        if event.get("event") == "evaluate" and "llm_model" in event:
            state = event.get("state", "?")
            for field_name in ("reason", "evidence", "raw", "llm_model", "llm_prompt"):
                if field_name in event:
                    bundle.context_non_evidentiary.append(
                        ContextEntry(key=f"evaluate.{state}.{field_name}", value=event[field_name])
                    )

    return bundle
