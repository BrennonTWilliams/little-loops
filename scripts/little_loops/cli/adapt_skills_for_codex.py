"""ll-adapt-skills-for-codex: thin alias for ``ll-adapt --host codex`` (skills + commands).

The implementation now lives in :mod:`little_loops.adapters.codex` and
:mod:`little_loops.adapters.core`.  This module is kept for backward
compatibility; it re-exports the original helper names used by tests and
delegates processing to :class:`~little_loops.adapters.codex.CodexEmitter`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from little_loops.adapters.codex import (
    CodexEmitter,
    _synthesized_skill_md,  # noqa: F401
    _title_case,  # noqa: F401
)
from little_loops.adapters.codex import (
    _extract_skill_short_desc as _extract_short_desc,  # noqa: F401
)
from little_loops.adapters.codex import (
    _insert_skill_fields as _insert_fields,  # noqa: F401
)
from little_loops.adapters.codex import (
    _make_openai_yaml_content as _make_openai_yaml,  # noqa: F401
)
from little_loops.adapters.core import process_commands as _core_process_commands
from little_loops.adapters.core import process_skills as _core_process_skills
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

__all__ = ["main_adapt_skills_for_codex"]


def _find_plugin_root() -> Path:
    from little_loops.skill_expander import _find_plugin_root as _fpr

    return _fpr()


# ---------------------------------------------------------------------------
# Backward-compat process wrappers (original 3/4-arg signatures)
# ---------------------------------------------------------------------------


def _process_skills(
    skills_dir: Path, apply: bool, quiet: bool
) -> tuple[int, int, int]:
    """Backward-compat wrapper: delegate to core traversal + CodexEmitter."""
    return _core_process_skills(CodexEmitter(), skills_dir, apply, quiet)


def _process_commands(
    commands_dir: Path, skills_dir: Path, apply: bool, quiet: bool
) -> tuple[int, int, int]:
    """Backward-compat wrapper: delegate to core traversal + CodexEmitter."""
    return _core_process_commands(CodexEmitter(), commands_dir, skills_dir, apply, quiet)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main_adapt_skills_for_codex() -> int:
    """Entry point for ll-adapt-skills-for-codex CLI."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-adapt-skills-for-codex", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-adapt-skills-for-codex",
            description=(
                "Add Codex Skills API frontmatter to ll skill SKILL.md files and "
                "bridge commands/*.md into skills/ll-<name>/ entries for Codex CLI. "
                "Dry-run by default; use --apply to write changes. "
                "(Thin alias for: ll-adapt --host codex)"
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  ll-adapt-skills-for-codex            # Dry-run: preview proposed changes
  ll-adapt-skills-for-codex --apply    # Write skill frontmatter + bridge commands
  ll-adapt-skills-for-codex --quiet    # Suppress per-entry output
""",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Write changes to SKILL.md files and create agents/openai.yaml (default: dry-run)",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            default=False,
            help="Suppress per-skill output; only print final summary",
        )

        args = parser.parse_args()

        plugin_root = _find_plugin_root()
        skills_dir = plugin_root / "skills"
        commands_dir = plugin_root / "commands"

        if not skills_dir.exists():
            print(f"ERROR: skills directory not found: {skills_dir}", file=sys.stderr)
            return 1

        mode = "APPLY" if args.apply else "DRY-RUN"
        if not args.quiet:
            print(f"ll-adapt-skills-for-codex [{mode}]")
            print(f"Skills dir: {skills_dir}")
            print(f"Commands dir: {commands_dir}")
            print()

        s_adapted, s_skipped, s_errors = _process_skills(skills_dir, args.apply, args.quiet)
        c_adapted, c_skipped, c_errors = _process_commands(
            commands_dir, skills_dir, args.apply, args.quiet
        )

        adapted = s_adapted + c_adapted
        skipped = s_skipped + c_skipped
        errors = s_errors + c_errors

        print(f"\nDone: {adapted} adapted, {skipped} skipped, {errors} errors")
        return 0 if errors == 0 else 1
