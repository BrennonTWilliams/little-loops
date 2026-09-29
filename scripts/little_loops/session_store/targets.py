"""History-store target types (ENH-3650, extended by FEAT-3535).

Leaf module with no ``session_store`` dependencies, so both :mod:`.db` (which resolves a
target) and :mod:`.backend` (which consumes one) can import it without a cycle.
``backend`` re-exports every name here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_URL_ENV = "LL_HISTORY_URL"
DEFAULT_TOKEN_ENV = "LL_HISTORY_AUTH_TOKEN"
DEFAULT_TELEMETRY_TIMEOUT_MS = 1500


@dataclass(frozen=True)
class BackendConfig:
    """Connection settings for a non-filesystem provider (``history.backend``).

    Holds the *names* of the environment variables that carry the endpoint and the auth
    token, never the token itself: a literal token is not accepted in config, and
    nothing here can echo one. ``url`` is an optional non-secret literal endpoint;
    exactly one of ``url`` / ``url_env`` supplies the endpoint.
    """

    provider: str
    url: str | None = None
    url_env: str | None = None
    auth_token_env: str = DEFAULT_TOKEN_ENV
    project_id: str | None = None
    telemetry_timeout_ms: int = DEFAULT_TELEMETRY_TIMEOUT_MS

    def endpoint(self) -> str:
        """Return the endpoint URL (the literal ``url``, else the ``url_env`` variable).

        Raises:
            HistoryUnavailable: no endpoint is configured or the variable is unset.
        """
        if self.url:
            return self.url
        name = self.url_env or DEFAULT_URL_ENV
        value = os.environ.get(name, "").strip()
        if not value:
            from little_loops.session_store.backend import HistoryUnavailable

            raise HistoryUnavailable(
                f"history.backend endpoint is not configured: set ${name} (or history.backend.url)"
            )
        return value

    def auth_token(self) -> str | None:
        """Return the auth token from its environment variable, or ``None`` if unset."""
        return os.environ.get(self.auth_token_env) or None


@dataclass(frozen=True)
class LocalTarget:
    """A history store on the local filesystem."""

    path: Path

    @property
    def provider(self) -> str:
        return "sqlite"


@dataclass(frozen=True)
class RemoteTarget:
    """A history store with no filesystem path."""

    config: BackendConfig

    @property
    def provider(self) -> str:
        return self.config.provider


HistoryTarget = LocalTarget | RemoteTarget
