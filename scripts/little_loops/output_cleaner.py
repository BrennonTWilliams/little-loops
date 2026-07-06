"""Anti-event + duplicate-window pre-filter for tool/log output (FEAT-2470).

LogCleaner-style pre-filter (EPIC-2456 technique [25]) that trims two kinds of
avoidable token cost from tool and log output *before* it enters the model's
context window:

- **Anti-events** — lines that carry no signal: progress bars (tqdm / ascii),
  spinner frames, pytest-xdist worker chatter, and bare carriage-return redraws.
  These are dropped outright.
- **Duplicate windows** — runs of consecutive identical lines (a stack trace or
  warning repeated N times) are collapsed to a single line plus a
  ``… (repeated N×)`` marker.

Follows the module-level compiled-``re.Pattern`` constant style of
``little_loops.text_utils`` (banner-grouped ``_NAME_RE`` constants) and the
single-regex ANSI-strip precedent in ``little_loops.cli.output.strip_ansi``.
The public entry point is :func:`filter_output`.
"""

from __future__ import annotations

import re

# --- ANSI / carriage-return normalization -------------------------------------
# CSI escape sequences (colors, cursor moves) — stripped before matching so an
# anti-event line wrapped in color codes still matches.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

# --- Anti-event line patterns (dropped outright) ------------------------------
# Each matches an entire line (after ANSI strip + rstrip) that is pure progress
# noise. Kept tight to avoid eating real content.
_ANTI_EVENT_RES: tuple[re.Pattern[str], ...] = (
    # tqdm-style: " 42%|████████  | 3/7 [00:01<00:02]"
    re.compile(r"^\s*\d{1,3}%\|.*\|.*$"),
    # ascii progress bar: "[====>      ] 40%" or "[####........]"
    re.compile(r"^\s*\[[#=>.\- ]{4,}\]\s*\d{0,3}%?\s*$"),
    # braille / ascii spinner frames: "⠋ working" or "| Loading"
    re.compile(r"^\s*[⠀-⣿]\s.*$"),
    # pytest-xdist bring-up + worker status chatter
    re.compile(r"^\s*bringing up nodes\.\.\.\s*$"),
    re.compile(r"^\s*gw\d+\s+\[.*\]\s*$"),
    re.compile(r"^\s*\[gw\d+\].*$"),
)


def _is_anti_event(line: str) -> bool:
    return any(pat.match(line) for pat in _ANTI_EVENT_RES)


def filter_output(raw: str, *, dup_threshold: int = 1) -> str:
    """Strip anti-event noise and collapse duplicate windows from ``raw``.

    Args:
        raw: Raw tool/log output.
        dup_threshold: Emit a ``… (repeated N×)`` marker once a line has
            repeated more than this many times consecutively. The default of 1
            collapses any run of ≥2 identical lines to a single line + marker.

    Returns:
        The cleaned text. Trailing newline presence is preserved from ``raw``.
    """
    if not raw:
        return raw

    trailing_nl = raw.endswith("\n")
    lines = raw.split("\n")

    kept: list[str] = []
    prev: str | None = None
    run = 0

    def _flush() -> None:
        # Close out a finished run of duplicate lines. The first occurrence is
        # already in ``kept``; collapse to a marker only past the threshold,
        # otherwise restore the remaining literal copies.
        if prev is None:
            return
        if run > dup_threshold:
            indent = prev[: len(prev) - len(prev.lstrip())]
            kept.append(f"{indent}… (repeated {run}×)")
        elif run > 1:
            kept.extend([prev] * (run - 1))

    for original in lines:
        line = _ANSI_RE.sub("", original).rstrip()
        if _is_anti_event(line):
            continue
        if line == "":
            # Blank lines are collapsed to a single blank, and always break a
            # duplicate run (they never carry a "repeated N×" marker).
            _flush()
            prev = None
            run = 0
            if not kept or kept[-1] == "":
                continue
            kept.append("")
            continue
        if line == prev:
            run += 1
            continue
        _flush()
        kept.append(line)
        prev = line
        run = 1

    _flush()

    result = "\n".join(kept)
    if trailing_nl and not result.endswith("\n"):
        result += "\n"
    return result
