"""Shared CLI output utilities: terminal width, text wrapping, and ANSI color."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import textwrap
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from little_loops.config import CliConfig


def terminal_size(default_cols: int = 80, default_rows: int = 24) -> tuple[int, int]:
    """Return ``(cols, rows)`` from ``shutil.get_terminal_size``.

    Use this when layout needs both dimensions (e.g. pinned-pane decisions in
    alt-screen mode). For column-only needs, prefer :func:`terminal_width`.
    """
    size = shutil.get_terminal_size((default_cols, default_rows))
    return size.columns, size.lines


def terminal_width(default: int = 80) -> int:
    """Return the current terminal column width, falling back to *default*."""
    return terminal_size(default_cols=default)[0]


def wrap_text(text: str, indent: str = "  ", width: int | None = None) -> str:
    """Wrap *text* at terminal width with consistent *indent* on every line."""
    w = width or terminal_width()
    return textwrap.fill(text, width=w, initial_indent=indent, subsequent_indent=indent)


# ---------------------------------------------------------------------------
# ANSI escape-sequence stripping
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences from *text* and return plain text."""
    return _ANSI_RE.sub("", text)


# ---------------------------------------------------------------------------
# Box-drawing character constants (Unicode box-drawing set)
# ---------------------------------------------------------------------------

BOX_H = "─"  # ─
BOX_V = "│"  # │
BOX_TL = "┌"  # ┌
BOX_TR = "┐"  # ┐
BOX_BL = "└"  # └
BOX_BR = "┘"  # ┘
BOX_ML = "├"  # ├
BOX_MR = "┤"  # ┤


# ---------------------------------------------------------------------------
# ANSI color helpers — suppressed when NO_COLOR=1 or stdout is not a TTY
# ---------------------------------------------------------------------------

_USE_COLOR: bool = os.environ.get("FORCE_COLOR", "") == "1" or (
    sys.stdout.isatty() and os.environ.get("NO_COLOR", "") == ""
)

PRIORITY_COLOR: dict[str, str] = {
    "P0": "38;5;208;1",
    "P1": "38;5;208",
    "P2": "33",
    "P3": "0",
    "P4": "2",
    "P5": "2",
}
TYPE_COLOR: dict[str, str] = {
    "BUG": "38;5;208",
    "FEAT": "32",
    "ENH": "34",
    "EPIC": "35",
}

# ENH-2539: per-category color map for ``ll-loop list`` headers. Slugs are
# _smart_title() output (``"Apo"`` becomes ``"apo"`` slug in CATEGORY_COLOR;
# see ``_smart_title`` for the reverse direction).
CATEGORY_COLOR: dict[str, str] = {
    "apo": "38;5;141",
    "code-quality": "32",
    "data": "34",
    "evaluation": "38;5;208",
    "example": "33;2",
    "gate": "38;5;160",
    "harness": "35",
    "integration": "38;5;39",
    "issue-management": "36",
    "lib": "90",
    "meta": "38;5;208",
    "optimization": "33",
    "orchestration": "38;5;141",
    "planning": "38;5;39",
    "quality": "32",
    "research": "36",
    "rl": "38;5;160",
    "routing": "35",
    "uncategorized": "0;2",
    "api-adoption": "33",
}

# ENH-2539: per-label color map for ``ll-loop list`` rows. Used by
# ``_render_labels`` in cli/loop/info.py.
LABEL_COLOR: dict[str, str] = {
    "hitl": "36",
    "comparison": "35",
    "generated": "33",
    "meta": "38;5;208",
}

# ENH-2539: acronyms preserved by ``_smart_title`` for category and subgroup
# subhead rendering. Keep entries UPPER-CASE.
ACRONYMS: frozenset[str] = frozenset({"APO", "HITL", "LLM", "SVG", "FSM", "RLHF", "API"})


