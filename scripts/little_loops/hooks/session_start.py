"""SessionStart hook handler: load config + apply ``.ll/ll.local.md`` overrides.

Python port of ``hooks/scripts/session-start.sh`` (FEAT-1450). The ``handle``
function is invoked by the dispatcher in
``little_loops.hooks.__init__::main_hooks`` after the Claude Code adapter
(``hooks/adapters/claude-code/session-start.sh``) reads the host's stdin
payload.

Observable side-effects preserved from the bash version:

1. Removes ``.ll/ll-context-state.json`` from the prior session (best-effort).
2. Resolves the project config via :func:`little_loops.config.core.resolve_config_path`.
3. If ``.ll/ll.local.md`` exists, parses its YAML frontmatter with
   ``yaml.safe_load`` and deep-merges it into the base config — arrays
   replace, explicit ``None`` removes keys.
4. Emits the rendered config JSON via ``LLHookResult.stdout`` so Claude Code
   ingests it as session context.
5. Composes stderr feedback covering the ``Config loaded`` line, the optional
   ``Local overrides applied`` line, a ``Warning: Large config`` line when the
   rendered config exceeds 5000 chars, the ``Warning: No config found`` line
   when neither candidate exists, and feature-flag validation warnings for
   ``sync.enabled`` / ``documents.enabled``.

The bash version had a stdout/stderr inconsistency for the no-config warning;
this port chooses stderr in both branches (per the issue's Step-resolved
decision).
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

import yaml

from little_loops.config.core import deep_merge, resolve_config_path
from little_loops.hooks.types import LLHookEvent, LLHookResult

_LOCAL_OVERRIDE_FILE = Path(".ll/ll.local.md")
_PRIOR_SESSION_STATE = Path(".ll/ll-context-state.json")
_LARGE_CONFIG_THRESHOLD = 5000


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter (arbitrary nested shapes) from a markdown doc.

    Mirrors the bash version's behaviour: returns ``{}`` for any malformed or
    missing frontmatter, and uses ``yaml.safe_load`` so nested dicts / lists /
    explicit nulls survive. Not interchangeable with
    ``little_loops.frontmatter.parse_frontmatter`` (which is a key:value subset
    parser) — local-override frontmatter needs full YAML.
    """
    if not content or not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    text = parts[1].strip()
    if not text:
        return {}
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def handle(event: LLHookEvent) -> LLHookResult:
    """Build the merged session-start config and validate feature flags.

    Returns ``LLHookResult(exit_code=0, feedback=<stderr>, stdout=<config-json>)``.
    """
    del event  # SessionStart consumes no payload fields today; cwd is implicit (os.getcwd()).

    cwd = Path.cwd()
    feedback_lines: list[str] = []

    # 1. Clean up prior-session state (best-effort, suppress all errors).
    with contextlib.suppress(OSError):
        _PRIOR_SESSION_STATE.unlink()

    # 2. Resolve base config.
    config_path = resolve_config_path(cwd)
    base_config: dict[str, Any] = {}
    if config_path is not None:
        try:
            base_config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            base_config = {}

    # 3. Apply local overrides if present.
    local_file = cwd / _LOCAL_OVERRIDE_FILE
    overrides_applied = False
    merged_config: dict[str, Any] = base_config
    if local_file.is_file():
        try:
            override_text = local_file.read_text(encoding="utf-8")
        except OSError:
            override_text = ""
        local_overrides = _parse_frontmatter(override_text)
        if local_overrides:
            merged_config = deep_merge(base_config, local_overrides)
            overrides_applied = True

    # 4. Compose the rendered stdout payload.
    if config_path is not None and not overrides_applied:
        # Match bash: preserve original on-disk formatting when no overrides.
        try:
            stdout_payload: str | None = config_path.read_text(encoding="utf-8")
        except OSError:
            stdout_payload = json.dumps(merged_config, indent=2)
    elif config_path is not None or overrides_applied:
        stdout_payload = json.dumps(merged_config, indent=2)
    else:
        stdout_payload = None

    # 5. Compose feedback (stderr).
    if config_path is not None:
        # Match bash output format: print() uses a space separator, not a colon-space.
        feedback_lines.append(f"[little-loops] Config loaded: {config_path}")
        if overrides_applied:
            feedback_lines.append(f"[little-loops] Local overrides applied from: {local_file}")
        if stdout_payload is not None and len(stdout_payload) > _LARGE_CONFIG_THRESHOLD:
            feedback_lines.append(
                f"[little-loops] Warning: Large config ({len(stdout_payload)} chars)"
            )
    else:
        feedback_lines.append(
            "[little-loops] Warning: No config found. Run /ll:init to create one."
        )

    # 6. Feature-flag validation warnings.
    feedback_lines.extend(_validate_features(merged_config))

    feedback = "\n".join(feedback_lines) if feedback_lines else None
    return LLHookResult(exit_code=0, feedback=feedback, stdout=stdout_payload)


def _validate_features(config: dict[str, Any]) -> list[str]:
    """Return stderr warning lines for misconfigured enabled features.

    Mirrors ``validate_enabled_features`` in the bash version exactly:

    - ``sync.enabled: true`` with empty ``sync.github`` → warn.
    - ``documents.enabled: true`` with empty ``documents.categories`` → warn.

    Other ``*.enabled`` flags (e.g. ``product.enabled``) are intentionally not
    validated — the existing ``TestSessionStartValidation`` test fixture
    enables ``product`` and asserts no ``Warning:`` substring appears.
    """
    warnings_out: list[str] = []
    sync = config.get("sync") if isinstance(config.get("sync"), dict) else {}
    if isinstance(sync, dict) and sync.get("enabled") is True:
        github = sync.get("github")
        if not isinstance(github, dict) or not github:
            warnings_out.append(
                "[little-loops] Warning: sync.enabled is true but sync.github is not configured"
            )
    documents = config.get("documents") if isinstance(config.get("documents"), dict) else {}
    if isinstance(documents, dict) and documents.get("enabled") is True:
        categories = documents.get("categories")
        if not isinstance(categories, dict) or not categories:
            warnings_out.append(
                "[little-loops] Warning: documents.enabled is true but no document categories"
                " configured"
            )
    return warnings_out
