"""Clean-slate parser for LLM rubric scoring output (BUG-3489).

Backs the ``policy_parse_scores`` fragment in ``lib/policy-router.yaml``: a
shell state re-parses a prior ``rubric_score`` state's captured LLM output
into per-dimension score files consumed by ``policy_table_dispatch``. Every
invocation first clears ``rubric-dim-*.txt`` / ``rubric-aggregate.txt`` in
``run_dir`` (mirroring ``frontmatter_scores._clean_slate()``) so a dimension
or aggregate omitted on this pass cannot be satisfied by a stale file from a
prior pass in the same run directory.

An omitted ``AGGREGATE:`` line and an omitted ``DIMENSION:`` line are both
valid partial evidence and simply write no file for that key — routing must
never see a score the scorer did not emit. Wholly unparseable output (no
recognized ``AGGREGATE:`` or ``DIMENSION:`` line at all) raises/exits
non-zero rather than fabricating an aggregate of ``0``; callers must route a
non-zero exit to a failure terminal via ``on_error``.

Public API:
    parse_scores(output) -> (aggregate, dimensions)
    main(argv)            -> int
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_AGGREGATE_RE = re.compile(r"AGGREGATE:\s*(\d+)", re.IGNORECASE)
_DIMENSION_RE = re.compile(r"DIMENSION:\s*([\w][\w\s\-]+?):\s*(\d+)", re.IGNORECASE)


def parse_scores(output: str) -> tuple[int | None, dict[str, str]]:
    """Extract the aggregate score and per-dimension scores from rubric output.

    Returns ``(aggregate, dimensions)`` where ``aggregate`` is ``None`` when
    no ``AGGREGATE:`` line is recognized (recognized dimensions alone are
    valid) and ``dimensions`` maps normalized dimension name (lowercase,
    spaces->hyphens) to its raw score text. A later duplicate ``DIMENSION:``
    line for the same normalized name overwrites an earlier one, matching
    the fragment's prior file-overwrite behavior.

    Raises ``ValueError`` when output has neither a recognized aggregate nor
    any recognized dimension — wholly unparseable output is a hard failure,
    not an implicit zero.
    """
    agg_match = _AGGREGATE_RE.search(output)
    aggregate = int(agg_match.group(1)) if agg_match else None

    dimensions: dict[str, str] = {}
    for match in _DIMENSION_RE.finditer(output):
        dim_name = re.sub(r"\s+", "-", match.group(1).strip().lower())
        dimensions[dim_name] = match.group(2).strip()

    if aggregate is None and not dimensions:
        raise ValueError("no recognized AGGREGATE or DIMENSION line in scoring output")

    return aggregate, dimensions


def _clean_slate(run_dir: Path) -> None:
    """Delete every ``rubric-dim-*.txt`` and ``rubric-aggregate.txt`` in ``run_dir``.

    Cleanup failures (e.g. a permissions error) propagate to the caller —
    silently continuing past a failed unlink would let a stale file survive
    into a pass that's supposed to guarantee a clean slate.
    """
    for path in run_dir.glob("rubric-dim-*.txt"):
        path.unlink(missing_ok=True)
    (run_dir / "rubric-aggregate.txt").unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    """Clean, read, parse, and publish scores for one ``run_dir``. Returns 0 on success.

    ``argv[0]`` is the run directory; it is created if absent. Reads the raw
    LLM output already materialized by the caller at
    ``run_dir/policy_parse_scores-scores.txt`` (this module does not write
    that file — the shell fragment does, and checks that write's own exit
    status before invoking this module, so a failed raw-input write can
    never cause a stale file to be parsed). Cleanup, read, parse, and write
    failures all print a diagnostic to stderr and return 1.
    """
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("policy_parse_scores: missing required <run_dir> argument", file=sys.stderr)
        return 1

    run_dir = Path(args[0])

    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        _clean_slate(run_dir)
        output = (run_dir / "policy_parse_scores-scores.txt").read_text(encoding="utf-8")
    except OSError as exc:
        print(f"policy_parse_scores: {exc}", file=sys.stderr)
        return 1

    try:
        aggregate, dimensions = parse_scores(output)
    except ValueError as exc:
        print(f"policy_parse_scores: {exc}", file=sys.stderr)
        return 1

    try:
        if aggregate is not None:
            (run_dir / "rubric-aggregate.txt").write_text(str(aggregate), encoding="utf-8")
        for dim_name, score in dimensions.items():
            (run_dir / f"rubric-dim-{dim_name}.txt").write_text(score, encoding="utf-8")
    except OSError as exc:
        print(f"policy_parse_scores: {exc}", file=sys.stderr)
        return 1

    if aggregate is not None:
        print(f"aggregate={aggregate}")
    for dim_name, score in dimensions.items():
        print(f"dim={dim_name} score={score}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
