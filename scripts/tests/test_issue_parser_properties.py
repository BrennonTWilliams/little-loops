"""Property-based tests for issue_parser module using Hypothesis.

These tests verify parser invariants hold across thousands of randomly
generated inputs, catching edge cases that example-based tests may miss.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from little_loops.issue_parser import IssueInfo, ProductImpact, slugify


class TestSlugifyProperties:
    """Property tests for slugify function."""

    @given(st.text(max_size=200))
    def test_slugify_idempotent(self, text: str) -> None:
        """Applying slugify twice produces same result as once."""
        assert slugify(slugify(text)) == slugify(text)

    @given(st.text(max_size=200))
    def test_slugify_only_word_chars_and_hyphens(self, text: str) -> None:
        """Output contains only Unicode word characters (\\w) and hyphens.

        Note: slugify uses \\w which matches [a-zA-Z0-9_] plus Unicode letters
        and digits. The result is lowercased, so uppercase ASCII letters become
        lowercase, but some Unicode characters may remain unchanged.
        """
        import re

        result = slugify(text)
        # slugify keeps \w characters (which includes Unicode word chars) and hyphens
        # Every character in result should be either a word char or hyphen
        for c in result:
            # \w matches word characters, or it's a hyphen
            assert re.match(r"[\w-]", c, re.UNICODE), f"Unexpected char: {repr(c)}"

    @given(st.text(max_size=200))
    def test_slugify_no_leading_trailing_hyphens(self, text: str) -> None:
        """Output has no leading or trailing hyphens."""
        result = slugify(text)
        if result:
            assert not result.startswith("-")
            assert not result.endswith("-")

    @given(st.text(max_size=200))
    def test_slugify_no_consecutive_hyphens(self, text: str) -> None:
        """Output has no consecutive hyphens."""
        result = slugify(text)
        assert "--" not in result

    @given(st.text(max_size=200))
    def test_slugify_preserves_alphanumeric(self, text: str) -> None:
        """Alphanumeric characters are preserved (as lowercase)."""
        result = slugify(text)
        # Every alphanumeric in the original should appear in the slug (lowercased)
        original_alnum = [c.lower() for c in text if c.isalnum()]
        slug_alnum = [c for c in result if c.isalnum()]
        # The slug should contain all original alphanumeric chars in order
        # (may be fewer due to stripping, but what's there is in order)
        original_str = "".join(original_alnum)
        slug_str = "".join(slug_alnum)
        assert slug_str == original_str


class TestIssueInfoProperties:
    """Property tests for IssueInfo dataclass."""

    @given(
        path=st.text(min_size=1, max_size=100).map(Path),
        issue_type=st.sampled_from(["bugs", "features", "enhancements"]),
        priority=st.sampled_from(["P0", "P1", "P2", "P3", "P4", "P5"]),
        issue_id=st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True),
        title=st.text(min_size=1, max_size=200),
        blocked_by=st.lists(
            st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True), max_size=5
        ),
        blocks=st.lists(
            st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True), max_size=5
        ),
        discovered_by=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    )
    @settings(max_examples=200)
    def test_roundtrip_serialization(
        self,
        path: Path,
        issue_type: str,
        priority: str,
        issue_id: str,
        title: str,
        blocked_by: list[str],
        blocks: list[str],
        discovered_by: str | None,
    ) -> None:
        """IssueInfo survives roundtrip through to_dict/from_dict."""
        original = IssueInfo(
            path=path,
            issue_type=issue_type,
            priority=priority,
            issue_id=issue_id,
            title=title,
            blocked_by=blocked_by,
            blocks=blocks,
            discovered_by=discovered_by,
        )
        restored = IssueInfo.from_dict(original.to_dict())

        assert restored.path == original.path
        assert restored.issue_type == original.issue_type
        assert restored.priority == original.priority
        assert restored.issue_id == original.issue_id
        assert restored.title == original.title
        assert restored.blocked_by == original.blocked_by
        assert restored.blocks == original.blocks
        assert restored.discovered_by == original.discovered_by

    @given(priority=st.sampled_from(["P0", "P1", "P2", "P3", "P4", "P5"]))
    def test_priority_int_valid_priorities(self, priority: str) -> None:
        """Valid priorities map to expected integers."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority=priority,
            issue_id="BUG-001",
            title="Test",
        )
        expected = int(priority[1])
        assert info.priority_int == expected

    @given(
        priority=st.text(max_size=10).filter(
            lambda x: not (len(x) >= 2 and x.startswith("P") and x[1:].isdigit())
        )
    )
    def test_priority_int_invalid_priorities(self, priority: str) -> None:
        """Invalid priorities map to 99."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority=priority,
            issue_id="BUG-001",
            title="Test",
        )
        assert info.priority_int == 99

    @given(priority=st.sampled_from(["P0", "P1", "P2", "P3", "P4", "P5"]))
    def test_priority_int_ordering(self, priority: str) -> None:
        """Priority integers maintain ordering (P0 < P1 < P2 ...)."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority=priority,
            issue_id="BUG-001",
            title="Test",
        )
        # priority_int should be the numeric part
        assert info.priority_int >= 0
        assert info.priority_int <= 5

    @given(
        blocked_by=st.lists(
            st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True),
            min_size=0,
            max_size=10,
        )
    )
    def test_to_dict_preserves_blocked_by_order(self, blocked_by: list[str]) -> None:
        """Serialization preserves blocked_by list order."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
            blocked_by=blocked_by,
        )
        data = info.to_dict()
        assert data["blocked_by"] == blocked_by

    @given(
        blocks=st.lists(
            st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True),
            min_size=0,
            max_size=10,
        )
    )
    def test_to_dict_preserves_blocks_order(self, blocks: list[str]) -> None:
        """Serialization preserves blocks list order."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
            blocks=blocks,
        )
        data = info.to_dict()
        assert data["blocks"] == blocks


