"""Deterministic frontmatter-to-score encoder for the ``issue_lifecycle`` policy mode.

Backs the ``frontmatter_scores`` fragment in ``lib/policy-router.yaml`` (FEAT-3474):
a shell state resolves an issue's frontmatter and writes per-dimension score files
that ``policy_table_dispatch`` (also in that fragment file) already consumes, in
place of the LLM ``rubric_score`` + ``policy_parse_scores`` pair used by the
``decision_table``/``rubric`` modes. This lets a policy-router loop route on an
Issue file's YAML frontmatter without any LLM call.

The encoding rules implemented here are shared verbatim with the JS
``encodeFrontmatterScores`` mirror in ``policy_builder_core.mjs`` (used by the
builder's Try-it panel) — see the issue's "Encoding Rules" section for the
authoritative spec. Both encoders are pinned against the same conformance
corpus so they can't silently drift.

Public API:
    encode_frontmatter_scores(fm, dims) -> dict[str, str]
    main(issue_id, dims_text, run_dir)  -> int
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_TRUTHY = {"true", "yes", "on", "1"}
_PRIORITY_RANK_RE = re.compile(r"^P(\d)$")


def _normalize_dim_name(name: str) -> str:
    """Lowercase + spaces->hyphens; underscores untouched.

    Mirrors ``normalizeDimName()`` in ``policy_builder_core.mjs`` so the
    filenames this module writes match the dim names ``_serializeRulesText()``
    emits into ``context.policy_rules``.
    """
    return re.sub(r"\s+", "-", name.strip().lower())


def _encode_boolean(value: object) -> str:
    """100 when string-truthy (true/yes/on/1, case-insensitive), else 0. Always written."""
    if isinstance(value, str) and value.strip().lower() in _TRUTHY:
        return "100"
    return "0"


def _encode_numeric(value: object) -> str | None:
    """Scalar written verbatim; list -> len(list); absent/None -> omitted (no file)."""
    if value is None:
        return None
    if isinstance(value, list):
        return str(len(value))
    return str(value)


def _encode_list(value: object) -> str:
    """Count semantics: list -> len(list); non-empty non-list scalar -> 1; absent/None/[] -> 0.

    Always written.
    """
    if value is None:
        return "0"
    if isinstance(value, list):
        return str(len(value))
    return "1"


def _encode_string(value: object) -> str | None:
    """str(value).strip(); absent/None -> omitted (no file)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def encode_frontmatter_scores(
    fm: dict[str, str | list | None], dims: list[tuple[str, str]]
) -> dict[str, str]:
    """Encode parsed issue frontmatter into per-dimension score text, per dim type.

    Pure function: ``fm`` is the dict returned by
    ``little_loops.frontmatter.parse_frontmatter(content, coerce_types=False)``
    (values are ``str``, ``list``, or ``None`` — never Python ``bool``/``int``,
    since that parser loads with ``yaml.BaseLoader``). ``dims`` is a list of
    ``(raw_frontmatter_key, type)`` pairs, ``type`` one of ``"boolean"``,
    ``"numeric"``, ``"list"``, ``"string"``.

    The special dim name ``"priority_rank"`` is not looked up directly in
    ``fm`` — it has no literal frontmatter key of its own. It is instead
    *derived* from ``fm.get("priority")``: when present and, after
    ``.strip()``, matching ``^P(\\d)$``, the digit is written; any other value
    (absent, ``None``, non-matching such as ``"high"``) omits the file. This
    is the only derived dimension; every other dim is encoded from its own raw
    key.

    Returns a dict keyed by the **normalized** dim name (lowercase,
    spaces->hyphens, underscores untouched — mirrors ``normalizeDimName()`` in
    ``policy_builder_core.mjs``) to the score text to write. Dims whose
    encoding rule omits the file (absent/null numeric or string, non-matching
    ``priority_rank``) are absent from the returned dict.
    """
    result: dict[str, str] = {}
    for raw_key, dim_type in dims:
        normalized = _normalize_dim_name(raw_key)

        if raw_key == "priority_rank":
            priority_value = fm.get("priority")
            if isinstance(priority_value, str):
                match = _PRIORITY_RANK_RE.match(priority_value.strip())
                if match:
                    result[normalized] = match.group(1)
            continue

        value = fm.get(raw_key)

        if dim_type == "boolean":
            result[normalized] = _encode_boolean(value)
        elif dim_type == "numeric":
            encoded = _encode_numeric(value)
            if encoded is not None:
                result[normalized] = encoded
        elif dim_type == "list":
            result[normalized] = _encode_list(value)
        elif dim_type == "string":
            encoded = _encode_string(value)
            if encoded is not None:
                result[normalized] = encoded
        # Unknown dim types are silently ignored — the builder UI is the
        # only writer of context.frontmatter_dimensions and only emits the
        # four known types.

    return result


