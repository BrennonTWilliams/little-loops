"""ll-issues set-scores: Write confidence and dimension scores to issue frontmatter."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from little_loops.config import BRConfig

SCORE_KEYS = (
    "confidence_score",
    "outcome_confidence",
    "score_complexity",
    "score_test_coverage",
    "score_ambiguity",
    "score_change_surface",
)
_SCORE_ARG_DESTS = (
    "confidence",
    "outcome",
    "score_complexity",
    "score_test_coverage",
    "score_ambiguity",
    "score_change_surface",
)

RISK_FACTORS_KEY = "risk_factors"
RISK_FACTOR_INPUT_ERROR_PREFIX = "Error: invalid risk factors:"
_MALFORMED_BASELINE_WARNING = "Warning: stored risk_factors baseline malformed; replaced"

_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
_CRITERION_RE = re.compile(r"[a-z][a-z0-9_-]{0,47}")
_DOMAINS = ("readiness", "outcome")
_MAX_DESCRIPTION_LEN = 200
_FACTOR_FIELDS = ("id", "domain", "criterion", "description")
# Fields that may change while an ID is retained, in the fixed reporting order.
_MUTABLE_FIELDS = ("domain", "criterion", "description")


class RiskFactorError(ValueError):
    """A risk-factor list failed validation."""


class _TargetError(Exception):
    """The issue's frontmatter target cannot be safely read or updated."""


@dataclass(frozen=True)
class RiskFactor:
    """One named, independently removable risk behind a confidence-check score."""

    id: str
    domain: str
    criterion: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "domain": self.domain,
            "criterion": self.criterion,
            "description": self.description,
        }


@dataclass(frozen=True)
class RetainedRiskFactor:
    """A factor present in both assessments: assessed fields plus what changed."""

    factor: RiskFactor
    changed_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {**self.factor.to_dict(), "changed_fields": list(self.changed_fields)}


@dataclass(frozen=True)
class RiskFactorDelta:
    """Membership comparison between two recorded factor lists, sorted by ID."""

    added: tuple[RiskFactor, ...]
    removed: tuple[RiskFactor, ...]
    retained: tuple[RetainedRiskFactor, ...]


def _validate_record(item: object) -> RiskFactor:
    if not isinstance(item, Mapping):
        raise RiskFactorError("each risk factor must be an object")
    keys = set(item)
    if keys != set(_FACTOR_FIELDS):
        missing = sorted(set(_FACTOR_FIELDS) - {str(k) for k in keys})
        extra = sorted(str(k) for k in keys - set(_FACTOR_FIELDS))
        raise RiskFactorError(
            f"risk factor fields must be exactly {_FACTOR_FIELDS} "
            f"(missing: {missing}, unexpected: {extra})"
        )
    for name in _FACTOR_FIELDS:
        if not isinstance(item[name], str):
            raise RiskFactorError(f"risk factor field '{name}' must be a string")
    factor = RiskFactor(
        id=item["id"],
        domain=item["domain"],
        criterion=item["criterion"],
        description=item["description"],
    )
    if _ID_RE.fullmatch(factor.id) is None:
        raise RiskFactorError(f"invalid id {factor.id!r}: must match {_ID_RE.pattern}")
    if factor.domain not in _DOMAINS:
        raise RiskFactorError(f"invalid domain {factor.domain!r}: must be one of {_DOMAINS}")
    if _CRITERION_RE.fullmatch(factor.criterion) is None:
        raise RiskFactorError(
            f"invalid criterion {factor.criterion!r}: must match {_CRITERION_RE.pattern}"
        )
    desc = factor.description
    if "\n" in desc or "\r" in desc:
        raise RiskFactorError(f"description for {factor.id!r} must be a single line")
    if not desc.strip():
        raise RiskFactorError(f"description for {factor.id!r} must not be blank")
    if len(desc) > _MAX_DESCRIPTION_LEN:
        raise RiskFactorError(
            f"description for {factor.id!r} exceeds {_MAX_DESCRIPTION_LEN} characters"
        )
    return factor


def _validate_records(data: object) -> list[RiskFactor]:
    if not isinstance(data, list):
        raise RiskFactorError("risk factors must be a list")
    factors = [_validate_record(item) for item in data]
    ids = [f.id for f in factors]
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise RiskFactorError(f"duplicate ids: {dupes}")
    return sorted(factors, key=lambda f: f.id)


