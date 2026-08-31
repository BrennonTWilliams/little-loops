"""ll-loop config subcommands: validate, install."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from little_loops.cli.loop._helpers import get_builtin_loops_dir, resolve_loop_path
from little_loops.logger import Logger


def cmd_validate(
    loop_name: str,
    args: argparse.Namespace,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Validate a loop definition."""
    from little_loops.config import BRConfig
    from little_loops.fsm.validation import ValidationSeverity, load_and_validate

    as_json = getattr(args, "json", False)
    orchestration_request_path = BRConfig(Path.cwd()).orchestration.request_path

    # The try only wraps loading (path resolution + load_and_validate), never the
    # success-path emissions below: those emissions can raise BrokenPipeError
    # (an OSError subclass), and letting that reach these handlers would print a
    # second, contradictory "invalid" document over a pipe error. See BUG-3230.
    try:
        path = resolve_loop_path(loop_name, loops_dir)
        fsm, violations_or_warnings = load_and_validate(
            path,
            raise_on_error=not as_json,
            orchestration_request_path=orchestration_request_path,
        )
    except FileNotFoundError as e:
        # Must precede the OSError clause below: FileNotFoundError is an OSError
        # subclass, so an OSError handler placed first would swallow this case.
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
    except (ValueError, yaml.YAMLError, OSError) as e:
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
            logger.error(f"{loop_name} is invalid: {e}")
        return 1

    if as_json:
        from little_loops.cli.output import print_json

        violations = violations_or_warnings
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

    logger.success(f"{loop_name} is valid")
    print(f"  States: {', '.join(fsm.states.keys())}")
    print(f"  Initial: {fsm.initial}")
    print(f"  Max steps: {fsm.max_steps}")
    if fsm.max_iterations is not None:
        print(f"  Max iterations: {fsm.max_iterations}")
    return 0


def cmd_install(
    loop_name: str,
    loops_dir: Path,
    logger: Logger,
    name_override: str | None = None,
) -> int:
    """Copy a built-in loop, or an arbitrary loop YAML path, into loops_dir.

    BUG-3367: ``loop_name`` is name-or-path — a built-in name is tried first
    (unchanged behavior); anything else falls back to treating the argument as
    a filesystem path (e.g. a workflow-generator draft), deriving the install
    name from the YAML's internal ``name:`` field unless ``name_override`` is
    given, with promote-style collision suffixing.
    """
    import shutil

    builtin_dir = get_builtin_loops_dir()
    source = builtin_dir / f"{loop_name}.yaml"

    if source.exists():
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

    path_candidate = Path(loop_name)
    if not path_candidate.exists():
        available = [f.stem for f in builtin_dir.glob("*.yaml")] if builtin_dir.exists() else []
        logger.error(f"No built-in loop named '{loop_name}'")
        if available:
            print(f"Available built-in loops: {', '.join(sorted(available))}")
        return 1

    from little_loops.fsm import is_runnable_loop

    if not is_runnable_loop(path_candidate):
        logger.error(f"Not a runnable loop definition: {path_candidate}")
        return 1

    if name_override:
        base_name = name_override
    else:
        import yaml

        try:
            data = yaml.safe_load(path_candidate.read_text())
        except (OSError, yaml.YAMLError) as e:
            logger.error(f"Failed to read {path_candidate}: {e}")
            return 1
        base_name = data.get("name") if isinstance(data, dict) else None
        if not isinstance(base_name, str) or not base_name:
            logger.error(
                f"{path_candidate} has no internal 'name:' field; use --name to specify one"
            )
            return 1

    loops_dir.mkdir(exist_ok=True)
    candidate = base_name
    suffix = 1
    while (loops_dir / f"{candidate}.yaml").exists() or (
        builtin_dir / f"{candidate}.yaml"
    ).exists():
        suffix += 1
        candidate = f"{base_name}-{suffix}"

    dest = loops_dir / f"{candidate}.yaml"
    shutil.copy2(path_candidate, dest)
    print(f"Installed {path_candidate} to {dest}")
    print("You can now customize it by editing the file.")
    return 0
