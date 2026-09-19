"""Tests for FEAT-3504: connected policy-builder serve routes.

Route-level tests build a real `SseBridge` with `method_routes` (the same
shape `cmd_serve --policy-builder` composes) over a temp project, and drive
it with `_lb_http_request` — the `TestLocalBridgeTransport`/`TestHistoryRoute`
precedent for exercising real HTTP against these handlers.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import re
import shutil
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

from little_loops.cli.artifact.policy_builder import render_policy_builder_html
from little_loops.cli.artifact.policy_builder_routes import make_run_request_routes
from little_loops.cli.artifact.serve import derive_workspace_id
from little_loops.config.core import BRConfig
from little_loops.config.features import EventsConfig
from little_loops.queue_store import DEFAULT_DB_PATH, cancel_entry, claim_entry, list_entries
from little_loops.transport import SseBridge
from tests.test_transport import _lb_http_request

GOLDEN_LIFECYCLE_YAML = (
    Path(__file__).parent / "fixtures" / "policy_builder" / "sample-issue-lifecycle.yaml"
).read_bytes()


def _make_config(project_root: Path) -> BRConfig:
    (project_root / ".ll").mkdir(parents=True, exist_ok=True)
    (project_root / ".ll" / "ll-config.json").write_text("{}", encoding="utf-8")
    features_dir = project_root / ".issues" / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    (features_dir / "P3-FEAT-1-sample.md").write_text(
        "---\nstatus: open\n---\n# FEAT-1: Sample feature\n\n## Summary\nSample.",
        encoding="utf-8",
    )
    return BRConfig(project_root)


def _events_config() -> EventsConfig:
    config = EventsConfig()
    config.transports = ["socket"]
    return config


def _bridge_for(config: BRConfig, workspace_id: str, *, base: Path, loops_dir: Path) -> SseBridge:
    html = render_policy_builder_html(config, workspace_id=workspace_id)

    def _page(handler: Any) -> None:
        body = html.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    method_routes = [
        ("GET", "policy-builder", _page),
        *make_run_request_routes(config, workspace_id=workspace_id),
    ]
    return SseBridge(
        _events_config(), port=0, base=base, loops_dir=loops_dir, method_routes=method_routes
    )


def _port(bridge: SseBridge) -> int:
    return int(urlparse(bridge.url).netloc.split(":")[1])


def _submit_payload(
    *,
    workspace_id: str,
    issue_id: str = "FEAT-1",
    request_id: str | None = None,
    yaml_bytes: bytes = GOLDEN_LIFECYCLE_YAML,
    revision_id: str | None = None,
) -> bytes:
    payload = {
        "requestId": request_id or str(uuid.uuid4()),
        "projectId": "doc-1",
        "workspaceId": workspace_id,
        "revisionId": revision_id or hashlib.sha256(yaml_bytes).hexdigest(),
        "yaml": yaml_bytes.decode("utf-8"),
        "issueId": issue_id,
    }
    return json.dumps(payload).encode("utf-8")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


@pytest.fixture
def short_tmp_path() -> Iterator[Path]:
    """Tmp dir with a short absolute path (AF_UNIX 104-char `sun_path` limit).

    Duplicated from `tests.test_transport` per that module's own note: a
    pytest fixture imported cross-module and used as a parameter name trips
    ruff's F811.
    """
    d = Path(tempfile.mkdtemp(prefix="ll-"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


class TestPageRoute:
    def test_serves_html_with_stamped_workspace_context(
        self, project: Path, short_tmp_path: Path
    ) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            status, body = _lb_http_request(
                _port(bridge), "GET", f"/{bridge._token}/policy-builder"
            )
            assert status == 200
            html = body.decode("utf-8")
            assert "const CONNECTED_CONTEXT = " in html
            m = re.search(r"const CONNECTED_CONTEXT = (\{.*?\});", html)
            assert m is not None
            assert json.loads(m.group(1)) == {"workspaceId": workspace_id}
        finally:
            bridge.close()


class TestSubmitRoute:
    def test_new_request_is_awaiting_approval_and_never_dispatched(
        self, project: Path, short_tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # claim_entry has no `root` kwarg; its default-shaped ".ll/queue.db"
        # resolves via cwd-walk (queue_store._is_default_shaped), so anchor
        # cwd at the project like test_cli_queue_run.py's precedent does.
        monkeypatch.chdir(project)
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            body = _submit_payload(workspace_id=workspace_id)
            status, resp = _lb_http_request(
                _port(bridge), "POST", f"/{bridge._token}/run-request", body=body
            )
            assert status == 200
            parsed = json.loads(resp)
            assert parsed["created"] is True
            assert parsed["warnings"] == []

            entries = list_entries(DEFAULT_DB_PATH, root=project)
            assert len(entries) == 1
            assert entries[0].status == "awaiting_approval"

            # A watcher/dispatcher only ever claims 'pending' rows (claim_entry's
            # own WHERE clause) — simulate a poll and assert zero dispatches.
            claimed = claim_entry(entries[0].id)
            assert claimed is False
            assert list_entries(DEFAULT_DB_PATH, root=project)[0].status == "awaiting_approval"
        finally:
            bridge.close()

    def test_exact_retry_returns_original_row_without_reenqueue(
        self, project: Path, short_tmp_path: Path
    ) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            request_id = str(uuid.uuid4())
            body = _submit_payload(workspace_id=workspace_id, request_id=request_id)
            status1, resp1 = _lb_http_request(
                _port(bridge), "POST", f"/{bridge._token}/run-request", body=body
            )
            status2, resp2 = _lb_http_request(
                _port(bridge), "POST", f"/{bridge._token}/run-request", body=body
            )
            assert status1 == status2 == 200
            parsed1, parsed2 = json.loads(resp1), json.loads(resp2)
            assert parsed1["queueId"] == parsed2["queueId"]
            assert parsed1["created"] is True
            assert parsed2["created"] is False
            assert len(list_entries(DEFAULT_DB_PATH, root=project)) == 1
        finally:
            bridge.close()

    def test_conflicting_payload_same_request_id_returns_409(
        self, project: Path, short_tmp_path: Path
    ) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            request_id = str(uuid.uuid4())
            first = _submit_payload(workspace_id=workspace_id, request_id=request_id)
            status1, _ = _lb_http_request(
                _port(bridge), "POST", f"/{bridge._token}/run-request", body=first
            )
            assert status1 == 200

            other_yaml = GOLDEN_LIFECYCLE_YAML.replace(b"sample-issue-lifecycle", b"other-name")
            second = _submit_payload(
                workspace_id=workspace_id, request_id=request_id, yaml_bytes=other_yaml
            )
            status2, resp2 = _lb_http_request(
                _port(bridge), "POST", f"/{bridge._token}/run-request", body=second
            )
            assert status2 == 409
            assert json.loads(resp2)["error"]["code"] == "request_conflict"
        finally:
            bridge.close()

    def test_revision_hash_mismatch_returns_422(self, project: Path, short_tmp_path: Path) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            body = _submit_payload(workspace_id=workspace_id, revision_id="a" * 64)
            status, resp = _lb_http_request(
                _port(bridge), "POST", f"/{bridge._token}/run-request", body=body
            )
            assert status == 422
            assert json.loads(resp)["error"]["code"] == "revision_mismatch"
            assert list_entries(DEFAULT_DB_PATH, root=project) == []
        finally:
            bridge.close()

    def test_missing_issue_returns_404(self, project: Path, short_tmp_path: Path) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            body = _submit_payload(workspace_id=workspace_id, issue_id="FEAT-999")
            status, resp = _lb_http_request(
                _port(bridge), "POST", f"/{bridge._token}/run-request", body=body
            )
            assert status == 404
            assert json.loads(resp)["error"]["code"] == "issue_not_found"
            assert list_entries(DEFAULT_DB_PATH, root=project) == []
        finally:
            bridge.close()

    def test_wrong_workspace_returns_403(self, project: Path, short_tmp_path: Path) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            body = _submit_payload(workspace_id="f" * 16)
            status, resp = _lb_http_request(
                _port(bridge), "POST", f"/{bridge._token}/run-request", body=body
            )
            assert status == 403
            assert json.loads(resp)["error"]["code"] == "wrong_workspace"
        finally:
            bridge.close()

    def test_unsupported_mode_yaml_returns_422_validation_failed(
        self, project: Path, short_tmp_path: Path
    ) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            no_category_yaml = re.sub(
                rb"^category: issue_lifecycle\n", b"", GOLDEN_LIFECYCLE_YAML, flags=re.MULTILINE
            )
            assert no_category_yaml != GOLDEN_LIFECYCLE_YAML
            body = _submit_payload(workspace_id=workspace_id, yaml_bytes=no_category_yaml)
            status, resp = _lb_http_request(
                _port(bridge), "POST", f"/{bridge._token}/run-request", body=body
            )
            assert status == 422
            parsed = json.loads(resp)
            assert parsed["error"]["code"] == "validation_failed"
            assert parsed["error"]["errors"]
            assert list_entries(DEFAULT_DB_PATH, root=project) == []
        finally:
            bridge.close()

    def test_oversized_body_returns_413(
        self, project: Path, short_tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exercises the size guard without pushing a real >1MiB payload over
        the socket (which races the server's early-413/no-read-back against
        the client's blocking `sendall`, per the module's own body-guard
        note); the module constant is lowered instead so a small body trips it."""
        import little_loops.cli.artifact.policy_builder_routes as routes_mod

        monkeypatch.setattr(routes_mod, "_MAX_RUN_REQUEST_BYTES", 64)

        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            body = _submit_payload(workspace_id=workspace_id)
            assert len(body) > 64
            status, resp = _lb_http_request(
                _port(bridge), "POST", f"/{bridge._token}/run-request", body=body
            )
            assert status == 413
            assert json.loads(resp)["error"]["code"] == "body_too_large"
        finally:
            bridge.close()

    def test_malformed_json_returns_400(self, project: Path, short_tmp_path: Path) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            status, resp = _lb_http_request(
                _port(bridge), "POST", f"/{bridge._token}/run-request", body=b"{not json"
            )
            assert status == 400
            assert json.loads(resp)["error"]["code"] == "bad_request"
        finally:
            bridge.close()

    def test_lone_surrogate_yaml_returns_400(self, project: Path, short_tmp_path: Path) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            payload = json.loads(_submit_payload(workspace_id=workspace_id))
            payload["yaml"] = "a\ud800"
            body = json.dumps(payload).encode("utf-8")
            status, resp = _lb_http_request(
                _port(bridge), "POST", f"/{bridge._token}/run-request", body=body
            )
            assert status == 400
            error = json.loads(resp)["error"]
            assert error["code"] == "bad_request"
            assert error["message"] == "missing or malformed field: yaml"
            assert list_entries(DEFAULT_DB_PATH, root=project) == []
        finally:
            bridge.close()

    def test_non_json_content_type_returns_400(self, project: Path, short_tmp_path: Path) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            body = _submit_payload(workspace_id=workspace_id)
            conn = http.client.HTTPConnection("127.0.0.1", _port(bridge), timeout=5.0)
            try:
                conn.putrequest("POST", f"/{bridge._token}/run-request", skip_host=True)
                conn.putheader("Host", f"127.0.0.1:{_port(bridge)}")
                conn.putheader("Content-Type", "text/plain")
                conn.putheader("Content-Length", str(len(body)))
                conn.endheaders(body)
                resp = conn.getresponse()
                data = resp.read()
                assert resp.status == 400
                assert json.loads(data)["error"]["code"] == "bad_request"
            finally:
                conn.close()
        finally:
            bridge.close()


