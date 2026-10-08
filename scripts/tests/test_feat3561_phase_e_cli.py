"""``ll-next`` CLI behavior: modes, exits, root resolution and read-only proof (FEAT-3561 E)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import little_loops.next_arena.state as state_module
from little_loops.cli import main_next
from little_loops.next_arena import render
from little_loops.next_arena.actions import parse_slash
from tests.next_arena_candidates_support import issue, ready_issue
from tests.next_arena_support import AS_OF, make_project, schema_errors, write_issue

ALL_VERBS = ("implement-issue", "refine-issue")


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the captured ``as_of`` so repeated CLI runs are comparable byte for byte."""
    monkeypatch.setattr(state_module, "_normalize_as_of", lambda _as_of: AS_OF)


def _populate(root: Path) -> Path:
    make_project(root)
    write_issue(root, "features/P2-FEAT-001-impl.md", text=ready_issue())
    write_issue(root, "bugs/P1-BUG-002-fix.md", text=ready_issue())
    write_issue(root, "enhancements/P3-ENH-003-refine.md", text=issue())
    write_issue(root, "bugs/P3-BUG-004-done.md", text=issue({"status": "done"}))
    write_issue(root, "epics/P3-EPIC-005-container.md", text=issue())
    write_issue(root, "bugs/P2-BUG-006-a.md", text=ready_issue())
    write_issue(root, "bugs/P3-BUG-006-b.md", text=ready_issue())
    write_issue(root, "features/P4-FEAT-0007-leading-zeros.md", text=ready_issue())
    return root


