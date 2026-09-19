"""Connected policy-builder HTTP routes for ``ll-artifact serve --policy-builder`` (FEAT-3504).

Issue-list, submit, and readback handlers exposing FEAT-3498's host-side
run-request contracts over HTTP. This module owns policy-payload knowledge
(body guards, the JSON `ErrorBody` shape, the nine-step submit ordering);
``SseBridge`` (``transport.py``) owns generic method/path dispatch and the
shared Host/token checks and knows nothing about policy payloads.

These routes only submit/read requests — they never approve, drain, launch a
process, or import ``LocalBridgeTransport``. Host approval is FEAT-3498's
``ll-queue run --id ID --approve``; host rejection is ``ll-queue cancel``.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import logging
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

from little_loops.cli.artifact.policy_revision import (
    PolicyRevisionConflictError,
    RunRequest,
    persist_policy_revision,
    validate_policy_revision,
)
from little_loops.issue_parser import find_issues
from little_loops.queue_store import create_or_get_run_request, get_run_request
from little_loops.runner_spec import ActionSpec, RunnerType

if TYPE_CHECKING:
    from little_loops.config.core import BRConfig

logger = logging.getLogger(__name__)

__all__ = ["make_run_request_routes"]

# Bounds the connected submit body; independent of `artifacts.export.max_artifact_bytes`
# (that key governs outbound history-snapshot exports — a different meaning and far too
# large a bound for a single policy YAML submission).
_MAX_RUN_REQUEST_BYTES = 1 << 20  # 1 MiB

_REQUEST_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_REVISION_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_WORKSPACE_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_MAX_SIMPLE_FIELD_LEN = 128


class _RouteError(Exception):
    """Raised by a route body to short-circuit with a structured `ErrorBody` response."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.errors = errors
        self.warnings = warnings


def _send_json(
    handler: http.server.BaseHTTPRequestHandler,
    status: int,
    payload: dict[str, Any],
    *,
    no_store: bool = False,
) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    if no_store:
        handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _send_error(
    handler: http.server.BaseHTTPRequestHandler,
    err: _RouteError,
    *,
    no_store: bool = False,
) -> None:
    error_body: dict[str, Any] = {"code": err.code, "message": err.message}
    if err.errors is not None:
        error_body["errors"] = err.errors
    if err.warnings is not None:
        error_body["warnings"] = err.warnings
    _send_json(handler, err.status, {"error": error_body}, no_store=no_store)


def _json_error_boundary(fn: Any, *, no_store: bool = False) -> Any:
    """Wrap a route body so any failure becomes a structured JSON response.

    A `_RouteError` raised by the body becomes its documented status/code. Any
    other exception is logged server-side (never a traceback in the response)
    and returned as `500 internal_error` — per FEAT-3504's unexpected-failure
    contract, this never rolls back a write that may have already committed
    (the queue transaction may have succeeded before the failure occurred).
    """

    def _wrapped(handler: http.server.BaseHTTPRequestHandler, *args: Any) -> None:
        try:
            fn(handler, *args)
        except _RouteError as err:
            _send_error(handler, err, no_store=no_store)
        except Exception:
            logger.error("policy_builder_routes: unexpected route failure", exc_info=True)
            _send_error(
                handler,
                _RouteError(500, "internal_error", "internal server error"),
                no_store=no_store,
            )

    return _wrapped


def _require_str_field(payload: dict[str, Any], name: str, pattern: re.Pattern[str]) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not pattern.match(value):
        raise _RouteError(400, "bad_request", f"missing or malformed field: {name}")
    return value


