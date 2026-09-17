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
import re
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

_COMMAND_FIELDS = ("test_cmd", "lint_cmd", "format_cmd", "type_cmd", "build_cmd")

# Launcher prefixes that wrap the "real" tool in a command string. Ordered
# longest-first so ``npm run`` matches before the bare ``npm`` form.
_LAUNCHER_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("python", "-m"),
    ("python3", "-m"),
    ("py", "-m"),
    ("uv", "run"),
    ("uvx",),
    ("poetry", "run"),
    ("pipenv", "run"),
    ("pdm", "run"),
    ("hatch", "run"),
    ("npm", "run"),
    ("npm", "exec"),
    ("pnpm", "run"),
    ("pnpm", "exec"),
    ("yarn", "run"),
    ("yarn", "exec"),
    ("bun", "run"),
    ("bun", "x"),
    ("npx",),
    ("bunx",),
    ("npm",),
    ("pnpm",),
    ("yarn",),
    ("bun",),
)


def base_tool_token(cmd: str) -> str:
    """Return the tool a command string ultimately runs, launcher prefixes stripped.

    ``"python -m pytest -q"`` -> ``"pytest"``; ``"npm run lint"`` -> ``"lint"``;
    ``"npx tsc --noEmit"`` -> ``"tsc"``; ``"./gradlew test"`` -> ``"gradlew"``.
    Leading ``KEY=value`` environment assignments are skipped. Used to decide
    whether a stored command and an introspected one name the *same* tool,
    so a stylistic variant (``python -m pytest`` vs ``pytest``) never triggers
    a config-drift warning.
    """
    import shlex

    try:
        tokens = shlex.split(cmd)
    except ValueError:
        tokens = cmd.split()
    while tokens and "=" in tokens[0] and not tokens[0].startswith("="):
        tokens.pop(0)
    stripped = True
    while stripped and tokens:
        stripped = False
        for prefix in _LAUNCHER_PREFIXES:
            n = len(prefix)
            if len(tokens) > n and tuple(tokens[:n]) == prefix:
                tokens = tokens[n:]
                stripped = True
                break
    if not tokens:
        return ""
    return tokens[0].rsplit("/", 1)[-1]


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

    # Precedence per field: manifest-declared tool table / script (declared)
    # > task-runner target (inferred) > tool config file (inferred)
    # > ecosystem convention (inferred) > template default.
    values: dict[str, IntrospectedValue] = {}
    for field_name in _COMMAND_FIELDS:
        default_value = project.get(field_name) or ""
        candidates = command_options.get(field_name)
        iv = None
        if py_data is not None:
            iv = _python_command(field_name, py_data, manifest_root, candidates, default_value)
        if iv is None and node_data is not None and node_manifest is not None:
            iv = _node_command(field_name, node_data, node_manifest)
        if iv is None:
            iv = _task_runner_command(field_name, root, py_data)
        if iv is None and node_manifest is not None:
            iv = _node_config_command(
                field_name, node_manifest.parent, node_data or {}, default_value, candidates
            )
        if iv is None:
            iv = _ecosystem_command(field_name, root, default_value, candidates)
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

    default_test_dir = project.get("test_dir") or "tests"
    values["project.test_dir"] = _introspect_test_dir(root, default_test_dir)

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
    "build_cmd": ("build",),
}


def _detect_package_manager(node_manifest: Path) -> str:
    """Package manager for *node_manifest*: ``packageManager`` field, then lockfiles."""
    root = node_manifest.parent
    data = _read_json(node_manifest) or {}
    declared = data.get("packageManager")
    if isinstance(declared, str):
        name = declared.split("@", 1)[0].strip()
        if name in ("npm", "pnpm", "yarn", "bun"):
            return name
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        return "bun"
    return "npm"


def _choose(
    default_value: str, candidates: list[str] | None, must_contain: str, fallback: str
) -> str:
    """Prefer the template default, then a curated option, that names *must_contain*."""
    if default_value and must_contain in default_value:
        return default_value
    for c in candidates or []:
        if must_contain in c:
            return c
    return fallback


def _any_glob(root: Path, *patterns: str) -> str | None:
    """First filename under *root* matching any of *patterns*, or None."""
    for pattern in patterns:
        for match in sorted(root.glob(pattern)):
            return match.name
    return None


# Tool config files that identify a tool even when package.json declares no
# script for it. (field, globs, package.json key, must_contain, fallback cmd)
_NODE_CONFIG_RULES: tuple[tuple[str, tuple[str, ...], str | None, str, str], ...] = (
    ("type_cmd", ("tsconfig.json",), None, "tsc", "npx tsc --noEmit"),
    ("lint_cmd", ("biome.json", "biome.jsonc"), None, "biome", "npx biome check ."),
    (
        "lint_cmd",
        ("eslint.config.*", ".eslintrc", ".eslintrc.*"),
        "eslintConfig",
        "eslint",
        "npx eslint .",
    ),
    ("format_cmd", ("biome.json", "biome.jsonc"), None, "biome", "npx biome format --write ."),
    (
        "format_cmd",
        (".prettierrc", ".prettierrc.*", "prettier.config.*"),
        "prettier",
        "prettier",
        "npx prettier --write .",
    ),
    ("test_cmd", ("vitest.config.*", "vite.config.*"), None, "vitest", "npx vitest run"),
    ("test_cmd", ("jest.config.*",), "jest", "jest", "npx jest"),
)


