"""ENH-3650: every hook/plugin path that opens history.db reaches ``_resolve_once``.

The hooks build a literal ``<root>/.ll/history.db`` (some wrapped in
``resolve_history_db``) and hand it to the writers, which open it through the
target-aware ``schema.connect``/``ensure_db`` seam. That seam resolves via
``backend._resolve_once``, so a later ``RemoteTarget`` is intercepted in one place
instead of at each hook. This test spies on ``_resolve_once`` and drives each path.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

import little_loops.session_store.backend as backend_mod
from little_loops.hooks.types import LLHookEvent


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".ll").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LL_HISTORY_DB", raising=False)
    monkeypatch.delenv("LL_AUTOMATION", raising=False)
    return tmp_path


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []
    real = backend_mod._resolve_once

    def _spy(target, *args, **kwargs):
        calls.append(target)
        return real(target, *args, **kwargs)

    monkeypatch.setattr(backend_mod, "_resolve_once", _spy)
    return calls


def _event(intent: str, payload: dict | None = None) -> LLHookEvent:
    return LLHookEvent(
        host="claude-code",
        intent=intent,
        payload=payload or {},
        cwd=str(Path.cwd()),
        session_id="sess-1",
    )


def _subagent_start(root: Path) -> None:
    from little_loops.hooks import subagent_start

    subagent_start.handle(_event("subagent-start", {"agent_id": "a1", "agent_type": "x"}))


def _subagent_stop(root: Path) -> None:
    from little_loops.hooks import subagent_stop

    subagent_stop.handle(_event("subagent-stop", {"agent_id": "a1", "agent_type": "x"}))


def _pre_compact(root: Path) -> None:
    from little_loops.hooks import pre_compact

    pre_compact._record_compaction("2026-01-01T00:00:00Z", "sess-1", root)


def _sweep_stale_refs(root: Path) -> None:
    from little_loops.hooks import sweep_stale_refs

    sweep_stale_refs._record_sweep(root, "sess-1", findings=0, fix_mode="report")


def _main_hooks(root: Path) -> None:
    from little_loops.session_store import hook_event_context

    with hook_event_context(
        root / ".ll" / "history.db", session_id="s", event_name="e", script="t"
    ):
        pass


def _user_prompt_submit(root: Path) -> None:
    from little_loops.session_store import record_prompt_opt_event

    record_prompt_opt_event(
        root / ".ll" / "history.db", session_id="s", offered=True, mode="quick", raw_len=1
    )


def _post_tool_use(root: Path) -> None:
    from little_loops.session_store import connect

    connect(root / ".ll" / "history.db").close()


def _session_start(root: Path) -> None:
    from little_loops.session_store import ensure_db, resolve_history_db

    ensure_db(resolve_history_db(root / ".ll" / "history.db"))


def _post_commit(root: Path) -> None:
    from little_loops.session_store import ensure_db, resolve_history_db

    ensure_db(resolve_history_db())


_PATHS: dict[str, Callable[[Path], None]] = {
    "main_hooks": _main_hooks,
    "post_tool_use": _post_tool_use,
    "user_prompt_submit": _user_prompt_submit,
    "pre_compact": _pre_compact,
    "subagent_start": _subagent_start,
    "subagent_stop": _subagent_stop,
    "sweep_stale_refs": _sweep_stale_refs,
    "session_start": _session_start,
    "post_commit": _post_commit,
}


@pytest.mark.parametrize("name", sorted(_PATHS))
def test_hook_path_reaches_resolve_once(name: str, project: Path, spy: list[object]) -> None:
    _PATHS[name](project)
    assert spy, f"{name} opened history.db without going through _resolve_once"
