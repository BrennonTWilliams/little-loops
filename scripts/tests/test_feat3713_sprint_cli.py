"""``ll-next`` run-sprint collection, demand-driven history and recording reuse (FEAT-3713)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import little_loops.next_arena.history as history_module
import little_loops.next_arena.recording as recording_module
import little_loops.next_arena.scan_activity as scan_activity
import little_loops.next_arena.sprint_state as sprint_state_module
import little_loops.next_arena.state as state_module
from little_loops.cli import main_next
from little_loops.next_arena import render
from little_loops.next_arena.history import RecentSprintInvocations
from little_loops.next_arena.recording import RecordingResult, RecordingStatus
from little_loops.next_arena.registry import registered_verbs
from little_loops.session_store.backend import LocalTarget
from tests.next_arena_candidates_support import ready_issue
from tests.next_arena_support import AS_OF, make_project, schema_errors, write_issue
from tests.sprint_support import bug, feat, write_sprint

CLI_DDL = """CREATE TABLE cli_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, binary TEXT NOT NULL,
    args TEXT NOT NULL, exit_code INTEGER, duration_ms INTEGER)"""

Run = Callable[..., tuple[int, str, str]]


@pytest.fixture(autouse=True)
def isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(state_module, "_normalize_as_of", lambda _as_of: AS_OF)
    monkeypatch.delenv("LL_HISTORY_DB", raising=False)
    monkeypatch.delenv("LL_ANALYTICS_CAPTURE", raising=False)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Run:
    def _run(*argv: str) -> tuple[int, str, str]:
        with patch("sys.argv", ["ll-next", *argv]):
            code = main_next()
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


@pytest.fixture
def proj(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = make_project(tmp_path / "proj")
    write_issue(root, feat(1), text=ready_issue())
    write_issue(root, bug(2), text=ready_issue())
    write_sprint(root, "alpha", ["FEAT-001"])
    write_sprint(root, "beta", ["BUG-002"])
    write_sprint(root, "broken", text="name: broken\nissues: 3\n")
    monkeypatch.chdir(root)
    return root.resolve()


def make_cli_store(root: Path, rows: list[tuple[Any, ...]]) -> Path:
    path = root / ".ll" / "history.db"
    conn = sqlite3.connect(path)
    conn.execute(CLI_DDL)
    conn.executemany(
        "INSERT INTO cli_events (id, ts, binary, args, exit_code, duration_ms) "
        "VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()
    return path


class Spy:
    """Counts history reads/target freezes and scripted collection calls."""

    def __init__(self) -> None:
        self.reads: list[dict[str, Any]] = []
        self.freezes = 0
        self.sprint_collections = 0


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Spy:
    spy = Spy()
    real_read = history_module.read_history_snapshot
    real_freeze = recording_module.freeze_history_target
    real_collect = sprint_state_module.collect_sprint_domain

    def read(target: Any, **kwargs: Any) -> Any:
        spy.reads.append({"target": target, **kwargs})
        return real_read(target, **kwargs)

    def freeze(root: Path) -> Any:
        spy.freezes += 1
        return real_freeze(root)

    def collect(*args: Any, **kwargs: Any) -> Any:
        spy.sprint_collections += 1
        return real_collect(*args, **kwargs)

    monkeypatch.setattr(history_module, "read_history_snapshot", read)
    monkeypatch.setattr(recording_module, "freeze_history_target", freeze)
    monkeypatch.setattr(sprint_state_module, "collect_sprint_domain", collect)
    # sprint-only/issue-only modes must make zero git calls
    monkeypatch.setattr(
        scan_activity,
        "load_scope_activity",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("git must not run")),
    )
    return spy


def envelope(run: Run, *argv: str) -> tuple[int, dict[str, Any]]:
    code, out, err = run("--json", "--no-record", *argv)
    assert err == ""
    data = json.loads(out)
    schema = render.load_output_schema()
    assert schema_errors(data, schema, schema) == []
    return code, data


# ------------------------------------------------------------------------ recommendations


def test_sprint_recommendations_end_to_end_with_real_history(
    proj: Path, run: Run, spy: Spy
) -> None:
    make_cli_store(
        proj,
        [
            (1, "2026-10-04T12:00:00Z", "ll-sprint", json.dumps(["run", "alpha"]), 0, 60_000),
            (2, "2026-10-06T12:00:00Z", "ll-sprint", json.dumps(["run", "--", "beta"]), 0, 1000),
            (
                3,
                "2026-10-06T13:00:00Z",
                "ll-sprint",
                json.dumps(["run", "beta", "--dry-run"]),
                0,
                5,
            ),
            (4, "2026-10-06T13:00:00Z", "ll-loop", json.dumps(["run", "alpha"]), 0, 5),
        ],
    )
    code, data = envelope(run, "--type", "run-sprint", "--top", "5")
    assert code == 0
    by_target = {r["target"]: r for r in data["recommendations"]}
    assert set(by_target) == {"alpha", "beta"}  # the malformed sibling is not offered
    alpha = by_target["alpha"]
    assert alpha["display_command"] == "ll-sprint run -- alpha"
    assert alpha["action_spec"]["variant"] == "sprint"
    assert alpha["action_spec"]["members"] == [{"issue_id": "FEAT-001", "status": "open"}]
    history = alpha["evidence"]["sprint"]["history"]
    assert history["witness"]["row_id"] == 1 and history["complete"] is True
    assert history["labels"] == ["name-based-definition-unknown"]
    # alpha last ran ~2.99 days ago; beta ~0.99 days: the longer-ago run scores higher
    assert (
        alpha["axes"]["since_last_run"]["score"]
        > by_target["beta"]["axes"]["since_last_run"]["score"]
    )
    assert by_target["beta"]["evidence"]["sprint"]["history"]["excluded"] == {
        "unmodeled_options": 1
    }
    # exactly one batched request holding every candidate (valid) sprint name
    assert len(spy.reads) == 1
    (request,) = spy.reads[0]["requests"]
    assert isinstance(request, RecentSprintInvocations)
    assert request.sprint_names == ("alpha", "beta") and request.project_root == proj
    assert spy.freezes == 1


def test_text_output_shows_the_copyable_option_safe_command(proj: Path, run: Run) -> None:
    code, out, err = run("--no-record", "--type", "run-sprint")
    assert (code, err) == (0, "")
    assert "ll-sprint run -- alpha" in out or "ll-sprint run -- beta" in out
    assert "[run-sprint]" in out


def test_default_pass_orders_sprint_after_loop_and_before_capture(
    proj: Path, run: Run, spy: Spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scan_activity, "load_scope_activity", lambda *a, **k: _unavailable_activity()
    )
    code, data = envelope(run)
    kinds = [r["action_type"] for r in data["recommendations"]]
    assert code == 0 and kinds[0] == "implement-issue" and kinds[-1] == "run-sprint"
    canonical = list(registered_verbs())
    assert kinds == sorted(kinds, key=canonical.index)  # one pass, canonical verb order


def _unavailable_activity() -> Any:
    from tests.test_feat3713_scan_candidates import activity

    return activity(
        available=False,
        unavailable_reason="git_failed",
        saturated=False,
        lower_bound=None,
        truncation_reason=None,
    )


# ------------------------------------------------------------ demand-driven collection


@pytest.mark.parametrize(
    "argv",
    [
        ("--type", "implement-issue"),
        ("--type", "refine-issue", "--type", "resolve-blocker"),
        ("--type", "capture-issues"),
        ("--explain", "implement-issue", "FEAT-001"),
        ("--explain", "capture-issues", "project"),
    ],
)
def test_non_sprint_modes_request_no_sprint_history_and_read_no_definitions(
    proj: Path, run: Run, spy: Spy, argv: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scan_activity, "load_scope_activity", lambda *a, **k: _unavailable_activity()
    )
    run("--no-record", *argv)
    assert spy.reads == [] and spy.freezes == 0 and spy.sprint_collections == 0


def test_no_discovered_definitions_means_no_request_and_no_target_resolution(
    proj: Path, run: Run, spy: Spy
) -> None:
    for path in (proj / ".sprints").glob("*.yaml"):
        path.unlink()
    code, out, _ = run("--no-record", "--type", "run-sprint")
    assert code == 1 and "no eligible candidate" in out
    assert spy.sprint_collections == 1  # definitions were looked for ...
    assert spy.reads == [] and spy.freezes == 0  # ... but nothing was requested or resolved


def test_only_invalid_definitions_means_no_request(proj: Path, run: Run, spy: Spy) -> None:
    for name in ("alpha", "beta"):
        (proj / ".sprints" / f"{name}.yaml").unlink()
    code, _, _ = run("--no-record", "--type", "run-sprint")
    assert code == 1 and spy.reads == [] and spy.freezes == 0


def test_help_usage_and_config_errors_precede_any_new_collection(
    proj: Path, run: Run, spy: Spy
) -> None:
    assert run("--type", "nope")[0] == 2
    assert run("--top", "0")[0] == 2
    (proj / ".ll" / "ll-config.json").write_text(
        json.dumps({"next": {"verbs": {"run-sprint": {"weights": {"ready_share": -1}}}}})
    )
    code, out, err = run("--type", "run-sprint")
    assert code == 2 and out == "" and "run-sprint.weights.ready_share" in err
    assert spy.sprint_collections == 0 and spy.reads == [] and spy.freezes == 0


def test_explain_reads_history_but_never_records(proj: Path, run: Run, spy: Spy) -> None:
    code, out, err = run("--explain", "run-sprint", "alpha")
    assert (code, err) == (0, "")
    assert "eligible: yes -> ll-sprint run -- alpha" in out
    assert len(spy.reads) == 1 and spy.freezes == 1
    broken_code, broken_out, _ = run("--explain", "run-sprint", "broken")
    assert broken_code == 0 and "excluded because: invalid_issues" in broken_out  # existing target
    code, out, _ = run("--explain", "run-sprint", "nope")
    assert code == 1 and "no sprint target 'nope' for run-sprint" in out


def test_explain_json_matches_the_envelope_schema(proj: Path, run: Run, spy: Spy) -> None:
    code, out, _ = run("--json", "--explain", "run-sprint", "alpha")
    data = json.loads(out)
    schema = render.load_output_schema()
    assert code == 0 and schema_errors(data, schema, schema) == []
    assert data["explanation"]["assessment"]["target_key"] == "sprint:alpha"
    assert data["explanation"]["alternates"] == []  # no phantom issue assessments


# --------------------------------------------------------------- history and recording


def test_no_record_still_reads_sprint_history(proj: Path, run: Run, spy: Spy) -> None:
    run("--no-record", "--type", "run-sprint")
    assert len(spy.reads) == 1


def test_freeze_failure_makes_history_unavailable_without_changing_the_exit(
    proj: Path, run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_root: Path) -> Any:
        raise OSError("cannot resolve")

    monkeypatch.setattr(recording_module, "freeze_history_target", broken)
    code, data = envelope(run, "--type", "run-sprint")
    assert code == 0
    for rec in data["recommendations"]:
        history = rec["evidence"]["sprint"]["history"]
        assert history["source_status"] == "unavailable" and history["witness"] is None
        assert rec["axes"]["since_last_run"]["missing_reason"] == "history_unavailable"


def test_missing_store_is_unavailable_never_never_run(proj: Path, run: Run) -> None:
    code, data = envelope(run, "--type", "run-sprint")
    assert code == 0
    axis = data["recommendations"][0]["axes"]["since_last_run"]
    assert axis["score"] is None and axis["missing_reason"] == "history_unavailable"


def test_recording_reuses_the_frozen_target_and_gate_still_runs_first(
    proj: Path, run: Run, spy: Spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    def fake_record(selected: Any, **kwargs: Any) -> RecordingResult:
        seen["target"] = kwargs["target"]
        seen["variants"] = [c.action_spec.variant for c in selected]
        return RecordingResult(
            RecordingStatus("recorded"),
            tuple(f"{i:08d}-0000-0000-0000-000000000000" for i in range(len(selected))),
        )

    gate_calls: list[bool] = []

    def gate(*_a: Any, **_k: Any) -> None:
        gate_calls.append(True)
        return None

    monkeypatch.setattr(recording_module, "record_shown", fake_record)
    monkeypatch.setattr(recording_module, "automatic_recording_gate", gate)
    code, out, _ = run("--json", "--type", "run-sprint")
    assert code == 0 and json.loads(out)["recording"]["status"] == "recorded"
    assert gate_calls == [True]
    assert seen["variants"] == ["sprint"]
    assert isinstance(seen["target"], LocalTarget) and seen["target"].path.is_absolute()
    assert spy.freezes == 1  # the read-path freeze is reused, not repeated


def test_disabled_recording_does_not_resolve_a_store_for_capture_only_modes(
    proj: Path, run: Run, spy: Spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scan_activity, "load_scope_activity", lambda *a, **k: _unavailable_activity()
    )
    run("--type", "capture-issues")
    assert spy.freezes == 0 and spy.reads == []


def test_original_cwd_relative_history_target_is_frozen_before_cwd_changes(
    proj: Path, run: Run, spy: Spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub = proj / "sub"
    sub.mkdir()
    monkeypatch.chdir(sub)
    monkeypatch.setenv("LL_HISTORY_DB", "rel/history.db")  # relative to the invoking cwd
    run("--no-record", "--type", "run-sprint")
    (read,) = spy.reads
    assert read["target"].path == sub / "rel" / "history.db"
    assert read["target"].path.is_absolute()


def test_configured_relative_history_path_is_project_root_relative_from_a_subdirectory(
    proj: Path, run: Run, spy: Spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    (proj / ".ll" / "ll-config.json").write_text(json.dumps({"history": {"db_path": "data/h.db"}}))
    sub = proj / "deep" / "er"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    run("--no-record", "--type", "run-sprint")
    (read,) = spy.reads
    assert read["target"].path == proj / "data" / "h.db"