def parse_risk_factors(raw: str) -> list[RiskFactor]:
    """Parse and validate a JSON array of risk-factor records; returns them sorted by ID.

    Pure: no I/O. Raises :class:`RiskFactorError` on any malformed input.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RiskFactorError(f"not valid JSON: {exc}") from exc
    return _validate_records(data)


def diff_risk_factors(previous: list[RiskFactor], assessed: list[RiskFactor]) -> RiskFactorDelta:
    """Compare two factor lists by exact ID; every entry list is sorted by ID."""
    prev = {f.id: f for f in previous}
    cur = {f.id: f for f in assessed}
    added = tuple(cur[i] for i in sorted(cur.keys() - prev.keys()))
    removed = tuple(prev[i] for i in sorted(prev.keys() - cur.keys()))
    retained = tuple(
        RetainedRiskFactor(
            factor=cur[i],
            changed_fields=tuple(
                name for name in _MUTABLE_FIELDS if getattr(prev[i], name) != getattr(cur[i], name)
            ),
        )
        for i in sorted(cur.keys() & prev.keys())
    )
    return RiskFactorDelta(added=added, removed=removed, retained=retained)


def _load_target(content: str) -> dict[str, Any] | None:
    """Parse the raw YAML of the block ``update_frontmatter`` would write to.

    Returns ``None`` when *content* has no frontmatter at all. Uses
    ``yaml.safe_load`` (matching the update writer) on the selected block —
    never the lenient reader — so an unparseable target is an error, not an
    absent baseline.
    """
    import yaml

    from little_loops.frontmatter import _canonical_frontmatter_block, _iter_frontmatter_blocks

    blocks = _iter_frontmatter_blocks(content)
    if not blocks:
        if content.startswith("---"):
            raise _TargetError("unterminated frontmatter fence")
        return None
    target = _canonical_frontmatter_block(blocks) or blocks[0]
    body_start, body_end = target.body_span
    try:
        loaded = yaml.safe_load(content[body_start:body_end])
    except yaml.YAMLError as exc:
        raise _TargetError(f"frontmatter is not valid YAML: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise _TargetError("frontmatter is not a mapping")
    return loaded


def _classify_baseline(raw: Mapping[str, Any] | None) -> tuple[str, list[RiskFactor] | None]:
    """Return ``(baseline, factors)``; *factors* is non-None only for ``present``."""
    if raw is None or RISK_FACTORS_KEY not in raw:
        return "absent", None
    try:
        return "present", _validate_records(raw[RISK_FACTORS_KEY])
    except RiskFactorError:
        return "malformed", None


def _presence(raw: Mapping[str, Any] | None) -> str:
    return "present" if raw is not None and RISK_FACTORS_KEY in raw else "absent"


def _clear_scores_unlocked(path: Path) -> bool:
    from little_loops.file_utils import atomic_write
    from little_loops.frontmatter import remove_frontmatter_keys

    content = path.read_text()
    new_content = remove_frontmatter_keys(content, SCORE_KEYS)
    changed = new_content != content
    if changed:
        atomic_write(path, new_content, shared_mode=True)
    return changed


def clear_scores(path: Path, *, base_dir: str = ".issues") -> bool:
    """Remove the six score keys from *path*'s frontmatter; returns whether anything changed.

    Locked and atomic — matching :func:`apply_status_transition`
    (``cli/issues/set_status.py``) — unlike ``cmd_set_scores``'s previous
    inline ``--clear`` branch, which read-modify-wrote unlocked with plain
    ``write_text``. Extracted (ENH-3630) so ``set-scores --clear`` and the
    preparation policy's ``clear_scores`` precondition share one writer.
    *base_dir* must be the project's configured issues base so every mutator
    derives the same tree lock. Risk factors (the last-recorded baseline) are
    never removed.
    """
    from little_loops.file_utils import acquire_lock, issue_lock_path

    with acquire_lock(issue_lock_path(path, base_dir)):
        return _clear_scores_unlocked(path)


def _read_factor_input(source: str) -> list[RiskFactor]:
    if source == "-":
        raw = sys.stdin.read()
    else:
        from pathlib import Path

        try:
            raw = Path(source).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise RiskFactorError(f"cannot read '{source}': {exc}") from exc
    return parse_risk_factors(raw)


def _factor_json(
    factors: list[RiskFactor],
    baseline: str,
    delta: RiskFactorDelta | None,
) -> dict[str, Any]:
    return {
        "recorded": True,
        "baseline": baseline,
        "factors": [f.to_dict() for f in factors],
        "added": None if delta is None else [f.to_dict() for f in delta.added],
        "removed": None if delta is None else [f.to_dict() for f in delta.removed],
        "retained": None if delta is None else [r.to_dict() for r in delta.retained],
    }


def _fail(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return 1


def cmd_set_scores(config: BRConfig, args: argparse.Namespace) -> int:
    """Write confidence and outcome scores (and optional risk factors) into an issue.

    Idempotent: calling with the same values has no net effect. Only the
    flags that are explicitly provided are written; omitted flags leave the
    corresponding frontmatter field unchanged. ``--clear`` instead removes the
    six score keys (absent keys are a no-op) and is exclusive with score and
    factor arguments. ``--risk-factors-file`` replaces the complete stored
    ``risk_factors`` list and reports a deterministic comparison against the
    previous list (see ``--json``).

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id and optional score flags

    Returns:
        Exit code (0 = success, 1 = error)
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.cli.output import print_json
    from little_loops.file_utils import acquire_lock, atomic_write, issue_lock_path
    from little_loops.frontmatter import update_frontmatter
    from little_loops.issue_parser import IssueParser

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    want_json = bool(getattr(args, "json", False))
    factor_source: str | None = getattr(args, "risk_factors_file", None)
    has_scores = any(getattr(args, dest, None) is not None for dest in _SCORE_ARG_DESTS)
    lock_path = issue_lock_path(path, config.issues.base_dir)

    issue_id = ""
    if want_json:
        try:
            issue_id = IssueParser(config).parse_file(path).issue_id
        except Exception as exc:  # noqa: BLE001 — any parse failure is operational
            return _fail(f"cannot read issue '{args.issue_id}': {exc}")

    if getattr(args, "clear", False):
        if has_scores or factor_source is not None:
            print(
                "Error: --clear cannot be combined with score or risk-factor arguments.",
                file=sys.stderr,
            )
            return 1
        try:
            with acquire_lock(lock_path):
                presence = "absent"
                if want_json:
                    presence = _presence(_load_target(path.read_text()))
                changed = _clear_scores_unlocked(path)
        except (_TargetError, OSError) as exc:
            return _fail(str(exc))
        if want_json:
            print_json(
                {
                    "issue_id": issue_id,
                    "cleared": changed,
                    "risk_factors": {"recorded": False, "baseline": presence},
                }
            )
        return 0

    factors: list[RiskFactor] | None = None
    if factor_source is not None:
        try:
            factors = _read_factor_input(factor_source)
        except RiskFactorError as exc:
            print(f"{RISK_FACTOR_INPUT_ERROR_PREFIX} {exc}", file=sys.stderr)
            return 1

    updates: dict[str, Any] = {}
    if args.confidence is not None:
        updates["confidence_score"] = args.confidence
    if args.outcome is not None:
        updates["outcome_confidence"] = args.outcome
    if args.score_complexity is not None:
        updates["score_complexity"] = args.score_complexity
    if args.score_test_coverage is not None:
        updates["score_test_coverage"] = args.score_test_coverage
    if args.score_ambiguity is not None:
        updates["score_ambiguity"] = args.score_ambiguity
    if args.score_change_surface is not None:
        updates["score_change_surface"] = args.score_change_surface

    if not updates and factors is None:
        print("Warning: no score flags provided; nothing to write.", file=sys.stderr)
        if want_json:
            try:
                with acquire_lock(lock_path):
                    presence = _presence(_load_target(path.read_text()))
            except (_TargetError, OSError) as exc:
                return _fail(str(exc))
            print_json(
                {
                    "issue_id": issue_id,
                    "risk_factors": {"recorded": False, "baseline": presence},
                }
            )
        return 0

    baseline = "absent"
    delta: RiskFactorDelta | None = None
    try:
        with acquire_lock(lock_path):
            content = path.read_text()
            raw = _load_target(content)
            fm_updates = dict(updates)
            if factors is not None:
                baseline, previous = _classify_baseline(raw)
                if previous is not None:
                    delta = diff_risk_factors(previous, factors)
                fm_updates[RISK_FACTORS_KEY] = [f.to_dict() for f in factors]
            else:
                baseline = _presence(raw)
            atomic_write(path, update_frontmatter(content, fm_updates), shared_mode=True)
    except (_TargetError, OSError) as exc:
        return _fail(str(exc))

    if factors is not None and baseline == "malformed":
        print(_MALFORMED_BASELINE_WARNING, file=sys.stderr)
    if want_json:
        if factors is not None:
            result: dict[str, Any] = _factor_json(factors, baseline, delta)
        else:
            result = {"recorded": False, "baseline": baseline}
        print_json({"issue_id": issue_id, "risk_factors": result})
    return 0
