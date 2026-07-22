"""Config building for headless ll-init."""

from __future__ import annotations

import importlib.resources
import json
from functools import lru_cache
from typing import Any

from little_loops.init.detect import TemplateMatch

SCHEMA_URL = (
    "https://raw.githubusercontent.com/BrennonTWilliams/little-loops/"
    "main/scripts/little_loops/config-schema.json"
)

_ANALYTICS_CAPTURE_KEYS = (
    "skills",
    "cli_commands",
    "corrections",
    "file_events",
    "usage_events",
    "hooks",
)


@lru_cache(maxsize=1)
def _load_schema() -> dict[str, Any]:
    """Load and cache the bundled config-schema.json.

    Reads via importlib.resources so the file ships inside the wheel and works
    in non-editable installs (the previous implementation walked out of the
    package via a parent-traversal that only resolved in editable installs).
    """
    traversable = importlib.resources.files("little_loops").joinpath("config-schema.json")
    return json.loads(traversable.read_text(encoding="utf-8"))


def schema_default(dotted_path: str) -> Any:
    """Return config-schema.json's declared ``default`` for a dotted property path.

    Walks ``properties.<part>`` for each segment of *dotted_path*, the same
    dotted-walk shape as ``little_loops.config.features.feature_enabled`` but
    over the JSON Schema tree instead of a config dict. Raises ``KeyError`` if
    the path or its ``default`` is missing — a schema/``build_config`` drift
    should fail loud rather than silently fall back to a stale literal.
    """
    node: dict[str, Any] = _load_schema()
    for part in dotted_path.split("."):
        properties = node.get("properties", {})
        if part not in properties:
            raise KeyError(
                f"config-schema.json has no property at {dotted_path!r} (missing {part!r})"
            )
        node = properties[part]
    if "default" not in node:
        raise KeyError(f"config-schema.json property {dotted_path!r} declares no default")
    return node["default"]


def strip_none_leaves(config: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of *config* with all ``None``-valued leaves removed.

    ``config.core.deep_merge`` treats a ``None`` in the override as a key-removal
    sentinel (BUG-2310). ``build_config`` emitted ``None`` leaves (e.g.
    ``loops.run_defaults.mode``, ``project.build_cmd``) and the TUI emitted
    ``project.<cmd>`` ``None`` for cleared fields; merging those over an existing
    config would silently delete the user's corresponding keys. Stripping them
    from generated output makes the merge additive (fix for BUG-2311).

    Nested dicts are recursed; every other value type passes through unchanged.
    """
    result: dict[str, Any] = {}
    for key, value in config.items():
        if value is None:
            continue
        if isinstance(value, dict):
            result[key] = strip_none_leaves(value)
        else:
            result[key] = value
    return result


def build_config(
    template: TemplateMatch,
    choices: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the output ll-config.json dict from a template and optional choices.

    Ports the skill's Step 4 and Step 8 config-building logic. The resulting
    dict is ready for serialisation with ``atomic_write_json``.

    Args:
        template: Matched template from detect_project_type().
        choices: Optional overrides. Booleans/values not listed here fall back to
            config-schema.json's declared ``default`` for the matching dotted path
            (see ``schema_default``) rather than a literal baked into this function.
            Recognised keys:
            - ``project_name`` (str): value written to project.name.
            - ``src_dir`` (str): override project.src_dir.
            - ``test_cmd`` / ``lint_cmd`` / ``format_cmd`` / ``type_cmd`` (str):
              override the matching project.* command.
            - ``scan_focus_dirs`` (list[str]): override scan.focus_dirs.
            - ``product_enabled`` (bool): include product section.
            - ``analytics_enabled`` (bool): include analytics section.
            - ``context_monitor_enabled`` (bool): include context_monitor.
            - ``learning_tests_enabled`` (bool): include learning_tests.
            - ``decisions_enabled`` (bool, default False): include decisions section.
            - ``scratch_pad_enabled`` (bool, default False): include scratch_pad section.
            - ``session_capture_enabled`` (bool, default False): include session_capture.
            - ``prompt_optimization_enabled`` (bool): when False, write
              prompt_optimization.enabled=false (opt-out of a default-on feature).
            - ``loop_clear_default`` (bool): write loops.run_defaults.clear.
            - ``loop_show_diagrams_default`` (str | None): write loops.run_defaults.show_diagrams.

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
    if choices.get("test_cmd"):
        project["test_cmd"] = choices["test_cmd"]
    if choices.get("lint_cmd"):
        project["lint_cmd"] = choices["lint_cmd"]
    if choices.get("format_cmd"):
        project["format_cmd"] = choices["format_cmd"]
    if choices.get("type_cmd"):
        project["type_cmd"] = choices["type_cmd"]
    config["project"] = project

    # --- issues ---
    config["issues"] = dict(data.get("issues", {}))

    # --- scan ---
    scan: dict[str, Any] = dict(data.get("scan", {}))
    if choices.get("scan_focus_dirs"):
        scan["focus_dirs"] = choices["scan_focus_dirs"]
    config["scan"] = scan

    # --- learning_tests (always written) ---
    learning_tests_enabled = bool(
        choices.get("learning_tests_enabled", schema_default("learning_tests.enabled"))
    )
    config["learning_tests"] = {"enabled": learning_tests_enabled}

    # --- analytics (always written) ---
    analytics_enabled = bool(choices.get("analytics_enabled", schema_default("analytics.enabled")))
    if analytics_enabled:
        config["analytics"] = {
            "enabled": True,
            "capture": {
                key: schema_default(f"analytics.capture.{key}") for key in _ANALYTICS_CAPTURE_KEYS
            },
        }
    else:
        config["analytics"] = {"enabled": False}

    # --- context_monitor (omit if disabled) ---
    context_monitor_enabled = bool(
        choices.get("context_monitor_enabled", schema_default("context_monitor.enabled"))
    )
    if context_monitor_enabled:
        config["context_monitor"] = {"enabled": True}

    # --- product (omit if disabled) ---
    product_enabled = bool(choices.get("product_enabled", schema_default("product.enabled")))
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
    prompt_optimization_enabled = choices.get(
        "prompt_optimization_enabled", schema_default("prompt_optimization.enabled")
    )
    if prompt_optimization_enabled is False:
        config["prompt_optimization"] = {"enabled": False}

    # --- history.session_digest (always written) ---
    session_digest_enabled = bool(
        choices.get("session_digest_enabled", schema_default("history.session_digest.enabled"))
    )
    config["history"] = {
        "session_digest": {
            "enabled": session_digest_enabled,
            "days": schema_default("history.session_digest.days"),
        }
    }

    # --- loops.run_defaults (always written; exposes the feature at init time) ---
    loop_clear = bool(choices.get("loop_clear_default", schema_default("loops.run_defaults.clear")))
    loop_show_diagrams = choices.get(
        "loop_show_diagrams_default", schema_default("loops.run_defaults.show_diagrams")
    )
    config["loops"] = {
        "run_defaults": {
            "clear": loop_clear,
            "show_diagrams": loop_show_diagrams,
        }
    }

    return strip_none_leaves(config)