def _node_config_command(
    field_name: str,
    root: Path,
    node_data: dict[str, Any],
    default_value: str,
    candidates: list[str] | None,
) -> IntrospectedValue | None:
    """Derive a command from a tool's config file when package.json has no script for it."""
    for rule_field, globs, pkg_key, must_contain, fallback in _NODE_CONFIG_RULES:
        if rule_field != field_name:
            continue
        found = _any_glob(root, *globs)
        if found is None and pkg_key and pkg_key in node_data:
            found = f'package.json "{pkg_key}"'
        if found is None:
            continue
        if must_contain == "vitest" and found.startswith("vite.config"):
            # vite.config.* only implies vitest when the dependency is present.
            deps = {**node_data.get("devDependencies", {}), **node_data.get("dependencies", {})}
            if "vitest" not in deps:
                continue
        value = _choose(default_value, candidates, must_contain, fallback)
        return IntrospectedValue(value, "inferred", f"{found} present")
    return None


# ---------------------------------------------------------------------------
# Task-runner targets (Makefile / justfile / tox / nox)
# ---------------------------------------------------------------------------


_TASK_TARGET_ALIASES: dict[str, tuple[str, ...]] = {
    "test_cmd": ("test", "tests", "check"),
    "lint_cmd": ("lint",),
    "format_cmd": ("format", "fmt"),
    "type_cmd": ("typecheck", "type-check", "types", "mypy"),
    "build_cmd": ("build",),
}
_MAKE_TARGET_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*:(?!=)", re.MULTILINE)
_JUST_RECIPE_RE = re.compile(r"^([A-Za-z0-9_-]+)(?:\s+[^:\n]*)?:(?!=)", re.MULTILINE)
_TOX_ENV_RE = re.compile(r"^\[testenv:([A-Za-z0-9_.-]+)\]", re.MULTILINE)
_NOX_SESSION_RE = re.compile(r"^def\s+([A-Za-z0-9_]+)\s*\(\s*session\b", re.MULTILINE)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _first_alias(names: set[str], field_name: str) -> str | None:
    for alias in _TASK_TARGET_ALIASES.get(field_name, ()):
        if alias in names:
            return alias
    return None


def _task_runner_command(
    field_name: str, root: Path, py_data: dict[str, Any] | None
) -> IntrospectedValue | None:
    """Derive ``make <target>`` / ``just <recipe>`` / ``tox -e`` / ``nox -s`` from task runners."""
    for filename in ("Makefile", "makefile", "GNUmakefile"):
        text = _read_text(root / filename)
        if text is None:
            continue
        targets = {
            m.group(1) for m in _MAKE_TARGET_RE.finditer(text) if not m.group(1).startswith(".")
        }
        target = _first_alias(targets, field_name)
        if target:
            return IntrospectedValue(f"make {target}", "inferred", f"{filename} target '{target}'")
        break

    for filename in ("justfile", "Justfile", ".justfile"):
        text = _read_text(root / filename)
        if text is None:
            continue
        recipes = {m.group(1) for m in _JUST_RECIPE_RE.finditer(text)}
        recipe = _first_alias(recipes, field_name)
        if recipe:
            return IntrospectedValue(f"just {recipe}", "inferred", f"{filename} recipe '{recipe}'")
        break

    tox_text = _read_text(root / "tox.ini")
    if tox_text is None and py_data and "tox" in py_data.get("tool", {}):
        legacy = py_data["tool"]["tox"].get("legacy_tox_ini")
        tox_text = legacy if isinstance(legacy, str) else ""
    if tox_text is not None:
        envs = {m.group(1) for m in _TOX_ENV_RE.finditer(tox_text)}
        env = _first_alias(envs, field_name)
        if env:
            return IntrospectedValue(f"tox -e {env}", "inferred", f"tox env '{env}'")
        if field_name == "test_cmd" and "[testenv]" in tox_text:
            return IntrospectedValue("tox", "inferred", "tox.ini [testenv]")

    nox_text = _read_text(root / "noxfile.py")
    if nox_text is not None:
        sessions = {m.group(1) for m in _NOX_SESSION_RE.finditer(nox_text)}
        session = _first_alias(sessions, field_name)
        if session:
            return IntrospectedValue(
                f"nox -s {session}", "inferred", f"noxfile.py session '{session}'"
            )
    return None


# ---------------------------------------------------------------------------
# Ecosystem conventions (Go / Rust / Java / .NET)
# ---------------------------------------------------------------------------