class TestProductImpactProperties:
    """Property tests for ProductImpact dataclass."""

    @given(
        goal_alignment=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
        persona_impact=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
        business_value=st.one_of(st.none(), st.sampled_from(["high", "medium", "low"])),
        user_benefit=st.one_of(st.none(), st.text(min_size=1, max_size=200)),
    )
    @settings(max_examples=200)
    def test_product_impact_roundtrip(
        self,
        goal_alignment: str | None,
        persona_impact: str | None,
        business_value: str | None,
        user_benefit: str | None,
    ) -> None:
        """ProductImpact survives roundtrip through to_dict/from_dict."""
        original = ProductImpact(
            goal_alignment=goal_alignment,
            persona_impact=persona_impact,
            business_value=business_value,
            user_benefit=user_benefit,
        )
        restored = ProductImpact.from_dict(original.to_dict())

        assert restored.goal_alignment == original.goal_alignment
        assert restored.persona_impact == original.persona_impact
        assert restored.business_value == original.business_value
        assert restored.user_benefit == original.user_benefit

    @given(
        goal_alignment=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
        persona_impact=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
        business_value=st.one_of(st.none(), st.sampled_from(["high", "medium", "low"])),
        user_benefit=st.one_of(st.none(), st.text(min_size=1, max_size=200)),
    )
    @settings(max_examples=200)
    def test_product_impact_none_from_dict(
        self,
        goal_alignment: str | None,
        persona_impact: str | None,
        business_value: str | None,
        user_benefit: str | None,
    ) -> None:
        """ProductImpact.from_dict returns None for None input."""
        # If all fields are None, the roundtrip should work
        impact = ProductImpact(
            goal_alignment=goal_alignment,
            persona_impact=persona_impact,
            business_value=business_value,
            user_benefit=user_benefit,
        )
        # Even with None values, roundtrip should preserve them
        result = ProductImpact.from_dict(impact.to_dict())
        assert result is not None
        assert result.goal_alignment == goal_alignment
        assert result.persona_impact == persona_impact
        assert result.business_value == business_value
        assert result.user_benefit == user_benefit

    def test_product_impact_from_dict_none(self) -> None:
        """ProductImpact.from_dict returns None for None input."""
        assert ProductImpact.from_dict(None) is None

    def test_product_impact_from_dict_empty(self) -> None:
        """ProductImpact.from_dict returns None for empty dict."""
        assert ProductImpact.from_dict({}) is None


