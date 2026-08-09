"""Version-aware learning-test staleness (ENH-3125).

Covers the resolver (``resolve_target_version``), the widened
``is_record_stale()`` predicate, the stale-reason renderer
(``describe_staleness``), the ``cmd_prove`` capture path, and the
``backfill-versions`` subcommand — AC-1 through AC-10 of ENH-3125.
"""

from __future__ import annotations

import datetime
import importlib.metadata
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from little_loops.learning_tests import Assertion, LearnTestRecord, read_record, write_record
from little_loops.learning_tests.gate import (
    describe_staleness,
    is_record_stale,
    resolve_target_version,
)

TODAY = datetime.date.today()


def _record(
    *,
    target: str = "requests",
    date: str | None = None,
    status: str = "proven",
    proven_package: str | None = None,
    proven_version: str | None = None,
    age_days: int | None = None,
) -> LearnTestRecord:
    if date is None:
        offset = age_days if age_days is not None else 0
        date = (TODAY - datetime.timedelta(days=offset)).isoformat()
    return LearnTestRecord(
        target=target,
        date=date,
        status=status,  # type: ignore[arg-type]
        assertions=[Assertion(claim="c", result="pass")],
        raw_output_path=None,
        proven_package=proven_package,
        proven_version=proven_version,
    )


# ---------------------------------------------------------------------------
# resolve_target_version (AC-5, AC-10)
# ---------------------------------------------------------------------------


class TestResolveTargetVersion:
    def test_resolves_installed_distribution(self) -> None:
        with patch(
            "little_loops.init.install_check.importlib.metadata.version", return_value="9.9.9"
        ):
            assert resolve_target_version("requests") == ("requests", "9.9.9")

    def test_uses_first_token_lowercased(self) -> None:
        """``target`` is free text; only the first token is a package candidate."""
        with patch(
            "little_loops.init.install_check.importlib.metadata.version", return_value="1.0.0"
        ) as mock_version:
            assert resolve_target_version("Anthropic SDK streaming") == ("anthropic", "1.0.0")
        mock_version.assert_called_once_with("anthropic")

    @pytest.mark.parametrize("target", ["asyncio", "subprocess", "concurrent.futures"])
    def test_stdlib_targets_return_none(self, target: str) -> None:
        """AC-5: stdlib names must never bind to a squatted PyPI distribution."""
        with patch(
            "little_loops.init.install_check.importlib.metadata.version", return_value="4.0.0"
        ) as mock_version:
            assert resolve_target_version(target) is None
        mock_version.assert_not_called()

    def test_missing_package_returns_none(self) -> None:
        with patch(
            "little_loops.init.install_check.importlib.metadata.version",
            side_effect=importlib.metadata.PackageNotFoundError("nope"),
        ):
            assert resolve_target_version("definitely-not-installed") is None

    def test_empty_target_returns_none(self) -> None:
        assert resolve_target_version("") is None
        assert resolve_target_version("   ") is None

    def test_internal_error_returns_none(self) -> None:
        """AC-10: the resolver never propagates."""
        with patch(
            "little_loops.init.install_check.importlib.metadata.version",
            side_effect=RuntimeError("metadata exploded"),
        ):
            assert resolve_target_version("requests") is None


# ---------------------------------------------------------------------------
# is_record_stale (AC-2, AC-3, AC-4, AC-6, AC-9)
# ---------------------------------------------------------------------------


