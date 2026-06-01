"""Tests for ENH-1753: history.db producer→consumer flow documentation wiring."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

ARCHITECTURE_MD = PROJECT_ROOT / "docs" / "ARCHITECTURE.md"
API_MD = PROJECT_ROOT / "docs" / "reference" / "API.md"


class TestEnh1753DocWiring:
    """ENH-1753: history.db producer→consumer flow must be documented in ARCHITECTURE.md and API.md."""

    def test_architecture_has_history_db_section(self) -> None:
        content = ARCHITECTURE_MD.read_text()
        assert "## History DB: Producer→Consumer Flow" in content, (
            "docs/ARCHITECTURE.md must contain a '## History DB: Producer→Consumer Flow' section"
        )

    def test_architecture_has_sequence_diagram(self) -> None:
        content = ARCHITECTURE_MD.read_text()
        assert "sequenceDiagram" in content, (
            "docs/ARCHITECTURE.md must contain a sequenceDiagram for the write-path flow"
        )

    def test_architecture_has_flowchart(self) -> None:
        content = ARCHITECTURE_MD.read_text()
        assert "flowchart TB" in content, (
            "docs/ARCHITECTURE.md must contain a flowchart TB for the read-path consumer fan-out"
        )

    def test_architecture_has_graceful_degradation_contract(self) -> None:
        content = ARCHITECTURE_MD.read_text()
        assert "_connect_readonly" in content, (
            "docs/ARCHITECTURE.md must document the _connect_readonly() graceful-degradation contract"
        )

    def test_api_has_history_reader_section(self) -> None:
        content = API_MD.read_text()
        assert "## little_loops.history_reader" in content, (
            "docs/reference/API.md must contain a '## little_loops.history_reader' module section"
        )

    def test_api_documents_find_user_corrections(self) -> None:
        content = API_MD.read_text()
        assert "find_user_corrections" in content, (
            "docs/reference/API.md must document the find_user_corrections() query function"
        )

    def test_api_documents_sessions_for_issue(self) -> None:
        content = API_MD.read_text()
        assert "sessions_for_issue" in content, (
            "docs/reference/API.md must document the sessions_for_issue() query function"
        )

    def test_api_documents_include_stale_parameter(self) -> None:
        content = API_MD.read_text()
        assert "include_stale" in content, (
            "docs/reference/API.md must document the include_stale parameter for stale-row filtering"
        )

    def test_api_documents_session_ref_dataclass(self) -> None:
        content = API_MD.read_text()
        assert "SessionRef" in content, (
            "docs/reference/API.md must document the SessionRef dataclass (ENH-1711)"
        )
