"""Derivation fingerprint of ``session_store.lifecycle.rebuild`` (ENH-3678).

Computes a digest of everything that decides what a non-usage ``rebuild()``
writes, so a test can tell when ``REBUILD_DERIVE_VERSION`` must be bumped.

The AST is used for *discovery only* (callees, docstring ranges, statement
ranges). The hashed representation is the source text of each function with
docstring lines removed, comments blanked and all whitespace stripped, which is
identical across CPython 3.10-3.13 (``ast.dump``/``ast.unparse`` are not).
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import subprocess
import tokenize
from pathlib import Path
from typing import Any

# Edges into the usage-derivation subtree are not followed: that path is
# governed by ``_USAGE_DERIVE_VERSION``. ``_stamp_rebuild_derive_version`` and
# ``refuse_on_remote`` are non-derivation statements in ``rebuild``'s body.
PRUNED_NAMES = frozenset(
    {
        "_backfill_usage_events",
        "_invalidate_usage_for_rebuild",
        "_set_usage_derive_checkpoint",
        "_stamp_rebuild_derive_version",
        "_usage_checkpoint_snapshot",
        "refuse_on_remote",
    }
)
# Reached and listed, but not hashed: host plumbing only; the prompt text lives
# in ``_summarize_block``, which stays hashed.
STOP_NAMES = frozenset({"_call_llm_for_summary"})

_SIMPLE_STMTS = (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Expr)
_CONSTANTS = ("_REBUILD_TABLES", "_REBUILD_SEARCH_KINDS")


def _module_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _stripped_statements(fn: ast.FunctionDef) -> list[ast.stmt]:
    """Simple statements in *fn* that reference a pruned name."""
    out: list[ast.stmt] = []
    for node in ast.walk(fn):
        if not isinstance(node, _SIMPLE_STMTS):
            continue
        if any(isinstance(n, ast.Name) and n.id in PRUNED_NAMES for n in ast.walk(node)):
            out.append(node)
    return out


def _referenced_names(fn: ast.FunctionDef, skip: list[ast.stmt]) -> set[str]:
    skipped = {id(n) for s in skip for n in ast.walk(s)}
    names: set[str] = set()
    for node in ast.walk(fn):
        if id(node) in skipped:
            continue
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "_pkg"
        ):
            names.add(node.attr)
    return names


def resolve_function_set(sources: dict[str, str]) -> list[tuple[str, str]]:
    """Walk from ``rebuild`` to a fixed point; return sorted ``(module, name)``.

    *sources* maps ``"lifecycle"``/``"writers"`` to module source. A name used
    in ``lifecycle`` resolves to a ``lifecycle`` def first, then ``writers``;
    names used in ``writers`` resolve within ``writers``.
    """
    funcs = {mod: _module_functions(ast.parse(src)) for mod, src in sources.items()}
    seen: set[tuple[str, str]] = set()
    todo = [("lifecycle", "rebuild")]
    while todo:
        mod, name = todo.pop()
        if (mod, name) in seen:
            continue
        seen.add((mod, name))
        if name in STOP_NAMES:
            continue
        fn = funcs[mod][name]
        skip = _stripped_statements(fn) if (mod, name) == ("lifecycle", "rebuild") else []
        for ref in _referenced_names(fn, skip):
            if ref in PRUNED_NAMES:
                continue
            order = ("lifecycle", "writers") if mod == "lifecycle" else ("writers",)
            for target in order:
                if ref in funcs[target]:
                    todo.append((target, ref))
                    break
    return sorted(seen)


def _blank_comments(source: str) -> list[str]:
    lines = source.splitlines()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            row, col = tok.start
            lines[row - 1] = lines[row - 1][:col]
    return lines


def _function_digest(
    lines: list[str], fn: ast.FunctionDef, extra_blank: list[ast.stmt] | None = None
) -> str:
    start = min([fn.lineno, *(d.lineno for d in fn.decorator_list)])
    blank: set[int] = set()
    for node in ast.walk(fn):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                blank.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    for stmt in extra_blank or []:
        blank.update(range(stmt.lineno, (stmt.end_lineno or stmt.lineno) + 1))
    kept = [lines[i - 1] for i in range(start, (fn.end_lineno or start) + 1) if i not in blank]
    text = "".join("".join(kept).split())
    return hashlib.sha256(text.encode()).hexdigest()


def _literal(tree: ast.Module, name: str) -> Any:
    """Literal value of module-level ``name`` (plain or annotated assignment)."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            return ast.literal_eval(node.value)
    raise KeyError(f"required constant {name!r} not found as a literal assignment")