def _smart_title(slug: str) -> str:
    """Title-case a slug (``"issue-management"`` -> ``"Issue Management"``)
    while preserving known acronyms (``"apo"`` -> ``"APO"``)."""
    parts = slug.replace("-", " ").split()
    return " ".join(p.upper() if p.upper() in ACRONYMS else p.capitalize() for p in parts)


def configure_output(config: CliConfig | None = None) -> None:
    """Apply CLI color configuration to module-level color state.

    Call this once at startup after loading BRConfig. Updates _USE_COLOR,
    PRIORITY_COLOR, TYPE_COLOR, CATEGORY_COLOR, and LABEL_COLOR based on
    config and NO_COLOR env var.

    Args:
        config: CliConfig from BRConfig.cli, or None for defaults.
    """
    global _USE_COLOR, PRIORITY_COLOR, TYPE_COLOR, CATEGORY_COLOR, LABEL_COLOR

    # NO_COLOR env var always takes precedence (industry convention)
    no_color_env = os.environ.get("NO_COLOR", "") != ""

    # FORCE_COLOR=1 forces color even when stdout is not a TTY
    force_color = os.environ.get("FORCE_COLOR", "") == "1"

    if config is None:
        _USE_COLOR = not no_color_env and (force_color or sys.stdout.isatty())
        return

    _USE_COLOR = config.color and not no_color_env and (force_color or sys.stdout.isatty())

    # Merge custom priority colors
    PRIORITY_COLOR.update(
        {
            "P0": config.colors.priority.P0,
            "P1": config.colors.priority.P1,
            "P2": config.colors.priority.P2,
            "P3": config.colors.priority.P3,
            "P4": config.colors.priority.P4,
            "P5": config.colors.priority.P5,
        }
    )

    # Merge custom type colors
    TYPE_COLOR.update(
        {
            "BUG": config.colors.type.BUG,
            "FEAT": config.colors.type.FEAT,
            "ENH": config.colors.type.ENH,
            "EPIC": config.colors.type.EPIC,
        }
    )


def use_color_enabled() -> bool:
    """Return the current module-level color state set by configure_output()."""
    return _USE_COLOR


def colorize(text: str, code: str) -> str:
    """Wrap *text* in the given ANSI escape *code*, or return it unchanged."""
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def print_json(data: Any) -> None:
    """Print *data* as formatted JSON to stdout."""
    print(json.dumps(data, indent=2))


def format_relative_time(seconds: float) -> str:
    """Format seconds as a human-readable relative time string (e.g., '3m ago')."""
    total = int(seconds)
    if total < 60:
        return f"{total}s ago"
    if total < 3600:
        m, s = divmod(total, 60)
        return f"{m}m ago" if s == 0 else f"{m}m {s}s ago"
    if total < 86400:
        h, rem = divmod(total, 3600)
        m = rem // 60
        return f"{h}h ago" if m == 0 else f"{h}h {m}m ago"
    d, rem = divmod(total, 86400)
    h = rem // 3600
    return f"{d}d ago" if h == 0 else f"{d}d {h}h ago"


# ---------------------------------------------------------------------------
# User-facing message helpers — simple, untimestamped, icon-prefixed.
# Distinguished from Logger (logger.py) by: no timestamps, direct stdout/stderr,
# icons only when color is enabled.
# ---------------------------------------------------------------------------

_ICONS: dict[str, str] = {
    "success": "✓",  # ✓
    "error": "✗",  # ✗
    "warning": "⚠",  # ⚠
    "info": "ℹ",  # ℹ
    "hint": "›",  # ›
}


def success(msg: str) -> None:
    """Print a success message to stdout."""
    icon = f"{_ICONS['success']} " if _USE_COLOR else ""
    print(f"{colorize(icon + msg, '32')}", flush=True)


def error(msg: str) -> None:
    """Print an error message to stderr."""
    icon = f"{_ICONS['error']} " if _USE_COLOR else ""
    print(f"{colorize(icon + msg, '38;5;208')}", file=sys.stderr, flush=True)


