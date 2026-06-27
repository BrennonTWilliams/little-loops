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

import subprocess
from pathlib import Path

from little_loops.fsm.interpolation import InterpolationContext, interpolate
from little_loops.fsm.validation import load_and_validate

LOOPS = Path(__file__).parent.parent / "little_loops" / "loops"
RN_REFINE = LOOPS / "rn-refine.yaml"
NODE_ORACLE = LOOPS / "oracles" / "plan-node-refine.yaml"


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
        """Bottom-up synthesis states exist and chain into assembly."""
        fsm = _load_rn_refine()
        for s in (
            "build_synth",
            "synth_pop",
            "integrate_node",
            "assemble",
            "final_score",
            "finalize",
        ):
            assert s in fsm.states, f"missing synthesis state: {s}"
        assert fsm.states["synth_pop"].on_no == "integrate_node"
        assert fsm.states["synth_pop"].on_yes == "assemble"
        assert fsm.states["integrate_node"].next == "synth_pop"

    def test_node_oracle_refines_then_decides(self) -> None:
        """The oracle scores a node then routes to the adaptive decompose decision."""
        fsm, _ = load_and_validate(NODE_ORACLE)
        assert fsm.states["score_node"].on_yes == "decide_decompose"
        assert fsm.states["decide_decompose"].next == "route_decision"
        assert fsm.states["route_decision"].on_yes == "gate_decompose"


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
            context={"plan_file": "nonexistent/plan.md", "run_dir": run_dir},
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
            context={"plan_file": str(plan), "run_dir": run_dir_rel},
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
