"""Tests for ReferenceInterceptorExtension — passthrough, veto, and wiring integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from little_loops import RouteContext, RouteDecision
from little_loops.events import EventBus
from little_loops.extension import ExtensionLoader, wire_extensions
from little_loops.extensions.reference_interceptor import ReferenceInterceptorExtension
from little_loops.issue_parser import IssueInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_route_context() -> RouteContext:
    """Return a minimal RouteContext for interceptor tests."""
    return RouteContext(
        state_name="build",
        state=MagicMock(),
        verdict="pass",
        action_result=None,
        eval_result=None,
        ctx={},
        iteration=1,
    )


def _make_issue_info(tmp_path: Path) -> IssueInfo:
    """Return a minimal IssueInfo backed by a real file."""
    issue_path = tmp_path / ".issues" / "features" / "P4-FEAT-999-test.md"
    issue_path.parent.mkdir(parents=True, exist_ok=True)
    issue_path.write_text("# FEAT-999: Test\n\n## Summary\nTest content.")
    return IssueInfo(
        path=issue_path,
        issue_type="features",
        priority="P4",
        issue_id="FEAT-999",
        title="Test",
    )


# ---------------------------------------------------------------------------
# Passthrough behaviour
# ---------------------------------------------------------------------------


class TestReferenceInterceptorPassthrough:
    """ReferenceInterceptorExtension returns None for both hooks (passthrough)."""

    def test_before_route_returns_none(self) -> None:
        ext = ReferenceInterceptorExtension()
        result = ext.before_route(_make_route_context())
        assert result is None

    def test_before_issue_close_returns_none(self, tmp_path: Path) -> None:
        ext = ReferenceInterceptorExtension()
        info = _make_issue_info(tmp_path)
        result = ext.before_issue_close(info)
        assert result is None

    def test_before_route_return_type_is_compatible(self) -> None:
        """Return type must be RouteDecision | None — None satisfies the protocol."""
        ext = ReferenceInterceptorExtension()
        result = ext.before_route(_make_route_context())
        assert result is None or isinstance(result, RouteDecision)

    def test_before_issue_close_return_type_is_compatible(self, tmp_path: Path) -> None:
        """Return type must be bool | None — None satisfies the protocol."""
        ext = ReferenceInterceptorExtension()
        info = _make_issue_info(tmp_path)
        result = ext.before_issue_close(info)
        assert result is None or isinstance(result, bool)


# ---------------------------------------------------------------------------
# Veto behaviour (custom subclass)
# ---------------------------------------------------------------------------


class TestInterceptorVeto:
    """Verify that returning False from before_issue_close() vetoes close_issue()."""

    def test_veto_interceptor_prevents_close(self, tmp_path: Path) -> None:
        """close_issue() returns False when an interceptor returns False."""
        from unittest.mock import MagicMock

        from little_loops.config import BRConfig
        from little_loops.issue_lifecycle import close_issue
        from little_loops.logger import Logger

        # Set up minimal config with required directories
        config_data = {
            "project": {"name": "test", "src_dir": "src/"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"}
                },
                "completed_dir": "completed",
                "deferred_dir": "deferred",
                "priorities": ["P4"],
            },
        }
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
        (ll_dir / "ll-config.json").write_text(json.dumps(config_data))
        (tmp_path / ".issues" / "completed").mkdir(parents=True, exist_ok=True)

        config = BRConfig(tmp_path)
        logger = MagicMock(spec=Logger)
        info = _make_issue_info(tmp_path)

        class VetoInterceptor:
            def before_issue_close(self, info: IssueInfo) -> bool | None:
                return False

        result = close_issue(
            info=info,
            config=config,
            logger=logger,
            close_reason="test_veto",
            close_status="Closed - Vetoed",
            interceptors=[VetoInterceptor()],
        )

        assert result is False
        # The issue file must still be in place (not moved)
        assert info.path.exists()

    def test_passthrough_interceptor_allows_close(self, tmp_path: Path) -> None:
        """close_issue() proceeds when ReferenceInterceptorExtension is in interceptors."""
        from unittest.mock import patch as upatch

        from little_loops.config import BRConfig
        from little_loops.issue_lifecycle import close_issue
        from little_loops.logger import Logger

        config_data = {
            "project": {"name": "test", "src_dir": "src/"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"}
                },
                "completed_dir": "completed",
                "deferred_dir": "deferred",
                "priorities": ["P4"],
            },
        }
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
        (ll_dir / "ll-config.json").write_text(json.dumps(config_data))
        (tmp_path / ".issues" / "completed").mkdir(parents=True, exist_ok=True)

        config = BRConfig(tmp_path)
        logger = MagicMock(spec=Logger)
        info = _make_issue_info(tmp_path)

        ext = ReferenceInterceptorExtension()

        # Patch git operations to avoid real git calls
        with (
            upatch("little_loops.issue_lifecycle._move_issue_to_completed"),
            upatch("little_loops.issue_lifecycle._commit_issue_completion"),
        ):
            result = close_issue(
                info=info,
                config=config,
                logger=logger,
                close_reason="test_pass",
                close_status="Closed - Test",
                interceptors=[ext],
            )

        assert result is True


# ---------------------------------------------------------------------------
# wire_extensions() integration
# ---------------------------------------------------------------------------


class TestReferenceInterceptorWiring:
    """ReferenceInterceptorExtension is correctly wired via wire_extensions()."""

    def test_interceptor_appended_to_executor_interceptors(self) -> None:
        """wire_extensions appends ReferenceInterceptorExtension to executor._interceptors."""
        ext = ReferenceInterceptorExtension()

        executor_obj = type(
            "Executor",
            (),
            {"_contributed_actions": {}, "_contributed_evaluators": {}, "_interceptors": []},
        )()

        bus = EventBus()
        with patch.object(ExtensionLoader, "load_all", return_value=[ext]):
            wire_extensions(bus, executor=executor_obj)

        assert len(executor_obj._interceptors) == 1
        assert executor_obj._interceptors[0] is ext

    def test_interceptor_not_registered_on_bus_without_on_event(self) -> None:
        """ReferenceInterceptorExtension has no on_event — it must not be registered on EventBus."""
        ext = ReferenceInterceptorExtension()
        assert not hasattr(ext, "on_event")

        bus = EventBus()
        executor_obj = type(
            "Executor",
            (),
            {"_contributed_actions": {}, "_contributed_evaluators": {}, "_interceptors": []},
        )()

        with patch.object(ExtensionLoader, "load_all", return_value=[ext]):
            extensions = wire_extensions(bus, executor=executor_obj)

        # Extension still returned even if not registered on bus
        assert ext in extensions
        # But interceptors list is populated
        assert ext in executor_obj._interceptors
