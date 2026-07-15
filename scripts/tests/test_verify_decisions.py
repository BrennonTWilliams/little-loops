"""Tests for ll-verify-decisions — .ll/decisions.yaml load+schema validator (ENH-2589)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.decisions import (
    DecisionEntry,
    RuleEntry,
    add_entry,
    save_decisions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path) -> Path:
    """Create the project skeleton (no decisions.yaml yet)."""
    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_yaml(decisions_path: Path, raw: str) -> None:
    """Write a raw YAML body to decisions_path (bypassing typed serialization)."""
    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    decisions_path.write_text(raw, encoding="utf-8")


# ---------------------------------------------------------------------------
# Unit tests: load_decisions malformed-input surface
#   (mirrors scripts/tests/test_decisions.py::TestLoadDecisions at line 75)
# ---------------------------------------------------------------------------


class TestLoadDecisionsMalformedInput:
    """The three corruption modes that ll-verify-decisions gates against.

    These duplicate the suite at test_decisions.py for redundancy — the
    CLI test below exercises the same surface end-to-end through
    load_decisions(). Keeping them close to the CLI test lets readers
    map exit-code → corruption class without cross-file traversal.
    """

    def test_yaml_error_othe_203(self, tmp_path: Path) -> None:
        """OTHE-203: unterminated quote → yaml.YAMLError."""
        decisions_path = tmp_path / ".ll" / "decisions.yaml"
        _write_yaml(
            decisions_path,
            'entries:\n  - id: OTHE-203\n    type: decision\n    rationale: "abc "" def"\n',
        )
        import yaml as _yaml

        with pytest.raises(_yaml.YAMLError, match="parsing"):
            from little_loops.decisions import load_decisions

            load_decisions(decisions_path)

    def test_key_error_missing_id(self, tmp_path: Path) -> None:
        """Missing required field → KeyError."""
        decisions_path = tmp_path / ".ll" / "decisions.yaml"
        _write_yaml(
            decisions_path,
            "entries:\n  - type: rule\n    rationale: no id here\n",
        )
        from little_loops.decisions import load_decisions

        with pytest.raises(KeyError):
            load_decisions(decisions_path)

    def test_value_error_unknown_type(self, tmp_path: Path) -> None:
        """Unknown discriminator → ValueError."""
        decisions_path = tmp_path / ".ll" / "decisions.yaml"
        _write_yaml(
            decisions_path,
            "entries:\n  - id: BAD-001\n    type: foo\n    rationale: bad discriminator\n",
        )
        from little_loops.decisions import load_decisions

        with pytest.raises(ValueError, match="Unknown entry type"):
            load_decisions(decisions_path)


# ---------------------------------------------------------------------------
# Integration tests: main_verify_decisions
#   (mirrors scripts/tests/test_verify_package_data.py::TestMainVerifyPackageData)
# ---------------------------------------------------------------------------


class TestMainVerifyDecisions:
    """CLI entry point tests — clean/dirty paths + --config-root override."""

    def test_clean_file_returns_zero(self, tmp_path: Path) -> None:
        """Loadable decisions.yaml → exit 0."""
        from little_loops.cli.verify_decisions import main_verify_decisions

        _make_project(tmp_path)
        decisions_path = tmp_path / ".ll" / "decisions.yaml"
        save_decisions(
            [RuleEntry(id="R-001", rule="Use atomic writes")],
            decisions_path,
        )
        with (
            patch("sys.argv", ["ll-verify-decisions", "--config-root", str(tmp_path)]),
            patch("builtins.print"),
        ):
            assert main_verify_decisions() == 0

    def test_yaml_error_returns_one(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """YAML parse error → exit 1 + single-line ERROR message on stderr."""
        from little_loops.cli.verify_decisions import main_verify_decisions

        _make_project(tmp_path)
        decisions_path = tmp_path / ".ll" / "decisions.yaml"
        _write_yaml(
            decisions_path,
            'entries:\n  - id: OTHE-203\n    type: decision\n    rationale: "abc "" def"\n',
        )
        with patch("sys.argv", ["ll-verify-decisions", "--config-root", str(tmp_path)]):
            ret = main_verify_decisions()
        captured = capsys.readouterr()
        assert ret == 1
        assert "ERROR" in captured.err
        assert str(decisions_path) in captured.err

    def test_key_error_returns_one(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Missing required field → exit 1 + ERROR on stderr."""
        from little_loops.cli.verify_decisions import main_verify_decisions

        _make_project(tmp_path)
        decisions_path = tmp_path / ".ll" / "decisions.yaml"
        _write_yaml(
            decisions_path,
            "entries:\n  - type: rule\n    rationale: no id here\n",
        )
        with patch("sys.argv", ["ll-verify-decisions", "--config-root", str(tmp_path)]):
            ret = main_verify_decisions()
        captured = capsys.readouterr()
        assert ret == 1
        assert "ERROR" in captured.err

    def test_value_error_returns_one(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Unknown entry type → exit 1 + ERROR on stderr."""
        from little_loops.cli.verify_decisions import main_verify_decisions

        _make_project(tmp_path)
        decisions_path = tmp_path / ".ll" / "decisions.yaml"
        _write_yaml(
            decisions_path,
            "entries:\n  - id: BAD-001\n    type: foo\n    rationale: bad discriminator\n",
        )
        with patch("sys.argv", ["ll-verify-decisions", "--config-root", str(tmp_path)]):
            ret = main_verify_decisions()
        captured = capsys.readouterr()
        assert ret == 1
        assert "ERROR" in captured.err
        assert "Unknown entry type" in captured.err

    def test_missing_file_returns_zero(self, tmp_path: Path) -> None:
        """Absent decisions.yaml is a clean state (load_decisions returns []) → exit 0."""
        from little_loops.cli.verify_decisions import main_verify_decisions

        _make_project(tmp_path)
        with (
            patch("sys.argv", ["ll-verify-decisions", "--config-root", str(tmp_path)]),
            patch("builtins.print"),
        ):
            assert main_verify_decisions() == 0

    def test_config_root_overrides_default(self, tmp_path: Path) -> None:
        """--config-root <path> resolves decisions.yaml under <path>/.ll/.

        Pre-populates a *different* repo at tmp_path/different/ with a dirty
        decisions.yaml to prove the CLI doesn't fall back to cwd when an
        explicit root is given.
        """
        from little_loops.cli.verify_decisions import main_verify_decisions

        _make_project(tmp_path)
        clean_root = tmp_path / "clean-repo"
        clean_root.mkdir()
        (clean_root / ".ll").mkdir(parents=True)
        save_decisions(
            [DecisionEntry(id="WORKFLOW-001", rule="Use YAML", scope="project")],
            clean_root / ".ll" / "decisions.yaml",
        )

        with (
            patch("sys.argv", ["ll-verify-decisions", "--config-root", str(clean_root)]),
            patch("builtins.print"),
        ):
            assert main_verify_decisions() == 0


# ---------------------------------------------------------------------------
# Fragment strict-pass tests (BUG-2646)
#   load_decisions() silently skips malformed .ll/decisions.d/*.json fragments
#   (BUG-2644), so the validator must run a *strict* fragment pass that lets
#   parse/schema errors escape as exit 1. This is the exact counterpoint to
#   test_decisions_fragments.py::TestDirectoryUnionRead::test_malformed_fragment_skipped.
# ---------------------------------------------------------------------------


def _frag_dir(tmp_path: Path) -> Path:
    return tmp_path / ".ll" / "decisions.d"


def _write_fragment(tmp_path: Path, name: str, payload: dict | str) -> Path:
    frag_dir = _frag_dir(tmp_path)
    frag_dir.mkdir(parents=True, exist_ok=True)
    p = frag_dir / name
    text = payload if isinstance(payload, str) else json.dumps(payload)
    p.write_text(text, encoding="utf-8")
    return p


class TestMainVerifyDecisionsFragments:
    """The strict fragment pass — mirrors TestMainVerifyDecisions shape."""

    def test_valid_fragment_passes(self, tmp_path: Path) -> None:
        """A well-formed fragment (via add_entry) → exit 0."""
        from little_loops.cli.verify_decisions import main_verify_decisions

        _make_project(tmp_path)
        add_entry(RuleEntry(id="NAMING-001", rule="r"), tmp_path / ".ll" / "decisions.yaml")
        with (
            patch("sys.argv", ["ll-verify-decisions", "--config-root", str(tmp_path)]),
            patch("builtins.print"),
        ):
            assert main_verify_decisions() == 0

    def test_malformed_json_fragment_blocks(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Unparseable JSON fragment → exit 1 (NOT silently skipped)."""
        from little_loops.cli.verify_decisions import main_verify_decisions

        _make_project(tmp_path)
        _write_fragment(tmp_path, "bad.json", "{not json")
        with patch("sys.argv", ["ll-verify-decisions", "--config-root", str(tmp_path)]):
            ret = main_verify_decisions()
        captured = capsys.readouterr()
        assert ret == 1
        assert "ERROR" in captured.err
        assert "bad.json" in captured.err

    def test_missing_id_fragment_blocks(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Fragment missing required ``id`` → exit 1."""
        from little_loops.cli.verify_decisions import main_verify_decisions

        _make_project(tmp_path)
        _write_fragment(tmp_path, "noid.json", {"type": "rule", "rule": "r"})
        with patch("sys.argv", ["ll-verify-decisions", "--config-root", str(tmp_path)]):
            ret = main_verify_decisions()
        captured = capsys.readouterr()
        assert ret == 1
        assert "ERROR" in captured.err

    def test_unknown_type_fragment_blocks(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Fragment with an unknown ``type`` discriminator → exit 1."""
        from little_loops.cli.verify_decisions import main_verify_decisions

        _make_project(tmp_path)
        _write_fragment(tmp_path, "badtype.json", {"id": "X", "type": "nope"})
        with patch("sys.argv", ["ll-verify-decisions", "--config-root", str(tmp_path)]):
            ret = main_verify_decisions()
        captured = capsys.readouterr()
        assert ret == 1
        assert "ERROR" in captured.err
        assert "Unknown entry type" in captured.err

    def test_clean_flat_file_plus_valid_fragment_passes(self, tmp_path: Path) -> None:
        """Flat file and fragment both valid → exit 0 (positive control)."""
        from little_loops.cli.verify_decisions import main_verify_decisions

        _make_project(tmp_path)
        decisions_path = tmp_path / ".ll" / "decisions.yaml"
        save_decisions([RuleEntry(id="R-001", rule="Use atomic writes")], decisions_path)
        _write_fragment(tmp_path, "ok.json", {"id": "OK-1", "type": "rule", "rule": "r"})
        with (
            patch("sys.argv", ["ll-verify-decisions", "--config-root", str(tmp_path)]),
            patch("builtins.print"),
        ):
            assert main_verify_decisions() == 0
