"""ll-next: advisory cross-verb next-action recommendations (FEAT-3561, FEAT-3711).

Reads the project's issue files (and, when a loop, sprint or scan action type is in scope, the
corresponding definitions, history and git activity) once, scores ``implement-issue``,
``refine-issue``, ``resolve-blocker``, ``run-loop``, ``run-sprint`` and ``capture-issues``
candidates deterministically, and prints up to N
recommendations (or explains one target). It is advisory and never runs the copied actions;
selection reads only the project's files (no git, no incidental telemetry).

Recording (FEAT-3711): a normal invocation also appends one ``shown`` event per offered
recommendation to the *existing* local ``history.db`` (it never creates or migrates the store)
and prints each saved ``rec_id``. ``--no-record`` and ``--explain`` write nothing. Two
subcommands dispatch on the first argument: ``accept REC_ID`` appends an idempotent explicit
acknowledgement, and ``feedback REC_ID`` is a read-only lookup (``accepted`` or ``unknown``).

Usage:
    ll-next [--json] [--top N] [--type VERB ...] [--no-record] [--explain VERB TARGET]
    ll-next accept REC_ID
    ll-next feedback [--json] REC_ID
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
            "Recommend what to do next across action types (advisory; nothing is executed). "
            "Offered recommendations are recorded in the existing local history store unless "
            "--no-record, --explain or the capture settings disable it. Run the copied actions "
            "from the printed project root."
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
  %(prog)s --type run-sprint                 Only existing sprint definitions with ready work
  %(prog)s --type capture-issues             A codebase scan when the configured scope is active
  %(prog)s --json                            Machine-readable envelope (see output-schema.json)
  %(prog)s --explain refine-issue FEAT-0123  Why this verb does or does not apply to the issue
  %(prog)s --explain run-loop NAME           Why a loop (exact command operand) is or is not offered
  %(prog)s --explain run-sprint NAME         Why a sprint (exact file stem) is or is not offered
  %(prog)s --explain capture-issues project  Why the configured scan scope is or is not offered
  %(prog)s --no-record                       Recommend without recording the offers
  %(prog)s accept REC_ID                     Explicitly acknowledge a recorded recommendation
  %(prog)s feedback REC_ID [--json]          Look up a recorded recommendation (accepted/unknown)

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
        "--no-record",
        action="store_true",
        help="Do not record the offered recommendations (--explain never records either)",
    )
    parser.add_argument(
        "--explain",
        nargs=2,
        metavar=("VERB", "TARGET"),
        help=(
            "Show the full assessment of TARGET for VERB: a full issue ID (e.g. FEAT-0123), "
            "for run-loop the exact loop command operand (may start with a dash), for "
            "run-sprint the exact sprint name, or for capture-issues the target `project`"
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


def _scan_in_scope(args: argparse.Namespace) -> bool:
    """True when the scan verb is in scope (scope and git activity are collected only then)."""
    from little_loops.next_arena.registry import scan_verbs

    scan = set(scan_verbs())
    if args.explain is not None:
        return args.explain[0] in scan
    return not args.types or any(t in scan for t in args.types)


def _sprints_in_scope(args: argparse.Namespace) -> bool:
    """True when the sprint verb is in scope (definitions and history are collected only then)."""
    from little_loops.next_arena.registry import sprint_verbs

    sprint = set(sprint_verbs())
    if args.explain is not None:
        return args.explain[0] in sprint
    return not args.types or any(t in sprint for t in args.types)


def _attach_sprint_history(state: Any, root: Path) -> tuple[Any, Any]:
    """Batch every candidate sprint name into one history request; ``(state, frozen target)``.

    Runs only when valid sprint definitions exist. The original-cwd-relative history target is
    frozen once here (independently of the recording gate) and returned so shown-offer recording
    reuses it; a freeze or read failure makes sprint history *unavailable* (typed, per request)
    without changing the recommendation outcome.
    """
    from dataclasses import replace

    from little_loops.next_arena.history import (
        HistoryReadResult,
        HistorySnapshot,
        RecentSprintInvocations,
        read_history_snapshot,
    )
    from little_loops.next_arena.inputs import Diagnostic
    from little_loops.next_arena.recording import freeze_history_target
    from little_loops.next_arena.sprint_state import sprint_history_names

    names = sprint_history_names(state.sprint_definitions)
    if not names:
        return state, None

    def unavailable(reason: str, detail: str) -> Any:
        from types import MappingProxyType

        result = HistoryReadResult(
            "unavailable",
            reason,
            diagnostics=(
                Diagnostic(
                    "history_unavailable",
                    f"history sprint_invocations read unavailable: {reason} ({detail})",
                    (),
                    "sprint_invocations",
                ),
            ),
        )
        return HistorySnapshot(
            MappingProxyType({"sprint_invocations": result}),
            result.diagnostics,
            state.as_of,
            None,
        )

    try:
        target, _provenance = freeze_history_target(root)
    except Exception as exc:  # sprint history unavailable; recording re-evaluates its own gate
        return replace(state, sprint_history=unavailable("target_unresolved", str(exc))), None
    try:
        snapshot = read_history_snapshot(
            target,
            as_of=state.as_of,
            requests=[RecentSprintInvocations(project_root=root, sprint_names=names)],
            now=_utc_now,
        )
    except Exception as exc:  # defensive: the reader reports storage trouble per request
        return replace(state, sprint_history=unavailable("read_failed", str(exc))), target
    return replace(state, sprint_history=snapshot), target


def _fail(message: str) -> int:
    print(f"ll-next: {message}", file=sys.stderr)
    return _EXIT_USAGE


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _subcommand_parser(name: str, description: str, *, json_flag: bool) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f"ll-next {name}",
        description=description,
        epilog="Exit codes: 0 success, 1 REC_ID unknown in this project, 2 usage, "
        "configuration or storage error.",
    )
    if json_flag:
        parser.add_argument("--json", action="store_true", help="Emit one JSON document")
    parser.add_argument(
        "rec_id",
        metavar="REC_ID",
        help="Recommendation ID printed by `ll-next` (8-4-4-4-12 hyphenated UUID, any case)",
    )
    return parser


def _parse_subcommand(
    parser: argparse.ArgumentParser, argv: list[str]
) -> tuple[argparse.Namespace | None, int | None, str | None]:
    """Parse a subcommand's argv; returns ``(args, exit_code, canonical_rec_id)``."""
    from little_loops.next_arena.recording import canonical_rec_id

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # --help (0) and argparse usage errors (2)
        return None, (exc.code if isinstance(exc.code, int) else _EXIT_USAGE), None
    try:
        return args, None, canonical_rec_id(args.rec_id)
    except ValueError:
        parser.print_usage(sys.stderr)
        return (
            None,
            _fail(f"REC_ID must be a hyphenated UUID (8-4-4-4-12), got {args.rec_id!r}"),
            None,
        )


