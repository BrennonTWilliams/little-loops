"""``assess_capture_scope``: gates, evidence-only ranking and CLI collection (FEAT-3713 step 2)."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import little_loops.next_arena.scan_activity as scan_activity
import little_loops.next_arena.state as state_module
from little_loops.cli import main_next
from little_loops.config import NextConfig
from little_loops.next_arena import render
from little_loops.next_arena.actions import (
    SCAN_COMMAND,
    action_fingerprint,
    parse_slash,
    scan_scope_hash,
)
from little_loops.next_arena.candidates import (
    assess_candidates,
    assessments_for_target,
    candidates_from_assessments,
)
from little_loops.next_arena.scan_activity import ScanActivity
from little_loops.next_arena.scan_candidates import FRESHNESS_LABEL, assess_capture_scope
from little_loops.next_arena.scan_state import resolve_scan_scope
from tests.next_arena_candidates_support import ready_issue
from tests.next_arena_support import AS_OF, make_project, memory_state, schema_errors, write_issue
from tests.scan_support import FakePopen, FakeProc, head_proc, record, sha, stream

SETTINGS = NextConfig().resolve_arena_settings()
IN_WINDOW = 1_790_000_000


def activity(**overrides: Any) -> ScanActivity:
    fields: dict[str, Any] = {
        "available": True,
        "unavailable_reason": None,
        "detail": None,
        "head": "a" * 40,
        "shallow": False,
        "threshold": 20,
        "lookback_days": 30,
        "window_start": "2026-09-07T12:00:00Z",
        "window_end": "2026-10-07T12:00:00Z",
        "scoped_commit_count": None,
        "lower_bound": 20,
        "saturated": True,
        "complete": False,
        "truncation_reason": "saturated",
        "records_visited": 20,
        "bytes_consumed": 100,
        "git_calls": 2,
    }
    fields.update(overrides)
    return ScanActivity(**fields)


def state_with(tmp_path: Path, scope: Any, act: ScanActivity | None) -> Any:
    root = tmp_path / "proj"
    root.mkdir(exist_ok=True)
    base = memory_state(root, {})
    return replace(base, scan_scope=scope, scan_activity=act)


@pytest.fixture
def scope(tmp_path: Path) -> Any:
    (tmp_path / "src").mkdir(exist_ok=True)
    return resolve_scan_scope(["src"], ["**/vendor/**"], tmp_path)


# ------------------------------------------------------------------------------- gates


def test_uncollected_domain_yields_no_assessment(tmp_path: Path) -> None:
    state = state_with(tmp_path, None, None)
    assert assess_capture_scope(state, settings=SETTINGS) is None
    assert [
        a for a in assess_candidates(state, settings=SETTINGS) if a.action_type == "capture-issues"
    ] == []


def test_saturated_activity_is_an_evidence_only_eligible_offer(tmp_path: Path, scope: Any) -> None:
    state = state_with(tmp_path, scope, activity())
    item = assess_capture_scope(state, settings=SETTINGS)
    assert item is not None and item.eligible and item.fully_resolved
    assert item.bucket_rank is None  # ranking happens in assess_candidates
    assert item.action_key == "scan-codebase" and item.display_command == SCAN_COMMAND
    assert item.target == "project" and item.target_key == f"scan:{scope.scope_hash}"
    assert item.target_key == f"scan:{scan_scope_hash(('src',), ('**/vendor/**',))}"
    assert dict(item.axes) == {} and item.coverage == "0/0"
    assert item.utility is None and item.selection_score is None
    assert item.gates["scope"].status == "pass" and item.gates["activity"].status == "pass"
    assert item.gates["activity"].code == "activity_threshold_met"
    assert action_fingerprint(item.action_spec) == item.action_fingerprint
    scan = item.evidence["scan"]
    assert scan["freshness"] == FRESHNESS_LABEL == "scan-freshness-unknown"
    assert scan["focus_dirs"] == ["src"] and scan["exclude_patterns"] == ["**/vendor/**"]
    assert "takes no scope argument" in scan["command_note"]
    assert item.evidence["scoring"] == {"mode": "evidence_only", "minimum_evidence": None}


def test_ranked_scan_names_the_evidence_only_mode_and_passed_gate(
    tmp_path: Path, scope: Any
) -> None:
    state = state_with(tmp_path, scope, activity())
    (ranked,) = [a for a in assess_candidates(state, settings=SETTINGS) if a.eligible]
    assert ranked.fully_resolved and ranked.bucket_rank == 1
    assert "evidence-only" in ranked.selection_reason
    assert "activity gate passed" in ranked.selection_reason
    assert "cold start" not in ranked.selection_reason
    assert ranked.utility is None and ranked.selection_score is None
    (cand,) = candidates_from_assessments([ranked])
    assert cand.coverage == "0/0"


def test_scored_verbs_keep_their_cold_start_wording(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    state = memory_state(root, {"bugs/P2-BUG-001-a.md": ready_issue()})
    ranked = [a for a in assess_candidates(state, settings=SETTINGS) if a.eligible]
    assert ranked and all("evidence-only" not in a.selection_reason for a in ranked)


@pytest.mark.parametrize(
    ("overrides", "status", "code"),
    [
        (
            {
                "saturated": False,
                "complete": True,
                "scoped_commit_count": 3,
                "lower_bound": None,
                "truncation_reason": None,
            },
            "fail",
            "activity_below_threshold",
        ),
        (
            {
                "saturated": False,
                "complete": True,
                "shallow": True,
                "scoped_commit_count": 3,
                "lower_bound": None,
                "truncation_reason": None,
            },
            "missing",
            "partial_shallow_history",
        ),
        (
            {"saturated": False, "lower_bound": 4, "truncation_reason": "record_cap"},
            "missing",
            "activity_partial",
        ),
        (
            {"saturated": False, "lower_bound": 4, "truncation_reason": "deadline"},
            "missing",
            "activity_partial",
        ),
        (
            {
                "available": False,
                "unavailable_reason": "git_failed",
                "detail": "boom",
                "saturated": False,
                "lower_bound": None,
                "truncation_reason": None,
            },
            "missing",
            "git_failed",
        ),
        (
            {
                "available": False,
                "unavailable_reason": "git_unsupported",
                "detail": "exit 129",
                "saturated": False,
                "lower_bound": None,
                "truncation_reason": None,
            },
            "missing",
            "git_unsupported",
        ),
    ],
)
def test_activity_gate_outcomes_are_distinct(
    tmp_path: Path, scope: Any, overrides: dict[str, Any], status: str, code: str
) -> None:
    item = assess_capture_scope(
        state_with(tmp_path, scope, activity(**overrides)), settings=SETTINGS
    )
    assert item is not None and not item.eligible
    gate = item.gates["activity"]
    assert (gate.status, gate.code) == (status, code)
    assert item.exclusion_reasons == (code,)
    assert item.action_spec is None and item.display_command is None


def test_unsupported_git_gate_names_the_option_and_minimum(tmp_path: Path, scope: Any) -> None:
    item = assess_capture_scope(
        state_with(
            tmp_path,
            scope,
            activity(
                available=False,
                unavailable_reason="git_unsupported",
                detail="usage error",
                saturated=False,
                lower_bound=None,
                truncation_reason=None,
            ),
        ),
        settings=SETTINGS,
    )
    assert item is not None
    reason = item.gates["activity"].reason
    assert "--no-lazy-fetch" in reason and "2.45.0" in reason


def test_partial_and_exact_evidence_render_distinctly(tmp_path: Path, scope: Any) -> None:
    exact = assess_capture_scope(
        state_with(
            tmp_path,
            scope,
            activity(
                saturated=False,
                complete=True,
                scoped_commit_count=3,
                lower_bound=None,
                truncation_reason=None,
            ),
        ),
        settings=SETTINGS,
    )
    partial = assess_capture_scope(
        state_with(
            tmp_path,
            scope,
            activity(saturated=False, lower_bound=3, truncation_reason="byte_cap"),
        ),
        settings=SETTINGS,
    )
    assert exact is not None and partial is not None
    assert "3 scoped commit(s) in" in exact.gates["activity"].reason
    assert "lower bound, not an exact value" in partial.gates["activity"].reason
    assert exact.evidence["scan"]["activity"]["scoped_commit_count"] == 3
    assert partial.evidence["scan"]["activity"]["scoped_commit_count"] is None


@pytest.mark.parametrize(
    ("focus", "code"),
    [([], "scope_empty"), (["nope"], "scope_no_existing_directory"), (["../x"], "scope_invalid")],
)
def test_unusable_scope_retains_a_failing_assessment_without_activity(
    tmp_path: Path, focus: list[str], code: str
) -> None:
    scope = resolve_scan_scope(focus, [], tmp_path)
    state = state_with(tmp_path, scope, None)
    item = assess_capture_scope(state, settings=SETTINGS)
    assert item is not None and not item.eligible
    assert item.gates["scope"].code == code and "activity" not in item.gates
    assert item.exclusion_reasons == (code,)
    # still explainable: an existing target is not an absent explain target
    named, _ = assessments_for_target(
        assess_candidates(state, settings=SETTINGS), item.target_key, "capture-issues"
    )
    assert named is not None


def test_symlink_scope_is_excluded_not_a_false_zero(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "alias").symlink_to("src", target_is_directory=True)
    scope = resolve_scan_scope(["alias"], [], tmp_path)
    item = assess_capture_scope(state_with(tmp_path, scope, None), settings=SETTINGS)
    assert item is not None and not item.eligible
    assert item.exclusion_reasons == ("symlink_scope_unsupported",)
    assert item.action_spec is None


def test_scope_change_changes_target_and_fingerprint_but_not_ordering(
    tmp_path: Path, scope: Any
) -> None:
    (tmp_path / "lib").mkdir()
    a = assess_capture_scope(state_with(tmp_path, scope, activity()), settings=SETTINGS)
    wider = resolve_scan_scope(["lib", "src"], ["**/vendor/**"], tmp_path)
    b = assess_capture_scope(state_with(tmp_path, wider, activity()), settings=SETTINGS)
    reordered = resolve_scan_scope(["src", "lib"], ["**/vendor/**"], tmp_path)
    c = assess_capture_scope(state_with(tmp_path, reordered, activity()), settings=SETTINGS)
    assert a is not None and b is not None and c is not None
    assert a.target_key != b.target_key and a.action_fingerprint != b.action_fingerprint
    assert (b.target_key, b.action_fingerprint) == (c.target_key, c.action_fingerprint)


def test_generation_is_pure_and_deterministic(tmp_path: Path, scope: Any) -> None:
    state = state_with(tmp_path, scope, activity())
    first = [a.to_dict() for a in assess_candidates(state, settings=SETTINGS)]
    second = [a.to_dict() for a in assess_candidates(state, settings=SETTINGS)]
    assert first == second
    assert json.dumps(first, allow_nan=False)


# --------------------------------------------------------------------------- the CLI


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(state_module, "_normalize_as_of", lambda _as_of: AS_OF)


Run = Callable[..., tuple[int, str, str]]


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
    (root / "src").mkdir()
    write_issue(root, "features/P2-FEAT-001-impl.md", text=ready_issue())
    monkeypatch.chdir(root)
    return root.resolve()


class GitSpy:
    """Replaces the loader's popen, counting git subprocess launches across CLI runs."""

    def __init__(self, factory: Callable[[], list[FakeProc]]) -> None:
        self.factory = factory
        self.argvs: list[list[str]] = []

    @property
    def calls(self) -> int:
        return len(self.argvs)


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Callable[..., GitSpy]:
    def install(factory: Callable[[], list[FakeProc]] | None = None) -> GitSpy:
        watcher = GitSpy(factory or (lambda: []))
        real = scan_activity.load_scope_activity

        def patched(*args: Any, **kwargs: Any) -> ScanActivity:
            popen = FakePopen(*watcher.factory())
            try:
                return real(*args, **{**kwargs, "popen": popen})
            finally:
                watcher.argvs.extend(c["argv"] for c in popen.calls)

        monkeypatch.setattr(scan_activity, "load_scope_activity", patched)
        return watcher

    return install


