"""Tests for the research-axis triage predicate (ENH-2971).

`triage_research_axes()` decides which of `/ll:refine-issue`'s three research
subagents actually need to spawn, from the issue file plus disk state alone.
Fixture-free `tmp_path` style, per `test_issues_anchors.py`.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from little_loops.issues.research_triage import (
    COVERAGE_THRESHOLD,
    AxisCoverage,
    triage_research_axes,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        check=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        },
    )


def _make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a git repo at *tmp_path* with *files* tracked and committed."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")
    return root


def _write_issue(root: Path, body: str, name: str = "P3-ENH-1-x.md") -> Path:
    issue_dir = root / ".issues" / "enhancements"
    issue_dir.mkdir(parents=True, exist_ok=True)
    path = issue_dir / name
    path.write_text(body, encoding="utf-8")
    return path


def _by_axis(result: tuple[AxisCoverage, ...]) -> dict[str, AxisCoverage]:
    return {c.axis: c for c in result}


SOURCE = "def helper():\n    return 1\n"


def _session_log(when: datetime | None) -> str:
    if when is None:
        return "\n## Session Log\n- `/ll:capture-issue` - 2026-01-01\n"
    stamp = when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return f"\n## Session Log\n- `/ll:refine-issue` - {stamp} - `abc.jsonl`\n"


# ---------------------------------------------------------------------------
# TestSparseIssue
# ---------------------------------------------------------------------------


class TestSparseIssue:
    """An issue with no resolving references covers no axis."""

    def test_no_sections_covers_nothing(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        issue = _write_issue(root, "# ENH-1\n\n## Summary\n\nSomething.\n")

        by_axis = _by_axis(triage_research_axes(issue, root))

        assert set(by_axis) == {"locator", "analyzer", "pattern_finder"}
        for coverage in by_axis.values():
            assert coverage.covered is False
            assert coverage.evidence == ""

    def test_sections_present_but_pathless_covers_nothing(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        issue = _write_issue(
            root,
            "# ENH-1\n\n"
            "## Integration Map\n\nSomething will change somewhere.\n\n"
            "## Root Cause\n\nThe logic is wrong.\n\n"
            "## Proposed Solution\n\nMake it right.\n",
        )

        for coverage in triage_research_axes(issue, root):
            assert coverage.covered is False


# ---------------------------------------------------------------------------
# TestLocatorAxis
# ---------------------------------------------------------------------------


class TestLocatorAxis:
    """The locator axis is satisfied by resolving Integration Map paths alone."""

    def test_all_paths_resolve_covers_locator(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE, "pkg/other.py": SOURCE})
        issue = _write_issue(
            root,
            "# ENH-1\n\n## Integration Map\n\n- `pkg/mod.py` — changes\n"
            "- `pkg/other.py` — changes\n",
        )

        locator = _by_axis(triage_research_axes(issue, root))["locator"]

        assert locator.covered is True
        assert "Integration Map" in locator.evidence
        assert "pkg/mod.py" in locator.evidence or "pkg/other.py" in locator.evidence

    def test_locator_needs_no_symbol(self, tmp_path: Path) -> None:
        """Bare paths satisfy locator; the other two axes still require a symbol."""
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        issue = _write_issue(root, "# ENH-1\n\n## Integration Map\n\n- `pkg/mod.py`\n")

        assert _by_axis(triage_research_axes(issue, root))["locator"].covered is True

    def test_below_threshold_fails(self, tmp_path: Path) -> None:
        """3 of 5 qualified paths resolving (60%) is under the 80% bar."""
        root = _make_repo(
            tmp_path, {f"pkg/mod{i}.py": SOURCE for i in range(3)} | {"pkg/x.py": SOURCE}
        )
        issue = _write_issue(
            root,
            "# ENH-1\n\n## Integration Map\n\n"
            "- `pkg/mod0.py`\n- `pkg/mod1.py`\n- `pkg/mod2.py`\n"
            "- `pkg/gone.py`\n- `pkg/vanished.py`\n",
        )

        assert _by_axis(triage_research_axes(issue, root))["locator"].covered is False

    def test_at_threshold_passes(self, tmp_path: Path) -> None:
        """4 of 5 qualified paths resolving (80%) meets the bar exactly."""
        assert COVERAGE_THRESHOLD == pytest.approx(0.8)
        root = _make_repo(tmp_path, {f"pkg/mod{i}.py": SOURCE for i in range(4)})
        issue = _write_issue(
            root,
            "# ENH-1\n\n## Integration Map\n\n"
            "- `pkg/mod0.py`\n- `pkg/mod1.py`\n- `pkg/mod2.py`\n- `pkg/mod3.py`\n"
            "- `pkg/gone.py`\n",
        )

        assert _by_axis(triage_research_axes(issue, root))["locator"].covered is True


# ---------------------------------------------------------------------------
# TestSymbolRequirement
# ---------------------------------------------------------------------------


class TestSymbolRequirement:
    """analyzer/pattern_finder need a co-located symbol; locator does not."""

    def test_root_cause_path_without_symbol_uncovered(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        issue = _write_issue(root, "# ENH-1\n\n## Root Cause\n\nThe file pkg/mod.py is wrong.\n")

        assert _by_axis(triage_research_axes(issue, root))["analyzer"].covered is False

    def test_root_cause_path_with_symbol_covered(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        issue = _write_issue(
            root,
            "# ENH-1\n\n## Root Cause\n\n`helper()` in `pkg/mod.py` returns the wrong value.\n",
        )

        analyzer = _by_axis(triage_research_axes(issue, root))["analyzer"]
        assert analyzer.covered is True
        assert "Root Cause" in analyzer.evidence

    def test_current_behavior_also_feeds_analyzer(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        issue = _write_issue(
            root,
            "# ENH-1\n\n## Current Behavior\n\n`helper()` in `pkg/mod.py` returns 1.\n",
        )

        assert _by_axis(triage_research_axes(issue, root))["analyzer"].covered is True

    def test_proposed_solution_path_without_symbol_uncovered(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        issue = _write_issue(root, "# ENH-1\n\n## Proposed Solution\n\nEdit pkg/mod.py.\n")

        assert _by_axis(triage_research_axes(issue, root))["pattern_finder"].covered is False

    def test_proposed_solution_path_with_symbol_covered(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        issue = _write_issue(
            root,
            "# ENH-1\n\n## Proposed Solution\n\nRewrite `helper()` in `pkg/mod.py`.\n",
        )

        assert _by_axis(triage_research_axes(issue, root))["pattern_finder"].covered is True


# ---------------------------------------------------------------------------
# TestReferenceFiltering
# ---------------------------------------------------------------------------


class TestReferenceFiltering:
    """Fenced refs don't count; unresolvable forms neither count nor sink an axis."""

    def test_fenced_ref_does_not_count(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        issue = _write_issue(
            root,
            "# ENH-1\n\n## Integration Map\n\n```\n- `pkg/mod.py`\n```\n",
        )

        assert _by_axis(triage_research_axes(issue, root))["locator"].covered is False

    def test_basename_and_glob_excluded_from_both_sides(self, tmp_path: Path) -> None:
        """A bare basename and a glob neither cover an axis nor break one."""
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        issue = _write_issue(
            root,
            "# ENH-1\n\n## Integration Map\n\n"
            "- `pkg/mod.py` — real\n"
            "- `executor.py` — bare basename\n"
            "- `skills/*/SKILL.md` — glob\n",
        )

        locator = _by_axis(triage_research_axes(issue, root))["locator"]
        assert locator.covered is True

    def test_only_unresolvable_forms_covers_nothing(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        issue = _write_issue(
            root,
            "# ENH-1\n\n## Integration Map\n\n- `executor.py`\n- `skills/*/SKILL.md`\n",
        )

        assert _by_axis(triage_research_axes(issue, root))["locator"].covered is False


# ---------------------------------------------------------------------------
# TestStalenessCheck
# ---------------------------------------------------------------------------


class TestStalenessCheck:
    """A resolving ref whose target changed after the last refine is not coverage."""

    def test_uncommitted_mtime_after_refine_is_stale(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        past = datetime.now(UTC) - timedelta(days=2)
        issue = _write_issue(
            root,
            "# ENH-1\n\n## Integration Map\n\n- `pkg/mod.py`\n" + _session_log(past),
        )
        # Working-tree edit, deliberately left uncommitted: git commit time is
        # still the seed commit, only mtime moves.
        (root / "pkg" / "mod.py").write_text(SOURCE + "# edited\n", encoding="utf-8")
        now = datetime.now(UTC).timestamp()
        os.utime(root / "pkg" / "mod.py", (now, now))

        locator = _by_axis(triage_research_axes(issue, root))["locator"]
        assert locator.covered is False
        assert "stale" in locator.evidence
        assert "pkg/mod.py" in locator.evidence

    def test_commit_after_refine_is_stale(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        past = datetime.now(UTC) - timedelta(days=2)
        issue = _write_issue(
            root,
            "# ENH-1\n\n## Integration Map\n\n- `pkg/mod.py`\n" + _session_log(past),
        )
        (root / "pkg" / "mod.py").write_text(SOURCE + "# edited\n", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "change")
        # Backdate mtime so only the git commit time can drive the verdict.
        old = (datetime.now(UTC) - timedelta(days=5)).timestamp()
        os.utime(root / "pkg" / "mod.py", (old, old))

        locator = _by_axis(triage_research_axes(issue, root))["locator"]
        assert locator.covered is False
        assert "stale" in locator.evidence

    def test_change_before_refine_stays_covered(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        old = (datetime.now(UTC) - timedelta(days=5)).timestamp()
        os.utime(root / "pkg" / "mod.py", (old, old))
        issue = _write_issue(
            root,
            "# ENH-1\n\n## Integration Map\n\n- `pkg/mod.py`\n" + _session_log(datetime.now(UTC)),
        )

        assert _by_axis(triage_research_axes(issue, root))["locator"].covered is True

    def test_no_prior_refine_skips_staleness(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        issue = _write_issue(
            root,
            "# ENH-1\n\n## Integration Map\n\n- `pkg/mod.py`\n" + _session_log(None),
        )
        now = datetime.now(UTC).timestamp()
        os.utime(root / "pkg" / "mod.py", (now, now))

        assert _by_axis(triage_research_axes(issue, root))["locator"].covered is True


# ---------------------------------------------------------------------------
# TestProgramDesignGateOverride
# ---------------------------------------------------------------------------


def _stamp_cutover(root: Path, date_str: str = "2026-01-01") -> None:
    import json

    ll_dir = root / ".ll"
    ll_dir.mkdir(exist_ok=True)
    (ll_dir / "program-design-cutover.json").write_text(
        json.dumps({"sha": "0" * 40, "date": date_str}), encoding="utf-8"
    )


_ANALYZER_ROOT_CAUSE = "## Root Cause\n\n`helper()` in `pkg/mod.py` returns the wrong value.\n"

_FRONTMATTER = "---\nid: ENH-1\ndiscovered_date: 2026-07-01\n---\n\n"

_SPECIFIC_DESIGN = (
    "## Program Design\n\n### Signatures\n\n- `helper() -> int`\n\n"
    "### Call Path\n\n`helper` -> `helper`\n"
)

_SPECIFIC_DESIGN_FENCED = (
    "## Program Design\n\n```\n### Signatures\n\n- `helper() -> int`\n\n"
    "### Call Path\n\n`helper` -> `helper`\n```\n"
)


class TestProgramDesignGateOverride:
    """BUG-3003: a failing Program Design gate forces the analyzer axis unmet."""

    def _gate_active_issue(self, tmp_path: Path, design_section: str) -> tuple[Path, Path]:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        _stamp_cutover(root)
        issue = _write_issue(
            root,
            _FRONTMATTER + "# ENH-1\n\n" + _ANALYZER_ROOT_CAUSE + "\n" + design_section,
            name="P3-ENH-1-x.md",
        )
        return root, issue

    def test_gate_active_missing_section_uncovers_analyzer(self, tmp_path: Path) -> None:
        root, issue = self._gate_active_issue(tmp_path, "")

        from little_loops.issues.program_design import program_design_gate_active

        content = issue.read_text(encoding="utf-8")
        assert program_design_gate_active(issue, content) is True

        analyzer = _by_axis(triage_research_axes(issue, root))["analyzer"]
        assert analyzer.covered is False
        assert analyzer.evidence

    def test_gate_active_empty_section_uncovers_analyzer(self, tmp_path: Path) -> None:
        root, issue = self._gate_active_issue(tmp_path, "## Program Design\n\n")

        analyzer = _by_axis(triage_research_axes(issue, root))["analyzer"]
        assert analyzer.covered is False
        assert analyzer.evidence

    def test_gate_active_boilerplate_section_uncovers_analyzer(self, tmp_path: Path) -> None:
        template = (
            "## Program Design\n\n### Types\n\n- `[FieldName]: [type]`\n\n"
            "### Signatures\n\n- `[function_name]([param]: [type]) -> [ReturnType]`\n\n"
            "### Call Path\n\n`[existing_caller]` -> `[new_function]` -> `[existing_callee]`\n"
        )
        root, issue = self._gate_active_issue(tmp_path, template)

        analyzer = _by_axis(triage_research_axes(issue, root))["analyzer"]
        assert analyzer.covered is False
        assert analyzer.evidence

    def test_gate_active_specific_section_leaves_analyzer_covered(self, tmp_path: Path) -> None:
        root, issue = self._gate_active_issue(tmp_path, _SPECIFIC_DESIGN)

        analyzer = _by_axis(triage_research_axes(issue, root))["analyzer"]
        assert analyzer.covered is True

    def test_gate_active_specific_fenced_section_leaves_analyzer_covered(
        self, tmp_path: Path
    ) -> None:
        """Regression: a fence-stripping extractor would false-positive here."""
        root, issue = self._gate_active_issue(tmp_path, _SPECIFIC_DESIGN_FENCED)

        analyzer = _by_axis(triage_research_axes(issue, root))["analyzer"]
        assert analyzer.covered is True

    def test_not_applicable_frontmatter_skips_override(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        _stamp_cutover(root)
        issue = _write_issue(
            root,
            "---\nid: ENH-1\ndiscovered_date: 2026-07-01\n"
            "program_design_not_applicable: true\n---\n\n"
            "# ENH-1\n\n" + _ANALYZER_ROOT_CAUSE,
            name="P3-ENH-1-x.md",
        )

        analyzer = _by_axis(triage_research_axes(issue, root))["analyzer"]
        assert analyzer.covered is True

    def test_gate_inactive_no_regression(self, tmp_path: Path) -> None:
        """No cutover stamp — legacy issues with no Program Design see no change."""
        root = _make_repo(tmp_path, {"pkg/mod.py": SOURCE})
        issue = _write_issue(
            root,
            _FRONTMATTER + "# ENH-1\n\n" + _ANALYZER_ROOT_CAUSE,
            name="P3-ENH-1-x.md",
        )

        from little_loops.issues.program_design import program_design_gate_active

        content = issue.read_text(encoding="utf-8")
        assert program_design_gate_active(issue, content) is False

        analyzer = _by_axis(triage_research_axes(issue, root))["analyzer"]
        assert analyzer.covered is True


# ---------------------------------------------------------------------------
# TestCorpusBaseline
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORPUS = _REPO_ROOT / ".issues"


def _corpus_issues() -> list[Path]:
    if not _CORPUS.is_dir():
        return []
    return sorted(p for p in _CORPUS.rglob("*.md") if p.name[0].isupper() or "-" in p.name)


@pytest.mark.slow
class TestCorpusBaseline:
    """Corpus-level gates from the issue's Acceptance Criteria.

    The ≥20% skip rate and ≤15pt band spread are both scored on the **coverage
    predicate** (``check_staleness=False``). That is what the issue calibrated
    them against: every row of ENH-2971's Expected Yield sensitivity table is a
    pure resolution rule, and the Staleness Check was never folded into a yield
    figure. Measured with staleness the same corpus scores 8.6% — recorded in
    the issue, and guarded separately by
    :meth:`test_full_predicate_is_not_inert` below, which is the regression
    class (a design that ships measurably dead) these gates exist to catch.
    """

    def test_skips_at_least_twenty_percent_of_axis_spawns(self) -> None:
        from little_loops.text_utils import build_ref_index

        issues = _corpus_issues()
        if len(issues) < 100:
            pytest.skip("issue corpus not available in this checkout")

        index = build_ref_index(_REPO_ROOT)
        covered = total = 0
        for issue in issues:
            for coverage in triage_research_axes(
                issue, _REPO_ROOT, index=index, check_staleness=False
            ):
                total += 1
                covered += bool(coverage.covered)

        assert total > 0
        assert covered / total >= 0.20, f"only {covered / total:.1%} of axis-spawns skipped"

    def test_full_predicate_is_not_inert(self) -> None:
        """With staleness on, the predicate must still skip a real share of spawns.

        The failure this catches is ENH-2971 Amendment 7's: a triage keyed on a
        reference form the corpus barely uses, which passed every unit test and
        would have skipped ~0.2% of spawns in production.
        """
        from little_loops.issues.research_triage import build_change_time_index
        from little_loops.text_utils import build_ref_index

        issues = _corpus_issues()
        if len(issues) < 100:
            pytest.skip("issue corpus not available in this checkout")

        index = build_ref_index(_REPO_ROOT)
        changes = build_change_time_index(_REPO_ROOT)
        covered = total = 0
        for issue in issues:
            for coverage in triage_research_axes(
                issue, _REPO_ROOT, index=index, change_times=changes
            ):
                total += 1
                covered += bool(coverage.covered)

        assert covered / total >= 0.05, f"predicate near-inert at {covered / total:.1%}"

    def test_locator_coverage_is_length_neutral(self) -> None:
        """Locator coverage must not encode Integration Map size (≤15pt spread)."""
        from little_loops.issues.research_triage import qualified_ref_count
        from little_loops.text_utils import build_ref_index

        issues = _corpus_issues()
        if len(issues) < 100:
            pytest.skip("issue corpus not available in this checkout")

        index = build_ref_index(_REPO_ROOT)
        bands = ((1, 2), (3, 5), (6, 10), (11, 20), (21, 10**6))
        tallies: dict[tuple[int, int], list[int]] = {b: [0, 0] for b in bands}
        for issue in issues:
            count = qualified_ref_count(issue, "locator", index=index)
            if count < 1:
                continue
            band = next(b for b in bands if b[0] <= count <= b[1])
            locator = _by_axis(
                triage_research_axes(issue, _REPO_ROOT, index=index, check_staleness=False)
            )["locator"]
            tallies[band][0] += bool(locator.covered)
            tallies[band][1] += 1

        rates = [hits / n for hits, n in tallies.values() if n >= 20]
        assert len(rates) >= 3, "not enough populated size bands to test neutrality"
        spread = (max(rates) - min(rates)) * 100
        assert spread <= 15.0, f"band spread {spread:.1f}pt exceeds the 15pt neutrality gate"
