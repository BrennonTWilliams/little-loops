"""Gate: token/cost reads ``FROM usage_events`` only via the chokepoint (ENH-3528).

Scans ``scripts/little_loops/`` for SQL string constants that select a token or
cost column ``FROM usage_events`` and fails on any site outside
``history_reader.usage.select_usage_observations`` and the reasoned allowlist.
A bare ``SUM`` check would miss the Python-side aggregations, so this looks at
every SQL string literal instead.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent.parent / "little_loops"

_TOKEN_COST_COLUMNS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "cost_usd",
)
_FROM_USAGE = re.compile(r"\bFROM\s+usage_events\b", re.IGNORECASE)

# (path relative to scripts/little_loops, enclosing function) -> reason.
_ALLOWLIST: dict[tuple[str, str], str] = {
    ("history_reader/usage.py", "select_usage_observations"): "the chokepoint itself",
    ("history_reader/usage.py", "recent_usage_events"): "row listing, not aggregation",
}
# Whole files that only copy, write, rebuild or migrate rows.
_ALLOWLIST_FILES: dict[str, str] = {
    "session_store/queries.py": "shareable export: row copy of allowlisted columns",
    "session_store/writers.py": "write path",
    "session_store/lifecycle.py": "rebuild / lifecycle path",
    "session_store/schema.py": "schema and migration path",
}


def _enclosing_functions(tree: ast.AST) -> dict[int, str]:
    owner: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                owner[id(child)] = node.name
    return owner


def _violations() -> list[str]:
    found: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(_SRC_ROOT).as_posix()
        if rel in _ALLOWLIST_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        owner = _enclosing_functions(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            text = node.value
            if not _FROM_USAGE.search(text):
                continue
            if not any(col in text for col in _TOKEN_COST_COLUMNS):
                continue
            func = owner.get(id(node), "<module>")
            if (rel, func) not in _ALLOWLIST:
                found.append(f"{rel}:{node.lineno} in {func}()")
    return found


def test_no_token_or_cost_reads_outside_the_chokepoint() -> None:
    assert _violations() == []


def test_gate_detects_a_stray_site(tmp_path: Path) -> None:
    """The scan matches the pre-chokepoint shape of the aggregators it replaced."""
    sample = 'conn.execute("SELECT input_tokens, cost_usd FROM usage_events")'
    tree = ast.parse(sample)
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)]
    assert any(_FROM_USAGE.search(s) and any(c in s for c in _TOKEN_COST_COLUMNS) for s in strings)


def test_quality_regressions_query_is_not_flagged() -> None:
    """``session_id, model, COUNT(*)`` reads no token/cost column."""
    text = "SELECT session_id, model, COUNT(*) as cnt FROM usage_events GROUP BY 1"
    assert not any(col in text for col in _TOKEN_COST_COLUMNS)
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "little_loops"
        / "issue_history"
        / "quality_regressions.py"
    ).read_text()
    assert "channel = 'transcript'" in source