class TestVersionAwareStaleness:
    def test_drift_is_stale_on_the_day_it_was_proven(self) -> None:
        """AC-2: version drift fires regardless of age."""
        rec = _record(age_days=0, proven_package="requests", proven_version="1.0.0")
        assert is_record_stale(rec, 30, installed_version="2.0.0") is True

    def test_match_is_not_stale_past_the_ordinary_threshold(self) -> None:
        """AC-3: a matching version buys a longer leash."""
        rec = _record(age_days=31, proven_package="requests", proven_version="1.0.0")
        assert is_record_stale(rec, 30, installed_version="1.0.0") is False

    def test_match_is_stale_past_the_backstop(self) -> None:
        """AC-3: the leash is longer, not unlimited."""
        rec = _record(age_days=30 * 12 + 1, proven_package="requests", proven_version="1.0.0")
        assert is_record_stale(rec, 30, installed_version="1.0.0") is True

    def test_backstop_multiplier_is_configurable(self) -> None:
        rec = _record(age_days=61, proven_package="requests", proven_version="1.0.0")
        assert is_record_stale(rec, 30, installed_version="1.0.0", backstop_multiplier=2) is True
        assert is_record_stale(rec, 30, installed_version="1.0.0", backstop_multiplier=12) is False

    def test_no_captured_version_falls_back_to_age(self) -> None:
        """AC-4: pre-existing records behave exactly as today."""
        assert is_record_stale(_record(age_days=31), 30) is True
        assert is_record_stale(_record(age_days=29), 30) is False

    def test_unresolvable_package_falls_back_to_age(self) -> None:
        rec = _record(
            target="claude-code", proven_package="claude-code", proven_version="1.0.0", age_days=31
        )
        with patch(
            "little_loops.learning_tests.gate.resolve_target_version",
            return_value=None,
        ):
            assert is_record_stale(rec, 30) is True

    def test_resolves_internally_when_no_version_passed(self) -> None:
        rec = _record(age_days=0, proven_package="requests", proven_version="1.0.0")
        with patch(
            "little_loops.learning_tests.gate.resolve_target_version",
            return_value=("requests", "2.0.0"),
        ):
            assert is_record_stale(rec, 30) is True

    def test_resolver_keys_on_proven_package_not_target(self) -> None:
        """The stored distribution name is authoritative; target text is not re-derived."""
        rec = _record(
            target="Anthropic SDK streaming",
            proven_package="anthropic",
            proven_version="1.0.0",
            age_days=0,
        )
        with patch(
            "little_loops.learning_tests.gate.resolve_target_version",
            return_value=("anthropic", "1.0.0"),
        ) as mock_resolve:
            assert is_record_stale(rec, 30) is False
        mock_resolve.assert_called_once_with("anthropic")

    def test_drift_wins_over_unparseable_date(self) -> None:
        rec = _record(date="not-a-date", proven_package="requests", proven_version="1.0.0")
        assert is_record_stale(rec, 30, installed_version="2.0.0") is True

    def test_unparseable_date_without_drift_is_fresh(self) -> None:
        rec = _record(date="not-a-date")
        assert is_record_stale(rec, 30) is False

    def test_version_aware_false_restores_pure_age_behavior(self) -> None:
        """AC-9: the escape hatch is behaviorally identical to today."""
        drifted_fresh = _record(age_days=0, proven_package="requests", proven_version="1.0.0")
        assert (
            is_record_stale(drifted_fresh, 30, installed_version="2.0.0", version_aware=False)
            is False
        )
        matched_old = _record(age_days=31, proven_package="requests", proven_version="1.0.0")
        assert (
            is_record_stale(matched_old, 30, installed_version="1.0.0", version_aware=False) is True
        )

    def test_version_aware_false_never_resolves(self) -> None:
        rec = _record(age_days=0, proven_package="requests", proven_version="1.0.0")
        with patch("little_loops.learning_tests.gate.resolve_target_version") as mock_resolve:
            is_record_stale(rec, 30, version_aware=False)
        mock_resolve.assert_not_called()

    def test_manual_mark_stale_is_not_rescued_by_a_matching_version(self) -> None:
        """AC-6: status == 'stale' outranks a matching version at every call site."""
        rec = _record(age_days=0, status="stale", proven_package="requests", proven_version="1.0.0")
        assert is_record_stale(rec, 30, installed_version="1.0.0") is True

    def test_stale_after_days_zero_still_clamped(self) -> None:
        assert is_record_stale(_record(age_days=2), 0) is True


# ---------------------------------------------------------------------------
# describe_staleness (AC-8)
# ---------------------------------------------------------------------------


class TestDescribeStaleness:
    def test_fresh_record_has_no_description(self) -> None:
        assert describe_staleness(_record(age_days=0), 30) is None

    def test_age_stale_names_the_age(self) -> None:
        assert describe_staleness(_record(age_days=45), 30) == "stale: 45 days old"

    def test_drift_stale_names_the_version_transition(self) -> None:
        rec = _record(age_days=0, proven_package="requests", proven_version="1.0.0")
        desc = describe_staleness(rec, 30, installed_version="2.0.0")
        assert desc is not None
        assert "days old" not in desc
        assert "1.0.0" in desc and "2.0.0" in desc

    def test_manual_stale_is_described(self) -> None:
        desc = describe_staleness(_record(age_days=0, status="stale"), 30)
        assert desc is not None
        assert "days old" not in desc