def _parse_dims_text(dims_text: str) -> list[tuple[str, str]]:
    """Parse ``name:type|name:type|...`` into ``[(raw_key, type), ...]``.

    Blank segments (e.g. trailing ``|``, empty input) are skipped. A segment
    with no ``:`` is skipped rather than raising — malformed
    ``context.frontmatter_dimensions`` should not crash the scorer state.
    """
    dims: list[tuple[str, str]] = []
    for segment in dims_text.split("|"):
        segment = segment.strip()
        if not segment or ":" not in segment:
            continue
        raw_key, _, dim_type = segment.partition(":")
        raw_key = raw_key.strip()
        dim_type = dim_type.strip()
        if raw_key and dim_type:
            dims.append((raw_key, dim_type))
    return dims


def _clean_slate(run_dir: Path) -> None:
    """Delete every ``rubric-dim-*.txt`` and ``rubric-aggregate.txt`` in ``run_dir``.

    ``run_dir`` persists for the whole loop run and ``policy_table_dispatch``
    reads every ``rubric-dim-*.txt`` present, so "absent -> no file" is only
    true across score passes if stale files from a prior pass are removed
    first (e.g. a field present on pass 1 and cleared by pass 2).
    """
    for path in run_dir.glob("rubric-dim-*.txt"):
        path.unlink(missing_ok=True)
    aggregate_path = run_dir / "rubric-aggregate.txt"
    aggregate_path.unlink(missing_ok=True)


def main(issue_id: str, dims_text: str, run_dir: str) -> int:
    """Resolve, clean slate, parse, encode, write. Returns 0 on success, 1 if unresolved.

    ``resolve_issue_path`` returns ``None`` rather than raising for an
    unresolvable ID, so this returns 1 without touching ``run_dir`` in that
    case — the caller (the ``frontmatter_scores`` fragment) must set
    ``on_error: failed`` for the non-zero exit to have any effect on routing.
    """
    # Imported lazily so this module has no import-time dependency on the
    # heavier issue-parsing stack, matching how policy_table_dispatch's
    # heredoc imports little_loops.fsm.policy_rules only when it runs.
    from little_loops.config import BRConfig
    from little_loops.frontmatter import parse_frontmatter
    from little_loops.issue_parser import resolve_issue_path
    from little_loops.paths import find_project_root

    # find_project_root returns None only when no .git/.ll boundary exists
    # anywhere above cwd; falling back to cwd itself keeps BRConfig's
    # constructor (which requires a Path) total instead of raising, while
    # matching every realistic invocation (a loop run from within a project).
    project_root = find_project_root(Path.cwd()) or Path.cwd()
    config = BRConfig(project_root)
    issue_path = resolve_issue_path(config, issue_id)
    if issue_path is None:
        return 1

    run_dir_path = Path(run_dir)
    os.makedirs(run_dir_path, exist_ok=True)
    _clean_slate(run_dir_path)

    content = issue_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(content, coerce_types=False)
    dims = _parse_dims_text(dims_text)
    scores = encode_frontmatter_scores(fm, dims)

    for normalized_name, text in scores.items():
        score_path = run_dir_path / f"rubric-dim-{normalized_name}.txt"
        score_path.write_text(text, encoding="utf-8")

    return 0
