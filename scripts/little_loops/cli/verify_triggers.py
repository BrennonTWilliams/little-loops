"""ll-verify-triggers: Validate skill description trigger accuracy.

Empirically validates whether each skill's ``description`` field fires correctly:
it should trigger on a set of realistic should-fire phrasings and stay silent on
a set of near-miss should-NOT-fire phrasings. Reports per-skill precision/recall
and a cross-skill collision matrix.

Only model-invocable skills are scored, and only skills that actually declare
``trigger_fixtures`` are measured; the rest are reported as unmeasured coverage
gaps. Exits non-zero when a *measured* skill falls below threshold or collides
with another skill (BUG-2879).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from little_loops.adapters.core import _is_model_invocation_disabled
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "shall",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "or",
        "and",
        "not",
        "no",
        "but",
        "if",
        "then",
        "else",
        "when",
        "where",
        "how",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "about",
        "above",
        "after",
        "again",
        "against",
        "any",
        "because",
        "before",
        "between",
        "into",
        "through",
        "during",
        "under",
        "over",
        "its",
        "it",
        "this",
        "that",
        "these",
        "those",
        "use",
        "used",
        "using",
        "also",
        "get",
        "got",
        "make",
        "made",
        "see",
    }
)

_MIN_WORD_LEN = 3


@dataclass
class TriggerFixtures:
    """Parsed trigger fixture data from a skill's frontmatter."""

    should_fire: list[str]
    should_not_fire: list[str]


@dataclass
class PrecisionRecall:
    """Precision and recall metrics for a single skill."""

    precision: float
    recall: float


@dataclass
class SkillTriggerResult:
    """Per-skill validation result."""

    skill_name: str
    description: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    precision: float = 0.0
    recall: float = 0.0
    false_positive_phrasings: list[str] = field(default_factory=list)
    false_negative_phrasings: list[str] = field(default_factory=list)
    measured: bool = False
    """True when the skill declared ``trigger_fixtures``.

    Unmeasured skills score 0.0/0.0 by construction and are excluded from the
    pass/fail computation — absence of fixtures is a coverage gap, not a
    threshold violation (BUG-2879).
    """


# Naming aliases for test compatibility
PhrasingFixture = TriggerFixtures


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------


def _extract_keywords(description: str) -> set[str]:
    """Extract matchable keywords from a skill description.

    Looks for an explicit ``Trigger keywords:`` line first; falls back to
    extracting all substantive words from the description body, filtering
    stopwords and short tokens.
    """
    for line in description.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("trigger keywords"):
            # Everything after the colon
            if ":" in stripped:
                trigger_text = stripped.split(":", 1)[1].strip()
            else:
                trigger_text = ""
            return _tokenize(trigger_text)

    # Fallback: tokenize the full description
    return _tokenize(description)


def _tokenize(text: str) -> set[str]:
    """Tokenize text into a set of normalized keywords."""
    tokens: set[str] = set()
    for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]*", text.lower()):
        if len(word) >= _MIN_WORD_LEN and word not in STOPWORDS:
            tokens.add(word)
    return tokens


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _match_phrasing(phrasing: str, keywords: set[str]) -> bool:
    """Return True if *phrasing* contains at least one keyword token."""
    phrasing_tokens = _tokenize(phrasing)
    return bool(phrasing_tokens & keywords)


def _match_score(phrasing: str, keywords: set[str]) -> int:
    """Number of keyword tokens found in the phrasing."""
    phrasing_tokens = _tokenize(phrasing)
    return len(phrasing_tokens & keywords)


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


def _load_trigger_fixtures(skill_md_path: Path) -> TriggerFixtures | None:
    """Parse trigger_fixtures from a SKILL.md frontmatter block.

    Returns None if the file has no trigger_fixtures or empty lists.
    """
    try:
        text = skill_md_path.read_text()
    except OSError:
        return None

    if not text.startswith("---"):
        return None

    end = text.find("---", 3)
    if end == -1:
        return None

    # Quick substring check before attempting YAML parse
    fm_text = text[3:end]
    if "trigger_fixtures" not in fm_text:
        return None

    import yaml

    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return None

    if not isinstance(fm, dict):
        return None

    fixtures = fm.get("trigger_fixtures")
    if not isinstance(fixtures, dict):
        return None

    should_fire = fixtures.get("should_fire", [])
    should_not_fire = fixtures.get("should_not_fire", [])

    if not isinstance(should_fire, list) or not isinstance(should_not_fire, list):
        return None

    if not should_fire and not should_not_fire:
        return None

    return TriggerFixtures(
        should_fire=[str(s) for s in should_fire],
        should_not_fire=[str(s) for s in should_not_fire],
    )


