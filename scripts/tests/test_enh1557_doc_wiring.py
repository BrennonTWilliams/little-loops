"""Doc-wiring regression tests for ENH-1557: harness-optimize state-mode documentation.

Asserts that:
1. docs/guides/LOOPS_GUIDE.md has a ### State Mode section with YAML snippet and behavior notes
2. docs/reference/loops.md has the per-state trajectory path, context vars, and state graph nodes
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

LOOPS_GUIDE = PROJECT_ROOT / "docs" / "guides" / "LOOPS_GUIDE.md"
LOOPS_REF = PROJECT_ROOT / "docs" / "reference" / "loops.md"


class TestLoopsGuideStateModeSection:
    """docs/guides/LOOPS_GUIDE.md must document harness-optimize state-mode."""

    def test_state_mode_heading_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "### State Mode" in content, (
            "docs/guides/LOOPS_GUIDE.md must have a '### State Mode' subsection (h3) "
            "under the harness-optimize section"
        )

    def test_targets_yaml_key_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "targets:" in content, (
            "docs/guides/LOOPS_GUIDE.md must include a 'targets:' YAML key in the "
            "State Mode activation snippet"
        )

    def test_states_yaml_key_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "states:" in content, (
            "docs/guides/LOOPS_GUIDE.md must include a 'states:' YAML key in the "
            "State Mode activation snippet"
        )

    def test_check_queue_node_mentioned(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "check_queue" in content, (
            "docs/guides/LOOPS_GUIDE.md must mention 'check_queue' in the State Mode "
            "behavior description"
        )

    def test_dequeue_state_node_mentioned(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "dequeue_state" in content, (
            "docs/guides/LOOPS_GUIDE.md must mention 'dequeue_state' in the State Mode "
            "behavior description"
        )

    def test_per_state_trajectory_path_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert ".ll/runs/harness-optimize/<run-id>/states/<state-name>/trajectory.jsonl" in content, (
            "docs/guides/LOOPS_GUIDE.md must document the per-state trajectory path "
            "'.ll/runs/harness-optimize/<run-id>/states/<state-name>/trajectory.jsonl'"
        )


class TestLoopsRefTrajectorySection:
    """docs/reference/loops.md must document the per-state trajectory layout and context vars."""

    def test_per_state_trajectory_path_present(self) -> None:
        content = LOOPS_REF.read_text()
        assert ".ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl" in content, (
            "docs/reference/loops.md ### Trajectory section must reference the per-state path "
            "'.ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl'"
        )

    def test_old_trajectory_path_absent(self) -> None:
        content = LOOPS_REF.read_text()
        assert ".loops/tmp/harness-optimize-trajectory.jsonl" not in content, (
            "docs/reference/loops.md must NOT reference the old trajectory path "
            "'.loops/tmp/harness-optimize-trajectory.jsonl' — it has been superseded by the "
            "per-state layout"
        )

    def test_state_name_context_var_present(self) -> None:
        content = LOOPS_REF.read_text()
        assert "STATE_NAME" in content, (
            "docs/reference/loops.md ### Context Variables table must include 'STATE_NAME' "
            "as a state-mode context variable"
        )

    def test_examples_file_context_var_present(self) -> None:
        content = LOOPS_REF.read_text()
        assert "EXAMPLES_FILE" in content, (
            "docs/reference/loops.md ### Context Variables table must include 'EXAMPLES_FILE' "
            "as a state-mode context variable"
        )

    def test_dequeue_state_node_in_state_graph(self) -> None:
        content = LOOPS_REF.read_text()
        assert "dequeue_state" in content, (
            "docs/reference/loops.md ### State Graph must include 'dequeue_state' node"
        )

    def test_check_queue_node_in_state_graph(self) -> None:
        content = LOOPS_REF.read_text()
        assert "check_queue" in content, (
            "docs/reference/loops.md ### State Graph must include 'check_queue' node"
        )
