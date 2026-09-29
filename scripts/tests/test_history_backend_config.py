"""``history.backend`` configuration surface (FEAT-3535, Step 4).

Schema, ``HistoryConfig`` parsing and the secret-handling rule: a token is only ever named
by an environment variable, never accepted in config, echoed by ``to_dict`` or held by a
config object.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.config import BRConfig
from little_loops.config.features import HistoryBackendConfig, HistoryConfig

SCHEMA = Path(__file__).parent.parent / "little_loops" / "config-schema.json"
SENTINEL = "sentinel-token-DO-NOT-LEAK"


def _backend_schema() -> dict:
    return json.loads(SCHEMA.read_text())["properties"]["history"]["properties"]["backend"]


class TestSchema:
    def test_backend_block_declared_and_closed(self) -> None:
        backend = _backend_schema()
        assert backend["type"] == "object"
        assert backend.get("additionalProperties") is False
        assert set(backend["properties"]) == {
            "provider",
            "url",
            "url_env",
            "auth_token_env",
            "project_id",
            "telemetry_timeout_ms",
        }

    def test_provider_is_an_enum_defaulting_to_sqlite(self) -> None:
        provider = _backend_schema()["properties"]["provider"]
        assert provider["enum"] == ["sqlite", "libsql"]
        assert provider["default"] == "sqlite"

    def test_no_property_can_carry_a_literal_token(self) -> None:
        props = _backend_schema()["properties"]
        assert not {"auth_token", "token", "password", "secret"} & set(props)

    def test_history_block_still_rejects_unknown_keys(self) -> None:
        history = json.loads(SCHEMA.read_text())["properties"]["history"]
        assert history.get("additionalProperties") is False


class TestHistoryBackendConfig:
    def test_defaults_to_sqlite(self) -> None:
        cfg = HistoryConfig.from_dict({})
        assert cfg.backend == HistoryBackendConfig()
        assert cfg.backend.provider == "sqlite"
        assert cfg.backend.telemetry_timeout_ms == 1500
        assert cfg.backend.auth_token_env == "LL_HISTORY_AUTH_TOKEN"

    def test_parses_a_libsql_block(self) -> None:
        cfg = HistoryConfig.from_dict(
            {
                "backend": {
                    "provider": "libsql",
                    "url_env": "MY_URL",
                    "auth_token_env": "MY_TOKEN",
                    "project_id": "acme-api",
                    "telemetry_timeout_ms": 900,
                }
            }
        )
        assert cfg.backend.provider == "libsql"
        assert cfg.backend.url_env == "MY_URL"
        assert cfg.backend.project_id == "acme-api"
        assert cfg.backend.telemetry_timeout_ms == 900

    @pytest.mark.parametrize(
        "junk", [None, "x", 3, [], {"provider": 5}, {"telemetry_timeout_ms": "x"}]
    )
    def test_lenient_never_raises(self, junk: object) -> None:
        assert isinstance(HistoryConfig.from_dict({"backend": junk}).backend, HistoryBackendConfig)

    def test_a_literal_token_key_is_ignored_and_never_stored(self) -> None:
        cfg = HistoryConfig.from_dict({"backend": {"provider": "libsql", "auth_token": SENTINEL}})
        assert SENTINEL not in repr(cfg)
        assert SENTINEL not in json.dumps(cfg.backend.to_dict())


class TestToDict:
    def _config(self, tmp_path: Path, backend: dict) -> BRConfig:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"history": {"backend": backend}})
        )
        return BRConfig(tmp_path)

    def test_to_dict_carries_env_var_names_but_no_token(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_HISTORY_AUTH_TOKEN", SENTINEL)
        cfg = self._config(
            tmp_path,
            {
                "provider": "libsql",
                "url_env": "LL_HISTORY_URL",
                "auth_token": SENTINEL,
                "project_id": "p",
            },
        )
        rendered = json.dumps(cfg.to_dict())
        assert SENTINEL not in rendered
        backend = cfg.to_dict()["history"]["backend"]
        assert backend["provider"] == "libsql"
        assert backend["auth_token_env"] == "LL_HISTORY_AUTH_TOKEN"
        assert backend["project_id"] == "p"