class TestReadbackRoute:
    def test_unknown_request_returns_404(self, project: Path, short_tmp_path: Path) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            fake_id = str(uuid.uuid4())
            status, resp = _lb_http_request(
                _port(bridge),
                "GET",
                f"/{bridge._token}/run-request/{fake_id}?workspaceId={workspace_id}",
            )
            assert status == 404
            assert json.loads(resp)["error"]["code"] == "request_not_found"
        finally:
            bridge.close()

    def test_readback_reflects_status_and_is_no_store(
        self, project: Path, short_tmp_path: Path
    ) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            request_id = str(uuid.uuid4())
            body = _submit_payload(workspace_id=workspace_id, request_id=request_id)
            _lb_http_request(_port(bridge), "POST", f"/{bridge._token}/run-request", body=body)

            conn = http.client.HTTPConnection("127.0.0.1", _port(bridge), timeout=5.0)
            try:
                path = f"/{bridge._token}/run-request/{request_id}?workspaceId={workspace_id}"
                conn.putrequest("GET", path, skip_host=True)
                conn.putheader("Host", f"127.0.0.1:{_port(bridge)}")
                conn.endheaders()
                resp = conn.getresponse()
                payload = json.loads(resp.read())
                assert resp.status == 200
                assert resp.getheader("Cache-Control") == "no-store"
                assert payload["status"] == "awaiting_approval"
                assert payload["bindings"]["issueId"] == "FEAT-1"
            finally:
                conn.close()
        finally:
            bridge.close()

    def test_host_rejection_via_cancel_surfaces_as_cancelled(
        self, project: Path, short_tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(project)
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            request_id = str(uuid.uuid4())
            body = _submit_payload(workspace_id=workspace_id, request_id=request_id)
            _, resp = _lb_http_request(
                _port(bridge), "POST", f"/{bridge._token}/run-request", body=body
            )
            queue_id = json.loads(resp)["queueId"]
            assert cancel_entry(queue_id, "rejected by host") is True

            status, readback = _lb_http_request(
                _port(bridge),
                "GET",
                f"/{bridge._token}/run-request/{request_id}?workspaceId={workspace_id}",
            )
            assert status == 200
            assert json.loads(readback)["status"] == "cancelled"
        finally:
            bridge.close()

    def test_wrong_workspace_returns_403(self, project: Path, short_tmp_path: Path) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            fake_id = str(uuid.uuid4())
            status, resp = _lb_http_request(
                _port(bridge),
                "GET",
                f"/{bridge._token}/run-request/{fake_id}?workspaceId=" + "f" * 16,
            )
            assert status == 403
            assert json.loads(resp)["error"]["code"] == "wrong_workspace"
        finally:
            bridge.close()


class TestIssuesRoute:
    def test_lists_active_issues(self, project: Path, short_tmp_path: Path) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge = _bridge_for(config, workspace_id, base=short_tmp_path, loops_dir=project / "loops")
        try:
            status, resp = _lb_http_request(_port(bridge), "GET", f"/{bridge._token}/issues")
            assert status == 200
            issues = json.loads(resp)["issues"]
            assert any(row["id"] == "FEAT-1" for row in issues)
        finally:
            bridge.close()


class TestCmdServeFlag:
    def test_flag_absent_by_default_passes_no_method_routes(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import argparse
        from unittest import mock

        from little_loops.cli.artifact.serve import cmd_serve
        from little_loops.logger import Logger

        _make_config(project)
        monkeypatch.setattr("pathlib.Path.cwd", lambda: project)
        with mock.patch("little_loops.transport.serve_sse_bridge", return_value=0) as spy:
            code = cmd_serve(
                argparse.Namespace(port=None, policy_builder=False), Logger(use_color=False)
            )
        assert code == 0
        assert spy.call_args.kwargs["method_routes"] is None
        assert spy.call_args.kwargs["extra_url_suffixes"] is None

    def test_flag_enabled_passes_four_method_routes_and_suffix(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import argparse
        from unittest import mock

        from little_loops.cli.artifact.serve import cmd_serve
        from little_loops.logger import Logger

        _make_config(project)
        monkeypatch.setattr("pathlib.Path.cwd", lambda: project)
        with mock.patch("little_loops.transport.serve_sse_bridge", return_value=0) as spy:
            code = cmd_serve(
                argparse.Namespace(port=None, policy_builder=True), Logger(use_color=False)
            )
        assert code == 0
        method_routes = spy.call_args.kwargs["method_routes"]
        assert method_routes is not None
        assert len(method_routes) == 4
        assert any(m == "GET" and p == "policy-builder" for m, p, _ in method_routes)
        assert spy.call_args.kwargs["extra_url_suffixes"] == ["policy-builder"]


class TestRestart:
    def test_workspace_id_is_stable_across_restart_old_token_stops_working(
        self, project: Path, short_tmp_path: Path
    ) -> None:
        config = _make_config(project)
        workspace_id = derive_workspace_id(project.resolve())
        bridge1 = _bridge_for(
            config, workspace_id, base=short_tmp_path, loops_dir=project / "loops"
        )
        request_id = str(uuid.uuid4())
        old_token = bridge1._token
        old_port = _port(bridge1)
        try:
            body = _submit_payload(workspace_id=workspace_id, request_id=request_id)
            status, _ = _lb_http_request(old_port, "POST", f"/{old_token}/run-request", body=body)
            assert status == 200
        finally:
            bridge1.close()

        bridge2 = _bridge_for(
            config, workspace_id, base=short_tmp_path, loops_dir=project / "loops"
        )
        try:
            assert bridge2._token != old_token
            status, resp = _lb_http_request(
                _port(bridge2),
                "GET",
                f"/{bridge2._token}/run-request/{request_id}?workspaceId={workspace_id}",
            )
            assert status == 200
            assert json.loads(resp)["requestId"] == request_id

            # The old token path is gone — the HTML transport error (404), not
            # this application's JSON ErrorBody.
            status_old, _ = _lb_http_request(
                _port(bridge2),
                "GET",
                f"/{old_token}/run-request/{request_id}?workspaceId={workspace_id}",
            )
            assert status_old == 404
        finally:
            bridge2.close()
