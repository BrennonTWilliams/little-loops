"""ll-next: advisory cross-verb next-action recommendations (FEAT-3561).

Reads the project's issue files (and, when a loop action type is in scope, its loop
definitions and filesystem run history) once, scores ``implement-issue``, ``refine-issue``,
``resolve-blocker`` and ``run-loop`` candidates deterministically, and prints up to N
recommendations (or explains one target). It is read-only and advisory: no ``history.db``
access, no git, no writes, no telemetry, and it never runs the copied actions.

Usage:
    ll-next [--json] [--top N] [--type VERB ...] [--explain VERB TARGET]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from little_loops.next_arena.registry import registered_verbs

_EXIT_OK = 0
_EXIT_NONE = 1
_EXIT_USAGE = 2


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid positive integer: {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value}")
    return value


def _build_parser() -> argparse.ArgumentParser:
    verbs = registered_verbs()
    parser = argparse.ArgumentParser(
        prog="ll-next",
        description=(
            "Recommend what to do next across action types (advisory; nothing is executed "
            "or written). Run the copied actions from the printed project root."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Action types: {", ".join(verbs)}

Examples:
  %(prog)s                                   One pass: the best candidate of each action type
  %(prog)s --top 10                          Up to 10, filled round-robin (per-type cap applies)
  %(prog)s --type refine-issue               Only refinement recommendations
  %(prog)s --type resolve-blocker            Only root blockers that gate other open work
  %(prog)s --type run-loop                   Only runnable loops (zero-argument, from history)
  %(prog)s --json                            Machine-readable envelope (see output-schema.json)
  %(prog)s --explain refine-issue FEAT-0123  Why this verb does or does not apply to the issue
  %(prog)s --explain run-loop NAME           Why a loop (exact command operand) is or is not offered

Exit codes:
  0 - recommendations (or a target assessment for --explain) were printed
  1 - no eligible candidate across the requested action types, or --explain target not found
  2 - usage error, no little-loops project found, or invalid configuration
""",
    )
    parser.add_argument("--json", action="store_true", help="Emit the JSON output envelope")
    parser.add_argument(
        "--top",
        type=_positive_int,
        default=None,
        metavar="N",
        help="Select up to N recommendations round-robin (default: one pass over the types)",
    )
    parser.add_argument(
        "--type",
        dest="types",
        action="append",
        choices=verbs,
        metavar="VERB",
        help=f"Restrict to an action type (repeatable): {', '.join(verbs)}",
    )
    parser.add_argument(
        "--explain",
        nargs=2,
        metavar=("VERB", "TARGET"),
        help=(
            "Show the full assessment of TARGET for VERB: a full issue ID (e.g. FEAT-0123), "
            "or for run-loop the exact loop command operand (may start with a dash)"
        ),
    )
    return parser


#: Stand-in for a literal ``--explain`` target while argparse runs (see :func:`_protect_target`).
_TARGET_PLACEHOLDER = "ll-next-explain-target-placeholder"


def _protect_target(argv: list[str]) -> tuple[list[str], str | None]:
    """Hide an option-looking ``--explain VERB TARGET`` operand from argparse.

    ``nargs=2`` cannot take a value such as ``-foo`` or ``--json`` (Python 3.11 rejects it;
    3.12 disambiguates by position). The operand directly after ``--explain VERB`` is always
    the literal target, so swap it for a placeholder before parsing and restore it after.
    Output flags that follow keep their meaning. Returns ``(argv, target-or-None)``.
    """
    registered = registered_verbs()
    for index, token in enumerate(argv):
        if token != "--explain":
            continue
        if index + 2 < len(argv) and argv[index + 1] in registered:
            protected = list(argv)
            protected[index + 2] = _TARGET_PLACEHOLDER
            return protected, argv[index + 2]
        break
    return argv, None


def _loops_in_scope(args: argparse.Namespace) -> bool:
    """True when a loop verb is in scope (loop sources and history are collected only then)."""
    from little_loops.next_arena.registry import loop_verbs

    loop = set(loop_verbs())
    if args.explain is not None:
        return args.explain[0] in loop
    return not args.types or any(t in loop for t in args.types)


def _fail(message: str) -> int:
    print(f"ll-next: {message}", file=sys.stderr)
    return _EXIT_USAGE


