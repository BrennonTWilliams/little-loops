"""Project type detection for headless ll-init."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Template filenames that are NOT project-type templates — skip during detection
_SECTION_TEMPLATES = frozenset(
    {
        "bug-sections.json",
        "feat-sections.json",
        "enh-sections.json",
        "epic-sections.json",
    }
)


@dataclass(frozen=True)
class TemplateMatch:
    """A matched project-type template."""

    name: str  # Human-readable name from _meta.name (e.g., "Python (Generic)")
    filename: str  # JSON filename (e.g., "python-generic.json")
    template_path: Path  # Absolute path to the template JSON
    meta: dict  # The _meta block
    data: dict  # Full template content (project, scan, issues, etc.)


def _find_templates_dir() -> Path:
    """Locate the templates/ directory relative to this package.

    Path: scripts/little_loops/init/detect.py → four parents up → project root.
    """
    return Path(__file__).parent.parent.parent.parent / "templates"


def _glob_match(pattern: str, root: Path) -> bool:
    """Return True if *pattern* matches at least one entry directly under *root*."""
    return any(True for _ in root.glob(pattern))


def _load_templates(templates_dir: Path) -> list[tuple[dict, Path]]:
    """Load all project-type template JSON files from *templates_dir*."""
    results: list[tuple[dict, Path]] = []
    for tmpl_path in sorted(templates_dir.glob("*.json")):
        if tmpl_path.name in _SECTION_TEMPLATES:
            continue
        try:
            data = json.loads(tmpl_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        meta = data.get("_meta", {})
        if "detect" not in meta:
            # Not a project-type template (e.g., section template without _meta.detect)
            continue
        results.append((data, tmpl_path))
    return results


def detect_documents(project_root: Path) -> dict:
    """Glob architecture and product documents into a categories dict.

    Patterns mirror the /ll:init skill's document auto-detection logic.
    Returns a dict suitable for config["documents"]["categories"]; empty if no docs found.
    """
    _EXCLUDE_DIRS = {".git", "node_modules", ".issues", ".ll", "dist", "build"}

    def _find(patterns: list[str]) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        for pattern in patterns:
            for p in sorted(project_root.glob(pattern)):
                parts = p.relative_to(project_root).parts
                if any(part in _EXCLUDE_DIRS for part in parts):
                    continue
                rel = str(p.relative_to(project_root))
                if rel not in seen:
                    seen.add(rel)
                    found.append(rel)
        return found

    arch_files = _find(
        [
            "**/architecture*.md",
            "**/design*.md",
            "**/api*.md",
            "docs/*.md",
        ]
    )
    product_files = _find(
        [
            "**/goal*.md",
            "**/roadmap*.md",
            "**/vision*.md",
            "**/requirements*.md",
        ]
    )

    categories: dict = {}
    if arch_files:
        categories["architecture"] = {
            "description": "Architecture and design documents",
            "files": arch_files,
        }
    if product_files:
        categories["product"] = {
            "description": "Product and requirements documents",
            "files": product_files,
        }
    return categories


def detect_project_type(root: Path, templates_dir: Path | None = None) -> TemplateMatch:
    """Detect the project type by matching template detect patterns against *root*.

    Algorithm:
    1. Load all project-type templates from templates_dir.
    2. Skip templates whose detect_exclude files exist at root.
    3. Match templates whose detect files exist at root.
    4. Empty detect list → fallback template (priority: -1).
    5. If no matches, return the fallback; raise if no fallback found.
    6. Among matches, return the first (alphabetical); fallback is last resort.

    Args:
        root: Project root directory to inspect.
        templates_dir: Override templates/ location (defaults to auto-discovery).

    Returns:
        The best-matching TemplateMatch; falls back to generic.json.

    Raises:
        FileNotFoundError: If no templates are found at all.
    """
    if templates_dir is None:
        templates_dir = _find_templates_dir()

    templates = _load_templates(templates_dir)
    if not templates:
        raise FileNotFoundError(f"No project-type templates found in {templates_dir}")

    fallback: TemplateMatch | None = None
    matches: list[TemplateMatch] = []

    for data, tmpl_path in templates:
        meta = data["_meta"]
        detect_files: list[str] = meta.get("detect", [])
        detect_exclude: list[str] = meta.get("detect_exclude", [])

        if not detect_files:
            # Empty detect → fallback candidate (generic.json has priority: -1)
            fallback = TemplateMatch(
                name=meta.get("name", tmpl_path.stem),
                filename=tmpl_path.name,
                template_path=tmpl_path,
                meta=meta,
                data=data,
            )
            continue

        # Check if at least one detect indicator exists at root
        if not any(_glob_match(f, root) for f in detect_files):
            continue

        # Excluded if any exclude file also exists
        if detect_exclude and any(_glob_match(f, root) for f in detect_exclude):
            continue

        matches.append(
            TemplateMatch(
                name=meta.get("name", tmpl_path.stem),
                filename=tmpl_path.name,
                template_path=tmpl_path,
                meta=meta,
                data=data,
            )
        )

    if matches:
        # On multi-match, prefer first alphabetically (templates are sorted on load)
        return matches[0]

    if fallback is not None:
        return fallback

    raise FileNotFoundError(
        f"No project-type template matched for {root} and no fallback found in {templates_dir}"
    )