def _fresh(stamp: int, n: int) -> FakeProc:
    return FakeProc(stream(*(record(sha(i), stamp, ["src/a.py"]) for i in range(n))))


def test_capture_recommendation_end_to_end(
    proj: Path, run: Run, spy: Callable[..., GitSpy], monkeypatch: pytest.MonkeyPatch
) -> None:
    # make the fixed AS_OF window contain the synthetic commit time
    stamp = int(AS_OF.timestamp()) - 3600
    git = spy(lambda: [head_proc(), _fresh(stamp, 25)])
    code, out, err = run("--json", "--no-record", "--type", "capture-issues")
    assert (code, err) == (0, "")
    envelope = json.loads(out)
    schema = render.load_output_schema()
    assert schema_errors(envelope, schema, schema) == []
    (rec,) = envelope["recommendations"]
    assert rec["action_type"] == "capture-issues" and rec["action_key"] == "scan-codebase"
    assert rec["display_command"] == "/ll:scan-codebase" == SCAN_COMMAND
    assert rec["action_spec"]["variant"] == "scan"
    assert rec["action_spec"]["working_directory"] == str(proj)
    assert rec["action_spec"]["focus_dirs"] == ["src"]
    assert rec["target"] == "project" and rec["target_key"].startswith("scan:")
    assert rec["utility"] is None and rec["selection_score"] is None
    assert (rec["resolved_axes"], rec["applicable_axes"], rec["coverage"]) == (0, 0, "0/0")
    assert rec["axes"] == {} and "evidence-only" in rec["selection_reason"]
    assert rec["evidence"]["scan"]["freshness"] == "scan-freshness-unknown"
    assert git.calls == 2
    code, text, _ = run("--no-record", "--type", "capture-issues")
    assert code == 0 and "/ll:scan-codebase" in text
    parse_slash(next(line.strip() for line in text.splitlines() if line.strip().startswith("/ll:")))