def main_next() -> int:
    """Entry point for the ll-next command.

    Returns:
        0 when recommendations or an existing target assessment were emitted, 1 when there is
        no eligible candidate or the explain target is absent, 2 for usage/configuration
        errors (concise stderr, empty stdout).
    """
    parser = _build_parser()
    argv, protected_target = _protect_target(sys.argv[1:])
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # --help (0) and argparse usage errors (2)
        return exc.code if isinstance(exc.code, int) else _EXIT_USAGE
    if protected_target is not None and args.explain is not None:
        args.explain = [args.explain[0], protected_target]

    if args.explain is not None:
        if args.top is not None or args.types:
            parser.print_usage(sys.stderr)
            return _fail("--explain cannot be combined with --top or --type")
        if args.explain[0] not in registered_verbs():
            parser.print_usage(sys.stderr)
            return _fail(
                f"--explain VERB must be one of: {', '.join(registered_verbs())} "
                f"(got {args.explain[0]!r})"
            )

    # Local imports keep `--help`/usage errors free of heavy module imports.
    from little_loops.config import BRConfig
    from little_loops.config.features import NextConfigError
    from little_loops.next_arena.candidates import (
        assess_candidates,
        assessments_for_target,
        candidates_from_assessments,
        loop_target_key,
        target_key_for,
    )
    from little_loops.next_arena.registry import DOMAIN_LOOP, get_verb
    from little_loops.next_arena.render import (
        build_envelope,
        build_explanation,
        collect_diagnostics,
        render_explain_text,
        render_json,
        render_text,
        scope_subject,
        target_not_found,
    )
    from little_loops.next_arena.selection import (
        bucket_order_for,
        select_candidates,
        selection_policy,
    )
    from little_loops.next_arena.state import collect_project_state
    from little_loops.paths import find_project_root

    # Resolve the project root once; every later step receives it.
    root = find_project_root(Path.cwd())
    if root is None:
        return _fail(
            "no little-loops project found (no .ll/ directory in the current directory or "
            "its parents); run ll-init in your project first"
        )

    try:
        config = BRConfig(root)
        settings = config.next.resolve_arena_settings()
    except NextConfigError as exc:
        return _fail(f"invalid configuration: {exc}")
    except Exception as exc:  # unreadable/invalid project config
        return _fail(f"could not load project configuration: {exc}")

    state = collect_project_state(root, config=config, include_loops=_loops_in_scope(args))
    if state.config_errors:
        return _fail("invalid configuration: " + "; ".join(state.config_errors))

    assessments = assess_candidates(state, settings=settings)
    state_diagnostics = (*state.diagnostics, *state.loop_diagnostics)

    if args.explain is not None:
        verb, target = args.explain
        key = (
            loop_target_key(target)
            if get_verb(verb).domain == DOMAIN_LOOP
            else target_key_for(target)
        )
        named, alternates = assessments_for_target(assessments, key, verb)
        explanation = build_explanation(named, alternates)
        if named is None:
            diagnostics = [target_not_found(target, verb)]
        else:
            diagnostics = collect_diagnostics(
                state_diagnostics, assessments, (verb,), scope_to=scope_subject(verb, target)
            )
        policy = selection_policy(top=None, bucket_order=(verb,), caps=settings.caps)
        if args.json:
            envelope = build_envelope(
                project_root=root,
                as_of=state.as_of,
                selection_policy=policy,
                explanation=explanation,
                diagnostics=diagnostics,
            )
            print(render_json(envelope))
        else:
            print(
                render_explain_text(
                    project_root=root,
                    explanation=explanation,
                    verb=verb,
                    target=target,
                    diagnostics=diagnostics,
                )
            )
        return _EXIT_OK if named is not None else _EXIT_NONE

    order = bucket_order_for(args.types)
    selected = select_candidates(
        candidates_from_assessments(assessments),
        top=args.top,
        bucket_order=order,
        caps=settings.caps,
    )
    diagnostics = collect_diagnostics(state_diagnostics, assessments, order)
    if args.json:
        envelope = build_envelope(
            project_root=root,
            as_of=state.as_of,
            selection_policy=selection_policy(top=args.top, bucket_order=order, caps=settings.caps),
            recommendations=selected,
            diagnostics=diagnostics,
        )
        print(render_json(envelope))
    else:
        print(
            render_text(
                project_root=root,
                recommendations=selected,
                bucket_order=order,
                diagnostics=diagnostics,
            )
        )
    return _EXIT_OK if selected else _EXIT_NONE
