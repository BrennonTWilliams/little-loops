"""ENH-3630/ENH-3623: resume matrix for the prepare-issue dispatch loop.

For each matrix scenario, kill the process (``HarnessCrash``) at every runner call of
every wrapper action state (and of the stub inner loop), both *before* the action
runs and *after* it ran but before its result was returned, then resume through
``PersistentExecutor.resume()`` exactly as ``ll-loop resume`` does. Autodev persists
``refine_current`` while the wrapper runs, so every resume restarts the wrapper at
``select_step``; the fact log must make that restart exact:

- identical artifacts (all parity fields) to the uncrashed run;
- at most one replayed command, and exactly one only when the kill landed *after* a
  command ran (slash command or inner ``scripted_run``) and before its done fact;
- identical counters (the repair-cycle projection and the fact-derived count).

Ported from the ``spike/preparation-policy-a51621302`` tag
(``test_preparation_policy_resume.py``); the ``MATRIX`` counts were re-measured
against main's ``decide()`` (BUG-3624/ENH-3625/BUG-3620/BUG-3622 plus the Step 5
``needs_child_scan`` SIZE_REVIEW fix) and came back unchanged from the spike's --
none of those fixes touch these six scenarios' step counts.

Runtime budget (ENH-3630 § Runtime budget): the full ``POINTS`` matrix is ~230
crash+clean pairs of real in-process autodev runs (~3 s/pair measured), well past
the parity/differential file's 60 s allowance. It is opt-in
(``LL_PREP_POLICY_RESUME_FULL=1``) and stays off ``slow``'s default inclusion via an
explicit ``skipif`` (unlike the parity file, which fits under 60 s and runs by
default). ``DEFAULT_POINTS`` -- one crash point per scenario -- runs unconditionally
so the resume mechanism itself always has default coverage.
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any

import pytest

from little_loops.preparation_policy import load_facts
from tests.autodev_harness import AutodevResult, Crash, Scenario, run_autodev
from tests.test_autodev_characterization import SCENARIOS, _assert_hermetic
from tests.test_preparation_policy_parity import DIFF_SCENARIOS, _observed_parity

_ALL = {s.name: s for s, _ in SCENARIOS} | {s.name: s for s in DIFF_SCENARIOS}

#: Runner calls per action state in the uncrashed policy run (re-measured against
#: main; see the module docstring), pinned by ``test_matrix_counts_match_clean_run``.
MATRIX: dict[str, dict[str, int]] = {
    "readiness_stagnated": {
        "select_step": 5,
        "resolve_issue": 1,
        "scripted_run": 1,
        "record_step": 4,
        "run_size_review": 1,
        "run_reconcile": 1,
        "run_rescore": 1,
        "apply_outcome": 1,
    },
    "oversized_atomic_go_reopen_implement": {
        "select_step": 6,
        "resolve_issue": 1,
        "scripted_run": 1,
        "record_step": 4,
        "run_size_review": 1,
        "record_guard2": 1,
        "run_wire": 1,
        "run_rescore": 1,
        "run_go_no_go": 1,
        "apply_outcome": 1,
    },
    "design_gate_failed": {
        "select_step": 7,
        "resolve_issue": 1,
        "scripted_run": 1,
        "record_step": 6,
        "run_size_review": 1,
        "run_reconcile": 1,
        "run_rescore": 2,
        "run_refine_gap": 1,
        "apply_outcome": 1,
    },
    "decision_reentry_exhausted": {
        "select_step": 3,
        "resolve_issue": 2,
        "scripted_run": 2,
        "record_step": 2,
        "apply_outcome": 1,
    },
    "size_review_decomposition": {
        "select_step": 7,
        "resolve_issue": 3,
        "scripted_run": 3,
        "record_step": 4,
        "run_size_review": 1,
        "apply_outcome": 3,
    },
    "h1_guard2_across_epochs_go": {
        "select_step": 10,
        "resolve_issue": 2,
        "scripted_run": 2,
        "record_step": 8,
        "run_size_review": 1,
        "record_guard2": 1,
        "run_wire": 2,
        "run_refine_gap": 1,
        "run_rescore": 2,
        "run_go_no_go": 1,
        "apply_outcome": 1,
    },
}

COMMAND_STATES = {
    "scripted_run",
    "run_wire",
    "run_refine_gap",
    "run_rescore",
    "run_reconcile",
    "run_size_review",
    "run_go_no_go",
}
_ACTION_STATES = COMMAND_STATES | {
    "select_step",
    "record_step",
    "record_guard2",
    "apply_outcome",
    "resolve_issue",
}

POINTS = [
    pytest.param(name, state, occ, when, id=f"{name}-{state}#{occ}-{when}")
    for name, counts in MATRIX.items()
    for state, n in counts.items()
    for occ in range(1, n + 1)
    for when in ("before", "after")
]

#: One crash point per scenario (the first action state's first occurrence, both
#: directions covered by picking "before" here and letting the full matrix cover
#: "after" -- this subset only has to prove the resume mechanism itself works, not
#: re-run the whole matrix). Always runs, unlike the ``LL_PREP_POLICY_RESUME_FULL``
#: gated matrix below.
DEFAULT_POINTS = [
    pytest.param(name, next(iter(counts)), 1, "before", id=f"{name}-{next(iter(counts))}#1-before")
    for name, counts in MATRIX.items()
]

_FULL_MATRIX_ENV = "LL_PREP_POLICY_RESUME_FULL"
_full_matrix_gate = pytest.mark.skipif(
    os.environ.get(_FULL_MATRIX_ENV) != "1",
    reason=f"opt-in: set {_FULL_MATRIX_ENV}=1 to run the full ~230-case resume matrix",
)


def _commands(r: AutodevResult) -> int:
    """Commands actually executed: slash calls + stub inner runs."""
    return len(r.slash_commands) + len(r.inner_calls)


def _fact_counts(r: AutodevResult) -> dict[str, int]:
    out: dict[str, int] = {}
    for path in sorted((r.run_dir / "prep-facts").glob("*.jsonl")):
        iid = path.stem
        out[iid] = load_facts(r.run_dir, iid).repair_cycles()
    return out


def _clean(name: str, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> AutodevResult:
    root = tmp_path / "clean"
    root.mkdir()
    r = run_autodev(_ALL[name], root, monkeypatch)
    _assert_hermetic(r)
    return r


@pytest.mark.timeout(300)
@pytest.mark.parametrize("name", list(MATRIX))
def test_matrix_counts_match_clean_run(
    name: str, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = _clean(name, tmp_path, monkeypatch)
    seen: dict[str, int] = {}
    for p in r.full_path:
        state = p.split(":", 1)[1]
        if state in _ACTION_STATES:
            seen[state] = seen.get(state, 0) + 1
    assert seen == MATRIX[name]


def _crash_and_resume(
    name: str,
    state: str,
    occurrence: int,
    when: str,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean = _clean(name, tmp_path, monkeypatch)
    root = tmp_path / "crash"
    root.mkdir()
    # A command replays exactly when it ran but its done fact was not written: a kill
    # after the command, or before the record state that follows it.
    ran_unrecorded = (when == "after" and state in COMMAND_STATES) or (
        when == "before" and state in ("record_step", "record_guard2")
    )
    expected_replays = 1 if ran_unrecorded else 0
    crash = Crash(
        state=state,
        occurrence=occurrence,
        when=when,  # type: ignore[arg-type]
        replay_same=ran_unrecorded,
    )
    scenario: Scenario = replace(_ALL[name], crash=crash)
    r = run_autodev(scenario, root, monkeypatch)
    _assert_hermetic(r)
    assert r.crashed_at is not None and r.crashed_at["state"] == state
    assert r.resumed_terminated_by == "terminal"

    replays = _commands(r) - _commands(clean)
    assert replays == expected_replays, (replays, r.slash_commands, clean.slash_commands)

    got, want = _observed_parity(r), _observed_parity(clean)
    if expected_replays:
        # The replayed slash command shows up once more in the log; nothing else may.
        assert len(got["slash"]) - len(want["slash"]) in (0, 1)
        got = {**got, "slash": _dedupe_one(got["slash"], want["slash"])}
    assert got == want
    assert _fact_counts(r) == _fact_counts(clean)


def _dedupe_one(got: tuple[str, ...], want: tuple[str, ...]) -> tuple[str, ...]:
    """*got* with one adjacent duplicate removed when that makes it equal *want*."""
    if got == want:
        return got
    for i in range(1, len(got)):
        if got[i] == got[i - 1] and got[:i] + got[i + 1 :] == want:
            return want
    return got


@pytest.mark.timeout(60)
@pytest.mark.parametrize(("name", "state", "occurrence", "when"), DEFAULT_POINTS)
def test_crash_and_resume_is_exact_default_subset(
    name: str,
    state: str,
    occurrence: int,
    when: str,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _crash_and_resume(name, state, occurrence, when, tmp_path, monkeypatch)


@pytest.mark.slow
@_full_matrix_gate
@pytest.mark.timeout(300)
@pytest.mark.parametrize(("name", "state", "occurrence", "when"), POINTS)
def test_crash_and_resume_is_exact_full_matrix(
    name: str,
    state: str,
    occurrence: int,
    when: str,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _crash_and_resume(name, state, occurrence, when, tmp_path, monkeypatch)
