"""ll-loop artifact/path header helpers — shared by run_foreground and feed.py.

Relocated from ``cli/loop/_helpers.py`` (ENH-2776).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.cli.loop.layout import _display_width, _truncate_to_width_ansi
from little_loops.cli.output import colorize
from little_loops.fsm.loop_paths import get_builtin_loops_dir

if TYPE_CHECKING:
    from little_loops.fsm.schema import FSMLoop


def _relativize_to_cwd(value: str) -> str:
    """Shorten an absolute path that lives under the current working directory.

    Absolute paths nested under ``cwd`` are rendered relative to it (e.g.
    ``/path/to/proj/.loops/runs/x/`` -> ``.loops/runs/x/``). Any trailing
    slash on *value* is preserved. Values that are already relative, or that
    point outside ``cwd``, are returned unchanged.
    """
    try:
        path = Path(value)
        if not path.is_absolute():
            return value
        rel = path.relative_to(Path.cwd())
    except (ValueError, OSError):
        return value
    result = str(rel)
    if value.endswith("/") and not result.endswith("/"):
        result += "/"
    return result


def _display_loop_path(loop_path: Path) -> str:
    """Render *loop_path* compactly for artifact headers.

    Built-in FSM loops (bundled under :func:`get_builtin_loops_dir`) are shown
    by filename only. Project-level loops (typically under ``.loops/``) and any
    other paths under the current working directory are shown relative to it.
    Paths that resolve outside both locations are returned unchanged.
    """
    try:
        resolved = loop_path.resolve()
        builtin_dir = get_builtin_loops_dir().resolve()
        resolved.relative_to(builtin_dir)
        return loop_path.name
    except (ValueError, OSError):
        return _relativize_to_cwd(str(loop_path))


def _artifact_lines(fsm: FSMLoop, loop_path: Path | None) -> list[tuple[str, str]]:
    """Extract path-like context values from *fsm* for display in artifact headers.

    Returns a list of ``(key, value)`` pairs where *value* is a non-empty string
    that starts with ``.``, ``/``, or ``~``, or contains ``/``, and does not
    contain ``${`` (unresolved template expression). When *loop_path* is not
    ``None``, the first entry is always ``("loop", ...)`` where the value is the
    filename for built-in loops or a cwd-relative path for project-level loops.
    Other path-like values (e.g. ``run_dir``) are relativized to the current
    working directory when they live under it.
    """
    pairs: list[tuple[str, str]] = []
    if loop_path is not None:
        pairs.append(("loop", _display_loop_path(loop_path)))
    context: dict[str, Any] = getattr(fsm, "context", None) or {}
    for key, value in context.items():
        if not isinstance(value, str) or not value:
            continue
        if "${" in value:
            continue
        if value.startswith(".") or value.startswith("/") or value.startswith("~") or "/" in value:
            pairs.append((key, _relativize_to_cwd(value)))
    return pairs


def _resolve_input_value(fsm: FSMLoop, show_input: bool) -> str | None:
    """Return the run's ``--input`` string for header display, or ``None``.

    Reads ``fsm.context[fsm.input_key]`` (falling back to the literal
    ``"input"`` key), and returns ``None`` when ``show_input`` is false, the
    value is absent, empty, or not a plain string (e.g. the dict-spread case
    in ``cmd_run`` where no single scalar exists to show).
    """
    if not show_input:
        return None
    context: dict[str, Any] = getattr(fsm, "context", None) or {}
    value = context.get(fsm.input_key)
    if value is None:
        value = context.get("input")
    if not isinstance(value, str) or not value:
        return None
    return value


_EFFORT_CODES = {"low": "L", "medium": "M", "high": "H", "xhigh": "XH", "max": "MX"}


def _effort_code(effort: str) -> str:
    """Abbreviate a reasoning-effort level to its 1-2 letter display code."""
    return _EFFORT_CODES.get(effort.lower(), effort.upper())


def _render_artifact_header_lines(
    fsm: FSMLoop,
    loop_path: Path | None,
    model: str | None,
    input_value: str | None,
    cols: int,
    *,
    effort: str | None = None,
) -> list[str]:
    """Compose the diagram-header artifact lines.

    Packs ``input:`` onto the ``loop:`` row and ``model:`` onto the
    ``run_dir:`` row (falling back to a standalone ``model:`` line when no
    ``run_dir`` context value is present) — ``input`` never separates from
    ``loop`` and ``model`` never separates from ``run_dir``. When ``effort``
    is set (ENH-2869), it's appended directly onto the ``model:`` value —
    no separate label, one space after the model name, abbreviated to a
    1-2 letter code (``model: <model> <CODE>``, e.g. ``L``/``M``/``H``/
    ``XH``/``MX`` for low/medium/high/xhigh/max); when ``effort`` is
    ``None`` the ``model:`` value is unchanged. Adjacent rows are then greedily merged
    onto a single line, front to back, as long as the combined row still fits
    within ``cols`` display columns — so all rows collapse to one line when
    there's room, and only the row(s) that don't fit spill onto subsequent
    lines. Each resulting line is clamped to ``cols`` via
    ``_truncate_to_width_ansi`` as a safety net for a single value too long
    to fit even alone.
    """
    model_display = model if model is None or effort is None else f"{model} {_effort_code(effort)}"

    artifact_pairs = _artifact_lines(fsm, loop_path)
    run_dir_present = any(key == "run_dir" for key, _ in artifact_pairs)
    rows: list[str] = []
    for key, value in artifact_pairs:
        line = f"  {key}: {colorize(value, '2')}"
        if key == "loop" and input_value:
            line += f"  input: {colorize(input_value, '2')}"
        elif key == "run_dir" and model_display is not None:
            line += f"  model: {colorize(model_display, '2')}"
        rows.append(line)
    if model_display is not None and not run_dir_present:
        rows.append(f"  model: {colorize(model_display, '2')}")

    if not rows:
        return []

    merged: list[str] = [rows[0]]
    for row in rows[1:]:
        candidate = f"{merged[-1]}  {row.strip()}"
        if _display_width(candidate) <= cols:
            merged[-1] = candidate
        else:
            merged.append(row)

    return [_truncate_to_width_ansi(line, cols) for line in merged]
