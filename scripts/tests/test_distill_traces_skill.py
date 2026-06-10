"""Tests for /ll:distill-traces skill — existence and section-scoped content assertions.

Modeled after test_audit_loop_run_skill.py for section-scoped content assertion pattern.
"""

from __future__ import annotations

from pathlib import Path

SKILL_PATH = Path(__file__).parent.parent.parent / "skills" / "distill-traces" / "SKILL.md"


class TestDistillTracesSkill:
    # ------------------------------------------------------------------
    # Skill existence checks
    # ------------------------------------------------------------------

    def test_skill_file_exists(self) -> None:
        assert SKILL_PATH.exists(), "skills/distill-traces/SKILL.md must exist"

    def test_skill_has_loop_name_argument(self) -> None:
        content = SKILL_PATH.read_text()
        assert "loop_name" in content or "loop-name" in content
        # → skill must accept a loop name argument

    def test_skill_has_min_success_argument(self) -> None:
        content = SKILL_PATH.read_text()
        assert "--min-success" in content
        # → skill must support --min-success N threshold parameter

    def test_skill_has_disable_model_invocation(self) -> None:
        content = SKILL_PATH.read_text()
        assert "disable-model-invocation: true" in content
        # → skill is prompt-driven, not a model-invocation wrapper

    # ------------------------------------------------------------------
    # Data source references
    # ------------------------------------------------------------------

    def test_skill_references_state_json(self) -> None:
        content = SKILL_PATH.read_text()
        assert "state.json" in content
        # → skill reads state.json to check run success status

    def test_skill_references_events_jsonl(self) -> None:
        content = SKILL_PATH.read_text()
        assert "events.jsonl" in content
        # → skill reads events.jsonl to extract state sequences

    def test_skill_references_status_completed(self) -> None:
        content = SKILL_PATH.read_text()
        assert "completed" in content
        # → skill filters runs by status == "completed"

    def test_skill_references_state_enter_event(self) -> None:
        content = SKILL_PATH.read_text()
        assert "state_enter" in content
        # → skill extracts state_enter events from events.jsonl

    def test_skill_references_route_event(self) -> None:
        content = SKILL_PATH.read_text()
        assert (
            '"route"' in content
            or "'route'" in content
            or "route events" in content
            or "`route`" in content
        )
        # → skill extracts route events for transition data

    # ------------------------------------------------------------------
    # Fragment schema section
    # ------------------------------------------------------------------

    def test_skill_has_fragments_schema(self) -> None:
        content = SKILL_PATH.read_text()
        assert "fragments:" in content
        # → skill documents the fragments: map output structure

    def test_skill_has_state_templates_yaml(self) -> None:
        content = SKILL_PATH.read_text()
        assert "state-templates.yaml" in content
        # → skill writes state-templates.yaml output file

    def test_skill_has_transitions_yaml(self) -> None:
        content = SKILL_PATH.read_text()
        assert "transitions.yaml" in content
        # → skill writes transitions.yaml output file

    # ------------------------------------------------------------------
    # Output path
    # ------------------------------------------------------------------

    def test_skill_outputs_to_lib_directory(self) -> None:
        content = SKILL_PATH.read_text()
        assert "lib/" in content
        # → output is written to scripts/little_loops/loops/lib/<loop-name>/

    def test_skill_writes_primitives_md(self) -> None:
        content = SKILL_PATH.read_text()
        assert "primitives.md" in content
        # → skill writes human-readable primitives index

    # ------------------------------------------------------------------
    # Graceful degradation
    # ------------------------------------------------------------------

    def test_skill_has_graceful_degradation_for_insufficient_runs(self) -> None:
        content = SKILL_PATH.read_text()
        # Must mention that fewer-than-threshold runs causes exit without writing artifacts
        assert "exit 0" in content or "exit without" in content or "without writing" in content
        # → skill exits cleanly when fewer than --min-success runs exist

    def test_skill_documents_default_min_success(self) -> None:
        content = SKILL_PATH.read_text()
        # Default threshold is 3
        assert "default 3" in content or "default: 3" in content or "(default 3)" in content
        # → --min-success defaults to 3

    # ------------------------------------------------------------------
    # History folder pattern
    # ------------------------------------------------------------------

    def test_skill_references_history_directory(self) -> None:
        content = SKILL_PATH.read_text()
        assert ".loops/.history" in content or ".history/" in content
        # → skill reads from the .loops/.history/ archive directory