def _history_context(
    sub: str,
) -> tuple[Path, str, Any, dict[str, str]] | int:
    """Project root, project key and frozen history target for a historical subcommand.

    Resolves only the root, the project config file (unreadable config exits 2) and the consumed
    history target; arena settings, project collection and ``next.*`` validation are bypassed.
    """
    from little_loops.config import BRConfig
    from little_loops.next_arena.recording import freeze_history_target, project_key_for
    from little_loops.paths import find_project_root

    root = find_project_root(Path.cwd())
    if root is None:
        return _fail(
            "no little-loops project found (no .ll/ directory in the current directory or "
            "its parents); run ll-init in your project first"
        )
    try:
        BRConfig(root)
    except Exception as exc:  # unreadable/invalid project config
        return _fail(f"could not load project configuration: {exc}")
    try:
        target, provenance = freeze_history_target(root)
    except Exception as exc:
        return _fail(f"could not resolve the history store for {sub}: {exc}")
    return root, project_key_for(root), target, provenance


def _main_accept(argv: list[str]) -> int:
    """``ll-next accept REC_ID``: idempotent explicit acknowledgement of a recorded offer."""
    parser = _subcommand_parser(
        "accept",
        "Explicitly acknowledge a recorded recommendation (idempotent). Acceptance records "
        "that you took the offer; it proves neither causation nor that work started or "
        "succeeded. Needs the existing history store (see `ll-session migrate`).",
        json_flag=False,
    )
    _args, code, rec_id = _parse_subcommand(parser, argv)
    if rec_id is None:
        return code if code is not None else _EXIT_USAGE
    context = _history_context("accept")
    if isinstance(context, int):
        return context
    _root, project_key, target, _provenance = context

    from little_loops.next_arena.recording import new_invocation_id, record_accepted
    from little_loops.next_arena.render import render_accept_text

    result = record_accepted(
        rec_id,
        target=target,
        project_key=project_key,
        invocation_id=new_invocation_id(),
        now=_utc_now,
    )
    if result.status in {"accepted", "already_accepted"} and result.offer is not None:
        print(
            render_accept_text(
                rec_id,
                result.offer,
                result.accepted_at or "",
                already=result.status == "already_accepted",
            )
        )
        return _EXIT_OK
    if result.status == "unknown":
        print(f"ll-next: no recommendation {rec_id} in this project.", file=sys.stderr)
        return _EXIT_NONE
    hint = (
        " (run `ll-session migrate` to prepare the history store)"
        if result.reason == "schema_not_ready"
        else ""
    )
    return _fail(f"cannot accept {rec_id}: {result.reason}{hint}")


