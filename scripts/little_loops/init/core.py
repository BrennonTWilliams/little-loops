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


def schema_enum(dotted_path: str) -> list[str]:
    """Return config-schema.json's declared ``enum`` for a dotted property path.

    Same dotted walk as :func:`schema_default`. Raises ``KeyError`` when the
    path or its ``enum`` is missing.
    """
    node: dict[str, Any] = _load_schema()
    for part in dotted_path.split("."):
        properties = node.get("properties", {})
        if part not in properties:
            raise KeyError(
                f"config-schema.json has no property at {dotted_path!r} (missing {part!r})"
            )
        node = properties[part]
    if "enum" not in node:
        raise KeyError(f"config-schema.json property {dotted_path!r} declares no enum")
    return list(node["enum"])


# Feature keys toggleable via ``--enable``/``--disable`` and the wizard's
# feature checkbox. Each maps to a ``{name}_enabled`` choice key honored by
# :func:`build_config`. Lives here (not in cli.py) so the TUI and the
# proposal layer can share it without importing argparse wiring.
_TOGGLEABLE_FEATURES: frozenset[str] = frozenset(
    {
        "product",
        "analytics",
        "context_monitor",
        "learning_tests",
        "decisions",
        "scratch_pad",
        "session_capture",
        "session_digest",
        "prompt_optimization",
        "parallel",
        "documents",
        "design_tokens",
        "sync",
        "confidence_gate",
        "tdd",
    }
)

# Features a fresh init turns on beyond the schema defaults. This is the ONE
# place both the headless path and the wizard read their first-run feature
# set from, so ``ll-init --yes`` and an accepted wizard run write the same
# config. Everything else stays at its config-schema.json default.
RECOMMENDED_FEATURES: frozenset[str] = frozenset({"context_monitor"})


def _schema_default_or(dotted_path: str, fallback: Any) -> Any:
    try:
        return schema_default(dotted_path)
    except KeyError:
        return fallback


def existing_feature_choices(existing: dict[str, Any]) -> dict[str, bool]:
    """Derive ``{feature}_enabled`` choices from an existing ll-config.json.

    Absent sections resolve to the config-schema.json default — never a
    literal ``True`` — so re-running ``ll-init`` over a config that omits
    ``product``/``learning_tests`` does not silently switch them on (the
    pre-fix headless path used ``.get("enabled", True)`` and flipped
    default-off features on every re-run). Section-presence rules mirror the
    wizard's pre-check logic: ``parallel`` has no ``enabled`` key (presence is
    the signal), ``design_tokens`` defaults to enabled within a present
    section (BUG-3274), and the nested ``sync`` / ``commands.*`` /
    ``history.session_digest`` keys map to their flat feature names.
    """
    choices: dict[str, bool] = {}
    for section in (
        "product",
        "analytics",
        "context_monitor",
        "learning_tests",
        "decisions",
        "scratch_pad",
        "session_capture",
        "prompt_optimization",
    ):
        block = existing.get(section)
        default = bool(_schema_default_or(f"{section}.enabled", False))
        if isinstance(block, dict):
            choices[f"{section}_enabled"] = bool(block.get("enabled", default))
        else:
            choices[f"{section}_enabled"] = default

    # documents is tri-state in build_config (None = "write it only when
    # docs were detected"), so an absent section must leave the key unset.
    documents = existing.get("documents")
    if isinstance(documents, dict):
        choices["documents_enabled"] = bool(
            documents.get("enabled", _schema_default_or("documents.enabled", False))
        )

    parallel = existing.get("parallel")
    choices["parallel_enabled"] = isinstance(parallel, dict)

    design_tokens = existing.get("design_tokens")
    if isinstance(design_tokens, dict):
        choices["design_tokens_enabled"] = bool(
            design_tokens.get("enabled", _schema_default_or("design_tokens.enabled", True))
        )
    else:
        choices["design_tokens_enabled"] = False

    sync = existing.get("sync")
    choices["sync_enabled"] = bool(
        sync.get("enabled", _schema_default_or("sync.enabled", False))
        if isinstance(sync, dict)
        else _schema_default_or("sync.enabled", False)
    )

    commands_raw = existing.get("commands")
    commands: dict[str, Any] = commands_raw if isinstance(commands_raw, dict) else {}
    gate = commands.get("confidence_gate")
    choices["confidence_gate_enabled"] = bool(
        gate.get("enabled", _schema_default_or("commands.confidence_gate.enabled", False))
        if isinstance(gate, dict)
        else _schema_default_or("commands.confidence_gate.enabled", False)
    )
    choices["tdd_enabled"] = bool(
        commands.get("tdd_mode", _schema_default_or("commands.tdd_mode", False))
    )

    history_raw = existing.get("history")
    history: dict[str, Any] = history_raw if isinstance(history_raw, dict) else {}
    digest = history.get("session_digest")
    choices["session_digest_enabled"] = bool(
        digest.get("enabled", _schema_default_or("history.session_digest.enabled", True))
        if isinstance(digest, dict)
        else _schema_default_or("history.session_digest.enabled", True)
    )
    return choices


