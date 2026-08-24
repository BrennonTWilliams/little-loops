"""Artifact template format: manifest validation + Jinja2 rendering (FEAT-3036).

A ``.llat/`` directory (``manifest.yaml`` + a Jinja2 template body + optional
``assets/``) can be rendered deterministically against a ``data.json`` via
``ll-artifact render``, with zero LLM cost per render. See
``.issues/features/P3-FEAT-3036-artifact-templates-design.md`` for the full
design: this module implements Phase 1 (template format + ``render``) only.

Rendering is a pure function: template + data.json -> artifact. This module
must never import ``host_runner`` or ``anthropic`` — that is Phase 2's
``extract`` concern, never the renderer's (design principle 2).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jinja2 import StrictUndefined, TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment

_MANIFEST_REQUIRED_KEYS = {"name", "version", "renderer", "output", "data_schema"}
_MANIFEST_OPTIONAL_KEYS = {"theme", "source", "extraction"}
_MANIFEST_ALLOWED_KEYS = _MANIFEST_REQUIRED_KEYS | _MANIFEST_OPTIONAL_KEYS

_SCHEMA_ALLOWED_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
_SCHEMA_ALLOWED_KEYS = {"type", "required", "properties", "items", "enum", "description"}

_RESERVED_CONTEXT_KEY = "ll"


class ManifestError(ValueError):
    """Raised when a manifest.yaml (or its template body) fails validation."""


class DataValidationError(ValueError):
    """Raised when data.json fails validation against manifest.data_schema."""


class TemplateResolutionError(ValueError):
    """Raised when ``<template>`` resolves neither as a path nor a named template."""


@dataclass
class ArtifactTemplate:
    """A loaded, validated ``.llat/`` template."""

    root: Path
    manifest: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.manifest["name"])

    @property
    def output(self) -> str:
        return str(self.manifest["output"])

    @property
    def data_schema(self) -> dict[str, Any]:
        return self.manifest["data_schema"]  # type: ignore[no-any-return]


def resolve_template(template_arg: str, templates_dir: Path) -> Path:
    """Resolve ``<template>``: path-first, then ``templates_dir/<name>.llat``.

    Raises TemplateResolutionError naming both paths tried if neither exists.
    """
    path_candidate = Path(template_arg)
    if path_candidate.is_dir():
        return path_candidate
    named_candidate = templates_dir / f"{template_arg}.llat"
    if named_candidate.is_dir():
        return named_candidate
    raise TemplateResolutionError(
        f"template '{template_arg}' not found. Tried: "
        f"{path_candidate} (as a filesystem path), "
        f"{named_candidate} (as a name under templates_dir)"
    )


def _validate_schema_shape(schema: Any, path: str = "data_schema") -> None:
    """Validate a ``data_schema`` node against the documented JSON Schema subset.

    Fails closed: any construct outside {type, required, properties, items,
    enum, description} is a manifest load error, never a silently-unenforced
    key (§ Second-pass decisions -> data.json validation).
    """
    if not isinstance(schema, dict):
        raise ManifestError(f"{path}: expected an object, got {type(schema).__name__}")

    unknown = set(schema.keys()) - _SCHEMA_ALLOWED_KEYS
    if unknown:
        raise ManifestError(
            f"{path}: unsupported construct(s) {sorted(unknown)} — the data_schema "
            "subset supports only: type, required, properties, items, enum, description"
        )

    schema_type = schema.get("type")
    if schema_type is not None and schema_type not in _SCHEMA_ALLOWED_TYPES:
        raise ManifestError(
            f"{path}.type: {schema_type!r} is not one of {sorted(_SCHEMA_ALLOWED_TYPES)}"
        )

    if ("required" in schema or "properties" in schema) and schema_type != "object":
        raise ManifestError(
            f"{path}: 'required'/'properties' are only permitted under type: object"
        )

    if "properties" in schema:
        props = schema["properties"]
        if not isinstance(props, dict):
            raise ManifestError(f"{path}.properties: expected an object")
        for key, sub_schema in props.items():
            _validate_schema_shape(sub_schema, f"{path}.properties.{key}")

    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, list) or not all(isinstance(r, str) for r in required):
            raise ManifestError(f"{path}.required: expected a list of strings")

    if "items" in schema:
        if schema_type != "array":
            raise ManifestError(f"{path}: 'items' is only permitted under type: array")
        items = schema["items"]
        if isinstance(items, list):
            raise ManifestError(f"{path}.items: tuple-form (a list of schemas) is not supported")
        _validate_schema_shape(items, f"{path}.items")

    if "enum" in schema:
        enum_values = schema["enum"]
        if not isinstance(enum_values, list) or not enum_values:
            raise ManifestError(f"{path}.enum: expected a non-empty list of scalars")
        for value in enum_values:
            if isinstance(value, (dict, list)):
                raise ManifestError(f"{path}.enum: values must be scalars")


def load_manifest(root: Path) -> dict[str, Any]:
    """Load and validate ``manifest.yaml`` under *root*.

    Fails closed with ManifestError on: missing file, invalid YAML, unknown
    top-level keys, missing required keys, ``renderer`` != ``jinja2``, an
    invalid ``theme``, a ``data_schema`` construct outside the documented
    subset, or a top-level ``ll`` key in ``data_schema.properties`` (the
    render context's reserved namespace, § Template context).
    """
    manifest_path = root / "manifest.yaml"
    if not manifest_path.is_file():
        raise ManifestError(f"manifest.yaml not found under {root}")

    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ManifestError(f"manifest.yaml: invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ManifestError("manifest.yaml: expected a top-level mapping")

    unknown = set(data.keys()) - _MANIFEST_ALLOWED_KEYS
    if unknown:
        raise ManifestError(f"manifest.yaml: unknown top-level key(s) {sorted(unknown)}")

    missing = _MANIFEST_REQUIRED_KEYS - set(data.keys())
    if missing:
        raise ManifestError(f"manifest.yaml: missing required key(s) {sorted(missing)}")

    if data["renderer"] != "jinja2":
        raise ManifestError(f"manifest.yaml: renderer must be 'jinja2', got {data['renderer']!r}")

    theme = data.get("theme")
    if theme is not None and theme != "design-tokens":
        raise ManifestError(f"manifest.yaml: theme must be 'design-tokens' if set, got {theme!r}")

    _validate_schema_shape(data["data_schema"])

    schema_props = (
        data["data_schema"].get("properties") if isinstance(data["data_schema"], dict) else None
    )
    if isinstance(schema_props, dict) and _RESERVED_CONTEXT_KEY in schema_props:
        raise ManifestError(
            f"manifest.yaml: data_schema declares a top-level '{_RESERVED_CONTEXT_KEY}' key, "
            "which is reserved for the render context"
        )

    return data


def validate_data(data: Any, schema: dict[str, Any], path: str = "data") -> None:
    """Validate *data* against *schema* (the documented subset), recursively."""
    schema_type = schema.get("type")

    if schema_type == "object":
        if not isinstance(data, dict):
            raise DataValidationError(f"{path}: expected object, got {type(data).__name__}")
        for key in schema.get("required", []):
            if key not in data:
                raise DataValidationError(f"{path}: missing required key '{key}'")
        props = schema.get("properties", {})
        for key, value in data.items():
            if key in props:
                validate_data(value, props[key], f"{path}.{key}")
    elif schema_type == "array":
        if not isinstance(data, list):
            raise DataValidationError(f"{path}: expected array, got {type(data).__name__}")
        items_schema = schema.get("items")
        if items_schema is not None:
            for index, item in enumerate(data):
                validate_data(item, items_schema, f"{path}[{index}]")
    elif schema_type == "string":
        if not isinstance(data, str):
            raise DataValidationError(f"{path}: expected string, got {type(data).__name__}")
    elif schema_type == "integer":
        if not isinstance(data, int) or isinstance(data, bool):
            raise DataValidationError(f"{path}: expected integer, got {type(data).__name__}")
    elif schema_type == "number":
        if not isinstance(data, (int, float)) or isinstance(data, bool):
            raise DataValidationError(f"{path}: expected number, got {type(data).__name__}")
    elif schema_type == "boolean":
        if not isinstance(data, bool):
            raise DataValidationError(f"{path}: expected boolean, got {type(data).__name__}")
    elif schema_type == "null":
        if data is not None:
            raise DataValidationError(f"{path}: expected null, got {type(data).__name__}")

    if "enum" in schema and data not in schema["enum"]:
        raise DataValidationError(f"{path}: value {data!r} not in enum {schema['enum']}")


def validate_top_level_data(data: Any, schema: dict[str, Any]) -> None:
    """Validate the top-level ``data.json`` payload, including the reserved-key check."""
    if isinstance(data, dict) and _RESERVED_CONTEXT_KEY in data:
        raise DataValidationError(
            f"data: top-level key '{_RESERVED_CONTEXT_KEY}' is reserved for the render context"
        )
    validate_data(data, schema, "data")


def build_environment() -> SandboxedEnvironment:
    """Construct the frozen Jinja2 environment for FEAT-3036 templates.

    Frozen per § Second-pass decisions -> Delimiter set and render
    determinism contract: not per-template configurable. Changing any of
    these settings is a template-format version bump — it breaks FEAT-3308's
    byte-exact round-trip requirement.
    """
    return SandboxedEnvironment(
        variable_start_string="[[=",
        variable_end_string="=]]",
        block_start_string="[[%",
        block_end_string="%]]",
        comment_start_string="[[#",
        comment_end_string="#]]",
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
        autoescape=False,
    )


def find_template_body(root: Path) -> Path:
    """Find the single ``template.*.j2`` body file under *root*."""
    candidates = sorted(root.glob("template.*.j2"))
    if not candidates:
        raise ManifestError(f"no template.*.j2 body found under {root}")
    if len(candidates) > 1:
        raise ManifestError(
            f"multiple template.*.j2 bodies found under {root}: "
            f"{[c.name for c in candidates]} — exactly one is required"
        )
    return candidates[0]


def load_assets(root: Path) -> dict[str, str]:
    """Read every file under ``assets/`` as UTF-8 text, keyed by relative path.

    Binary assets (data-URI encoding) are out of scope for v1
    (§ Template context).
    """
    assets_dir = root / "assets"
    if not assets_dir.is_dir():
        return {}
    assets: dict[str, str] = {}
    for path in sorted(assets_dir.rglob("*")):
        if path.is_file():
            assets[str(path.relative_to(assets_dir).as_posix())] = path.read_text(encoding="utf-8")
    return assets


def build_ll_namespace(root: Path, manifest: dict[str, Any], config: object) -> dict[str, Any]:
    """Build the reserved ``ll`` render-context namespace (§ Template context)."""
    namespace: dict[str, Any] = {"assets": load_assets(root)}
    if manifest.get("theme") == "design-tokens":
        from little_loops.cli.artifact.policy_builder import _themed_css_vars

        namespace["theme_css"] = _themed_css_vars(config)
    return namespace


def render_template(template: ArtifactTemplate, data: dict[str, Any], config: object) -> str:
    """Render *template* against *data*: a pure function, no LLM call.

    Raises ManifestError on a malformed template body (syntax error, no
    loader available for ``include``/``extends``/``import``), or
    DataValidationError if the render itself hits an undefined name
    (StrictUndefined backstop, § Second-pass decisions).
    """
    from jinja2 import UndefinedError

    body_path = find_template_body(template.root)
    source = body_path.read_text(encoding="utf-8")
    env = build_environment()
    try:
        jinja_template = env.from_string(source)
    except TemplateSyntaxError as exc:
        raise ManifestError(f"{body_path}: {exc}") from exc

    context: dict[str, Any] = dict(data)
    context[_RESERVED_CONTEXT_KEY] = build_ll_namespace(template.root, template.manifest, config)

    try:
        return jinja_template.render(**context)
    except UndefinedError as exc:
        raise DataValidationError(f"{body_path}: {exc}") from exc


def load_data(data_path: Path) -> Any:
    """Read and JSON-parse *data_path*, raising DataValidationError on malformed JSON."""
    try:
        return json.loads(data_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DataValidationError(f"{data_path}: invalid JSON: {exc}") from exc
