"""ll-loop edit-routes subcommand: render and edit FSM routing as a decision table."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli.loop._helpers import resolve_loop_path
from little_loops.logger import Logger


def cmd_edit_routes(
    loop_name: str,
    args: argparse.Namespace,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Render a loop's routing as a decision table; open editor to modify routes.

    Returns:
        0 = success or no changes
        1 = parse error or unknown state in edited table
        2 = loop not found
    """
    from little_loops.fsm.route_table import (
        CompoundGridParser,
        CompoundGridRenderer,
        PolicyRuleApplier,
        PolicyRuleExtractor,
        RouteTableApplier,
        RouteTableExtractor,
        RouteTableParser,
        RouteTableRenderer,
        detect_routing_gaps,
        open_in_editor,
    )
    from little_loops.fsm.validation import load_and_validate

    fmt = getattr(args, "format", "markdown")
    dry_run = getattr(args, "dry_run", False)
    no_warnings = getattr(args, "no_warnings", False)
    allow_delete = getattr(args, "allow_delete", False)

    try:
        path = resolve_loop_path(loop_name, loops_dir)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 2

    try:
        fsm, _ = load_and_validate(path)
    except ValueError as e:
        logger.error(f"{loop_name} is invalid: {e}")
        return 1

    # Auto-detect decision-table mode: explicit flag OR loop imports policy-router with policy_rules
    decision_table = getattr(args, "decision_table", False) or (
        any("lib/policy-router" in imp for imp in fsm.imports)
        and "policy_rules" in fsm.context
    )

    if decision_table:
        # Decision-table mode: compound condition×action grid for policy-router loops
        rules = PolicyRuleExtractor.extract(fsm)
        table_text = (
            CompoundGridRenderer.to_csv(rules) if fmt == "csv"
            else CompoundGridRenderer.to_markdown(rules)
        )
        if dry_run:
            print(table_text, end="")
            return 0

        edited = open_in_editor(table_text, fmt)
        if edited is None:
            logger.error("Editor exited with non-zero status; no changes applied")
            return 1

        known_states = set(fsm.states.keys())
        try:
            parsed_dt = (
                CompoundGridParser.parse_csv(edited, known_states) if fmt == "csv"
                else CompoundGridParser.parse_markdown(edited, known_states)
            )
        except ValueError as e:
            logger.error(f"Parse error: {e}")
            return 1

        if not no_warnings:
            for w in parsed_dt.warnings:
                print(f"⚠  {w}")

        PolicyRuleApplier.apply(path, parsed_dt.rules)
        return 0

    # Gap/conflict detection (verdict-matrix mode only)
    if not no_warnings:
        warnings = detect_routing_gaps(fsm)
        for w in warnings:
            print(f"⚠  {w}")

    # Extract and render
    matrix = RouteTableExtractor.extract(fsm)
    if fmt == "csv":
        table_text = RouteTableRenderer.to_csv(matrix)
    else:
        table_text = RouteTableRenderer.to_markdown(matrix)

    if dry_run:
        print(table_text, end="")
        return 0

    # Open editor
    edited = open_in_editor(table_text, fmt)
    if edited is None:
        logger.error("Editor exited with non-zero status; no changes applied")
        return 1

    # Parse edited table
    known_states = set(fsm.states.keys())
    try:
        if fmt == "csv":
            parsed = RouteTableParser.parse_csv(edited, known_states)
        else:
            parsed = RouteTableParser.parse_markdown(edited, known_states)
    except ValueError as e:
        logger.error(f"Parse error: {e}")
        return 1

    # Apply changes
    RouteTableApplier.apply(
        path, matrix, parsed.matrix, new_stubs=parsed.new_stubs, allow_delete=allow_delete
    )
    return 0
