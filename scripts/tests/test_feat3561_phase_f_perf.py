"""Structural performance checks and the opt-in scaled gate for ``ll-next`` (FEAT-3561 F).

Default suite (no wall-clock limit; file-creation volume previously beach-balled the macOS
test host and a time limit would be flaky on shared runners):

* one parse (and one read) per issue file, and zero re-reads at assessment/selection time;
* zero git/subprocess/shell calls across collect -> assess -> select -> render and the CLI;
* deterministic operation counts on injected in-memory states at ~500 vs ~5,000 issues for
  chains, shared-descendant DAGs, wide fan-out/fan-in and cycles (never a timing ratio),
  with constant-size capped reachability summaries, preserved cycle diagnostics and a
  graph analysis that is built once and cached;
* a ~200-file filesystem smoke test -- the **only** filesystem-creating performance test.

The ``perf``-marked gate assesses and selects over an in-memory 10,000-issue / ~20,000-edge
``ProjectState`` (never 10,000 files). It is skipped unless ``--run-perf`` is passed and, being
``no_parallel`` too, runs only serially::

    python -m pytest scripts/tests/test_feat3561_phase_f_perf.py --run-perf -n 0 -m perf
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import little_loops.next_arena.graph as graph_module
import little_loops.next_arena.state as state_module
from little_loops.cli import main_next
from little_loops.config import BRConfig
from little_loops.next_arena.candidates import (
    assess_candidates,
    candidates_from_assessments,
)
from little_loops.next_arena.graph import DEFAULT_LEVERAGE_CAP, LeverageIndex, OpCounter
from little_loops.next_arena.inputs import FormattingPolicy, Thresholds
from little_loops.next_arena.render import (
    bucket_diagnostics,
    build_envelope,
    collect_diagnostics,
    render_json,
    render_text,
)
from little_loops.next_arena.selection import bucket_order_for, select_candidates, selection_policy
from little_loops.next_arena.state import (
    ProjectState,
    build_project_state,
    build_source_record,
    collect_project_state,
    downstream_leverage,
)
from tests.next_arena_candidates_support import issue, ready_issue
from tests.next_arena_support import AS_OF, issue_text, make_project, memory_state, write_issue

CAP = DEFAULT_LEVERAGE_CAP
SMALL = 500
LARGE = 5000
#: 10x more nodes may cost at most ~10x the work; 12 leaves slack for log-free constants only.
MAX_GROWTH_RATIO = 12.0

# ----------------------------------------------------------------------------- fixtures


def _fid(i: int) -> str:
    return f"FEAT-{i:05d}"


def _files(
    n: int,
    prerequisites: Callable[[int], Sequence[int]],
    *,
    fm: Callable[[int], Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    """``n`` in-memory FEAT sources; issue ``i`` is ``blocked_by`` ``prerequisites(i)``."""
    files: dict[str, str] = {}
    for i in range(n):
        front: dict[str, Any] = dict(fm(i)) if fm is not None else {}
        prereqs = [_fid(p) for p in prerequisites(i)]
        if prereqs:
            front["blocked_by"] = prereqs
        files[f"features/P3-{_fid(i)}-x.md"] = issue_text(front)
    return files


def _chain(n: int) -> dict[str, str]:
    return _files(n, lambda i: [i - 1] if i else [])


def _layered(n: int) -> dict[str, str]:
    """Shared-descendant DAG: layers of width 5; each node waits on the whole previous layer."""
    width = 5
    return _files(
        n, lambda i: range(((i // width) - 1) * width, (i // width) * width) if i >= width else []
    )


def _fan_out(n: int) -> dict[str, str]:
    """One root every other issue waits on (the root has ``n - 1`` direct dependents)."""
    return _files(n, lambda i: [0] if i else [])


def _fan_in(n: int) -> dict[str, str]:
    """One sink that waits on every other issue (``n - 1`` prerequisites)."""
    return _files(n, lambda i: range(1, n) if i == 0 else [])


def _rings(n: int) -> dict[str, str]:
    """Disjoint 5-issue dependency cycles."""
    ring = 5
    return _files(n, lambda i: [(i // ring) * ring + ((i % ring) + 1) % ring])


def _giant_ring(n: int) -> dict[str, str]:
    """A single cycle through every issue (one giant SCC)."""
    return _files(n, lambda i: [(i + 1) % n])


SHAPES: dict[str, Callable[[int], dict[str, str]]] = {
    "chain": _chain,
    "shared_descendants": _layered,
    "wide_fan_out": _fan_out,
    "wide_fan_in": _fan_in,
    "disjoint_cycles": _rings,
    "giant_cycle": _giant_ring,
}


def _measure(
    root: Path, files: dict[str, str], cap: int = CAP
) -> tuple[int, ProjectState, LeverageIndex]:
    """Total graph-build + leverage-index operations for an injected state."""
    counter = OpCounter()
    state = memory_state(root, files, counter=counter)
    index = state.graph.leverage_index(cap, counter)
    return counter.operations, state, index


# --------------------------------------------------------- operation-count linearity


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_operation_count_grows_linearly_500_to_5000(shape: str, tmp_path: Path) -> None:
    build = SHAPES[shape]
    small_ops, _, _ = _measure(tmp_path, build(SMALL))
    large_ops, large_state, _ = _measure(tmp_path, build(LARGE))
    ratio = large_ops / small_ops

    assert 5.0 <= ratio <= MAX_GROWTH_RATIO, f"{shape}: {small_ops} -> {large_ops} ({ratio:.2f}x)"
    # Absolute bound: every node and edge costs at most a constant number of capped merges,
    # each touching at most cap + 1 retained IDs per summary kind.
    edges = sum(len(r.blocked_by) + len(r.blocks) + len(r.depends_on) for r in large_state.records)
    assert large_ops <= 2 * (LARGE + edges) * (CAP + 1), f"{shape}: {large_ops} ops"


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_saturated_reachability_uses_constant_size_summaries(shape: str, tmp_path: Path) -> None:
    _, state, index = _measure(tmp_path, SHAPES[shape](LARGE))
    k = CAP + 1  # cap retained IDs plus one so the source itself can be excluded
    assert index.components, "index must cover the nonterminal nodes"
    for comp in index.components:
        assert len(comp.ids) <= k
        assert len(comp.ambiguous) <= k
        assert len(comp.missing) <= k
        assert len(comp.cyclic_ids) <= k
    # Samples are bounded and never contain the source, even when it is retained internally.
    for issue_id in (_fid(0), _fid(1), _fid(LARGE // 2), _fid(LARGE - 1)):
        lev = index.query(issue_id)
        assert issue_id not in lev.sample
        assert len(lev.sample) <= CAP
        if lev.saturated:
            assert lev.count is None and lev.count_lower_bound == CAP
            assert len(lev.sample) == CAP
        else:
            assert lev.count == len(lev.sample)


def test_saturated_head_of_a_chain_and_exact_tail(tmp_path: Path) -> None:
    _, state, index = _measure(tmp_path, _chain(LARGE))
    head = downstream_leverage(state, _fid(0))
    assert head.saturated and head.count_lower_bound == CAP and len(head.sample) == CAP
    assert _fid(0) not in head.sample
    # 3 dependents remain below the last issue: exact, no saturation.
    near_tail = downstream_leverage(state, _fid(LARGE - 4))
    assert (near_tail.status, near_tail.count) == ("exact", 3)
    assert downstream_leverage(state, _fid(LARGE - 1)).count == 0


def test_queries_cost_o_cap_after_one_index_build(tmp_path: Path) -> None:
    _, state, index = _measure(tmp_path, _layered(LARGE))
    queries = OpCounter()
    for i in range(LARGE):
        index.query(_fid(i), queries)
    assert queries.operations == LARGE  # exactly one tick per query: no per-query traversal

    again = OpCounter()
    assert state.graph.leverage_index(CAP, again) is index  # cached, not rebuilt
    assert again.operations == 0


def test_graph_analysis_is_built_once_for_a_full_assessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"index": 0}
    real = graph_module.build_leverage_index

    def counting(*args: Any, **kwargs: Any) -> LeverageIndex:
        calls["index"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(graph_module, "build_leverage_index", counting)
    state = memory_state(tmp_path, _chain(300))
    assess_candidates(state)
    assess_candidates(state)  # a second full assessment reuses the cached index
    for i in range(0, 300, 7):
        downstream_leverage(state, _fid(i))
    assert calls["index"] == 1


def test_cycle_diagnostics_are_preserved_at_scale(tmp_path: Path) -> None:
    rings = LARGE // 5
    _, state, index = _measure(tmp_path, _rings(LARGE))

    assert len(state.graph.cycles) == rings and all(len(c) == 5 for c in state.graph.cycles)
    cycle_diags = [d for d in state.diagnostics if d.code == "dependency_cycle"]
    assert len(cycle_diags) == rings
    assert len(state.graph.cyclic_ids) == LARGE
    for issue_id in (_fid(0), _fid(7), _fid(LARGE - 1)):
        lev = index.query(issue_id)
        assert lev.in_cycle
        assert issue_id in lev.cycle_ids and len(lev.cycle_ids) <= CAP + 1
        assert lev.count == 4 and issue_id not in lev.sample  # ring-mates only, never itself


def test_giant_cycle_is_one_component_with_bounded_evidence(tmp_path: Path) -> None:
    _, state, index = _measure(tmp_path, _giant_ring(LARGE))
    assert len(state.graph.cycles) == 1 and len(state.graph.cycles[0]) == LARGE
    assert len(index.components) == 1
    assert len(index.components[0].ids) == CAP + 1  # one extra retained ID for self-exclusion
    lev = index.query(_fid(0))
    assert lev.saturated and lev.in_cycle and len(lev.sample) == CAP
    assert _fid(0) not in lev.sample
    assert len([d for d in state.diagnostics if d.code == "dependency_cycle"]) == 1


# ------------------------------------------------------------ filesystem smoke project


def _smoke_files() -> dict[str, str]:
    """~200 source files of mixed status/readiness/shape for the end-to-end smoke path."""
    files: dict[str, str] = {}
    kinds = (("BUG", "bugs"), ("FEAT", "features"), ("ENH", "enhancements"))
    for i in range(1, 197):
        kind, dirname = kinds[i % 3]
        name = f"P{i % 5}-{kind}-{i:04d}-item.md"
        fm: dict[str, Any] = {}
        if i % 3 != 1:
            fm.update({"confidence_score": 90, "outcome_confidence": 80})
        if i % 7 == 0:
            fm["status"] = "done"
        elif i % 11 == 0:
            fm["status"] = "blocked"
        if i % 5 == 0:
            prev = kinds[(i - 1) % 3][0]
            fm["blocked_by"] = [f"{prev}-{i - 1:04d}"]
        files[f"{dirname}/{name}"] = issue_text(fm)
    files["epics/P3-EPIC-0500-container.md"] = issue_text({})
    files["bugs/P3-BUG-0150-dup-a.md"] = issue_text({})
    files["bugs/P4-BUG-0150-dup-b.md"] = issue_text({})  # duplicate full ID -> ambiguous
    files["enhancements/notes-no-number.md"] = issue_text({})  # numberless: owns no ID
    return files


@pytest.fixture(scope="module")
def smoke_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The single filesystem-creating performance fixture (~200 files, written once)."""
    root = make_project(tmp_path_factory.mktemp("feat3561-smoke"))
    for rel, text in _smoke_files().items():
        write_issue(root, rel, text=text)
    return root.resolve()