def _main_feedback(argv: list[str]) -> int:
    """``ll-next feedback REC_ID``: read-only lookup reporting ``accepted`` or ``unknown``."""
    parser = _subcommand_parser(
        "feedback",
        "Look up a recorded recommendation: `accepted` (explicit acknowledgement present) or "
        "`unknown` (offer found, acceptance unknown). There is no `ignored` state. Read-only.",
        json_flag=True,
    )
    args, code, rec_id = _parse_subcommand(parser, argv)
    if args is None or rec_id is None:
        return code if code is not None else _EXIT_USAGE
    context = _history_context("feedback")
    if isinstance(context, int):
        return context
    _root, project_key, target, provenance = context

    from little_loops.next_arena.history import RecommendationLookup, read_history_snapshot
    from little_loops.next_arena.recording import FeedbackResult, lookup_feedback
    from little_loops.next_arena.render import (
        build_feedback_document,
        render_feedback_text,
        render_json,
    )

    snapshot = read_history_snapshot(
        target,
        as_of=_utc_now(),
        requests=[RecommendationLookup(project_key=project_key, rec_id=rec_id)],
        now=_utc_now,
    )
    result = lookup_feedback(snapshot, rec_id, provenance=provenance)
    if isinstance(result, FeedbackResult):
        exit_code = _EXIT_OK if result.found else _EXIT_NONE
    else:
        exit_code = _EXIT_USAGE
    if args.json:
        print(render_json(build_feedback_document(rec_id, result)))
    elif exit_code == _EXIT_USAGE:
        print(render_feedback_text(rec_id, result), file=sys.stderr)
    else:
        print(render_feedback_text(rec_id, result))
    return exit_code