def test_explain_resolves_the_current_scope_even_when_the_gate_fails(
    proj: Path, run: Run, spy: Callable[..., GitSpy]
) -> None:
    git = spy(lambda: [head_proc(), FakeProc(b"")])  # a quiet history: below threshold
    code, out, err = run("--explain", "capture-issues", "project")
    assert (code, err) == (0, "")
    assert "eligible: no" in out and "activity_below_threshold" in out
    assert git.calls == 2
    code, out, _ = run("--json", "--explain", "capture-issues", "project")
    envelope = json.loads(out)
    assessment = envelope["explanation"]["assessment"]
    assert code == 0 and assessment["target"] == "project" and assessment["eligible"] is False
    assert assessment["target_key"].startswith("scan:")
    assert envelope["explanation"]["alternates"] == []  # no phantom issue assessments
    assert "FEAT-001" not in json.dumps(assessment)


def test_explain_of_a_rejected_scope_is_still_an_existing_target(
    proj: Path, run: Run, spy: Callable[..., GitSpy]
) -> None:
    (proj / "src").rmdir()
    git = spy()
    code, out, err = run("--explain", "capture-issues", "project")
    assert (code, err) == (0, "")
    assert "scope_no_existing_directory" in out
    assert git.calls == 0  # an unusable scope makes no git call
    code, out, _ = run("--explain", "capture-issues", "other")
    assert code == 1 and "no scan target 'other'" in out


