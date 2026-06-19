"""Tests for learning test pre-release audit gate (ENH-2214)."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from little_loops.learning_tests import LearnTestRecord, write_record
from little_loops.learning_tests.import_scan import get_imported_packages
from little_loops.learning_tests.release_gate import run_release_gate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(
    project_dir: Path,
    *,
    enabled: bool = True,
    release_gate: str = "warn",
    stale_after_days: int = 30,
    scan_dirs: list[str] | None = None,
) -> None:
    ll_dir = project_dir / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    lt_config: dict = {
        "enabled": enabled,
        "release_gate": release_gate,
        "stale_after_days": stale_after_days,
    }
    if scan_dirs is not None:
        lt_config["scan_dirs"] = scan_dirs
    (ll_dir / "ll-config.json").write_text(
        json.dumps({"learning_tests": lt_config}),
        encoding="utf-8",
    )


def _write_record_file(
    project_dir: Path, target: str, status: str, date: str | None = None
) -> None:
    """Write a minimal learning-test record into project_dir's registry."""
    lt_dir = project_dir / ".ll" / "learning-tests"
    lt_dir.mkdir(parents=True, exist_ok=True)
    record_date = date if date is not None else datetime.date.today().isoformat()
    record = LearnTestRecord(
        target=target,
        date=record_date,
        status=status,  # type: ignore[arg-type]
        assertions=[],
        raw_output_path=None,
    )
    write_record(record, base_dir=lt_dir)


def _write_source_file(project_dir: Path, rel_path: str, content: str) -> None:
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _base_dir(project_dir: Path) -> Path:
    return project_dir / ".ll" / "learning-tests"


# ---------------------------------------------------------------------------
# Tests: get_imported_packages
# ---------------------------------------------------------------------------


class TestGetImportedPackages:
    def test_finds_simple_import(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text("import requests\n")
        result = get_imported_packages([tmp_path])
        assert "requests" in result

    def test_finds_from_import(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text("from anthropic import Anthropic\n")
        result = get_imported_packages([tmp_path])
        assert "anthropic" in result

    def test_multiple_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("import requests\n")
        (tmp_path / "b.py").write_text("import stripe\n")
        result = get_imported_packages([tmp_path])
        assert "requests" in result
        assert "stripe" in result

    def test_recursive_subdirs(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").write_text("import boto3\n")
        result = get_imported_packages([tmp_path])
        assert "boto3" in result

    def test_multiple_source_dirs(self, tmp_path: Path) -> None:
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "x.py").write_text("import requests\n")
        (dir_b / "y.py").write_text("import stripe\n")
        result = get_imported_packages([dir_a, dir_b])
        assert "requests" in result
        assert "stripe" in result

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        result = get_imported_packages([tmp_path / "nonexistent"])
        assert result == set()

    def test_non_py_files_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("import requests\n")
        (tmp_path / "script.sh").write_text("import requests\n")
        result = get_imported_packages([tmp_path])
        assert "requests" not in result

    def test_deduplicates_across_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("import requests\n")
        (tmp_path / "b.py").write_text("import requests\n")
        result = get_imported_packages([tmp_path])
        assert result == {"requests"}


# ---------------------------------------------------------------------------
# Tests: run_release_gate
# ---------------------------------------------------------------------------


class TestReleaseGateDisabled:
    def test_skips_when_lt_disabled(self, tmp_path: Path) -> None:
        _write_config(tmp_path, enabled=False, release_gate="block")
        _write_record_file(tmp_path, "requests", "refuted")
        _write_source_file(tmp_path, "scripts/main.py", "import requests\n")
        result = run_release_gate(tmp_path, base_dir=_base_dir(tmp_path))
        assert result == 0

    def test_skips_when_no_config(self, tmp_path: Path) -> None:
        _write_record_file(tmp_path, "requests", "refuted")
        _write_source_file(tmp_path, "scripts/main.py", "import requests\n")
        result = run_release_gate(tmp_path, base_dir=_base_dir(tmp_path))
        assert result == 0


class TestReleaseGateWarnMode:
    def test_returns_0_on_stale_imported_package(self, tmp_path: Path) -> None:
        _write_config(tmp_path, enabled=True, release_gate="warn")
        _write_record_file(tmp_path, "requests", "proven", date="2020-01-01")
        _write_source_file(tmp_path, "scripts/main.py", "import requests\n")
        result = run_release_gate(tmp_path, base_dir=_base_dir(tmp_path))
        assert result == 0

    def test_returns_0_on_refuted_imported_package(self, tmp_path: Path) -> None:
        _write_config(tmp_path, enabled=True, release_gate="warn")
        _write_record_file(tmp_path, "anthropic", "refuted")
        _write_source_file(tmp_path, "scripts/main.py", "import anthropic\n")
        result = run_release_gate(tmp_path, base_dir=_base_dir(tmp_path))
        assert result == 0


class TestReleaseGateBlockMode:
    def test_returns_1_on_stale_imported_package(self, tmp_path: Path) -> None:
        _write_config(tmp_path, enabled=True, release_gate="block")
        _write_record_file(tmp_path, "requests", "proven", date="2020-01-01")
        _write_source_file(tmp_path, "scripts/main.py", "import requests\n")
        result = run_release_gate(tmp_path, base_dir=_base_dir(tmp_path))
        assert result == 1

    def test_returns_1_on_refuted_imported_package(self, tmp_path: Path) -> None:
        _write_config(tmp_path, enabled=True, release_gate="block")
        _write_record_file(tmp_path, "anthropic", "refuted")
        _write_source_file(tmp_path, "scripts/main.py", "import anthropic\n")
        result = run_release_gate(tmp_path, base_dir=_base_dir(tmp_path))
        assert result == 1

    def test_returns_0_on_fresh_proven_package(self, tmp_path: Path) -> None:
        _write_config(tmp_path, enabled=True, release_gate="block")
        today = datetime.date.today().isoformat()
        _write_record_file(tmp_path, "requests", "proven", date=today)
        _write_source_file(tmp_path, "scripts/main.py", "import requests\n")
        result = run_release_gate(tmp_path, base_dir=_base_dir(tmp_path))
        assert result == 0

    def test_excludes_unimported_packages(self, tmp_path: Path) -> None:
        """Stale/refuted records for packages not imported in scan_dirs are excluded."""
        _write_config(tmp_path, enabled=True, release_gate="block")
        _write_record_file(tmp_path, "stripe", "refuted")
        # scripts/ dir exists but doesn't import stripe
        _write_source_file(tmp_path, "scripts/main.py", "import anthropic\n")
        result = run_release_gate(tmp_path, base_dir=_base_dir(tmp_path))
        assert result == 0

    def test_returns_0_when_no_stale_or_refuted_records(self, tmp_path: Path) -> None:
        _write_config(tmp_path, enabled=True, release_gate="block")
        # No records at all
        result = run_release_gate(tmp_path, base_dir=_base_dir(tmp_path))
        assert result == 0

    def test_custom_scan_dirs(self, tmp_path: Path) -> None:
        """Respects learning_tests.scan_dirs config key."""
        _write_config(tmp_path, enabled=True, release_gate="block", scan_dirs=["lib/"])
        _write_record_file(tmp_path, "requests", "refuted")
        # Only lib/ is scanned, not scripts/
        _write_source_file(tmp_path, "scripts/main.py", "import requests\n")
        _write_source_file(tmp_path, "lib/util.py", "import something_else\n")
        result = run_release_gate(tmp_path, base_dir=_base_dir(tmp_path))
        # "requests" is not imported in lib/, so gate passes
        assert result == 0
