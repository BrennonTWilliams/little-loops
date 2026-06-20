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
            - ``decisions_enabled`` (bool, default False): include decisions section.
            - ``scratch_pad_enabled`` (bool, default False): include scratch_pad section.
            - ``session_capture_enabled`` (bool, default False): include session_capture.
            - ``prompt_optimization_enabled`` (bool, default True): when False, write
              prompt_optimization.enabled=false (opt-out of a default-on feature).
            - ``loop_clear_default`` (bool, default True): write loops.run_defaults.clear.
            - ``loop_show_diagrams_default`` (str | None, default "clean"): write loops.run_defaults.show_diagrams.

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

    # --- decisions (opt-in; omit if disabled) ---
    if choices.get("decisions_enabled"):
        config["decisions"] = {"enabled": True}

    # --- scratch_pad (opt-in; omit if disabled) ---
    if choices.get("scratch_pad_enabled"):
        config["scratch_pad"] = {"enabled": True}

    # --- session_capture (opt-in; omit if disabled) ---
    if choices.get("session_capture_enabled"):
        config["session_capture"] = {"enabled": True}

    # --- prompt_optimization (default-on; only write when opting out) ---
    if choices.get("prompt_optimization_enabled", True) is False:
        config["prompt_optimization"] = {"enabled": False}

    # --- history.session_digest (always written) ---
    session_digest_enabled = bool(choices.get("session_digest_enabled", True))
    config["history"] = {
        "session_digest": {
            "enabled": session_digest_enabled,
            "days": 7,
            "char_cap": 1200,
        }
    }

    # --- loops.run_defaults (always written; exposes the feature at init time) ---
    loop_clear = bool(choices.get("loop_clear_default", True))
    loop_show_diagrams = choices.get("loop_show_diagrams_default", "clean")
    config["loops"] = {
        "run_defaults": {
            "clear": loop_clear,
            "show_diagrams": loop_show_diagrams,
            "mode": None,
        }
    }

    return config
