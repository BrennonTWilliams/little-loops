"""``ll-doctor`` under a remote history backend (FEAT-3535, Step 6).

The doctor reports the backend, reachability, recorded vs installed schema version, the
project stamp and config conflicts. It never echoes the auth token, and it never fails on a
remote target the way the local-file probes would (there is no file to stat).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from little_loops.cli import doctor
from little_loops.session_store import db as db_mod
from little_loops.session_store import remote_schema, remote_telemetry
from little_loops.session_store.hrana import HranaClient
from little_loops.session_store.schema import _MIGRATIONS
from tests.hrana_stub import HranaStub

TOKEN = "sentinel-token-DO-NOT-LEAK"
N = len(_MIGRATIONS)


def _write(root: Path, backend: dict, extra: dict | None = None) -> None:
    (root / ".ll").mkdir(exist_ok=True)
    (root / ".ll" / "ll-config.json").write_text(
        json.dumps({"history": {"backend": backend, **(extra or {})}})
    )


@pytest.fixture
def remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[HranaStub]:
    stub = HranaStub(token=TOKEN).start()
    monkeypatch.setenv("LL_HISTORY_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("LL_HISTORY_URL", stub.url)
    monkeypatch.delenv("LL_HISTORY_DB", raising=False)
    _write(
        tmp_path,
        {"provider": "libsql", "url_env": "LL_HISTORY_URL", "project_id": "acme-api"},
    )
    monkeypatch.chdir(tmp_path)
    remote_schema.clear_verification_cache()
    remote_telemetry.reset_for_tests()
    db_mod.clear_backend_config_cache()
    remote_schema.migrate_remote(HranaClient(stub.url, TOKEN), "acme-api")
    try:
        yield stub
    finally:
        stub.stop()
        remote_schema.clear_verification_cache()
        db_mod.clear_backend_config_cache()


class TestHistoryDbProbe:
    def test_reports_the_remote_backend_as_full(self, remote: HranaStub) -> None:
        data = doctor._history_db_data()
        assert data["status"] == "full"
        assert "libsql" in data["note"]
        assert "127.0.0.1" in data["note"]

    def test_an_unreachable_endpoint_is_an_error(self, remote: HranaStub) -> None:
        remote.stop()
        data = doctor._history_db_data()
        assert data["status"] == "unsupported" and data["severity"] == "error"
        assert TOKEN not in json.dumps(data)

    def test_schema_drift_is_not_applicable_and_never_raises(self, remote: HranaStub) -> None:
        data = doctor._schema_drift_data()
        assert data["status"] == "unsupported"
        assert data["severity"] == "informational"

    def test_the_probe_ignores_the_unreachable_marker(self, remote: HranaStub) -> None:
        remote_telemetry.mark_unreachable(remote.url)
        assert doctor._history_db_data()["status"] == "full"


class TestBackendData:
    def test_current_store(self, remote: HranaStub) -> None:
        data = doctor._history_backend_data()
        assert data["provider"] == "libsql"
        assert data["recorded_version"] == N and data["installed_version"] == N
        assert data["project_id"] == "acme-api" and data["stamped_project_id"] == "acme-api"
        assert data["status"] == "full"
        assert data["conflicts"] == []
        assert set(data["row_counts"]) >= {"raw_events", "message_events", "tool_events"}

    def test_behind_store_names_the_migrate_command(self, remote: HranaStub) -> None:
        remote.db.execute("update meta set value = '5' where key = 'schema_version'")
        remote_schema.clear_verification_cache()
        data = doctor._history_backend_data()
        assert data["recorded_version"] == 5
        assert data["status"] == "unsupported"
        assert "ll-session migrate" in data["note"]

    def test_project_mismatch_is_reported(self, remote: HranaStub, tmp_path: Path) -> None:
        _write(tmp_path, {"provider": "libsql", "url_env": "LL_HISTORY_URL", "project_id": "other"})
        db_mod.clear_backend_config_cache()
        data = doctor._history_backend_data()
        assert data["status"] == "unsupported" and data["severity"] == "error"
        assert "project_id" in data["note"]

    def test_history_db_env_conflict_is_reported(
        self, remote: HranaStub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / "x.db"))
        data = doctor._history_backend_data()
        assert any("LL_HISTORY_DB" in c for c in data["conflicts"])

    def test_history_db_path_conflict_is_reported(self, remote: HranaStub, tmp_path: Path) -> None:
        _write(
            tmp_path,
            {"provider": "libsql", "url_env": "LL_HISTORY_URL", "project_id": "acme-api"},
            extra={"db_path": "custom.db"},
        )
        db_mod.clear_backend_config_cache()
        assert any("db_path" in c for c in doctor._history_backend_data()["conflicts"])

    def test_sqlite_provider_is_informational(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".ll").mkdir()
        monkeypatch.chdir(tmp_path)
        db_mod.clear_backend_config_cache()
        data = doctor._history_backend_data()
        assert data["provider"] == "sqlite" and data["severity"] == "informational"


class TestNoTokenLeaks:
    def test_no_doctor_surface_echoes_the_token(
        self, remote: HranaStub, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = {
            "history_db": doctor._history_db_data(),
            "backend": doctor._history_backend_data(),
            "drift": doctor._schema_drift_data(),
        }
        doctor._print_history_db_section()
        doctor._print_history_backend_section()
        remote.stop()
        payload["down"] = doctor._history_backend_data()
        out = capsys.readouterr()
        assert TOKEN not in json.dumps(payload)
        assert TOKEN not in out.out and TOKEN not in out.err

    def test_registered_check_results_hold_no_token(self, remote: HranaStub) -> None:
        results = doctor._history_backend_check()
        assert results and results[0].name == "history_backend"
        assert TOKEN not in repr(results)
