"""ENH-3184 AC2: guard that every task-path child-process spawn is projected.

Enumerates ``subprocess.(run|Popen|check_output|call)`` call sites (not env
construction — an env-construction-shaped guard passes clean on the pre-ENH-3184
tree while ``fsm/runners.py``/``fsm/evaluators.py`` leaked the full environment,
see the issue body) across the task-path module list below, and asserts each
call's ``env=`` either resolves back to :func:`little_loops.host_runner.project_child_env`
or carries an inline ``# ll-no-project: <reason>`` exemption marker on the call's
own line or the line immediately above it.

The per-module ``(spawns, markers)`` table is pinned exactly, not just a
maximum — both a new unmarked spawn *and* a new (unexplained) exemption fail
this test, forcing a deliberate table update either way (AC2).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# (relative path under scripts/, expected total spawn count, expected exempted
# spawn count). expected routed count is spawns - markers.
_TASK_PATH_MODULES: dict[str, tuple[int, int]] = {
    "little_loops/fsm/runners.py": (1, 0),
    "little_loops/fsm/evaluators.py": (4, 1),
    "little_loops/runner_spec.py": (3, 0),
    "little_loops/subprocess_utils.py": (1, 0),
    "little_loops/mcp_call.py": (1, 0),
    "little_loops/worktree_utils.py": (4, 3),
    "little_loops/parallel/worker_pool.py": (9, 7),
    "little_loops/fsm/handoff_handler.py": (1, 0),
    "little_loops/learning_tests/extractor.py": (1, 0),
    "little_loops/session_store/lifecycle.py": (1, 0),
    "little_loops/git_operations.py": (11, 9),
    "little_loops/prepatch_check.py": (2, 1),
    "little_loops/cli/loop/_helpers.py": (2, 0),
    "little_loops/cli/issues/decisions.py": (1, 0),
    "little_loops/cli/action.py": (1, 1),
    "little_loops/cli/doctor.py": (1, 1),
    "little_loops/init/install_check.py": (5, 5),
    # Holds the helper itself; spawns nothing (host_runner.py:1837's
    # `dict(os.environ)` is a snapshot of the parent's own env for reading
    # LL_HOST_CLI/LL_HOOK_HOST, never passed as a child env=).
    "little_loops/host_runner.py": (0, 0),
}

_SPAWN_ATTRS = {"run", "Popen", "check_output", "call"}
_MARKER = "ll-no-project:"


def _is_spawn_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
        and node.func.attr in _SPAWN_ATTRS
    )


def _is_helper_call(value: ast.AST | None) -> bool:
    """True if *value* is (directly) a call to ``project_child_env``."""
    if not isinstance(value, ast.Call):
        return False
    func = value.func
    if isinstance(func, ast.Name):
        return func.id == "project_child_env"
    if isinstance(func, ast.Attribute):
        return func.attr == "project_child_env"
    return False


def _classify_spawns(source: str) -> tuple[list[ast.Call], list[ast.Call], list[ast.Call]]:
    """Return (all_spawns, exempted_spawns, unrouted_and_unmarked_spawns).

    "Routed" means the spawn's ``env=`` keyword is either a direct
    ``project_child_env(...)`` call, or a bare ``Name`` whose nearest
    preceding simple assignment (``Assign``/``AnnAssign`` to that name,
    anywhere earlier in the file — scope-flat, which is sufficient given
    this codebase's shape of one env-building assignment per spawning
    function) is itself a ``project_child_env(...)`` call. A spawn that is
    neither routed nor exempted is a real AC2 defect.
    """
    lines = source.splitlines()
    tree = ast.parse(source)

    assigns: list[tuple[int, str, bool]] = []
    spawns: list[ast.Call] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                assigns.append((node.lineno, node.targets[0].id, _is_helper_call(node.value)))
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if isinstance(node.target, ast.Name):
                assigns.append((node.lineno, node.target.id, _is_helper_call(node.value)))
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            if _is_spawn_call(node):
                spawns.append(node)
            self.generic_visit(node)

    _Visitor().visit(tree)

    exempted: list[ast.Call] = []
    unrouted: list[ast.Call] = []
    for call in spawns:
        env_kw = next((kw.value for kw in call.keywords if kw.arg == "env"), None)
        routed = False
        if env_kw is not None:
            if _is_helper_call(env_kw):
                routed = True
            elif isinstance(env_kw, ast.Name):
                prior = [a for a in assigns if a[1] == env_kw.id and a[0] < call.lineno]
                if prior:
                    routed = max(prior, key=lambda a: a[0])[2]
        if routed:
            continue
        above = lines[call.lineno - 2] if call.lineno - 2 >= 0 else ""
        same = lines[call.lineno - 1] if 0 <= call.lineno - 1 < len(lines) else ""
        if _MARKER in above or _MARKER in same:
            exempted.append(call)
        else:
            unrouted.append(call)

    return spawns, exempted, unrouted


@pytest.fixture(scope="module")
def scripts_root() -> Path:
    return Path(__file__).parent.parent


class TestSpawnSiteGuard:
    def test_module_list_matches_task_path_definition(self, scripts_root: Path) -> None:
        """The guard's module list is itself asserted, so a module can't silently
        join the task path (spawn a host CLI / bash -c / declared-action process)
        without also joining the guard (AC2)."""
        for relpath in _TASK_PATH_MODULES:
            assert (scripts_root / relpath).is_file(), f"missing task-path module {relpath}"

    @pytest.mark.parametrize("relpath", sorted(_TASK_PATH_MODULES))
    def test_every_spawn_is_projected_or_exempted(self, scripts_root: Path, relpath: str) -> None:
        exp_spawns, exp_markers = _TASK_PATH_MODULES[relpath]
        source = (scripts_root / relpath).read_text()
        spawns, exempted, unrouted = _classify_spawns(source)

        assert not unrouted, (
            f"{relpath}: {len(unrouted)} spawn(s) neither routed through "
            f"project_child_env() nor exempted with '# ll-no-project: <reason>': "
            f"lines {[c.lineno for c in unrouted]}"
        )
        assert len(spawns) == exp_spawns, (
            f"{relpath}: found {len(spawns)} subprocess.(run|Popen|check_output|call) "
            f"sites, expected {exp_spawns} (pinned census, ENH-3184). Update the table "
            "deliberately if a spawn was added or removed."
        )
        assert len(exempted) == exp_markers, (
            f"{relpath}: found {len(exempted)} '# ll-no-project:' exempted sites, "
            f"expected exactly {exp_markers} (pinned census, ENH-3184). A new exemption "
            "must be a deliberate table update, not a silent pass."
        )