def compute_fingerprint(sources: dict[str, str], manifest: dict[str, Any]) -> dict[str, Any]:
    """Return ``{"function_set": [...], "digest": "<sha256>"}``.

    Hashed: every non-stopped function in the resolved set, ``_REBUILD_TABLES``
    minus ``usage_events``, ``_REBUILD_SEARCH_KINDS`` minus ``"usage"``, the manifest
    DDL of those non-usage rebuild tables, and (only when nonempty) the non-usage
    entries of ``_REBUILD_TABLE_PREDICATES``.
    """
    resolved = resolve_function_set(sources)
    trees = {mod: ast.parse(src) for mod, src in sources.items()}
    funcs = {mod: _module_functions(tree) for mod, tree in trees.items()}
    lines = {mod: _blank_comments(src) for mod, src in sources.items()}
    parts: list[str] = []
    for mod, name in resolved:
        if name in STOP_NAMES:
            continue
        fn = funcs[mod][name]
        extra = _stripped_statements(fn) if (mod, name) == ("lifecycle", "rebuild") else None
        parts.append(f"fn:{mod}.{name}:{_function_digest(lines[mod], fn, extra)}")
    tables = [t for t in _literal(trees["lifecycle"], "_REBUILD_TABLES") if t != "usage_events"]
    kinds = [k for k in _literal(trees["lifecycle"], "_REBUILD_SEARCH_KINDS") if k != "usage"]
    # Non-usage deletion predicates decide which rows a rebuild keeps (BUG-3715).
    # Hashed only when nonempty so the legacy usage-only definition keeps its digest.
    predicates = _literal(trees["lifecycle"], "_REBUILD_TABLE_PREDICATES")
    kept = {t: p for t, p in sorted(predicates.items()) if t != "usage_events"}
    parts.append("tables:" + ",".join(tables))
    parts.append("kinds:" + ",".join(kinds))
    if kept:
        parts.append("predicates:" + json.dumps(kept, sort_keys=True))
    for table in tables:
        ddl = json.dumps(manifest["objects"].get(table), sort_keys=True)
        parts.append(f"ddl:{table}:{ddl}")
    return {
        "function_set": [f"{mod}.{name}" for mod, name in resolved],
        "digest": hashlib.sha256("\n".join(parts).encode()).hexdigest(),
    }


def sources_at(repo_root: Path, rev: str | None) -> tuple[dict[str, str], dict[str, Any]]:
    """Module sources and manifest at git *rev* (``None`` = working tree)."""
    base = "scripts/little_loops/session_store"
    names = {
        "lifecycle": f"{base}/lifecycle.py",
        "writers": f"{base}/writers.py",
        "manifest": f"{base}/schema_manifest.json",
    }

    def read(rel: str) -> str:
        if rev is None:
            return (repo_root / rel).read_text(encoding="utf-8")
        return subprocess.run(
            ["git", "show", f"{rev}:{rel}"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    return (
        {"lifecycle": read(names["lifecycle"]), "writers": read(names["writers"])},
        json.loads(read(names["manifest"])),
    )


SNAPSHOT_REL = "scripts/little_loops/session_store/rebuild_fingerprint.json"
# Commit of the schema-58 bump: the last derivation change before the derive gate.
LEGACY_REV = "9cb4467d6"


def regenerate(repo_root: Path) -> dict[str, Any]:
    """Rewrite the checked-in snapshot from the working tree.

    ``frozen_legacy_digest`` is never regenerated once present; on first creation it is
    computed from ``LEGACY_REV``.
    """
    path = repo_root / SNAPSHOT_REL
    current = compute_fingerprint(*sources_at(repo_root, None))
    frozen = None
    if path.exists():
        frozen = json.loads(path.read_text(encoding="utf-8")).get("frozen_legacy_digest")
    if frozen is None:
        frozen = compute_fingerprint(*sources_at(repo_root, LEGACY_REV))["digest"]
    snapshot = {
        "current_digest": current["digest"],
        "frozen_legacy_digest": frozen,
        "function_set": current["function_set"],
    }
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return snapshot
