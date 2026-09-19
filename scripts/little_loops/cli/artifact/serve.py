"""``ll-artifact serve`` (FEAT-3323; read-only history route FEAT-3321).

Blocking wrapper around `little_loops.transport.SseBridge` /
`serve_sse_bridge`: binds `events.bridge.port` (default `8766`, `--port`
overrides), fans in every `UnixSocketTransport` producer socket in the
project, and prints the full tokenized URL for the Level 1 (notify) page —
see `docs/reference/ARTIFACT_CONTROL_LEVELS.md`. One module per subcommand,
following the `cli/artifact/dashboard.py` convention.

When `events.bridge.history` is `true`, `cmd_serve` also mounts a read-only
`GET /{token}/history` route (`make_history_route`) and serves the
`dashboard.llat` page in place of the FEAT-3323 placeholder, so a `sql.js`
query box refreshes against the live `.ll/history.db` on a timer. With the
gate off (the default), `ll-artifact serve` is byte-for-byte FEAT-3323
behavior — see FEAT-3321's § Expected Behavior.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import http.server
import json
import socket
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.logger import Logger

if TYPE_CHECKING:
    from little_loops.config.core import BRConfig
    from little_loops.transport import SseBridge


def add_serve_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``serve`` subcommand parser."""
    serve = subparsers.add_parser(
        "serve",
        help="Serve live EventBus events over a localhost SSE bridge",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=None,
        help="TCP port to bind (default: events.bridge.port, 8766)",
    )
    serve.add_argument(
        "--policy-builder",
        action="store_true",
        default=False,
        help="Also serve the connected policy builder at GET /{token}/policy-builder (FEAT-3504)",
    )


def derive_workspace_id(project_root: Path) -> str:
    """Deterministic 16-hex-char workspace id for *project_root* (FEAT-3504).

    First 16 hex chars of the SHA-256 of the resolved project root path, so
    it stays stable across serve restarts (a fresh per-process token cannot
    be used here — request dedup and readback both key on
    ``(workspace_id, request_id)``, so a per-process value would break the
    reload/retry acceptance criterion). Callers must resolve *project_root*
    once and reuse that single value everywhere workspace identity matters
    (this function, the request-binding comparison, and the queue-store
    calls) — a symlinked cwd re-resolving differently across calls would
    otherwise keep the same workspace id but change the bound path string.
    """
    return hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:16]


def make_history_route(
    config: BRConfig,
) -> Callable[[http.server.BaseHTTPRequestHandler], None]:
    """Build the handler mounted at ``"history"`` (FEAT-3321).

    Never migrates or creates ``.ll/history.db`` (``allow_missing=True``
    reads through :func:`~little_loops.cli.artifact.dashboard.build_history_payload`,
    whose read-only opener never touches a missing file). Caches the built
    JSON body behind a lock, keyed on the source db's ``(st_mtime_ns,
    st_size)`` — without this, N open browser tabs each cost one full
    ATTACH + ``CREATE TABLE ... AS SELECT`` + gzip + base64 over the whole
    db every `history_poll_s` seconds, unbounded (``max_clients`` gates only
    the SSE stream, not ``_routes``). A matching ``If-None-Match`` returns
    ``304`` with no body; a ``ValueError`` from the size pre-check (raw
    snapshot over ``artifacts.export.max_artifact_bytes``) becomes ``413``.
    """
    from little_loops.cli.artifact.dashboard import build_history_payload

    db_path = config.project_root / ".ll" / "history.db"
    mode = config.artifacts.export.mode
    local_mode = mode == "local"

    lock = threading.Lock()
    cache_key: tuple[int, int] | None = None
    cache_body: bytes | None = None
    cache_etag: str | None = None
    cache_initialized = False

    def handler(req: http.server.BaseHTTPRequestHandler) -> None:
        nonlocal cache_key, cache_body, cache_etag, cache_initialized

        try:
            st = db_path.stat()
            current_key: tuple[int, int] | None = (st.st_mtime_ns, st.st_size)
        except OSError:
            current_key = None

        with lock:
            if not cache_initialized or current_key != cache_key:
                from little_loops.cli.artifact.dashboard import resolve_tables

                tables = resolve_tables(None, local_mode)
                try:
                    payload = build_history_payload(
                        db_path=db_path,
                        config=config,
                        tables=tables,
                        since_iso=None,
                        mode=mode,
                        allow_missing=True,
                    )
                except ValueError as exc:
                    body = str(exc).encode("utf-8")
                    req.send_response(413)
                    req.send_header("Content-Type", "text/plain; charset=utf-8")
                    req.send_header("Content-Length", str(len(body)))
                    req.end_headers()
                    req.wfile.write(body)
                    return
                cache_key = current_key
                cache_body = json.dumps(payload.to_dict()).encode("utf-8")
                cache_etag = (
                    f'"{current_key[0]}-{current_key[1]}"' if current_key is not None else '"empty"'
                )
                cache_initialized = True
            response_body = cache_body
            response_etag = cache_etag
        # set by the branch above on first request (cache_initialized guards every path)
        assert response_body is not None and response_etag is not None

        if req.headers.get("If-None-Match") == response_etag:
            req.send_response(304)
            req.send_header("ETag", response_etag)
            req.end_headers()
            return

        req.send_response(200)
        req.send_header("Content-Type", "application/json")
        req.send_header("Cache-Control", "no-store")
        req.send_header("ETag", response_etag)
        req.send_header("Content-Length", str(len(response_body)))
        req.end_headers()
        req.wfile.write(response_body)

    return handler