# ---------------------------------------------------------------------------
# Skill description loading
# ---------------------------------------------------------------------------


def _load_skill_descriptions(
    skills_dir: Path,
    model_invocable_only: bool = False,
) -> dict[str, tuple[str, Path]]:
    """Load (description, path) for all SKILL.md files under *skills_dir*.

    Returns a dict mapping skill name → (description, path).
    Skills without frontmatter or a description are skipped.

    When *model_invocable_only* is True, skills carrying a truthy
    ``disable-model-invocation`` are skipped as well — trigger accuracy is
    meaningless for a skill the model can never auto-invoke. The filter is
    opt-in so other callers (``issue_history.evolution._load_skill_keywords``)
    keep seeing the full population.
    """
    skills: dict[str, tuple[str, Path]] = {}

    if not skills_dir.is_dir():
        return skills

    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            text = skill_md.read_text()
        except OSError:
            continue

        if not text.startswith("---"):
            continue

        end = text.find("---", 3)
        if end == -1:
            continue

        fm_text = text[3:end]

        import yaml

        try:
            fm = yaml.safe_load(fm_text)
        except yaml.YAMLError:
            continue

        if not isinstance(fm, dict):
            continue

        if model_invocable_only and _is_model_invocation_disabled(fm):
            continue

        name = fm.get("name") or skill_md.parent.name
        desc = fm.get("description", "")
        if desc:
            skills[name] = (str(desc), skill_md)

    return skills


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------


