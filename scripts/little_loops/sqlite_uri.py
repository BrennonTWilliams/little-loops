"""SQLite ``file:`` URI construction for literal local database paths (BUG-3737).

A filesystem path interpolated into ``file:{path}?mode=ro`` is parsed as URI syntax:
``#`` and ``?`` truncate it (dropping the owned ``mode=`` option, so SQLite falls back to
read-write-create), and ``%XX`` sequences are percent-decoded to a different file. This
module percent-encodes the path instead. Dependency-free and connection-free: it never
stats, opens or creates the database.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

_MODES = ("ro", "rw")


def sqlite_file_uri(path: Path, *, mode: Literal["ro", "rw"] = "ro") -> str:
    """Return a percent-encoded absolute ``file:`` URI selecting exactly *path*.

    *mode* is an internally owned SQLite open mode: ``ro`` (read-only) or ``rw``
    (read-write, never creating a missing file). Anything else, including ``rwc``,
    raises :class:`ValueError`, as does an actual embedded NUL in *path* (encoding it
    would select a decoded-prefix alias). A literal ``%00`` in a filename is valid and
    is encoded as ``%2500``. The path keeps its absolute spelling: symlinks and ``..``
    are not resolved.
    """
    if mode not in _MODES:
        raise ValueError(f"unsupported SQLite URI mode {mode!r}; expected one of {_MODES}")
    path = Path(path)
    if "\x00" in str(path):
        raise ValueError("embedded null character in database path")
    return f"{path.absolute().as_uri()}?mode={mode}"
