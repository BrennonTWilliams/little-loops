"""ll-loop config subcommands: compile, validate, install."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from little_loops.cli.loop._helpers import get_builtin_loops_dir, resolve_loop_path
from little_loops.logger import Logger


def cmd_compile(
    args: argparse.Namespace,
    logger: Logger,
) -> int:
    """Compile paradigm YAML to FSM."""
    import yaml

    from little_loops.fsm.compilers import compile_paradigm

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return 1

    try:
        with open(input_path) as f:
            spec = yaml.safe_load(f)
        fsm = compile_paradigm(spec)
    except ValueError as e:
        logger.error(f"Compilation error: {e}")
        return 1
    except yaml.YAMLError as e:
        logger.error(f"YAML parse error: {e}")
        return 1

    output_path = (
        Path(args.output) if args.output else Path(str(input_path).replace(".yaml", ".fsm.yaml"))
    )

    # Convert FSMLoop to dict for YAML output
    fsm_dict: dict[str, Any] = {
        "name": fsm.name,
        "paradigm": fsm.paradigm,
        "initial": fsm.initial,
        "states": {name: state.to_dict() for name, state in fsm.states.items()},
        "max_iterations": fsm.max_iterations,
    }
    if fsm.context:
        fsm_dict["context"] = fsm.context
    if fsm.maintain:
        fsm_dict["maintain"] = fsm.maintain
    if fsm.backoff:
        fsm_dict["backoff"] = fsm.backoff
    if fsm.timeout:
        fsm_dict["timeout"] = fsm.timeout

    with open(output_path, "w") as f:
        yaml.dump(fsm_dict, f, default_flow_style=False, sort_keys=False)

    logger.success(f"Compiled to: {output_path}")
    return 0


def cmd_validate(
    loop_name: str,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Validate a loop definition."""
    import yaml

    from little_loops.fsm.compilers import compile_paradigm
    from little_loops.fsm.validation import load_and_validate

    try:
        path = resolve_loop_path(loop_name, loops_dir)

        # Load the file to check format
        with open(path) as f:
            spec = yaml.safe_load(f)

        # Auto-compile if it's a paradigm file (has 'paradigm' but no 'initial')
        if "paradigm" in spec and "initial" not in spec:
            logger.info(f"Compiling paradigm file for validation: {path}")
            fsm = compile_paradigm(spec)
        else:
            fsm = load_and_validate(path)

        logger.success(f"{loop_name} is valid")
        print(f"  States: {', '.join(fsm.states.keys())}")
        print(f"  Initial: {fsm.initial}")
        print(f"  Max iterations: {fsm.max_iterations}")
        return 0
    except FileNotFoundError as e:
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
