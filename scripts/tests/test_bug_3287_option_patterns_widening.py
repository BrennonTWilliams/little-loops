"""BUG-3287 part 2: `_OPTION_PATTERNS[3]` (`bullet` tier) widening + the
corpus differential that guards it.

The live `.issues/` corpus is not a stable fixture -- it grows and edits daily,
so a full corpus-wide before/after diff cannot be a permanent, pinned
assertion (see BUG-3287 Tests -> Corpus differential -> "mechanism +
persistence" note). What IS pinned here, permanently:

- A frozen-fixture regression for the seven files BUG-3287 measured by name at
  implementation time: the four "movers" whose resolved `heading` or `count`
  changes in a way the 15-shape regex matrix alone would not catch
  (BUG-3229, ENH-3264, ENH-2164, ENH-2358), two of the seven directive-1
  preempted issues confirming part 2 does not regress their (already-fixed by
  part 1) `residual_directive` reporting (BUG-1183, ENH-2446), and one
  representative `0 -> N` newly-decidable sample (FEAT-3151). Fixture copies
  live under `fixtures/issues/bug3287_corpus/`.
- The 15-shape match matrix for `_OPTION_PATTERNS[3]` and `_extract_option_label`.
- A content-independent crash-safety sweep over the live corpus (mirrors
  `TestUnappliedDecisionLiveCorpusSweep`), which is safe to keep permanent
  because it asserts no exception, not a value comparison.

A full live-corpus differential (no count decreases / no heading changes
except the four pinned movers) was run as a landing gate during
implementation per BUG-3287 Implementation Steps 3 and 6, not committed here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "issues" / "bug3287_corpus"


class TestOptionPatternsTier3MatchMatrix:
    """BUG-3287 part 2: the 15-shape match matrix verified against the widened
    `_OPTION_PATTERNS[3]` regex -- every previously-matching shape still
    matches (strict superset), plus the newly-reachable bold-wrapped/relaxed
    shapes, plus explicit non-goals."""

    MATRIX = (
        ("- (a) foo", True),
        ("* Option B: x", True),
        ("- **Option B** x", True),
        ("- **(a) foo**", True),
        ("- *(a)* foo", True),
        ("- (a)foo", True),
        ("- (a): text", True),
        ("- (a)", True),
        ("- some bullet", False),
        ("- optional extras", False),
        ("- **Options** are", False),
        ("1. (a) foo", False),
        ("  - (a) indented", False),
        ("-(a) foo", False),
        ("- ***(a)*** foo", False),
    )

    @pytest.mark.parametrize("shape,expected", MATRIX)
    def test_shape(self, shape: str, expected: bool) -> None:
        from little_loops.issue_parser import _OPTION_PATTERNS

        matched = bool(_OPTION_PATTERNS[3].search(shape))
        assert matched == expected, f"{shape!r}: expected match={expected}, got {matched}"


class TestExtractOptionLabelBoldWrapped:
    """BUG-3287 part 2: `_extract_option_label` gains the same `\\*{0,2}` hoist
    so bold-wrapped markers strip to the same label as plain ones."""

    def test_plain_marker_label(self) -> None:
        from little_loops.issue_parser import _extract_option_label

        assert _extract_option_label("- (a) foo") == "foo"

    def test_bold_wrapped_marker_label_matches_plain(self) -> None:
        from little_loops.issue_parser import _extract_option_label

        assert _extract_option_label("- **(a) foo**") == "foo"


class TestCorpusDifferentialFrozenFixtures:
    """BUG-3287 pinned corpus differential, frozen at implementation time.

    Reproduces the corpus-wide diff mechanism (old tier-3 regex literal,
    monkeypatched, vs the live widened regex) against seven frozen copies of
    real `.issues/` files rather than the live, ever-changing corpus -- so
    this stays deterministic across runs.
    """

    # BUG-3287 Proposed Solution -- the pre-widening tier-3 regex, kept here as
    # a literal (not a reference to the live pattern) so this test cannot
    # become vacuously self-comparing if the live regex changes again later.
    _OLD_TIER3_RE = r"^[-*]\s+(?:\([a-z0-9]\)\s+|\*{0,2}Option\s+[A-Za-z0-9])"

    _PINNED = {
        "BUG-3229": {
            "before": (2, "provisional_e", "Proposed Solution"),
            "after": (1, "bullet", "Proposed Solution"),
        },
        "ENH-3264": {
            "before": (1, "numbered", "Confidence Check Notes"),
            "after": (2, "bullet", "Proposed Solution"),
        },
        "ENH-2164": {
            "before": (1, "numbered", "Reopened"),
            "after": (
                3,
                "bullet",
                "Relationship to ENH-2165, rn-remediate, and Conjunctive Rules",
            ),
        },
        "ENH-2358": {
            "before": (2, "numbered", "Implementation Steps"),
            "after": (3, "bullet", "Expected Behavior"),
        },
        # Two of the seven defect-1-preempted issues: part 2 must not disturb
        # their already-fixed (by part 1) residual_directive reporting -- count
        # and heading stay stable, only the newly-reachable shapes elsewhere in
        # the corpus should move.
        "BUG-1183": {
            "before": (2, "bold_label", "Proposed Solution"),
            "after": (2, "bold_label", "Proposed Solution"),
        },
        "ENH-2446": {
            "before": (2, "bullet", "Proposed Solution"),
            "after": (2, "bullet", "Proposed Solution"),
        },
        # A representative 0 -> N newly-decidable sample.
        "FEAT-3151": {
            "before": (0, None, None),
            "after": (2, "bullet", "Decisions"),
        },
    }

    def _locate_with_pattern(self, content: str, tier3_pattern):
        import little_loops.issue_parser as ip

        original = ip._OPTION_PATTERNS
        patched = list(original)
        patched[3] = tier3_pattern
        ip._OPTION_PATTERNS = tuple(patched)
        try:
            return ip.locate_enumerable_options(content)
        finally:
            ip._OPTION_PATTERNS = original

    @pytest.mark.parametrize("issue_id", sorted(_PINNED))
    def test_pinned_before_after(self, issue_id: str) -> None:
        import re

        from little_loops.issue_parser import locate_enumerable_options

        path = FIXTURE_DIR / f"{issue_id}.md"
        assert path.exists(), f"missing frozen fixture: {path}"
        content = path.read_text(encoding="utf-8")

        old_re = re.compile(self._OLD_TIER3_RE, re.MULTILINE | re.IGNORECASE)
        before = self._locate_with_pattern(content, old_re)
        after = locate_enumerable_options(content)

        expected_before = self._PINNED[issue_id]["before"]
        expected_after = self._PINNED[issue_id]["after"]
        assert (before.count, before.pattern, before.heading) == expected_before, (
            f"{issue_id} before-state drifted from the pinned frozen fixture"
        )
        assert (after.count, after.pattern, after.heading) == expected_after, (
            f"{issue_id} after-state (live widened regex) diverged from the pinned expectation"
        )


class TestOptionPatternsLiveCorpusSweepDoesNotCrash:
    """Content-independent crash-safety sweep over the live `.issues/` corpus
    (mirrors TestUnappliedDecisionLiveCorpusSweep's style) -- safe to keep
    permanent since it never compares against a stored baseline."""

    def test_corpus_sweep_does_not_crash(self) -> None:
        from little_loops.issue_parser import locate_enumerable_options

        issues_dir = Path(__file__).parent.parent.parent / ".issues"
        if not issues_dir.exists():
            pytest.skip("no .issues/ corpus in this checkout")
        for path in issues_dir.rglob("*.md"):
            content = path.read_text(encoding="utf-8", errors="ignore")
            located = locate_enumerable_options(content)
            assert located.count >= 0
            if located.residual_directive is not None:
                rd = located.residual_directive
                assert rd.pattern == "provisional_e"
                assert rd.count == 2
                assert len(rd.options) == 1
                assert rd.residual_directive is None