# ---------------------------------------------------------------------------
# Record schema round-trip
# ---------------------------------------------------------------------------


class TestRecordVersionFields:
    def test_fields_default_to_none(self) -> None:
        rec = LearnTestRecord(
            target="pytest", date="2026-04-25", status="proven", assertions=[], raw_output_path=None
        )
        assert rec.proven_package is None
        assert rec.proven_version is None

    def test_round_trip_through_disk(self, tmp_path: Path) -> None:
        rec = _record(proven_package="requests", proven_version="1.2.3")
        write_record(rec, base_dir=tmp_path)
        restored = read_record("requests", base_dir=tmp_path)
        assert restored is not None
        assert restored.proven_package == "requests"
        assert restored.proven_version == "1.2.3"

    def test_from_dict_tolerates_absent_keys(self) -> None:
        rec = LearnTestRecord.from_dict(
            {"target": "pytest", "date": "2026-04-25", "status": "proven", "assertions": []}
        )
        assert rec.proven_version is None


# ---------------------------------------------------------------------------
# Capture path: cmd_prove (AC-1) and backfill-versions (AC-7)
# ---------------------------------------------------------------------------


class TestProveStampsVersion:
    def test_prove_writes_proven_package_and_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """AC-1: the record on disk carries the resolved package/version after prove."""
        from little_loops.cli.learning_tests import main_learning_tests

        base = tmp_path / ".ll" / "learning-tests"
        write_record(_record(target="requests", proven_version=None), base_dir=base)
        monkeypatch.chdir(tmp_path)

        with (
            patch("sys.argv", ["ll-learning-tests", "prove", "requests"]),
            patch("subprocess.run", return_value=Mock(returncode=0)),
            patch(
                "little_loops.init.install_check.importlib.metadata.version", return_value="2.31.0"
            ),
        ):
            assert main_learning_tests() == 0

        stored = read_record("requests", base_dir=base)
        assert stored is not None
        assert stored.proven_package == "requests"
        assert stored.proven_version == "2.31.0"
        assert json.loads(capsys.readouterr().out)["proven_version"] == "2.31.0"

    def test_prove_leaves_unresolvable_target_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.cli.learning_tests import main_learning_tests

        base = tmp_path / ".ll" / "learning-tests"
        write_record(_record(target="asyncio"), base_dir=base)
        monkeypatch.chdir(tmp_path)

        with (
            patch("sys.argv", ["ll-learning-tests", "prove", "asyncio"]),
            patch("subprocess.run", return_value=Mock(returncode=0)),
        ):
            assert main_learning_tests() == 0

        stored = read_record("asyncio", base_dir=base)
        assert stored is not None
        assert stored.proven_version is None


