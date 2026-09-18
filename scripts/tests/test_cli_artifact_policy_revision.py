"""Tests for little_loops.cli.artifact.policy_revision (FEAT-3498).

Pure validate/persist functions: no transport, no queue, no browser.
"""

from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path

from little_loops.cli.artifact.policy_revision import (
    PolicyRevisionConflictError,
    validate_policy_revision,
)
from little_loops.cli.artifact.policy_revision import (
    persist_policy_revision as persist,
)

_VALID_LIFECYCLE_YAML = textwrap.dedent(
    """
    name: test-lifecycle
    category: issue_lifecycle
    initial: start
    parameters:
      issue_id:
        type: string
        required: true
    states:
      start:
        action_type: shell
        action: echo hi
        on_success: done
        on_failure: done
      done:
        terminal: true
    """
).lstrip()


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TestValidatePolicyRevision:
    def test_valid_issue_lifecycle_yaml_passes(self, tmp_path: Path) -> None:
        outcome = validate_policy_revision(_VALID_LIFECYCLE_YAML.encode(), project_root=tmp_path)
        assert outcome.ok is True
        assert outcome.errors == []
        assert outcome.mode == "issue_lifecycle"

    def test_malformed_yaml_syntax_is_a_structured_error(self, tmp_path: Path) -> None:
        outcome = validate_policy_revision(b"not: valid: yaml: [", project_root=tmp_path)
        assert outcome.ok is False
        assert outcome.errors

    def test_non_mapping_yaml_is_a_structured_error(self, tmp_path: Path) -> None:
        outcome = validate_policy_revision(b"- just\n- a\n- list\n", project_root=tmp_path)
        assert outcome.ok is False
        assert outcome.errors

    def test_missing_required_top_level_fields_is_a_structured_error(self, tmp_path: Path) -> None:
        outcome = validate_policy_revision(b"name: incomplete\n", project_root=tmp_path)
        assert outcome.ok is False
        assert outcome.errors

    def test_unsupported_mode_is_rejected(self, tmp_path: Path) -> None:
        yaml_bytes = _VALID_LIFECYCLE_YAML.replace(
            "category: issue_lifecycle", "category: something_else"
        ).encode()
        outcome = validate_policy_revision(yaml_bytes, project_root=tmp_path)
        assert outcome.ok is False
        assert any("Unsupported policy mode" in e for e in outcome.errors)

    def test_missing_required_issue_id_parameter_is_rejected(self, tmp_path: Path) -> None:
        yaml_bytes = (
            textwrap.dedent(
                """
            name: no-issue-param
            category: issue_lifecycle
            initial: start
            states:
              start:
                action_type: shell
                action: echo hi
                on_success: done
                on_failure: done
              done:
                terminal: true
            """
            )
            .lstrip()
            .encode()
        )
        outcome = validate_policy_revision(yaml_bytes, project_root=tmp_path)
        assert outcome.ok is False
        assert any("issue_id" in e for e in outcome.errors)

    def test_temp_validation_file_is_cleaned_up(self, tmp_path: Path) -> None:
        validate_policy_revision(_VALID_LIFECYCLE_YAML.encode(), project_root=tmp_path)
        artifact_dir = tmp_path / ".loops" / "policy-builder"
        assert list(artifact_dir.glob("*")) == []


class TestPersistPolicyRevision:
    def test_persists_byte_identical_content(self, tmp_path: Path) -> None:
        data = _VALID_LIFECYCLE_YAML.encode()
        rev_id = _hash(data)
        dest = persist(data, rev_id, project_root=tmp_path)
        assert dest.read_bytes() == data
        assert dest.name == f"lifecycle-{rev_id[:12]}.yaml"

    def test_non_ascii_bytes_round_trip_with_matching_hash(self, tmp_path: Path) -> None:
        data = "name: y\ncomment: héllo wörld\n".encode()
        rev_id = _hash(data)
        dest = persist(data, rev_id, project_root=tmp_path)
        assert dest.read_bytes() == data
        assert _hash(dest.read_bytes()) == rev_id

    def test_idempotent_repersist_of_same_bytes(self, tmp_path: Path) -> None:
        data = _VALID_LIFECYCLE_YAML.encode()
        rev_id = _hash(data)
        first = persist(data, rev_id, project_root=tmp_path)
        second = persist(data, rev_id, project_root=tmp_path)
        assert first == second
        assert second.read_bytes() == data

    def test_same_hash_different_bytes_raises_conflict(self, tmp_path: Path) -> None:
        data = _VALID_LIFECYCLE_YAML.encode()
        rev_id = _hash(data)
        persist(data, rev_id, project_root=tmp_path)
        try:
            persist(b"different content entirely", rev_id, project_root=tmp_path)
            raise AssertionError("expected PolicyRevisionConflictError")
        except PolicyRevisionConflictError:
            pass

    def test_project_anchored_under_loops_policy_builder(self, tmp_path: Path) -> None:
        data = _VALID_LIFECYCLE_YAML.encode()
        rev_id = _hash(data)
        dest = persist(data, rev_id, project_root=tmp_path)
        assert dest.parent == tmp_path / ".loops" / "policy-builder"

    def test_no_leftover_temp_files(self, tmp_path: Path) -> None:
        data = _VALID_LIFECYCLE_YAML.encode()
        rev_id = _hash(data)
        persist(data, rev_id, project_root=tmp_path)
        artifact_dir = tmp_path / ".loops" / "policy-builder"
        names = {p.name for p in artifact_dir.glob("*")}
        assert names == {f"lifecycle-{rev_id[:12]}.yaml"}


class TestNoTransportOrQueueDependency:
    """Ported from the retired FEAT-3488 level-2 spike's structural guard:
    this module must stay pure -- no transport or queue coupling -- so it
    stays importable by both `ll-queue`'s store and a future same-origin
    serve route with no transport dependency either way."""

    def test_module_does_not_import_transport_or_queue_store(self) -> None:
        import ast

        import little_loops.cli.artifact.policy_revision as mod

        forbidden = {"transport", "LocalBridgeTransport", "queue_store"}
        tree = ast.parse(Path(mod.__file__).read_text(), filename=mod.__file__)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[-1] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {alias.name for alias in node.names}
                if node.module:
                    names.add(node.module.split(".")[-1])
            else:
                continue
            assert not (names & forbidden), (
                f"policy_revision.py imports forbidden name(s) {names & forbidden}"
            )