def test_git_is_called_only_when_the_scan_verb_is_in_scope(
    proj: Path, run: Run, spy: Callable[..., GitSpy]
) -> None:
    git = spy()
    for argv in (
        ("--type", "implement-issue"),
        ("--type", "refine-issue", "--type", "run-loop"),
        ("--type", "resolve-blocker"),
        ("--explain", "implement-issue", "FEAT-001"),
        ("--explain", "run-sprint", "alpha"),
    ):
        run("--no-record", *argv)
    assert git.calls == 0


def test_usage_and_config_errors_precede_collection(
    proj: Path, run: Run, spy: Callable[..., GitSpy]
) -> None:
    git = spy()
    assert run("--top", "0")[0] == 2
    assert run("--type", "nope")[0] == 2
    (proj / ".ll" / "ll-config.json").write_text(
        json.dumps({"next": {"verbs": {"capture-issues": {"activity_threshold": 0}}}})
    )
    code, out, err = run("--type", "capture-issues")
    assert code == 2 and out == "" and "activity_threshold" in err
    assert git.calls == 0


def test_configured_threshold_and_lookback_are_consumed(
    proj: Path, run: Run, spy: Callable[..., GitSpy]
) -> None:
    (proj / ".ll" / "ll-config.json").write_text(
        json.dumps(
            {
                "scan": {"focus_dirs": ["src/"], "exclude_patterns": []},
                "next": {
                    "verbs": {
                        "capture-issues": {"activity_threshold": 3, "activity_lookback_days": 7}
                    }
                },
            }
        )
    )
    stamp = int(AS_OF.timestamp()) - 3600
    git = spy(lambda: [head_proc(), _fresh(stamp, 5)])
    code, out, _ = run("--json", "--no-record", "--type", "capture-issues")
    activity_json = json.loads(out)["recommendations"][0]["evidence"]["scan"]["activity"]
    assert code == 0 and activity_json["threshold"] == 3 and activity_json["lookback_days"] == 7
    assert activity_json["saturated"] is True
    since = next(a for a in git.argvs[1] if a.startswith("--since-as-filter="))
    assert since == f"--since-as-filter={int(AS_OF.timestamp()) - 7 * 86400}"


def test_non_git_project_reports_unavailable_never_a_zero(
    proj: Path, run: Run, spy: Callable[..., GitSpy]
) -> None:
    spy(lambda: [FakeProc(b"", b"fatal: not a git repository\n", 128)])
    code, out, _ = run("--explain", "capture-issues", "project")
    assert code == 0 and "not_a_git_repository" in out and "activity_below_threshold" not in out
    code, out, _ = run("--no-record", "--type", "capture-issues")
    assert code == 1 and "no eligible candidate" in out


def test_default_pass_includes_capture_issues_after_the_others(
    proj: Path, run: Run, spy: Callable[..., GitSpy]
) -> None:
    stamp = int(AS_OF.timestamp()) - 3600
    spy(lambda: [head_proc(), _fresh(stamp, 30)])
    code, out, _ = run("--json", "--no-record")
    kinds = [r["action_type"] for r in json.loads(out)["recommendations"]]
    assert code == 0 and kinds == ["implement-issue", "capture-issues"]
