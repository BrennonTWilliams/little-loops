"""Loop file path resolution and loading — shared by the FSM core and CLI layers.

``resolve_loop_path``/``get_builtin_loops_dir`` relocated from
``cli/loop/_helpers.py`` (ENH-2773); ``load_loop``/``load_loop_with_spec``
relocated the same way (ENH-2776) so ``fsm/validation.py``, ``fsm/executor.py``,
``fsm/fragments.py``, and ``analytics/variance.py`` can resolve/load loops
without a cli -> fsm -> cli import cycle.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from little_loops.fsm.schema import FSMLoop
    from little_loops.logger import Logger


def get_builtin_loops_dir() -> Path:
    """Get the path to built-in loops bundled with the plugin."""
    return Path(__file__).parent.parent / "loops"


def draft_internal_name(workflow_yaml: Path) -> str | None:
    """Return a generator draft's internal ``name:`` field, or None if unreadable."""
    try:
        data = yaml.safe_load(workflow_yaml.read_text())
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    name = data.get("name")
    return name if isinstance(name, str) and name else None


def resolve_loop_path(name_or_path: str, loops_dir: Path) -> Path:
    """Resolve loop name to file path."""
    path = Path(name_or_path)
    if path.exists():
        return path

    # Try <loops_dir>/<name>.fsm.yaml first (compiled FSM)
    fsm_path = loops_dir / f"{name_or_path}.fsm.yaml"
    if fsm_path.exists():
        return fsm_path

    # Fall back to <loops_dir>/<name>.yaml
    loops_path = loops_dir / f"{name_or_path}.yaml"
    if loops_path.exists():
        return loops_path

    # Fall back to built-in loops from plugin directory
    builtin_path = get_builtin_loops_dir() / f"{name_or_path}.yaml"
    if builtin_path.exists():
        return builtin_path

    # BUG-3367: fall back to an unpromoted workflow-generator draft, addressed
    # by its instance-folder name (runs/<name>/workflow.yaml)...
    run_dir_path = loops_dir / "runs" / name_or_path / "workflow.yaml"
    if run_dir_path.exists():
        return run_dir_path

    # ...or by the draft's internal `name:` field, scanning runs/*/workflow.yaml.
    # Same latest-mtime-wins policy as `ll-loop list` uses for duplicate names.
    runs_root = loops_dir / "runs"
    if runs_root.exists():
        candidates = sorted(runs_root.glob("*/workflow.yaml"))
        matches = [wf for wf in candidates if draft_internal_name(wf) == name_or_path]
        if matches:
            matches.sort(key=lambda p: p.stat().st_mtime)
            if len(matches) > 1:
                skipped = ", ".join(str(p) for p in matches[:-1])
                print(
                    f"Note: skipped older draft(s) named {name_or_path!r}: {skipped}",
                    file=sys.stderr,
                )
            return matches[-1]

    raise FileNotFoundError(
        f"Loop not found: {name_or_path}. Tried: "
        f"{path} (as a filesystem path), "
        f"{fsm_path} (compiled FSM), "
        f"{loops_path} (project loop), "
        f"{builtin_path} (built-in loop), "
        f"{run_dir_path} (generator-draft run dir), "
        f"{runs_root}/*/workflow.yaml (generator-draft internal name scan)"
    )


def load_loop(name_or_path: str, loops_dir: Path, logger: Logger) -> FSMLoop:
    """Load and validate a loop.

    Raises:
        FileNotFoundError: If loop not found.
        ValueError: If loop is invalid.
    """
    from little_loops.fsm.validation import load_and_validate

    path = resolve_loop_path(name_or_path, loops_dir)
    fsm, _ = load_and_validate(path)
    return fsm


def load_loop_with_spec(
    name_or_path: str, loops_dir: Path, logger: Logger
) -> tuple[FSMLoop, dict[str, Any]]:
    """Load a loop and return both the FSMLoop and raw spec dict.

    Used by commands that need access to raw YAML fields (e.g., description).

    Raises:
        FileNotFoundError: If loop not found.
        ValueError: If loop is invalid.
    """
    import yaml

    from little_loops.fsm.validation import load_and_validate

    path = resolve_loop_path(name_or_path, loops_dir)

    with open(path) as f:
        spec = yaml.safe_load(f)

    fsm, _ = load_and_validate(path)
    return fsm, spec
