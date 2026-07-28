"""Loop file path resolution — shared by the FSM core and CLI layers.

Relocated from ``cli/loop/_helpers.py`` (ENH-2773) so ``fsm/validation.py``,
``fsm/executor.py``, and ``fsm/fragments.py`` can resolve loop paths without a
cli -> fsm -> cli import cycle. ``cli/loop/_helpers.py`` re-exports these names
for backward compatibility.
"""

from __future__ import annotations

from pathlib import Path


def get_builtin_loops_dir() -> Path:
    """Get the path to built-in loops bundled with the plugin."""
    return Path(__file__).parent.parent / "loops"


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

    raise FileNotFoundError(f"Loop not found: {name_or_path}")
