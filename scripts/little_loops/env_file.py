"""Project ``.env`` fallback loading.

Loads ``<project_root>/.env`` into ``os.environ`` as a *fallback*: keys
already present in the real environment are never overridden, so a stale
``.env`` value can't shadow a deliberately exported one. Wired into
``BRConfig.__init__`` so every CLI entry point (``ll-auto``, ``ll-loop``,
``ll-parallel``, ``ll-sprint``, ...) picks it up uniformly and child host-CLI
processes inherit the values.

Motivation: ``claude setup-token`` tells subscription users to set
``CLAUDE_CODE_OAUTH_TOKEN``, and the conventional place is a gitignored
project ``.env`` — which nothing here read before this module, leaving the
``request_path: sdk`` credential probe to silently downgrade to the CLI path.

Deliberately a ~stdlib parser rather than a ``python-dotenv`` dependency
(see the dependency-minimization policy in ``.claude/CLAUDE.md``): supports
comments, blank lines, an optional ``export `` prefix, and single/double
quoted values. No interpolation, multiline values, or escape processing.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_LINE_RE = re.compile(
    r"""^\s*
        (?:export\s+)?
        (?P<key>[A-Za-z_][A-Za-z0-9_]*)
        \s*=\s*
        (?P<value>.*?)
        \s*$""",
    re.VERBOSE,
)


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a ``.env`` file into a dict. Missing/unreadable file → ``{}``.

    Malformed lines (no ``=``, invalid key) are skipped silently — matching
    ``dotenv`` convention, since ``.env`` files are user-managed and a parse
    hard-fail here would break every CLI entry point.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _LINE_RE.match(line)
        if match is None:
            continue
        value = match.group("value")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        result[match.group("key")] = value
    return result


def load_env_fallback(project_root: Path) -> dict[str, str]:
    """Merge ``<project_root>/.env`` into ``os.environ``, env-wins precedence.

    Only keys absent from ``os.environ`` are set (a set-but-empty variable
    counts as present — an explicit ``FOO=`` in the shell is a deliberate
    unset-like signal, not an invitation to backfill). Returns the subset of
    keys actually applied. Idempotent, so repeated ``BRConfig`` constructions
    in one process are harmless.
    """
    applied: dict[str, str] = {}
    for key, value in parse_env_file(project_root / ".env").items():
        if key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied
