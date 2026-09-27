"""Spike: run/state-scoped stall state keying for BUG-3629."""

from __future__ import annotations

import hashlib
from pathlib import Path


def stall_paths(
    state_dir: Path | None, state_name: str, track: list[str], cwd: Path
) -> tuple[Path, Path]:
    """Return (snapshot_file, count_file); fall back to cwd/.loops/tmp when no state_dir."""
    key = hashlib.md5("|".join(sorted(track)).encode()).hexdigest()[:12]
    if state_dir is None:
        base = cwd / ".loops" / "tmp"
        stem = f"ll-action-stall-{key}"
    else:
        base = state_dir
        stem = f"{state_name}-{key}"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{stem}.txt", base / f"{stem}.count"


def check_stall(
    current_hash: str,
    *,
    state_dir: Path | None,
    state_name: str,
    track: list[str],
    max_repeat: int,
    cwd: Path,
) -> tuple[str, int]:
    """Mirror evaluate_action_stall's state machine; returns (verdict, stall_count)."""
    state_file, count_file = stall_paths(state_dir, state_name, track, cwd)
    previous: str | None = None
    count = 0
    try:
        previous = state_file.read_text().strip()
        count = int(count_file.read_text().strip())
    except (FileNotFoundError, ValueError):
        pass
    if previous is None or current_hash != previous:
        state_file.write_text(current_hash)
        count_file.write_text("0")
        return "yes", 0
    count += 1
    count_file.write_text(str(count))
    return ("no" if count >= max_repeat else "yes"), count