def warning(msg: str) -> None:
    """Print a warning message to stdout."""
    icon = f"{_ICONS['warning']} " if _USE_COLOR else ""
    print(f"{colorize(icon + msg, '33')}", flush=True)


def info(msg: str) -> None:
    """Print an informational message to stdout."""
    icon = f"{_ICONS['info']} " if _USE_COLOR else ""
    print(f"{colorize(icon + msg, '36')}", flush=True)


def hint(msg: str) -> None:
    """Print a hint / dim message to stdout."""
    icon = f"{_ICONS['hint']} " if _USE_COLOR else ""
    print(f"{colorize(icon + msg, '2')}", flush=True)


# ---------------------------------------------------------------------------
# Structured formatters — pure string-returning helpers
# ---------------------------------------------------------------------------


def table(headers: list[str], rows: list[list[str]], max_col_width: int = 40) -> str:
    """Return an auto-width box-drawn table string.

    Column widths are the lesser of *max_col_width* and the longest value
    in each column. Values exceeding *max_col_width* are truncated.
    """
    if not headers:
        return ""

    ncols = len(headers)
    all_cells = [headers] + rows

    col_widths: list[int] = [0] * ncols
    for row in all_cells:
        for i, cell in enumerate(row):
            if i < ncols:
                col_widths[i] = max(col_widths[i], len(cell))

    col_widths = [max(3, min(w, max_col_width)) for w in col_widths]

    def _cell(text: str, width: int) -> str:
        if len(text) <= width:
            return text.ljust(width)
        return text[: width - 1] + "…"

    def _sep(left: str, mid: str, right: str) -> str:
        parts = [BOX_H * w for w in col_widths]
        return left + mid.join(parts) + right

    lines: list[str] = []
    lines.append(_sep(BOX_TL, "┬", BOX_TR))
    lines.append(
        BOX_V + BOX_V.join(_cell(h, w) for h, w in zip(headers, col_widths, strict=True)) + BOX_V
    )
    lines.append(_sep(BOX_ML, "┼", BOX_MR))

    for row in rows:
        padded = []
        for i in range(ncols):
            val = row[i] if i < len(row) else ""
            padded.append(_cell(val, col_widths[i]))
        lines.append(BOX_V + BOX_V.join(padded) + BOX_V)

    lines.append(_sep(BOX_BL, "┴", BOX_BR))

    return "\n".join(lines)


def status_block(items: dict[str, str]) -> str:
    """Return aligned key-value pairs.

    Keys are right-padded so values align. Returns empty string for an empty dict.
    """
    if not items:
        return ""

    max_key = max(len(k) for k in items)
    lines: list[str] = []
    for key, value in items.items():
        lines.append(f"{key.ljust(max_key)}: {value}")
    return "\n".join(lines)


def progress(current: int, total: int, width: int = 20) -> str:
    """Return a ``|####`` |`` progress bar of *width* columns."""
    if width < 3:
        width = 3
    inner = width - 2

    if total <= 0:
        filled = 0
    else:
        filled = max(0, min(inner, round(inner * current / total)))

    return "|" + "#" * filled + " " * (inner - filled) + "|"


def sparkline(current: int, total: int, width: int = 16) -> str:
    """Return a Unicode block-character progress bar of *width* characters."""
    if width < 1:
        width = 1
    if total <= 0:
        filled = 0
    else:
        filled = max(0, min(width, round(width * current / total)))
    return "█" * filled + "░" * (width - filled)


# ---------------------------------------------------------------------------
# Output mode toggling
# ---------------------------------------------------------------------------

_OUTPUT_MODE: Literal["human", "json", "plain"] = "human"


def set_output_mode(mode: Literal["human", "json", "plain"]) -> None:
    """Set the global output mode for all formatters."""
    global _OUTPUT_MODE
    _OUTPUT_MODE = mode


def get_output_mode() -> Literal["human", "json", "plain"]:
    """Return the current global output mode."""
    return _OUTPUT_MODE