@pytest.fixture
def proj(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _populate(tmp_path / "proj")
    monkeypatch.chdir(root)
    return root.resolve()


Run = Callable[..., tuple[int, str, str]]


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Run:
    def _run(*argv: str) -> tuple[int, str, str]:
        with patch("sys.argv", ["ll-next", *argv]):
            code = main_next()
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


def _json(run: Run, *argv: str) -> tuple[int, dict[str, Any]]:
    code, out, err = run("--json", *argv)
    assert err == ""
    envelope = json.loads(out)
    schema = render.load_output_schema()
    assert schema_errors(envelope, schema, schema) == []
    return code, envelope


# ----------------------------------------------------------------------- recommendations


def test_default_is_one_pass_over_registered_verbs(proj: Path, run: Run) -> None:
    code, envelope = _json(run)
    assert code == 0
    picked = [(r["action_type"], r["target"]) for r in envelope["recommendations"]]
    assert [v for v, _ in picked] == list(ALL_VERBS)  # one slot per verb, canonical order
    assert len({t for _, t in picked}) == len(picked)  # a target at most once
    assert envelope["selection_policy"]["mode"] == "single_pass"
    assert envelope["explanation"] is None
    assert envelope["project_root"] == str(proj)
    assert all(
        r["action_spec"]["working_directory"] == str(proj) for r in envelope["recommendations"]
    )


def test_text_output_lists_recommendations_and_states_working_directory(
    proj: Path, run: Run
) -> None:
    code, out, err = run()
    assert (code, err) == (0, "")
    assert f"Project root: {proj}" in out
    assert "Run copied actions from the project root" in out
    commands = [line.strip() for line in out.splitlines() if line.strip().startswith("/ll:")]
    assert commands
    for line in commands:
        parse_slash(line)  # displayed actions follow the declared slash grammar


def test_top_uses_round_robin_with_caps(proj: Path, run: Run) -> None:
    code, envelope = _json(run, "--top", "3")
    assert code == 0
    policy = envelope["selection_policy"]
    assert policy["mode"] == "round_robin" and policy["top"] == 3
    recs = envelope["recommendations"]
    assert len(recs) == 3
    # round-robin: first round takes each verb once before any verb's second pick
    assert [r["action_type"] for r in recs[:2]] == list(ALL_VERBS)
    ranks = [r["bucket_rank"] for r in recs]
    assert all(isinstance(rank, int) and rank >= 1 for rank in ranks)
    assert len({r["target_key"] for r in recs}) == len(recs)
    per_verb = [r["action_type"] for r in recs]
    assert max(per_verb.count(v) for v in ALL_VERBS) <= policy["caps"]["implement-issue"]


def test_top_respects_configured_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    root = _populate(tmp_path / "capped")
    (root / ".ll" / "ll-config.json").write_text(
        json.dumps({"next": {"verbs": {"implement-issue": {"cap": 1}}}}), encoding="utf-8"
    )
    monkeypatch.chdir(root)
    _, envelope = _json(run, "--top", "10", "--type", "implement-issue")
    assert envelope["selection_policy"]["caps"] == {"implement-issue": 1}
    assert len(envelope["recommendations"]) == 1


@pytest.mark.parametrize("verb", ALL_VERBS)
def test_type_restricts_to_requested_buckets(proj: Path, run: Run, verb: str) -> None:
    code, envelope = _json(run, "--type", verb)
    assert code == 0
    assert {r["action_type"] for r in envelope["recommendations"]} == {verb}
    assert envelope["selection_policy"]["bucket_order"] == [verb]


def test_type_is_repeatable_and_follows_canonical_order(proj: Path, run: Run) -> None:
    _, envelope = _json(run, "--type", "refine-issue", "--type", "implement-issue")
    assert envelope["selection_policy"]["bucket_order"] == list(ALL_VERBS)


def test_empty_backlog_exits_one_with_distinct_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    root = make_project(tmp_path / "empty")
    monkeypatch.chdir(root)
    code, envelope = _json(run)
    assert code == 1 and envelope["recommendations"] == []
    # Issue buckets are empty sources; run-loop sees only built-in definitions, which a
    # history-free project does not offer (cold_start_scope gate), so its bucket is gate-failed.
    by_code = {d["code"]: d for d in envelope["diagnostics"]}
    assert set(by_code) == {"empty_source", "gate_failed"}
    assert by_code["gate_failed"]["subject"] == "run-loop"
    assert "cold_start_scope" in by_code["gate_failed"]["message"]
    code, out, _ = run()
    assert code == 1 and "no eligible candidate" in out and "[empty_source]" in out


def test_gate_failures_report_gate_diagnostics_and_exit_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    root = make_project(tmp_path / "gated")
    write_issue(root, "bugs/P2-BUG-001-unscored.md", text=issue())
    write_issue(
        root, "bugs/P2-BUG-002-low.md", text=issue({"confidence_score": 5, "outcome_confidence": 5})
    )
    monkeypatch.chdir(root)
    code, envelope = _json(run, "--type", "implement-issue")
    assert code == 1
    assert {d["code"] for d in envelope["diagnostics"]} >= {"gate_failed", "gate_missing"}


def test_refine_cap_is_a_structured_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    from tests.next_arena_candidates_support import FORMAT_ENTRY, VERIFY_ENTRY

    root = make_project(tmp_path / "capped")
    sessions = [FORMAT_ENTRY, VERIFY_ENTRY] + [
        ("/ll:refine-issue", f"2026-09-0{n}T10:00:00") for n in range(3, 9)
    ]
    write_issue(
        root,
        "bugs/P2-BUG-001-capped.md",
        text=issue({"confidence_score": 10, "outcome_confidence": 10}, sessions=sessions),
    )
    monkeypatch.chdir(root)
    code, envelope = _json(run, "--type", "refine-issue")
    assert code == 1
    assert "refine_cap_exhausted" in {d["code"] for d in envelope["diagnostics"]}


def test_numberless_and_unsupported_sources_are_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    root = _populate(tmp_path / "odd")
    write_issue(root, "bugs/notes.md", text="# scratch\n")
    monkeypatch.chdir(root)
    code, envelope = _json(run)
    assert code == 0
    unsupported = [d for d in envelope["diagnostics"] if d["code"] == "unsupported_issue_filename"]
    assert any(d["paths"] == [".issues/bugs/notes.md"] for d in unsupported)
    assert any(
        d["code"] == "ambiguous_issue_id" and d["subject"] == "BUG-006"
        for d in envelope["diagnostics"]
    )


# ----------------------------------------------------------------------------- explain


def test_explain_recommended_target(proj: Path, run: Run) -> None:
    code, envelope = _json(run, "--explain", "implement-issue", "FEAT-001")
    assert code == 0 and envelope["recommendations"] == []
    assessment = envelope["explanation"]["assessment"]
    assert assessment["eligible"] is True
    assert assessment["display_command"] == "/ll:manage-issue feature implement FEAT-001"
    assert [a["action_type"] for a in envelope["explanation"]["alternates"]] == [
        "refine-issue",
        "resolve-blocker",
    ]


@pytest.mark.parametrize(
    ("target", "reason"),
    [
        ("BUG-004", "terminal_status"),
        ("EPIC-005", "epic_container"),
        ("BUG-006", "ambiguous_issue_id"),
        ("ENH-003", "readiness_score_absent"),
    ],
)
def test_explain_excluded_targets_exit_zero_with_reasons(
    proj: Path, run: Run, target: str, reason: str
) -> None:
    code, envelope = _json(run, "--explain", "implement-issue", target)
    assert code == 0
    assessment = envelope["explanation"]["assessment"]
    assert assessment["eligible"] is False and assessment["action_spec"] is None
    assert reason in assessment["exclusion_reasons"]


def test_explain_text_mode(proj: Path, run: Run) -> None:
    code, out, err = run("--explain", "refine-issue", "ENH-003")
    assert (code, err) == (0, "")
    assert "refine-issue:" in out and "/ll:format-issue ENH-003" in out
    assert "alternate implement-issue:" in out


def test_explain_matches_full_id_exactly_as_spelled(proj: Path, run: Run) -> None:
    code, envelope = _json(run, "--explain", "implement-issue", "FEAT-0007")
    assert code == 0
    assert envelope["explanation"]["assessment"]["display_command"].endswith(" FEAT-0007")
    for alias in ("FEAT-7", "7", "feat-001", ".issues/features/P2-FEAT-001-impl.md"):
        code, envelope = _json(run, "--explain", "implement-issue", alias)
        assert code == 1 and envelope["explanation"] is None
        assert [d["code"] for d in envelope["diagnostics"]] == ["target_not_found"]


def test_explain_absent_target_text_mode(proj: Path, run: Run) -> None:
    code, out, err = run("--explain", "refine-issue", "FEAT-9999")
    assert code == 1 and err == ""
    assert "no issue target 'FEAT-9999'" in out and "[target_not_found]" in out


# ---------------------------------------------------------------------------- usage errors


@pytest.mark.parametrize(
    "argv",
    [
        ("--top", "0"),
        ("--top", "-3"),
        ("--top", "many"),
        ("--type", "run-sprints"),
        ("--type", "nope"),
        ("--explain", "refine-issue"),
        ("--explain", "run-sprints", "FEAT-001"),
        ("--explain", "refine-issue", "FEAT-001", "--top", "2"),
        ("--explain", "refine-issue", "FEAT-001", "--type", "refine-issue"),
        ("--execute",),
        ("--bogus",),
    ],
)
def test_usage_errors_exit_two_with_empty_stdout(
    proj: Path, run: Run, argv: tuple[str, ...]
) -> None:
    code, out, err = run(*argv)
    assert code == 2 and out == ""
    assert err.strip() and "Traceback" not in err
    assert len(err.strip().splitlines()) <= 3  # concise: usage line plus the error


def test_no_execute_flag_in_help(run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run("--help")
    assert code == 0 and err == ""
    assert "--execute" not in out
    for flag in ("--json", "--top", "--type", "--explain"):
        assert flag in out
    assert "implement-issue" in out and "refine-issue" in out


def test_no_project_root_exits_two_without_initializing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    monkeypatch.chdir(bare)
    code, out, err = run()
    assert code == 2 and out == ""
    assert "no little-loops project found" in err and "Traceback" not in err
    assert not (bare / ".ll").exists() and list(bare.iterdir()) == []


def test_invalid_arena_config_exits_two_with_empty_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    for name, config in {
        "negative": {"next": {"verbs": {"implement-issue": {"weights": {"priority": -1}}}}},
        "unknown-verb": {"next": {"verbs": {"mystery": {}}}},
        "all-zero": {
            "next": {
                "verbs": {
                    "refine-issue": {
                        "weights": dict.fromkeys(
                            ("priority", "readiness_gap", "leverage", "staleness", "momentum"), 0
                        )
                    }
                }
            }
        },
        "bad-cap": {"next": {"verbs": {"implement-issue": {"cap": 0}}}},
    }.items():
        root = make_project(tmp_path / name, config=config)
        write_issue(root, "bugs/P2-BUG-001-x.md", text=ready_issue())
        monkeypatch.chdir(root)
        for argv in ((), ("--json",), ("--explain", "refine-issue", "BUG-001")):
            code, out, err = run(*argv)
            assert code == 2 and out == "", name
            assert "invalid configuration" in err and "Traceback" not in err


def test_invalid_confidence_gate_threshold_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    root = make_project(
        tmp_path / "gate",
        config={"commands": {"confidence_gate": {"readiness_threshold": 150}}},
    )
    write_issue(root, "bugs/P2-BUG-001-x.md", text=ready_issue())
    monkeypatch.chdir(root)
    code, out, err = run()
    assert code == 2 and out == "" and "confidence_gate" in err


def test_unreadable_project_config_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    root = make_project(tmp_path / "broken")
    (root / ".ll" / "ll-config.json").write_text("{not json", encoding="utf-8")
    monkeypatch.chdir(root)
    code, out, err = run()
    assert code == 2 and out == "" and "Traceback" not in err


def test_legacy_loop_history_weights_do_not_break_ll_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    root = make_project(
        tmp_path / "legacy", config={"next": {"loop_history": {"weights": {"junk": "x"}}}}
    )
    write_issue(root, "bugs/P2-BUG-001-x.md", text=ready_issue())
    monkeypatch.chdir(root)
    code, _ = _json(run)
    assert code == 0


# ------------------------------------------------------------------------- root resolution


def test_root_and_subdirectory_invocations_are_identical(
    proj: Path, run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub = proj / ".issues" / "bugs"
    outputs = []
    for cwd in (proj, sub, proj / ".ll"):
        monkeypatch.chdir(cwd)
        code, out, err = run("--json", "--top", "4")
        assert (code, err) == (0, "")
        outputs.append(out)
    assert outputs[0] == outputs[1] == outputs[2]
    text_root = None
    for cwd in (proj, sub):
        monkeypatch.chdir(cwd)
        _, out, _ = run()
        text_root = text_root or out
        assert out == text_root


def test_nested_repository_does_not_inherit_outer_project_root(
    proj: Path, run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    (proj / ".git").mkdir()
    nested = proj / "vendor" / "inner"
    (nested / ".git").mkdir(parents=True)
    monkeypatch.chdir(nested)
    code, out, err = run()
    assert code == 2 and out == "" and "no little-loops project found" in err

    make_project(nested)  # a nested repository with its own project uses its own root
    write_issue(nested, "bugs/P2-BUG-001-inner.md", text=ready_issue())
    code, envelope = _json(run)
    assert code == 0 and envelope["project_root"] == str(nested.resolve())
    assert {r["target"] for r in envelope["recommendations"]} == {"BUG-001"}


# ----------------------------------------------------------------------- read-only proof


def _snapshot(root: Path) -> dict[str, tuple[Any, ...]]:
    snap: dict[str, tuple[Any, ...]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in [*dirnames, *filenames]:
            path = Path(dirpath, name)
            stat = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            snap[str(path.relative_to(root))] = (stat.st_mtime_ns, stat.st_size, digest)
    return snap


def _boom(*_a: Any, **_k: Any) -> Any:
    raise AssertionError("ll-next must not spawn subprocesses or touch telemetry")


@pytest.fixture
def forbidden(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for target in ("run", "Popen", "check_output", "check_call", "call"):
        monkeypatch.setattr(subprocess, target, _boom)
    monkeypatch.setattr(os, "system", _boom)
    import little_loops.session_store as session_store

    monkeypatch.setattr(session_store, "cli_event_context", _boom)
    import little_loops.cli.next as cli_next

    assert not hasattr(cli_next, "cli_event_context")
    yield


@pytest.mark.parametrize(
    "argv",
    [
        (),
        ("--json",),
        ("--top", "5"),
        ("--type", "refine-issue", "--json"),
        ("--explain", "implement-issue", "FEAT-001"),
        ("--explain", "implement-issue", "BUG-006", "--json"),
        ("--explain", "refine-issue", "FEAT-9999"),
        ("--top", "0"),
        ("--help",),
    ],
)
def test_all_modes_are_read_only(
    proj: Path, run: Run, forbidden: None, argv: tuple[str, ...]
) -> None:
    before = _snapshot(proj)
    run(*argv)
    assert _snapshot(proj) == before  # no new, removed, changed or re-touched file
    assert not (proj / ".ll" / "history.db").exists()
    assert not list(proj.rglob("history.db*"))


def test_error_paths_do_not_create_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Run, forbidden: None
) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    monkeypatch.chdir(bare)
    before = _snapshot(tmp_path)
    assert run()[0] == 2
    assert _snapshot(tmp_path) == before


def test_module_imports_no_history_helpers() -> None:
    import ast

    import little_loops.cli.next as cli_next

    tree = ast.parse(Path(cli_next.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
    # FEAT-3711: recording/accept/feedback read and write the existing history store, but only
    # through the next_arena seams -- never the session store, git, subprocess or the
    # incidental-telemetry ``cli_event_context``.
    forbidden_parts = ("session_store", "subprocess", "git", "cli_event_context")
    offenders = {name for name in imported if any(part in name for part in forbidden_parts)}
    assert not offenders, offenders
    history_imports = {name for name in imported if "history" in name}
    assert history_imports <= {
        "little_loops.next_arena.history",
        "read_history_snapshot",
        "freeze_history_target",
    }, history_imports
