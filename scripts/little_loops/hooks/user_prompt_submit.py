"""UserPromptSubmit hook handler: auto-prompt optimization.

Python port of ``hooks/scripts/user-prompt-check.sh`` (FEAT-1482). The
``handle`` function is invoked by the dispatcher in
``little_loops.hooks.__init__::main_hooks`` after the Codex adapter
(``hooks/adapters/codex/prompt-submit.sh``) reads the host's stdin payload.

Applies bypass guards (slash commands, *, #, ?, short prompts) then
renders ``hooks/prompts/optimize-prompt-hook.md`` with
``prompt_optimization.*`` config values substituted. Returns the rendered
template via ``LLHookResult.stdout`` so the host injects it as
``additionalContext`` alongside the user's original prompt.

Config path is resolved via :func:`little_loops.config.core.resolve_config_path`,
which probes ``.codex/ll-config.json`` first when ``LL_HOOK_HOST=codex``.
"""

from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path
from typing import Any

from little_loops.config.core import resolve_config_path
from little_loops.config.features import AnalyticsCaptureConfig, feature_enabled
from little_loops.hooks.types import LLHookEvent, LLHookResult
from little_loops.session_store import is_correction, record_correction, record_skill_event

_NO_CONFIG_MSG = (
    "[little-loops] No config found. Run /ll:init to set up little-loops for this project."
)

# Navigate from this file up to the plugin root, then into hooks/prompts/.
# Path: scripts/little_loops/hooks/user_prompt_submit.py → parents[3] = repo root.
_PROMPT_FILE = Path(__file__).resolve().parents[3] / "hooks" / "prompts" / "optimize-prompt-hook.md"

_MIN_PROMPT_LENGTH = 10


def _load_config(cwd: Path) -> dict[str, Any] | None:
    config_path = resolve_config_path(cwd)
    if config_path is None:
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def handle(event: LLHookEvent) -> LLHookResult:
    """Apply prompt optimization if enabled; return rendered template on stdout.

    Mirrors the bypass-guard logic of ``user-prompt-check.sh`` and uses
    ``resolve_config_path()`` for host-aware config lookup (probes
    ``.codex/ll-config.json`` first when ``LL_HOOK_HOST=codex``).
    """
    user_prompt = event.payload.get("prompt", "")
    if not isinstance(user_prompt, str):
        user_prompt = ""

    if not user_prompt.strip():
        return LLHookResult(exit_code=0)

    cwd = Path.cwd()
    config = _load_config(cwd)

    if config is not None and feature_enabled(config, "analytics.enabled"):
        capture = AnalyticsCaptureConfig.from_dict(config.get("analytics", {}).get("capture", {}))
        if is_correction(user_prompt, extra_patterns=capture.correction_patterns):
            if capture.corrections:
                session_id = event.payload.get("session_id") or event.session_id
                with contextlib.suppress(Exception):
                    record_correction(
                        cwd / ".ll" / "history.db", session_id, user_prompt, "user_prompt_submit"
                    )
        # TODO(ENH-1835): wire analytics.capture.cli_commands gate when ENH-1834 lands
        m = re.match(r"^/ll:([a-z][a-z0-9-]*)(.*)", user_prompt.strip(), re.DOTALL)
        if m:
            session_id = event.payload.get("session_id") or event.session_id
            with contextlib.suppress(Exception):
                record_skill_event(
                    cwd / ".ll" / "history.db", session_id, m.group(1), m.group(2).strip()[:200]
                )

    if config is None:
        return LLHookResult(exit_code=0, stdout=_NO_CONFIG_MSG + "\n")

    raw_opt = config.get("prompt_optimization", {})
    prompt_opt: dict[str, Any] = raw_opt if isinstance(raw_opt, dict) else {}

    if not prompt_opt.get("enabled", False):
        return LLHookResult(exit_code=0)

    mode = str(prompt_opt.get("mode", "quick"))
    confirm = str(prompt_opt.get("confirm", "true"))
    bypass_prefix = str(prompt_opt.get("bypass_prefix", "*"))

    # Bypass guards (mirrors user-prompt-check.sh order)
    if bypass_prefix and user_prompt.startswith(bypass_prefix):
        return LLHookResult(exit_code=0)
    if user_prompt.startswith("/"):
        return LLHookResult(exit_code=0)
    if user_prompt.startswith("#"):
        return LLHookResult(exit_code=0)
    if user_prompt.startswith("?"):
        return LLHookResult(exit_code=0)
    if len(user_prompt) < _MIN_PROMPT_LENGTH:
        return LLHookResult(exit_code=0)

    if not _PROMPT_FILE.is_file():
        return LLHookResult(exit_code=0)

    try:
        template = _PROMPT_FILE.read_text(encoding="utf-8")
    except OSError:
        return LLHookResult(exit_code=0)

    rendered = (
        template.replace("{{USER_PROMPT}}", user_prompt)
        .replace("{{MODE}}", mode)
        .replace("{{CONFIRM}}", confirm)
    )
    return LLHookResult(exit_code=0, stdout=rendered)
