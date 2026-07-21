"""Project type detection for headless ll-init."""

from __future__ import annotations

import json
import os
import sys
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
    match_count: int = 0  # Number of _meta.detect globs that matched (0 for fallback)


def _find_templates_dir() -> Path:
    """Locate the in-package templates/ directory.

    Honors CLAUDE_PLUGIN_ROOT only when its templates/ subdirectory exists
    (legacy override). Falls back to the in-package location so pip-installed
    and editable installs both resolve correctly without env vars.
    """
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        env_path = Path(env_root) / "templates"
        if env_path.is_dir():
            return env_path
    return Path(__file__).resolve().parent.parent / "templates"


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

    Convenience wrapper around detect_project_type_all() that returns just the
    winner. See that function for the full algorithm and candidate ordering.

    Args:
        root: Project root directory to inspect.
        templates_dir: Override templates/ location (defaults to auto-discovery).

    Returns:
        The best-matching TemplateMatch; falls back to generic.json.

    Raises:
        FileNotFoundError: If no templates are found at all.
    """
    return detect_project_type_all(root, templates_dir)[0]


def detect_project_type_all(root: Path, templates_dir: Path | None = None) -> list[TemplateMatch]:
    """Detect the project type, returning all scored candidates.

    Algorithm:
    1. Load all project-type templates from templates_dir.
    2. Score each template by counting how many of its `_meta.detect` globs
       matched at root (0 matches → not a candidate).
    3. Veto: a candidate with any `_meta.detect_exclude` glob present at root
       is dropped unconditionally, regardless of match strength.
    4. Empty detect list → fallback template (e.g. generic.json, priority: -1).
    5. Sort surviving candidates by (-match_count, -meta.priority, filename)
       so stronger evidence wins; ties fall back to priority, then the
       previous alphabetical order.
    6. If no candidate scored, return [fallback]; raise if no fallback found.

    Args:
        root: Project root directory to inspect.
        templates_dir: Override templates/ location (defaults to auto-discovery).

    Returns:
        Non-empty list of candidates; index 0 is the winner, the remainder
        (if any) are runners-up sorted by descending match strength.

    Raises:
        FileNotFoundError: If no templates are found at all, or nothing
            matched and no fallback template exists.
    """
    if templates_dir is None:
        templates_dir = _find_templates_dir()

    if not templates_dir.exists():
        print(
            f"  Warning: templates/ not found at {templates_dir}; defaulting to generic project type",
            file=sys.stderr,
        )
        return [
            TemplateMatch(
                name="Generic",
                filename="generic.json",
                template_path=templates_dir / "generic.json",
                meta={"name": "Generic", "detect": []},
                data={},
            )
        ]

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

        match_count = sum(1 for f in detect_files if _glob_match(f, root))
        if match_count == 0:
            continue

        # Excluded if any exclude file also exists — hard veto, independent
        # of match strength.
        if detect_exclude and any(_glob_match(f, root) for f in detect_exclude):
            continue

        matches.append(
            TemplateMatch(
                name=meta.get("name", tmpl_path.stem),
                filename=tmpl_path.name,
                template_path=tmpl_path,
                meta=meta,
                data=data,
                match_count=match_count,
            )
        )

    if matches:
        matches.sort(key=lambda m: (-m.match_count, -m.meta.get("priority", 0), m.filename))
        return matches

    if fallback is not None:
        return [fallback]

    raise FileNotFoundError(
        f"No project-type template matched for {root} and no fallback found in {templates_dir}"
    )


def format_detection_summary(matches: list[TemplateMatch]) -> str:
    """Format a human-readable detection summary from detect_project_type_all()'s output.

    Falls back to a plain "Detected project type: X" line when there's no
    scored evidence to show (the generic fallback, or a lone candidate).
    Otherwise reports the winner's match strength and any runner-ups, e.g.:
    "Detected: Python (Generic) — 3/3 indicators; also matched: Rust (1/2)".
    """
    winner = matches[0]
    if winner.match_count == 0:
        return f"Detected project type: {winner.name}"

    total = len(winner.meta.get("detect", []))
    summary = f"Detected: {winner.name} — {winner.match_count}/{total} indicators"

    runners_up = [m for m in matches[1:] if m.match_count > 0]
    if runners_up:
        parts = [f"{m.name} ({m.match_count}/{len(m.meta.get('detect', []))})" for m in runners_up]
        summary += "; also matched: " + ", ".join(parts)

    return summary
