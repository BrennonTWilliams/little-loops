"""ll-adapt: unified host-parameterized skill/command/agent adapter.

Dispatches to host-specific emitters via the :func:`resolve_emitter` registry.
Dry-run by default; use ``--apply`` to write changes.
"""

from __future__ import annotations

import argparse
import sys

from little_loops.adapters.core import (
    AdapterError,
    process_agents,
    process_commands,
    process_skills,
    resolve_emitter,
)
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

__all__ = ["main_adapt"]


def _find_plugin_root():
    from little_loops.skill_expander import _find_plugin_root as _fpr

    return _fpr()


def main_adapt() -> int:
    """Entry point for ``ll-adapt`` CLI."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-adapt", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-adapt",
            description=(
                "Generate host-specific skill, command, and agent artefacts for a given host. "
                "Dry-run by default; use --apply to write changes."
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  ll-adapt --host codex                # Dry-run: preview proposed changes
  ll-adapt --host codex --apply        # Write Codex artefacts
  ll-adapt --host codex --only codebase-analyzer --apply  # Single agent
  ll-adapt --host codex --quiet        # Suppress per-entry output
""",
        )
        parser.add_argument(
            "--host",
            required=True,
            metavar="HOST",
            help="Target host (e.g. codex, omp)",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Write changes (default: dry-run)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            dest="dry_run",
            help="Preview changes without writing (default behaviour; explicit alias)",
        )
        parser.add_argument(
            "--only",
            metavar="NAME",
            default=None,
            help="Restrict agent processing to a single agent by stem name",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            default=False,
            help="Suppress per-entry output; only print final summary",
        )

        args = parser.parse_args()
        apply = args.apply and not args.dry_run

        try:
            emitter = resolve_emitter(args.host)
        except AdapterError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        plugin_root = _find_plugin_root()
        skills_dir = plugin_root / "skills"
        commands_dir = plugin_root / "commands"
        agents_dir = plugin_root / "agents"

        mode = "APPLY" if apply else "DRY-RUN"
        if not args.quiet:
            print(f"ll-adapt --host {args.host} [{mode}]")
            print(f"Plugin root: {plugin_root}")
            if args.only:
                print(f"Filter:      {args.only}")
            print()

        total_adapted = total_skipped = total_errors = 0

        # Skills
        if skills_dir.exists():
            s_adapted, s_skipped, s_errors = process_skills(emitter, skills_dir, apply, args.quiet)
            total_adapted += s_adapted
            total_skipped += s_skipped
            total_errors += s_errors

        # Commands
        c_adapted, c_skipped, c_errors = process_commands(
            emitter, commands_dir, skills_dir, apply, args.quiet
        )
        total_adapted += c_adapted
        total_skipped += c_skipped
        total_errors += c_errors

        # Agents
        if agents_dir.exists():
            codex_dir = plugin_root / ".codex" / "agents"
            a_adapted, a_skipped, a_errors = process_agents(
                emitter, agents_dir, codex_dir, apply, args.quiet, args.only
            )
            total_adapted += a_adapted
            total_skipped += a_skipped
            total_errors += a_errors

        print(f"\nDone: {total_adapted} adapted, {total_skipped} skipped, {total_errors} errors")
        return 0 if total_errors == 0 else 1