class TestBackfillVersions:
    def _seed(self, tmp_path: Path) -> Path:
        base = tmp_path / ".ll" / "learning-tests"
        write_record(_record(target="requests"), base_dir=base)
        write_record(_record(target="asyncio"), base_dir=base)
        return base

    def test_backfill_stamps_resolvable_and_skips_the_rest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC-7: resolvable non-stdlib targets get stamped; everything else is untouched."""
        from little_loops.cli.learning_tests import main_learning_tests

        base = self._seed(tmp_path)
        monkeypatch.chdir(tmp_path)
        with (
            patch("sys.argv", ["ll-learning-tests", "backfill-versions"]),
            patch(
                "little_loops.init.install_check.importlib.metadata.version", return_value="2.31.0"
            ),
        ):
            assert main_learning_tests() == 0

        requests_rec = read_record("requests", base_dir=base)
        asyncio_rec = read_record("asyncio", base_dir=base)
        assert requests_rec is not None and asyncio_rec is not None
        assert requests_rec.proven_version == "2.31.0"
        assert asyncio_rec.proven_version is None

    def test_backfill_is_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from little_loops.cli.learning_tests import main_learning_tests

        base = self._seed(tmp_path)
        monkeypatch.chdir(tmp_path)
        for _ in range(2):
            with (
                patch("sys.argv", ["ll-learning-tests", "backfill-versions"]),
                patch(
                    "little_loops.init.install_check.importlib.metadata.version",
                    return_value="2.31.0",
                ),
            ):
                assert main_learning_tests() == 0
        path = base / "requests.md"
        assert path.read_text().count("proven_version") == 1

    def test_dry_run_writes_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.cli.learning_tests import main_learning_tests

        base = self._seed(tmp_path)
        monkeypatch.chdir(tmp_path)
        with (
            patch("sys.argv", ["ll-learning-tests", "backfill-versions", "--dry-run"]),
            patch(
                "little_loops.init.install_check.importlib.metadata.version", return_value="2.31.0"
            ),
        ):
            assert main_learning_tests() == 0
        stored = read_record("requests", base_dir=base)
        assert stored is not None
        assert stored.proven_version is None
        assert "requests" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Discoverability hook message (AC-8)
# ---------------------------------------------------------------------------


class TestHookStaleMessage:
    def _setup(self, tmp_path: Path, record: LearnTestRecord) -> None:
        (tmp_path / ".ll").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"learning_tests": {"enabled": True, "discoverability": {"mode": "warn"}}})
        )
        write_record(record, base_dir=tmp_path / ".ll" / "learning-tests")

    def _event(self, tmp_path: Path, content: str):
        from little_loops.hooks.types import LLHookEvent

        return LLHookEvent(
            host="claude-code",
            intent="pre_tool_use",
            payload={
                "tool_name": "Write",
                "tool_input": {"file_path": "x.py", "content": content},
            },
            cwd=str(tmp_path),
        )

    def test_drift_stale_names_versions_not_days(self, tmp_path: Path) -> None:
        """AC-8: a drift-staled record must not render '(stale: 0 days old)'."""
        from little_loops.hooks import learning_tests_gate

        learning_tests_gate._SESSION_CACHE.clear()
        self._setup(
            tmp_path,
            _record(
                target="requests", age_days=0, proven_package="requests", proven_version="1.0.0"
            ),
        )
        with patch(
            "little_loops.init.install_check.importlib.metadata.version", return_value="2.31.0"
        ):
            result = learning_tests_gate.gate(self._event(tmp_path, "import requests\n"))
        assert result.feedback is not None
        assert "days old" not in result.feedback
        assert "1.0.0" in result.feedback and "2.31.0" in result.feedback

    def test_age_stale_still_names_days(self, tmp_path: Path) -> None:
        from little_loops.hooks import learning_tests_gate

        learning_tests_gate._SESSION_CACHE.clear()
        self._setup(tmp_path, _record(target="requests", age_days=45))
        result = learning_tests_gate.gate(self._event(tmp_path, "import requests\n"))
        assert result.feedback is not None
        assert "45 days old" in result.feedback


# ---------------------------------------------------------------------------
# Config plumbing
# ---------------------------------------------------------------------------


class TestVersionStalenessConfig:
    def test_defaults(self) -> None:
        from little_loops.config.features import LearningTestsConfig

        cfg = LearningTestsConfig()
        assert cfg.version_aware_staleness is True
        assert cfg.version_match_backstop_multiplier == 12

    def test_from_dict_overrides(self) -> None:
        from little_loops.config.features import LearningTestsConfig

        cfg = LearningTestsConfig.from_dict(
            {"version_aware_staleness": False, "version_match_backstop_multiplier": 3}
        )
        assert cfg.version_aware_staleness is False
        assert cfg.version_match_backstop_multiplier == 3

    def test_schema_declares_both_knobs(self) -> None:
        schema_path = Path(__file__).parent.parent / "little_loops" / "config-schema.json"
        props = json.loads(schema_path.read_text())["properties"]["learning_tests"]["properties"]
        assert props["version_aware_staleness"]["default"] is True
        assert props["version_match_backstop_multiplier"]["default"] == 12


class TestInstalledPackageVersionGeneralized:
    def test_defaults_to_little_loops(self) -> None:
        from little_loops.init.install_check import installed_package_version

        with patch(
            "little_loops.init.install_check.importlib.metadata.version", return_value="1.2.3"
        ) as mock_version:
            assert installed_package_version() == "1.2.3"
        mock_version.assert_called_once_with("little-loops")

    def test_accepts_an_explicit_package_name(self) -> None:
        from little_loops.init.install_check import installed_package_version

        with patch(
            "little_loops.init.install_check.importlib.metadata.version", return_value="2.31.0"
        ) as mock_version:
            assert installed_package_version("requests") == "2.31.0"
        mock_version.assert_called_once_with("requests")

    def test_missing_package_returns_none(self) -> None:
        from little_loops.init.install_check import installed_package_version

        with patch(
            "little_loops.init.install_check.importlib.metadata.version",
            side_effect=importlib.metadata.PackageNotFoundError("requests"),
        ):
            assert installed_package_version("requests") is None
