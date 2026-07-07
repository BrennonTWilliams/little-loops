"""Tests for the DES audit walker at ``little_loops.observability.audit``.

The audit walker classifies every emit site in ``scripts/little_loops/`` against the
``DES_VARIANTS`` registry. Its verdict gates F5's adoption: every currently-emitted
event must have a registered variant before F5 can land.

Precedent: ``scripts/tests/test_verify_design_tokens.py:178-238`` (``TestMain`` shape).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.verify_des_audit import main_verify_des_audit
from little_loops.observability import audit_tree

# ---------------------------------------------------------------------------
# Audit walker (core logic)
# ---------------------------------------------------------------------------


class TestAuditWalker:
    """Tests for ``audit_tree()`` — the static emit-site classifier."""

    def test_synthetic_tree_clean_passes(self, tmp_path: Path) -> None:
        """A synthetic source tree with only registered emit types returns no violations."""
        (tmp_path / "mod.py").write_text(
            '"""Module."""\n'
            "from somewhere import event_bus\n"
            'event_bus.emit("loop_start", {"loop": "x"})\n',
            encoding="utf-8",
        )
        result = audit_tree(tmp_path)
        assert result.uncovered_event_types == []

    def test_synthetic_tree_unregistered_returns_violation(self, tmp_path: Path) -> None:
        """An emit site with an unregistered event type is flagged."""
        (tmp_path / "mod.py").write_text(
            '"""Module."""\n'
            "from somewhere import event_bus\n"
            'event_bus.emit("totally_unknown_event", {})\n',
            encoding="utf-8",
        )
        result = audit_tree(tmp_path)
        assert "totally_unknown_event" in result.uncovered_event_types

    def test_real_tree_passes(self) -> None:
        """The audit must pass against the actual ``scripts/little_loops/`` tree.

        This is the F5 acceptance gate: the registry must cover the real emitted
        surface, so the audit returns zero violations when walked over the source.
        """
        # tests/ lives under scripts/tests/, so walk up to scripts/little_loops/.
        here = Path(__file__).resolve()
        scripts_root = here.parent.parent  # scripts/
        pkg_root = scripts_root / "little_loops"
        if not pkg_root.is_dir():
            pytest.skip(f"Source tree not found at {pkg_root}")
        result = audit_tree(pkg_root)
        assert result.uncovered_event_types == [], (
            f"Audit found uncovered event types in real tree: "
            f"{sorted(set(result.uncovered_event_types))}"
        )

    def test_files_scanned_non_zero(self, tmp_path: Path) -> None:
        """The walker records the number of .py files it inspected."""
        (tmp_path / "a.py").write_text('"""x."""\n', encoding="utf-8")
        (tmp_path / "b.py").write_text('"""y."""\n', encoding="utf-8")
        result = audit_tree(tmp_path)
        assert result.files_scanned >= 2

    def test_unreadable_file_does_not_crash(self, tmp_path: Path) -> None:
        """Files that fail to read are skipped, not raised."""
        (tmp_path / "ok.py").write_text('"""OK."""\n', encoding="utf-8")
        # Create a directory disguised as a .py — ``rglob`` will return it but
        # ``read_text`` will raise ``IsADirectoryError``. The walker must tolerate this.
        bad = tmp_path / "bad.py"
        bad.mkdir()
        result = audit_tree(tmp_path)
        # Just assert it didn't crash and reported the readable file.
        assert result.files_scanned >= 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for ``main_verify_des_audit()`` — the CLI entry point."""

    def test_clean_real_tree_returns_zero(self) -> None:
        """Against the real source tree, the CLI exits 0 (audit passes)."""
        with (
            patch.object(sys, "argv", ["ll-verify-des-audit"]),
            patch("builtins.print"),
        ):
            assert main_verify_des_audit() == 0

    def test_synthetic_bad_emit_returns_one(self, tmp_path: Path) -> None:
        """A synthetic source tree with an unregistered emit returns exit code 1."""
        pkg = tmp_path / "scripts" / "little_loops"
        pkg.mkdir(parents=True)
        (pkg / "mod.py").write_text(
            '"""M."""\nfrom x import event_bus\nevent_bus.emit("definitely_not_registered", {})\n',
            encoding="utf-8",
        )
        with (
            patch.object(
                sys,
                "argv",
                ["ll-verify-des-audit", "--source-dir", str(pkg)],
            ),
            patch("builtins.print"),
        ):
            assert main_verify_des_audit() == 1

    def test_json_output_is_parseable(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """``--json`` emits parseable JSON describing the audit verdict."""
        pkg = tmp_path / "scripts" / "little_loops"
        pkg.mkdir(parents=True)
        (pkg / "ok.py").write_text('"""O."""\n', encoding="utf-8")
        with patch.object(
            sys,
            "argv",
            ["ll-verify-des-audit", "--source-dir", str(pkg), "--json"],
        ):
            ret = main_verify_des_audit()
        data = json.loads(capsys.readouterr().out)
        assert ret == 0
        assert data["passed"] is True
        assert "uncovered_event_types" in data

    def test_json_output_violations_are_listed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """``--json`` emits a list of uncovered event types when the audit fails."""
        pkg = tmp_path / "scripts" / "little_loops"
        pkg.mkdir(parents=True)
        (pkg / "mod.py").write_text(
            '"""M."""\nfrom x import event_bus\nevent_bus.emit("totally_bogus", {})\n',
            encoding="utf-8",
        )
        with patch.object(
            sys,
            "argv",
            ["ll-verify-des-audit", "--source-dir", str(pkg), "--json"],
        ):
            ret = main_verify_des_audit()
        data = json.loads(capsys.readouterr().out)
        assert ret == 1
        assert data["passed"] is False
        assert "totally_bogus" in data["uncovered_event_types"]