def test_smoke_project_is_about_two_hundred_files(smoke_project: Path) -> None:
    count = len(list((smoke_project / ".issues").rglob("*.md")))
    assert 195 <= count <= 205


def test_smoke_full_collect_assess_select_path(smoke_project: Path) -> None:
    state = collect_project_state(smoke_project, as_of=AS_OF)
    assessments = assess_candidates(state)
    candidates = candidates_from_assessments(assessments)
    order = bucket_order_for(None)
    settings = state.config.next.resolve_arena_settings()
    selected = select_candidates(candidates, top=10, bucket_order=order, caps=settings.caps)

    assert len(state.records) >= 195
    targets = len(state.identity.node_paths)
    assert len(assessments) == targets * len(order)
    assert candidates and selected
    assert len({c.target_key for c in selected}) == len(selected)
    assert any(d.code == "ambiguous_issue_id" for d in state.diagnostics)
    # Ranks are dense and unique per verb among the runnable candidates.
    for verb in order:
        ranks = sorted(c.bucket_rank for c in candidates if c.action_type == verb)
        assert ranks == list(range(1, len(ranks) + 1))
    envelope = build_envelope(
        project_root=smoke_project,
        as_of=state.as_of,
        selection_policy=selection_policy(top=10, bucket_order=order, caps=settings.caps),
        recommendations=selected,
        diagnostics=collect_diagnostics(state.diagnostics, assessments, order),
    )
    assert json.loads(render_json(envelope))["recommendations"]
    assert "ll-next:" in render_text(
        project_root=smoke_project, recommendations=selected, bucket_order=order
    )