def _require_simple_str_field(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value or len(value) > _MAX_SIMPLE_FIELD_LEN:
        raise _RouteError(400, "bad_request", f"missing or malformed field: {name}")
    return value


def _read_request_body(handler: http.server.BaseHTTPRequestHandler) -> bytes:
    """Body guards: `Content-Length` presence/bound, then `Content-Type`."""
    length_header = handler.headers.get("Content-Length")
    if length_header is None:
        raise _RouteError(400, "bad_request", "missing Content-Length")
    try:
        length = int(length_header)
    except ValueError:
        raise _RouteError(400, "bad_request", "invalid Content-Length") from None
    if length < 0:
        raise _RouteError(400, "bad_request", "invalid Content-Length")
    if length > _MAX_RUN_REQUEST_BYTES:
        raise _RouteError(413, "body_too_large", "request body exceeds the size limit")

    content_type = (handler.headers.get("Content-Type") or "").split(";", 1)[0].strip()
    if content_type != "application/json":
        raise _RouteError(400, "bad_request", "Content-Type must be application/json")

    return handler.rfile.read(length) if length else b""


def _parse_run_request(payload_bytes: bytes) -> tuple[RunRequest, dict[str, Any]]:
    """Step 1: JSON parse + field presence/type/shape guards; build a `RunRequest`."""
    try:
        payload = json.loads(payload_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise _RouteError(400, "bad_request", "invalid JSON body") from None
    if not isinstance(payload, dict):
        raise _RouteError(400, "bad_request", "JSON body must be an object")

    request_id = _require_str_field(payload, "requestId", _REQUEST_ID_RE)
    revision_id = _require_str_field(payload, "revisionId", _REVISION_ID_RE)
    workspace_id = _require_str_field(payload, "workspaceId", _WORKSPACE_ID_RE)
    project_id = _require_simple_str_field(payload, "projectId")
    issue_id = _require_simple_str_field(payload, "issueId")
    yaml_text = payload.get("yaml")
    if not isinstance(yaml_text, str) or not yaml_text:
        raise _RouteError(400, "bad_request", "missing or malformed field: yaml")

    request = RunRequest(
        request_id=request_id,
        project_id=project_id,
        workspace_id=workspace_id,
        revision_id=revision_id,
        yaml=yaml_text.encode("utf-8"),
        issue_id=issue_id,
    )
    return request, payload


def _make_submit_handler(config: BRConfig, *, workspace_id: str) -> Any:
    def _submit(handler: http.server.BaseHTTPRequestHandler) -> None:
        body_bytes = _read_request_body(handler)
        request, _payload = _parse_run_request(body_bytes)

        # Step 2: recompute the hash; the route (not persist_policy_revision)
        # is the only place that checks it against the caller's revisionId.
        actual_hash = hashlib.sha256(request.yaml).hexdigest()
        if actual_hash != request.revision_id:
            raise _RouteError(422, "revision_mismatch", "revisionId does not match yaml bytes")

        # Step 3: workspace binding.
        if request.workspace_id != workspace_id:
            raise _RouteError(403, "wrong_workspace", "workspaceId does not match this server")

        # Step 4: existing-request early return — bypasses mutable issue/
        # validation/persistence checks for a matching retry.
        existing = get_run_request(request.request_id, workspace_id, root=config.project_root)
        if existing is not None:
            if (
                existing.revision_id != request.revision_id
                or existing.issue_id != request.issue_id
                or existing.project_root != str(config.project_root)
            ):
                raise _RouteError(
                    409, "request_conflict", "requestId is already bound to a different revision"
                )
            _send_json(
                handler,
                200,
                {"requestId": request.request_id, "queueId": existing.id, "created": False},
            )
            return

        # Step 5: new-request issue-existence check.
        issues = find_issues(config)
        if not any(info.issue_id == request.issue_id for info in issues):
            raise _RouteError(404, "issue_not_found", "issue does not exist in this project")

        # Step 6: validate the submitted YAML.
        outcome = validate_policy_revision(request.yaml, project_root=config.project_root)
        if not outcome.ok:
            raise _RouteError(
                422,
                "validation_failed",
                "policy revision failed validation",
                errors=outcome.errors,
                warnings=outcome.warnings,
            )

        # Step 7: persist the immutable revision snapshot.
        try:
            dest = persist_policy_revision(
                request.yaml, request.revision_id, project_root=config.project_root
            )
        except PolicyRevisionConflictError as exc:
            raise _RouteError(409, "request_conflict", str(exc)) from exc

        # Step 8: enqueue as awaiting_approval. timeout=None is mandatory — the
        # default 120s would kill a real lifecycle run.
        action = ActionSpec(
            name=f"policy-builder:{request.issue_id}",
            runner=RunnerType.LOOP,
            target=str(dest),
            timeout=None,
        )
        entry, created = create_or_get_run_request(
            request, action=action, project_root=config.project_root, root=config.project_root
        )

        # Step 9.
        _send_json(
            handler,
            200,
            {
                "requestId": request.request_id,
                "queueId": entry.id,
                "created": created,
                "warnings": outcome.warnings,
            },
        )

    return _json_error_boundary(_submit)


def _make_readback_handler(config: BRConfig, *, workspace_id: str) -> Any:
    def _readback(handler: http.server.BaseHTTPRequestHandler, request_id: str) -> None:
        if not _REQUEST_ID_RE.match(request_id):
            raise _RouteError(400, "bad_request", "requestId is not a valid UUID")

        query = parse_qs(urlsplit(handler.path).query)
        actual_workspace_id = (query.get("workspaceId") or [""])[0]
        if actual_workspace_id != workspace_id:
            raise _RouteError(403, "wrong_workspace", "workspaceId does not match this server")

        entry = get_run_request(request_id, workspace_id, root=config.project_root)
        if entry is None:
            raise _RouteError(404, "request_not_found", "no run request with that id")

        _send_json(
            handler,
            200,
            {
                "requestId": entry.request_id,
                "queueId": entry.id,
                "status": entry.status,
                "bindings": {"issueId": entry.issue_id, "revisionId": entry.revision_id},
                "loopInstanceId": entry.loop_instance_id,
                "runDir": entry.run_dir,
                "result": entry.result,
            },
            no_store=True,
        )

    return _json_error_boundary(_readback, no_store=True)


def _make_issues_handler(config: BRConfig) -> Any:
    def _issues(handler: http.server.BaseHTTPRequestHandler) -> None:
        summaries = [
            {
                "id": info.issue_id,
                "title": info.title,
                "priority": info.priority,
                "status": info.status,
                "path": str(info.path),
            }
            for info in find_issues(config)
        ]
        _send_json(handler, 200, {"issues": summaries})

    return _json_error_boundary(_issues)


def make_run_request_routes(config: BRConfig, *, workspace_id: str) -> list[tuple[str, str, Any]]:
    """Build the `(method, pattern, handler)` tuples for `SseBridge.method_routes`.

    Submit, readback, and issue-list — the three connected application routes
    this issue adds (the page route itself is composed separately in
    `cli/artifact/serve.py`, from `render_policy_builder_html`).
    """
    return [
        ("POST", "run-request", _make_submit_handler(config, workspace_id=workspace_id)),
        (
            "GET",
            "run-request/{requestId}",
            _make_readback_handler(config, workspace_id=workspace_id),
        ),
        ("GET", "issues", _make_issues_handler(config)),
    ]
