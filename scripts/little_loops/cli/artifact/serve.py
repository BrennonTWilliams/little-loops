"""``ll-artifact serve`` (FEAT-3323).

Blocking wrapper around `little_loops.transport.SseBridge` /
`serve_sse_bridge`: binds `events.bridge.port` (default `8766`, `--port`
overrides), fans in every `UnixSocketTransport` producer socket in the
project, and prints the full tokenized URL for the Level 1 (notify) page —
see `docs/reference/ARTIFACT_CONTROL_LEVELS.md`. One module per subcommand,
following the `cli/artifact/dashboard.py` convention.
"""

from __future__ import annotations

import argparse
import errno
import socket
from pathlib import Path

from little_loops.logger import Logger


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

    try:
        return serve_sse_bridge(config.events, port=port)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            logger.error(
                f"ll-artifact serve: port {port} is already in use (another "
                "ll-artifact serve?); pass --port N"
            )
            return 1
        raise
