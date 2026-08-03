"""ll-issues fold-findings: one ``### Codebase Research Findings`` block per H2 (ENH-2993).

``commands/refine-issue.md`` is markdown; its only route into Python is
``Bash``, and its ``allowed-tools`` permits ``Bash(ll-issues:*)``. Without this
entry point :func:`~little_loops.issues.fold_research_findings.fold_research_findings`
is unreachable from Steps 5a/5c and the change ships inert — the same reason
``research_triage.py``'s entry point exists.

**Content arrives on stdin, never in argv.** The payload is LLM-authored
markdown containing backticks, ``$``, ``!``, em-dashes and newlines; routing it
through an argv-quoted ``Bash`` invocation is the single most likely way for
this change to ship broken. ``ll-issues prioritize`` already establishes stdin
as the in-repo convention for structured input.

Exit codes:

* ``0`` — folded (or, with ``--dry-run``, would have folded). Creating a
  missing findings block *or a missing parent H2* is an ordinary success path.
* ``1`` — the issue ID does not resolve, or stdin carried no payload.
* ``2`` — ``--section`` names an absent H2 and ``--no-create`` was passed.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def add_fold_findings_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the fold-findings subparser on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "fold-findings",
        help="Merge stdin markdown into the single Codebase Research Findings block under a section",
    )
    p.set_defaults(command="fold-findings")
    p.add_argument("issue_id", help="Issue ID to write into (e.g. ENH-2993)")
    p.add_argument(
        "--section",
        required=True,
        help="Parent H2 heading text, without the leading '## ' (e.g. 'Program Design')",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resulting block to stdout and write nothing",
    )
    p.add_argument(
        "--no-create",
        action="store_true",
        help="Exit 2 instead of creating --section when it is absent",
    )
    add_config_arg(p)
    return p


def _section_order(config: BRConfig, issue_path_name: str) -> list[str]:
    """Canonical v2.0 section order for the issue's type.

    Mirrors :func:`~little_loops.issue_template.assemble_issue_markdown`'s own
    emission order — common sections in template order, then type-specific ones
    — so a section created here lands where the template would have put it.
    Falls back to ENH's shared table when the type cannot be read; the
    ``common_sections`` block is documented as shared across BUG/FEAT/ENH.
    """
    from little_loops.issue_template import load_issue_sections, resolve_templates_dir

    issue_type = "ENH"
    for candidate in ("BUG", "FEAT", "ENH", "EPIC"):
        if f"-{candidate}-" in issue_path_name.upper():
            issue_type = candidate
            break
    try:
        data = load_issue_sections(issue_type, resolve_templates_dir(config))
    except (OSError, ValueError):
        return []
    return [*data.get("common_sections", {}), *data.get("type_sections", {})]


def cmd_fold_findings(config: BRConfig, args: argparse.Namespace) -> int:
    """Fold a stdin markdown batch into one findings block under ``--section``.

    The dated provenance line and the ``###`` heading are supplied here, never
    by the caller: hand-written headings are exactly the inert-adoption shape
    the ``duplicate_findings_block`` gap exists to catch.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.file_utils import atomic_write
    from little_loops.issues.fold_research_findings import (
        SUB_HEADING,
        dated_marker,
        ensure_section,
        find_subsections,
        fold_research_findings,
    )

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    payload = "" if sys.stdin.isatty() else sys.stdin.read()
    if not payload.strip():
        # A bad heredoc quoting is the likeliest cause, and a silent no-op there
        # would read as a successful fold in the caller's transcript.
        print("Error: no content on stdin — nothing to fold.", file=sys.stderr)
        return 1

    content = path.read_text(encoding="utf-8")
    order = _section_order(config, path.name)
    prepared = ensure_section(content, args.section, order)
    if prepared is not content and args.no_create:
        print(
            f"Error: section '{args.section}' not found in {path.name} (--no-create).",
            file=sys.stderr,
        )
        return 2

    updated = fold_research_findings(prepared, args.section, payload, marker=dated_marker())

    if args.dry_run:
        spans = find_subsections(updated, args.section, SUB_HEADING)
        block = updated[spans[0][1] : spans[0][2]].rstrip("\n") if spans else ""
        print(f"[dry-run] {path.name} — '{args.section}':\n")
        print(block)
        return 0

    atomic_write(path, updated)
    print(f"Folded findings into '{args.section}' in {path.name}.")
    return 0