# ------------------------------------------------------------------------- parse count


@pytest.fixture
def parse_counters(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    counts = {"parse": 0, "read": 0}
    real_parse = state_module._parse_frontmatter
    real_read = state_module._read_text

    def parse(content: str) -> dict[str, Any]:
        counts["parse"] += 1
        return real_parse(content)

    def read(path: Path) -> str:
        counts["read"] += 1
        return real_read(path)

    monkeypatch.setattr(state_module, "_parse_frontmatter", parse)
    monkeypatch.setattr(state_module, "_read_text", read)
    return counts


def test_exactly_one_read_and_parse_per_issue_file(
    smoke_project: Path, parse_counters: dict[str, int]
) -> None:
    files = len(list((smoke_project / ".issues").rglob("*.md")))
    state = collect_project_state(smoke_project, as_of=AS_OF)
    assert len(state.records) == files
    assert parse_counters == {"parse": files, "read": files}


def test_no_reads_or_parses_at_assessment_selection_or_render_time(
    smoke_project: Path, parse_counters: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    state = collect_project_state(smoke_project, as_of=AS_OF)
    baseline = dict(parse_counters)
    file_reads: list[str] = []

    def no_read(self: Path, *args: Any, **kwargs: Any) -> Any:
        file_reads.append(str(self))
        raise AssertionError(f"re-read of {self}")

    for name in ("read_text", "read_bytes", "open"):
        monkeypatch.setattr(Path, name, no_read)

    order = bucket_order_for(None)
    settings = state.config.next.resolve_arena_settings()
    assessments = assess_candidates(state, settings=settings)
    selected = select_candidates(
        candidates_from_assessments(assessments), top=None, bucket_order=order, caps=settings.caps
    )
    render_text(project_root=smoke_project, recommendations=selected, bucket_order=order)
    render_json(
        build_envelope(
            project_root=smoke_project,
            as_of=state.as_of,
            selection_policy=selection_policy(top=None, bucket_order=order, caps=settings.caps),
            recommendations=selected,
            diagnostics=collect_diagnostics(state.diagnostics, assessments, order),
        )
    )

    assert file_reads == []
    assert parse_counters == baseline


def test_session_log_is_fence_scanned_once_per_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``build_source_record`` extracts the Session Log body once and derives both views."""
    import little_loops.session_log as session_log

    scans = {"n": 0}
    real = session_log.fence_spans

    def counting(content: str) -> Any:
        scans["n"] += 1
        return real(content)

    monkeypatch.setattr(session_log, "fence_spans", counting)
    text = issue(sessions=[("/ll:refine-issue", "2026-09-01T10:00:00")] * 2)
    config = BRConfig(tmp_path)
    record = build_source_record(
        tmp_path / ".issues" / "bugs" / "P2-BUG-001-x.md",
        text,
        project_root=tmp_path,
        config=config,
    )
    assert scans["n"] == 1
    assert record.session_commands == tuple(session_log.parse_session_log(text))
    assert dict(record.session_command_counts) == session_log.count_session_commands(text)
    assert record.session_command_counts == {"/ll:refine-issue": 2}


# ------------------------------------------------------------- zero git / subprocess


@pytest.fixture
def spawn_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make every process-spawning entry point record the call and raise."""
    calls: list[str] = []

    def forbid(name: str) -> Callable[..., Any]:
        def boom(*args: Any, **kwargs: Any) -> Any:
            calls.append(f"{name}{args!r}")
            raise AssertionError(f"{name} called by the ll-next core: {args!r}")

        return boom

    for name in ("run", "Popen", "check_output", "check_call", "call"):
        monkeypatch.setattr(subprocess, name, forbid(f"subprocess.{name}"))
    for name in ("system", "popen", "posix_spawn", "posix_spawnp", "fork", "execv", "execvp"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, forbid(f"os.{name}"))
    return calls


def test_core_pipeline_makes_zero_git_or_subprocess_calls(
    smoke_project: Path, spawn_calls: list[str]
) -> None:
    state = collect_project_state(smoke_project, as_of=AS_OF)
    order = bucket_order_for(None)
    settings = state.config.next.resolve_arena_settings()
    assessments = assess_candidates(state, settings=settings)
    selected = select_candidates(
        candidates_from_assessments(assessments), top=10, bucket_order=order, caps=settings.caps
    )
    render_text(project_root=smoke_project, recommendations=selected, bucket_order=order)

    assert selected
    assert spawn_calls == []


@pytest.mark.parametrize(
    "argv", [[], ["--json"], ["--top", "5", "--json"], ["--type", "refine-issue"]]
)
def test_cli_makes_zero_git_or_subprocess_calls(
    smoke_project: Path,
    spawn_calls: list[str],
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(smoke_project)
    with patch("sys.argv", ["ll-next", *argv]):
        code = main_next()
    out = capsys.readouterr().out
    assert code in (0, 1) and out
    assert spawn_calls == []


# ----------------------------------------------------- fixed-clock mixed-bucket fixture


def test_mixed_bucket_missing_gate_zero_score_and_cold_start_are_deterministic(
    tmp_path: Path,
) -> None:
    files = {
        # scored implementation candidate
        "bugs/P1-BUG-001-scored.md": ready_issue(),
        # cold start: valid scores, no priority anywhere -> insufficient evidence, fallback rank
        "bugs/BUG-002-nopriority.md": ready_issue(),
        # missing gate input: no scores at all (implement ineligible, refine applicable)
        "features/P2-FEAT-003-unscored.md": issue(),
        # zero-valued scores fail the gates but are valid (not "absent")
        "enhancements/P2-ENH-004-zero.md": issue({"confidence_score": 0, "outcome_confidence": 0}),
    }
    first = assess_candidates(memory_state(tmp_path, dict(files)))
    second = assess_candidates(memory_state(tmp_path, dict(reversed(list(files.items())))))
    assert [a.to_dict() for a in first] == [a.to_dict() for a in second]  # fixed clock, any order

    by = {(a.action_type, a.target): a for a in first}
    scored, cold = by[("implement-issue", "BUG-001")], by[("implement-issue", "BUG-002")]
    assert scored.utility is not None and scored.bucket_rank == 1
    assert cold.cold_start and cold.bucket_rank == 2 and cold.utility is None
    missing = by[("implement-issue", "FEAT-003")]
    assert not missing.eligible
    assert missing.gates["readiness"].status == "missing"
    zero = by[("implement-issue", "ENH-004")]
    assert not zero.eligible and zero.gates["readiness"].status == "fail"
    assert by[("refine-issue", "FEAT-003")].eligible  # refinement still has work to offer


def test_bucket_diagnostics_counts_gate_codes_across_many_rejected_targets(
    tmp_path: Path,
) -> None:
    """Regression: aggregating gate codes over two or more rejected targets must not raise.

    The 10k gate exposed ``Counter.update(dict.fromkeys(...))`` adding ``None`` counts as soon
    as a second actionable target in an empty bucket had a failed gate.
    """
    low = {"confidence_score": 10, "outcome_confidence": 10}
    files = {f"bugs/P2-BUG-{n:03d}-low.md": issue(low) for n in range(1, 4)}
    assessments = assess_candidates(memory_state(tmp_path, files))
    notes = bucket_diagnostics(assessments, ("implement-issue",))
    assert [d.code for d in notes] == ["gate_failed"]
    assert "3 of 3 actionable" in notes[0].message
    assert "readiness_below_threshold x3" in notes[0].message


# ------------------------------------------------------------------ scaled opt-in gate

PERF_BUDGET_SECONDS = 30.0
PERF_ISSUES = 10_000


def _perf_records(root: Path, config: BRConfig) -> tuple[list[Any], int]:
    """10,000 injected sources with ~20,000 dependency edges (fixture construction)."""
    kinds = (("BUG", "bugs"), ("FEAT", "features"), ("ENH", "enhancements"))

    def ident(i: int) -> str:
        return f"EPIC-{i:05d}" if i % 50 == 0 else f"{kinds[i % 3][0]}-{i:05d}"

    records = []
    edges = 0
    for i in range(PERF_ISSUES):
        kind, dirname = ("EPIC", "epics") if i % 50 == 0 else kinds[i % 3]
        fm: dict[str, Any] = {}
        if i % 3 == 0:
            fm.update({"confidence_score": 90, "outcome_confidence": 80})
        if i % 10 == 0:
            fm["status"] = "done"
        elif i % 17 == 0:
            fm["status"] = "blocked"
        if i >= 1:
            fm["blocked_by"] = [ident(i - 1)]
            edges += 1
        if i >= 3:
            fm["depends_on"] = [ident(i // 3)]
            edges += 1
        text = issue_text(fm)
        records.append(
            build_source_record(
                root / ".issues" / dirname / f"P{i % 5}-{kind}-{i:05d}-x.md",
                text,
                project_root=root,
                config=config,
                category=None,
            )
        )
    return records, edges


@pytest.mark.perf
@pytest.mark.no_parallel
def test_ten_thousand_issue_assess_and_select_within_budget(tmp_path: Path) -> None:
    config = BRConfig(tmp_path)
    records, edges = _perf_records(tmp_path, config)  # untimed: fixture construction
    assert len(records) == PERF_ISSUES and edges >= 19_900
    settings = config.next.resolve_arena_settings()
    order = bucket_order_for(None)

    started = time.perf_counter()
    state = build_project_state(
        records,
        project_root=tmp_path,
        as_of=AS_OF,
        config=config,
        formatting_policy=FormattingPolicy({}, {}, None),
        thresholds=Thresholds(85, 65, False),
    )
    built = time.perf_counter()
    assessments = assess_candidates(state, settings=settings)
    assessed = time.perf_counter()
    selected = select_candidates(
        candidates_from_assessments(assessments), top=10, bucket_order=order, caps=settings.caps
    )
    render_json(
        build_envelope(
            project_root=tmp_path,
            as_of=state.as_of,
            selection_policy=selection_policy(top=10, bucket_order=order, caps=settings.caps),
            recommendations=selected,
            diagnostics=collect_diagnostics(state.diagnostics, assessments, order),
        )
    )
    finished = time.perf_counter()

    total = finished - started
    print(
        f"10k gate: state {built - started:.2f}s, assess {assessed - built:.2f}s, "
        f"select+render {finished - assessed:.2f}s, total {total:.2f}s "
        f"({PERF_ISSUES} issues, {edges} edges)"
    )
    assert len(assessments) == len(state.identity.node_paths) * len(order)
    assert selected
    assert total <= PERF_BUDGET_SECONDS, f"10k-issue gate took {total:.1f}s"