def _compute_precision_recall(tp: int, fp: int, fn: int) -> PrecisionRecall:
    """Return (precision, recall) from confusion-matrix counts."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return PrecisionRecall(precision=precision, recall=recall)


def _detect_collisions(
    results: dict[str, SkillTriggerResult],
    phrasing_matches: dict[str, set[str]],
) -> list[dict]:
    """Detect cross-skill collisions from phrase-level match data.

    A collision occurs when a single phrasing triggered more than one skill.
    """
    collisions: list[dict] = []
    for phrasing, matched_skills in sorted(phrasing_matches.items()):
        if len(matched_skills) > 1:
            collisions.append(
                {
                    "phrasing": phrasing,
                    "skills": sorted(matched_skills),
                }
            )
    return collisions


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------


def _run_validation(
    skills_dir: Path,
    precision_threshold: float = 0.5,
    recall_threshold: float = 0.5,
) -> tuple[dict[str, SkillTriggerResult], list[dict], dict]:
    """Run full trigger validation across all skills.

    Returns (results_by_skill, collisions, thresholds_dict).
    """
    # 1. Load skill descriptions and extract keywords
    skill_descs = _load_skill_descriptions(skills_dir, model_invocable_only=True)
    skill_keywords: dict[str, set[str]] = {
        name: _extract_keywords(desc) for name, (desc, _) in skill_descs.items()
    }

    # 2. Load trigger fixtures per skill
    skill_fixtures: dict[str, TriggerFixtures] = {}
    for name, (_, path) in skill_descs.items():
        fixtures = _load_trigger_fixtures(path)
        if fixtures is not None:
            skill_fixtures[name] = fixtures

    # 3. Evaluate each skill with fixtures
    results: dict[str, SkillTriggerResult] = {}
    phrasing_matches: dict[str, set[str]] = defaultdict(set)

    for skill_name, (desc, _) in skill_descs.items():
        fixtures = skill_fixtures.get(skill_name)
        if fixtures is None:
            results[skill_name] = SkillTriggerResult(
                skill_name=skill_name,
                description=desc,
            )
            continue

        tp = 0
        fp = 0
        fn = 0
        fp_phrasings: list[str] = []
        fn_phrasings: list[str] = []

        # Evaluate should_fire phrasings
        for phrasing in fixtures.should_fire:
            # Check which skills this phrasing matches
            matched: list[str] = []
            for other_name, other_kw in skill_keywords.items():
                if _match_phrasing(phrasing, other_kw):
                    matched.append(other_name)

            if matched:
                phrasing_matches[phrasing] |= set(matched)

            if skill_name in matched:
                tp += 1
            else:
                fn += 1
                fn_phrasings.append(phrasing)

        # Evaluate should_not_fire phrasings
        for phrasing in fixtures.should_not_fire:
            matched_not: list[str] = []
            for other_name, other_kw in skill_keywords.items():
                if _match_phrasing(phrasing, other_kw):
                    matched_not.append(other_name)

            if matched_not:
                phrasing_matches[phrasing] |= set(matched_not)

            if skill_name in matched_not:
                fp += 1
                fp_phrasings.append(phrasing)

        pr = _compute_precision_recall(tp, fp, fn)
        results[skill_name] = SkillTriggerResult(
            skill_name=skill_name,
            description=desc,
            tp=tp,
            fp=fp,
            fn=fn,
            precision=pr.precision,
            recall=pr.recall,
            false_positive_phrasings=fp_phrasings,
            false_negative_phrasings=fn_phrasings,
            measured=True,
        )

    # 4. Detect collisions
    collisions = _detect_collisions(results, dict(phrasing_matches))

    thresholds = {
        "precision_threshold": precision_threshold,
        "recall_threshold": recall_threshold,
    }

    return results, collisions, thresholds


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def _coverage(results: dict[str, SkillTriggerResult]) -> tuple[int, int]:
    """Return (measured_count, total_count) over model-invocable skills."""
    return sum(1 for r in results.values() if r.measured), len(results)


def _format_text_report(
    results: dict[str, SkillTriggerResult],
    collisions: list[dict],
    thresholds: dict,
) -> str:
    """Format a human-readable text report."""
    measured_count, total = _coverage(results)
    lines: list[str] = []
    lines.append("Skill Trigger Validation Report")
    lines.append("=" * 50)
    lines.append(
        f"Thresholds: precision ≥ {thresholds['precision_threshold']:.0%}, "
        f"recall ≥ {thresholds['recall_threshold']:.0%}"
    )
    lines.append(
        f"Fixture coverage: {measured_count}/{total} model-invocable skill(s) "
        f"declare trigger_fixtures"
    )
    lines.append("")

    # Per-skill table — unmeasured skills are listed separately so a coverage
    # gap is never mistaken for a 0% score (BUG-2879).
    measured = [n for n in sorted(results) if results[n].measured]
    unmeasured = [n for n in sorted(results) if not results[n].measured]

    if measured:
        lines.append(f"{'Skill':<40} {'Precision':>10} {'Recall':>10}")
        lines.append(f"{'':-<40} {'':->10} {'':->10}")
        for name in measured:
            r = results[name]
            lines.append(f"{name:<40} {r.precision:>10.0%} {r.recall:>10.0%}")
        lines.append("")

    if unmeasured:
        lines.append(f"Unmeasured ({len(unmeasured)} skill(s) with no trigger_fixtures)")
        lines.append("=" * 50)
        for name in unmeasured:
            lines.append(f"  {name}")
        lines.append("")

    # Collisions — a clean result is only meaningful if some phrasings were
    # actually tested; with no fixtures the check is vacuous by construction.
    if collisions:
        lines.append("Cross-Skill Collisions")
        lines.append("=" * 50)
        for c in collisions:
            skills = ", ".join(c["skills"])
            lines.append(f'  Phrasing: "{c["phrasing"]}"')
            lines.append(f"  Colliding skills: {skills}")
            lines.append("")
    elif measured_count == 0:
        lines.append("Collision detection skipped: no trigger fixtures to test.")
        lines.append("")
    else:
        lines.append("No cross-skill collisions detected.")
        lines.append("")

    # Failures — scored skills only
    failures: list[str] = []
    for name in measured:
        r = results[name]
        if r.precision < thresholds["precision_threshold"]:
            failures.append(
                f"  {name}: precision {r.precision:.0%} < {thresholds['precision_threshold']:.0%}"
            )
        if r.recall < thresholds["recall_threshold"]:
            failures.append(
                f"  {name}: recall {r.recall:.0%} < {thresholds['recall_threshold']:.0%}"
            )

    if collisions:
        failures.append("  Collisions detected")
    if failures:
        lines.append("FAILURES")
        lines.append("=" * 50)
        for f in failures:
            lines.append(f)

    return "\n".join(lines)


def _format_json_report(
    results: dict[str, SkillTriggerResult],
    collisions: list[dict],
    thresholds: dict,
) -> str:
    """Format results as JSON."""
    skills_list = []
    for name in sorted(results):
        r = results[name]
        skills_list.append(
            {
                "name": r.skill_name,
                "description": r.description,
                "precision": r.precision,
                "recall": r.recall,
                "tp": r.tp,
                "fp": r.fp,
                "fn": r.fn,
                "false_positive_phrasings": r.false_positive_phrasings,
                "false_negative_phrasings": r.false_negative_phrasings,
                "measured": r.measured,
            }
        )

    measured_count, total = _coverage(results)

    return json.dumps(
        {
            "thresholds": thresholds,
            "coverage": {"measured": measured_count, "total": total},
            "skills": skills_list,
            "collisions": collisions,
            "collision_detection": "skipped" if measured_count == 0 else "run",
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _any_failures(
    results: dict[str, SkillTriggerResult],
    collisions: list[dict],
    precision_threshold: float,
    recall_threshold: float,
) -> bool:
    """True when any *measured* skill is below threshold or collisions exist.

    Skills with no ``trigger_fixtures`` are unmeasured and cannot fail a
    threshold they were never scored against (BUG-2879).
    """
    if collisions:
        return True
    for r in results.values():
        if not r.measured:
            continue
        if r.precision < precision_threshold:
            return True
        if r.recall < recall_threshold:
            return True
    return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main_verify_triggers() -> int:
    """Entry point for ll-verify-triggers CLI.

    Returns 0 when all skills meet threshold and there are no collisions;
    returns 1 otherwise.
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-triggers", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-verify-triggers",
            description=(
                "Validate skill description trigger accuracy against should-fire "
                "and should-NOT-fire phrasings. Reports per-skill precision/recall "
                "and cross-skill collision matrix."
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""\
Examples:
  %(prog)s                         # Validate all skills against default thresholds
  %(prog)s --json                  # Machine-readable JSON output
  %(prog)s --precision-threshold 0.8 --recall-threshold 0.6

Exit codes:
  0 - All measured skills meet thresholds, no collisions
  1 - A skill that declares trigger_fixtures is below threshold, or collisions

Only model-invocable skills are scored. A skill with no trigger_fixtures is
reported as unmeasured and never fails the exit code.
""",
        )
        parser.add_argument(
            "-C",
            "--directory",
            type=Path,
            default=None,
            help="Base directory (default: current directory)",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            default=False,
            help="Output results as JSON",
        )
        parser.add_argument(
            "--precision-threshold",
            type=float,
            default=0.5,
            metavar="F",
            help="Minimum precision required (default: 0.5)",
        )
        parser.add_argument(
            "--recall-threshold",
            type=float,
            default=0.5,
            metavar="F",
            help="Minimum recall required (default: 0.5)",
        )

        args = parser.parse_args()

        base_dir = args.directory or Path.cwd()
        skills_dir = base_dir / "skills"

        if not skills_dir.exists():
            print(
                f"ERROR: skills directory not found: {skills_dir}",
                file=sys.stderr,
            )
            return 1

        results, collisions, thresholds = _run_validation(
            skills_dir,
            precision_threshold=args.precision_threshold,
            recall_threshold=args.recall_threshold,
        )

        if args.json:
            print(_format_json_report(results, collisions, thresholds))
        else:
            print(_format_text_report(results, collisions, thresholds))

        if _any_failures(
            results,
            collisions,
            args.precision_threshold,
            args.recall_threshold,
        ):
            return 1
        return 0
