"""Gate direct host transcript-root joins outside the session layout seam.

Only Python source under ``scripts/little_loops`` is scanned. The literal
examples in the private-reference and skill-prose lint tests are test data,
not reader code. Host config and output paths such as ``.claude/settings.json``
and ``.claude/user-messages.jsonl`` do not pair a transcript root and are
intentionally ignored.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent.parent / "little_loops"

# Adjacent path components that identify host transcript roots.
_TRANSCRIPT_ROOTS = {
    (".claude", "projects"),
    (".codex", "sessions"),
    (".opencode", "projects"),
    (".pi", "projects"),
    (".qwen", "projects"),
    (".gemini", "tmp"),
    (".kimi-code", "sessions"),
    (".omp", "agent"),
}

# (source-relative path, enclosing function) -> reason for the direct join.
_ALLOWLIST: dict[tuple[str, str], str] = {
    ("session_store/sessions.py", "list_workspaces"): (
        "the discovery seam's workspace enumeration for encoded-directory hosts"
    ),
    ("session_store/sessions.py", "_list_claude_workspaces"): (
        "the discovery seam's Claude workspace enumerator"
    ),
    ("session_store/writers.py", "host_layout_for"): (
        "host layout metadata consumed by the discovery and ingest seam"
    ),
    ("user_messages.py", "_get_claude_project_folder"): (
        "legacy project-folder resolver called by the discovery seam"
    ),
    ("user_messages.py", "_get_opencode_project_folder"): (
        "legacy project-folder resolver called by the discovery seam"
    ),
    ("user_messages.py", "_get_pi_project_folder"): (
        "legacy project-folder resolver called by the discovery seam"
    ),
    ("user_messages.py", "_get_qwen_project_folder"): (
        "legacy project-folder resolver called by the discovery seam"
    ),
}


def _segments(node: ast.AST) -> list[str]:
    """Return literal components of a ``/``, ``joinpath`` or ``Path`` chain."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return [*_segments(node.left), *_segments(node.right)]
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in {"joinpath", "join"}:
            return [*_segments(func.value), *(part for arg in node.args for part in _segments(arg))]
        if isinstance(func, ast.Name) and func.id in {"Path", "PurePath"}:
            return [part for arg in node.args for part in _segments(arg)]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [part for part in node.value.replace("\\", "/").split("/") if part]
    return []


def _enclosing_function(node: ast.AST, parents: dict[int, ast.AST]) -> str:
    while id(node) in parents:
        node = parents[id(node)]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node.name
    return "<module>"


def _root_sites(source: str, rel: str) -> set[tuple[str, str, int, tuple[str, str]]]:
    """Find literal transcript-root joins and their nearest enclosing function."""
    tree = ast.parse(source, filename=rel)
    parents = {id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    sites: set[tuple[str, str, int, tuple[str, str]]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.BinOp, ast.Call)):
            continue
        parts = _segments(node)
        for pair in zip(parts, parts[1:], strict=False):
            if pair in _TRANSCRIPT_ROOTS:
                sites.add((rel, _enclosing_function(node, parents), node.lineno, pair))
    return sites


def _all_sites() -> set[tuple[str, str, int, tuple[str, str]]]:
    sites: set[tuple[str, str, int, tuple[str, str]]] = set()
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(_SRC_ROOT).as_posix()
        sites.update(_root_sites(path.read_text(encoding="utf-8"), rel))
    return sites


def test_no_direct_transcript_roots_outside_reasoned_allowlist() -> None:
    violations = sorted(
        f"{rel}:{line} in {func}(): {root[0]}/{root[1]}"
        for rel, func, line, root in _all_sites()
        if (rel, func) not in _ALLOWLIST
    )
    assert not violations, "route reader discovery through detect_sessions():\n" + "\n".join(
        violations
    )


def test_allowlist_has_no_stale_entries() -> None:
    live = {(rel, func) for rel, func, _line, _root in _all_sites()}
    stale = set(_ALLOWLIST) - live
    assert not stale, f"remove stale transcript-root allowlist entries: {sorted(stale)}"
    assert all(reason.strip() for reason in _ALLOWLIST.values())


def test_gate_detects_stray_reader_join() -> None:
    source = 'def stray(home):\n    return home / ".claude" / "projects" / "workspace"\n'
    assert _root_sites(source, "stray.py") == {("stray.py", "stray", 2, (".claude", "projects"))}


def test_non_transcript_claude_paths_are_not_flagged() -> None:
    source = (
        "def config(home):\n"
        '    return home / ".claude" / "settings.json"\n'
        "def output(cwd):\n"
        '    return cwd / ".claude" / "user-messages.jsonl"\n'
    )
    assert _root_sites(source, "reader.py") == set()
