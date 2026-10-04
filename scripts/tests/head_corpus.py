"""Read the committed ``.issues`` corpus at ``HEAD`` instead of the working tree (ENH-3697).

Repo-wide corpus ratchets (``test_prose_dep_sweep_gate``) read the live ``.issues/``
tree, so another session's uncommitted edits can turn the ``code-run-gate`` red even
though ``main`` is clean. Under ``LL_CORPUS_GATE_AT_HEAD`` the sweep reads committed
blobs instead. Blobs are read in one ``git cat-file --batch`` pass — nothing is
exported to disk, so the gate creates no files.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from little_loops.config.core import BRConfig
from little_loops.issue_parser import IssueInfo, IssueParser

CORPUS_GATE_ENV = "LL_CORPUS_GATE_AT_HEAD"

_FALSY = {"", "0", "false", "no", "off"}


def corpus_gate_at_head() -> bool:
    """True when ``LL_CORPUS_GATE_AT_HEAD`` is set to a truthy value."""
    return os.environ.get(CORPUS_GATE_ENV, "").strip().lower() not in _FALSY


def _git(repo_root: Path, *args: str, stdin: bytes | None = None) -> bytes | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            input=stdin,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def head_issue_blobs(config: BRConfig) -> dict[str, bytes] | None:
    """Return ``{repo-relative path: content}`` for every tracked issue file at HEAD.

    Covers each category directory's ``*.md`` files. Returns ``None`` when there is no
    usable ``HEAD`` (not a git repo, empty repo, git unavailable) so callers can fall
    back to the working tree.
    """
    root = config.project_root
    if _git(root, "rev-parse", "--verify", "-q", "HEAD^{commit}") is None:
        return None

    dirs: list[str] = []
    for cat in config.issue_categories:
        try:
            dirs.append(config.get_issue_dir(cat).relative_to(root).as_posix())
        except ValueError:
            continue
    if not dirs:
        return {}

    listing = _git(root, "ls-tree", "-r", "-z", "--name-only", "HEAD", "--", *dirs)
    if listing is None:
        return None
    paths = [
        p.decode("utf-8")
        for p in listing.split(b"\0")
        if p.endswith(b".md") and p.decode("utf-8").rsplit("/", 1)[0] in dirs
    ]
    if not paths:
        return {}

    request = b"".join(f"HEAD:{p}\n".encode() for p in paths)
    out = _git(root, "cat-file", "--batch", stdin=request)
    if out is None:
        return None

    blobs: dict[str, bytes] = {}
    pos = 0
    for p in paths:
        eol = out.index(b"\n", pos)
        header = out[pos:eol].split()
        if len(header) != 3 or header[1] != b"blob":
            return None
        size = int(header[2])
        blobs[p] = out[eol + 1 : eol + 1 + size]
        pos = eol + 1 + size + 1
    return blobs


class BlobPath:
    """Duck-typed ``Path`` whose content comes from a HEAD blob.

    Carries the real working-tree path and delegates everything except
    ``read_text``/``read_bytes`` to it: the gate walks ``resolve()``/``parent``/
    ``parents`` (``find_project_root``, ``_warn_deprecated_key``,
    ``IssueParser._parse_type_and_id``), so a bare name+content pair is not enough.
    """

    def __init__(self, path: Path, content: bytes) -> None:
        self._path = path
        self._content = content

    def read_bytes(self) -> bytes:
        return self._content

    def read_text(self, encoding: str | None = None, errors: str | None = None) -> str:
        return self._content.decode(encoding or "utf-8", errors or "strict")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._path, name)

    def __fspath__(self) -> str:
        return os.fspath(self._path)

    def __str__(self) -> str:
        return str(self._path)

    def __repr__(self) -> str:
        return f"BlobPath({self._path!r})"


class HeadIssueParser(IssueParser):
    """``IssueParser`` that serves committed blobs for ``BlobPath`` arguments."""

    def _read_content(self, issue_path: Path) -> str:
        if isinstance(issue_path, BlobPath):
            return issue_path.read_text(encoding="utf-8")
        return super()._read_content(issue_path)


def head_issue_infos(config: BRConfig, blobs: dict[str, bytes]) -> list[tuple[IssueInfo, BlobPath]]:
    """Parse every HEAD blob into ``(IssueInfo, BlobPath)`` pairs, sorted by path."""
    parser = HeadIssueParser(config)
    pairs: list[tuple[IssueInfo, BlobPath]] = []
    for rel in sorted(blobs):
        blob_path = BlobPath(config.project_root / rel, blobs[rel])
        pairs.append((parser.parse_file(blob_path), blob_path))  # type: ignore[arg-type]
    return pairs