def _record_offers(
    config: Any,
    root: Path,
    args: argparse.Namespace,
    selected: Any,
    as_of: datetime,
    frozen_target: Any = None,
) -> tuple[dict[str, Any], list[str]]:
    """Gate, then atomically record the shown rows; never changes the recommendations or exit."""
    from little_loops.next_arena.recording import (
        RecordingStatus,
        automatic_recording_gate,
        freeze_history_target,
        new_invocation_id,
        project_key_for,
        record_shown,
    )

    # The env kill switch and every config gate are evaluated before any target resolution.
    reason = automatic_recording_gate(
        config, no_record=args.no_record, explain=False, has_offers=bool(selected)
    )
    if reason is not None:
        return RecordingStatus("disabled", reason).to_dict(), []
    try:
        target = frozen_target
        if target is None:
            target, _provenance = freeze_history_target(root)
        result = record_shown(
            selected,
            target=target,
            project_key=project_key_for(root),
            invocation_id=new_invocation_id(),
            as_of=as_of,
            requested_top=args.top,
            requested_types=list(args.types or []),
            now=_utc_now,
        )
    except Exception:  # best-effort: recording trouble never changes recommendations or exit
        return RecordingStatus("unavailable", "write_failed").to_dict(), []
    return result.recording.to_dict(), list(result.rec_ids)


def main_next() -> int:
    """Entry point for the ll-next command.

    Returns:
        0 when recommendations or an existing target assessment were emitted, 1 when there is
        no eligible candidate or the explain target is absent, 2 for usage/configuration
        errors (concise stderr, empty stdout).
    """
    raw_argv = sys.argv[1:]
    if raw_argv[:1] == ["accept"]:  # historical subcommands dispatch before the flat parser
        return _main_accept(raw_argv[1:])
    if raw_argv[:1] == ["feedback"]:
        return _main_feedback(raw_argv[1:])
    parser = _build_parser()
    argv, protected_target = _protect_target(raw_argv)
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
        sprint_target_key,
        target_key_for,
    )
    from little_loops.next_arena.registry import (
        DOMAIN_LOOP,
        DOMAIN_SCAN,
        DOMAIN_SPRINT,
        get_verb,
    )
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
        if not (args.no_record or args.explain):
            config.next.resolve_recording_enabled()  # validate before any storage is touched
    except NextConfigError as exc:
        return _fail(f"invalid configuration: {exc}")
    except Exception as exc:  # unreadable/invalid project config
        return _fail(f"could not load project configuration: {exc}")

    state = collect_project_state(
        root,
        config=config,
        include_loops=_loops_in_scope(args),
        include_scan=_scan_in_scope(args),
        include_sprints=_sprints_in_scope(args),
        settings=settings,
    )
    if state.config_errors:
        return _fail("invalid configuration: " + "; ".join(state.config_errors))

    state, frozen_history_target = _attach_sprint_history(state, root)
    assessments = assess_candidates(state, settings=settings)
    state_diagnostics = (*state.diagnostics, *state.loop_diagnostics, *state.sprint_diagnostics)

    if args.explain is not None:
        verb, target = args.explain
        domain = get_verb(verb).domain
        if domain == DOMAIN_LOOP:
            key = loop_target_key(target)
        elif domain == DOMAIN_SPRINT:
            key = sprint_target_key(target)
        elif domain == DOMAIN_SCAN:
            # ``scan:SCOPE_HASH`` embeds the *current* scope; the readable target is ``project``.
            key = next(
                (a.target_key for a in assessments if a.action_type == verb and a.target == target),
                f"scan:{target}",
            )
        else:
            key = target_key_for(target)
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
                recording={"status": "disabled", "reason": "explain"},
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
    recording, rec_ids = _record_offers(
        config, root, args, selected, state.as_of, frozen_history_target
    )  # before rendering: IDs are exposed only for rows actually saved
    if args.json:
        envelope = build_envelope(
            project_root=root,
            as_of=state.as_of,
            selection_policy=selection_policy(top=args.top, bucket_order=order, caps=settings.caps),
            recording=recording,
            recommendations=selected,
            rec_ids=rec_ids,
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
                recording=recording,
                rec_ids=rec_ids,
            )
        )
    return _EXIT_OK if selected else _EXIT_NONE
