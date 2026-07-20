"""Manifest-declared command + src_dir detection with provenance (FEAT-2703).

Reads what a repo *declares* about its own tooling and layout — manifest tool
tables, script entries, and package-layout markers — instead of trusting
template literals. Every derived value carries a provenance tag
(``declared`` / ``inferred`` / ``default``) so callers can distinguish
verified facts from unverified template defaults.

Design principle: read declarations, don't guess. A value is tagged
``declared``/``inferred`` only when the repo unambiguously states it;
otherwise it stays the template default, tagged ``default``.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from little_loops.init.detect import TemplateMatch

Provenance = Literal["declared", "inferred", "default"]

_SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".ll",
    ".issues",
    "__pycache__",
}

_COMMAND_FIELDS = ("test_cmd", "lint_cmd", "format_cmd", "type_cmd")


@dataclass(frozen=True)
class IntrospectedValue:
    """A single derived value with its provenance and supporting evidence."""

    value: str | list[str]
    provenance: Provenance
    evidence: str = ""


@dataclass(frozen=True)
class Ambiguity:
    """Multiple equally-valid candidates found for *field*; none was adopted."""

    field: str
    candidates: list[str]
    note: str = ""


@dataclass(frozen=True)
class IntrospectResult:
    """Full introspection output: resolved values plus unresolved ambiguities."""

    values: dict[str, IntrospectedValue]
    ambiguities: list[Ambiguity]


def introspect(root: Path, template: TemplateMatch) -> IntrospectResult:
    """Derive project.{test,lint,format,type}_cmd, project.src_dir, and
    scan.focus_dirs from repo manifests, falling back to *template* defaults.
    """
    project = template.data.get("project", {})
    scan = template.data.get("scan", {})
    command_options = template.meta.get("command_options", {})

    py_manifest = _find_manifest(root, "pyproject.toml")
    node_manifest = _find_manifest(root, "package.json")
    manifest_root = root
    if py_manifest is not None:
        manifest_root = py_manifest.parent
    elif node_manifest is not None:
        manifest_root = node_manifest.parent

    py_data = _read_toml(py_manifest) if py_manifest else None
    node_data = _read_json(node_manifest) if node_manifest else None

    values: dict[str, IntrospectedValue] = {}
    for field_name in _COMMAND_FIELDS:
        default_value = project.get(field_name) or ""
        iv = None
        if py_data is not None:
            iv = _python_command(
                field_name, py_data, manifest_root, command_options.get(field_name), default_value
            )
        if iv is None and node_data is not None and node_manifest is not None:
            iv = _node_command(field_name, node_data, node_manifest)
        if iv is None:
            iv = IntrospectedValue(
                value=default_value, provenance="default", evidence="template default"
            )
        values[f"project.{field_name}"] = iv

    default_src_dir = project.get("src_dir") or ""
    src_dir_iv, ambiguity = _introspect_src_dir(root, py_data, default_src_dir)
    values["project.src_dir"] = src_dir_iv
    ambiguities = [ambiguity] if ambiguity is not None else []

    values["scan.focus_dirs"] = _introspect_focus_dirs(
        root, src_dir_iv, scan.get("focus_dirs") or []
    )

    return IntrospectResult(values=values, ambiguities=ambiguities)


# ---------------------------------------------------------------------------
# Manifest discovery
# ---------------------------------------------------------------------------


def _find_manifest(root: Path, filename: str) -> Path | None:
    """Return *root/filename* if present, else the sole one-level-nested match."""
    direct = root / filename
    if direct.exists():
        return direct
    candidates = [
        p
        for p in sorted(root.glob(f"*/{filename}"))
        if not any(part in _SKIP_DIRS for part in p.relative_to(root).parts)
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _read_toml(path: Path) -> dict[str, Any] | None:
    try:
        return tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Python command detection
# ---------------------------------------------------------------------------


# Static fallback commands used only when neither the template default nor its
# command_options pool already names the detected tool (e.g. the `generic`
# template, which carries no command_options at all).
_TOOL_FALLBACK_COMMANDS = {
    "test_cmd": {"pytest": "pytest"},
    "lint_cmd": {"ruff": "ruff check .", "flake8": "flake8", "pylint": "pylint"},
    "format_cmd": {"ruff": "ruff format .", "black": "black ."},
}


def _pick_candidate(
    default_value: str,
    candidates: list[str] | None,
    must_contain: str,
    field_name: str,
    tool_name: str,
) -> str:
    if default_value and must_contain in default_value:
        return default_value
    for c in candidates or []:
        if must_contain in c:
            return c
    return _TOOL_FALLBACK_COMMANDS[field_name][tool_name]


def _python_command(
    field_name: str,
    py_data: dict[str, Any],
    manifest_root: Path,
    candidates: list[str] | None,
    default_value: str,
) -> IntrospectedValue | None:
    tool = py_data.get("tool", {})

    if field_name == "test_cmd":
        if "pytest" in tool and "ini_options" in tool.get("pytest", {}):
            value = _pick_candidate(default_value, candidates, "pytest", "test_cmd", "pytest")
            return IntrospectedValue(value, "declared", "[tool.pytest.ini_options] present")
        return None

    if field_name == "lint_cmd":
        if "ruff" in tool:
            value = _pick_candidate(default_value, candidates, "ruff", "lint_cmd", "ruff")
            return IntrospectedValue(value, "declared", "[tool.ruff] present")
        if "flake8" in tool:
            value = _pick_candidate(default_value, candidates, "flake8", "lint_cmd", "flake8")
            return IntrospectedValue(value, "declared", "[tool.flake8] present")
        if "pylint" in tool:
            value = _pick_candidate(default_value, candidates, "pylint", "lint_cmd", "pylint")
            return IntrospectedValue(value, "declared", "[tool.pylint] present")
        return None

    if field_name == "format_cmd":
        if "ruff" in tool:
            value = _pick_candidate(default_value, candidates, "ruff format", "format_cmd", "ruff")
            return IntrospectedValue(value, "declared", "[tool.ruff] present")
        if "black" in tool:
            value = _pick_candidate(default_value, candidates, "black", "format_cmd", "black")
            return IntrospectedValue(value, "declared", "[tool.black] present")
        return None

    if field_name == "type_cmd":
        if "mypy" in tool:
            return IntrospectedValue("mypy", "declared", "[tool.mypy] present")
        if (manifest_root / "pyrightconfig.json").exists():
            return IntrospectedValue("pyright", "declared", "pyrightconfig.json present")
        return None

    return None


# ---------------------------------------------------------------------------
# TS/JS command detection
# ---------------------------------------------------------------------------


_NODE_SCRIPT_ALIASES = {
    "test_cmd": ("test",),
    "lint_cmd": ("lint",),
    "format_cmd": ("format",),
    "type_cmd": ("typecheck", "type-check", "tsc"),
}


def _detect_package_manager(node_manifest: Path) -> str:
    root = node_manifest.parent
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "bun.lockb").exists():
        return "bun"
    return "npm"


def _node_command(
    field_name: str, node_data: dict[str, Any], node_manifest: Path
) -> IntrospectedValue | None:
    scripts = node_data.get("scripts", {})
    for script_name in _NODE_SCRIPT_ALIASES.get(field_name, ()):
        if script_name in scripts:
            pm = _detect_package_manager(node_manifest)
            return IntrospectedValue(
                f"{pm} run {script_name}", "declared", f"package.json scripts.{script_name}"
            )
    return None


# ---------------------------------------------------------------------------
# src_dir detection
# ---------------------------------------------------------------------------


_SRC_CANDIDATE_SKIP_DIRS = _SKIP_DIRS | {"tests", "test"}


def _iter_candidate_dirs(root: Path, pattern: str) -> set[str]:
    found: set[str] = set()
    for p in root.glob(pattern):
        parts = p.relative_to(root).parts
        if any(part in _SRC_CANDIDATE_SKIP_DIRS for part in parts):
            continue
        found.add(f"{parts[0]}/")
    return found


def _iter_top_level_package_dirs(root: Path) -> set[str]:
    """Top-level dirs that are themselves a package, or that contain one.

    Covers both ``D/__init__.py`` (D is the package) and ``D/pkg/__init__.py``
    (D holds a nested package, e.g. this repo's ``scripts/little_loops/``).
    """
    return _iter_candidate_dirs(root, "*/__init__.py") | _iter_candidate_dirs(
        root, "*/*/__init__.py"
    )


def _pyproject_src_candidate(py_data: dict[str, Any] | None) -> str | None:
    if py_data is None:
        return None
    tool = py_data.get("tool", {})
    setuptools = tool.get("setuptools", {}).get("packages", {}).get("find", {})
    where = setuptools.get("where")
    if where:
        return f"{where[0].rstrip('/')}/"
    hatch = tool.get("hatch", {}).get("build", {})
    for key in ("include", "packages"):
        entries = hatch.get(key)
        if entries:
            first = str(entries[0]).lstrip("./").split("/")[0].rstrip("*")
            if first:
                return f"{first}/"
    return None


def _tsconfig_src_candidate(root: Path) -> str | None:
    tsconfig = root / "tsconfig.json"
    if not tsconfig.exists():
        return None
    data = _read_json(tsconfig)
    if not data:
        return None
    compiler_options = data.get("compilerOptions", {})
    root_dir = compiler_options.get("rootDir")
    if root_dir:
        return f"{root_dir.strip('./').split('/')[0]}/"
    include = data.get("include")
    if include:
        first = str(include[0]).lstrip("./").split("/")[0]
        if first:
            return f"{first}/"
    return None


def _cargo_src_candidate(root: Path) -> str | None:
    if not (root / "Cargo.toml").exists():
        return None
    if (root / "src" / "main.rs").exists() or (root / "src" / "lib.rs").exists():
        return "src/"
    return None


def _introspect_src_dir(
    root: Path, py_data: dict[str, Any] | None, default_value: str
) -> tuple[IntrospectedValue, Ambiguity | None]:
    candidates: set[str] = set()
    evidence = ""

    if _iter_candidate_dirs(root, "src/*/__init__.py"):
        candidates.add("src/")
        evidence = "src/*/__init__.py package marker"

    package_dirs = _iter_top_level_package_dirs(root)
    if package_dirs:
        candidates |= package_dirs
        if not evidence:
            names = ", ".join(sorted(package_dirs))
            evidence = f"sole package marker under {names}"

    pyproject_candidate = _pyproject_src_candidate(py_data)
    if pyproject_candidate:
        candidates.add(pyproject_candidate)
        evidence = evidence or "pyproject.toml packages declaration"

    tsconfig_candidate = _tsconfig_src_candidate(root)
    if tsconfig_candidate:
        candidates.add(tsconfig_candidate)
        evidence = evidence or "tsconfig.json rootDir/include"

    cargo_candidate = _cargo_src_candidate(root)
    if cargo_candidate:
        candidates.add(cargo_candidate)
        evidence = evidence or "Cargo.toml + src/main.rs or src/lib.rs"

    if len(candidates) == 1:
        return IntrospectedValue(next(iter(candidates)), "inferred", evidence), None

    if len(candidates) > 1:
        return (
            IntrospectedValue(default_value, "default", "multiple src_dir candidates"),
            Ambiguity(field="src_dir", candidates=sorted(candidates)),
        )

    return IntrospectedValue(default_value, "default", "no unambiguous package marker"), None


# ---------------------------------------------------------------------------
# scan.focus_dirs
# ---------------------------------------------------------------------------


def _introspect_focus_dirs(
    root: Path, src_dir_iv: IntrospectedValue, default_focus_dirs: list[str]
) -> IntrospectedValue:
    focus_dirs: list[str] = []
    if src_dir_iv.provenance != "default" and isinstance(src_dir_iv.value, str):
        focus_dirs.append(src_dir_iv.value)

    for test_dir_name in ("tests/", "test/"):
        if (root / test_dir_name).is_dir():
            if not any(test_dir_name.startswith(fd) for fd in focus_dirs):
                focus_dirs.append(test_dir_name)

    if not focus_dirs:
        return IntrospectedValue(list(default_focus_dirs), "default", "template default")

    return IntrospectedValue(focus_dirs, "inferred", "adopted src_dir + detected test directory")
