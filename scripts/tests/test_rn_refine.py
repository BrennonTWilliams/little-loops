"""Tests for the recursive rn-refine loop and its per-node oracle.

rn-refine treats a plan as the ROOT of a decomposition tree and refines it
recursively to adaptive depth: refine node -> decide leaf/decompose -> enqueue
children depth-first -> (queue drains) -> bottom-up synthesis -> reassemble ->
overwrite source. These tests cover the structural state graph plus the
deterministic shell plumbing (queue ops, child-id allocation, depth-first
enqueue, and the deepest-first synthesis topological order) by executing the
real action bodies rendered through the engine's interpolator.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import little_loops.rn_synth_queue as rn_synth_queue
from little_loops.fsm.interpolation import InterpolationContext, interpolate
from little_loops.fsm.validation import load_and_validate
from little_loops.rn_synth_queue import mark_complete, queue_is_empty, try_pop_ready

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

LOOPS = Path(__file__).parent.parent / "little_loops" / "loops"
RN_REFINE = LOOPS / "rn-refine.yaml"
NODE_ORACLE = LOOPS / "oracles" / "plan-node-refine.yaml"
INTEGRATE_ORACLE = LOOPS / "oracles" / "integrate-node.yaml"
QUEUE_MODULE = Path(rn_synth_queue.__file__)


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


def _render(action: str, *, context: dict | None = None, captured: dict | None = None) -> str:
    """Render a raw state action the way the runner does before execution."""
    ctx = InterpolationContext(context=context or {}, captured=captured or {})
    return interpolate(action, ctx)


def _load_rn_refine():
    fsm, _ = load_and_validate(RN_REFINE)
    return fsm


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestLoadsClean:
    def test_rn_refine_validates_without_errors(self) -> None:
        _, errors = load_and_validate(RN_REFINE)
        hard = [
            e for e in errors if str(getattr(e.severity, "value", e.severity)).lower() == "error"
        ]
        assert hard == [], f"rn-refine has validation errors: {hard}"

    def test_node_oracle_validates_without_errors(self) -> None:
        _, errors = load_and_validate(NODE_ORACLE)
        hard = [
            e for e in errors if str(getattr(e.severity, "value", e.severity)).lower() == "error"
        ]
        assert hard == [], f"plan-node-refine has validation errors: {hard}"

    def test_integrate_node_oracle_validates_without_errors(self) -> None:
        _, errors = load_and_validate(INTEGRATE_ORACLE)
        hard = [
            e for e in errors if str(getattr(e.severity, "value", e.severity)).lower() == "error"
        ]
        assert hard == [], f"integrate-node has validation errors: {hard}"


# ---------------------------------------------------------------------------
# Structural state graph (recursive work-tree shape)
# ---------------------------------------------------------------------------


class TestRecursiveStructure:
    def test_refine_node_delegates_to_node_oracle(self) -> None:
        """The per-node refinement must be delegated to the reusable oracle sub-loop."""
        fsm = _load_rn_refine()
        assert fsm.states["refine_node"].loop == "oracles/plan-node-refine"

    def test_decomposed_node_loops_back_to_dequeue(self) -> None:
        """A DECOMPOSED node enqueues children (in the oracle) and returns to the queue."""
        fsm = _load_rn_refine()
        assert fsm.states["route_decomposed"].on_yes == "dequeue_next"

    def test_empty_queue_routes_to_synthesis(self) -> None:
        """When the work-tree queue drains, control moves to bottom-up synthesis."""
        fsm = _load_rn_refine()
        assert fsm.states["dequeue_next"].on_yes == "build_synth"

    def test_synthesis_chain_present(self) -> None:
        """Bottom-up synthesis fans out to workers then chains into assembly (ENH-2565)."""
        fsm = _load_rn_refine()
        for s in (
            "build_synth",
            "synth_dispatch",
            "assemble",
            "final_score",
            "finalize",
        ):
            assert s in fsm.states, f"missing synthesis state: {s}"
        assert fsm.states["build_synth"].next == "synth_dispatch"
        # ENH-2691: synth_dispatch gates on worker/per-node failure instead of
        # falling through unconditionally.
        assert fsm.states["synth_dispatch"].on_yes == "assemble"
        assert fsm.states["synth_dispatch"].on_no == "synth_failure_record"
        assert fsm.states["synth_dispatch"].on_error == "assemble"
        assert fsm.states["synth_failure_record"].next == "assemble"
        # The serial pop/integrate/snapshot trio is replaced by the fan-out worker.
        for s in ("synth_pop", "integrate_node", "snapshot_node"):
            assert s not in fsm.states, f"serial synthesis state {s} should be removed"

    def test_synth_dispatch_background_spawns_integrate_worker(self) -> None:
        """The fan-out state background-spawns the integrate-node worker and barriers."""
        action = _load_rn_refine().states["synth_dispatch"].action
        assert "ll-loop run oracles/integrate-node" in action
        assert "--context run_dir=" in action
        assert "&" in action and "wait" in action  # background-spawn + barrier
        assert "${context.synth_workers}" in action

    def _dispatch_action(self) -> str:
        return _load_rn_refine().states["synth_dispatch"].action

    def test_synth_dispatch_empty_queue_short_circuits(self, tmp_path: Path) -> None:
        """No internal nodes → skip spawning workers, route straight to assemble."""
        rd = tmp_path / "run"
        rd.mkdir()
        (rd / "synth_queue.txt").write_text("")  # drained / no internal nodes
        rendered = _render(
            self._dispatch_action(),
            context={"synth_workers": "4"},
            captured={"run_dir": {"output": str(rd)}},
        )
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr
        assert "NO_INTERNAL_NODES" in result.stdout
        assert not (rd / "worker-logs").exists()  # never spawned a worker

    def test_synth_dispatch_spawns_clamped_workers_concurrently(self, tmp_path: Path) -> None:
        """K queued nodes with a fake ll-loop worker: workers run concurrently, clamped."""
        rd = tmp_path / "run"
        rd.mkdir()
        (rd / "synth_queue.txt").write_text("p0\np1\n")  # 2 internal nodes
        # Fake `ll-loop`: record start, sleep so overlap is observable, record end.
        bindir = tmp_path / "bin"
        bindir.mkdir()
        fake = bindir / "ll-loop"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            f'echo "start $$ $(date +%s%N)" >> "{rd}/spawn-trace.txt"\n'
            "sleep 0.5\n"
            f'echo "end $$ $(date +%s%N)" >> "{rd}/spawn-trace.txt"\n'
        )
        fake.chmod(0o755)
        rendered = _render(
            self._dispatch_action(),
            context={"synth_workers": "8"},  # clamps down to the 2 queued nodes
            captured={"run_dir": {"output": str(rd)}},
        )
        env = dict(os.environ)
        env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
        result = subprocess.run(
            ["bash", "-c", rendered], cwd=tmp_path, capture_output=True, text=True, env=env
        )
        assert result.returncode == 0, result.stderr
        assert "SYNTH_WORKERS_DONE workers=2" in result.stdout  # clamped to queue length
        # Two workers spawned, and their [start,end] intervals overlap (concurrent).
        lines = [ln.split() for ln in (rd / "spawn-trace.txt").read_text().splitlines()]
        starts = sorted(int(t) for tag, _pid, t in lines if tag == "start")
        ends = sorted(int(t) for tag, _pid, t in lines if tag == "end")
        assert len(starts) == 2 and len(ends) == 2
        # Concurrency: the second worker started before the first finished.
        assert starts[1] < ends[0], "workers did not overlap — dispatch ran serially"

    def test_synth_dispatch_result_ok_on_clean_pass(self, tmp_path: Path) -> None:
        """A clean pass (all workers exit 0, no failed_integrations log) prints OK."""
        rd = tmp_path / "run"
        rd.mkdir()
        (rd / "synth_queue.txt").write_text("p0\n")
        bindir = tmp_path / "bin"
        bindir.mkdir()
        fake = bindir / "ll-loop"
        fake.write_text("#!/usr/bin/env bash\nexit 0\n")
        fake.chmod(0o755)
        rendered = _render(
            self._dispatch_action(),
            context={"synth_workers": "1"},
            captured={"run_dir": {"output": str(rd)}},
        )
        env = dict(os.environ)
        env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
        result = subprocess.run(
            ["bash", "-c", rendered], cwd=tmp_path, capture_output=True, text=True, env=env
        )
        assert result.returncode == 0, result.stderr
        assert "SYNTH_DISPATCH_RESULT=OK" in result.stdout
        assert "SYNTH_DISPATCH_RESULT=FAILED" not in result.stdout

    def test_synth_dispatch_result_ok_on_empty_queue(self, tmp_path: Path) -> None:
        """The NO_INTERNAL_NODES early exit must also print the OK marker (ENH-2691) so a
        single evaluator pattern covers both branches without misrouting to on_no."""
        rd = tmp_path / "run"
        rd.mkdir()
        (rd / "synth_queue.txt").write_text("")
        rendered = _render(
            self._dispatch_action(),
            context={"synth_workers": "4"},
            captured={"run_dir": {"output": str(rd)}},
        )
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr
        assert "SYNTH_DISPATCH_RESULT=OK" in result.stdout

    def test_synth_dispatch_result_failed_on_worker_crash(self, tmp_path: Path) -> None:
        """A worker process crash (non-zero exit) flips the result to FAILED (ENH-2691)."""
        rd = tmp_path / "run"
        rd.mkdir()
        (rd / "synth_queue.txt").write_text("p0\n")
        bindir = tmp_path / "bin"
        bindir.mkdir()
        fake = bindir / "ll-loop"
        fake.write_text("#!/usr/bin/env bash\nexit 1\n")
        fake.chmod(0o755)
        rendered = _render(
            self._dispatch_action(),
            context={"synth_workers": "1"},
            captured={"run_dir": {"output": str(rd)}},
        )
        env = dict(os.environ)
        env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
        result = subprocess.run(
            ["bash", "-c", rendered], cwd=tmp_path, capture_output=True, text=True, env=env
        )
        assert result.returncode == 0, result.stderr
        assert "SYNTH_DISPATCH_RESULT=FAILED" in result.stdout

    def test_synth_dispatch_result_failed_on_per_node_integration_failure(
        self, tmp_path: Path
    ) -> None:
        """A worker that exits 0 but left a per-node failure record still flips to FAILED
        (ENH-2691) — the worker's own `integrate_error` -> `pop` loop never crashes the
        process, so this signal must come from failed_integrations/log.txt, not $?."""
        rd = tmp_path / "run"
        rd.mkdir()
        (rd / "synth_queue.txt").write_text("p0\n")
        failed_dir = rd / "failed_integrations"
        failed_dir.mkdir()
        (failed_dir / "log.txt").write_text("p0\n")
        bindir = tmp_path / "bin"
        bindir.mkdir()
        fake = bindir / "ll-loop"
        fake.write_text("#!/usr/bin/env bash\nexit 0\n")
        fake.chmod(0o755)
        rendered = _render(
            self._dispatch_action(),
            context={"synth_workers": "1"},
            captured={"run_dir": {"output": str(rd)}},
        )
        env = dict(os.environ)
        env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
        result = subprocess.run(
            ["bash", "-c", rendered], cwd=tmp_path, capture_output=True, text=True, env=env
        )
        assert result.returncode == 0, result.stderr
        assert "SYNTH_DISPATCH_RESULT=FAILED" in result.stdout

    def test_node_oracle_refines_then_decides(self) -> None:
        """The oracle scores a node then routes to the adaptive decompose decision."""
        fsm, _ = load_and_validate(NODE_ORACLE)
        assert fsm.states["score_node"].on_yes == "decide_decompose"
        assert fsm.states["decide_decompose"].next == "route_decision"
        assert fsm.states["route_decision"].on_yes == "gate_decompose"


class TestSynthFailureRecord:
    """ENH-2691: synth_failure_record surfaces which node(s) failed before assemble."""

    def _action(self) -> str:
        return _load_rn_refine().states["synth_failure_record"].action

    def test_records_failed_node_ids_from_log(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        failed_dir = rd / "failed_integrations"
        failed_dir.mkdir(parents=True)
        (failed_dir / "log.txt").write_text("p0\np2\n")
        (rd / "plan-rubric.md").write_text("")
        rendered = _render(self._action(), captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr
        rubric = (rd / "plan-rubric.md").read_text()
        assert "RECOVERY_NEEDED" in rubric
        assert "p0" in rubric and "p2" in rubric

    def test_records_generic_message_when_log_absent(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        rd.mkdir(parents=True)
        (rd / "plan-rubric.md").write_text("")
        rendered = _render(self._action(), captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr
        rubric = (rd / "plan-rubric.md").read_text()
        assert "RECOVERY_NEEDED" in rubric
        assert "worker process failure" in rubric


class TestTerminalAndDiagnoseRouting:
    def test_init_on_error_routes_to_diagnose(self) -> None:
        assert _load_rn_refine().states["init"].on_error == "diagnose"

    def test_diagnose_exists_and_is_prompt(self) -> None:
        fsm = _load_rn_refine()
        assert "diagnose" in fsm.states
        assert fsm.states["diagnose"].action_type == "prompt"

    def test_diagnose_routes_to_failed(self) -> None:
        assert _load_rn_refine().states["diagnose"].next == "failed"

    def test_report_routes_to_done(self) -> None:
        assert _load_rn_refine().states["report"].next == "done"

    def test_report_action_type_is_prompt(self) -> None:
        assert _load_rn_refine().states["report"].action_type == "prompt"

    def test_done_is_bare_terminal(self) -> None:
        fsm = _load_rn_refine()
        assert fsm.states["done"].terminal is True
        assert getattr(fsm.states["done"], "action", None) is None


# ---------------------------------------------------------------------------
# init plumbing — seeds the root node + work-tree bookkeeping
# ---------------------------------------------------------------------------


class TestInitPlumbing:
    def _init_action(self) -> str:
        return _load_rn_refine().states["init"].action

    def test_missing_file_exits_nonzero_and_creates_no_run_dir(self, tmp_path: Path) -> None:
        run_dir = ".loops/runs/rn-refine-T"
        rendered = _render(
            self._init_action(),
            context={"plan_file": "nonexistent/plan.md", "run_dir": run_dir, "resume": ""},
        )
        result = _bash(rendered, tmp_path)
        assert result.returncode != 0
        assert "ERROR" in result.stdout or "ERROR" in result.stderr
        assert not (tmp_path / run_dir).exists()

    def test_seeds_root_node_and_worktree_files(self, tmp_path: Path) -> None:
        content = "# Big Plan\n\n## Phase 1\n\n- a\n\n## Phase 2\n\n- b\n"
        plan = tmp_path / "plan.md"
        plan.write_text(content)
        run_dir_rel = ".loops/runs/rn-refine-T"
        rendered = _render(
            self._init_action(),
            context={"plan_file": str(plan), "run_dir": run_dir_rel, "resume": ""},
        )
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0
        rd = tmp_path / run_dir_rel
        # Canonical working copy + root node copy both equal the source.
        assert (rd / "plan.md").read_text() == content
        assert (rd / "nodes" / "n0" / "plan.md").read_text() == content
        # Work-tree bookkeeping seeded with the root.
        assert (rd / "queue.txt").read_text().strip() == "n0"
        assert (rd / "depth_map.txt").read_text().strip() == "n0 0"
        assert (rd / "node_counter.txt").read_text().strip() == "1"
        assert (rd / "edges.tsv").exists()
        assert (rd / "plan-rubric.md").read_text() == ""
        # Absolute run dir echoed for capture.
        assert Path(result.stdout.strip()).is_absolute()

    def test_init_action_guards_against_already_absolute_run_dir(self) -> None:
        """init must branch on whether $DIR is already absolute (BUG-2435)."""
        action = self._init_action()
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action

    def test_init_handles_absolute_context_run_dir(self, tmp_path: Path) -> None:
        """When ${context.run_dir} is already absolute, init must not double it (BUG-2435)."""
        content = "# Big Plan\n\n## Phase 1\n\n- a\n"
        plan = tmp_path / "plan.md"
        plan.write_text(content)
        run_dir_abs = tmp_path / ".loops" / "runs" / "rn-refine-T"
        rendered = _render(
            self._init_action(),
            context={"plan_file": str(plan), "run_dir": str(run_dir_abs), "resume": ""},
        )
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0
        assert Path(result.stdout.strip()) == run_dir_abs


# ---------------------------------------------------------------------------
# dequeue plumbing — depth-first pop
# ---------------------------------------------------------------------------


class TestDequeuePlumbing:
    def test_pops_head_and_records_depth_and_visited(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        rd.mkdir()
        (rd / "queue.txt").write_text("n0\nn1\n")
        (rd / "depth_map.txt").write_text("n0 0\nn1 1\n")
        (rd / "visited.txt").write_text("")
        (rd / "dequeue_count.txt").write_text("0")
        action = _load_rn_refine().states["dequeue_next"].action
        rendered = _render(action, captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == "n0"
        assert (rd / "queue.txt").read_text().strip() == "n1"
        assert (rd / "current_depth.txt").read_text().strip() == "0"
        assert "n0" in (rd / "visited.txt").read_text()

    def test_empty_queue_emits_sentinel(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        rd.mkdir()
        (rd / "queue.txt").write_text("")
        action = _load_rn_refine().states["dequeue_next"].action
        rendered = _render(action, captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert "QUEUE_EMPTY" in result.stdout

    def _dequeue_action(self) -> str:
        return _load_rn_refine().states["dequeue_next"].action

    def test_deadline_drain_parks_queue_and_emits_sentinel(self, tmp_path: Path) -> None:
        """ENH-2707: past the soft deadline, a non-empty queue is drained instead
        of popped — undrained.txt captures the remainder and queue.txt is emptied."""
        rd = tmp_path / "run"
        rd.mkdir()
        (rd / "queue.txt").write_text("n5\nn6\nn7\n")
        (rd / "depth_map.txt").write_text("n5 1\nn6 1\nn7 1\n")
        (rd / "visited.txt").write_text("")
        (rd / "dequeue_count.txt").write_text("0")
        ctx = InterpolationContext(
            context={"timeout_total": "21600", "synth_reserve": "3600"},
            captured={"run_dir": {"output": str(rd)}},
            elapsed_ms=18_000_001,  # 1ms past (timeout_total - synth_reserve)
        )
        rendered = interpolate(self._dequeue_action(), ctx)
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr
        assert "DEADLINE_DRAIN" in result.stdout
        assert "QUEUE_EMPTY" not in result.stdout
        assert (rd / "undrained.txt").read_text() == "n5\nn6\nn7\n"
        assert (rd / "queue.txt").read_text().strip() == ""

    def test_before_deadline_still_pops_normally(self, tmp_path: Path) -> None:
        """Elapsed time under the reserved-synthesis budget must not trigger a drain."""
        rd = tmp_path / "run"
        rd.mkdir()
        (rd / "queue.txt").write_text("n0\n")
        (rd / "depth_map.txt").write_text("n0 0\n")
        (rd / "visited.txt").write_text("")
        (rd / "dequeue_count.txt").write_text("0")
        ctx = InterpolationContext(
            context={"timeout_total": "21600", "synth_reserve": "3600"},
            captured={"run_dir": {"output": str(rd)}},
            elapsed_ms=1_000,
        )
        rendered = interpolate(self._dequeue_action(), ctx)
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "n0"
        assert "DEADLINE_DRAIN" not in result.stdout
        assert not (rd / "undrained.txt").exists()

    def test_deadline_drain_evaluator_routes_to_build_synth(self) -> None:
        """The widened evaluator pattern must still route both sentinels to build_synth,
        leaving the QUEUE_EMPTY on_yes/on_no wiring exercised by TestRecursiveStructure
        unchanged (ENH-2707 widens the pattern instead of adding a chained gate)."""
        fsm = _load_rn_refine()
        assert fsm.states["dequeue_next"].evaluate.pattern == "QUEUE_EMPTY|DEADLINE_DRAIN"
        assert fsm.states["dequeue_next"].on_yes == "build_synth"


# ---------------------------------------------------------------------------
# Oracle decompose bookkeeping — child-id allocation + depth-first enqueue
# ---------------------------------------------------------------------------


class TestMaterializeChildren:
    def _materialize_action(self) -> str:
        fsm, _ = load_and_validate(NODE_ORACLE)
        return fsm.states["materialize_children"].action

    def test_allocates_ids_edges_depth_and_prepends_queue(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        node_dir = rd / "nodes" / "n0"
        stage = node_dir / "children"
        stage.mkdir(parents=True)
        (stage / "1.md").write_text("# First subgoal\n\ndetail a\n")
        (stage / "2.md").write_text("# Second subgoal\n\ndetail b\n")
        (rd / "node_counter.txt").write_text("1")
        (rd / "queue.txt").write_text("nSIB\n")  # an existing sibling already queued
        (rd / "depth_map.txt").write_text("n0 0\n")
        (rd / "edges.tsv").write_text("")

        rendered = _render(
            self._materialize_action(),
            context={"run_dir": str(rd), "node_id": "n0", "depth": "0"},
            captured={"run_dir": {"output": str(node_dir)}},
        )
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0
        assert "DECOMPOSED_OK" in result.stdout

        # Two child node dirs created with their sub-plans.
        assert (rd / "nodes" / "n1" / "plan.md").read_text().startswith("# First subgoal")
        assert (rd / "nodes" / "n2" / "plan.md").read_text().startswith("# Second subgoal")
        # Counter advanced past both children.
        assert (rd / "node_counter.txt").read_text().strip() == "3"
        # Edges recorded with titles.
        edges = (rd / "edges.tsv").read_text()
        assert "n0\tn1\tFirst subgoal" in edges
        assert "n0\tn2\tSecond subgoal" in edges
        # Children at parent depth + 1.
        depth = (rd / "depth_map.txt").read_text()
        assert "n1 1" in depth and "n2 1" in depth
        # Depth-first: children prepended BEFORE the existing sibling.
        queue = [ln for ln in (rd / "queue.txt").read_text().splitlines() if ln.strip()]
        assert queue == ["n1", "n2", "nSIB"]

    def test_no_staged_children_reports_no_children(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        node_dir = rd / "nodes" / "n0"
        node_dir.mkdir(parents=True)
        (rd / "node_counter.txt").write_text("1")
        (rd / "queue.txt").write_text("")
        (rd / "depth_map.txt").write_text("n0 0\n")
        (rd / "edges.tsv").write_text("")
        rendered = _render(
            self._materialize_action(),
            context={"run_dir": str(rd), "node_id": "n0", "depth": "0"},
            captured={"run_dir": {"output": str(node_dir)}},
        )
        result = _bash(rendered, tmp_path)
        assert "NO_CHILDREN" in result.stdout


class TestGateDecomposeCaps:
    def _gate_action(self) -> str:
        fsm, _ = load_and_validate(NODE_ORACLE)
        return fsm.states["gate_decompose"].action

    def _run(self, tmp_path: Path, depth: str, max_depth: str, max_nodes: str, counter: str) -> str:
        rd = tmp_path / "run"
        rd.mkdir(exist_ok=True)
        (rd / "node_counter.txt").write_text(counter)
        rendered = _render(
            self._gate_action(),
            context={
                "run_dir": str(rd),
                "depth": depth,
                "max_depth": max_depth,
                "max_nodes": max_nodes,
            },
        )
        return _bash(rendered, tmp_path).stdout

    def test_depth_cap(self, tmp_path: Path) -> None:
        # depth 3, max_depth 3 -> next depth 4 > 3 -> capped
        assert "CAP_DEPTH" in self._run(tmp_path, "3", "3", "40", "5")

    def test_node_budget_cap(self, tmp_path: Path) -> None:
        assert "CAP_NODES" in self._run(tmp_path, "0", "3", "10", "10")

    def test_ok_under_caps(self, tmp_path: Path) -> None:
        assert "OK" in self._run(tmp_path, "0", "3", "40", "2")


# ---------------------------------------------------------------------------
# Bottom-up synthesis topological order (deepest internal nodes first)
# ---------------------------------------------------------------------------


class TestBuildSynthOrder:
    def _build_synth_action(self) -> str:
        return _load_rn_refine().states["build_synth"].action

    def test_deepest_first_order_and_leaf_backfill(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        nodes = rd / "nodes"
        # Tree: n0 -> {n1(leaf), n2}; n2 -> {n3(leaf), n4(leaf)}
        for nid in ("n0", "n1", "n2", "n3", "n4"):
            (nodes / nid).mkdir(parents=True)
            (nodes / nid / "plan.md").write_text(f"# {nid}\n")
        (rd / "edges.tsv").write_text("n0\tn1\tone\nn0\tn2\ttwo\nn2\tn3\tthree\nn2\tn4\tfour\n")
        (rd / "depth_map.txt").write_text("n0 0\nn1 1\nn2 1\nn3 2\nn4 2\n")

        rendered = _render(self._build_synth_action(), captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr

        # Internal nodes only (n0, n2), deepest first -> n2 before n0.
        order = [ln for ln in (rd / "synth_queue.txt").read_text().splitlines() if ln.strip()]
        assert order == ["n2", "n0"]
        # Leaves are backfilled with final.md; internal nodes are not (integration writes theirs).
        for leaf in ("n1", "n3", "n4"):
            assert (nodes / leaf / "final.md").exists()
        for internal in ("n0", "n2"):
            assert not (nodes / internal / "final.md").exists()

    def test_no_decomposition_yields_empty_synth_queue(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        nodes = rd / "nodes"
        (nodes / "n0").mkdir(parents=True)
        (nodes / "n0" / "plan.md").write_text("# root\n")
        (rd / "edges.tsv").write_text("")
        (rd / "depth_map.txt").write_text("n0 0\n")
        rendered = _render(self._build_synth_action(), captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0
        assert (rd / "synth_queue.txt").read_text().strip() == ""
        # Root (a leaf in this degenerate case) is backfilled so assembly has an input.
        assert (nodes / "n0" / "final.md").exists()


# ---------------------------------------------------------------------------
# ENH-2565: resume from an interrupted integration phase
# ---------------------------------------------------------------------------


class TestResumeRouting:
    """init -> check_resume routes 3-way (BUG-2610): RESUME_WALK -> resume_reconcile,
    RESUME_SYNTH -> resume_build_synth (via route_resume_synth), FRESH -> dequeue_next."""

    def test_init_routes_to_check_resume(self) -> None:
        assert _load_rn_refine().states["init"].next == "check_resume"

    def test_check_resume_routes_walk_and_synth_legs(self) -> None:
        fsm = _load_rn_refine()
        assert fsm.states["check_resume"].on_yes == "resume_reconcile"
        assert fsm.states["check_resume"].on_no == "route_resume_synth"
        assert fsm.states["check_resume"].on_error == "dequeue_next"
        assert fsm.states["route_resume_synth"].on_yes == "resume_build_synth"
        assert fsm.states["route_resume_synth"].on_no == "dequeue_next"
        assert fsm.states["resume_reconcile"].next == "dequeue_next"

    def test_resume_context_knob_declared(self) -> None:
        assert "resume" in _load_rn_refine().context

    def test_deadline_drain_context_knobs_declared(self) -> None:
        """ENH-2707: synth_reserve + its timeout_total mirror must be declared context
        vars (the engine exposes no ${loop.timeout} interpolation to read the
        top-level `timeout:` field directly, so it must be hand-mirrored)."""
        ctx = _load_rn_refine().context
        assert ctx["synth_reserve"] == 3600
        assert ctx["timeout_total"] == _load_rn_refine().timeout

    def test_resume_build_synth_routes_to_dispatch(self) -> None:
        assert _load_rn_refine().states["resume_build_synth"].next == "synth_dispatch"

    def test_check_resume_emits_fresh_without_knob(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        (rd / "nodes").mkdir(parents=True)
        action = _load_rn_refine().states["check_resume"].action
        rendered = _render(
            action, context={"resume": ""}, captured={"run_dir": {"output": str(rd)}}
        )
        result = _bash(rendered, tmp_path)
        assert "FRESH" in result.stdout
        assert "RESUME_WALK" not in result.stdout and "RESUME_SYNTH" not in result.stdout

    def test_check_resume_emits_resume_synth_when_tree_fully_walked(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        (rd / "nodes").mkdir(parents=True)
        (rd / "visited.txt").write_text("n0\n")
        (rd / "node_outcome_n0.txt").write_text("REFINED_LEAF\n")
        (rd / "queue.txt").write_text("")
        action = _load_rn_refine().states["check_resume"].action
        rendered = _render(
            action, context={"resume": "1"}, captured={"run_dir": {"output": str(rd)}}
        )
        result = _bash(rendered, tmp_path)
        assert "RESUME_SYNTH" in result.stdout

    def test_check_resume_emits_resume_walk_when_node_in_flight(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        (rd / "nodes").mkdir(parents=True)
        # n0 visited and complete; n1 visited but never got an outcome (in-flight kill).
        (rd / "visited.txt").write_text("n0\nn1\n")
        (rd / "node_outcome_n0.txt").write_text("REFINED_LEAF\n")
        (rd / "queue.txt").write_text("")
        action = _load_rn_refine().states["check_resume"].action
        rendered = _render(
            action, context={"resume": "1"}, captured={"run_dir": {"output": str(rd)}}
        )
        result = _bash(rendered, tmp_path)
        assert "RESUME_WALK" in result.stdout

    def test_check_resume_emits_resume_walk_when_queue_nonempty(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        (rd / "nodes").mkdir(parents=True)
        (rd / "visited.txt").write_text("n0\n")
        (rd / "node_outcome_n0.txt").write_text("DECOMPOSED\n")
        (rd / "queue.txt").write_text("n1\n")
        action = _load_rn_refine().states["check_resume"].action
        rendered = _render(
            action, context={"resume": "1"}, captured={"run_dir": {"output": str(rd)}}
        )
        result = _bash(rendered, tmp_path)
        assert "RESUME_WALK" in result.stdout

    def test_check_resume_emits_resume_walk_when_undrained_nonempty(self, tmp_path: Path) -> None:
        """ENH-2707: a soft-deadline drain empties queue.txt into undrained.txt, so a
        naive queue-emptiness check would misroute a drained run to RESUME_SYNTH even
        though nodes were never walked."""
        rd = tmp_path / "run"
        (rd / "nodes").mkdir(parents=True)
        (rd / "visited.txt").write_text("n0\n")
        (rd / "node_outcome_n0.txt").write_text("REFINED_LEAF\n")
        (rd / "queue.txt").write_text("")
        (rd / "undrained.txt").write_text("n5\nn6\n")
        action = _load_rn_refine().states["check_resume"].action
        rendered = _render(
            action, context={"resume": "1"}, captured={"run_dir": {"output": str(rd)}}
        )
        result = _bash(rendered, tmp_path)
        assert "RESUME_WALK" in result.stdout


class TestResumeReconcile:
    """resume_reconcile re-queues visited-but-outcome-less nodes ahead of anything
    still sitting in queue.txt, preserving visited.txt's relative order (BUG-2610)."""

    def _action(self) -> str:
        return _load_rn_refine().states["resume_reconcile"].action

    def test_requeues_incomplete_visited_nodes_before_stale_queue(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        rd.mkdir(parents=True)
        # n0, n1 visited+complete; n19 visited, no outcome (in-flight at kill time).
        (rd / "visited.txt").write_text("n0\nn1\nn19\n")
        (rd / "node_outcome_n0.txt").write_text("REFINED_LEAF\n")
        (rd / "node_outcome_n1.txt").write_text("DECOMPOSED\n")
        # n5, n20-n23 were sitting in queue.txt, never dequeued.
        (rd / "queue.txt").write_text("n5\nn20\nn21\nn22\nn23\n")
        rendered = _render(self._action(), captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr
        order = [ln for ln in (rd / "queue.txt").read_text().splitlines() if ln.strip()]
        # In-flight node first, then the never-dequeued queue tail, unchanged order.
        assert order == ["n19", "n5", "n20", "n21", "n22", "n23"]

    def test_no_incomplete_nodes_leaves_queue_untouched(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        rd.mkdir(parents=True)
        (rd / "visited.txt").write_text("n0\n")
        (rd / "node_outcome_n0.txt").write_text("DECOMPOSED\n")
        (rd / "queue.txt").write_text("n1\nn2\n")
        rendered = _render(self._action(), captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr
        order = [ln for ln in (rd / "queue.txt").read_text().splitlines() if ln.strip()]
        assert order == ["n1", "n2"]

    def test_merges_undrained_nodes_back_into_queue_and_clears_it(self, tmp_path: Path) -> None:
        """ENH-2707: nodes parked by the soft-deadline drain were never dequeued, so
        they never entered visited.txt — PENDING alone would never see them. They
        must merge back in (after PENDING, before any never-dequeued queue tail) and
        undrained.txt must be cleared so a repeat resume is idempotent."""
        rd = tmp_path / "run"
        rd.mkdir(parents=True)
        (rd / "visited.txt").write_text("n0\nn19\n")
        (rd / "node_outcome_n0.txt").write_text("REFINED_LEAF\n")
        (rd / "queue.txt").write_text("")  # drain emptied this
        (rd / "undrained.txt").write_text("n5\nn6\nn7\n")
        rendered = _render(self._action(), captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr
        order = [ln for ln in (rd / "queue.txt").read_text().splitlines() if ln.strip()]
        assert order == ["n19", "n5", "n6", "n7"]
        assert (rd / "undrained.txt").read_text().strip() == ""


class TestInitResumeShortCircuit:
    """init must NOT re-seed (clobber) an existing tree when resuming."""

    def _init_action(self) -> str:
        return _load_rn_refine().states["init"].action

    def test_resume_preserves_existing_tree(self, tmp_path: Path) -> None:
        plan = tmp_path / "plan.md"
        plan.write_text("# Plan\n\n## A\n- x\n")
        rd = tmp_path / "run"
        # Simulate a prior run's tree with a hand-marked queue we must not clobber.
        (rd / "nodes" / "n0").mkdir(parents=True)
        (rd / "nodes" / "n0" / "plan.md").write_text("# INDEX (do not clobber)\n")
        (rd / "queue.txt").write_text("nSHOULD_SURVIVE\n")
        (rd / "node_counter.txt").write_text("7")
        rendered = _render(
            self._init_action(),
            context={"plan_file": str(plan), "run_dir": str(rd), "resume": "1"},
        )
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0
        # Existing bookkeeping untouched (no re-seed).
        assert (rd / "queue.txt").read_text().strip() == "nSHOULD_SURVIVE"
        assert (rd / "node_counter.txt").read_text().strip() == "7"
        assert (rd / "nodes" / "n0" / "plan.md").read_text() == "# INDEX (do not clobber)\n"
        # source-path is (re)recorded so scope/write-lock stay satisfied on resume.
        assert (rd / ".source-path").read_text().strip() == str(plan.resolve())

    def test_fresh_run_still_seeds(self, tmp_path: Path) -> None:
        plan = tmp_path / "plan.md"
        plan.write_text("# Plan\n\n## A\n- x\n")
        rd = tmp_path / "run"
        rendered = _render(
            self._init_action(),
            context={"plan_file": str(plan), "run_dir": str(rd), "resume": ""},
        )
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0
        assert (rd / "queue.txt").read_text().strip() == "n0"
        assert (rd / "node_counter.txt").read_text().strip() == "1"

    def test_no_resume_flag_refuses_to_reseed(self, tmp_path: Path) -> None:
        """BUG-2610: run_dir pointed at a populated prior tree without
        --context resume=1 must refuse (exit 1 + hint), not destroy the tree."""
        plan = tmp_path / "plan.md"
        plan.write_text("# Plan\n\n## A\n- x\n")
        rd = tmp_path / "run"
        (rd / "nodes" / "n0").mkdir(parents=True)
        (rd / "nodes" / "n0" / "plan.md").write_text("# INDEX (do not clobber)\n")
        (rd / "queue.txt").write_text("nSHOULD_SURVIVE\n")
        (rd / "node_counter.txt").write_text("7")
        rendered = _render(
            self._init_action(),
            context={"plan_file": str(plan), "run_dir": str(rd), "resume": ""},
        )
        result = _bash(rendered, tmp_path)
        assert result.returncode == 1
        assert "resume=1" in result.stdout
        # Existing tree must survive the refusal untouched.
        assert (rd / "queue.txt").read_text().strip() == "nSHOULD_SURVIVE"
        assert (rd / "node_counter.txt").read_text().strip() == "7"
        assert (rd / "nodes" / "n0" / "plan.md").read_text() == "# INDEX (do not clobber)\n"


class TestResumeBuildSynth:
    """resume_build_synth rebuilds synth_queue from on-disk final.md absence (AC #5)."""

    def _action(self) -> str:
        return _load_rn_refine().states["resume_build_synth"].action

    def test_requeues_only_internal_nodes_lacking_final(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        nodes = rd / "nodes"
        # Tree: n0 -> {n1(leaf), n2}; n2 -> {n3(leaf), n4(leaf)}. Internals: n0, n2.
        for nid in ("n0", "n1", "n2", "n3", "n4"):
            (nodes / nid).mkdir(parents=True)
            (nodes / nid / "plan.md").write_text(f"# {nid}\n")
        (rd / "edges.tsv").write_text("n0\tn1\tone\nn0\tn2\ttwo\nn2\tn3\tthree\nn2\tn4\tfour\n")
        (rd / "depth_map.txt").write_text("n0 0\nn1 1\nn2 1\nn3 2\nn4 2\n")
        # n2 already integrated (has final.md); n0 does not. Leaves n3/n4 done; n1 not.
        (nodes / "n2" / "final.md").write_text("# n2 integrated\n")
        for leaf in ("n3", "n4"):
            (nodes / leaf / "final.md").write_text(f"# {leaf}\n")
        rendered = _render(self._action(), captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr
        # Only n0 (internal, still lacking final.md) is re-queued; n2 is skipped.
        order = [ln for ln in (rd / "synth_queue.txt").read_text().splitlines() if ln.strip()]
        assert order == ["n0"]
        # Idempotent leaf backfill restored n1's missing final.md.
        assert (nodes / "n1" / "final.md").exists()

    def test_covers_popped_but_not_integrated_node(self, tmp_path: Path) -> None:
        """A node dropped from the OLD queue but never integrated is re-queued."""
        rd = tmp_path / "run"
        nodes = rd / "nodes"
        # n0 -> {n1(leaf)}; n1 leaf has final.md, n0 was popped pre-kill (never integrated).
        for nid in ("n0", "n1"):
            (nodes / nid).mkdir(parents=True)
            (nodes / nid / "plan.md").write_text(f"# {nid}\n")
        (nodes / "n1" / "final.md").write_text("# n1\n")
        (rd / "edges.tsv").write_text("n0\tn1\tonly\n")
        (rd / "depth_map.txt").write_text("n0 0\nn1 1\n")
        # Stale old queue is empty (n0 was popped) — resume must ignore it and rebuild.
        (rd / "synth_queue.txt").write_text("")
        rendered = _render(self._action(), captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0
        order = [ln for ln in (rd / "synth_queue.txt").read_text().splitlines() if ln.strip()]
        assert order == ["n0"]


class TestAssembleAndFinalize:
    def test_assemble_prefers_root_final(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        (rd / "nodes" / "n0").mkdir(parents=True)
        (rd / "nodes" / "n0" / "final.md").write_text("# assembled\n")
        (rd / "nodes" / "n0" / "plan.md").write_text("# index\n")
        action = _load_rn_refine().states["assemble"].action
        rendered = _render(action, captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0
        assert (rd / "plan.md").read_text() == "# assembled\n"

    def test_assemble_writes_partial_drain_marker_when_undrained_nonempty(
        self, tmp_path: Path
    ) -> None:
        """ENH-2707: when dequeue_next's soft-deadline drain left nodes unwalked,
        assemble must append a PARTIAL_DRAIN marker (reusing the RECOVERY_NEEDED
        contract) naming the undrained nodes and the resume command."""
        rd = tmp_path / "run"
        (rd / "nodes" / "n0").mkdir(parents=True)
        (rd / "nodes" / "n0" / "final.md").write_text("# assembled\n")
        (rd / "undrained.txt").write_text("n5\nn6\n")
        (rd / ".source-path").write_text("/tmp/orig-plan.md\n")
        action = _load_rn_refine().states["assemble"].action
        rendered = _render(action, captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr
        rubric = (rd / "plan-rubric.md").read_text()
        assert "PARTIAL_DRAIN" in rubric
        assert "n5,n6" in rubric
        assert "--context resume=1" in rubric
        assert "/tmp/orig-plan.md" in rubric

    def test_assemble_omits_partial_drain_marker_when_undrained_empty(
        self, tmp_path: Path
    ) -> None:
        rd = tmp_path / "run"
        (rd / "nodes" / "n0").mkdir(parents=True)
        (rd / "nodes" / "n0" / "final.md").write_text("# assembled\n")
        action = _load_rn_refine().states["assemble"].action
        rendered = _render(action, captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr
        assert not (rd / "plan-rubric.md").exists() or (
            "PARTIAL_DRAIN" not in (rd / "plan-rubric.md").read_text()
        )

    def test_finalize_overwrites_source_in_place(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        rd.mkdir()
        source = tmp_path / "orig-plan.md"
        source.write_text("# old\n")
        (rd / ".source-path").write_text(str(source) + "\n")
        (rd / "plan.md").write_text("# reassembled refined plan\n")
        action = _load_rn_refine().states["finalize"].action
        rendered = _render(action, captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0
        assert source.read_text() == "# reassembled refined plan\n"
        # ENH-2418: a timestamped backup of the ORIGINAL source is written before overwrite.
        backups = list(rd.glob("source-backup-*.md"))
        assert len(backups) == 1, f"expected exactly one backup, got: {backups}"
        assert backups[0].read_text() == "# old\n"


# ---------------------------------------------------------------------------
# ENH-2418: preflight invariant + safe-abort terminal for the in-place write
# ---------------------------------------------------------------------------


class TestFinalizeSafety:
    """Guard against a degenerate synthesis silently clobbering the user's source.

    The recursive-descent pipeline re-assembles ${run_dir}/plan.md from the node
    tree. If that file is empty, truncated below the floor, or drops required
    sections, the run must NOT overwrite the original — it terminates via the
    new `finalize_aborted` terminal with the invariant violation surfaced.
    """

    def _preflight_action(self) -> str:
        return _load_rn_refine().states["preflight_check"].action

    def _finalize_action(self) -> str:
        return _load_rn_refine().states["finalize"].action

    def _seed(
        self,
        tmp_path: Path,
        *,
        plan: str,
        source: str,
        children: dict[str, str] | None = None,
    ) -> Path:
        rd = tmp_path / "run"
        rd.mkdir()
        (rd / "plan.md").write_text(plan)
        source_path = tmp_path / "plan.md"
        source_path.write_text(source)
        (rd / ".source-path").write_text(str(source_path) + "\n")
        for nid, final_content in (children or {}).items():
            node_dir = rd / "nodes" / nid
            node_dir.mkdir(parents=True, exist_ok=True)
            (node_dir / "final.md").write_text(final_content)
        return rd

    def test_preflight_emits_ok_for_healthy_plan(self, tmp_path: Path) -> None:
        source = "# Big Plan\n\n## Phase 1\n\n- a\n\n## Phase 2\n\n- b\n"
        plan = source + "\n## Phase 3 (added)\n\n- c\n"
        rd = self._seed(tmp_path, plan=plan, source=source)
        rendered = _render(self._preflight_action(), captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr
        assert "INVARIANT_OK" in result.stdout
        assert "INVARIANT_FAIL" not in result.stdout

    def test_preflight_aborts_on_empty_final(self, tmp_path: Path) -> None:
        source = "# Big Plan\n\n## Phase 1\n\n- a\n"
        rd = self._seed(tmp_path, plan="", source=source)
        rendered = _render(self._preflight_action(), captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert "INVARIANT_FAIL" in result.stdout
        assert "EMPTY" in result.stdout

    def test_preflight_aborts_on_truncated_below_floor(self, tmp_path: Path) -> None:
        # Source is ~80 bytes; final is 4 bytes (~5%) — well below the 0.5 floor.
        source = "# Big Plan\n\n## Phase 1\n\n" + ("- bullet line\n" * 6) + "## Phase 2\n"
        rd = self._seed(tmp_path, plan="# x\n", source=source)
        rendered = _render(self._preflight_action(), captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert "INVARIANT_FAIL" in result.stdout
        assert "BELOW_FLOOR" in result.stdout

    def test_preflight_aborts_on_missing_required_sections(self, tmp_path: Path) -> None:
        # Source has two top-level sections; final keeps only one.
        source = "# Big Plan\n\n## Phase 1\n\n- a\n\n## Phase 2\n\n- b\n"
        plan = "# Big Plan\n\n## Phase 1\n\n- a\n" + ("x" * 200)  # preserve length, drop section
        rd = self._seed(tmp_path, plan=plan, source=source)
        rendered = _render(self._preflight_action(), captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert "INVARIANT_FAIL" in result.stdout
        assert "MISSING_SECTIONS" in result.stdout
        assert "Phase 2" in result.stdout

    def test_preflight_ok_when_heading_moved_to_child(self, tmp_path: Path) -> None:
        # ENH-2690: the root decomposed and rewrote its own index heading for
        # "Phase 2" (decide_decompose's documented behavior), but the section's
        # content is redeemed by a child node's final.md h1 title — not lost.
        source = "# Big Plan\n\n## Phase 1\n\n- a\n\n## Phase 2\n\n- b\n"
        plan = "# Big Plan\n\n## Phase 1\n\n- a\n\n## Phase 2 (expanded, see below)\n"
        rd = self._seed(
            tmp_path,
            plan=plan,
            source=source,
            children={"n1": "# Phase 2\n\n- b\n- more detail\n"},
        )
        rendered = _render(self._preflight_action(), captured={"run_dir": {"output": str(rd)}})
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0, result.stderr
        assert "INVARIANT_OK" in result.stdout
        assert "INVARIANT_FAIL" not in result.stdout

    def test_finalize_dry_run_does_not_overwrite_source(self, tmp_path: Path) -> None:
        source = "# original\n"
        rd = self._seed(tmp_path, plan="# reassembled\n", source=source)
        rendered = _render(
            self._finalize_action(),
            captured={"run_dir": {"output": str(rd)}},
            context={"dry_run": "true"},
        )
        result = _bash(rendered, tmp_path)
        assert result.returncode == 0
        # Source is untouched in dry-run mode.
        assert (tmp_path / "plan.md").read_text() == "# original\n"
        # No backup written in dry-run mode (nothing destructive attempted).
        assert list(rd.glob("source-backup-*.md")) == []

    def test_finalize_aborted_is_terminal(self) -> None:
        fsm = _load_rn_refine()
        assert "finalize_aborted" in fsm.states
        assert fsm.states["finalize_aborted"].terminal is True

    def test_finalize_aborted_action_is_shell(self) -> None:
        fsm = _load_rn_refine()
        assert fsm.states["finalize_aborted"].action_type == "shell"

    def test_preflight_routes_to_finalize_on_ok(self) -> None:
        fsm = _load_rn_refine()
        assert fsm.states["preflight_check"].on_yes == "finalize"

    def test_preflight_routes_to_finalize_aborted_on_fail(self) -> None:
        fsm = _load_rn_refine()
        assert fsm.states["preflight_check"].on_no == "finalize_aborted"

    def test_preflight_routes_to_finalize_aborted_on_error(self) -> None:
        fsm = _load_rn_refine()
        assert fsm.states["preflight_check"].on_error == "finalize_aborted"

    def test_final_score_routes_to_preflight_check(self) -> None:
        fsm = _load_rn_refine()
        assert fsm.states["final_score"].on_yes == "preflight_check"
        assert fsm.states["final_score"].on_no == "preflight_check"

    def test_description_states_final_score_is_advisory(self) -> None:
        # ENH-2692: root-level rubric verdict has no effect on control flow
        # (both on_yes/on_no route to preflight_check above); the loop
        # description must say so explicitly rather than implying the
        # write-back is gated on rubric convergence.
        fsm = _load_rn_refine()
        assert "ADVISORY" in fsm.description


# ---------------------------------------------------------------------------
# ENH-2565: readiness-gated pop + concurrency core
#
# The bottom-up-synthesis concurrency core (little_loops.rn_synth_queue) is the
# shippable module the oracles/integrate-node worker sub-loop invokes (both as a
# library and via `python -m little_loops.rn_synth_queue`). Each method below
# retires one acceptance criterion: the worker's pop is a thin shim around
# try_pop_ready / mark_complete / queue_is_empty.
# ---------------------------------------------------------------------------


class TestSynthPopReadinessGate:
    """Retire the ENH-2565 acceptance criteria against the rn_synth_queue module."""

    # -- fixture helpers ----------------------------------------------------

    @staticmethod
    def _node_dir(rd: Path, nid: str) -> Path:
        d = rd / "nodes" / nid
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _seed_final(self, rd: Path, nid: str) -> None:
        """Give a node a final.md — a backfilled leaf or an integrated internal node."""
        (self._node_dir(rd, nid) / "final.md").write_text(f"# {nid} final\n")

    def _write_queue(self, rd: Path, order: list[str]) -> None:
        rd.mkdir(parents=True, exist_ok=True)
        (rd / "synth_queue.txt").write_text("".join(f"{n}\n" for n in order))

    def _seed_build_synth_tree(self, tmp_path: Path) -> Path:
        """Mirror TestBuildSynthOrder's tree: n0 -> {n1(leaf), n2}; n2 -> {n3, n4}.

        Internal nodes are n0 and n2; leaves n1, n3, n4 already carry final.md.
        The deepest-first synth queue that build_synth would emit is [n2, n0].
        """
        rd = tmp_path / "run"
        for nid in ("n0", "n1", "n2", "n3", "n4"):
            self._node_dir(rd, nid)
            (rd / "nodes" / nid / "plan.md").write_text(f"# {nid}\n")
        (rd / "edges.tsv").write_text("n0\tn1\tone\nn0\tn2\ttwo\nn2\tn3\tthree\nn2\tn4\tfour\n")
        (rd / "depth_map.txt").write_text("n0 0\nn1 1\nn2 1\nn3 2\nn4 2\n")
        for leaf in ("n1", "n3", "n4"):
            self._seed_final(rd, leaf)
        self._write_queue(rd, ["n2", "n0"])  # deepest-first, internal-only
        return rd

    def _seed_flat_ready(self, tmp_path: Path, k: int) -> tuple[Path, list[str]]:
        """K independent internal nodes, each with one already-integrated leaf child.

        Every queued node is ready from the start, so pops are gated only by the
        lock — this isolates the no-double-pop / no-lost-node contention behavior.
        """
        rd = tmp_path / "run"
        ids = [f"p{i}" for i in range(k)]
        edges = []
        for pid in ids:
            self._node_dir(rd, pid)
            child = f"{pid}c"
            self._seed_final(rd, child)  # leaf child already integrated
            edges.append(f"{pid}\t{child}\tchild-of-{pid}")
        (rd / "edges.tsv").write_text("\n".join(edges) + "\n")
        self._write_queue(rd, ids)
        return rd, ids

    # -- test 1: DRAIN contract ---------------------------------------------

    def test_pop_returns_none_when_queue_empty(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        rd.mkdir()
        # No synth_queue.txt at all -> empty -> None on every call.
        assert try_pop_ready(rd) is None
        assert queue_is_empty(rd) is True
        # A queue file with only blank lines is likewise empty.
        (rd / "synth_queue.txt").write_text("\n   \n\n")
        assert try_pop_ready(rd) is None
        assert queue_is_empty(rd) is True

    # -- test 2: deepest-first invariant under locking ----------------------

    def test_pop_returns_deepest_first_in_serial(self, tmp_path: Path) -> None:
        rd = self._seed_build_synth_tree(tmp_path)
        # n2 (depth 1) is the deepest ready internal node; n0 (depth 0) is not
        # ready until n2 integrates, because n2 is one of n0's children.
        assert try_pop_ready(rd) == "n2"
        self._seed_final(rd, "n2")  # simulate integrate_node writing n2/final.md
        assert try_pop_ready(rd) == "n0"
        assert try_pop_ready(rd) is None
        assert queue_is_empty(rd) is True

    # -- test 3: readiness gating -------------------------------------------

    def test_pop_skips_node_with_unfinished_child(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        self._node_dir(rd, "n0")
        self._node_dir(rd, "n1")
        (rd / "edges.tsv").write_text("n0\tn1\tonly-child\n")
        self._write_queue(rd, ["n0"])
        # n1 lacks final.md -> n0 not ready -> None, but queue is NOT empty (WAIT).
        assert try_pop_ready(rd) is None
        assert queue_is_empty(rd) is False
        # After n1 integrates, n0 becomes ready and pops.
        self._seed_final(rd, "n1")
        assert try_pop_ready(rd) == "n0"

    # -- test 4: no double-pop under N-worker contention --------------------

    def test_pop_never_returns_same_node_twice_under_contention(self, tmp_path: Path) -> None:
        rd, ids = self._seed_flat_ready(tmp_path, k=4)

        def drain() -> list[str]:
            out: list[str] = []
            while True:
                node = try_pop_ready(rd, lock_timeout=5.0)
                if node is None:
                    return out
                out.append(node)

        popped: list[str] = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            for f in as_completed([pool.submit(drain) for _ in range(8)]):
                popped.extend(f.result(timeout=10.0))

        assert sorted(popped) == sorted(ids)  # every queued node popped exactly once
        assert len(popped) == len(set(popped))  # no duplicates
        assert queue_is_empty(rd) is True

    # -- test 5: no lost node with simultaneous callers ---------------------

    def test_pop_with_all_children_ready_handles_simultaneous_callers(self, tmp_path: Path) -> None:
        k = 8
        rd, ids = self._seed_flat_ready(tmp_path, k=k)

        def pop_once() -> str | None:
            return try_pop_ready(rd, lock_timeout=5.0)

        results: list[str | None] = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(pop_once) for _ in range(k)]
            for f in as_completed(futures):
                # A raised acquire_lock TimeoutError would surface here and fail.
                results.append(f.result(timeout=10.0))

        got = [r for r in results if r is not None]
        assert len(got) == k  # no lost node
        assert sorted(got) == sorted(ids)  # exactly the queued set, all distinct
        assert queue_is_empty(rd) is True

    # -- test 6: WAIT-vs-DRAIN disambiguation -------------------------------

    def test_pop_returns_none_when_nonempty_but_nothing_ready(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        self._node_dir(rd, "n0")
        self._node_dir(rd, "n1")  # child, not yet integrated
        (rd / "edges.tsv").write_text("n0\tn1\tchild\n")
        self._write_queue(rd, ["n0"])
        # Non-empty queue, nothing ready -> None, and queue_is_empty is False so
        # the worker knows to sleep and retry rather than route to assemble.
        assert try_pop_ready(rd) is None
        assert queue_is_empty(rd) is False

    # -- test 7: mark_complete observable + idempotent ----------------------

    def test_mark_complete_touches_done_sentinel_and_is_idempotent(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        rd.mkdir()
        sentinel = rd / "done" / "n0.done"
        assert not sentinel.exists()
        mark_complete(rd, "n0")
        assert sentinel.exists()
        before = sorted(p.name for p in (rd / "done").iterdir())
        mark_complete(rd, "n0")  # second call must not raise
        after = sorted(p.name for p in (rd / "done").iterdir())
        assert before == after == ["n0.done"]

    # -- regression guard: correct locking primitive -----------------------

    def test_no_import_of_fsm_concurrency_lockmanager(self) -> None:
        """rn_synth_queue must use acquire_lock, never little_loops.fsm.concurrency."""
        source = QUEUE_MODULE.read_text()
        tree = ast.parse(source)
        offenders = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("little_loops.fsm.concurrency")
        ]
        assert offenders == [], (
            f"spike queue.py must not import fsm.concurrency; found: {offenders}"
        )
        # Positive assertion: it depends on the intended primitive.
        assert "from little_loops.file_utils import acquire_lock" in source

    # -- driver CLI subprocess ----------------------------------------------

    def test_driver_cli_returns_drain_when_empty(self, tmp_path: Path) -> None:
        rd = tmp_path / "run"
        rd.mkdir()
        env = dict(os.environ)
        # little_loops resolves from scripts/ (the package root).
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(_REPO_ROOT / "scripts"), env.get("PYTHONPATH", "")) if p
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "little_loops.rn_synth_queue",
                "try-pop",
                str(rd),
            ],
            cwd=str(_REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == "DRAIN\n"
