"""Issue template assembly using per-type section definition files.

Reads per-type template files (bug-sections.json, feat-sections.json,
enh-sections.json) from templates/ and assembles structured markdown for
issue files. Used by sync pull to produce v2.0-compliant issues.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _default_templates_dir() -> Path:
    """Return the bundled templates/ directory relative to this package."""
    return Path(__file__).resolve().parent.parent.parent / "templates"


def load_issue_sections(issue_type: str, templates_dir: Path | None = None) -> dict[str, Any]:
    """Load per-type sections JSON from the given or default templates directory.

    Args:
        issue_type: Issue type prefix (BUG, FEAT, ENH).
        templates_dir: Optional override path. Defaults to bundled templates/.

    Returns:
        Parsed JSON data as a dict.

    Raises:
        FileNotFoundError: If the per-type sections file does not exist.
    """
    base = templates_dir if templates_dir is not None else _default_templates_dir()
    filename = f"{issue_type.lower()}-sections.json"
    path = base / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def assemble_issue_markdown(
    sections_data: dict[str, Any],
    issue_type: str,
    variant: str,
    issue_id: str,
    title: str,
    frontmatter: dict[str, Any],
    content: dict[str, str] | None = None,
    labels: list[str] | None = None,
) -> str:
    """Assemble structured markdown from template sections and content.

    Args:
        sections_data: Parsed per-type sections data.
        issue_type: Issue type prefix (BUG, FEAT, ENH).
        variant: Creation variant name (full, minimal, legacy).
        issue_id: Issue identifier (e.g. "ENH-517").
        title: Issue title text.
        frontmatter: Dict of YAML frontmatter key-value pairs.
        content: Optional mapping of section name to content string.
            Sections not in this dict get their creation_template placeholder.
        labels: Optional list of label strings for the Labels section.

    Returns:
        Complete markdown string with frontmatter, heading, and sections.
    """
    content = content or {}
    variant_config = sections_data.get("creation_variants", {}).get(variant)
    if variant_config is None:
        raise ValueError(f"Unknown creation variant: {variant!r}")

    common_sections = sections_data.get("common_sections", {})
    type_sections = sections_data.get("type_sections", {})
    exclude_deprecated = variant_config.get("exclude_deprecated", False)
    include_common = variant_config.get("include_common", [])
    include_type = variant_config.get("include_type_sections", False)

    parts: list[str] = []

    # YAML frontmatter
    parts.append("---")
    for key, value in frontmatter.items():
        parts.append(f"{key}: {value}")
    parts.append("---")
    parts.append("")

    # Title heading
    parts.append(f"# {issue_id}: {title}")
    parts.append("")

    # Common sections from variant
    for section_name in include_common:
        section_def = common_sections.get(section_name)
        if section_def is None:
            continue
        if exclude_deprecated and section_def.get("deprecated", False):
            continue
        _append_section(parts, section_name, section_def, content)

    # Type-specific sections
    if include_type and type_sections:
        for section_name, section_def in type_sections.items():
            if exclude_deprecated and section_def.get("deprecated", False):
                continue
            _append_section(parts, section_name, section_def, content)

    # Ensure Labels section is present (even if not in variant's include_common)
    if labels is not None and "Labels" not in include_common:
        labels_str = ", ".join(f"`{lbl}`" for lbl in labels) if labels else ""
        parts.append("## Labels")
        parts.append("")
        parts.append(labels_str)
        parts.append("")

    return "\n".join(parts)


def _append_section(
    parts: list[str],
    section_name: str,
    section_def: dict[str, Any],
    content: dict[str, str],
) -> None:
    """Append a single section to the parts list."""
    body = content.get(section_name, section_def.get("creation_template", ""))
    parts.append(f"## {section_name}")
    parts.append("")
    if body:
        parts.append(body)
        parts.append("")
