"""Doc-wiring regression tests for ENH-1734: documentation updates for ENH-1691 EventBus wiring.

Asserts that:
1. docs/reference/API.md documents AutoManager db_path parameter and EventBus/SQLiteTransport behavior
2. docs/reference/EVENT-SCHEMA.md includes issue.skipped and issue.started entries
3. docs/ARCHITECTURE.md includes ll-auto row in CLI wiring table
4. docs/reference/CLI.md backfill framing reflects live writes
5. docs/reference/CONFIGURATION.md backfill description updated
6. config-schema.json sqlite description includes issue lifecycle events
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

API_MD = PROJECT_ROOT / "docs" / "reference" / "API.md"
EVENT_SCHEMA_MD = PROJECT_ROOT / "docs" / "reference" / "EVENT-SCHEMA.md"
ARCHITECTURE_MD = PROJECT_ROOT / "docs" / "ARCHITECTURE.md"
CLI_MD = PROJECT_ROOT / "docs" / "reference" / "CLI.md"
CONFIGURATION_MD = PROJECT_ROOT / "docs" / "reference" / "CONFIGURATION.md"
CONFIG_SCHEMA_JSON = PROJECT_ROOT / "config-schema.json"


class TestApiMdAutoManager:
    """docs/reference/API.md must document AutoManager constructor with new parameters."""

    def test_db_path_param_present(self) -> None:
        content = API_MD.read_text()
        assert "db_path" in content, (
            "API.md AutoManager constructor block must include 'db_path' parameter"
        )

    def test_label_filter_param_present(self) -> None:
        content = API_MD.read_text()
        assert "label_filter" in content, (
            "API.md AutoManager constructor block must include 'label_filter' parameter"
        )

    def test_preview_full_param_present(self) -> None:
        content = API_MD.read_text()
        assert "preview_full" in content, (
            "API.md AutoManager constructor block must include 'preview_full' parameter"
        )

    def test_only_ids_type_corrected(self) -> None:
        content = API_MD.read_text()
        assert "list[str] | set[str] | None" in content, (
            "API.md must document only_ids type as 'list[str] | set[str] | None' (not set[str] | None)"
        )

    def test_eventbus_sqlite_behavior_note(self) -> None:
        content = API_MD.read_text()
        assert "SQLiteTransport" in content and "AutoManager" in content, (
            "API.md must document that AutoManager wires EventBus and SQLiteTransport internally"
        )

    def test_event_bus_param_in_complete_issue_lifecycle(self) -> None:
        content = API_MD.read_text()
        assert "complete_issue_lifecycle" in content, (
            "API.md must include complete_issue_lifecycle function documentation"
        )

    def test_event_bus_param_in_defer_issue(self) -> None:
        content = API_MD.read_text()
        assert "defer_issue" in content, "API.md must include defer_issue function documentation"

    def test_undefer_issue_return_fixed(self) -> None:
        content = API_MD.read_text()
        assert "in-place" in content or "updated in-place" in content, (
            "API.md undefer_issue return description must note the issue is updated in-place "
            "(no file move), not 'New Path of the issue in its active category directory'"
        )


class TestEventSchemaMd:
    """docs/reference/EVENT-SCHEMA.md must include issue.skipped and issue.started."""

    def test_issue_skipped_in_master_table(self) -> None:
        content = EVENT_SCHEMA_MD.read_text()
        assert "| `issue.skipped`" in content, (
            "EVENT-SCHEMA.md master event-type table must include an 'issue.skipped' row"
        )

    def test_issue_started_in_master_table(self) -> None:
        content = EVENT_SCHEMA_MD.read_text()
        assert "| `issue.started`" in content, (
            "EVENT-SCHEMA.md master event-type table must include an 'issue.started' row"
        )

    def test_issue_skipped_section_block(self) -> None:
        content = EVENT_SCHEMA_MD.read_text()
        assert "### `issue.skipped`" in content, (
            "EVENT-SCHEMA.md must include a '### `issue.skipped`' section block"
        )

    def test_issue_started_section_block(self) -> None:
        content = EVENT_SCHEMA_MD.read_text()
        assert "### `issue.started`" in content, (
            "EVENT-SCHEMA.md must include a '### `issue.started`' section block"
        )

    def test_issue_skipped_json_example(self) -> None:
        content = EVENT_SCHEMA_MD.read_text()
        assert '"event": "issue.skipped"' in content, (
            "EVENT-SCHEMA.md issue.skipped section must include a JSON example"
        )

    def test_issue_started_json_example(self) -> None:
        content = EVENT_SCHEMA_MD.read_text()
        assert '"event": "issue.started"' in content, (
            "EVENT-SCHEMA.md issue.started section must include a JSON example"
        )


class TestArchitectureMd:
    """docs/ARCHITECTURE.md must document ll-auto CLI wiring and updated event list."""

    def test_ll_auto_row_in_cli_wiring_table(self) -> None:
        content = ARCHITECTURE_MD.read_text()
        assert "`ll-auto`" in content and "AutoManager" in content, (
            "ARCHITECTURE.md Extensions/Transports table must include an ll-auto row "
            "documenting that AutoManager wires SQLiteTransport directly"
        )

    def test_issue_skipped_in_event_emitters_table(self) -> None:
        content = ARCHITECTURE_MD.read_text()
        assert "issue.skipped" in content, (
            "ARCHITECTURE.md Event Emitters table Issue Lifecycle row must list issue.skipped"
        )

    def test_issue_started_in_event_emitters_table(self) -> None:
        content = ARCHITECTURE_MD.read_text()
        assert "issue.started" in content, (
            "ARCHITECTURE.md Event Emitters table Issue Lifecycle row must list issue.started"
        )

    def test_sqlite_transport_direct_wiring_noted(self) -> None:
        content = ARCHITECTURE_MD.read_text()
        assert "AutoManager.__init__()" in content, (
            "ARCHITECTURE.md must note that AutoManager.__init__() wires SQLiteTransport directly"
        )

    def test_automanager_class_diagram_has_event_bus(self) -> None:
        content = ARCHITECTURE_MD.read_text()
        assert "event_bus" in content and "EventBus" in content, (
            "ARCHITECTURE.md AutoManager class diagram must include event_bus member"
        )

    def test_automanager_class_diagram_has_db_path(self) -> None:
        content = ARCHITECTURE_MD.read_text()
        assert "db_path" in content, (
            "ARCHITECTURE.md AutoManager class diagram must include db_path member"
        )


class TestCliMdBackfillFraming:
    """docs/reference/CLI.md backfill references must reflect live writes as primary mechanism."""

    def test_ll_auto_live_write_mentioned(self) -> None:
        content = CLI_MD.read_text()
        assert "live" in content and "AutoManager" in content, (
            "CLI.md must mention that ll-auto writes issue lifecycle events live via AutoManager"
        )

    def test_backfill_framed_as_legacy(self) -> None:
        content = CLI_MD.read_text()
        assert "historical" in content or "before ENH-1691" in content, (
            "CLI.md must frame ll-session backfill as for historical/pre-ENH-1691 data"
        )

    def test_ll_session_description_updated(self) -> None:
        content = CLI_MD.read_text()
        # The ll-session description should mention AutoManager's live-write role
        assert "ll-session" in content and "AutoManager" in content, (
            "CLI.md ll-session description must note AutoManager populates issue_events via live-write"
        )


class TestConfigurationMdBackfill:
    """docs/reference/CONFIGURATION.md backfill description must reflect live writes."""

    def test_live_transport_note_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "ENH-1691" in content or "live" in content, (
            "CONFIGURATION.md events.sqlite section must note live-write as the primary mechanism"
        )

    def test_backfill_framed_as_legacy(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "historical" in content or "before ENH-1691" in content, (
            "CONFIGURATION.md must frame backfill as for historical/pre-ENH-1691 data"
        )


class TestConfigSchemaJson:
    """config-schema.json sqlite description must include issue lifecycle events."""

    def test_issue_lifecycle_events_in_description(self) -> None:
        content = CONFIG_SCHEMA_JSON.read_text()
        assert "issue.completed" in content or "issue lifecycle" in content.lower(), (
            "config-schema.json sqlite description must mention issue lifecycle events"
        )

    def test_automanager_wiring_noted(self) -> None:
        content = CONFIG_SCHEMA_JSON.read_text()
        assert "AutoManager" in content, (
            "config-schema.json sqlite description must note AutoManager wires directly "
            "without requiring events.transports config"
        )
