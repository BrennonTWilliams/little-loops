"""ll-verify-design-tokens: Structural lint for half-flipped design-token themes.

A design-token profile pairs a light-tuned ``semantic.json`` (defining the
``surface``, ``text``, ``border`` and ``action`` color groups) with one or more
``themes/<name>.json`` overrides. A *half-flipped* theme is one that inverts the
foreground/background pair — overriding both ``surface`` **and** ``text`` to move
onto a near-black (or near-white) surface — but leaves ``border``/``action`` (and
any other semantic color group) falling through to the light-tuned defaults. The
token-stamping path then renders those light values onto the inverted surface:
harsh gridlines, muddy accents, and a ``danger == action.primary`` collision.

This lint catches that class at authoring time. For every profile under the
profiles directory it computes, for each theme that performs a full inversion
(overrides ``surface`` and ``text``), the set of semantic color groups the theme
fails to override. A non-empty set is a violation.

A theme that does not invert the surface/text pair (e.g. a ``light.json`` that
only restates ``surface``) is exempt — falling through to the light-tuned
``semantic.json`` is correct for it.

Exit 0 when every inverting theme is complete; exit 1 on any violation.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Theme is treated as a full foreground/background inversion (and therefore
# required to override every semantic color group) only when it overrides BOTH
# of these groups. A theme touching neither (or only one) is not inverting and
# is exempt from the completeness requirement.
_INVERSION_GROUPS: frozenset[str] = frozenset({"surface", "text"})

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ThemeViolation:
    """One half-flipped theme: an inverting theme missing semantic color groups."""

    profile: str
    theme: str
    missing_groups: list[str]


@dataclass
class ProfileResult:
    """Lint result for a single profile directory."""

    profile: str
    violations: list[ThemeViolation] = field(default_factory=list)

    @property
    def has_violations(self) -> bool:
        return bool(self.violations)


# ---------------------------------------------------------------------------
# Core lint logic
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict:
    """Load a JSON object, returning {} on absence or parse/type error."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _color_groups(doc: dict) -> set[str]:
    """Return the set of color-group keys (surface, text, border, action, ...)."""
    color = doc.get("color")
    return set(color.keys()) if isinstance(color, dict) else set()


def lint_profile(profile_dir: Path) -> ProfileResult:
    """Lint one profile directory for half-flipped themes.

    For each ``themes/*.json`` that overrides both ``surface`` and ``text``
    (a full inversion), report any semantic color group it fails to override.
    """
    result = ProfileResult(profile=profile_dir.name)

    semantic_groups = _color_groups(_load_json(profile_dir / "semantic.json"))
    if not semantic_groups:
        return result  # nothing to compare against

    themes_dir = profile_dir / "themes"
    if not themes_dir.is_dir():
        return result

    for theme_file in sorted(themes_dir.glob("*.json")):
        theme_groups = _color_groups(_load_json(theme_file))
        # Only inverting themes (override both surface and text) must be complete.
        if not _INVERSION_GROUPS.issubset(theme_groups):
            continue
        missing = semantic_groups - theme_groups
        if missing:
            result.violations.append(
                ThemeViolation(
                    profile=profile_dir.name,
                    theme=theme_file.stem,
                    missing_groups=sorted(missing),
                )
            )

    return result


def lint_profiles_dir(profiles_dir: Path) -> list[ProfileResult]:
    """Lint every profile subdirectory under *profiles_dir*."""
    results: list[ProfileResult] = []
    for profile_dir in sorted(p for p in profiles_dir.iterdir() if p.is_dir()):
        result = lint_profile(profile_dir)
        if result.has_violations:
            results.append(result)
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _format_text_report(results: list[ProfileResult]) -> str:
    lines: list[str] = ["Design-Token Theme Completeness Lint", "=" * 50, ""]
    if results:
        lines.append("Half-flipped themes (override surface+text but omit groups):")
        for r in results:
            for v in r.violations:
                groups = ", ".join(v.missing_groups)
                lines.append(
                    f"  {v.profile}/themes/{v.theme}.json: missing color groups: {groups}"
                )
        lines.append("")
        lines.append("FAILED")
    else:
        lines.append("All inverting themes override every semantic color group.")
        lines.append("")
        lines.append("PASSED")
    return "\n".join(lines)


def _format_json_report(results: list[ProfileResult]) -> str:
    return json.dumps(
        {
            "violations": [
                {
                    "profile": v.profile,
                    "theme": v.theme,
                    "missing_groups": v.missing_groups,
                }
                for r in results
                for v in r.violations
            ],
            "passed": not results,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _find_profiles_dir(base_dir: Path) -> Path | None:
    """Locate a design-token ``profiles/`` directory under *base_dir*.

    Tries the source-repo bundled-template layout (editable + installed) and the
    user-project ``.ll/design-tokens/profiles/`` layout.
    """
    for candidate in (
        base_dir / "scripts" / "little_loops" / "templates" / "design-tokens" / "profiles",
        base_dir / "little_loops" / "templates" / "design-tokens" / "profiles",
        base_dir / ".ll" / "design-tokens" / "profiles",
    ):
        if candidate.is_dir():
            return candidate
    return None


def main_verify_design_tokens() -> int:
    """Entry point for ll-verify-design-tokens.

    Returns 0 when no half-flipped themes are found; 1 otherwise.

    Note: run against the bundled little-loops templates this currently flags
    ``editorial-mono`` (a known-incomplete profile pending a follow-on); fix or
    point ``--profiles-dir`` at a complete profile set to gate CI on exit 0.
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-design-tokens", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-verify-design-tokens",
            description=(
                "Lint design-token profiles for half-flipped themes — a theme that "
                "inverts surface+text but leaves border/action falling through to "
                "light-tuned semantic defaults."
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""\
Examples:
  %(prog)s                          # Auto-discover profiles dir from cwd
  %(prog)s -C /path/to/root         # Discover under a specific project root
  %(prog)s --profiles-dir DIR       # Lint a specific profiles directory
  %(prog)s --json                   # Machine-readable JSON output

Exit codes:
  0 - Every inverting theme overrides all semantic color groups
  1 - One or more half-flipped themes (or no profiles dir found)
""",
        )
        parser.add_argument(
            "-C",
            "--directory",
            type=Path,
            default=None,
            help="Project root to discover the profiles directory under (default: cwd)",
        )
        parser.add_argument(
            "--profiles-dir",
            type=Path,
            default=None,
            help="Explicit path to a design-token profiles/ directory (overrides -C discovery)",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            default=False,
            help="Output results as JSON",
        )

        args = parser.parse_args()

        profiles_dir = args.profiles_dir or _find_profiles_dir(args.directory or Path.cwd())

        if profiles_dir is None or not profiles_dir.is_dir():
            print(
                "ERROR: design-token profiles directory not found "
                f"(searched under {args.directory or Path.cwd()})",
                file=sys.stderr,
            )
            return 1

        results = lint_profiles_dir(profiles_dir)

        if args.json:
            print(_format_json_report(results))
        else:
            print(_format_text_report(results))

        return 1 if results else 0
