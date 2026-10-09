"""Shared fixtures/helpers for the FEAT-3561 ``ll-next`` arena tests.

Phase B introduced these; later phases (candidates, selection, CLI) reuse them:

* :func:`make_project` / :func:`write_issue` build a tiny on-disk project.
* :func:`issue_text` renders frontmatter plus a body.
* :func:`assert_resolver_parity` is the emitted-operand check: for a unique-number source,
  the real ``issue_parser.resolve_issue_path`` result for the emitted ID must be the
  assessed source path.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.config import BRConfig
from little_loops.issue_parser import resolve_issue_path
from little_loops.next_arena.state import (
    ProjectState,
    SourceRecord,
    collect_project_state,
    supported_source,
)

AS_OF = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)

CATEGORY_DIRS = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements", "EPIC": "epics"}


def make_project(root: Path, *, config: Mapping[str, Any] | None = None) -> Path:
    """Create ``.ll/`` (+ optional config) and the empty category dirs under *root*."""
    (root / ".ll").mkdir(parents=True, exist_ok=True)
    if config is not None:
        (root / ".ll" / "ll-config.json").write_text(json.dumps(config), encoding="utf-8")
    for dirname in CATEGORY_DIRS.values():
        (root / ".issues" / dirname).mkdir(parents=True, exist_ok=True)
    return root


def issue_text(
    frontmatter: Mapping[str, Any] | None = None,
    body: str = "# Title\n\n## Summary\n\nText.\n",
) -> str:
    """Render a markdown issue: a frontmatter block (scalars/lists) followed by *body*."""
    lines: list[str] = []
    if frontmatter is not None:
        lines.append("---")
        for key, value in frontmatter.items():
            if isinstance(value, (list, tuple)):
                if not value:
                    lines.append(f"{key}: []")
                else:
                    lines.append(f"{key}:")
                    lines.extend(f"- {item}" for item in value)
            elif value is None:
                lines.append(f"{key}:")
            else:
                lines.append(f"{key}: {value}")
        lines.append("---")
        lines.append("")
    return "\n".join(lines) + body


def write_issue(
    root: Path,
    relpath: str,
    frontmatter: Mapping[str, Any] | None = None,
    body: str = "# Title\n\n## Summary\n\nText.\n",
    *,
    text: str | None = None,
) -> Path:
    """Write ``root/.issues/<relpath>`` (parents created) and return the path."""
    path = root / ".issues" / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text is not None else issue_text(frontmatter, body), encoding="utf-8")
    return path


def collect(root: Path, **kwargs: Any) -> ProjectState:
    """``collect_project_state`` with the shared fixed clock."""
    kwargs.setdefault("as_of", AS_OF)
    return collect_project_state(root, **kwargs)


def record(state: ProjectState, relpath: str) -> SourceRecord:
    """The record for ``.issues/<relpath>``."""
    found = state.record_for_path(f".issues/{relpath}")
    assert found is not None, f"no record for {relpath}"
    return found


def assert_resolver_parity(state: ProjectState, issue_id: str) -> Path:
    """Assert the real resolver maps *issue_id* to the assessed (unique, supported) source.

    This is the emitted-operand check: ``manage-issue``/refinement commands resolve their
    operand through ``resolve_issue_path``; it must land on the path the arena assessed.
    Returns the resolved path.
    """
    source = supported_source(state, issue_id)
    assert source is not None, f"{issue_id} has no unique supported source"
    resolved = resolve_issue_path(_config(state), issue_id)
    assert resolved is not None, f"resolver found nothing for {issue_id}"
    assert resolved.resolve() == source.path.resolve(), (
        f"resolver chose {resolved} but the arena assessed {source.path}"
    )
    return resolved


def _config(state: ProjectState) -> BRConfig:
    return state.config


def memory_state(
    root: Path,
    files: Mapping[str, str],
    *,
    config: BRConfig | None = None,
    counter: Any = None,
) -> ProjectState:
    """Build a :class:`ProjectState` from in-memory ``{relpath-under-.issues: text}`` files.

    Creates no files (the path ``root/.issues/<relpath>`` never has to exist), so scaled
    fixtures never hit the filesystem. *root* only needs to be a resolvable directory for
    ``BRConfig`` when *config* is omitted.
    """
    from little_loops.next_arena.inputs import FormattingPolicy, Thresholds
    from little_loops.next_arena.state import build_project_state, build_source_record

    cfg = config or BRConfig(root)
    records = [
        build_source_record(
            root / ".issues" / rel, text, project_root=root, config=cfg, category=None
        )
        for rel, text in files.items()
    ]
    return build_project_state(
        records,
        project_root=root,
        as_of=AS_OF,
        config=cfg,
        formatting_policy=FormattingPolicy({}, {}, None),
        thresholds=Thresholds(85, 65, False),
        counter=counter,
    )


# --------------------------------------------------------------------- schema validation


def schema_errors(instance: Any, schema: Mapping[str, Any], root: Mapping[str, Any]) -> list[str]:
    """Validate *instance* against the JSON Schema subset the ``ll-next`` schema uses.

    ``jsonschema`` is not a repo dependency, so this small walker covers exactly the keywords
    ``render.build_output_schema`` emits: ``$ref`` (``#/$defs/...``), ``type`` (string or
    list), ``enum``, ``const``, ``required``, ``properties``, ``additionalProperties``
    (bool or schema), ``propertyNames`` (enum), ``items``, ``oneOf``, ``anyOf``, ``minimum``,
    ``maximum``, ``minLength`` and ``pattern``. Returns a list of ``path: message`` strings
    (empty when valid). An unknown keyword fails loudly so the walker cannot silently go stale.
    """
    return _walk(instance, schema, root, "$")


_KNOWN_KEYWORDS = {
    "$ref", "$schema", "$id", "$defs", "title", "description", "type", "enum", "const",
    "required", "properties", "additionalProperties", "propertyNames", "items", "oneOf",
    "anyOf", "minimum", "maximum", "minLength", "pattern",
}  # fmt: skip


def _type_ok(value: Any, name: str) -> bool:
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, dict)
    raise AssertionError(f"walker does not know type {name!r}")


def _walk(value: Any, schema: Mapping[str, Any], root: Mapping[str, Any], path: str) -> list[str]:
    import re

    unknown = set(schema) - _KNOWN_KEYWORDS
    assert not unknown, f"schema walker does not support keywords {sorted(unknown)} at {path}"
    if "$ref" in schema:
        target: Any = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return _walk(value, target, root, path)
    errors: list[str] = []
    if "const" in schema and (
        value != schema["const"] or isinstance(value, bool) != isinstance(schema["const"], bool)
    ):
        errors.append(f"{path}: expected const {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in enum")
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(value, n) for n in names):
            return [*errors, f"{path}: expected type {names}, got {type(value).__name__}"]
    if "oneOf" in schema:
        matches = [b for b in schema["oneOf"] if not _walk(value, b, root, path)]
        if len(matches) != 1:
            errors.append(f"{path}: matched {len(matches)} oneOf branches (need exactly 1)")
    if "anyOf" in schema and not any(not _walk(value, b, root, path) for b in schema["anyOf"]):
        errors.append(f"{path}: matched no anyOf branch")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} does not match {schema['pattern']!r}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} > maximum {schema['maximum']}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            errors.extend(_walk(item, schema["items"], root, f"{path}[{index}]"))
    if isinstance(value, dict):
        for key in schema.get("required", ()):
            if key not in value:
                errors.append(f"{path}: missing required {key!r}")
        properties = schema.get("properties", {})
        for key, item in value.items():
            if "propertyNames" in schema and key not in schema["propertyNames"].get("enum", [key]):
                errors.append(f"{path}: property name {key!r} not allowed")
            if key in properties:
                errors.extend(_walk(item, properties[key], root, f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected property {key!r}")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(_walk(item, schema["additionalProperties"], root, f"{path}.{key}"))
    return errors
