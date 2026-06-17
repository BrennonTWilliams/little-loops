"""ll-loop config subcommands: validate, install."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli.loop._helpers import get_builtin_loops_dir, resolve_loop_path
from little_loops.logger import Logger


def cmd_validate(
    loop_name: str,
    args: argparse.Namespace,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Validate a loop definition."""
    from little_loops.fsm.validation import ValidationSeverity, load_and_validate

    as_json = getattr(args, "json", False)

    try:
        path = resolve_loop_path(loop_name, loops_dir)

        if as_json:
            from little_loops.cli.output import print_json

            fsm, violations = load_and_validate(path, raise_on_error=False)
            has_errors = any(v.severity == ValidationSeverity.ERROR for v in violations)
            print_json(
                {
                    "loop": loop_name,
                    "valid": not has_errors,
                    "violations": [
                        {"severity": v.severity.value, "path": v.path, "message": v.message}
                        for v in violations
                    ],
                }
            )
            return 1 if has_errors else 0

        fsm, warnings = load_and_validate(path)
        logger.success(f"{loop_name} is valid")
        print(f"  States: {', '.join(fsm.states.keys())}")
        print(f"  Initial: {fsm.initial}")
        print(f"  Max steps: {fsm.max_steps}")
        if fsm.max_iterations is not None:
            print(f"  Max iterations: {fsm.max_iterations}")
        for w in warnings:
            print(f"  ⚠ {w}")
        return 0
    except FileNotFoundError as e:
        if as_json:
            from little_loops.cli.output import print_json

            print_json(
                {
                    "loop": loop_name,
                    "valid": False,
                    "violations": [{"severity": "error", "path": "<root>", "message": str(e)}],
                }
            )
        else:
            logger.error(str(e))
        return 1
    except ValueError as e:
        logger.error(f"{loop_name} is invalid: {e}")
        return 1


def cmd_install(
    loop_name: str,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Copy a built-in loop to .loops/ for customization."""
    import shutil

    builtin_dir = get_builtin_loops_dir()
    source = builtin_dir / f"{loop_name}.yaml"

    if not source.exists():
        available = [f.stem for f in builtin_dir.glob("*.yaml")] if builtin_dir.exists() else []
        logger.error(f"No built-in loop named '{loop_name}'")
        if available:
            print(f"Available built-in loops: {', '.join(sorted(available))}")
        return 1

    loops_dir.mkdir(exist_ok=True)
    dest = loops_dir / f"{loop_name}.yaml"

    if dest.exists():
        logger.error(f"Loop already exists: {dest}")
        print("Remove it first or edit it directly.")
        return 1

    shutil.copy2(source, dest)
    print(f"Installed {loop_name} to {dest}")
    print("You can now customize it by editing the file.")
    return 0