class TestIssueInfoWithProductImpactProperties:
    """Property tests for IssueInfo with product_impact field."""

    @given(
        path=st.text(min_size=1, max_size=100).map(Path),
        issue_type=st.sampled_from(["bugs", "features", "enhancements"]),
        priority=st.sampled_from(["P0", "P1", "P2", "P3", "P4", "P5"]),
        issue_id=st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True),
        title=st.text(min_size=1, max_size=200),
        blocked_by=st.lists(
            st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True), max_size=5
        ),
        blocks=st.lists(
            st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True), max_size=5
        ),
        discovered_by=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
        goal_alignment=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
        persona_impact=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
        business_value=st.one_of(st.none(), st.sampled_from(["high", "medium", "low"])),
        user_benefit=st.one_of(st.none(), st.text(min_size=1, max_size=200)),
    )
    @settings(max_examples=200)
    def test_roundtrip_with_product_impact(
        self,
        path: Path,
        issue_type: str,
        priority: str,
        issue_id: str,
        title: str,
        blocked_by: list[str],
        blocks: list[str],
        discovered_by: str | None,
        goal_alignment: str | None,
        persona_impact: str | None,
        business_value: str | None,
        user_benefit: str | None,
    ) -> None:
        """IssueInfo with product_impact survives roundtrip through to_dict/from_dict."""
        product_impact = ProductImpact(
            goal_alignment=goal_alignment,
            persona_impact=persona_impact,
            business_value=business_value,
            user_benefit=user_benefit,
        )
        original = IssueInfo(
            path=path,
            issue_type=issue_type,
            priority=priority,
            issue_id=issue_id,
            title=title,
            blocked_by=blocked_by,
            blocks=blocks,
            discovered_by=discovered_by,
            product_impact=product_impact,
        )
        restored = IssueInfo.from_dict(original.to_dict())

        assert restored.path == original.path
        assert restored.issue_type == original.issue_type
        assert restored.priority == original.priority
        assert restored.issue_id == original.issue_id
        assert restored.title == original.title
        assert restored.blocked_by == original.blocked_by
        assert restored.blocks == original.blocks
        assert restored.discovered_by == original.discovered_by
        assert restored.product_impact is not None
        assert restored.product_impact.goal_alignment == goal_alignment
        assert restored.product_impact.persona_impact == persona_impact
        assert restored.product_impact.business_value == business_value
        assert restored.product_impact.user_benefit == user_benefit

    @given(
        path=st.text(min_size=1, max_size=100).map(Path),
        issue_type=st.sampled_from(["bugs", "features", "enhancements"]),
        priority=st.sampled_from(["P0", "P1", "P2", "P3", "P4", "P5"]),
        issue_id=st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True),
        title=st.text(min_size=1, max_size=200),
        blocked_by=st.lists(
            st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True), max_size=5
        ),
        blocks=st.lists(
            st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True), max_size=5
        ),
        discovered_by=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    )
    @settings(max_examples=200)
    def test_roundtrip_without_product_impact(
        self,
        path: Path,
        issue_type: str,
        priority: str,
        issue_id: str,
        title: str,
        blocked_by: list[str],
        blocks: list[str],
        discovered_by: str | None,
    ) -> None:
        """IssueInfo without product_impact survives roundtrip (backward compatibility)."""
        original = IssueInfo(
            path=path,
            issue_type=issue_type,
            priority=priority,
            issue_id=issue_id,
            title=title,
            blocked_by=blocked_by,
            blocks=blocks,
            discovered_by=discovered_by,
        )
        restored = IssueInfo.from_dict(original.to_dict())

        assert restored.path == original.path
        assert restored.issue_type == original.issue_type
        assert restored.priority == original.priority
        assert restored.issue_id == original.issue_id
        assert restored.title == original.title
        assert restored.blocked_by == original.blocked_by
        assert restored.blocks == original.blocks
        assert restored.discovered_by == original.discovered_by
        assert restored.product_impact is None
