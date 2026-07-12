"""Grep/AST fallback :class:`CodeQueryProvider` — the day-one reference implementation.

Always ``available``, always ``freshness: fresh`` (it reads the working tree
directly, never a stale index). This provider IS the degradation story:
consumers never write ``if graph_available`` branches — ``resolve_provider``
falls back here automatically.

- ``defines``/``callees_of`` use a Python ``ast`` parse of the target file
  (exact confidence).
- ``callers_of``/``references``/``importers_of`` use ``git grep -n`` word-
  boundary search over tracked files (heuristic confidence).
- ``impact_of`` walks an import graph built from ``ast`` imports across
  tracked ``.py`` files, depth-limited.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from little_loops.codequery.core import QUERY_KINDS, CodeRef, ProviderStatus

_NAME = "fallback"


def _git_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return Path.cwd()
    return Path(result.stdout.strip())


def _tracked_py_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [root / line for line in result.stdout.splitlines() if line]


def _git_grep_word(root: Path, word: str) -> list[tuple[str, int, str]]:
    """Run ``git grep -n -w`` for *word*; return (path, line, text) hits.

    A non-zero exit code from ``git grep`` means "no matches" (not an
    error) unless it's a usage/repo error — the returncode-check idiom used
    in ``issue_discovery/search.py::reopen_issue`` and ``git_operations.py``.
    """
    result = subprocess.run(
        ["git", "grep", "-n", "-w", "--", word],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        return []
    hits: list[tuple[str, int, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        path, lineno_str, text = parts
        try:
            lineno = int(lineno_str)
        except ValueError:
            continue
        hits.append((path, lineno, text))
    return hits


def _parse_ast(path: Path) -> ast.AST | None:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _short_symbol(qualified: str) -> str:
    """Return the trailing identifier of a dotted symbol path."""
    return qualified.rsplit(".", 1)[-1]


class FallbackProvider:
    """Grep/AST-backed :class:`~little_loops.codequery.core.CodeQueryProvider`."""

    name = _NAME

    def capabilities(self) -> set[str]:
        return set(QUERY_KINDS)

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            available=True,
            freshness="fresh",
            indexed_at=None,
            detail="reads the working tree directly; no index to go stale",
        )

    def defines(self, path: str) -> list[CodeRef]:
        root = _git_root()
        target = root / path
        tree = _parse_ast(target)
        if tree is None:
            return []
        refs: list[CodeRef] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                refs.append(
                    CodeRef(
                        path=path,
                        line=node.lineno,
                        symbol=node.name,
                        kind="class" if isinstance(node, ast.ClassDef) else "function",
                        confidence="exact",
                        provider=self.name,
                    )
                )
        return refs

    def callees_of(self, symbol: str) -> list[CodeRef]:
        short = _short_symbol(symbol)
        root = _git_root()
        # callees_of needs the defining file; use references as a heuristic
        # locator of the definition site, then parse that file's body.
        candidates = self.defines_scan_for(short, root)
        refs: list[CodeRef] = []
        for path in candidates:
            tree = _parse_ast(root / path)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == short:
                    for call in ast.walk(node):
                        if not isinstance(call, ast.Call):
                            continue
                        callee_name = _call_name(call.func)
                        if callee_name is None:
                            continue
                        refs.append(
                            CodeRef(
                                path=path,
                                line=call.lineno,
                                symbol=callee_name,
                                kind="call",
                                confidence="exact",
                                provider=self.name,
                            )
                        )
        return refs

    def defines_scan_for(self, short_symbol: str, root: Path) -> list[str]:
        """Return relative paths where *short_symbol* is defined (via git grep heuristic)."""
        hits = _git_grep_word(root, short_symbol)
        paths: list[str] = []
        for path, _lineno, text in hits:
            if not path.endswith(".py"):
                continue
            stripped = text.strip()
            if stripped.startswith(f"def {short_symbol}(") or stripped.startswith(
                f"class {short_symbol}"
            ) or stripped.startswith(f"async def {short_symbol}("):
                if path not in paths:
                    paths.append(path)
        return paths

    def callers_of(self, symbol: str) -> list[CodeRef]:
        short = _short_symbol(symbol)
        root = _git_root()
        hits = _git_grep_word(root, short)
        refs: list[CodeRef] = []
        for path, lineno, text in hits:
            stripped = text.strip()
            if stripped.startswith(f"def {short}(") or stripped.startswith(f"class {short}"):
                continue
            refs.append(
                CodeRef(
                    path=path,
                    line=lineno,
                    symbol=short,
                    kind="reference",
                    confidence="heuristic",
                    provider=self.name,
                )
            )
        return refs

    def references(self, symbol: str) -> list[CodeRef]:
        short = _short_symbol(symbol)
        root = _git_root()
        hits = _git_grep_word(root, short)
        return [
            CodeRef(
                path=path,
                line=lineno,
                symbol=short,
                kind="reference",
                confidence="heuristic",
                provider=self.name,
            )
            for path, lineno, _text in hits
        ]

    def importers_of(self, module: str) -> list[CodeRef]:
        module_name = module
        if module_name.endswith(".py"):
            module_name = module_name[: -len(".py")].replace("/", ".")
        short = module_name.rsplit(".", 1)[-1]
        root = _git_root()
        hits = _git_grep_word(root, short)
        refs: list[CodeRef] = []
        for path, lineno, text in hits:
            stripped = text.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                refs.append(
                    CodeRef(
                        path=path,
                        line=lineno,
                        symbol=module_name,
                        kind="import",
                        confidence="heuristic",
                        provider=self.name,
                    )
                )
        return refs

    def impact_of(self, paths: list[str], depth: int = 2) -> list[CodeRef]:
        root = _git_root()
        py_files = _tracked_py_files(root)
        import_graph: dict[str, set[str]] = {}
        for py_file in py_files:
            rel = str(py_file.relative_to(root))
            tree = _parse_ast(py_file)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        import_graph.setdefault(rel, set()).add(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    import_graph.setdefault(rel, set()).add(node.module)

        targets = {p.replace("/", ".").removesuffix(".py") for p in paths}
        impacted: set[str] = set()
        frontier = set(targets)
        for _ in range(max(depth, 1)):
            next_frontier: set[str] = set()
            for rel, imports in import_graph.items():
                if rel in impacted:
                    continue
                if any(target in imported for target in frontier for imported in imports):
                    impacted.add(rel)
                    next_frontier.add(rel.replace("/", ".").removesuffix(".py"))
            if not next_frontier:
                break
            frontier = next_frontier

        return [
            CodeRef(
                path=rel,
                line=1,
                symbol=rel,
                kind="impact",
                confidence="heuristic",
                provider=self.name,
            )
            for rel in sorted(impacted)
        ]


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None
