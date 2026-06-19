"""PostToolUse install-nudge gate for Bash tool calls (ENH-2212).

When a Bash command contains a package-manager install invocation (pip, uv,
poetry, npm, yarn, pnpm), extracts the package name, queries the Learning Test
Registry, and emits a nudge via ``/ll:explore-api`` if no proven record exists
or the existing record is stale.

Gated behind ``learning_tests.enabled`` in ``.ll/ll-config.json``.  When
disabled (default), the handler is a no-op — no registry I/O occurs.

Supported install commands:
    pip install <pkg>    pip3 install <pkg>
    uv add <pkg>         poetry add <pkg>
    npm install <pkg>    yarn add <pkg>    pnpm add <pkg>

Out of scope (silently skipped):
    pip install -r requirements.txt  (flag-prefixed, no single package name)
    Transitive or bulk installs      (only the first explicit package token)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from little_loops.config.core import resolve_config_path
from little_loops.config.features import LearningTestsConfig
from little_loops.hooks.types import LLHookEvent, LLHookResult
from little_loops.learning_tests import check_learning_test
from little_loops.learning_tests.gate import format_nudge_message, is_record_stale

# Matches pip/pip3/uv/poetry/npm/yarn/pnpm install/add followed by the first
# non-flag package token.  The negative lookahead (?!-) rejects flag tokens
# like -r, --save-dev, etc., causing the whole match to fail when the first
# argument is a flag (e.g. pip install -r requirements.txt → no match).
_INSTALL_RE = re.compile(
    r"\b(?:pip3?\s+install|uv\s+add|poetry\s+add|npm\s+install|yarn\s+add|pnpm\s+add)"
    r"\s+((?!-)\S+)",
    re.IGNORECASE,
)

# Session-level cache: normalized package name → True (proven+fresh) / False.
# Avoids repeated registry reads when the same package is installed multiple
# times in one session.
_SESSION_CACHE: dict[str, bool] = {}


def _load_lt_config(cwd: Path) -> LearningTestsConfig:
    """Load LearningTestsConfig from project config, returning defaults on miss."""
    config_path = resolve_config_path(cwd)
    if config_path is None:
        return LearningTestsConfig()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LearningTestsConfig()
    if not isinstance(data, dict):
        return LearningTestsConfig()
    return LearningTestsConfig.from_dict(data.get("learning_tests", {}))


def _normalize_pkg(raw: str) -> str | None:
    """Normalize a raw package token from the install command.

    Strips surrounding quotes, extras (``[...]``), and version specifiers
    (``>=``, ``==``, ``~=``, ``!=``, ``<=``, ``<``, ``>``).  Returns ``None``
    for flags (``-r``, ``--requirement``), empty strings, or tokens that
    resolve to empty after stripping.
    """
    if not raw:
        return None
    # Flags (should be filtered by regex, but defensive)
    if raw.startswith("-"):
        return None
    # Strip surrounding quotes
    raw = raw.strip("\"'")
    if not raw or raw.startswith("-"):
        return None
    # Strip extras: anthropic[bedrock] → anthropic
    raw = re.sub(r"\[.*?\]", "", raw)
    # Strip version specifiers: requests>=2.0 → requests
    raw = re.sub(r"[><=!~][^\s]*$", "", raw)
    raw = raw.strip()
    return raw if raw else None


def gate(event: LLHookEvent) -> LLHookResult:
    """Check Bash install commands against the Learning Test Registry.

    Returns a nudge (exit_code=0, feedback=...) when the installed package has
    no proven record or the existing record is stale.  Silent pass otherwise.
    """
    cwd = Path(event.cwd) if event.cwd else Path.cwd()
    lt_config = _load_lt_config(cwd)

    if not lt_config.enabled:
        return LLHookResult(exit_code=0)

    payload = event.payload or {}
    tool_input = payload.get("tool_input", {}) or {}
    cmd = tool_input.get("command") or ""

    m = _INSTALL_RE.search(cmd)
    if not m:
        return LLHookResult(exit_code=0)

    pkg = _normalize_pkg(m.group(1))
    if not pkg:
        return LLHookResult(exit_code=0)

    # Session cache hit
    if pkg in _SESSION_CACHE:
        if _SESSION_CACHE[pkg]:
            return LLHookResult(exit_code=0)
        return LLHookResult(exit_code=0, feedback=format_nudge_message(pkg, stale=False))

    base_dir = cwd / ".ll" / "learning-tests"
    record = check_learning_test(pkg, base_dir=base_dir)

    if record is not None and record.status == "proven":
        if is_record_stale(record, lt_config.stale_after_days):
            _SESSION_CACHE[pkg] = False
            return LLHookResult(exit_code=0, feedback=format_nudge_message(pkg, stale=True))
        _SESSION_CACHE[pkg] = True
        return LLHookResult(exit_code=0)

    _SESSION_CACHE[pkg] = False
    return LLHookResult(exit_code=0, feedback=format_nudge_message(pkg, stale=False))
