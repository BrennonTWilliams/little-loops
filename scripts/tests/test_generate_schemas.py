"""Tests for generate_schemas module and ll-generate-schemas CLI."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.generate_schemas import SCHEMA_DEFINITIONS, generate_schemas


class TestSchemaDefinitions:
    """Tests for the SCHEMA_DEFINITIONS catalog."""

    def test_all_21_event_types_defined(self) -> None:
        """All 21 LLEvent types must be defined."""
        assert len(SCHEMA_DEFINITIONS) == 21

    def test_expected_event_types_present(self) -> None:
        """Each of the 21 known event types must appear in catalog."""
        expected = {
            "loop_start",
            "state_enter",
            "route",
            "action_start",
            "action_output",
            "action_complete",
            "evaluate",
            "retry_exhausted",
            "rate_limit_exhausted",
            "rate_limit_storm",
            "handoff_detected",
            "handoff_spawned",
            "loop_complete",
            "loop_resume",
            "state.issue_completed",
            "state.issue_failed",
            "issue.failure_captured",
            "issue.closed",
            "issue.completed",
            "issue.deferred",
            "parallel.worker_completed",
        }
        assert set(SCHEMA_DEFINITIONS.keys()) == expected


class TestGenerateSchemas:
    """Tests for generate_schemas() output."""

    def test_creates_21_files(self, tmp_path: Path) -> None:
        """Generates exactly 21 schema files."""
        generate_schemas(tmp_path)
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 21

    def test_creates_output_dir_if_missing(self, tmp_path: Path) -> None:
        """Creates the output directory if it doesn't exist."""
        output_dir = tmp_path / "nested" / "schemas"
        generate_schemas(output_dir)
        assert output_dir.exists()
        assert len(list(output_dir.glob("*.json"))) == 21

    def test_all_files_are_valid_json(self, tmp_path: Path) -> None:
        """Every generated file contains valid JSON."""
        generate_schemas(tmp_path)
        for f in tmp_path.glob("*.json"):
            data = json.loads(f.read_text())
            assert isinstance(data, dict)

    def test_all_schemas_have_required_json_schema_fields(self, tmp_path: Path) -> None:
        """Every schema includes $schema, $id, title, description, type, and properties."""
        generate_schemas(tmp_path)
        for f in tmp_path.glob("*.json"):
            data = json.loads(f.read_text())
            assert "$schema" in data, f"{f.name} missing $schema"
            assert "$id" in data, f"{f.name} missing $id"
            assert "title" in data, f"{f.name} missing title"
            assert "description" in data, f"{f.name} missing description"
            assert data.get("type") == "object", f"{f.name} should be type: object"
            assert "properties" in data, f"{f.name} missing properties"

    def test_all_schemas_require_event_and_ts(self, tmp_path: Path) -> None:
        """Every schema must mark 'event' and 'ts' as required (wire format fields)."""
        generate_schemas(tmp_path)
        for f in tmp_path.glob("*.json"):
            data = json.loads(f.read_text())
            required = data.get("required", [])
            assert "event" in required, f"{f.name}: 'event' not in required"
            assert "ts" in required, f"{f.name}: 'ts' not in required"

    def test_dot_in_event_type_becomes_underscore_in_filename(self, tmp_path: Path) -> None:
        """Event types with dots use underscores in filenames (filesystem safety)."""
        generate_schemas(tmp_path)
        assert (tmp_path / "state_issue_completed.json").exists()
        assert (tmp_path / "state_issue_failed.json").exists()
        assert (tmp_path / "issue_failure_captured.json").exists()
        assert (tmp_path / "issue_closed.json").exists()
        assert (tmp_path / "issue_completed.json").exists()
        assert (tmp_path / "issue_deferred.json").exists()
        assert (tmp_path / "parallel_worker_completed.json").exists()

    def test_idempotent_on_second_run(self, tmp_path: Path) -> None:
        """Running twice overwrites files without error and produces same output."""
        generate_schemas(tmp_path)
        content_first = {f.name: f.read_text() for f in tmp_path.glob("*.json")}
        generate_schemas(tmp_path)
        content_second = {f.name: f.read_text() for f in tmp_path.glob("*.json")}
        assert content_first == content_second

    # --- Spot-checks for specific event types ---

    def test_loop_start_schema(self, tmp_path: Path) -> None:
        """loop_start.json has correct payload fields."""
        generate_schemas(tmp_path)
        data = json.loads((tmp_path / "loop_start.json").read_text())
        props = data["properties"]
        assert "event" in props
        assert "ts" in props
        assert "loop" in props

    def test_state_enter_schema(self, tmp_path: Path) -> None:
        """state_enter.json has state and iteration fields."""
        generate_schemas(tmp_path)
        data = json.loads((tmp_path / "state_enter.json").read_text())
        props = data["properties"]
        assert "state" in props
        assert "iteration" in props
        assert props["iteration"]["type"] == "integer"

    def test_action_complete_schema(self, tmp_path: Path) -> None:
        """action_complete.json has exit_code, duration_ms, output_preview, is_prompt, session_jsonl."""
        generate_schemas(tmp_path)
        data = json.loads((tmp_path / "action_complete.json").read_text())
        props = data["properties"]
        assert "exit_code" in props
        assert "duration_ms" in props
        assert "output_preview" in props
        assert "is_prompt" in props
        assert "session_jsonl" in props

    def test_loop_start_schema_id_format(self, tmp_path: Path) -> None:
        """$id uses little-loops://event-<type>.json format."""
        generate_schemas(tmp_path)
        data = json.loads((tmp_path / "loop_start.json").read_text())
        assert data["$id"] == "little-loops://event-loop_start.json"

    def test_draft07_schema_url(self, tmp_path: Path) -> None:
        """$schema field uses JSON Schema draft-07."""
        generate_schemas(tmp_path)
        data = json.loads((tmp_path / "loop_start.json").read_text())
        assert data["$schema"] == "http://json-schema.org/draft-07/schema#"


class TestGenerateSchemasCLI:
    """Tests for ll-generate-schemas CLI entry point."""

    def test_cli_returns_zero_on_success(self, tmp_path: Path) -> None:
        """CLI returns 0 when schemas generate successfully."""
        from little_loops.cli.schemas import main_generate_schemas

        with patch("sys.argv", ["ll-generate-schemas", "--output", str(tmp_path)]):
            result = main_generate_schemas()
        assert result == 0

    def test_cli_creates_files(self, tmp_path: Path) -> None:
        """CLI generates 21 schema files in the specified output directory."""
        from little_loops.cli.schemas import main_generate_schemas

        with patch("sys.argv", ["ll-generate-schemas", "--output", str(tmp_path)]):
            main_generate_schemas()
        assert len(list(tmp_path.glob("*.json"))) == 21

    def test_cli_default_output_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI defaults to docs/reference/schemas/ relative to cwd."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "docs" / "reference").mkdir(parents=True)

        from little_loops.cli.schemas import main_generate_schemas

        with patch("sys.argv", ["ll-generate-schemas"]):
            result = main_generate_schemas()
        assert result == 0
        assert (tmp_path / "docs" / "reference" / "schemas").exists()
