"""Learning-test discoverability gate for PreToolUse (FEAT-1742).

When the host is about to execute a Write or Edit tool call, parses the
file content for external package imports, queries the Learning Test
Registry for each package, and emits a nudge when an import has no
proven record and discoverability is enabled.

Config keys read from ``.ll/ll-config.json``:
- ``learning_tests.enabled`` (bool, default False) — master switch.
- ``learning_tests.discoverability.mode`` (str, default "warn") —
  ``"off"`` silences all hints; ``"warn"`` emits a hint and allows the
  tool call; ``"block"`` injects feedback into model context and blocks.
- ``learning_tests.discoverability.skip_packages`` (list[str]) —
  packages that are never flagged (stdlib, type stubs, etc.).
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from little_loops.config.core import resolve_config_path
from little_loops.config.features import LearningTestsConfig
from little_loops.hooks.types import LLHookEvent, LLHookResult
from little_loops.learning_tests import check_learning_test
from little_loops.learning_tests.gate import is_record_stale
from little_loops.learning_tests.import_scan import _PY_IMPORT_RE

_JS_REQUIRE_RE = re.compile(r"""require\s*\(\s*['"]([^./'"][^'"]*)['"]\s*\)""")
_JS_IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*import\s+(?:.*?\s+from\s+)?['"]([^./'"][^'"]+)['"]""", re.MULTILINE
)

_BUILTIN_SKIP: frozenset[str] = frozenset(
    {"__future__", "__builtins__", "typing_extensions", "abc", "io", "re", "json"}
)

# Session-level cache: package name → True (proven) / False (no record or refuted/stale).
# Avoids repeated registry lookups for the same package within a session.
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


def _extract_packages(content: str, file_path: str) -> list[str]:
    """Extract unique top-level package names from file content."""
    seen: set[str] = set()
    pkgs: list[str] = []
    is_js = file_path.endswith((".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"))

    if is_js:
        candidates: list[str] = []
        for m in _JS_REQUIRE_RE.finditer(content):
            candidates.append(m.group(1))
        for m in _JS_IMPORT_RE.finditer(content):
            candidates.append(m.group(1))
        for raw in candidates:
            pkg = raw if raw.startswith("@") else raw.split("/")[0]
            if pkg and pkg not in seen:
                seen.add(pkg)
                pkgs.append(pkg)
    else:
        for m in _PY_IMPORT_RE.finditer(content):
            pkg = m.group(1)
            if pkg not in seen:
                seen.add(pkg)
                pkgs.append(pkg)

    return pkgs


def gate(event: LLHookEvent) -> LLHookResult:
    """Check file imports against the Learning Test Registry and nudge on gaps."""
    cwd = Path(event.cwd) if event.cwd else Path.cwd()
    lt_config = _load_lt_config(cwd)

    if not lt_config.enabled:
        return LLHookResult(exit_code=0)

    disc = lt_config.discoverability
    if disc.mode == "off":
        return LLHookResult(exit_code=0)

    payload = event.payload
    tool_name = payload.get("tool_name", "")
    tool_input: dict = payload.get("tool_input", {}) or {}

    if tool_name == "Write":
        content = tool_input.get("content", "") or ""
        file_path = tool_input.get("file_path", "") or ""
    elif tool_name == "Edit":
        content = tool_input.get("new_string", "") or ""
        file_path = tool_input.get("file_path", "") or ""
    else:
        return LLHookResult(exit_code=0)

    if not content:
        return LLHookResult(exit_code=0)

    skip = set(disc.skip_packages) | _BUILTIN_SKIP
    packages = _extract_packages(content, file_path)
    base_dir = cwd / ".ll" / "learning-tests"

    missing: list[str] = []
    stale_ages: dict[str, int] = {}  # pkg -> age in days, for stale proven records
    for pkg in packages:
        if pkg in skip:
            continue
        if pkg in _SESSION_CACHE:
            if not _SESSION_CACHE[pkg]:
                missing.append(pkg)
            continue
        record = check_learning_test(pkg, base_dir=base_dir)
        if record is not None and record.status == "proven":
            if is_record_stale(record, lt_config.stale_after_days):
                _SESSION_CACHE[pkg] = False
                try:
                    age = (datetime.date.today() - datetime.date.fromisoformat(record.date)).days
                    stale_ages[pkg] = age
                except (ValueError, TypeError):
                    pass
                missing.append(pkg)
            else:
                _SESSION_CACHE[pkg] = True
        else:
            proven = record is not None and record.status == "proven"
            _SESSION_CACHE[pkg] = proven
            if not proven:
                missing.append(pkg)

    if not missing:
        return LLHookResult(exit_code=0)

    parts = []
    for pkg in missing:
        if pkg in stale_ages:
            parts.append(f'"{pkg}" (stale: {stale_ages[pkg]} days old)')
        else:
            parts.append(f'"{pkg}"')
    pkg_list = ", ".join(parts)
    hint = (
        f"[ll: proof-first hint] No learning-test record found for {pkg_list}. "
        f"You're about to write integration code based on training-data assumptions. "
        f'Consider: ll-loop run proof-first-task --context task="<your task>"'
    )

    if disc.mode == "block":
        return LLHookResult(exit_code=2, feedback=hint)
    return LLHookResult(exit_code=0, feedback=hint)
