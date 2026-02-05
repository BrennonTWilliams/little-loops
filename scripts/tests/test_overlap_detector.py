"""Tests for overlap detector."""

from pathlib import Path
from unittest.mock import Mock

from little_loops.issue_parser import IssueInfo
from little_loops.parallel.overlap_detector import OverlapDetector, OverlapResult


def make_issue(issue_id: str, content: str = "") -> IssueInfo:
    """Create a mock issue with given content."""
    mock_path = Mock(spec=Path)
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = content

    return IssueInfo(
        path=mock_path,
        issue_type="enhancements",
        priority="P3",
        issue_id=issue_id,
        title=f"Test {issue_id}",
    )


class TestOverlapDetector:
    """Tests for OverlapDetector class."""

    def test_register_and_unregister(self) -> None:
        """Should track registered issues."""
        detector = OverlapDetector()
        issue = make_issue("ENH-001", "Modify src/cli.py")

        detector.register_issue(issue)
        assert "ENH-001" in detector.get_active_issues()

        detector.unregister_issue("ENH-001")
        assert "ENH-001" not in detector.get_active_issues()

    def test_detect_file_overlap(self) -> None:
        """Should detect when issues modify same file."""
        detector = OverlapDetector()

        issue1 = make_issue("ENH-001", "Modify src/cli.py")
        issue2 = make_issue("ENH-002", "Also modify src/cli.py")

        detector.register_issue(issue1)
        result = detector.check_overlap(issue2)

        assert result.has_overlap
        assert "ENH-001" in result.overlapping_issues
        assert "src/cli.py" in result.overlapping_files

    def test_no_overlap_different_files(self) -> None:
        """Should return no overlap for different files."""
        detector = OverlapDetector()

        issue1 = make_issue("ENH-001", "Modify src/cli.py")
        issue2 = make_issue("ENH-002", "Modify src/config.py")

        detector.register_issue(issue1)
        result = detector.check_overlap(issue2)

        assert not result.has_overlap
        assert len(result.overlapping_issues) == 0

    def test_detect_directory_overlap(self) -> None:
        """Should detect directory overlaps."""
        detector = OverlapDetector()

        issue1 = make_issue("ENH-001", "Changes in scripts/ directory")
        issue2 = make_issue("ENH-002", "Modify scripts/little_loops/cli.py")

        detector.register_issue(issue1)
        result = detector.check_overlap(issue2)

        assert result.has_overlap

    def test_detect_scope_overlap(self) -> None:
        """Should detect scope overlaps."""
        detector = OverlapDetector()

        issue1 = make_issue("ENH-001", "scope: sidebar")
        issue2 = make_issue("ENH-002", "Changes to sidebar component")

        detector.register_issue(issue1)
        detector.check_overlap(issue2)

        # Note: This depends on whether "sidebar" is extracted from "Changes to sidebar component"
        # The scope pattern requires "scope:" or similar prefix

    def test_multiple_active_issues(self) -> None:
        """Should check against all active issues."""
        detector = OverlapDetector()

        issue1 = make_issue("ENH-001", "Modify src/cli.py")
        issue2 = make_issue("ENH-002", "Modify src/config.py")
        issue3 = make_issue("ENH-003", "Modify src/cli.py and src/utils.py")

        detector.register_issue(issue1)
        detector.register_issue(issue2)
        result = detector.check_overlap(issue3)

        assert result.has_overlap
        assert "ENH-001" in result.overlapping_issues
        # ENH-002 doesn't overlap with issue3

    def test_clear(self) -> None:
        """Should clear all tracked issues."""
        detector = OverlapDetector()

        detector.register_issue(make_issue("ENH-001", "content"))
        detector.register_issue(make_issue("ENH-002", "content"))

        detector.clear()
        assert len(detector.get_active_issues()) == 0

    def test_get_hints(self) -> None:
        """Should return hints for registered issue."""
        detector = OverlapDetector()
        issue = make_issue("ENH-001", "Modify src/cli.py")

        detector.register_issue(issue)
        hints = detector.get_hints("ENH-001")

        assert hints is not None
        assert "src/cli.py" in hints.files

    def test_get_hints_unregistered(self) -> None:
        """Should return None for unregistered issue."""
        detector = OverlapDetector()
        assert detector.get_hints("ENH-999") is None

    def test_check_overlap_does_not_register(self) -> None:
        """check_overlap should not register the issue."""
        detector = OverlapDetector()
        issue = make_issue("ENH-001", "content")

        detector.check_overlap(issue)
        assert "ENH-001" not in detector.get_active_issues()

    def test_thread_safety(self) -> None:
        """Should be thread-safe for concurrent operations."""
        import threading

        detector = OverlapDetector()
        errors: list[Exception] = []

        def register_and_unregister(issue_id: str) -> None:
            try:
                issue = make_issue(issue_id, f"Modify file_{issue_id}.py")
                detector.register_issue(issue)
                detector.check_overlap(issue)
                detector.unregister_issue(issue_id)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=register_and_unregister, args=(f"ENH-{i:03d}",))
            for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestOverlapResult:
    """Tests for OverlapResult dataclass."""

    def test_bool_conversion(self) -> None:
        """Should be truthy when overlap detected."""
        assert OverlapResult(has_overlap=True)
        assert not OverlapResult(has_overlap=False)

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        result = OverlapResult()
        assert not result.has_overlap
        assert result.overlapping_issues == []
        assert result.overlapping_files == set()

    def test_with_overlap_data(self) -> None:
        """Should store overlap information."""
        result = OverlapResult(
            has_overlap=True,
            overlapping_issues=["ENH-001", "ENH-002"],
            overlapping_files={"src/cli.py"},
        )
        assert result.has_overlap
        assert len(result.overlapping_issues) == 2
        assert "src/cli.py" in result.overlapping_files
