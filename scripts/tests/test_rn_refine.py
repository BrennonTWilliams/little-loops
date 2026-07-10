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

from little_loops.fsm.interpolation import InterpolationContext, interpolate
from little_loops.fsm.validation import load_and_validate

# ENH-2565 spike package lives at scripts/tests/spike/rn_refine_synth_pop. It is
# imported via its full ``scripts.tests.spike...`` dotted path so the same import
# works both here (under pytest) and from the subprocess CLI test. ``scripts`` is
# an implicit namespace package, so the repo root must be on sys.path.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.tests.spike.rn_refine_synth_pop import (  # noqa: E402
    mark_complete,
    queue_is_empty,
    try_pop_ready,
)

LOOPS = Path(__file__).parent.parent / "little_loops" / "loops"
RN_REFINE = LOOPS / "rn-refine.yaml"
NODE_ORACLE = LOOPS / "oracles" / "plan-node-refine.yaml"
SPIKE_DIR = Path(__file__).parent / "spike" / "rn_refine_synth_pop"


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
            context={"plan_file": str(plan), "run_dir": str(run_dir_abs)},
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

    def _seed(self, tmp_path: Path, *, plan: str, source: str) -> Path:
        rd = tmp_path / "run"
        rd.mkdir()
        (rd / "plan.md").write_text(plan)
        source_path = tmp_path / "plan.md"
        source_path.write_text(source)
        (rd / ".source-path").write_text(str(source_path) + "\n")
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


# ---------------------------------------------------------------------------
# ENH-2565 spike: readiness-gated pop + concurrency core
#
# The bottom-up-synthesis concurrency core is proved out as a standalone library
# (scripts/tests/spike/rn_refine_synth_pop/queue.py) BEFORE rn-refine.yaml's
# synth_pop action is rewritten to import it. Each method below retires one
# acceptance criterion from the ENH-2565 spike plan; the eventual synth_pop
# PYEOF becomes a thin shim around try_pop_ready / mark_complete / queue_is_empty.
# ---------------------------------------------------------------------------


class TestSynthPopReadinessGate:
    """Retire the ENH-2565 acceptance criteria against the spike queue library."""

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
        (rd / "edges.tsv").write_text(
            "n0\tn1\tone\nn0\tn2\ttwo\nn2\tn3\tthree\nn2\tn4\tfour\n"
        )
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

    def test_pop_never_returns_same_node_twice_under_contention(
        self, tmp_path: Path
    ) -> None:
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

    def test_pop_with_all_children_ready_handles_simultaneous_callers(
        self, tmp_path: Path
    ) -> None:
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

    def test_pop_returns_none_when_nonempty_but_nothing_ready(
        self, tmp_path: Path
    ) -> None:
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

    def test_mark_complete_touches_done_sentinel_and_is_idempotent(
        self, tmp_path: Path
    ) -> None:
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
        """queue.py must use acquire_lock, never little_loops.fsm.concurrency."""
        source = (SPIKE_DIR / "queue.py").read_text()
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
        # scripts.* resolves from the repo root; little_loops from scripts/.
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(_REPO_ROOT), str(_REPO_ROOT / "scripts"), env.get("PYTHONPATH", "")) if p
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.tests.spike.rn_refine_synth_pop",
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