# Choice keys whose build_config output carries sub-config (thresholds,
# profile names, worker counts, categories). On a re-init these must NOT be
# re-emitted from the existing config: build_config would write schema
# defaults over the user's tuned values (readiness_threshold 91 -> 85,
# design_tokens.active "warm-paper" -> "default"). The existing section
# survives verbatim through merge_with_existing instead.
SUBCONFIG_FEATURE_CHOICES: frozenset[str] = frozenset(
    {"parallel_enabled", "documents_enabled", "design_tokens_enabled", "confidence_gate_enabled"}
)


def reinit_feature_choices(existing: dict[str, Any]) -> dict[str, bool]:
    """Feature choices for re-running init over *existing*.

    :func:`existing_feature_choices` minus :data:`SUBCONFIG_FEATURE_CHOICES`,
    so flag-only sections round-trip through build_config while sub-config
    sections are preserved by the merge rather than rebuilt from defaults.
    """
    return {
        key: value
        for key, value in existing_feature_choices(existing).items()
        if key not in SUBCONFIG_FEATURE_CHOICES
    }


def recommended_feature_choices() -> dict[str, bool]:
    """Feature choices for a fresh init: schema defaults + :data:`RECOMMENDED_FEATURES`.

    Built by running :func:`existing_feature_choices` over an empty config
    (so every feature resolves to its schema default) and then overlaying
    the recommended set. Shared by ``ll-init --yes`` and the wizard's
    pre-checked feature list.
    """
    choices = existing_feature_choices({})
    for feature in RECOMMENDED_FEATURES:
        choices[f"{feature}_enabled"] = True
    return choices


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

    Default precedence: config-schema.json is the single source of truth for
    feature defaults (via ``schema_default``); templates contribute only
    project-type *structure* (commands, scan focus/excludes, issue
    categories). A template block that disagrees with a schema default is a
    template bug, not an override.

    Args:
        template: Matched template from detect_project_type().
        choices: Optional overrides. Booleans/values not listed here fall back to
            config-schema.json's declared ``default`` for the matching dotted path
            (see ``schema_default``) rather than a literal baked into this function.
            Recognised keys:
            - ``project_name`` (str): value written to project.name.
            - ``src_dir`` (str): override project.src_dir.
            - ``test_cmd`` / ``lint_cmd`` / ``format_cmd`` / ``type_cmd`` /
              ``build_cmd`` (str): override the matching project.* command.
            - ``scan_focus_dirs`` (list[str]): override scan.focus_dirs.
            - ``product_enabled`` (bool): include product section.
            - ``analytics_enabled`` (bool): include analytics section.
            - ``context_monitor_enabled`` (bool): include context_monitor.
            - ``learning_tests_enabled`` (bool): include learning_tests.
            - ``decisions_enabled`` (bool, default False): include decisions section.
            - ``scratch_pad_enabled`` (bool, default False): include scratch_pad section.
            - ``session_capture_enabled`` (bool, default False): include session_capture.
            - ``prompt_optimization_enabled`` (bool, default False): when True,
              write prompt_optimization.enabled=true (opt-in to a default-off
              feature).
            - ``loop_clear_default`` (bool): write loops.run_defaults.clear.
            - ``loop_show_diagrams_default`` (str | None): write loops.run_defaults.show_diagrams.
            - ``parallel_enabled`` (bool, opt-in): write a parallel section so
              headless init matches what the TUI writes when parallel is selected.
            - ``documents_enabled`` (bool | None): tri-state. True always writes
              the documents section; False omits it; None (default) writes it
              only when ``documents_categories`` detected something.
            - ``documents_categories`` (dict): detected document categories to
              attach when the documents section is written.
            - ``design_tokens_enabled`` (bool, opt-in): write design_tokens with
              the schema-default profile.
            - ``sync_enabled`` (bool, opt-in): write sync.enabled=true.
            - ``confidence_gate_enabled`` (bool, opt-in): write
              commands.confidence_gate with schema-default thresholds.
            - ``tdd_enabled`` (bool, opt-in): write commands.tdd_mode=true.
            - ``code_query_enabled`` (bool, opt-in): write code_query.provider
              (schema default ``auto``) so ll-code prefers the codegraph index.

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
    if choices.get("test_dir"):
        project["test_dir"] = choices["test_dir"]
    if choices.get("test_cmd"):
        project["test_cmd"] = choices["test_cmd"]
    if choices.get("lint_cmd"):
        project["lint_cmd"] = choices["lint_cmd"]
    if choices.get("format_cmd"):
        project["format_cmd"] = choices["format_cmd"]
    if choices.get("type_cmd"):
        project["type_cmd"] = choices["type_cmd"]
    if choices.get("build_cmd"):
        project["build_cmd"] = choices["build_cmd"]
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

    # --- prompt_optimization (default-off; only write when opting in) ---
    prompt_optimization_enabled = choices.get(
        "prompt_optimization_enabled", schema_default("prompt_optimization.enabled")
    )
    if prompt_optimization_enabled is True:
        config["prompt_optimization"] = {"enabled": True}

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

    # --- parallel (opt-in; carries the template's stamped defaults) ---
    # ARCHITECTURE-096 mandates the parallel stamp in every project-type
    # template so init-using projects see the same defaults as config-file
    # users; carrying the block here is what makes that stamp live (the
    # headless path previously dropped it — audit M-2).
    if choices.get("parallel_enabled"):
        config["parallel"] = dict(data.get("parallel", {}))

    # --- documents (opt-in or auto-detected categories) ---
    documents_choice = choices.get("documents_enabled")
    documents_categories = choices.get("documents_categories") or {}
    if documents_choice is True or (documents_choice is None and documents_categories):
        doc_section: dict[str, Any] = {"enabled": True}
        if documents_categories:
            doc_section["categories"] = documents_categories
        config["documents"] = doc_section

    # --- design_tokens (opt-in; schema-default profile) ---
    if choices.get("design_tokens_enabled"):
        config["design_tokens"] = {
            "enabled": True,
            "active": schema_default("design_tokens.active"),
        }

    # --- sync (opt-in) ---
    if choices.get("sync_enabled"):
        config["sync"] = {"enabled": True}

    # --- code_query (written once a codegraph index exists / was built) ---
    if choices.get("code_query_enabled"):
        config["code_query"] = {"provider": schema_default("code_query.provider")}

    # --- commands block (confidence_gate + tdd_mode; opt-in each) ---
    commands: dict[str, Any] = {}
    if choices.get("confidence_gate_enabled"):
        commands["confidence_gate"] = {
            "enabled": True,
            "readiness_threshold": schema_default("commands.confidence_gate.readiness_threshold"),
            "outcome_threshold": schema_default("commands.confidence_gate.outcome_threshold"),
        }
    if choices.get("tdd_enabled"):
        commands["tdd_mode"] = True
    if commands:
        config["commands"] = commands

    return strip_none_leaves(config)