def _ecosystem_command(
    field_name: str, root: Path, default_value: str, candidates: list[str] | None
) -> IntrospectedValue | None:
    """Convention-derived commands for ecosystems whose build tool implies the commands.

    These mostly re-confirm the project-type template's literal, but they
    attach *evidence* (``go.mod present``) so the wizard can show why the
    value was proposed rather than labelling it a bare template default.
    """
    if (root / "go.mod").exists():
        marker = "go.mod present"
        if field_name == "test_cmd":
            return IntrospectedValue(
                _choose(default_value, candidates, "go test", "go test ./..."), "inferred", marker
            )
        if field_name == "lint_cmd":
            golangci = _any_glob(root, ".golangci.yml", ".golangci.yaml", ".golangci.toml")
            if golangci:
                return IntrospectedValue(
                    _choose(default_value, candidates, "golangci-lint", "golangci-lint run"),
                    "inferred",
                    f"{golangci} present",
                )
            return IntrospectedValue(
                _choose(default_value, candidates, "go vet", "go vet ./..."), "inferred", marker
            )
        if field_name == "format_cmd":
            return IntrospectedValue(
                _choose(default_value, candidates, "gofmt", "gofmt -w ."), "inferred", marker
            )
        if field_name == "build_cmd":
            return IntrospectedValue(
                _choose(default_value, candidates, "go build", "go build ./..."), "inferred", marker
            )
        return None

    if (root / "Cargo.toml").exists():
        marker = "Cargo.toml present"
        table = {
            "test_cmd": ("cargo test", "cargo test"),
            "lint_cmd": ("clippy", "cargo clippy -- -D warnings"),
            "format_cmd": ("cargo fmt", "cargo fmt"),
            "build_cmd": ("cargo build", "cargo build"),
        }
        if field_name in table:
            must, fallback = table[field_name]
            evidence = (
                "rustfmt.toml present"
                if field_name == "format_cmd" and (root / "rustfmt.toml").exists()
                else marker
            )
            return IntrospectedValue(
                _choose(default_value, candidates, must, fallback), "inferred", evidence
            )
        return None

    if (root / "pom.xml").exists():
        table = {
            "test_cmd": ("mvn test", "mvn test"),
            "build_cmd": ("mvn", "mvn package -DskipTests"),
        }
        if field_name in table:
            must, fallback = table[field_name]
            return IntrospectedValue(
                _choose(default_value, candidates, must, fallback), "inferred", "pom.xml present"
            )
        return None

    gradle = _any_glob(root, "build.gradle", "build.gradle.kts")
    if gradle:
        runner = "./gradlew" if (root / "gradlew").exists() else "gradle"
        evidence = f"{gradle} present" + (" (gradlew wrapper)" if runner == "./gradlew" else "")
        gradle_cmds: dict[str, str] = {
            "test_cmd": f"{runner} test",
            "build_cmd": f"{runner} build -x test",
        }
        if field_name in gradle_cmds:
            return IntrospectedValue(
                _choose(default_value, candidates, f"{runner} ", gradle_cmds[field_name]),
                "inferred",
                evidence,
            )
        return None

    dotnet = _any_glob(root, "*.sln", "*.csproj", "*.fsproj")
    if dotnet:
        table = {
            "test_cmd": ("dotnet test", "dotnet test"),
            "lint_cmd": ("dotnet format", "dotnet format --verify-no-changes"),
            "format_cmd": ("dotnet format", "dotnet format"),
            "build_cmd": ("dotnet build", "dotnet build"),
        }
        if field_name in table:
            must, fallback = table[field_name]
            return IntrospectedValue(
                _choose(default_value, candidates, must, fallback), "inferred", f"{dotnet} present"
            )
    return None


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
    evidence_parts: list[str] = []
    if src_dir_iv.provenance != "default" and isinstance(src_dir_iv.value, str):
        focus_dirs.append(src_dir_iv.value)
        evidence_parts.append("adopted src_dir")

    for test_dir_name in ("tests/", "test/"):
        if (root / test_dir_name).is_dir():
            if not any(test_dir_name.startswith(fd) for fd in focus_dirs):
                focus_dirs.append(test_dir_name)
                evidence_parts.append(f"detected {test_dir_name} directory")

    if not focus_dirs:
        return IntrospectedValue(list(default_focus_dirs), "default", "template default")

    return IntrospectedValue(focus_dirs, "inferred", " + ".join(evidence_parts))


# ---------------------------------------------------------------------------
# project.test_dir
# ---------------------------------------------------------------------------


def _introspect_test_dir(root: Path, default_value: str) -> IntrospectedValue:
    for test_dir_name in ("tests/", "test/"):
        if (root / test_dir_name).is_dir():
            return IntrospectedValue(
                test_dir_name, "inferred", f"detected {test_dir_name} directory"
            )
    return IntrospectedValue(default_value, "default", "template default")