def _make_page_html_factory(config: BRConfig) -> Callable[[SseBridge], str]:
    """Build the ``page_html_factory`` passed to ``serve_sse_bridge`` (FEAT-3321)."""

    def factory(bridge: SseBridge) -> str:
        from little_loops.cli.artifact.dashboard import (
            ServeContext,
            build_dashboard_html,
            resolve_tables,
        )

        mode = config.artifacts.export.mode
        result = build_dashboard_html(
            db_path=config.project_root / ".ll" / "history.db",
            config=config,
            tables=resolve_tables(None, mode == "local"),
            since_iso=None,
            mode=mode,
            serve_context=ServeContext(
                events_url=bridge.url + "events",
                interaction_url=None,
                history_url=bridge.url + "history",
            ),
        )
        return result.html

    return factory


def cmd_serve(args: argparse.Namespace, logger: Logger) -> int:
    """Bind the SSE bridge and block until Ctrl-C.

    Returns 0 on a clean Ctrl-C shutdown, 1 on a bind failure (port already in
    use, or AF_UNIX unavailable on this platform — the same message
    `wire_transports` uses for the "socket" transport).
    """
    if not hasattr(socket, "AF_UNIX"):
        logger.error(
            "UnixSocketTransport requires AF_UNIX, which is not available on this "
            "platform (e.g. Windows). ll-artifact serve has nothing to fan in without it."
        )
        return 1

    from little_loops.config.core import BRConfig
    from little_loops.transport import serve_sse_bridge

    config = BRConfig(Path.cwd())
    port = args.port if getattr(args, "port", None) is not None else config.events.bridge.port

    routes = None
    page_html_factory = None
    if config.events.bridge.history:
        routes = {"history": make_history_route(config)}
        page_html_factory = _make_page_html_factory(config)

    method_routes = None
    extra_url_suffixes = None
    if getattr(args, "policy_builder", False):
        from little_loops.cli.artifact.policy_builder import render_policy_builder_html
        from little_loops.cli.artifact.policy_builder_routes import make_run_request_routes

        # § Scope and origin: resolved once and reused everywhere workspace
        # identity matters (derive_workspace_id, the route module's binding
        # comparisons, and the queue-store calls it makes).
        root = config.project_root.resolve()
        workspace_id = derive_workspace_id(root)
        policy_builder_html = render_policy_builder_html(config, workspace_id=workspace_id)

        def _serve_policy_builder_page(handler: http.server.BaseHTTPRequestHandler) -> None:
            body = policy_builder_html.encode("utf-8")
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html; charset=utf-8")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)

        method_routes = [
            ("GET", "policy-builder", _serve_policy_builder_page),
            *make_run_request_routes(config, workspace_id=workspace_id),
        ]
        extra_url_suffixes = ["policy-builder"]

    try:
        return serve_sse_bridge(
            config.events,
            port=port,
            routes=routes,
            method_routes=method_routes,
            page_html_factory=page_html_factory,
            extra_url_suffixes=extra_url_suffixes,
        )
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            logger.error(
                f"ll-artifact serve: port {port} is already in use (another "
                "ll-artifact serve?); pass --port N"
            )
            return 1
        raise
