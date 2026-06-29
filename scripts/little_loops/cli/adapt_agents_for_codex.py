"""ll-adapt-agents-for-codex: thin alias for ``ll-adapt --host codex`` (agents).

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
    _format_agent_toml,
)
from little_loops.adapters.codex import (
    _extract_agent_short_desc as _extract_short_desc,  # noqa: F401
)
from little_loops.adapters.core import _read_frontmatter
from little_loops.adapters.core import process_agents as _core_process_agents
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

__all__ = ["main_adapt_agents_for_codex"]

_MAX_SHORT_DESC = 80


def _find_plugin_root() -> Path:
    from little_loops.skill_expander import _find_plugin_root as _fpr

    return _fpr()


# ---------------------------------------------------------------------------
# Backward-compat function wrappers (original signatures)
# ---------------------------------------------------------------------------


def _extract_agent_frontmatter(text: str) -> dict | None:
    """Backward-compat wrapper around core._read_frontmatter."""
    return _read_frontmatter(text)


def _emit_agent_toml(name: str, description: str, model: str, body: str) -> str:
    """Backward-compat wrapper (4-arg): delegates to _format_agent_toml with empty fm."""
    return _format_agent_toml(name, description, model, body, {})


def _process_agents(
    agents_dir: Path,
    codex_dir: Path,
    apply: bool,
    quiet: bool,
    only: str | None,
) -> tuple[int, int, int]:
    """Backward-compat wrapper: delegate to core traversal + CodexEmitter."""
    return _core_process_agents(CodexEmitter(), agents_dir, codex_dir, apply, quiet, only)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main_adapt_agents_for_codex() -> int:
    """Entry point for ll-adapt-agents-for-codex CLI."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-adapt-agents-for-codex", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-adapt-agents-for-codex",
            description=(
                "Emit .codex/agents/<name>.toml files from agents/*.md for Codex subagent "
                "discovery. Dry-run by default; use --apply to write changes. "
                "(Thin alias for: ll-adapt --host codex)"
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  ll-adapt-agents-for-codex              # Dry-run: preview proposed changes
  ll-adapt-agents-for-codex --apply      # Write .codex/agents/*.toml files
  ll-adapt-agents-for-codex --only codebase-analyzer --apply  # Single agent
  ll-adapt-agents-for-codex --quiet      # Suppress per-entry output
""",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Write .codex/agents/*.toml files (default: dry-run)",
        )
        parser.add_argument(
            "--only",
            metavar="NAME",
            default=None,
            help="Restrict to a single agent by stem name (e.g. codebase-analyzer)",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            default=False,
            help="Suppress per-agent output; only print final summary",
        )

        args = parser.parse_args()

        plugin_root = _find_plugin_root()
        agents_dir = plugin_root / "agents"
        codex_dir = plugin_root / ".codex" / "agents"

        if not agents_dir.exists():
            print(f"ERROR: agents directory not found: {agents_dir}", file=sys.stderr)
            return 1

        mode = "APPLY" if args.apply else "DRY-RUN"
        if not args.quiet:
            print(f"ll-adapt-agents-for-codex [{mode}]")
            print(f"Agents dir: {agents_dir}")
            print(f"Output dir: {codex_dir}")
            if args.only:
                print(f"Filter:     {args.only}")
            print()

        adapted, skipped, errors = _process_agents(
            agents_dir, codex_dir, args.apply, args.quiet, args.only
        )

        print(f"\nDone: {adapted} adapted, {skipped} skipped, {errors} errors")
        return 0 if errors == 0 else 1
