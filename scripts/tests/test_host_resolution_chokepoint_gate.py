"""Gate: host selection goes through ``host_runner.resolve_host()`` (BUG-3644).

``resolve_host()`` reads ``orchestration.host_cli`` itself on the ambient-env
path (``env is None``), so new code cannot skip the config key unless it:

(a) hand-rolls an ``LL_HOST_CLI`` / ``orchestration.host_cli`` read for host
    selection outside ``host_runner.py``;
(b) calls ``resolve_host(env=...)`` / ``resolve_host(some_env)`` with a copy of
    ambient env, which silently skips the config step (only
    ``resolve_host_named`` may pass ``env``, and it lives in ``host_runner.py``);
(c) calls the deprecated ``apply_host_cli_from_config`` in production code.

AST-scans ``scripts/little_loops/`` and fails on any site outside the reasoned
allowlist. Matchers are deliberately narrow: docstring/error-message mentions
and dict-literal child-env writes are not reads.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_ROOT = _REPO_ROOT / "scripts" / "little_loops"

_OWNER = "host_runner.py"

# path relative to scripts/little_loops -> one-line reason (reads only; a
# resolve_host(env=...) call or apply_host_cli_from_config call is never allowed
# outside host_runner.py).
_ALLOWLIST: dict[str, str] = {
    "config/orchestration.py": "loads orchestration.host_cli from the config dict (data.get)",
    "init/cli.py": "ll-init reads/persists orchestration.host_cli in the raw config dict",
}


def _is_host_cli_key_read(node: ast.AST) -> bool:
    """``.get("LL_HOST_CLI")`` / ``["LL_HOST_CLI"]`` load / ``orchestration.host_cli`` reads."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if (
            node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in ("LL_HOST_CLI", "host_cli")
        ):
            return True
    if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
        if isinstance(node.slice, ast.Constant) and node.slice.value in (
            "LL_HOST_CLI",
            "host_cli",
        ):
            return True
    if (
        isinstance(node, ast.Attribute)
        and node.attr == "host_cli"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "orchestration"
    ):
        return True
    return False


def _is_resolve_host_with_env(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    if name != "resolve_host":
        return False
    return bool(node.args) or any(kw.arg == "env" for kw in node.keywords)


def _is_apply_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    return name == "apply_host_cli_from_config"


def _scan(tree: ast.AST) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {"read": [], "env_call": [], "apply": []}
    for node in ast.walk(tree):
        if _is_host_cli_key_read(node):
            found["read"].append(node.lineno)  # type: ignore[attr-defined]
        if _is_resolve_host_with_env(node):
            found["env_call"].append(node.lineno)  # type: ignore[attr-defined]
        if _is_apply_call(node):
            found["apply"].append(node.lineno)  # type: ignore[attr-defined]
    return found


def _iter_source_files() -> list[Path]:
    return sorted(p for p in _SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def _violations() -> list[str]:
    out: list[str] = []
    for path in _iter_source_files():
        rel = path.relative_to(_SRC_ROOT).as_posix()
        if rel == _OWNER:
            continue
        found = _scan(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        if rel not in _ALLOWLIST:
            out.extend(f"{rel}:{ln} hand-rolled host_cli/LL_HOST_CLI read" for ln in found["read"])
        out.extend(f"{rel}:{ln} resolve_host(env=...) skips config" for ln in found["env_call"])
        out.extend(f"{rel}:{ln} apply_host_cli_from_config call" for ln in found["apply"])
    return out


def test_no_host_selection_bypass_outside_resolve_host() -> None:
    violations = _violations()
    assert not violations, (
        "host selection must go through host_runner.resolve_host() (which reads "
        "orchestration.host_cli itself). Route the call through it, use "
        "resolve_host_named(name) for a fixed host, or add a reasoned allowlist "
        "entry in this test:\n" + "\n".join(violations)
    )


def test_allowlist_entries_still_exist_and_still_read() -> None:
    """Catch allowlist drift: a missing file or one with no remaining read."""
    stale, unused = [], []
    for rel in _ALLOWLIST:
        path = _SRC_ROOT / rel
        if not path.exists():
            stale.append(rel)
            continue
        if not _scan(ast.parse(path.read_text(encoding="utf-8")))["read"]:
            unused.append(rel)
    assert not stale, f"allowlist entries for files that no longer exist: {stale}"
    assert not unused, f"allowlist entries with no remaining host_cli read -- remove: {unused}"


def test_gate_detects_a_stray_site() -> None:
    tree = ast.parse(
        "import os\n"
        "a = os.environ.get('LL_HOST_CLI')\n"
        "b = env['LL_HOST_CLI']\n"
        "c = cfg.orchestration.host_cli\n"
        "d = raw['orchestration']['host_cli']\n"
        "e = resolve_host(dict(os.environ))\n"
        "f = resolve_host(env=x)\n"
        "apply_host_cli_from_config(cfg)\n"
    )
    found = _scan(tree)
    assert len(found["read"]) == 4
    assert len(found["env_call"]) == 2
    assert len(found["apply"]) == 1


def test_gate_ignores_non_reads() -> None:
    tree = ast.parse(
        "child = project_child_env(extra={'LL_HOST_CLI': 'codex'})\n"
        "msg = 'see LL_HOST_CLI'\n"
        "env['LL_HOST_CLI'] = 'x'\n"
        "fp = shown.conditions.host_cli\n"
        "r = resolve_host(project_root=root)\n"
        "s = resolve_host()\n"
    )
    found = _scan(tree)
    assert found == {"read": [], "env_call": [], "apply": []}
