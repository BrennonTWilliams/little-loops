"""Config building for headless ll-init."""

from __future__ import annotations

from typing import Any

from little_loops.init.detect import TemplateMatch

SCHEMA_URL = (
    "https://raw.githubusercontent.com/BrennonTWilliams/little-loops/main/config-schema.json"
)

_DEFAULT_ANALYTICS_CAPTURE: dict[str, Any] = {
    "skills": ["*"],
    "cli_commands": ["*"],
    "corrections": True,
    "file_events": True,
}


def build_config(
    template: TemplateMatch,
    choices: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the output ll-config.json dict from a template and optional choices.

    Ports the skill's Step 4 and Step 8 config-building logic. The resulting
    dict is ready for serialisation with ``atomic_write_json``.

    Args:
        template: Matched template from detect_project_type().
        choices: Optional overrides. Recognised keys:
            - ``project_name`` (str): value written to project.name.
            - ``src_dir`` (str): override project.src_dir.
            - ``product_enabled`` (bool, default True): include product section.
            - ``analytics_enabled`` (bool, default True): include analytics section.
            - ``context_monitor_enabled`` (bool, default True): include context_monitor.
            - ``learning_tests_enabled`` (bool, default True): include learning_tests.

    Returns:
        Complete config dict (``$schema`` key first, then sections).
    """
    choices = choices or {}
    data = template.data

    config: dict[str, Any] = {"$schema": SCHEMA_URL}

    # --- project ---
    project: dict[str, Any] = dict(data.get("project", {}))
    if choices.get("project_name"):
        project["name"] = choices["project_name"]
    if choices.get("src_dir"):
        project["src_dir"] = choices["src_dir"]
    config["project"] = project

    # --- issues ---
    config["issues"] = dict(data.get("issues", {}))

    # --- scan ---
    config["scan"] = dict(data.get("scan", {}))

    # --- learning_tests (always written) ---
    learning_tests_enabled = bool(choices.get("learning_tests_enabled", True))
    config["learning_tests"] = {"enabled": learning_tests_enabled}

    # --- analytics (always written) ---
    analytics_enabled = bool(choices.get("analytics_enabled", True))
    if analytics_enabled:
        config["analytics"] = {
            "enabled": True,
            "capture": dict(_DEFAULT_ANALYTICS_CAPTURE),
        }
    else:
        config["analytics"] = {"enabled": False}

    # --- context_monitor (omit if disabled) ---
    context_monitor_enabled = bool(choices.get("context_monitor_enabled", True))
    if context_monitor_enabled:
        config["context_monitor"] = {"enabled": True}

    # --- product (omit if disabled; default True for --yes mode) ---
    product_enabled = bool(choices.get("product_enabled", True))
    if product_enabled:
        config["product"] = {"enabled": True}

    # --- history.session_digest (always written) ---
    session_digest_enabled = bool(choices.get("session_digest_enabled", True))
    config["history"] = {
        "session_digest": {
            "enabled": session_digest_enabled,
            "days": 7,
            "char_cap": 1200,
        }
    }

    return config
