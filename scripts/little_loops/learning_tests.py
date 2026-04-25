"""Learning test registry for little-loops.

Provides CRUD operations for learning test records stored as YAML-frontmatter
markdown files under .ll/learning-tests/<slug>.md.

Reading uses yaml.safe_load on the raw frontmatter block (rather than the
hand-rolled parse_frontmatter) because the assertions field is a block
sequence of dicts, which parse_frontmatter cannot deserialize.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from little_loops.frontmatter import update_frontmatter
from little_loops.issue_parser import slugify

_DEFAULT_BASE_DIR = Path(".ll") / "learning-tests"


@dataclass
class Assertion:
    """A single claim tested against an API or library."""

    claim: str
    result: Literal["pass", "fail", "untested"]

    def to_dict(self) -> dict[str, str]:
        return {"claim": self.claim, "result": self.result}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Assertion:
        return cls(
            claim=data["claim"],
            result=data.get("result", "untested"),
        )


@dataclass
class LearnTestRecord:
    """A learning test record capturing what is known about an API or library."""

    target: str
    date: str
    status: Literal["proven", "refuted", "stale"]
    assertions: list[Assertion]
    raw_output_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "date": self.date,
            "status": self.status,
            "assertions": [a.to_dict() for a in self.assertions],
            "raw_output_path": self.raw_output_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LearnTestRecord:
        return cls(
            target=data["target"],
            date=data["date"],
            status=data.get("status", "proven"),
            assertions=[Assertion.from_dict(a) for a in (data.get("assertions") or [])],
            raw_output_path=data.get("raw_output_path"),
        )


def _resolve_base(base_dir: Path | None) -> Path:
    return base_dir if base_dir is not None else Path.cwd() / _DEFAULT_BASE_DIR


def _slug_path(target_slug: str, base_dir: Path) -> Path:
    return base_dir / f"{target_slug}.md"


def _read_frontmatter_yaml(content: str) -> dict[str, Any] | None:
    """Extract and parse the YAML frontmatter block using yaml.safe_load."""
    fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return None
    return yaml.safe_load(fm_match.group(1)) or {}


def write_record(record: LearnTestRecord, *, base_dir: Path | None = None) -> Path:
    """Write a LearnTestRecord to .ll/learning-tests/<slug>.md.

    Overwrites any existing file for the same target slug.
    Returns the path of the written file.
    """
    base = _resolve_base(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    slug = slugify(record.target)
    path = _slug_path(slug, base)
    fm_text = yaml.dump(record.to_dict(), default_flow_style=False, sort_keys=False).strip()
    path.write_text(f"---\n{fm_text}\n---\n")
    return path


def read_record(target_slug: str, *, base_dir: Path | None = None) -> LearnTestRecord | None:
    """Read a LearnTestRecord by slug. Returns None if not found."""
    base = _resolve_base(base_dir)
    path = _slug_path(target_slug, base)
    if not path.exists():
        return None
    data = _read_frontmatter_yaml(path.read_text())
    if data is None:
        return None
    return LearnTestRecord.from_dict(data)


def list_records(*, base_dir: Path | None = None) -> list[LearnTestRecord]:
    """Return all LearnTestRecord objects from the registry directory."""
    base = _resolve_base(base_dir)
    if not base.exists():
        return []
    records = []
    for md_file in sorted(base.glob("*.md")):
        data = _read_frontmatter_yaml(md_file.read_text())
        if data is not None:
            records.append(LearnTestRecord.from_dict(data))
    return records


def mark_stale(target_slug: str, *, base_dir: Path | None = None) -> None:
    """Set status to 'stale' on an existing record, preserving all other fields."""
    base = _resolve_base(base_dir)
    path = _slug_path(target_slug, base)
    if not path.exists():
        return
    updated = update_frontmatter(path.read_text(), {"status": "stale"})
    path.write_text(updated)


def check_learning_test(target: str, *, base_dir: Path | None = None) -> LearnTestRecord | None:
    """Look up a record by target name (slugified). Returns None if not found."""
    return read_record(slugify(target), base_dir=base_dir)
